"""Verification: a verdict for every extracted value, with its evidence (D25, D26, D29).

    python -m archivist.pipeline.verify --run baseline-dev-v1 --out archivist-dev-v2 --workers 4

--config picks the file that maps roles to models (default config/models.toml), --policy whose
outcome a verdict's own status, confidence and proposal are (default POLICY). Every verdict
records the outcome of both policies, v2 and v3, so both are scored from one run (as_policy).

Policy v2, pre-registered before it is scored on the test set:

- Every value is read twice (D26): once in context, by the extractor reading the whole page, and
  once in isolation, by a blind re-read of its cell alone (reread.py). Money fields are re-read
  like any other: reading a page in context can make a mistake add up (a misread debit carried
  through every later balance), and a re-reader that sees one cell at a time can't.
- A field is accepted only when the two reads agree after normalisation and no check on the
  extracted values involving it fails.
- The document checks run twice: on the extracted values and on the re-read values. Where a
  re-read disagrees with the extraction, the re-read value is proposed as the correction if the
  re-read values hold up: no check on the re-read values fails on the field, and some equation
  of the documents' arithmetic holds for it with every value in it read (ledger.balanced). That
  covers both re-read values passing a check the extracted ones fail and a consistent misreading
  whose extracted chain adds up as well as the re-read one. Failing that, a check's suggestion
  the re-read agrees with is proposed, as before. Both chains' flags are kept as evidence.
- A disagreement, a failed check, an illegible or failed re-read, or a field without a citation
  box to re-read goes to review. The extracted value itself is never changed; a correction is
  only ever proposed.
- Occluded fields (occlusion.py: a stamp or stain covers at least 10% of the box) are accepted
  only if everything agrees, with lower confidence.
- A field the extractor abstained on (null) is abstained, and is not re-read.

Policy v3 is v2 with a second look before an alarm. When the first re-read disagrees with the
extractor or finds the field illegible, the re-reader reads it once more from a differently padded
crop of the same box (reread.SECOND_PAD_Y, SECOND_PAD_X). The extracted value is accepted only if
a look agrees with it and no check on the extracted values involving it fails. If both looks agree
with each other but not with the extractor, their value is proposed and the field goes to review;
in every other case it goes to review with nothing proposed. A second look that fails (a timeout,
say) is no look: the field keeps its v2 outcome. Every other field is decided as in v2.

Confidence, for the risk–coverage curve, under either policy: 0.99 accepted; 0.9 the same but
occluded; 0.5 for review with a proposed correction; 0.3 for review without one (an unresolved
disagreement); 0.0 when the extractor abstained.

Unresolvable cross-document flags are notes: kept as evidence, never a reason for review. A check
that fails only on the re-read values is evidence too: when the two reads agree on a field, the
failure lies with a neighbour's re-read, and that neighbour goes to review on its disagreement.
Agreement compares canonical forms: money as an amount (the clerk's notation, ledger.money),
dates as a calendar date, account and memo numbers as digits, the amount in words as its letters
(D22), anything else as text with spacing and case ignored.

Re-reads use the corrected citation boxes: a run extracted with S0 or S1 is corrected here as
S0+ink would (citations.py, D23), and each corrected box is widened to the extractor's own
horizontal extent, kept on the citation as raw_bbox, before cropping (reread.region). Both the
corrected box and the regions sent to the re-reader are part of the evidence. Every model call
goes through the roles, so a rerun replays the cache and spends nothing.

Writes results/runs/<out>/verdicts.jsonl, one VerdictRecord (a FieldVerdict with its page, doc
type, evidence and both policies' outcomes) per extracted field, and run.json with the config,
counts and cost: cost_usd is what this run spent, cost_full_usd what its calls cost when they were
first made, cache hits included, i.e. what the configuration costs on pages it has never seen.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import threading
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel

from archivist.doctypes import REGISTRY, is_unresolvable
from archivist.doctypes.ledger import balanced, calendar_date, money
from archivist.models import BudgetExceeded, Region, describe_config, load_roles
from archivist.models.budget import BudgetGuard
from archivist.models.registry import CONFIG_PATH
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
Policy = Literal["v2", "v3"]
POLICIES: tuple[Policy, ...] = ("v2", "v3")
# Whose outcome a verdict's own status, confidence and proposal are: the headline policy (D29,
# results/arms_compare.json).
POLICY: Policy = "v2"
SECOND_LOOK: frozenset[str] = frozenset({"disagrees", "illegible"})  # what a second look is for
Proposer = Literal["reread_chain", "check", "second_look"]


class Occluder(BaseModel):
    label: str
    bbox: BBox
    cover: float  # share of the field's box this region covers


class Evidence(BaseModel):
    route: Literal["arithmetic", "reread"]  # arithmetic: money, checked by sums as well as re-read
    citation: Citation | None  # the corrected box, and the extractor's own as raw_bbox
    crop: BBox | None = None  # the region of the page the re-reader saw
    occluded_by: list[Occluder] = []
    reread: str | None = None  # the blind re-read; None when illegible or not re-read
    reread_status: ReReadStatus
    reread_flags: list[Flag] = []  # the checks run on the re-read values: the second chain
    reread_balances: bool = False  # an equation holds for the re-read value (ledger.balanced)
    proposed: str | None = None  # the proposed correction, under the verdict's own policy
    proposed_by: Proposer | None = None
    second_look: str | None = None  # v3's second look; None when illegible or not taken
    second_look_status: ReReadStatus = "not_reread"  # compared with the extracted value
    second_crop: BBox | None = None  # the region of the page the second look saw


class PolicyOutcome(BaseModel):
    status: Literal["accepted", "review", "abstained"]
    confidence: float
    proposed: str | None = None
    proposed_by: Proposer | None = None


class VerdictRecord(FieldVerdict):
    page_id: str
    doc_type: str
    evidence: Evidence
    policy: str = "v2"  # whose outcome status, confidence and evidence.proposed are
    policies: dict[str, PolicyOutcome] = {}  # every policy's outcome; empty before v3 existed


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


def needs_reread(value: ExtractedValue) -> bool:
    """Whether the policy asks for a blind re-read of this field: of every one read (D26)."""
    return not value.abstained and value.value is not None


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


def _proposal(
    fid: str, read: str, failed: Sequence[Flag], reread_failed: Sequence[Flag], balances: bool
) -> tuple[str | None, str | None, str]:
    """The proposed correction for a disagreement, what proposed it, and the note's wording."""
    detail = f"the blind re-read reads {read!r}"
    if balances and not reread_failed:
        if failed:
            why = "the re-read values pass the checks the extracted values fail"
        else:
            why = "the extracted values add up, but so do the re-read values, which disagree"
        return read, "reread_chain", f"{detail}; {why}: proposed as the correction"
    suggestions = [f.suggested for f in failed if f.suggested is not None]
    suggested = next((s for s in suggestions if same_reading(fid, s, read)), None)
    if suggested is not None:
        detail += f", as a check suggests ({suggested}): proposed as the correction"
        return suggested, "check", detail
    return None, None, detail


