"""The pre-registered test report, tested against PREREGISTRATION.md before its first run (P17).

Every run here is hand-built in tmp_path, small enough that the right answer is obvious; nothing
reads data/test. What PREREGISTRATION.md says decides each hypothesis, word for word:

- H1: "the headline's error rate among accepted fields is lower than the baseline's, with
  non-overlapping 95% intervals." Error rate among accepted fields is "wrong values accepted ÷
  values accepted"; the intervals come from "2,000 page-level bootstrap resamples (seed 0)". Both
  conditions must hold. Intervals that share even one end point overlap.
- H2: "the headline catches at least 85% of wrong values." At least: exactly 85% is met. A wrong
  value is caught when it is sent to review; "a failed page scores all its fields as omitted",
  which are wrong values nobody caught.
- H3: "the headline sends at most 20% of fields to review." At most: exactly 20% is met. "Scoring
  rules are those in src/archivist/eval/metrics.py", whose review rate counts the status "review"
  only: an abstained field (the extractor returned null) is not sent to review.
- H4: "the all-open-weights arm's error rate among accepted fields is below 1%." Below: exactly 1%
  is not met. It is judged on arm B, not the headline.
- H5: "the headline flags at least 90% of the planted source errors." At least: exactly 90% is met.
  Under policy v2 a field a check flags goes to review, so a source error counts as flagged when
  any of its fields is sent to review; a note on an accepted field is not a flag. A source error
  listed on both a memo and its card is one planted error.

A hypothesis whose rate is undefined (nothing accepted, no wrong values, no source errors) is not
met: the pre-registration asks for a number, and there is none.
"""

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from archivist.eval import test_report
from archivist.eval.metrics import bootstrap_ci, summarise
from archivist.eval.run_eval import score_verdicts
from archivist.pipeline.extract import PageExtraction
from archivist.pipeline.verify import Evidence, PolicyOutcome, VerdictRecord
from archivist.schema import BBox, Citation, ExtractedValue, FieldGT, Flag, PageGT, SourceError

PREREGISTRATION = Path(__file__).resolve().parents[1] / "PREREGISTRATION.md"
SAME = "<as printed>"  # a read that equals the printed value
CONFIDENCE = {"accepted": 0.99, "review": 0.3, "abstained": 0.0}


@dataclass(frozen=True)
class F:
    """One field: what is printed, what each extraction read and each arm's policy v2 status.

    None as a status means the arm has no verdict for the field, as on a page that failed.
    """

    printed: str
    read: str | None = SAME  # test-baseline (Muse Spark 1.3), which arms A and C verify
    a: str | None = "accepted"
    open_read: str | None = SAME  # test-baseline-open (Muse Spark Open), which arm B verifies
    b: str | None = "accepted"
    c: str | None = "accepted"
    note: bool = False  # arm A's verdict carries an occlusion note


def _fid(page_id: str, i: int) -> str:
    return f"M:{page_id}:f{i:02d}"


def _box(i: int) -> BBox:
    return BBox(x0=0, y0=20 * i, x1=200, y1=20 * i + 20)


def _resolve(f: F, read: str | None) -> str | None:
    return f.printed if read == SAME else read


def _verdict(page_id: str, i: int, f: F, read: str | None, status: str) -> VerdictRecord:
    outcome = PolicyOutcome(status=status, confidence=CONFIDENCE[status])
    fid = _fid(page_id, i)
    notes = [Flag(field_id=fid, check="occlusion", detail="12% covered by stamp")] if f.note else []
    return VerdictRecord(
        field_id=fid,
        value=None if status == "abstained" else read,
        confidence=outcome.confidence,
        status=status,
        flags=notes,
        page_id=page_id,
        doc_type="payment_memo",
        evidence=Evidence(route="reread", citation=None, reread_status="agrees"),
        policies={"v2": outcome, "v3": outcome},
    )


def _lines(models) -> str:
    return "".join(m.model_dump_json() + "\n" for m in models)


