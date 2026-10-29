"""The pre-registered real-pages test on the Treasury Bulletin (PREREGISTRATION_REAL.md, P29).

    python -m archivist.templates.real_test sweep --side held_out [--workers 4]
    python -m archivist.templates.real_test deep --side held_out [--workers 8]

On the development side, to try the runner, the issues, the pages a family and the allowance may
be given (--issues, --per-family, --allowance); on the held-out side every choice is the
pre-registration's and cannot be changed: every held-out issue, PER_FAMILY pages a family drawn
with SEED, an ALLOWANCE of $40. Nothing runs on the held-out side unless the code is the code
tagged TAG (frozen(): no tracked or untracked difference from the tag under FROZEN), and that is
checked before any held-out page is opened.

Roles and the five enabled types come from config/real_test.toml. A side's first start records
its caps in caps.json: the Meta cap at the Meta total of the spend ledger plus the allowance, the
Baseten cap at the Baseten total, so no Baseten call can be made. Every start, resumes included,
sets both from that file before any role is built.

sweep: every page of the side's issues classified among the five types, one call each
(extract.classify). sweep.jsonl has a line a page as it is answered, {"page", "classified_as"} or
{"page", "failed"}; a rerun asks only the pages without an answer, so a page that failed is asked
again (a transport error is asked afresh; an answer that would not parse replays from the cache and
fails the same way) and a page answered is never asked twice. sweep.json counts the pages of each
family, those set aside (unsupported) by era, and those still failed.

deep: in each family, PER_FAMILY of the pages the sweep classified into it, drawn with
random.Random(SEED).sample from their ids sorted, or all of them where it has no more; each page's
class is the sweep's. Each page is read in context (extract.read_page with S0 and the arithmetic
test's output allowance) and boxed by S0+grid (grid.assign over the page's OCR layer, with the
order fallback's blind guard), then every page is verified under policy v2 (verify.verify, SAM on
every page, no second looks). sample.json fixes the pages at the first start; predictions.jsonl is
the single read, the baseline, every value it gives accepted; boxes.jsonl has each page's box
sources and what the grid found; verdicts.jsonl and run.json are Archivist's. A rerun reads only
the pages not yet read, so a failed page is tried again and a page read is never read twice;
verification runs again over every page read, replaying from the cache what it already asked.

Writes results/real_test/<side>/. No model is called by the analysis or the labels, which come
after the runs and are not here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import threading
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from archivist.doctypes import UNSUPPORTED, DocType, from_config, recorded
from archivist.doctypes.template import TemplateType
from archivist.ingest.fraser import DEFAULT_ROOT, Manifest, Split, pdf_name
from archivist.models import BudgetExceeded, describe_config, load_roles
from archivist.models.budget import BACKEND_CAPS, LEDGER_PATH, BudgetGuard
from archivist.pipeline import extract, occlusion, reread, verify
from archivist.schema import PageExtraction, VerdictRecord
from archivist.templates import grid, ocr
from archivist.templates import test as arithmetic
from archivist.templates.pages import REAL, Page, PageRefused

CONFIG = Path("config/real_test.toml")
OUT_DIR = Path("results/real_test")
SIDES = ("development", "held_out")
FAMILIES = (
    "short_term_foreign_liabilities_as",
    "security_transactions_as_reported_by",
    "outstanding_forward_exchange_contracts",
    "receipts_and_expenditures_under_railroad",
    "total_claims_by_country",
)
SEED = 4004
PER_FAMILY = 12
ALLOWANCE = 40.0  # USD on the Meta Model API, both stages together
TAG = "run-real-treasury"
FROZEN = ("src", "config", "templates", "pyproject.toml", "uv.lock")


class NotFrozen(RuntimeError):
    pass


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def frozen(git: Callable[..., subprocess.CompletedProcess] = _git) -> None:
    """Raises NotFrozen unless TAG exists and nothing under FROZEN differs from it, tracked or
    untracked."""
    if git("rev-parse", "-q", "--verify", f"refs/tags/{TAG}").returncode != 0:
        raise NotFrozen(f"no tag {TAG}: the held-out side runs only on the tagged code")
    if git("diff", "--quiet", TAG, "--", *FROZEN).returncode != 0:
        raise NotFrozen(f"the code differs from {TAG} under {FROZEN}")
    untracked = git("status", "--porcelain", "--untracked-files=all", "--", *FROZEN).stdout
    if untracked.strip():
        raise NotFrozen(f"files under {FROZEN} not in {TAG}:\n{untracked}")


@cache
def _split(root: Path) -> Split:
    return Split.model_validate_json((root / "split.json").read_text(encoding="utf-8"))


@cache
def _manifest(root: Path) -> Manifest:
    return Manifest.model_validate_json((root / "manifest.json").read_text(encoding="utf-8"))


@cache
def _hashes(root: Path) -> dict[tuple[str, int], str]:
    return {(p.issue, p.page): p.sha256 for p in _manifest(root).pages}


def issues_of(side: str, root: Path = DEFAULT_ROOT) -> list[str]:
    return list(getattr(_split(root), side))


def page_refs(issues: Sequence[str], root: Path = DEFAULT_ROOT) -> list[str]:
    """Every page of the issues, in the manifest's order: "<issue>_p<NNN>"."""
    wanted = set(issues)
    return [f"{p.issue}_p{p.page:03d}" for p in _manifest(root).pages if p.issue in wanted]