def _outcome(
    review: bool, proposed: str | None, proposed_by: Proposer | None, occluded: bool
) -> PolicyOutcome:
    if not review:
        confidence = ACCEPTED_OCCLUDED if occluded else ACCEPTED
        return PolicyOutcome(status="accepted", confidence=confidence)
    confidence = PROPOSED if proposed is not None else UNRESOLVED
    return PolicyOutcome(
        status="review", confidence=confidence, proposed=proposed, proposed_by=proposed_by
    )


def _second_detail(status: ReReadStatus, second: ReRead) -> str:
    if status == "failed":
        return f"the second look failed: {second.error}"
    if status == "illegible":
        return "a second look, from a wider crop, found it illegible"
    return f"a second look, from a wider crop, reads {second.value!r}"


def decide(
    page_id: str,
    doc_type: str,
    value: ExtractedValue,
    flags: Sequence[Flag],
    occluders: Sequence[Occluder],
    reading: ReRead | None,
    reread_flags: Sequence[Flag] = (),
    balances: bool = False,
    second: ReRead | None = None,
    policy: Policy = POLICY,
) -> VerdictRecord:
    """Both policies for one field: its flags from the checks on the extracted values, what covers
    it, its re-read, the flags from the checks on the re-read values, whether an equation holds
    for its re-read value, and its second look (None if not taken). The verdict's own status,
    confidence and proposal are `policy`'s.
    """
    route = "arithmetic" if field_kind(value.field_id) in MONEY_FIELDS else "reread"
    fid = value.field_id
    notes = [
        Flag(field_id=fid, check="occlusion", detail=f"{o.cover:.0%} covered by {o.label}")
        for o in occluders
    ]
    if value.abstained or value.value is None:
        abstained = PolicyOutcome(status="abstained", confidence=ABSTAINED)
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
            policy=policy,
            policies=dict.fromkeys(POLICIES, abstained),
        )

    failed = [f for f in flags if not is_unresolvable(f)]
    reread_failed = [f for f in reread_flags if not is_unresolvable(f)]
    status = _reread_status(value, reading)
    read = reading.value if reading is not None and status != "no_citation" else None
    proposed = proposed_by = None
    if status == "disagrees":
        proposed, proposed_by, detail = _proposal(fid, read, failed, reread_failed, balances)
        notes.append(Flag(field_id=fid, check="reread", detail=detail, suggested=proposed))
    elif status == "failed":
        detail = f"the re-read failed: {reading.error}"
        notes.append(Flag(field_id=fid, check="reread", detail=detail))
    elif status in REREAD_DETAIL:
        notes.append(Flag(field_id=fid, check="reread", detail=REREAD_DETAIL[status]))

    review = bool(failed) or status in ("disagrees", "illegible", "failed", "no_citation")
    v2 = _outcome(review, proposed, proposed_by, bool(occluders))

    v3, looked, second_status = v2, None, "not_reread"
    if second is not None and status in SECOND_LOOK:
        second_status = _reread_status(value, second)
        looked = second.value if second.error is None else None
        notes.append(
            Flag(field_id=fid, check="reread", detail=_second_detail(second_status, second))
        )
        if second_status == "agrees":
            v3 = _outcome(bool(failed), None, None, bool(occluders))
        elif status == second_status == "disagrees" and same_reading(fid, read, looked):
            # v2's proposal, when it made one, is this same reading with its own provenance.
            v3 = _outcome(True, proposed or read, proposed_by or "second_look", bool(occluders))
        elif second_status != "failed":  # a look that failed is no look: v2 stands
            v3 = _outcome(True, None, None, bool(occluders))
    policies = {"v2": v2, "v3": v3}
    chosen = policies[policy]
    return VerdictRecord(
        field_id=value.field_id,
        value=value.value,  # never changed: a correction is only ever proposed
        confidence=chosen.confidence,
        status=chosen.status,
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
            reread_flags=list(reread_flags),
            reread_balances=balances,
            proposed=chosen.proposed,
            proposed_by=chosen.proposed_by,
            second_look=looked,
            second_look_status=second_status,
            second_crop=second.crop if second_status != "not_reread" else None,
        ),
        policy=policy,
        policies=policies,
    )


