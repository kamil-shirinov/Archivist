"""Verification: a verdict for every extracted value, with its evidence (D25).

    python -m archivist.pipeline.verify --run baseline-dev-v1 --out archivist-dev-v1 --workers 4

The policy, pre-registered before it is scored on the test set:

- Money fields (debit, credit, balance, brought and carried forward, the memo's amount) are
  verified by the arithmetic: accepted when no check involving them fails.
- Every other field (dates, descriptions, names, account, sheet and memo numbers, the amount in
  words, ledger references) gets a blind re-read (reread.py), and is accepted when the re-read
  agrees with the extracted value after normalisation.
- A field implicated by a failed check, or whose re-read disagrees or is illegible, goes to
  review. Flagged money fields are re-read too, and both readings are kept as evidence. Where a
  check suggests a value and the re-read agrees with that suggestion, the suggestion is attached
  as the proposed correction. The extracted value itself is never changed.
- Occluded fields (occlusion.py: a stamp or stain covers at least 10% of the box) are re-read
  too, money included, and accepted only if everything agrees, with lower confidence.
- A field the extractor abstained on (null) is abstained, and is not re-read.
- A field that needs a re-read but has no citation box, or whose re-read call fails, goes to
  review: it could not be verified.

Confidence, for the risk–coverage curve: 0.99 accepted (checked, or re-read agreement); 0.9 the
same but occluded; 0.5 for review with a proposed correction; 0.3 for review without one (an
unresolved disagreement); 0.0 when the extractor abstained.

Unresolvable cross-document flags are notes: kept as evidence, never a reason for review.
Agreement compares canonical forms: money as an amount (the clerk's notation, ledger.money),
dates as a calendar date, account and memo numbers as digits, the amount in words as its letters
(D22), anything else as text with spacing and case ignored.

Re-reads use the corrected citation boxes: a run extracted with S0 or S1 is corrected here as
S0+ink would (citations.py, D23), and each corrected box is widened to the extractor's own
horizontal extent before cropping (reread.widen). Both the corrected box and the region sent to
the re-reader are part of the evidence. Every model call
goes through the roles, so a rerun replays the cache and spends nothing.

Writes results/runs/<out>/verdicts.jsonl, one VerdictRecord (a FieldVerdict with its page, doc
type and evidence) per extracted field, and run.json with the config, counts and cost.
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from archivist.doctypes import REGISTRY, is_unresolvable
from archivist.doctypes.ledger import calendar_date, money
from archivist.models import BudgetExceeded, Region, describe_config, load_roles
from archivist.models.budget import BudgetGuard
from archivist.pipeline import citations, occlusion, reread
from archivist.pipeline.checks import run_checks
from archivist.pipeline.extract import IMAGE_SUFFIXES, RUNS_DIR, PageExtraction, load_predictions
from archivist.schema import BBox, Citation, ExtractedValue, FieldVerdict, Flag

MONEY_FIELDS = frozenset(
    {"debit", "credit", "balance", "brought_forward", "carried_forward", "amount"}
)
DIGIT_FIELDS = frozenset({"account_no", "memo_no"})
ACCEPTED = 0.99
ACCEPTED_OCCLUDED = 0.9
PROPOSED = 0.5
UNRESOLVED = 0.3
ABSTAINED = 0.0
CONFIDENCE = {
    "accepted": ACCEPTED,
    "accepted_occluded": ACCEPTED_OCCLUDED,
    "review_proposed": PROPOSED,
    "review_unresolved": UNRESOLVED,
    "abstained": ABSTAINED,
}
VERDICTS_FILE = "verdicts.jsonl"

ReReadStatus = Literal["agrees", "disagrees", "illegible", "failed", "no_citation", "not_reread"]


class Occluder(BaseModel):
    label: str
    bbox: BBox
    cover: float  # share of the field's box this region covers


class Evidence(BaseModel):
    route: Literal["arithmetic", "reread"]  # what verifies the field when nothing else applies
    citation: Citation | None  # the corrected box
    crop: BBox | None = None  # the region of the page the re-reader saw
    occluded_by: list[Occluder] = []
    reread: str | None = None  # the blind re-read; None when illegible or not re-read
    reread_status: ReReadStatus
    proposed: str | None = None  # a check's suggestion that the re-read agrees with


class VerdictRecord(FieldVerdict):
    page_id: str
    doc_type: str
    evidence: Evidence


@dataclass(frozen=True)
class ReRead:
    value: str | None  # None: illegible, or the call failed
    error: str | None = None
    crop: BBox | None = None


def field_kind(field_id: str) -> str:
    return field_id.rsplit(":", 1)[-1]


def canonical(field_id: str, text: str) -> str:
    """The form two readings of a field are compared in; see the module docstring."""
    if not text.strip():
        return ""
    kind = field_kind(field_id)
    if kind in MONEY_FIELDS and (amount := money(text)) is not None:
        return str(amount)
    if kind == "date" and (day := calendar_date(text)) is not None:
        return day.isoformat()
    if kind in DIGIT_FIELDS and (digits := re.sub(r"\D", "", text)):
        return digits
    if kind == "amount_words" and (letters := re.sub(r"[^A-Z]", "", text.upper())):
        return letters
    return " ".join(text.split()).upper()


def same_reading(field_id: str, a: str, b: str) -> bool:
    return canonical(field_id, a) == canonical(field_id, b)


def needs_reread(value: ExtractedValue, flags: Sequence[Flag], occluded: bool) -> bool:
    """Whether the policy asks for a blind re-read of this field."""
    if value.abstained or value.value is None:
        return False
    failed = any(not is_unresolvable(f) for f in flags)
    return field_kind(value.field_id) not in MONEY_FIELDS or occluded or failed


def _reread_status(value: ExtractedValue, reading: ReRead | None) -> ReReadStatus:
    if value.citation is None:
        return "no_citation"
    if reading is None:
        raise ValueError(f"{value.field_id} needs a re-read and has none")
    if reading.error is not None:
        return "failed"
    if reading.value is None:
        return "illegible"
    return "agrees" if same_reading(value.field_id, reading.value, value.value) else "disagrees"


REREAD_DETAIL = {
    "illegible": "the blind re-read found it illegible",
    "no_citation": "no citation box to re-read, so it could not be verified",
}


def decide(
    page_id: str,
    doc_type: str,
    value: ExtractedValue,
    flags: Sequence[Flag],
    occluders: Sequence[Occluder],
    reading: ReRead | None,
) -> VerdictRecord:
    """The policy for one field: its flags from the checks, what covers it, its re-read if any."""
    route = "arithmetic" if field_kind(value.field_id) in MONEY_FIELDS else "reread"
    fid = value.field_id
    notes = [
        Flag(field_id=fid, check="occlusion", detail=f"{o.cover:.0%} covered by {o.label}")
        for o in occluders
    ]
    if value.abstained or value.value is None:
        return VerdictRecord(
            field_id=value.field_id,
            value=None,
            confidence=ABSTAINED,
            status="abstained",
            flags=[*flags, *notes],
            page_id=page_id,
            doc_type=doc_type,
            evidence=Evidence(
                route=route,
                citation=value.citation,
                occluded_by=list(occluders),
                reread_status="not_reread",
            ),
        )

    failed = [f for f in flags if not is_unresolvable(f)]
    if needs_reread(value, flags, bool(occluders)):
        status = _reread_status(value, reading)
    else:
        status = "not_reread"
    read = reading.value if reading is not None and status != "no_citation" else None
    proposed = None
    if status == "disagrees":
        suggestions = [f.suggested for f in failed if f.suggested is not None]
        proposed = next((s for s in suggestions if same_reading(fid, s, read)), None)
        detail = f"the blind re-read reads {read!r}"
        if proposed is not None:
            detail += f", as a check suggests ({proposed}): proposed as the correction"
        notes.append(Flag(field_id=fid, check="reread", detail=detail, suggested=proposed))
    elif status == "failed":
        detail = f"the re-read failed: {reading.error}"
        notes.append(Flag(field_id=fid, check="reread", detail=detail))
    elif status in REREAD_DETAIL:
        notes.append(Flag(field_id=fid, check="reread", detail=REREAD_DETAIL[status]))

    review = bool(failed) or status in ("disagrees", "illegible", "failed", "no_citation")
    if review:
        confidence = PROPOSED if proposed is not None else UNRESOLVED
    else:
        confidence = ACCEPTED_OCCLUDED if occluders else ACCEPTED
    return VerdictRecord(
        field_id=value.field_id,
        value=value.value,  # never changed: a correction is only ever proposed
        confidence=confidence,
        status="review" if review else "accepted",
        flags=[*flags, *notes],
        page_id=page_id,
        doc_type=doc_type,
        evidence=Evidence(
            route=route,
            citation=value.citation,
            occluded_by=list(occluders),
            crop=reading.crop if reading is not None else None,
            reread=read,
            reread_status=status,
            proposed=proposed,
        ),
    )


@dataclass
class _Page:
    extraction: PageExtraction
    image: bytes
    values: list[ExtractedValue]  # with corrected citations
    reach: dict[str, BBox]  # the extractor's own boxes, when corrected here
    regions: list[Region]


def _occluders(value: ExtractedValue, regions: Sequence[Region]) -> list[Occluder]:
    return [
        Occluder(label=r.label, bbox=r.bbox, cover=round(share, 4))
        for r, share in occlusion.occluders(value, regions)
    ]


def verify(
    pages: Sequence[PageExtraction],
    images: Mapping[str, Path],
    roles: Mapping[str, object],
    *,
    correct_citations: bool,
    workers: int = 1,
) -> tuple[list[VerdictRecord], dict]:
    """Every value of every page through the policy; returns the verdicts and the call counts."""
    segmenter, llm = roles[occlusion.ROLE], roles[reread.ROLE]
    by_field: dict[str, list[Flag]] = defaultdict(list)
    for flag in run_checks(pages):
        by_field[flag.field_id].append(flag)

    def prepare(page: PageExtraction) -> _Page:
        image = images[page.page_id].read_bytes()
        values, reach = page.values, {}
        if correct_citations and values:
            values = citations.correct(image, values).values
            reach = {v.field_id: v.citation.bbox for v in page.values if v.citation is not None}
        regions = occlusion.detect(image, segmenter) if values else []
        return _Page(page, image, values, reach, regions)

    def read_one(job: tuple[bytes, BBox, str]) -> tuple[ReRead, bool]:
        image, box, prompt = job
        picture = Image.open(io.BytesIO(image))
        seen = reread.crop_box(box, *picture.size)
        try:
            text, cached = reread.reread(picture, box, prompt, llm)
        except BudgetExceeded:
            raise
        except Exception as error:  # one field failing must not stop the others
            return ReRead(None, f"{type(error).__name__}: {error}"[:300], seen), False
        return ReRead(text, crop=seen), cached

    with ThreadPoolExecutor(max_workers=workers) as pool:
        prepared = list(pool.map(prepare, sorted(pages, key=lambda p: p.page_id)))
        jobs, keys = [], []
        for page in prepared:
            plugin = REGISTRY.get(page.extraction.doc_type)
            for value in page.values:
                occluded = bool(occlusion.occluders(value, page.regions))
                if value.citation is not None and needs_reread(
                    value, by_field[value.field_id], occluded
                ):
                    box = reread.widen(value.citation.bbox, page.reach.get(value.field_id))
                    jobs.append((page.image, box, plugin.reread_prompt(value.field_id)))
                    keys.append(value.field_id)
        results = list(pool.map(read_one, jobs))
    readings = {key: reading for key, (reading, _) in zip(keys, results, strict=True)}

    verdicts = [
        decide(
            page.extraction.page_id,
            page.extraction.doc_type,
            value,
            by_field[value.field_id],
            _occluders(value, page.regions),
            readings.get(value.field_id),
        )
        for page in prepared
        for value in page.values
    ]
    calls = {
        "segmenter_pages": sum(bool(p.values) for p in prepared),
        "regions": dict(sorted(Counter(r.label for p in prepared for r in p.regions).items())),
        "rereads": len(jobs),
        "rereads_from_cache": sum(cached for _, cached in results),
        "rereads_failed": sum(r.error is not None for r, _ in results),
    }
    return verdicts, calls


def _counts(verdicts: Sequence[VerdictRecord]) -> dict:
    return {
        "fields": len(verdicts),
        "by_status": dict(sorted(Counter(v.status for v in verdicts).items())),
        "by_confidence": {
            str(c): n for c, n in sorted(Counter(v.confidence for v in verdicts).items())
        },
        "by_route": dict(sorted(Counter(v.evidence.route for v in verdicts).items())),
        "by_reread_status": dict(
            sorted(Counter(v.evidence.reread_status for v in verdicts).items())
        ),
        "occluded": sum(bool(v.evidence.occluded_by) for v in verdicts),
        "proposed_corrections": sum(v.evidence.proposed is not None for v in verdicts),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def load_verdicts(path: Path) -> list[VerdictRecord]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [VerdictRecord.model_validate_json(line) for line in lines if line.strip()]


def run(
    source_dir: Path,
    out_dir: Path,
    roles: Mapping[str, object],
    *,
    guard: BudgetGuard,
    config: Mapping[str, object],
    workers: int = 1,
) -> dict:
    """Verify the source run's predictions into out_dir; returns what goes in run.json."""
    predictions = source_dir / "predictions.jsonl"
    if not predictions.exists():
        raise FileNotFoundError(f"{predictions} is missing: run archivist.pipeline.extract first")
    source = json.loads((source_dir / "run.json").read_text())
    strategy = source.get("citations", "S0")  # runs before --citations existed were S0
    images_dir = Path(source["images"])
    images = {p.stem: p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES}
    pages = load_predictions(predictions)
    missing = sorted(p.page_id for p in pages if p.page_id not in images)
    if missing:
        raise FileNotFoundError(f"no image in {images_dir} for {missing[:5]}")

    started, spent_before = _now(), guard.spent()
    verdicts, calls = verify(
        pages, images, roles, correct_citations=not strategy.endswith("+ink"), workers=workers
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(v.model_dump_json() + "\n" for v in verdicts)
    (out_dir / VERDICTS_FILE).write_text(text, encoding="utf-8")
    record = {
        "run_id": out_dir.name,
        "source_run": source_dir.name,
        "images": str(images_dir),
        "config": dict(config),
        "citations": strategy if strategy.endswith("+ink") else f"{strategy}+ink (corrected here)",
        "policy": {
            "money_fields": sorted(MONEY_FIELDS),
            "confidence": CONFIDENCE,
            "occlusion_prompts": list(occlusion.PROMPTS),
            "occlusion_cover": occlusion.COVER,
            "reread_padding": {"vertical": reread.PAD_Y, "horizontal": reread.PAD_X},
        },
        "counts": {"pages": len(pages), **_counts(verdicts)},
        "calls": calls,
        "cost_usd": guard.spent() - spent_before,
        "started_at": started,
        "finished_at": _now(),
    }
    (out_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run", required=True, help="the extraction run to verify")
    parser.add_argument("--out", required=True, help="the run id to write the verdicts to")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    roles = load_roles()
    guard = roles[reread.ROLE].inner.guard  # Cache -> Budget -> the guard shared by every role
    record = run(
        RUNS_DIR / args.run,
        RUNS_DIR / args.out,
        roles,
        guard=guard,
        config=describe_config(),
        workers=args.workers,
    )
    counts, calls = record["counts"], record["calls"]
    print(
        f"{counts['fields']} fields on {counts['pages']} pages: {counts['by_status']}; "
        f"{counts['occluded']} occluded, {counts['proposed_corrections']} corrections proposed"
    )
    print(
        f"{calls['rereads']} re-reads ({calls['rereads_from_cache']} from cache, "
        f"{calls['rereads_failed']} failed); ${record['cost_usd']:.4f} spent"
    )


if __name__ == "__main__":
    main()