def resolve(ref: str, side: str, root: Path = DEFAULT_ROOT) -> Page:
    """A Treasury page of the side's issues, its image matching the manifest; else PageRefused."""
    found = REAL.fullmatch(ref)
    if found is None:
        raise PageRefused(f"{ref}: not a Treasury Bulletin page")
    issue, number = found["issue"], int(found["page"])
    if issue not in issues_of(side, root):
        raise PageRefused(f"{ref}: issue {issue} is not on the {side} side")
    expected = _hashes(root).get((issue, number))
    path = root / "pages" / issue / f"p{number:03d}.jpg"
    if expected is None or not path.is_file():
        raise PageRefused(f"{ref}: not in the manifest, or {path} is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise PageRefused(f"{ref}: {path} does not match the manifest")
    return Page(ref, ref, path)


_PDFIUM = threading.Lock()  # pdfium fails to load pages when two threads open documents at once


def words(page: Page, root: Path = DEFAULT_ROOT) -> tuple[ocr.Word, ...]:
    """The page's OCR layer, one page at a time across the deep check's workers."""
    found = REAL.fullmatch(page.ref)
    with _PDFIUM:
        return ocr.layer(root / "pdf" / pdf_name(found["issue"]), int(found["page"]), page.path)


def sample(classes: Mapping[str, str], per_family: int, seed: int = SEED) -> dict[str, list[str]]:
    """Each family's pages for the deep check: per_family of them drawn from their ids sorted with
    a fresh random.Random(seed), or all of them where it has no more; each list sorted."""
    by_family: dict[str, list[str]] = defaultdict(list)
    for ref, name in classes.items():
        by_family[name].append(ref)
    out = {}
    for family in FAMILIES:
        refs = sorted(by_family.get(family, []))
        chosen = refs if len(refs) <= per_family else random.Random(seed).sample(refs, per_family)
        out[family] = sorted(chosen)
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def caps(out: Path, allowance: float, ledger: Path = LEDGER_PATH) -> dict[str, float]:
    """The side's caps, recorded at its first start and read back on every later one."""
    path = out / "caps.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    guard = BudgetGuard(0.0, ledger)
    record = {
        "meta": round(guard.spent("meta") + allowance, 6),
        "baseten": round(guard.spent("baseten"), 6),
        "allowance": allowance,
        "recorded_at": _now(),
    }
    out.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def set_caps(record: Mapping[str, float]) -> None:
    for backend, (variable, _) in BACKEND_CAPS.items():
        os.environ[variable] = str(record[backend])


def _types(config: Path) -> dict[str, DocType]:
    doc_types = from_config(config)
    if tuple(doc_types) != FAMILIES:
        raise ValueError(f"{config} must enable the five families, in order: {FAMILIES}")
    return doc_types


# --- The sweep ----------------------------------------------------------------------------------


def classes(out: Path) -> dict[str, str]:
    """Each page's class from sweep.jsonl, the last answer for a page standing."""
    answered: dict[str, str] = {}
    for line in _lines(out / "sweep.jsonl"):
        if "classified_as" in line:
            answered[line["page"]] = line["classified_as"]
    return answered


def sweep(
    refs: Sequence[str],
    side: str,
    out: Path,
    llm: object,
    doc_types: Mapping[str, DocType],
    *,
    workers: int = 4,
    root: Path = DEFAULT_ROOT,
) -> dict:
    """Classify every page not yet answered; returns what goes in sweep.json."""
    out.mkdir(parents=True, exist_ok=True)
    done = classes(out)
    todo = [ref for ref in refs if ref not in done]
    lock = threading.Lock()

    def one(ref: str) -> dict:
        image = resolve(ref, side, root).path.read_bytes()
        try:
            return {"page": ref, "classified_as": extract.classify(image, llm, doc_types)}
        except BudgetExceeded:
            raise
        except Exception as error:  # one page failing must not stop the others
            return {"page": ref, "failed": f"{type(error).__name__}: {error}"[:500]}

    with (out / "sweep.jsonl").open("a", encoding="utf-8") as log:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(one, ref) for ref in todo]):
                line = future.result()
                with lock:
                    log.write(json.dumps(line) + "\n")
                    log.flush()
    answered = classes(out)
    failed = sorted(ref for ref in refs if ref not in answered)
    era = defaultdict(Counter)
    for ref in refs:
        if ref in answered:
            era["1939-1942" if ref < "1950" else "1982-1994"][answered[ref]] += 1
    return {
        "side": side,
        "pages": len(refs),
        "classified": len(answered),
        "by_family": {f: sum(answered.get(r) == f for r in refs) for f in FAMILIES},
        "set_aside": sum(answered.get(r) == UNSUPPORTED for r in refs),
        "by_era": {e: dict(sorted(c.items())) for e, c in sorted(era.items())},
        "failed": failed,
    }