def as_policy(verdict: VerdictRecord, policy: str) -> VerdictRecord:
    """The verdict as `policy` decided it: its status, confidence and proposal."""
    if verdict.policy == policy:
        return verdict
    if policy not in verdict.policies:
        raise ValueError(f"{verdict.field_id}: no outcome for policy {policy!r}; rerun verify")
    outcome = verdict.policies[policy]
    evidence = verdict.evidence.model_copy(
        update={"proposed": outcome.proposed, "proposed_by": outcome.proposed_by}
    )
    return verdict.model_copy(
        update={
            "status": outcome.status,
            "confidence": outcome.confidence,
            "evidence": evidence,
            "policy": policy,
        }
    )


@dataclass
class _Page:
    extraction: PageExtraction
    image: bytes
    values: list[ExtractedValue]  # with corrected citations
    regions: list[Region]


def reread_values(
    pages: Sequence[PageExtraction], readings: Mapping[str, ReRead]
) -> list[PageExtraction]:
    """The pages as the re-reader read them: a value it couldn't give is unread (None)."""
    out = []
    for page in pages:
        values = []
        for v in page.values:
            reading = readings.get(v.field_id)
            text = reading.value if reading is not None and reading.error is None else None
            values.append(v.model_copy(update={"value": text, "abstained": text is None}))
        out.append(page.model_copy(update={"values": values}))
    return out


