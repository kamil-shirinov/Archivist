"""The open-weights run's scorer (P46, PREREGISTRATION_OPENW.md), on synthetic records only: no
model, no cache, no real page, no label of a held-out cell."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # labelling/ sits beside src/

from labelling import score, score_openw  # noqa: E402
from labelling.score import Scored  # noqa: E402


def cell(n: int, *, page="1940-01_p001", stratum="1939_1942", **changes) -> Scored:
    fields = dict(
        cell=f"T.f:{page}:{n:02d}:c", stratum=stratum, family="f", page=page, weight=1.0, choice="value",
        outcome="right", status="accepted", unanswered=False, both_ways=False,
    )
    return Scored(**(fields | changes))


# --- The measures and the target ----------------------------------------------------------------


def test_sent_to_a_person_is_over_every_drawn_cell_and_follows_the_variant():
    cells = [
        cell(1, status="review"),
        cell(2, status="accepted", unanswered=True),
        cell(3, status=score_openw.NO_VALUE, outcome="abstained"),
        cell(4, status="abstained", outcome="abstained"),
    ]
    as_run = score.estimate(cells, score_openw.parts("as_run"))["sent_to_person"]["value"]
    to_review = score.estimate(cells, score_openw.parts("failed_to_review"))["sent_to_person"]["value"]
    assert (as_run, to_review) == (0.25, 0.5)


def test_o1_is_judged_on_the_rate_itself_in_the_primary_variant():
    def variant(wrong, accepted):
        cells = [cell(n, outcome="wrong" if n < wrong else "right") for n in range(accepted)]
        return score_openw.results(cells)

    passing, failing = variant(0, 200), variant(3, 200)  # 0% and 1.5% wrong among accepted
    assert score_openw.target(passing)["met"] is True
    found = score_openw.target(failing)
    assert found["met"] is False and found["variant"] == "kept/as_run" and found["value"] == 0.015
    assert set(found["in_every_variant"]) == set(failing)
    empty = score_openw.results([cell(1, status="review")])  # nothing accepted: no rate, not met
    assert score_openw.target(empty)["met"] is False


def test_the_measures_are_version_1s_own_functions_on_every_variant():
    cells = [cell(1, outcome="wrong"), cell(2, page="1940-04_p055", both_ways=True), cell(3, stratum="total_claims")]
    mine = score_openw.results(cells)
    theirs = score.label_results(cells)
    assert set(mine) == set(theirs)
    for name in theirs:
        for measure in score_openw.COMPARED:
            assert mine[name]["overall"][measure] == theirs[name]["overall"][measure]
    score_openw.same_as_scored(mine, json.loads(json.dumps(theirs)))
    altered = json.loads(json.dumps(theirs))
    altered["kept/as_run"]["by_stratum"]["total_claims"]["catch_rate"]["value"] = 0.5
    with pytest.raises(ValueError, match="not its score's"):
        score_openw.same_as_scored(mine, altered)


def test_a_cell_open_gave_no_value_is_outside_the_error_rates_and_counted():
    draw = {
        "families": {"f": {"confirmed": 2, "classified": 3, "deep_pages": 1}},
        "strata": {"1939_1942": {"cells": 4, "sampled": 2}},
        "sample": [
            {"cell": "T.f:p:01:c", "stratum": "1939_1942", "family": "f", "page": "p"},
            {"cell": "T.f:p:02:c", "stratum": "1939_1942", "family": "f", "page": "p"},
        ],
    }
    from archivist.schema import Evidence, ExtractedValue, VerdictRecord

    first = {s["cell"]: {"choice": "value", "value": "5"} for s in draw["sample"]}
    found = {"T.f:p:01:c": {"field": "T.f:p:03:c"}, "T.f:p:02:c": {"field": None, "how": "row_not_found"}}
    reads = {"T.f:p:03:c": ExtractedValue(field_id="T.f:p:03:c", value="5", citation=None)}
    verdicts = {
        "T.f:p:03:c": VerdictRecord(
            field_id="T.f:p:03:c", value="5", confidence=0.99, status="accepted", page_id="p", doc_type="f",
            evidence=Evidence(route="arithmetic", citation=None, reread_status="agrees"),
        )
    }
    out = score_openw.open_cells(draw, first, found, reads, verdicts, {"T.f:p:03:c"}, {"f": lambda f, t: t})
    assert [c.outcome for c in out] == ["right", "abstained"]
    assert [c.status for c in out] == ["accepted", score_openw.NO_VALUE]
    assert out[0].unanswered is True and out[0].weight == 2.0 * 2.0
    verdicts["T.f:p:03:c"] = verdicts["T.f:p:03:c"].model_copy(update={"value": "6"})
    with pytest.raises(ValueError, match="not Open's read"):
        score_openw.open_cells(draw, first, found, reads, verdicts, set(), {"f": lambda f, t: t})


# --- Provenance and what must be committed ------------------------------------------------------


def fake_git(head: str, tag: str = "abc123", diff: int = 0):
    def git(*args):
        out, code = "", 0
        if args[:1] == ("rev-parse",):
            out = tag if "--verify" in args else head
        if args[:1] == ("diff",):
            code = diff
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="")

    return git


def test_provenance_refuses_anything_but_a_checkout_of_its_own_tag(tmp_path, monkeypatch):
    with pytest.raises(score_openw.NotFrozen, match="not run-real-openw"):
        score_openw.provenance(tmp_path, git=fake_git(head="def456"))
    with pytest.raises(score_openw.NotFrozen, match="differs"):
        score_openw.provenance(tmp_path, git=fake_git(head="abc123", diff=1))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(score_openw.NotFrozen, match="tag's checkout"):
        score_openw.provenance(tmp_path, git=fake_git(head="abc123"))


def test_records_must_be_committed_and_pushed(tmp_path):
    path = tmp_path / "r.json"
    with pytest.raises(score_openw.NotCommitted, match="missing"):
        score_openw.committed(tmp_path, [path])
    path.write_text("{}\n")

    def git(tracked=True, clean=True, pushed=True):
        def run(*args):
            code = {"ls-files": 0 if tracked else 1, "diff": 0 if clean else 1, "merge-base": 0 if pushed else 1}
            return subprocess.CompletedProcess(args, code.get(args[0], 0), stdout="c" * 40, stderr="")

        return run

    for wrong, says in (({"tracked": False}, "not committed"), ({"clean": False}, "differs"), ({"pushed": False}, "not pushed")):
        with pytest.raises(score_openw.NotCommitted, match=says):
            score_openw.committed(tmp_path, [path], git=git(**wrong))
    assert score_openw.committed(tmp_path, [path], git=git()) == {"r.json": hashlib.sha256(b"{}\n").hexdigest()}


# --- End to end, on synthetic records -----------------------------------------------------------


def test_score_end_to_end_on_synthetic_records(tmp_path, monkeypatch):
    import archivist.models
    from archivist.schema import Evidence, ExtractedValue, PageExtraction, VerdictRecord
    from archivist.templates import real_openw, real_test
    from labelling import draw as drawing

    types = real_test._types(real_test.CONFIG)
    short, claims = "short_term_foreign_liabilities_as", score.DRIFT_FAMILY
    chosen = [(short, "1940-01_p051"), (short, "1940-04_p055"), *((claims, p) for p in score.IRELAND)]

    def pages_reading(text):
        return [
            PageExtraction(
                page_id=page_id,
                doc_type=family,
                values=[ExtractedValue(field_id=f, value=text, citation=None) for f in types[family].field_ids(page_id)],
            )
            for family, page_id in chosen
        ]

    def verdicts_of(pages, status="accepted", reread="agrees"):
        return [
            VerdictRecord(
                field_id=v.field_id, value=v.value, confidence=1.0, status=status, page_id=p.page_id,
                doc_type=p.doc_type, evidence=Evidence(route="reread", citation=None, reread_status=reread),
            )
            for p in pages
            for v in p.values
        ]

    def write(path, lines):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines))

    # Version 1: its records, draw and labels as score.py's own end-to-end test has them, then its score.
    first = tmp_path / real_test.OUT_DIR / score.SIDE
    pages = pages_reading("5")
    write(first / "predictions.jsonl", [p.model_dump_json() for p in pages])
    write(first / "verdicts.jsonl", [v.model_dump_json() for v in verdicts_of(pages)])
    write(first / "boxes.jsonl", [{"page": p.page_id, "box_sources": {v.field_id: "ocr" for v in p.values}} for p in pages])
    strata, coverage = drawing.cells_of(pages, types)
    sample = [
        {"cell": c, "stratum": name, "family": drawing.parts(c)[0], "page": drawing.parts(c)[1]}
        for name, cells in strata.items()
        for c in (*cells[:2], cells[-1])
    ]
    deep = {f: sum(p.doc_type == f for p in pages) for f in real_test.FAMILIES}
    draw = {
        "side": "held_out",
        "families": {f: {"classified": 3 * n, "confirmed": 2 * n, "deep_pages": n} for f, n in deep.items()},
        "strata": {name: {"cells": len(cells), "sampled": 3} for name, cells in strata.items()},
        "coverage_by_page": coverage,
        "sample": sample,
        "relabel": [sample[0]["cell"]],
        "pages_checked": [{"page": "1940-01_p051", "family": short}],
    }
    write(first / "labels" / "draw.json", [draw])
    labels = [{"cell": s["cell"], "choice": "value", "value": "5"} for s in sample]
    labels[1] = {"cell": sample[1]["cell"], "choice": "cant_read", "value": None}
    write(first / "labels" / "labels.jsonl", labels)
    (first / score.LAYOUT_RECORD).write_text(json.dumps({"pages": [{"page": p, "ocr": "changed: 17 columns"} for p in score.BOTH_WAYS]}))
    (first / "sweep.json").write_text(json.dumps({"pages": 9, "classified": 9, "failed": [], "by_family": {},
                                                  "set_aside_by_classifier": 0, "type_unconfirmed": 0, "by_era": {}}))
    write(first / "unanswered_rereads.jsonl", [{"key": "k1"}])
    write(first / "unanswered_rereads_2.jsonl", [])
    monkeypatch.setattr(archivist.models, "load_roles", lambda *a, **k: {"rereader": None, "segmenter": None})
    monkeypatch.setattr(score, "reread_keys", lambda *a: {"k1": {sample[0]["cell"]}, "k2": set()})
    monkeypatch.setattr(score, "detections", lambda pages, *a: {p.page_id: {"stamp": 0, "stain": 0} for p in pages})
    (first / "score").mkdir()
    (first / score_openw.FIRST_SCORE).write_text(json.dumps(score.score(tmp_path)))

    # Open weights: it reads "6" on the first page and "5" elsewhere; one drawn cell it does not find.
    records = tmp_path / real_openw.OUT_DIR / score_openw.SIDE
    opened = [
        p if p.page_id != "1940-01_p051" else p.model_copy(update={"values": [v.model_copy(update={"value": "6"}) for v in p.values]})
        for p in pages_reading("5")
    ]
    write(records / "predictions.jsonl", [p.model_dump_json() for p in opened])
    write(records / "boxes.jsonl", [{"page": p.page_id, "box_sources": {v.field_id: "table:ocr" for v in p.values}} for p in opened])
    found = [{**s, "field": s["cell"], "how": "label", "same_position": True} for s in sample]
    found[-1] |= {"field": None, "how": "row_not_found"}
    (records / "cells.json").write_text(json.dumps({"cells": found}))
    drawn_fields = {c["field"] for c in found if c["field"]}
    final = [v for v in verdicts_of(opened) if v.field_id in drawn_fields]
    final = [v.model_copy(update={"status": "review"}) if v.page_id == "1940-01_p051" and v.field_id != sample[0]["cell"] else v for v in final]
    write(records / "verdicts.jsonl", [v.model_dump_json() for v in final])
    write(records / "verdicts.pass1.jsonl", [v.model_copy(update={"evidence": v.evidence.model_copy(update={"reread_status": "failed"})}).model_dump_json() for v in final if v.field_id == sample[0]["cell"]])
    (records / "run.json").write_text(json.dumps({"pages_read": 7, "failed": [], "cost_usd": {"baseten": 1.0}}))

    record = score_openw.score_openw(tmp_path)
    kept = record["open_weights"]["kept/as_run"]
    assert kept["cells"] == 6 and kept["by_outcome"] == {"right": 3, "wrong": 1, "cant_read": 1, "abstained": 1}
    # The first page's sample[0] Open read 6, labelled 5, and accepted: a wrong value accepted.
    assert kept["overall"]["archivist_error"]["value"] > 0 and record["o1"]["met"] is False
    assert record["open_weights"]["kept/failed_to_review"]["overall"]["archivist_error"]["value"] == 0.0
    assert record["version_1"]["kept/as_run"]["overall"]["single_read_error"]["value"] == 0.0
    assert record["cells_found"]["overall"] == {"label": 5, "row_not_found": 1}
    assert record["cells_found"]["status"][score_openw.NO_VALUE] == 1
    assert record["asked_again"] == {"cells": 1, "drawn": 1}
    assert record["box_sources_drawn_cells"] == {"table:ocr": 5}
    text = score_openw.render({"provenance": {"tag": "t", "commit": "c" * 40, "scorer_sha256": "0" * 64, "rules_sha256": "1" * 64}, **record})
    assert "| kept/as_run | Wrong among accepted |" in text and "**O1**" in text

    scored = json.loads((first / score_openw.FIRST_SCORE).read_text())
    scored["labels"]["kept/as_run"]["overall"]["catch_rate"]["value"] = 0.123
    (first / score_openw.FIRST_SCORE).write_text(json.dumps(scored))
    with pytest.raises(ValueError, match="not its score's"):
        score_openw.score_openw(tmp_path)