def _extraction(run: Path, pages: dict[str, list[F]], attr: str) -> None:
    run.mkdir(parents=True)
    predictions = []
    for page_id, fields in pages.items():
        values = []
        for i, f in enumerate(fields):
            read = _resolve(f, getattr(f, attr))
            citation = Citation(page_id=page_id, bbox=_box(i))
            values.append(
                ExtractedValue(
                    field_id=_fid(page_id, i), value=read, citation=citation, abstained=read is None
                )
            )
        predictions.append(PageExtraction(page_id=page_id, doc_type="payment_memo", values=values))
    (run / "predictions.jsonl").write_text(_lines(predictions))
    run_json = {
        "config": "config/models.toml",
        "citations": "S0+ink",
        "counts": {"pages": len(pages), "extracted": len(pages)},
        "failed_pages": [],
        "sessions": [{"aborted": None}],
        "cost_usd": 0.5,
    }
    (run / "run.json").write_text(json.dumps(run_json))


def _verdicts(run: Path, source: str, pages: dict[str, list[F]], arm: str, attr: str) -> None:
    run.mkdir(parents=True)
    verdicts = [
        _verdict(page_id, i, f, _resolve(f, getattr(f, attr)), getattr(f, arm))
        for page_id, fields in pages.items()
        for i, f in enumerate(fields)
        if getattr(f, arm) is not None
    ]
    (run / "verdicts.jsonl").write_text(_lines(verdicts))
    run_json = {
        "source_run": source,
        "config": f"config/arms/{arm}.toml",
        "policy": {"version": "v2"},
        "counts": {"verdicts": len(verdicts)},
        "calls": {"rereads": 1, "rereads_failed": 0, "second_looks": 0, "second_looks_failed": 0},
        "cost_usd": 0.0,
        "cost_full_usd": 0.25,
    }
    (run / "run.json").write_text(json.dumps(run_json))


def _world(
    tmp_path: Path,
    pages: dict[str, list[F]],
    errors: dict[str, list[list[str]]] | None = None,
) -> dict:
    """Ground truth, the two extraction runs and the three verdict runs, as test_report names them.

    errors maps a page to its planted source errors, each a list of field ids.
    """
    data, runs = tmp_path / "data", tmp_path / "runs"
    gt = data / "test" / "gt"
    gt.mkdir(parents=True)
    (data / "test" / "manifest.json").write_text(json.dumps({"pages": sorted(pages)}))
    for page_id, fields in pages.items():
        page = PageGT(
            page_id=page_id,
            doc_type="memo",
            image_path=f"images/{page_id}.jpg",
            width=1000,
            height=1000,
            severity=0,
            fields=[
                FieldGT(field_id=_fid(page_id, i), printed=f.printed, bbox=_box(i))
                for i, f in enumerate(fields)
            ],
            artefacts=[],
            source_errors=[
                SourceError(kind="memo_ledger_mismatch", field_ids=ids, note="planted")
                for ids in (errors or {}).get(page_id, [])
            ],
        )
        (gt / f"{page_id}.json").write_text(page.model_dump_json())
    _extraction(runs / "test-baseline", pages, "read")
    _extraction(runs / "test-baseline-open", pages, "open_read")
    _verdicts(runs / "test-archivist-A", "test-baseline", pages, "a", "read")
    _verdicts(runs / "test-archivist-B", "test-baseline-open", pages, "b", "open_read")
    _verdicts(runs / "test-archivist-C", "test-baseline", pages, "c", "read")
    return {"runs_dir": runs, "data_root": data, "manifest_sha256": None}


def _report(world: dict) -> dict:
    return test_report.build_report(test_report.CONFIGS, **world)


def _spread(fields: list[F], per_page: int = 10) -> dict[str, list[F]]:
    return {
        f"memo-{n:02d}": fields[start : start + per_page]
        for n, start in enumerate(range(0, len(fields), per_page))
    }


# --- The report says what the pre-registration says --------------------------------------------


def test_each_claim_is_the_pre_registered_hypothesis_word_for_word():
    text = PREREGISTRATION.read_text(encoding="utf-8")
    world_free = test_report._hypotheses({k: {"stats": _stats()} for k in ("baseline", "A", "B")})
    for h, judged in world_free.items():
        claim = judged["claim"]
        assert f"- {h}: {claim[0].lower()}{claim[1:]}\n" in text


