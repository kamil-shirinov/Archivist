import random

import pytest

from archivist.eval.metrics import (
    OUTCOMES,
    FieldOutcome,
    bootstrap_ci,
    normalise,
    risk_coverage,
    score_page,
    source_error_detection,
    summarise,
)
from archivist.schema import (
    BBox,
    Citation,
    ExtractedValue,
    FieldGT,
    FieldVerdict,
    Flag,
    PageGT,
    SourceError,
)

DEBIT = "L:card-01-1:03:debit"
CREDIT = "L:card-01-1:03:credit"
DATE = "L:card-01-1:03:date"
DESCRIPTION = "L:card-01-1:03:description"
BALANCE = "L:card-01-1:03:balance"
ACCOUNT = "L:card-01-1:hdr:account_no"


def _box(x0: int, y0: int, x1: int, y1: int) -> BBox:
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _page(fields: list[tuple[str, str]], **kwargs) -> PageGT:
    return PageGT(
        page_id=kwargs.get("page_id", "card-01-1"),
        doc_type="ledger",
        image_path="images/card-01-1.jpg",
        width=1000,
        height=1400,
        severity=kwargs.get("severity", 1),
        fields=[
            FieldGT(field_id=fid, printed=printed, bbox=_box(0, 10 * i, 100, 10 * i + 10))
            for i, (fid, printed) in enumerate(fields)
        ],
        artefacts=[],
        source_errors=kwargs.get("source_errors", []),
    )


def _value(field_id: str, value: str | None, **kwargs) -> ExtractedValue:
    return ExtractedValue(field_id=field_id, value=value, citation=None, **kwargs)


def _verdict(field_id: str, value: str | None, status: str, confidence: float) -> FieldVerdict:
    return FieldVerdict(field_id=field_id, value=value, confidence=confidence, status=status)


def _outcome(page_id: str, outcome: str, status: str = "accepted", **kwargs) -> FieldOutcome:
    return FieldOutcome(
        page_id=page_id,
        field_id=f"L:{page_id}:01:debit",
        doc_type=kwargs.get("doc_type", "ledger"),
        severity=kwargs.get("severity", 0),
        occluded=False,
        printed="1.00",
        predicted="1.00",
        outcome=outcome,
        status=status,
        confidence=kwargs.get("confidence"),
        citation_ok=kwargs.get("citation_ok"),
    )


# --- normalise ---


def test_money_forms_are_equal():
    assert normalise(DEBIT, "£4,375.50") == normalise(DEBIT, "4375.5") == "4375.50"
    assert normalise(DEBIT, "4,375.50") == "4375.50"
    assert normalise("M:memo-0001:amount", "£ 12.5") == "12.50"


def test_date_forms_are_equal():
    assert normalise(DATE, "21.08.1976") == normalise(DATE, "21/08/76") == "21/08/76"
    assert normalise(DATE, "1-8-85") == "01/08/85"


def test_account_digits_only_and_text_upper_collapsed():
    assert normalise(ACCOUNT, "1619 5204") == "16195204"
    assert normalise("M:memo-0001:memo_no", "No. 008327") == "008327"
    assert normalise(DESCRIPTION, "  chq   098975 ") == "CHQ 098975"


def test_amount_in_words_compares_letters_only():
    words = "M:memo-0001:amount_words"
    printed = "Sixty-three pounds and forty-six pence"
    for variant in (
        "Sixty-three pounds and fortysix pence",
        "sixty three pounds and forty six pence",
        "SIXTY-THREE POUNDS AND FORTY-SIX PENCE.",
    ):
        assert normalise(words, variant) == normalise(words, printed)
    assert normalise(words, "Sixty-eight pounds and forty-six pence") != normalise(words, printed)
    page = _page([(words, printed)])
    assert _outcomes(page, [_value(words, "Sixty three pounds and fortysix pence")]) == {
        words: "correct"
    }
    assert normalise(DESCRIPTION, "STANDING-ORDER") != normalise(DESCRIPTION, "STANDING ORDER")


def test_blank_normalises_to_empty_and_garbage_falls_back_to_text():
    assert normalise(DEBIT, "") == normalise(DEBIT, "   ") == ""
    assert normalise(DEBIT, "illegible") == "ILLEGIBLE"


# --- score_page: each outcome ---


@pytest.fixture
def page() -> PageGT:
    return _page([(DEBIT, "4,375.50"), (CREDIT, ""), (DATE, "21/08/76"), (DESCRIPTION, "CASH")])