# --- The deep check -----------------------------------------------------------------------------


def read_one(
    page: Page,
    doc_type: TemplateType,
    roles: Mapping[str, object],
    layer: Sequence[ocr.Word],
    workers: int,
) -> tuple[PageExtraction, dict]:
    """The single read of one page and its S0+grid boxes; raises ExtractionFailed."""
    image = page.path.read_bytes()
    values = extract.read_page(
        image,
        page.page_id,
        roles[extract.ROLE],
        doc_type,
        "S0",
        arithmetic.output_tokens(doc_type),
    )
    check = arithmetic.blind_check(image, page.page_id, doc_type, roles[reread.ROLE], workers)
    values, sources, found = grid.assign(values, doc_type, image, layer, check)
    extraction = PageExtraction(page_id=page.page_id, doc_type=doc_type.name, values=values)
    return extraction, {"page": page.ref, "box_sources": sources, "grid": found}


def deep(
    out: Path,
    side: str,
    roles: Mapping[str, object],
    doc_types: Mapping[str, DocType],
    *,
    per_family: int = PER_FAMILY,
    workers: int = 8,
    root: Path = DEFAULT_ROOT,
    layer_of: Callable[[Page], Sequence[ocr.Word]] | None = None,
) -> tuple[list[VerdictRecord], dict]:
    """Read and box the sampled pages not yet read, then verify every page read; returns the
    verdicts and what goes in run.json, less the costs."""
    layer_of = layer_of or (lambda page: words(page, root))
    path = out / "sample.json"
    if path.exists():
        chosen = json.loads(path.read_text(encoding="utf-8"))["pages"]
    else:
        swept = classes(out)
        if not swept:
            raise FileNotFoundError(f"no sweep in {out}: run the sweep first")
        chosen = sample(swept, per_family)
        record = {"seed": SEED, "per_family": per_family, "pages": chosen, "drawn_at": _now()}
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    family_of = {ref: family for family, refs in chosen.items() for ref in refs}

    predictions, boxes, failures = (
        out / name for name in ("predictions.jsonl", "boxes.jsonl", "failed.jsonl")
    )
    read = {line["page_id"] for line in _lines(predictions)}
    todo = [ref for ref in sorted(family_of) if ref not in read]
    lock = threading.Lock()

    def one(ref: str) -> None:
        page = resolve(ref, side, root)
        doc_type = doc_types[family_of[ref]]
        try:
            extraction, record = read_one(page, doc_type, roles, layer_of(page), workers)
        except BudgetExceeded:
            raise
        except Exception as error:  # one page failing must not stop the others
            line = {"page": ref, "failed": f"{type(error).__name__}: {error}"[:1000]}
            with lock, failures.open("a", encoding="utf-8") as log:
                log.write(json.dumps(line) + "\n")
            print(f"{ref}: the read failed", flush=True)
            return
        with lock:
            with boxes.open("a", encoding="utf-8") as log:
                log.write(json.dumps(record) + "\n")
            with predictions.open("a", encoding="utf-8") as log:
                log.write(extraction.model_dump_json() + "\n")
        print(f"{ref}: {len(extraction.values)} cells read", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(one, ref) for ref in todo]):
            future.result()

    pages = sorted(extract.load_predictions(predictions), key=lambda p: p.page_id)
    images = {p.page_id: resolve(p.page_id, side, root).path for p in pages}
    verdicts, calls = verify.verify(
        pages,
        images,
        roles,
        correct_citations=False,
        doc_types=doc_types,
        workers=workers,
        policy="v2",
        second_looks=False,
    )
    sources = Counter(s for line in _lines(boxes) for s in line["box_sources"].values())
    done = {p.page_id for p in pages}
    record = {
        "sample": chosen,
        "pages_read": len(pages),
        "failed": sorted(set(family_of) - done),
        "box_sources": dict(sorted(sources.items())),
        "counts": {"pages": len(pages), **verify._counts(verdicts)},
        "calls": calls,
    }
    return verdicts, record