def test_the_configurations_are_the_pre_registered_ones():
    configs = test_report.CONFIGS
    assert (test_report.BASELINE, test_report.HEADLINE, test_report.OPEN_WEIGHTS) == (
        "baseline",
        "A",
        "B",
    )
    assert configs["baseline"]["verdicts"] is None  # every value accepted
    # Arms A and C verify the baseline's own reads; arm B reads with Muse Spark Open throughout.
    assert configs["A"]["extraction"] == configs["C"]["extraction"] == "test-baseline"
    assert configs["B"]["extraction"] == "test-baseline-open"
    assert test_report.POLICY == "v2"


# --- Judging on hand-built statistics: the thresholds and the edges ----------------------------


def _stats(**overrides) -> dict:
    stats = {
        "n_fields": 100,
        "n_accepted": 100,
        "errors_missed": 0,
        "error_rate_accepted": 0.0,
        "error_rate_accepted_ci95": (0.0, 0.0),
        "n_wrong": 10,
        "errors_caught": 10,
        "catch_rate": 1.0,
        "catch_rate_ci95": (1.0, 1.0),
        "n_review": 10,
        "review_rate": 0.1,
        "review_rate_ci95": (0.1, 0.1),
        "n_source_errors": 10,
        "source_errors_found": 10,
        "source_error_recall": 1.0,
    }
    return stats | overrides


def _judge(baseline: dict | None = None, headline: dict | None = None, open_: dict | None = None):
    rows = {
        "baseline": {"stats": _stats(**(baseline or {}))},
        "A": {"stats": _stats(**(headline or {}))},
        "B": {"stats": _stats(**(open_ or {}))},
    }
    return test_report._hypotheses(rows)


def _errors(rate: float | None, ci: tuple[float, float] | None) -> dict:
    return {"error_rate_accepted": rate, "error_rate_accepted_ci95": ci}


@pytest.mark.parametrize(
    ("headline", "baseline", "lower", "apart", "met"),
    [
        # Lower, and the headline's interval ends before the baseline's begins.
        ((0.015, (0.01, 0.0199)), (0.03, (0.02, 0.04)), True, True, True),
        # The intervals just touch: they share 0.02, so they overlap.
        ((0.015, (0.01, 0.02)), (0.03, (0.02, 0.04)), True, False, False),
        # They just overlap.
        ((0.015, (0.01, 0.0201)), (0.03, (0.02, 0.04)), True, False, False),
        # Apart, but the headline is the higher one.
        ((0.05, (0.045, 0.06)), (0.03, (0.02, 0.04)), False, True, False),
        # The same rate.
        ((0.03, (0.02, 0.04)), (0.03, (0.02, 0.04)), False, False, False),
        # Nothing accepted: no rate and no interval.
        ((None, None), (0.03, (0.02, 0.04)), False, False, False),
        # A rate but no interval (every resample undefined) cannot show non-overlap.
        ((0.0, None), (0.03, (0.02, 0.04)), False, False, False),
    ],
)
def test_h1_needs_a_lower_rate_and_intervals_that_do_not_overlap(
    headline, baseline, lower, apart, met
):
    h1 = _judge(baseline=_errors(*baseline), headline=_errors(*headline))["H1"]
    assert h1["numbers"]["lower"] is lower
    assert h1["numbers"]["intervals_apart"] is apart
    assert h1["met"] is met


@pytest.mark.parametrize(
    ("caught", "wrong", "met"),
    [
        (17, 20, True),  # exactly 85%
        (85, 100, True),
        (1003, 1180, True),  # exactly 85% again, judged on the counts, not a rounded float
        (1002, 1180, False),
        (84, 100, False),
        (20, 20, True),
        (0, 0, False),  # no wrong values: the catch rate is undefined
    ],
)
def test_h2_is_met_at_85_percent_and_above(caught, wrong, met):
    rate = caught / wrong if wrong else None
    h2 = _judge(headline={"errors_caught": caught, "n_wrong": wrong, "catch_rate": rate})["H2"]
    assert h2["met"] is met
    assert (h2["numbers"]["caught"], h2["numbers"]["wrong"]) == (caught, wrong)
    assert h2["numbers"]["threshold"] == 0.85


@pytest.mark.parametrize(
    ("review", "fields", "met"),
    [
        (20, 100, True),  # exactly 20%
        (1, 5, True),
        (21, 100, False),
        (201, 1000, False),
        (0, 100, True),
        (0, 0, False),  # no fields: the review rate is undefined
    ],
)
def test_h3_is_met_at_20_percent_and_below(review, fields, met):
    rate = review / fields if fields else None
    h3 = _judge(headline={"n_review": review, "n_fields": fields, "review_rate": rate})["H3"]
    assert h3["met"] is met
    assert h3["numbers"]["threshold"] == 0.2