def _outcomes(page: PageGT, predictions) -> dict[str, str]:
    return {o.field_id: o.outcome for o in score_page(page, predictions)}


def test_correct_including_both_blank(page):
    got = _outcomes(
        page,
        [
            _value(DEBIT, "£4375.5"),
            _value(CREDIT, ""),
            _value(DATE, "21.08.1976"),
            _value(DESCRIPTION, "cash"),
        ],
    )
    assert set(got.values()) == {"correct"}


def test_hallucinated_misread_omitted_abstained(page):
    got = _outcomes(
        page,
        [
            _value(DEBIT, "4,875.50"),
            _value(CREDIT, "12.00"),
            _value(DATE, ""),
        ],
    )
    assert got == {
        DEBIT: "misread",
        CREDIT: "hallucinated",
        DATE: "omitted",  # "" where something is printed
        DESCRIPTION: "omitted",  # no prediction at all
    }


def test_abstention_forms(page):
    got = _outcomes(page, [_value(DEBIT, None), _value(CREDIT, "", abstained=True)])
    assert got[DEBIT] == got[CREDIT] == "abstained"
    verdicts = _outcomes(
        page,
        [_verdict(DATE, "21/08/76", "abstained", 0.2), _verdict(DEBIT, None, "review", 0.4)],
    )
    assert verdicts[DATE] == verdicts[DEBIT] == "abstained"


def test_outcome_metadata_and_baseline_status(page):
    page.fields[0].occluded_by = ["stamp-1"]
    outcomes = score_page(page, [_value(DEBIT, "4,375.50"), _value(CREDIT, None)])
    debit, credit, date, _ = outcomes
    assert len(outcomes) == len(page.fields)
    assert (debit.page_id, debit.severity, debit.doc_type) == ("card-01-1", 1, "ledger")
    assert debit.occluded and not credit.occluded
    assert debit.status == "accepted" and debit.confidence is None
    assert credit.status == "abstained"
    assert date.status is None and date.outcome == "omitted"


def test_verdicts_carry_status_and_confidence(page):
    outcomes = score_page(page, [_verdict(DEBIT, "4375.50", "review", 0.6)])
    assert outcomes[0].outcome == "correct"
    assert (outcomes[0].status, outcomes[0].confidence) == ("review", 0.6)
    assert outcomes[0].citation_ok is None


def test_citation_centre_must_lie_in_truth_box(page):
    # DEBIT's truth box is (0, 0, 100, 10).
    def cited(page_id: str, bbox: BBox) -> ExtractedValue:
        return ExtractedValue(
            field_id=DEBIT, value="4,375.50", citation=Citation(page_id=page_id, bbox=bbox)
        )

    assert score_page(page, [cited("card-01-1", _box(40, 2, 150, 8))])[0].citation_ok  # x 95
    assert not score_page(page, [cited("card-01-1", _box(40, 2, 160, 8))])[0].citation_ok  # x 100
    assert not score_page(page, [cited("card-01-1", _box(90, 2, 250, 8))])[0].citation_ok
    assert not score_page(page, [cited("card-01-2", _box(40, 2, 60, 8))])[0].citation_ok
    assert score_page(page, [_value(DEBIT, "4,375.50")])[0].citation_ok is None


def test_duplicate_predictions_rejected(page):
    with pytest.raises(ValueError):
        score_page(page, [_value(DEBIT, "1.00"), _value(DEBIT, "2.00")])


# --- summarise ---


def test_summarise_counts_and_rates():
    outcomes = [
        _outcome("p1", "correct", "accepted", citation_ok=True),
        _outcome("p1", "correct", "accepted", citation_ok=False),
        _outcome("p1", "correct", "review"),  # false alarm
        _outcome("p1", "misread", "accepted"),  # missed
        _outcome("p2", "hallucinated", "review", severity=2),  # caught
        _outcome("p2", "omitted", "abstained", severity=2),  # caught
        _outcome("p2", "abstained", "abstained", severity=2),
        _outcome("p2", "omitted", None, severity=2, doc_type="memo"),  # no prediction
    ]
    s = summarise(outcomes)
    overall = s["overall"]
    assert sum(overall["counts"].values()) == overall["n_fields"] == len(outcomes)
    assert overall["field_accuracy"] == 3 / 8
    assert overall["n_accepted"] == 3
    assert overall["error_rate_accepted"] == 1 / 3
    assert overall["citation_accuracy"] == 1 / 2
    assert overall["review_rate"] == 2 / 8
    assert (overall["errors_caught"], overall["errors_missed"], overall["false_alarms"]) == (2, 1, 1)
    assert set(s["by_severity"]) == {0, 2} and set(s["by_doc_type"]) == {"ledger", "memo"}
    for group in ("by_severity", "by_doc_type"):
        assert sum(g["n_fields"] for g in s[group].values()) == len(outcomes)
    assert s["by_severity"][2]["error_rate_accepted"] is None


