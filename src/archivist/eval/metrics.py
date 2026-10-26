"""Scoring rules, fixed and tested before any model output is scored (D20).

Every ground-truth field gets exactly one outcome:

    correct       the normalised prediction equals the normalised printed value (both "" counts)
    hallucinated  nothing is printed but a non-empty value was returned
    misread       something is printed and a different non-empty value was returned
    omitted       no prediction for the field, or "" returned where something is printed
    abstained     the value is None, abstained=True, or the verdict's status is "abstained"

Predictions for field ids that are not in the ground truth are ignored. A wrong value is a
misread, hallucinated or omitted field. An accepted field counts as an error whenever its
outcome is not correct, so an accepted null is an error too.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

import numpy as np
from pydantic import BaseModel

from archivist.schema import BBox, ExtractedValue, FieldVerdict, Flag, PageGT

Outcome = Literal["correct", "misread", "hallucinated", "omitted", "abstained"]
Status = Literal["accepted", "review", "abstained"]

OUTCOMES: tuple[Outcome, ...] = ("correct", "misread", "hallucinated", "omitted", "abstained")
WRONG: frozenset[str] = frozenset({"misread", "hallucinated", "omitted"})
MONEY_FIELDS = frozenset(
    {"debit", "credit", "balance", "brought_forward", "carried_forward", "amount"}
)
DATE_FIELDS = frozenset({"date"})
DIGIT_FIELDS = frozenset({"account_no", "memo_no"})
WORDS_FIELDS = frozenset({"amount_words"})  # compared on letters only (D22)

_DATE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})")


class FieldOutcome(BaseModel):
    page_id: str
    field_id: str
    doc_type: Literal["ledger", "memo"]
    severity: int
    occluded: bool
    printed: str
    predicted: str | None
    outcome: Outcome
    status: Status | None  # None when there is no prediction for the field
    confidence: float | None  # only verdicts carry a confidence
    citation_ok: bool | None  # None when there is no citation


def field_kind(field_id: str) -> str:
    """The name at the end of a field id: "L:card-01-1:03:debit" -> "debit"."""
    return field_id.rsplit(":", 1)[-1]


def _text(text: str) -> str:
    return " ".join(text.split()).upper()


def _money(text: str) -> str | None:
    cleaned = re.sub(r"[£,\s]", "", text)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _date(text: str) -> str | None:
    match = _DATE.fullmatch(text.strip())
    if match is None:
        return None
    day, month, year = match.groups()
    return f"{int(day):02d}/{int(month):02d}/{year[-2:]}"


def normalise(field_id: str, text: str) -> str:
    """Canonical form for comparison; a value that doesn't parse as its type falls back to text."""
    if not text.strip():
        return ""
    kind = field_kind(field_id)
    if kind in MONEY_FIELDS:
        return _money(text) or _text(text)
    if kind in DATE_FIELDS:
        return _date(text) or _text(text)
    if kind in DIGIT_FIELDS:
        return re.sub(r"\D", "", text) or _text(text)
    if kind in WORDS_FIELDS:
        return re.sub(r"[^A-Z]", "", text.upper()) or _text(text)
    return _text(text)


def _centre_inside(predicted: BBox, truth: BBox) -> bool:
    cx = (predicted.x0 + predicted.x1) / 2
    cy = (predicted.y0 + predicted.y1) / 2
    return truth.x0 <= cx < truth.x1 and truth.y0 <= cy < truth.y1


def _outcome(field_id: str, printed: str, value: str | None, abstained: bool) -> Outcome:
    if abstained or value is None:
        return "abstained"
    truth, guess = normalise(field_id, printed), normalise(field_id, value)
    if truth == guess:
        return "correct"
    if truth == "":
        return "hallucinated"
    if guess == "":
        return "omitted"
    return "misread"