@pytest.mark.parametrize(
    ("wrong", "accepted", "met"),
    [
        (1, 100, False),  # exactly 1% is not below 1%
        (99, 9900, False),
        (98, 9900, True),
        (1, 101, True),
        (0, 1, True),
        (0, 0, False),  # nothing accepted: the error rate is undefined
    ],
)
def test_h4_is_met_only_strictly_below_1_percent(wrong, accepted, met):
    rate = wrong / accepted if accepted else None
    open_ = {"errors_missed": wrong, "n_accepted": accepted, "error_rate_accepted": rate}
    h4 = _judge(open_=open_)["H4"]
    assert h4["met"] is met
    assert (h4["numbers"]["wrong"], h4["numbers"]["accepted"]) == (wrong, accepted)


def test_h4_judges_arm_b_and_not_the_headline():
    good, bad = (0, 1000, 0.0), (500, 1000, 0.5)
    keys = ("errors_missed", "n_accepted", "error_rate_accepted")
    assert _judge(headline=dict(zip(keys, bad)), open_=dict(zip(keys, good)))["H4"]["met"]
    assert not _judge(headline=dict(zip(keys, good)), open_=dict(zip(keys, bad)))["H4"]["met"]


@pytest.mark.parametrize(
    ("found", "planted", "met"),
    [
        (9, 10, True),  # exactly 90%
        (90, 100, True),
        (89, 100, False),
        (10, 10, True),
        (0, 0, False),  # nothing planted: the recall is undefined
    ],
)
def test_h5_is_met_at_90_percent_and_above(found, planted, met):
    rate = found / planted if planted else None
    headline = {
        "source_errors_found": found,
        "n_source_errors": planted,
        "source_error_recall": rate,
    }
    h5 = _judge(headline=headline)["H5"]
    assert h5["met"] is met
    assert h5["numbers"]["threshold"] == 0.9


# --- Judging hand-built runs, end to end ------------------------------------------------------


def _h1_pages(headline_on_wrong: str) -> dict[str, list[F]]:
    """Ten pages of four fields; the baseline misreads two on every page."""
    return {
        f"memo-{p:02d}": [
            F("Alpha"),
            F("Beta"),
            F("Gamma", read="Garnma", a=headline_on_wrong),
            F("Delta", read="Dclta", a=headline_on_wrong),
        ]
        for p in range(10)
    }


def test_h1_is_met_when_the_headline_reviews_every_wrong_value_the_baseline_accepts(tmp_path):
    report = _report(_world(tmp_path, _h1_pages("review")))
    h1 = report["hypotheses"]["H1"]
    assert h1["met"]
    head, base = h1["numbers"]["headline"], h1["numbers"]["baseline"]
    assert (head["accepted"], head["wrong"], head["rate"]) == (20, 0, 0.0)
    assert (base["accepted"], base["wrong"], base["rate"]) == (40, 20, 0.5)
    # Every page is two of four wrong for the baseline and none for the headline, so every page
    # resample gives the same rate.
    assert tuple(head["ci95"]) == (0.0, 0.0)
    assert tuple(base["ci95"]) == (0.5, 0.5)


def test_h1_is_not_met_when_the_headline_accepts_the_same_wrong_values(tmp_path):
    h1 = _report(_world(tmp_path, _h1_pages("accepted")))["hypotheses"]["H1"]
    assert not h1["met"]
    assert not h1["numbers"]["lower"]


def test_h1_is_not_met_when_the_rate_is_lower_but_the_intervals_share_a_point(tmp_path):
    # The baseline accepts one wrong value on a page of one and nine right ones on a page of nine:
    # its page resamples run from 0 (the second page twice) to 1 (the first twice). The headline
    # reviews the wrong value: 0, always. Lower, but both intervals contain 0.
    pages = {
        "memo-01": [F("Alpha", read="Alpa", a="review")],
        "memo-02": [F(f"Value {i}") for i in range(9)],
    }
    h1 = _report(_world(tmp_path, pages))["hypotheses"]["H1"]
    assert tuple(h1["numbers"]["baseline"]["ci95"]) == (0.0, 1.0)
    assert tuple(h1["numbers"]["headline"]["ci95"]) == (0.0, 0.0)
    assert h1["numbers"]["lower"]
    assert not h1["numbers"]["intervals_apart"]
    assert not h1["met"]


