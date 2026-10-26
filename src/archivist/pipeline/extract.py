"""Single-pass baseline: classify each page, then extract it with its document type in one call.

    python -m archivist.pipeline.extract --split dev --run-id baseline-dev-v1 --workers 4

--citations picks how the boxes are made: S0 takes them from the extraction call as asked in P10;
S1 asks for them the way Muse Spark's grounding guidance says, around the ink rather than the
cell; S0+ink and S1+ink take S0's or S1's boxes and correct them page by page from the image
alone (pipeline/citations.py). The default follows results/citation_validation.json.

Every image in data/<split>/images/ goes through the extractor role, already Cache(Budget(...)).
A page's id is its file stem and is never interpreted. A page classified as unsupported yields no
values. An answer that is truncated or doesn't parse is asked for once more, with a note; if that
fails too, the page is recorded as failed and nothing of it is written: a page is extracted whole
or not at all.

Results go to results/runs/<run_id>/: predictions.jsonl, one PageExtraction per line, and run.json
with the model config, counts, failed pages, the cost from the spend ledger and the times. A rerun
resumes: pages already in predictions.jsonl are skipped and failed ones are tried again. A page
that failed on an error (a timeout, say) is asked afresh; one that failed on bad answers replays
them from the cache and fails the same way, so a rerun never changes what the model said.
"""

from __future__ import annotations

import argparse
import io
import json
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from pydantic import BaseModel

from archivist.doctypes import REGISTRY, UNSUPPORTED
from archivist.models import BudgetExceeded, LLMRequest, VisionLLM, describe_config, load_roles
from archivist.models.budget import BudgetGuard
from archivist.pipeline import citations
from archivist.schema import ExtractedValue

DATA_ROOT = Path("data")
RUNS_DIR = Path("results/runs")
ROLE = "extractor"
CITATION_STRATEGIES = ("S0", "S0+ink", "S1", "S1+ink")  # simplest first
CITATIONS = "S0+ink"  # adopted in results/citation_validation.json (D23)
CLASSIFY_TOKENS = 2_048
EXTRACT_TOKENS = 16_000  # a full card is 95 values with boxes, plus reasoning
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
RETRY_NOTE = (
    "\n\nYour previous answer was cut off or did not match the JSON schema. Answer again in full, "
    "as JSON that matches the schema."
)


class PageExtraction(BaseModel):
    page_id: str
    doc_type: str  # a registered DocType name, or "unsupported"
    values: list[ExtractedValue]


class ExtractionFailed(RuntimeError):
    pass


def _ask[T](
    llm: VisionLLM,
    what: str,
    prompt: str,
    image: bytes,
    schema: dict,
    max_output_tokens: int,
    parse: Callable[[object], T],
) -> T:
    """One structured-output call, asked once more if the answer can't be parsed.

    The retry adds a note to the prompt, which also makes it a different cache entry: asking the
    same request again would only replay the bad answer.
    """
    errors = []
    for attempt in (prompt, prompt + RETRY_NOTE):
        request = LLMRequest(
            role=ROLE,
            prompt=attempt,
            images=(image,),
            json_schema=schema,
            max_output_tokens=max_output_tokens,
        )
        text = llm.complete(request).text
        try:
            return parse(json.loads(text))
        except (ValueError, TypeError) as error:  # bad JSON, a missing field, a bad box
            errors.append(f"{type(error).__name__}: {error}"[:500])
    raise ExtractionFailed(f"{what}: " + " | retry: ".join(errors))


def classify(image: bytes, llm: VisionLLM) -> str:
    """The registered document type this page is, or "unsupported"."""
    names = [*REGISTRY, UNSUPPORTED]
    kinds = "\n".join(f"- {name}: {doc_type.description}" for name, doc_type in REGISTRY.items())
    prompt = (
        "Which kind of document is this scanned page? The kinds are:\n"
        f"{kinds}\n"
        f'Answer "{UNSUPPORTED}" if the page is none of these.'
    )
    schema = {
        "type": "object",
        "properties": {"doc_type": {"type": "string", "enum": names}},
        "required": ["doc_type"],
        "additionalProperties": False,
    }

    def parse(data: object) -> str:
        if not isinstance(data, dict) or data.get("doc_type") not in names:
            raise ValueError(f"expected one of {names}, got {data!r}")
        return data["doc_type"]

    return _ask(llm, "classification", prompt, image, schema, CLASSIFY_TOKENS, parse)