# --- The command --------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("stage", choices=("sweep", "deep"))
    parser.add_argument("--side", choices=SIDES, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--issues", nargs="+", help="development side only: default every issue")
    parser.add_argument("--per-family", type=int, help=f"development only: default {PER_FAMILY}")
    parser.add_argument("--allowance", type=float, help=f"development only: default {ALLOWANCE}")
    args = parser.parse_args(argv)
    if args.side == "held_out":
        if args.issues or args.per_family is not None or args.allowance is not None:
            parser.error("the held-out side takes the pre-registration's choices alone")
        frozen()  # before any held-out page is opened
    issues = args.issues or issues_of(args.side)
    stray = sorted(set(issues) - set(issues_of(args.side)))
    if stray:
        parser.error(f"not {args.side} issues: {stray}")

    out = OUT_DIR / args.side
    record = caps(out, ALLOWANCE if args.allowance is None else args.allowance)
    set_caps(record)
    roles = load_roles(CONFIG)
    doc_types = _types(CONFIG)
    guard = roles[extract.ROLE].inner.guard
    before, started = guard.spent("meta"), _now()
    common = {
        "config": describe_config(CONFIG),
        "doc_types": recorded(doc_types),
        "caps": record,
        "started_at": started,
    }
    if args.stage == "sweep":
        llm = roles[extract.ROLE]
        summary = sweep(page_refs(issues), args.side, out, llm, doc_types, workers=args.workers)
        summary |= common | {
            "issues": issues,
            "cost_usd": guard.spent("meta") - before,
            "finished_at": _now(),
        }
        (out / "sweep.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            f"{summary['classified']} of {summary['pages']} pages classified: "
            f"{summary['by_family']}, "
            f"{summary['set_aside']} set aside, {len(summary['failed'])} failed; "
            f"${summary['cost_usd']:.4f} spent"
        )
        return
    verdicts, summary = deep(
        out,
        args.side,
        roles,
        doc_types,
        per_family=PER_FAMILY if args.per_family is None else args.per_family,
        workers=args.workers,
    )
    (out / verify.VERDICTS_FILE).write_text(
        "".join(v.model_dump_json() + "\n" for v in verdicts), encoding="utf-8"
    )
    cost_full = summary["calls"].pop("cost_full_usd")
    summary = common | summary | {
        "citations": grid.STRATEGY,
        "policy": {
            "version": "v2",
            "second_looks": False,
            "occlusion_prompts": list(occlusion.PROMPTS),
            "occlusion_cover": occlusion.COVER,
            "reread_padding": {"vertical": reread.PAD_Y, "horizontal": reread.PAD_X},
        },
        "cost_usd": guard.spent("meta") - before,
        "cost_full_usd": cost_full,
        "finished_at": _now(),
    }
    (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    counts = summary["counts"]
    print(
        f"{counts['fields']} cells on {counts['pages']} pages ({len(summary['failed'])} failed): "
        f"{counts['by_status']}; boxes {summary['box_sources']}; {counts['occluded']} occluded; "
        f"${summary['cost_usd']:.4f} spent"
    )


if __name__ == "__main__":
    main()