@pytest.mark.parametrize(("failed_fields", "met"), [(1, True), (2, False)])
def test_h2_counts_only_review_as_caught_and_a_failed_page_as_wrong_and_missed(
    tmp_path, failed_fields, met
):
    pages = {
        "memo-01": [
            *[F(f"Value {i}", read=f"Va1ue {i}", a="review") for i in range(17)],  # caught
            *[F(f"Other {i}", read=f"0ther {i}", a="accepted") for i in range(2)],  # missed
            F("Right", a="review"),  # a false alarm, not a wrong value
            F("Blank", read=None, a="abstained"),  # null: abstained, not a wrong value
        ],
        # Arm A has no verdicts for this page: every field is omitted, wrong and not caught.
        "memo-02": [F(f"Lost {i}", a=None) for i in range(failed_fields)],
    }
    report = _report(_world(tmp_path, pages))
    h2 = report["hypotheses"]["H2"]
    assert h2["numbers"]["caught"] == 17
    assert h2["numbers"]["wrong"] == 19 + failed_fields  # 17/20 is 85%; 17/21 is below
    assert h2["met"] is met
    assert report["configurations"]["A"]["stats"]["wrong_unanswered"] == failed_fields


@pytest.mark.parametrize(
    ("review", "abstained", "met"),
    [
        (2, 1, True),  # 2 of 10 fields: exactly 20%
        (2, 5, True),  # abstained fields are not sent to review, however many
        (3, 0, False),
    ],
)
def test_h3_counts_the_status_review_only(tmp_path, review, abstained, met):
    fields = [
        *[F(f"Review {i}", a="review") for i in range(review)],
        *[F(f"Blank {i}", read=None, a="abstained") for i in range(abstained)],
    ]
    fields += [F(f"Value {i}") for i in range(10 - len(fields))]
    world = _world(tmp_path, {"memo-01": fields})
    report = _report(world)
    h3 = report["hypotheses"]["H3"]
    assert (h3["numbers"]["review"], h3["numbers"]["fields"]) == (review, 10)
    assert h3["met"] is met
    # The scoring rules of metrics.py, as pre-registered, give the same review rate.
    ours = score_verdicts(world["runs_dir"] / "test-archivist-A", world["data_root"] / "test/gt")
    assert h3["numbers"]["rate"] == summarise(ours.ours)["overall"]["review_rate"]


@pytest.mark.parametrize(("accepted", "met"), [(100, False), (101, True)])
def test_h4_is_arm_b_on_its_own_extraction_strictly_below_1_percent(tmp_path, accepted, met):
    # One wrong value among arm B's accepted ones; arm A accepts nothing but wrong values.
    fields = [
        F(f"Value {i}", read=f"Wrong {i}", open_read="Wrong" if i == 0 else SAME)
        for i in range(accepted)
    ]
    report = _report(_world(tmp_path, _spread(fields)))
    h4 = report["hypotheses"]["H4"]
    assert (h4["numbers"]["wrong"], h4["numbers"]["accepted"]) == (1, accepted)
    assert h4["met"] is met
    assert report["configurations"]["A"]["stats"]["error_rate_accepted"] == 1.0


@pytest.mark.parametrize(("found", "met"), [(9, True), (8, False)])
def test_h5_counts_a_source_error_found_when_a_field_of_it_is_sent_to_review(
    tmp_path, found, met
):
    # Ten pages, each with one planted error over both its fields. On the pages where it is
    # found, the first field goes to review; elsewhere one is accepted with a note and the other
    # abstained, and neither is a find.
    pages, errors = {}, {}
    for p in range(10):
        page_id = f"memo-{p:02d}"
        if p < found:
            pages[page_id] = [F("Twelve", a="review"), F("12.00")]
        else:
            pages[page_id] = [F("Twelve", note=True), F("12.00", read=None, a="abstained")]
        errors[page_id] = [[_fid(page_id, 0), _fid(page_id, 1)]]
    h5 = _report(_world(tmp_path, pages, errors))["hypotheses"]["H5"]
    assert (h5["numbers"]["found"], h5["numbers"]["planted"]) == (found, 10)
    assert h5["met"] is met