def extract_page(
    image_path: Path, roles: Mapping[str, object], citation_strategy: str = CITATIONS
) -> PageExtraction:
    """Classify the page, then read every field of its type; raises ExtractionFailed."""
    if citation_strategy not in CITATION_STRATEGIES:
        raise ValueError(f"citation strategy must be one of {CITATION_STRATEGIES}")
    llm = roles[ROLE]
    image = image_path.read_bytes()
    width, height = Image.open(io.BytesIO(image)).size
    page_id = image_path.stem
    doc_type = classify(image, llm)
    if doc_type == UNSUPPORTED:
        return PageExtraction(page_id=page_id, doc_type=doc_type, values=[])
    plugin = REGISTRY[doc_type]
    values = _ask(
        llm,
        f"{doc_type} extraction",
        plugin.extraction_prompt(grounding=citation_strategy.startswith("S1")),
        image,
        plugin.extraction_schema(),
        EXTRACT_TOKENS,
        lambda data: plugin.parse(page_id, data, width, height),
    )
    if citation_strategy.endswith("+ink"):
        values = citations.correct(image, values).values
    return PageExtraction(page_id=page_id, doc_type=doc_type, values=values)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_predictions(path: Path) -> list[PageExtraction]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        return [PageExtraction.model_validate_json(line) for line in lines if line.strip()]
    except ValueError as error:
        raise ValueError(f"{path} has an unreadable line; fix or remove it: {error}") from error


def run(
    images: Path,
    run_dir: Path,
    roles: Mapping[str, object],
    *,
    guard: BudgetGuard,
    config: Mapping[str, object],
    workers: int = 1,
    citation_strategy: str = CITATIONS,
) -> dict:
    """Extract every page not yet in run_dir/predictions.jsonl; returns what goes in run.json."""
    pages = sorted(p for p in images.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not pages:
        raise FileNotFoundError(f"no images in {images}")
    run_dir.mkdir(parents=True, exist_ok=True)
    predictions_path, run_path = run_dir / "predictions.jsonl", run_dir / "run.json"
    done = {p.page_id: p.doc_type for p in load_predictions(predictions_path)}
    todo = [p for p in pages if p.stem not in done]
    previous = json.loads(run_path.read_text()) if run_path.exists() else {}

    started, spent_before = _now(), guard.spent()
    failed: dict[str, str] = {}
    extracted, aborted = 0, None
    with (
        ThreadPoolExecutor(max_workers=workers) as pool,
        predictions_path.open("a", encoding="utf-8") as out,
    ):
        futures = {
            pool.submit(extract_page, page, roles, citation_strategy): page for page in todo
        }
        try:
            for future in as_completed(futures):
                page_id = futures[future].stem
                try:
                    extraction = future.result()
                except BudgetExceeded:
                    raise
                except Exception as error:  # one page failing must not stop the others
                    failed[page_id] = f"{type(error).__name__}: {error}"
                    print(f"{page_id:<14} FAILED {failed[page_id][:200]}", flush=True)
                    continue
                out.write(extraction.model_dump_json() + "\n")
                out.flush()
                done[page_id] = extraction.doc_type
                extracted += 1
                print(f"{page_id:<14} {extraction.doc_type:<14} {len(extraction.values)} values")
        except BaseException as error:
            aborted = f"{type(error).__name__}: {error}"
            pool.shutdown(cancel_futures=True)
            raise
        finally:
            session = {
                "started_at": started,
                "finished_at": _now(),
                "pages_extracted": extracted,
                "cost_usd": guard.spent() - spent_before,
                "aborted": aborted,
            }
            sessions = [*previous.get("sessions", []), session]
            record = {
                "run_id": run_dir.name,
                "images": str(images),
                "config": dict(config),
                "citations": citation_strategy,
                "counts": {
                    "pages": len(pages),
                    "extracted": len(done),
                    "failed": len(failed),
                    "by_doc_type": dict(sorted(Counter(done.values()).items())),
                },
                "failed_pages": dict(sorted(failed.items())),
                "cost_usd": sum(s["cost_usd"] for s in sessions),
                "started_at": sessions[0]["started_at"],
                "finished_at": session["finished_at"],
                "sessions": sessions,
            }
            run_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--split", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--citations", choices=CITATION_STRATEGIES, default=CITATIONS)
    args = parser.parse_args(argv)

    images = DATA_ROOT / args.split / "images"
    if not images.is_dir():
        raise SystemExit(f"{images} is missing: rebuild the split with archivist.synth.build (D17)")
    roles = load_roles()
    guard = roles[ROLE].inner.guard  # Cache -> Budget -> the guard shared by every role
    record = run(
        images,
        RUNS_DIR / args.run_id,
        roles,
        guard=guard,
        config=describe_config(),
        workers=args.workers,
        citation_strategy=args.citations,
    )
    counts = record["counts"]
    print(
        f"{counts['extracted']}/{counts['pages']} pages extracted, {counts['failed']} failed, "
        f"${record['cost_usd']:.4f} spent on this run"
    )


if __name__ == "__main__":
    main()