def test_summarise_counts_add_up_on_scored_page(page):
    outcomes = score_page(page, [_value(DEBIT, "1.00"), _value(CREDIT, "2.00")])
    counts = summarise(outcomes)["overall"]["counts"]
    assert set(counts) == set(OUTCOMES)
    assert sum(counts.values()) == len(page.fields)


# --- bootstrap_ci ---


def _many_pages(n_pages: int, seed: int = 1) -> list[FieldOutcome]:
    rng = random.Random(seed)
    return [
        _outcome(f"p{p:03d}", "correct" if rng.random() < 0.8 else "misread")
        for p in range(n_pages)
        for _ in range(10)
    ]


def test_bootstrap_is_seeded_and_narrows_with_more_pages():
    outcomes = _many_pages(60)
    a = bootstrap_ci(outcomes, "field_accuracy", n=500, seed=3)
    assert a == bootstrap_ci(outcomes, "field_accuracy", n=500, seed=3)
    assert a[0] <= 0.8 <= a[1]
    few = bootstrap_ci(outcomes[:50], "field_accuracy", n=500, seed=3)
    assert few[1] - few[0] > a[1] - a[0]


def test_bootstrap_resamples_pages_not_fields():
    # Each page is all right or all wrong: page-level resampling sees 4 units, not 40 fields,
    # so a resample can only land on multiples of 1/4.
    outcomes = [
        _outcome(f"p{p}", "correct" if p < 2 else "misread") for p in range(4) for _ in range(10)
    ]
    seen = set()

    def accuracy(sample: list[FieldOutcome]) -> float:
        value = sum(o.outcome == "correct" for o in sample) / len(sample)
        seen.add(round(value, 6))
        return value

    bootstrap_ci(outcomes, accuracy, n=200)
    assert len(seen) > 1 and seen <= {0.0, 0.25, 0.5, 0.75, 1.0}


def test_bootstrap_undefined_metric_is_none():
    outcomes = [_outcome("p1", "correct", "review")]
    assert bootstrap_ci(outcomes, "error_rate_accepted", n=50) is None
    assert bootstrap_ci([], "field_accuracy") is None


# --- risk_coverage ---


def test_risk_coverage_is_monotone_and_reaches_full_coverage():
    rng = random.Random(5)
    outcomes = [
        _outcome("p1", rng.choice(["correct", "misread"]), confidence=round(rng.random(), 1))
        for _ in range(50)
    ]
    points = risk_coverage(outcomes)
    coverages = [c for c, _ in points]
    assert coverages == sorted(coverages) and len(set(coverages)) == len(coverages)
    assert coverages[-1] == 1.0
    assert points[-1][1] == sum(o.outcome != "correct" for o in outcomes) / len(outcomes)


def test_risk_coverage_counts_ties_together_and_skips_unscored():
    outcomes = [
        _outcome("p1", "correct", confidence=0.9),
        _outcome("p1", "misread", confidence=0.9),
        _outcome("p1", "abstained", "abstained", confidence=0.1),
        _outcome("p1", "correct"),  # baseline field, no confidence
    ]
    assert risk_coverage(outcomes) == [(2 / 3, 1 / 2), (1.0, 2 / 3)]


# --- source_error_detection ---


def test_source_error_recall():
    errors = [
        SourceError(kind="balance_arithmetic", field_ids=[BALANCE], note=""),
        SourceError(kind="memo_ledger_mismatch", field_ids=["M:memo-0015:amount", DEBIT], note=""),
    ]
    pages = [_page([(DEBIT, "18.16"), (BALANCE, "1,991.49")], source_errors=errors)]
    flags = [Flag(field_id=DEBIT, check="crossdoc", detail="memo says 58.16")]
    assert source_error_detection(pages, flags) == 0.5
    assert source_error_detection(pages, []) == 0.0
    assert source_error_detection([_page([(DEBIT, "1.00")])], flags) is None