def test_h5_counts_a_source_error_listed_on_a_memo_and_its_card_once(tmp_path):
    pages = {
        "card-01": [F("100.00"), F("Smith")],
        "memo-01": [F("120.00", a="review"), F("Smith")],
    }
    shared = [_fid("card-01", 0), _fid("memo-01", 0)]
    errors = {"card-01": [shared], "memo-01": [shared]}
    h5 = _report(_world(tmp_path, pages, errors))["hypotheses"]["H5"]
    assert (h5["numbers"]["found"], h5["numbers"]["planted"]) == (1, 1)
    assert h5["met"]


def test_undefined_rates_are_not_met_and_render_as_a_dash(tmp_path):
    # Every value read right and accepted, and nothing planted: there are no wrong values to
    # catch and no source errors to flag.
    report = _report(_world(tmp_path, {"memo-01": [F("Alpha"), F("Beta")]}))
    head = report["configurations"]["A"]["stats"]
    assert (head["n_wrong"], head["catch_rate"], head["catch_rate_ci95"]) == (0, None, None)
    assert (head["n_source_errors"], head["source_error_recall"]) == (0, None)
    h = report["hypotheses"]
    assert not h["H2"]["met"]
    assert not h["H5"]["met"]
    assert h["H2"]["numbers"]["rate"] is None
    assert "—" in h["H2"]["summary"] and "—" in h["H5"]["summary"]
    text = test_report.render(report, "—")
    assert "**H2: not met.**" in text and "**H5: not met.**" in text


def test_an_empty_headline_run_accepts_nothing_and_catches_nothing(tmp_path):
    world = _world(tmp_path, _h1_pages("review"))
    (world["runs_dir"] / "test-archivist-A" / "verdicts.jsonl").write_text("")
    report = _report(world)
    head = report["configurations"]["A"]["stats"]
    assert (head["n_accepted"], head["error_rate_accepted"]) == (0, None)
    assert head["error_rate_accepted_ci95"] is None
    # Every field is omitted: a wrong value neither accepted nor sent to review.
    assert head["n_wrong"] == head["wrong_unanswered"] == 40
    h = report["hypotheses"]
    assert not h["H1"]["met"]
    assert not h["H2"]["met"] and h["H2"]["numbers"]["caught"] == 0
    # Read literally, nothing was sent to review, so H3's threshold holds; H1 and H2 do not.
    assert h["H3"]["numbers"]["review"] == 0 and h["H3"]["met"]
    assert "neither accepted nor sent to review" in test_report.render(report, "—")


@pytest.mark.parametrize("missing", ["test-baseline", "test-baseline-open", "test-archivist-B"])
def test_a_missing_run_stops_the_report(tmp_path, missing):
    world = _world(tmp_path, _h1_pages("review"))
    for path in sorted((world["runs_dir"] / missing).iterdir()):
        path.unlink()
    (world["runs_dir"] / missing).rmdir()
    with pytest.raises(FileNotFoundError):
        _report(world)


def test_missing_ground_truth_stops_the_report(tmp_path):
    world = _world(tmp_path, _h1_pages("review"))
    for path in (world["data_root"] / "test" / "gt").iterdir():
        path.unlink()
    with pytest.raises(FileNotFoundError):
        _report(world)


def test_the_report_refuses_a_manifest_that_is_not_the_pre_registered_one(tmp_path):
    world = _world(tmp_path, _h1_pages("review"))
    manifest = (world["data_root"] / "test" / "manifest.json").read_bytes()
    with pytest.raises(SystemExit, match="not the pre-registered"):
        _report(world | {"manifest_sha256": "0" * 64})
    report = _report(world | {"manifest_sha256": hashlib.sha256(manifest).hexdigest()})
    assert report["manifest_sha256"] == hashlib.sha256(manifest).hexdigest()
    assert test_report.MANIFEST_SHA256 == (
        "78db32f34cdb7a2aa2fb5ab4f24e5d9540d11729460e9657b604b141c250c1e4"
    )