def _occluders(value: ExtractedValue, regions: Sequence[Region]) -> list[Occluder]:
    return [
        Occluder(label=r.label, bbox=r.bbox, cover=round(share, 4))
        for r, share in occlusion.occluders(value, regions)
    ]


class Metered:
    """A role that adds up what its answers cost, cache hits included: a hit carries the usage of
    the call that first produced it, so the sum is what the configuration costs, not this run.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.cost_usd = 0.0
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _add(self, response: Any) -> Any:
        with self._lock:
            self.cost_usd += response.usage.cost_usd
        return response

    def complete(self, request: Any) -> Any:
        return self._add(self.inner.complete(request))

    def segment(self, request: Any) -> Any:
        return self._add(self.inner.segment(request))


Job = tuple[bytes, BBox, str, float, float]  # image, box, prompt, horizontal and vertical padding


def verify(
    pages: Sequence[PageExtraction],
    images: Mapping[str, Path],
    roles: Mapping[str, object],
    *,
    correct_citations: bool,
    workers: int = 1,
    policy: Policy = POLICY,
) -> tuple[list[VerdictRecord], dict]:
    """Every value of every page through both policies; returns the verdicts and the call counts.
    Second looks are asked only for the fields whose first re-read calls for one.
    """
    segmenter, llm = Metered(roles[occlusion.ROLE]), Metered(roles[reread.ROLE])

    def prepare(page: PageExtraction) -> _Page:
        image = images[page.page_id].read_bytes()
        values = page.values
        if correct_citations and values:
            values = citations.correct(image, values).values
        regions = occlusion.detect(image, segmenter) if values else []
        return _Page(page, image, values, regions)

    def read_one(job: Job) -> tuple[ReRead, bool]:
        image, box, prompt, pad_x, pad_y = job
        picture = Image.open(io.BytesIO(image))
        seen = reread.crop_box(box, *picture.size, pad_x=pad_x, pad_y=pad_y)
        try:
            text, cached = reread.reread(picture, box, prompt, llm, pad_x=pad_x, pad_y=pad_y)
        except BudgetExceeded:
            raise
        except Exception as error:  # one field failing must not stop the others
            return ReRead(None, f"{type(error).__name__}: {error}"[:300], seen), False
        return ReRead(text, crop=seen), cached

    with ThreadPoolExecutor(max_workers=workers) as pool:
        prepared = list(pool.map(prepare, sorted(pages, key=lambda p: p.page_id)))
        jobs: list[Job] = []
        keys: list[ExtractedValue] = []
        for page in prepared:
            plugin = REGISTRY.get(page.extraction.doc_type)
            for value in page.values:
                if value.citation is not None and needs_reread(value):
                    box = reread.region(value.citation)
                    prompt = plugin.reread_prompt(value.field_id)
                    jobs.append((page.image, box, prompt, reread.PAD_X, reread.PAD_Y))
                    keys.append(value)
        results = list(pool.map(read_one, jobs))
        readings = {v.field_id: reading for v, (reading, _) in zip(keys, results, strict=True)}

        wanted = [
            (job, value)
            for job, value in zip(jobs, keys, strict=True)
            if _reread_status(value, readings[value.field_id]) in SECOND_LOOK
        ]
        second_jobs = [
            (image, box, prompt, reread.SECOND_PAD_X, reread.SECOND_PAD_Y)
            for (image, box, prompt, _, _), _ in wanted
        ]
        second_keys = [value.field_id for _, value in wanted]
        second_results = list(pool.map(read_one, second_jobs))
    seconds = {k: look for k, (look, _) in zip(second_keys, second_results, strict=True)}

    reread_pages = reread_values(pages, readings)
    by_field: dict[str, list[Flag]] = defaultdict(list)
    for flag in run_checks(pages):
        by_field[flag.field_id].append(flag)
    reread_by_field: dict[str, list[Flag]] = defaultdict(list)
    for flag in run_checks(reread_pages):
        reread_by_field[flag.field_id].append(flag)
    holds = balanced(reread_pages)

    verdicts = [
        decide(
            page.extraction.page_id,
            page.extraction.doc_type,
            value,
            by_field[value.field_id],
            _occluders(value, page.regions),
            readings.get(value.field_id),
            reread_by_field[value.field_id],
            value.field_id in holds,
            seconds.get(value.field_id),
            policy,
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
        "second_looks": len(second_jobs),
        "second_looks_from_cache": sum(cached for _, cached in second_results),
        "second_looks_failed": sum(r.error is not None for r, _ in second_results),
        "cost_full_usd": segmenter.cost_usd + llm.cost_usd,
    }
    return verdicts, calls


def _counts(verdicts: Sequence[VerdictRecord]) -> dict:
    proposers = [v.evidence.proposed_by for v in verdicts]
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
        "proposed_by": dict(sorted(Counter(filter(None, proposers)).items())),
        "reread_chain_flags": sum(len(v.evidence.reread_flags) for v in verdicts),
        "by_second_look": dict(
            sorted(Counter(v.evidence.second_look_status for v in verdicts).items())
        ),
        "by_policy": {
            policy: {
                "by_status": dict(sorted(Counter(o.status for o in outcomes).items())),
                "proposed_corrections": sum(o.proposed is not None for o in outcomes),
            }
            for policy in POLICIES
            if (outcomes := [v.policies[policy] for v in verdicts if policy in v.policies])
        },
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
    policy: Policy = POLICY,
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
        pages,
        images,
        roles,
        correct_citations=not strategy.endswith("+ink"),
        workers=workers,
        policy=policy,
    )
    cost_full = calls.pop("cost_full_usd")
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
            "version": policy,
            "recorded": list(POLICIES),
            "v2": "D26: every field read twice, checks on both chains",
            "v3": "D29: v2, with a second look before an alarm",
            "money_fields": sorted(MONEY_FIELDS),
            "confidence": CONFIDENCE,
            "occlusion_prompts": list(occlusion.PROMPTS),
            "occlusion_cover": occlusion.COVER,
            "reread_padding": {"vertical": reread.PAD_Y, "horizontal": reread.PAD_X},
            "second_look_padding": {
                "vertical": reread.SECOND_PAD_Y,
                "horizontal": reread.SECOND_PAD_X,
            },
        },
        "counts": {"pages": len(pages), **_counts(verdicts)},
        "calls": calls,
        "cost_usd": guard.spent() - spent_before,
        "cost_full_usd": cost_full,
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
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--policy", choices=POLICIES, default=POLICY)
    args = parser.parse_args(argv)

    roles = load_roles(args.config)
    guard = roles[reread.ROLE].inner.guard  # Cache -> Budget -> the guard shared by every role
    record = run(
        RUNS_DIR / args.run,
        RUNS_DIR / args.out,
        roles,
        guard=guard,
        config=describe_config(args.config),
        workers=args.workers,
        policy=args.policy,
    )
    counts, calls = record["counts"], record["calls"]
    print(
        f"{counts['fields']} fields on {counts['pages']} pages: {counts['by_status']}; "
        f"{counts['occluded']} occluded, {counts['proposed_corrections']} corrections proposed"
    )
    for policy, tally in counts["by_policy"].items():
        print(f"  {policy}: {tally['by_status']}, {tally['proposed_corrections']} proposed")
    print(
        f"{calls['rereads']} re-reads ({calls['rereads_from_cache']} from cache, "
        f"{calls['rereads_failed']} failed), {calls['second_looks']} second looks "
        f"({calls['second_looks_from_cache']} from cache, {calls['second_looks_failed']} failed); "
        f"${record['cost_usd']:.4f} spent, ${record['cost_full_usd']:.4f} at full price"
    )


if __name__ == "__main__":
    main()
