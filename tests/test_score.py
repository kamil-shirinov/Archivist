"""labelling.score on synthetic records only: no held-out record, label or verdict is read."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # labelling/ sits beside src/

from labelling import score  # noqa: E402
from labelling.score import Judged, Scored  # noqa: E402


def canonical(field_id: str, text: str) -> str:
    return text.replace(",", "").strip()


def cell(n: int, *, page: str = "1940-01_p001", stratum: str = "1939_1942", **changes) -> Scored:
    base = Scored(
        cell=f"T.short_term_foreign_liabilities_as:{page}:{n:02d}:france",
        stratum=stratum,
        family="short_term_foreign_liabilities_as",
        page=page,
        weight=1.0,
        choice="value",
        outcome="right",
        status="accepted",
        unanswered=False,
        both_ways=False,
    )
    return replace(base, **changes)


def test_wilson_matches_known_values():
    low, high = score.wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4) and high == pytest.approx(0.7634, abs=1e-4)
    assert score.wilson(0, 0) is None
    assert score.wilson(0, 5)[0] == 0.0 and score.wilson(5, 5)[1] == 1.0


def test_judged_follows_the_labels_rules():
    assert score.judged("f", "value", "1,234", "1234", canonical) == "right"
    assert score.judged("f", "value", "1,234", "1235", canonical) == "wrong"
    assert score.judged("f", "blank", None, "", canonical) == "right"
    assert score.judged("f", "blank", None, "7", canonical) == "wrong"
    assert score.judged("f", "value", "7", "", canonical) == "wrong"
    for choice in ("not_on_page", "column_not_on_page"):
        assert score.judged("f", choice, None, "", canonical) == "wrong"
    assert score.judged("f", "cant_read", None, "7", canonical) == "cant_read"
    assert score.judged("f", "value", "7", None, canonical) == "abstained"
    assert score.judged("f", "cant_read", None, None, canonical) == "cant_read"


def test_rates_are_ratios_of_weighted_sums():
    cells = [
        cell(1, outcome="right", status="accepted", weight=1.0),
        cell(2, outcome="wrong", status="accepted", weight=2.0),
        cell(3, outcome="wrong", status="review", weight=3.0),
        cell(4, outcome="right", status="review", weight=4.0),
        cell(5, outcome="cant_read", status="accepted", weight=50.0),
        cell(6, outcome="abstained", status="abstained", weight=60.0),
    ]
    found = score.estimate(cells, score.label_parts("as_run"))
    assert found["single_read_error"]["value"] == pytest.approx(5 / 10)
    assert found["archivist_error"]["value"] == pytest.approx(2 / 3)
    assert found["catch_rate"]["value"] == pytest.approx(3 / 5)


def test_unanswered_rereads_go_to_review_in_the_second_variant():
    cells = [
        cell(1, outcome="wrong", status="accepted", unanswered=True),
        cell(2, outcome="right", status="accepted"),
    ]
    as_run = score.estimate(cells, score.label_parts("as_run"))
    failed = score.estimate(cells, score.label_parts("failed_to_review"))
    assert as_run["archivist_error"]["value"] == pytest.approx(1 / 2)
    assert failed["archivist_error"]["value"] == 0.0
    assert as_run["catch_rate"]["value"] == 0.0 and failed["catch_rate"]["value"] == 1.0
    assert failed["single_read_error"] == as_run["single_read_error"]


def test_the_bootstrap_resamples_within_strata():
    sums = {
        "a": np.array([[1.0, 1.0]] * 3),
        "b": np.array([[0.0, 1.0]] * 2),
    }
    assert score.stratified_ci(sums) == pytest.approx((0.6, 0.6))
    mixed = {"a": np.array([[1.0, 1.0], [0.0, 1.0], [1.0, 2.0]])}
    assert score.stratified_ci(mixed) == score.stratified_ci(mixed)  # seed 0, reproducible
    low, high = score.stratified_ci(mixed)
    assert 0.0 <= low < high <= 1.0
    assert score.stratified_ci({"a": np.array([[0.0, 0.0]])}) is None
    assert score.stratified_ci({}) is None


def test_estimate_groups_by_page_within_stratum():
    cells = [cell(1, page="p1", outcome="wrong"), cell(2, page="p1"), cell(3, page="p2")]
    cells += [cell(4, page="p3", stratum="total_claims")]
    found = score.estimate(cells, score.label_parts("as_run"))["single_read_error"]
    assert found["value"] == pytest.approx(1 / 4)
    assert found["ci"][0] == 0.0 and found["ci"][1] <= 2 / 3 + 1e-9


def test_weights_follow_the_preregistration():
    draw = {
        "families": {
            "a": {"classified": 30, "confirmed": 24, "deep_pages": 12},
            "b": {"classified": 5, "confirmed": 5, "deep_pages": 5},
        },
        "strata": {"s": {"cells": 1000, "sampled": 100}},
        "sample": [
            {"cell": "x", "family": "a", "stratum": "s"},
            {"cell": "y", "family": "b", "stratum": "s"},
        ],
    }
    assert score.POPULATION == "confirmed"
    assert score.cell_weights(draw) == {"x": 2.0 * 10, "y": 1.0 * 10}
    assert score.cell_weights(draw, "classified") == {"x": 2.5 * 10, "y": 1.0 * 10}


def test_headline_gives_both_error_rates_and_r1_in_every_variant():
    cells = [cell(1, page="p1", outcome="wrong", status="review"), cell(2, page="p2")]
    found = score.headline(cells)
    assert set(found) == {"left_out/as_run", "left_out/failed_to_review", "kept/as_run", "kept/failed_to_review"}
    assert found["kept/as_run"]["single_read_error"]["value"] == pytest.approx(1 / 2)
    assert found["kept/as_run"]["archivist_error"]["value"] == 0.0
    assert found["kept/as_run"]["r1_met"] in (True, False)


def test_r1_is_met_only_when_archivist_lies_wholly_below():
    def overall(mine, single):
        return {"archivist_error": {"ci": mine}, "single_read_error": {"ci": single}}

    assert score.r1(overall((0.01, 0.04), (0.05, 0.09)))["met"]
    assert not score.r1(overall((0.01, 0.06), (0.05, 0.09)))["met"]
    assert not score.r1(overall((0.10, 0.12), (0.05, 0.09)))["met"]
    assert not score.r1(overall(None, (0.05, 0.09)))["met"]


def test_label_results_give_every_variant():
    cells = [
        cell(1, page="p1", outcome="wrong", status="accepted", both_ways=True),
        cell(2, page="p2", outcome="right", status="accepted", unanswered=True),
        cell(3, page="p3", outcome="wrong", status="review", stratum="total_claims"),
        cell(4, page="p4", outcome="cant_read", stratum="total_claims", choice="cant_read"),
    ]
    found = score.label_results(cells)
    assert set(found) == {"left_out/as_run", "left_out/failed_to_review", "kept/as_run", "kept/failed_to_review"}
    assert found["kept/as_run"]["cells"] == 4 and found["left_out/as_run"]["cells"] == 3
    assert found["kept/as_run"]["overall"]["single_read_error"]["value"] == pytest.approx(2 / 3)
    assert found["left_out/as_run"]["overall"]["single_read_error"]["value"] == pytest.approx(1 / 2)
    assert found["kept/as_run"]["by_outcome"] == {"right": 1, "wrong": 2, "cant_read": 1, "abstained": 0}
    assert found["kept/as_run"]["by_stratum"]["total_claims"]["counted"]["cells"] == 2
    assert found["left_out/failed_to_review"]["overall"]["archivist_error"]["value"] is None


def judged_cell(n, **changes) -> Judged:
    base = Judged(
        field_id=f"f{n}",
        family="short_term_foreign_liabilities_as",
        stratum="1939_1942",
        page=f"p{n % 2}",
        weight=1.0,
        status="accepted",
        unanswered=False,
        both_ways=False,
        source="ocr",
    )
    return replace(base, **changes)


def test_review_rate_and_box_sources_over_every_cell():
    units = [
        judged_cell(1, status="review", source="grid"),
        judged_cell(2, unanswered=True),
        judged_cell(3, source=None),
        judged_cell(4, status="abstained", source="model"),
    ]
    found = score.population_results(units)
    as_run, failed = found["kept/as_run"]["overall"], found["kept/failed_to_review"]["overall"]
    assert as_run["review_rate"]["value"] == pytest.approx(1 / 4)
    assert failed["review_rate"]["value"] == pytest.approx(2 / 4)
    assert as_run["boxed_ocr"]["value"] == pytest.approx(1 / 3)
    assert as_run["boxed_grid"]["value"] == pytest.approx(1 / 3)
    assert as_run["boxed_model"]["value"] == pytest.approx(1 / 3)
    family = found["kept/as_run"]["by_family"]["short_term_foreign_liabilities_as"]
    assert family["cells"] == 4


def test_family_weights_weigh_the_review_rate():
    units = [
        judged_cell(1, status="review", weight=3.0),
        judged_cell(2, family="total_claims_by_country", stratum="total_claims", weight=1.0),
    ]
    found = score.population_results(units)["kept/as_run"]["overall"]["review_rate"]["value"]
    assert found == pytest.approx(3 / 4)


def test_both_ways_set_from_the_layout_records():
    record = {
        "pages": [
            {"page": "a", "ocr": "changed: 17 columns"},
            {"page": "b", "ocr": "a different table"},
            {"page": "c", "ocr": "cannot be checked: 18 words; changed (L17), checked by eye"},
            {"page": "d", "ocr": "same as the template"},
            {"page": "e", "ocr": "cannot be checked: 3 words"},
            {"page": "f", "ocr": "cannot be checked: 0 words"},
        ]
    }
    marks = {"e": {"layout": "changed"}, "f": {"layout": "same"}}
    assert score.both_ways(record, marks) == {"a", "b", "c", "e"}


def test_the_fixed_both_ways_set_is_the_deviations_forty():
    assert len(score.BOTH_WAYS) == 40
    assert {score.REVISIONS, "1941-02_p058", "1940-12_p024", "1941-01_p022"} <= score.BOTH_WAYS
    assert not any(p.startswith(("198", "199")) for p in score.BOTH_WAYS)


def test_relabel_agreement_waits_and_compares_by_value():
    draw = {"relabel": ["x", "y", "z"]}
    first = {
        "x": {"choice": "value", "value": "1,000"},
        "y": {"choice": "blank", "value": None},
        "z": {"choice": "value", "value": "5"},
    }
    second = {"x": {"choice": "value", "value": "1000"}, "y": {"choice": "blank", "value": None}}
    assert score.relabel_agreement(draw, first, second, canonical)["status"] == "pending"
    second["z"] = {"choice": "cant_read", "value": None}
    found = score.relabel_agreement(draw, first, second, canonical)
    assert found["agree"] == 2 and found["of"] == 3 and found["wilson"] == score.wilson(2, 3)


def test_classification_check_waits_and_names_wrong_pages():
    draw = {"pages_checked": [{"page": "p1"}, {"page": "p2"}]}
    assert score.precision(draw, {"p1": {"verdict": "right"}})["status"] == "pending"
    found = score.precision(draw, {"p1": {"verdict": "right"}, "p2": {"verdict": "wrong"}})
    assert found["right"] == 1 and found["wrong_pages"] == ["p2"]


@dataclass(frozen=True)
class FakeInstance:
    rule: str
    field: str
    unresolved: str | None = None
    result: tuple | None = None

    def own_field(self) -> str:
        return self.field


class FakeType:
    def __init__(self, instances):
        self._instances = instances

    def instances(self, pages):
        return iter(self._instances)

    def evaluate(self, instance, texts):
        return instance.result


@dataclass
class FakePage:
    page_id: str
    doc_type: str
    values: tuple = ()


def test_identities_by_page_group():
    holds = (Decimal(10), Decimal(10), Decimal("0.5"))
    fails = (Decimal(10), Decimal(12), Decimal("0.5"))
    fake = FakeType(
        [
            FakeInstance("t.sum", "T.t:changed_p1:r:c", result=holds),
            FakeInstance("t.sum", "T.t:changed_p1:r:d", result=fails),
            FakeInstance("t.sum", "T.t:other_p2:r:c", result=None),
            FakeInstance("t.sum", "T.t:other_p2:r:d", unresolved="no page", result=holds),
        ]
    )
    found = score.identities({"t": fake}, [FakePage("changed_p1", "t")], {"changed_p1"})
    assert found == {
        "t.sum": {
            "changed_layout": {"held": 1, "failed": 1, "unchecked": 0},
            "other": {"held": 0, "failed": 0, "unchecked": 2},
        }
    }


def fake_git(head: str, tag: str = "abc123"):
    def git(*args):
        out = ""
        if args[:1] == ("rev-parse",):
            out = tag if "--verify" in args else head
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    return git


def test_provenance_refuses_code_that_is_not_the_tag(tmp_path):
    with pytest.raises(score.NotFrozen, match="not run-real-treasury"):
        score.provenance(tmp_path, git=fake_git(head="def456"))


def test_provenance_refuses_to_run_outside_the_tag_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(score.NotFrozen, match="tag's checkout"):
        score.provenance(tmp_path, git=fake_git(head="abc123"))


def test_provenance_passes_the_tags_frozen_check_through(tmp_path):
    def git(*args):
        if args[:1] == ("diff",):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        return fake_git(head="abc123")(*args)

    with pytest.raises(score.NotFrozen, match="differs"):
        score.provenance(tmp_path, git=git)


def labels_git(*, tracked=True, clean=True, pushed=True):
    def git(*args):
        code, out = 0, ""
        if args[0] == "ls-files":
            code = 0 if tracked else 1
        elif args[0] == "diff":
            code = 0 if clean else 1
        elif args[0] == "log":
            out = "c" * 40
        elif args[0] == "merge-base":
            code = 0 if pushed else 1
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="")

    return git


def test_the_labels_must_be_committed_and_pushed_before_scoring(tmp_path):
    from archivist.templates import real_test

    labels = tmp_path / real_test.OUT_DIR / score.SIDE / "labels"
    labels.mkdir(parents=True)
    with pytest.raises(score.NotCommitted, match="nothing is labelled"):
        score.committed_labels(tmp_path, git=labels_git())
    (labels / "labels.jsonl").write_text('{"cell": "x"}\n')
    (labels / "draw.json").write_text("{}\n")
    for wrong, match in (({"tracked": False}, "not committed"), ({"clean": False}, "differs"), ({"pushed": False}, "not pushed")):
        with pytest.raises(score.NotCommitted, match=match):
            score.committed_labels(tmp_path, git=labels_git(**wrong))
    found = score.committed_labels(tmp_path, git=labels_git())
    assert set(found) == {"draw.json", "labels.jsonl"}
    assert found["labels.jsonl"] == hashlib.sha256(b'{"cell": "x"}\n').hexdigest()


def test_render_shows_every_variant():
    cells = [cell(1, page="p1", outcome="wrong"), cell(2, page="p2", stratum="total_claims")]
    coverage = {
        "p1": {
            "family": "short_term_foreign_liabilities_as",
            **dict.fromkeys(
                ("rows", "rows_not_returned", "rows_left_empty", "figure_cells", "figure_cells_not_returned", "figure_cells_left_empty"),
                1,
            ),
        }
    }
    record = {
        "provenance": {"tag": "run-real-treasury", "commit": "b8ff15d9d8", "scorer_sha256": "0" * 64},
        "weights": {"population": "confirmed"},
        "label_files_sha256": {"labels.jsonl": "f" * 64},
        "labels": score.label_results(cells),
        "headline_with_classified_weights": score.headline(cells),
        "every_cell": score.population_results([judged_cell(1)]),
        "unanswered_rereads": {
            "keys": {"a": 1},
            "cells": 1,
            "accepted_as_run": 0,
            "sampled_cells": 0,
            "sampled_accepted_as_run": 0,
        },
        "coverage_by_page": coverage,
        "coverage_by_family": {"short_term_foreign_liabilities_as": {"pages": 1, **{k: v for k, v in coverage["p1"].items() if k != "family"}}},
        "identities": {"t.sum": {"changed_layout": {"held": 1, "failed": 0, "unchecked": 0}, "other": {"held": 0, "failed": 0, "unchecked": 0}}},
        "template_drift": {"1993-06_p097": {"prints_gdr_row": False}},
        "revisions_page": {"page": score.REVISIONS, "what": "a different table", "cells": 1, "by_status": {}, "labelled_cells": {}},
        "sweep": {},
        "sam": {},
        "relabel": {"status": "pending"},
        "classification_check": {"status": "pending"},
    }
    text = score.render(record)
    for variant in ("left_out/as_run", "kept/failed_to_review"):
        assert variant in text
    assert "| p1 | short_term_foreign_liabilities_as | 1 | 1 | 1 | 1 | 1 | 1 |" in text
    assert "t.sum | 1 / 0 / 0 | 0 / 0 / 0" in text
    assert "`labels.jsonl` " + "f" * 64 in text
    shown = [line for line in text.splitlines() if line.startswith("With classified-page weights")]
    assert len(shown) == 1 and "kept/failed_to_review: single read" in shown[0]


def test_score_end_to_end_on_synthetic_records(tmp_path, monkeypatch):
    import json

    import archivist.models
    from archivist.schema import Evidence, ExtractedValue, PageExtraction, VerdictRecord
    from archivist.templates import real_test
    from labelling import draw as drawing

    types = real_test._types(real_test.CONFIG)
    short, claims = "short_term_foreign_liabilities_as", score.DRIFT_FAMILY
    chosen = [(short, "1940-01_p051"), (short, "1940-04_p055"), *((claims, p) for p in score.IRELAND)]
    pages = [
        PageExtraction(
            page_id=page_id,
            doc_type=family,
            values=[ExtractedValue(field_id=f, value="5", citation=None) for f in types[family].field_ids(page_id)],
        )
        for family, page_id in chosen
    ]
    records = tmp_path / real_test.OUT_DIR / score.SIDE
    (records / "labels").mkdir(parents=True)

    def write(name, lines):
        (records / name).write_text("".join(json.dumps(line) + "\n" for line in lines))

    (records / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    verdicts = [
        VerdictRecord(
            field_id=v.field_id,
            value=v.value,
            confidence=1.0,
            status="accepted",
            page_id=p.page_id,
            doc_type=p.doc_type,
            evidence=Evidence(route="reread", citation=None, reread_status="agrees"),
        )
        for p in pages
        for v in p.values
    ]
    (records / "verdicts.jsonl").write_text("".join(v.model_dump_json() + "\n" for v in verdicts))
    write("boxes.jsonl", [{"page": p.page_id, "box_sources": {v.field_id: "ocr" for v in p.values}} for p in pages])
    strata, coverage = drawing.cells_of(pages, types)
    sample = [
        {"cell": c, "stratum": name, "family": drawing.parts(c)[0], "page": drawing.parts(c)[1]}
        for name, cells in strata.items()
        for c in (*cells[:2], cells[-1])  # the last 1939–1942 cell is on 1940-04 p055
    ]
    deep = {f: sum(p.doc_type == f for p in pages) for f in real_test.FAMILIES}
    draw = {
        "families": {f: {"classified": 3 * n, "confirmed": 2 * n, "deep_pages": n} for f, n in deep.items()},
        "strata": {name: {"cells": len(cells), "sampled": 3} for name, cells in strata.items()},
        "coverage_by_page": coverage,
        "sample": sample,
        "relabel": [sample[0]["cell"]],
        "pages_checked": [{"page": "1940-01_p051", "family": short}],
    }
    (records / "labels" / "draw.json").write_text(json.dumps(draw))
    labels = [{"cell": s["cell"], "choice": "value", "value": "5"} for s in sample]
    labels[1] = {"cell": sample[1]["cell"], "choice": "cant_read", "value": None}
    write("labels/labels.jsonl", labels)
    (records / score.LAYOUT_RECORD).write_text(
        json.dumps({"pages": [{"page": p, "ocr": "changed: 17 columns"} for p in score.BOTH_WAYS]})
    )
    (records / "sweep.json").write_text(
        json.dumps(
            {"pages": 9, "classified": 9, "failed": [], "by_family": {}, "set_aside_by_classifier": 0,
             "type_unconfirmed": 0, "by_era": {}}
        )
    )
    write("unanswered_rereads.jsonl", [{"key": "k1"}])
    write("unanswered_rereads_2.jsonl", [])

    unanswered_cell = sample[0]["cell"]
    monkeypatch.setattr(archivist.models, "load_roles", lambda *a, **k: {"rereader": None, "segmenter": None})
    monkeypatch.setattr(score, "reread_keys", lambda *a: {"k1": {unanswered_cell}, "k2": set()})
    monkeypatch.setattr(score, "detections", lambda pages, *a: {p.page_id: {"stamp": 0, "stain": 1} for p in pages})

    record = score.score(tmp_path)
    kept = record["labels"]["kept/as_run"]
    assert kept["cells"] == 6 and kept["by_outcome"]["cant_read"] == 1
    assert kept["overall"]["single_read_error"]["value"] == 0.0
    assert record["labels"]["left_out/as_run"]["cells"] == 5  # 1940-04 p055 is a both-ways page
    assert record["unanswered_rereads"]["cells"] == 1 and record["unanswered_rereads"]["sampled_cells"] == 1
    assert record["every_cell"]["kept/failed_to_review"]["overall"]["review_rate"]["value"] > 0
    assert set(record["template_drift"]) == set(score.IRELAND)
    assert record["template_drift"]["1993-06_p097"]["prints_gdr_row"] is False
    assert record["coverage_by_page"] == coverage
    assert record["weights"]["family_weights"][short] == 2.0
    assert set(record["headline_with_classified_weights"]) == set(record["labels"])
    assert record["sam"]["pages_with_a_detection"] == len(pages)
    assert record["relabel"]["status"] == "pending" and record["classification_check"]["status"] == "pending"
    score.render({"provenance": {"tag": "t", "commit": "c" * 40, "scorer_sha256": "0" * 64}, **record})

    write("unanswered_rereads_2.jsonl", [{"key": "stray"}])
    with pytest.raises(ValueError, match="match no re-read"):
        score.score(tmp_path)