def score_page(
    page: PageGT, predictions: Sequence[FieldVerdict] | Sequence[ExtractedValue]
) -> list[FieldOutcome]:
    """One outcome per ground-truth field, in ground-truth order."""
    by_id: dict[str, FieldVerdict | ExtractedValue] = {}
    for prediction in predictions:
        if prediction.field_id in by_id:
            raise ValueError(f"duplicate prediction for {prediction.field_id}")
        by_id[prediction.field_id] = prediction

    outcomes = []
    for field in page.fields:
        prediction = by_id.get(field.field_id)
        status: Status | None = None
        confidence = citation_ok = None
        if prediction is None:
            value, outcome = None, "omitted"
        elif isinstance(prediction, FieldVerdict):
            value, status, confidence = prediction.value, prediction.status, prediction.confidence
            outcome = _outcome(field.field_id, field.printed, value, status == "abstained")
        else:
            value = prediction.value
            abstained = prediction.abstained or value is None
            status = "abstained" if abstained else "accepted"
            outcome = _outcome(field.field_id, field.printed, value, abstained)
            if prediction.citation is not None:
                citation = prediction.citation
                citation_ok = citation.page_id == page.page_id and _centre_inside(
                    citation.bbox, field.bbox
                )
        outcomes.append(
            FieldOutcome(
                page_id=page.page_id,
                field_id=field.field_id,
                doc_type=page.doc_type,
                severity=page.severity,
                occluded=bool(field.occluded_by),
                printed=field.printed,
                predicted=value,
                outcome=outcome,
                status=status,
                confidence=confidence,
                citation_ok=citation_ok,
            )
        )
    return outcomes


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _stats(outcomes: Sequence[FieldOutcome]) -> dict:
    counts = dict.fromkeys(OUTCOMES, 0)
    accepted = review = caught = missed = false_alarms = cited = cited_ok = 0
    for o in outcomes:
        counts[o.outcome] += 1
        correct = o.outcome == "correct"
        if o.status == "accepted":
            accepted += 1
            missed += not correct
        elif o.status == "review":
            review += 1
            false_alarms += correct
        if o.status in ("review", "abstained") and o.outcome in WRONG:
            caught += 1
        if correct and o.citation_ok is not None:
            cited += 1
            cited_ok += o.citation_ok
    n = len(outcomes)
    return {
        "n_fields": n,
        "counts": counts,
        "field_accuracy": _ratio(counts["correct"], n),
        "n_accepted": accepted,
        "error_rate_accepted": _ratio(missed, accepted),
        "citation_accuracy": _ratio(cited_ok, cited),
        "review_rate": _ratio(review, n),
        "errors_caught": caught,
        "errors_missed": missed,
        "false_alarms": false_alarms,
    }


def _grouped(outcomes: Iterable[FieldOutcome], key: Callable[[FieldOutcome], object]) -> dict:
    groups: dict = defaultdict(list)
    for o in outcomes:
        groups[key(o)].append(o)
    return {k: _stats(groups[k]) for k in sorted(groups)}


def summarise(outcomes: Sequence[FieldOutcome]) -> dict:
    """Overall, per-severity and per-doc-type statistics; undefined ratios are None."""
    return {
        "overall": _stats(outcomes),
        "by_severity": _grouped(outcomes, lambda o: o.severity),
        "by_doc_type": _grouped(outcomes, lambda o: o.doc_type),
    }


def bootstrap_ci(
    outcomes: Sequence[FieldOutcome],
    metric: str | Callable[[Sequence[FieldOutcome]], float | None],
    n: int = 2000,
    seed: int = 0,
) -> tuple[float, float] | None:
    """95% percentile interval from resampling whole pages with replacement.

    metric is a key of summarise()'s "overall" stats or a function of a list of outcomes.
    Resamples where the metric is undefined are dropped; None if it is never defined.
    """
    compute = metric if callable(metric) else (lambda sample: _stats(sample)[metric])
    by_page: dict[str, list[FieldOutcome]] = defaultdict(list)
    for o in outcomes:
        by_page[o.page_id].append(o)
    pages = [by_page[p] for p in sorted(by_page)]
    if not pages:
        return None
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        picks = rng.integers(0, len(pages), size=len(pages))
        value = compute([o for i in picks for o in pages[i]])
        if value is not None:
            values.append(value)
    if not values:
        return None
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def risk_coverage(outcomes: Sequence[FieldOutcome]) -> list[tuple[float, float]]:
    """(coverage, error rate) as the confidence threshold sweeps from strict to lenient.

    Only fields with a confidence take part. At threshold t every field with confidence >= t is
    taken as accepted, and anything not correct among them is an error. One point per distinct
    confidence, highest first, so coverage rises monotonically to 1.
    """
    scored = sorted((o for o in outcomes if o.confidence is not None), key=lambda o: -o.confidence)
    points = []
    errors = 0
    for i, o in enumerate(scored):
        errors += o.outcome != "correct"
        if i + 1 == len(scored) or scored[i + 1].confidence != o.confidence:
            points.append(((i + 1) / len(scored), errors / (i + 1)))
    return points


def source_error_detection(pages: Iterable[PageGT], flags: Iterable[Flag]) -> float | None:
    """Recall of ground-truth source errors: one counts as found if any of its fields is flagged."""
    flagged = {flag.field_id for flag in flags}
    errors = [error for page in pages for error in page.source_errors]
    found = sum(any(f in flagged for f in error.field_ids) for error in errors)
    return _ratio(found, len(errors))