def test_the_arms_are_scored_under_policy_v2_whatever_their_own_policy(tmp_path):
    world = _world(tmp_path, _h1_pages("review"))
    before = _report(world)["configurations"]["A"]["stats"]
    path = world["runs_dir"] / "test-archivist-A" / "verdicts.jsonl"
    accept = PolicyOutcome(status="accepted", confidence=0.99)
    rewritten = []
    for line in path.read_text().splitlines():
        v = VerdictRecord.model_validate_json(line)
        policies = {"v2": v.policies["v2"], "v3": accept}
        rewritten.append(
            v.model_copy(update={"policy": "v3", "status": "accepted", "policies": policies})
        )
    path.write_text(_lines(rewritten))
    assert _report(world)["configurations"]["A"]["stats"] == before


# --- The bootstrap and determinism ------------------------------------------------------------


def _varied_pages() -> dict[str, list[F]]:
    """Twelve pages of different sizes and outcomes, so that resamples differ."""
    pages = {}
    for p in range(12):
        fields = [F(f"Value {p}-{i}") for i in range(3 + p % 4)]
        for i in range(p % 3):
            fields.append(F(f"Wrong {p}-{i}", read=f"Wr0ng {p}-{i}", a=("accepted", "review")[i]))
        if p % 5 == 0:
            fields.append(F(f"Fine {p}", a="review"))
        pages[f"memo-{p:02d}"] = fields
    return pages


def test_the_bootstrap_draws_2000_resamples_of_whole_pages_with_seed_0(tmp_path, monkeypatch):
    pages = _varied_pages()
    world = _world(tmp_path, pages)
    real = np.random.default_rng
    rngs: list[dict] = []

    class Spy:
        def __init__(self, seed):
            self.rng = real(seed)
            rngs.append({"seed": seed, "draws": []})

        def integers(self, low, high, size):
            rngs[-1]["draws"].append((low, high, size))
            return self.rng.integers(low, high, size=size)

    monkeypatch.setattr(np.random, "default_rng", Spy)
    report = _report(world)
    monkeypatch.undo()

    assert report["bootstrap"] == {"unit": "page", "resamples": 2000, "seed": 0}
    # One bootstrap per scoring: the baseline once, each arm with its extraction alone too.
    assert len(rngs) == 7
    for rng in rngs:
        assert rng["seed"] == 0
        assert rng["draws"] == [(0, len(pages), len(pages))] * 2000


def test_the_intervals_are_the_frozen_page_bootstrap_of_metrics_py(tmp_path):
    world = _world(tmp_path, _varied_pages())
    head = _report(world)["configurations"]["A"]["stats"]
    scored = score_verdicts(world["runs_dir"] / "test-archivist-A", world["data_root"] / "test/gt")
    ours = scored.ours
    for key in ("error_rate_accepted", "review_rate"):
        expected = bootstrap_ci(ours, key, n=2000, seed=0)
        assert tuple(head[f"{key}_ci95"]) == expected
        assert expected != bootstrap_ci(ours, key, n=2000, seed=1)  # the seed matters here

    def catch_rate(sample):
        wrong = [o for o in sample if o.outcome in ("misread", "hallucinated", "omitted")]
        return sum(o.status == "review" for o in wrong) / len(wrong) if wrong else None

    assert tuple(head["catch_rate_ci95"]) == bootstrap_ci(ours, catch_rate, n=2000, seed=0)


def test_two_runs_on_the_same_inputs_give_identical_output(tmp_path):
    world = _world(tmp_path, _varied_pages())
    first = _report(world)
    second = _report(world)
    assert json.dumps(first, indent=2) == json.dumps(second, indent=2)
    assert test_report.render(first, "—") == test_report.render(second, "—")

    # The order of lines in the run files does not matter either.
    shuffle = random.Random(7)
    for run in ("test-baseline", "test-archivist-A", "test-archivist-B", "test-archivist-C"):
        name = "predictions.jsonl" if run == "test-baseline" else "verdicts.jsonl"
        path = world["runs_dir"] / run / name
        lines = path.read_text().splitlines()
        shuffle.shuffle(lines)
        path.write_text("".join(line + "\n" for line in lines))
    third = _report(world)
    assert json.dumps(third, indent=2) == json.dumps(first, indent=2)
    assert test_report.render(third, "—") == test_report.render(first, "—")
