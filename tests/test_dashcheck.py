"""The dash check (labelling/serve.py, /dashcheck) and the corrected-key score
(labelling/score_corrected.py), on synthetic records only: no held-out record, label or page is
read, and nothing is scored for real."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # labelling/ sits beside src/

from archivist.schema import BBox, Citation, ExtractedValue, PageExtraction  # noqa: E402
from archivist.templates import real_test  # noqa: E402
from labelling import draw, score, score_corrected, score_openw, serve  # noqa: E402

TYPES = real_test._types(real_test.CONFIG)
RAILROAD = "receipts_and_expenditures_under_railroad"
START = datetime(2026, 11, 1, 9, tzinfo=UTC)


# --- The page -----------------------------------------------------------------------------------


@pytest.fixture
def labels(tmp_path: Path, monkeypatch) -> serve.Labels:
    out = tmp_path / "held_out"
    out.mkdir()
    pages = []
    for m in range(1, 7):
        page_id = f"1940-{m:02d}_p026"
        values = [
            ExtractedValue(
                field_id=f, value="-", citation=Citation(page_id=page_id, bbox=BBox(x0=1, y0=2, x1=30, y1=12))
            )
            for f in TYPES[RAILROAD].field_ids(page_id)
        ]
        pages.append(PageExtraction(page_id=page_id, doc_type=RAILROAD, values=values))
    (out / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    by_family = {f: {"classified": 3, "confirmed": 2, "type_unconfirmed": 1} for f in real_test.FAMILIES}
    (out / "sweep.json").write_text(json.dumps({"by_family": by_family}))
    titles = [{"page": p.page_id, "classified_as": p.doc_type, "pattern": "x"} for p in pages]
    (out / "titles.jsonl").write_text("".join(json.dumps(t) + "\n" for t in titles))
    (out / "verdicts.jsonl").write_text("")
    (out / "run.json").write_text("{}")
    monkeypatch.setattr(real_test, "OUT_DIR", tmp_path)
    draw.main(["--side", "held_out"])
    return serve.Labels("held_out", out / "labels")


def _first_pass(labels: serve.Labels, monkeypatch, blank_every: int = 10) -> list[str]:
    """Every drawn cell labelled 7, except every tenth, labelled blank; returns the blanks."""
    monkeypatch.setattr(serve, "_now", lambda: START)
    blanks = []
    for n, sampled in enumerate(labels.draw["sample"]):
        if n % blank_every == 0:
            labels.answer({"pass": "first", "cell": sampled["cell"], "choice": "blank"})
            blanks.append(sampled["cell"])
        else:
            labels.answer({"pass": "first", "cell": sampled["cell"], "choice": "value", "value": "7"})
    return blanks


def test_the_labelling_page_states_the_dash_rule() -> None:
    page = (Path(serve.__file__).parent / "label.html").read_text()
    assert 'A printed dash is typed "-". Blank means nothing is printed in the cell.' in page


def test_the_dash_check_waits_for_the_whole_relabel(labels: serve.Labels, monkeypatch) -> None:
    _first_pass(labels, monkeypatch)
    shown = labels.dashes()
    assert "40 of 40 relabel cells have no answer" in shown["blocked"] and shown["cells"] == []
    with pytest.raises(ValueError, match="not open"):
        labels.dash({"cell": labels.blanks()[0], "mark": "dash"})
    monkeypatch.setattr(serve, "_now", lambda: START + timedelta(hours=24))
    for cell in labels.draw["relabel"][:-1]:
        labels.answer({"pass": "relabel", "cell": cell, "choice": "blank"})
    assert "1 of 40" in labels.dashes()["blocked"]
    labels.answer({"pass": "relabel", "cell": labels.draw["relabel"][-1], "choice": "value", "value": "-"})
    assert labels.dashes()["blocked"] is None


def _relabelled(labels: serve.Labels, monkeypatch) -> list[str]:
    blanks = _first_pass(labels, monkeypatch)
    monkeypatch.setattr(serve, "_now", lambda: START + timedelta(hours=24))
    for cell in labels.draw["relabel"]:
        labels.answer({"pass": "relabel", "cell": cell, "choice": "value", "value": "7"})
    monkeypatch.setattr(serve, "_now", lambda: START + timedelta(hours=25))
    return blanks


def test_every_first_pass_blank_is_shown_named_never_with_a_read(labels: serve.Labels, monkeypatch) -> None:
    blanks = _relabelled(labels, monkeypatch)
    shown = labels.dashes()
    assert [c["cell"] for c in shown["cells"]] == blanks == labels.blanks() and len(blanks) == 30
    for cell in shown["cells"]:
        # the labelling page's naming and locator: no figure, verdict, box source or first label
        assert set(cell) == {
            "n", "cell", "page", "title", "unit", "row_label", "row_heading", "row_hint",
            "occurrence", "column", "box",
        }  # fmt: skip
    assert shown["answers"] == {}


def test_a_blank_is_marked_dash_nothing_or_cant_tell_and_the_last_mark_stands(
    labels: serve.Labels, monkeypatch
) -> None:
    blanks = _relabelled(labels, monkeypatch)
    not_blank = next(s["cell"] for s in labels.draw["sample"] if s["cell"] not in blanks)
    with pytest.raises(ValueError, match="not a first-pass blank"):
        labels.dash({"cell": not_blank, "mark": "dash"})
    with pytest.raises(ValueError, match="mark must be one of"):
        labels.dash({"cell": blanks[0], "mark": "zero"})
    labels.dash({"cell": blanks[0], "mark": "nothing"})
    labels.dash({"cell": blanks[0], "mark": "dash"})
    labels.dash({"cell": blanks[1], "mark": "cant_tell"})
    lines = (labels.labels / serve.DASH_ANSWERS).read_text().splitlines()
    assert [json.loads(line)["mark"] for line in lines] == ["nothing", "dash", "cant_tell"]
    assert set(json.loads(lines[0])) == {"cell", "mark", "checked_at"}
    assert labels.dashes()["answers"] == {blanks[0]: {"mark": "dash"}, blanks[1]: {"mark": "cant_tell"}}
    # the marks go to their own file: the label files are untouched by them
    assert not any("mark" in line for line in (labels.labels / "labels.jsonl").read_text().splitlines())


def test_the_first_mark_closes_the_relabel_pass(labels: serve.Labels, monkeypatch) -> None:
    blanks = _relabelled(labels, monkeypatch)
    assert labels.cells("relabel")["blocked"] is None
    labels.dash({"cell": blanks[0], "mark": "dash"})
    assert "relabel pass is closed" in labels.cells("relabel")["blocked"]
    with pytest.raises(ValueError, match="not a pass open"):
        labels.answer({"pass": "relabel", "cell": labels.draw["relabel"][0], "choice": "blank"})


def test_the_server_serves_the_dash_check(labels: serve.Labels, monkeypatch) -> None:
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    blanks = _relabelled(labels, monkeypatch)
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.handler(labels))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(f"{base}/dashcheck").read().decode()
        assert "Dash printed" in page and "Nothing printed" in page and "Can't tell" in page
        state = json.loads(urllib.request.urlopen(f"{base}/api/dashes").read())
        assert len(state["cells"]) == len(blanks)
        request = urllib.request.Request(
            f"{base}/api/dash",
            data=json.dumps({"cell": blanks[0], "mark": "dash"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert json.loads(urllib.request.urlopen(request).read())["mark"] == "dash"
    finally:
        server.shutdown()


# --- The corrected key --------------------------------------------------------------------------


def test_only_blanks_marked_dash_change_and_only_to_a_dash() -> None:
    first = {
        "a": {"cell": "a", "choice": "blank", "value": None},
        "b": {"cell": "b", "choice": "blank", "value": None},
        "c": {"cell": "c", "choice": "blank", "value": None},
        "d": {"cell": "d", "choice": "value", "value": "5"},
        "e": {"cell": "e", "choice": "cant_read", "value": None},
    }
    marks = {"a": {"mark": "dash"}, "b": {"mark": "nothing"}, "c": {"mark": "cant_tell"}, "d": {"mark": "dash"}}
    key = score_corrected.corrected_key(first, marks)
    assert key["a"]["choice"] == "value" and key["a"]["value"] == "-"
    assert all(key[c] == first[c] for c in "bcde")
    assert first["a"]["choice"] == "blank"  # the first-pass key itself is not changed


def _draw(cells: list[str]) -> dict:
    sample = [{"cell": c, "stratum": "1939_1942" if i % 2 else "total_claims"} for i, c in enumerate(cells)]
    return {"sample": sample, "relabel": cells[:2]}


def test_ready_needs_the_relabel_first_and_every_blank_marked() -> None:
    cells = ["a", "b", "c"]
    first = {"a": {"choice": "blank"}, "b": {"choice": "value"}, "c": {"choice": "blank"}}
    relabels = [{"cell": "a", "labelled_at": "2026-11-03T09:00:00+00:00"}, {"cell": "b", "labelled_at": "2026-11-03T09:01:00+00:00"}]
    dashes = [
        {"cell": "a", "mark": "dash", "checked_at": "2026-11-03T10:00:00+00:00"},
        {"cell": "c", "mark": "nothing", "checked_at": "2026-11-03T10:01:00+00:00"},
    ]
    score_corrected.ready(_draw(cells), first, relabels, dashes)
    with pytest.raises(score_corrected.NotReady, match="relabel cells have no answer"):
        score_corrected.ready(_draw(cells), first, relabels[:1], dashes)
    with pytest.raises(score_corrected.NotReady, match="after the dash check began"):
        late = [*relabels, {"cell": "a", "labelled_at": "2026-11-03T10:00:30+00:00"}]
        score_corrected.ready(_draw(cells), first, late, dashes)
    with pytest.raises(score_corrected.NotReady, match="1 of 2 first-pass blanks have no dash mark"):
        score_corrected.ready(_draw(cells), first, relabels, dashes[:1])
    with pytest.raises(score_corrected.NotReady, match="not first-pass blanks"):
        stray = [*dashes, {"cell": "b", "mark": "dash", "checked_at": "2026-11-03T10:02:00+00:00"}]
        score_corrected.ready(_draw(cells), first, relabels, stray)
    with pytest.raises(score_corrected.NotReady, match="no mark"):
        score_corrected.ready(_draw(cells), first, relabels, [])


def test_changes_are_counted_overall_and_by_stratum() -> None:
    cells = ["a", "b", "c", "d"]
    first = {c: {"cell": c, "choice": "blank", "value": None} for c in cells}
    marks = {"a": {"mark": "dash"}, "b": {"mark": "dash"}, "c": {"mark": "nothing"}, "d": {"mark": "cant_tell"}}
    key = score_corrected.corrected_key(first, marks)
    found = score_corrected.changes(_draw(cells), first, key, marks)
    assert found["answers_changed"] == 2 and found["labelled_cells"] == 4
    assert found["marks"] == {"dash": 2, "nothing": 1, "cant_tell": 1}
    assert found["answers_changed_by_stratum"] == {"1939_1942": 1, "total_claims": 1}


def _records(tmp_path: Path, monkeypatch) -> tuple[Path, list[dict]]:
    """Synthetic held-out records, labels and an official score, as test_score's end-to-end test
    builds them; the first read gives "-" where the first pass says blank."""
    import archivist.models
    from archivist.schema import Evidence, VerdictRecord
    from labelling import draw as drawing

    short, claims = "short_term_foreign_liabilities_as", score.DRIFT_FAMILY
    chosen = [(short, "1940-01_p051"), (short, "1940-04_p055"), *((claims, p) for p in score.IRELAND)]
    pages = [
        PageExtraction(
            page_id=page_id,
            doc_type=family,
            values=[ExtractedValue(field_id=f, value="5", citation=None) for f in TYPES[family].field_ids(page_id)],
        )
        for family, page_id in chosen
    ]
    strata, coverage = drawing.cells_of(pages, TYPES)
    sample = [
        {"cell": c, "stratum": name, "family": drawing.parts(c)[0], "page": drawing.parts(c)[1]}
        for name, cells in strata.items()
        for c in cells[:4]
    ]
    dashed = {sample[0]["cell"], sample[1]["cell"], sample[4]["cell"]}
    for page in pages:
        for value in page.values:
            if value.field_id in dashed:
                value.value = "-"
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
    deep = {f: sum(p.doc_type == f for p in pages) for f in real_test.FAMILIES}
    the_draw = {
        "families": {f: {"classified": 3 * n, "confirmed": 2 * n, "deep_pages": n} for f, n in deep.items()},
        "strata": {name: {"cells": len(cells), "sampled": 4} for name, cells in strata.items()},
        "coverage_by_page": coverage,
        "sample": sample,
        "relabel": [sample[0]["cell"], sample[2]["cell"]],
        "pages_checked": [{"page": "1940-01_p051", "family": short}],
    }
    (records / "labels" / "draw.json").write_text(json.dumps(the_draw))
    first = [
        {"cell": s["cell"], "choice": "blank", "value": None, "labelled_at": "2026-11-01T09:00:00+00:00"}
        if s["cell"] in dashed
        else {"cell": s["cell"], "choice": "value", "value": "5", "labelled_at": "2026-11-01T09:00:00+00:00"}
        for s in sample
    ]
    write("labels/labels.jsonl", first)
    (records / score.LAYOUT_RECORD).write_text(
        json.dumps({"pages": [{"page": p, "ocr": "changed: 17 columns"} for p in score.BOTH_WAYS]})
    )
    (records / "sweep.json").write_text(
        json.dumps(
            {"pages": 9, "classified": 9, "failed": [], "by_family": {}, "set_aside_by_classifier": 0,
             "type_unconfirmed": 0, "by_era": {}}
        )
    )
    write("unanswered_rereads.jsonl", [])
    write("unanswered_rereads_2.jsonl", [])
    monkeypatch.setattr(archivist.models, "load_roles", lambda *a, **k: {"rereader": None, "segmenter": None})
    monkeypatch.setattr(score, "reread_keys", lambda *a: {})
    monkeypatch.setattr(score, "detections", lambda pages, *a: {p.page_id: {"stamp": 0} for p in pages})

    official = score.score(tmp_path)
    official["provenance"] = {"scorer_sha256": hashlib.sha256(Path(score.__file__).read_bytes()).hexdigest()}
    official["label_files_sha256"] = {
        "labels.jsonl": hashlib.sha256((records / "labels" / "labels.jsonl").read_bytes()).hexdigest()
    }
    (records / "score").mkdir()
    (records / "score" / "score.json").write_text(json.dumps(official, indent=2) + "\n")

    # Open weights reads what version 1 read, found every drawn cell by label and accepted it.
    from archivist.templates import real_openw

    opened = tmp_path / real_openw.OUT_DIR / score.SIDE
    opened.mkdir(parents=True)
    (opened / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    (opened / "boxes.jsonl").write_text(
        "".join(json.dumps({"page": p.page_id, "box_sources": {v.field_id: "table:ocr" for v in p.values}}) + "\n" for p in pages)
    )
    found = [{**s, "field": s["cell"], "how": "label", "same_position": True} for s in sample]
    (opened / "cells.json").write_text(json.dumps({"cells": found}))
    drawn = {s["cell"] for s in sample}
    (opened / "verdicts.jsonl").write_text("".join(v.model_dump_json() + "\n" for v in verdicts if v.field_id in drawn))
    (opened / "run.json").write_text(json.dumps({"pages_read": len(pages), "failed": []}))
    open_official = score_openw.score_openw(tmp_path)
    open_official["provenance"] = {
        "scorer_sha256": hashlib.sha256(Path(score_openw.__file__).read_bytes()).hexdigest(),
        "rules_sha256": hashlib.sha256(Path(score.__file__).read_bytes()).hexdigest(),
    }
    open_official["files_sha256"] = dict(official["label_files_sha256"])
    (opened / "score").mkdir()
    (opened / "score" / "score.json").write_text(json.dumps(open_official, indent=2) + "\n")

    write(
        "labels/relabels.jsonl",
        [
            {"cell": sample[0]["cell"], "choice": "value", "value": "-", "labelled_at": "2026-11-03T09:00:00+00:00"},
            {"cell": sample[2]["cell"], "choice": "value", "value": "5", "labelled_at": "2026-11-03T09:01:00+00:00"},
        ],
    )
    marks = {sample[0]["cell"]: "dash", sample[1]["cell"]: "nothing", sample[4]["cell"]: "dash"}
    write(
        "labels/dashes_checked.jsonl",
        [{"cell": c, "mark": m, "checked_at": "2026-11-03T10:00:00+00:00"} for c, m in marks.items()],
    )
    return records, sample


def test_the_corrected_key_is_scored_by_the_official_functions_beside_the_official_score(
    tmp_path: Path, monkeypatch
) -> None:
    records, _ = _records(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in (records / "labels").iterdir()} | {
        records / "score" / "score.json": (records / "score" / "score.json").read_bytes()
    }
    record = score_corrected.version_1(tmp_path)

    official, corrected = record["official"]["labels"], record["corrected_key"]["labels"]
    assert official["kept/as_run"]["by_outcome"]["wrong"] == 3  # each "-" read against a blank
    assert corrected["kept/as_run"]["by_outcome"]["wrong"] == 1  # the one marked nothing printed
    assert corrected["kept/as_run"]["by_choice"] == {"blank": 1, "value": 7}
    assert record["changes"]["answers_changed"] == 2 and record["changes"]["cells_checked"] == 3
    assert record["changes"]["marks"] == {"dash": 2, "nothing": 1, "cant_tell": 0}
    agreement = record["relabel_agreement"]
    assert agreement["first_pass_key"]["agree"] == 1 and agreement["corrected_key"]["agree"] == 2
    # nothing under labels/ or score/ was written
    assert all(path.read_bytes() == data for path, data in before.items())
    assert not (records / score_corrected.OUT).exists()

    text = score_corrected.render(
        {
            "provenance": {"tag": "run-real-treasury", "commit": "c" * 40, "scorers_sha256": {"labelling/score.py": "s" * 64}},
            "files_sha256": {"labels.jsonl": "f" * 64},
            **record,
        }
    )
    rows = [line for line in text.splitlines() if line.startswith("| kept/as_run |")]
    assert "**official**" in rows[0] and "corrected" in rows[1]  # the official score always first
    assert "Answers changed: 2 of 8" in text


def test_the_corrected_score_refuses_a_key_or_scorer_other_than_the_official_scores(
    tmp_path: Path, monkeypatch
) -> None:
    records, _ = _records(tmp_path, monkeypatch)
    official = json.loads((records / "score" / "score.json").read_text())
    official["label_files_sha256"]["labels.jsonl"] = "0" * 64
    (records / "score" / "score.json").write_text(json.dumps(official))
    with pytest.raises(score_corrected.NotReady, match="not the file the official score recorded"):
        score_corrected.version_1(tmp_path)


def test_the_corrected_score_refuses_unless_the_official_results_are_reproduced(
    tmp_path: Path, monkeypatch
) -> None:
    records, _ = _records(tmp_path, monkeypatch)
    official = json.loads((records / "score" / "score.json").read_text())
    official["labels"]["kept/as_run"]["overall"]["single_read_error"]["value"] = 0.5
    (records / "score" / "score.json").write_text(json.dumps(official))
    with pytest.raises(ValueError, match="does not reproduce the official labels"):
        score_corrected.version_1(tmp_path)


def test_the_corrected_score_needs_its_files_committed_and_pushed(tmp_path: Path) -> None:
    import subprocess

    path = tmp_path / "dashes_checked.jsonl"
    path.write_text("{}\n")

    def git(tracked=True, clean=True, pushed=True):
        def run(*args):
            code = {"ls-files": tracked, "diff": clean, "merge-base": pushed}.get(args[0], True)
            return subprocess.CompletedProcess(args, 0 if code else 1, stdout="abc\n", stderr="")

        return run

    for wrong, match in (({"tracked": False}, "not committed"), ({"clean": False}, "differs"), ({"pushed": False}, "not pushed")):
        with pytest.raises(score.NotCommitted, match=match):
            score_corrected.committed(tmp_path, [path], git=git(**wrong))
    with pytest.raises(score.NotCommitted, match="missing"):
        score_corrected.committed(tmp_path, [tmp_path / "relabels.jsonl"], git=git())
    assert score_corrected.committed(tmp_path, [path], git=git()) == {
        "dashes_checked.jsonl": hashlib.sha256(b"{}\n").hexdigest()
    }


def test_the_dash_marks_are_named_as_the_server_names_them() -> None:
    assert score_corrected.DASH_ANSWERS == serve.DASH_ANSWERS
    assert score_corrected.DASH_MARKS == serve.DASH_MARKS


def test_open_weights_is_scored_on_the_same_key_by_its_own_scorer(tmp_path: Path, monkeypatch) -> None:
    from archivist.templates import real_openw

    records, _ = _records(tmp_path, monkeypatch)
    opened = tmp_path / real_openw.OUT_DIR / score.SIDE
    before = {path: path.read_bytes() for path in (*(records / "labels").iterdir(), opened / "score" / "score.json")}
    record = score_corrected.open_weights(tmp_path)

    official, corrected = record["official"], record["corrected_key"]
    assert official["open_weights"]["kept/as_run"]["by_outcome"]["wrong"] == 3
    assert corrected["open_weights"]["kept/as_run"]["by_outcome"]["wrong"] == 1
    # version 1's side-by-side figures move with the key too, and equal version_1()'s
    assert corrected["version_1"]["kept/as_run"]["by_outcome"]["wrong"] == 1
    v1 = score_corrected.version_1(tmp_path)["corrected_key"]["labels"]
    for name, variant in corrected["version_1"].items():
        for measure in ("single_read_error", "archivist_error", "catch_rate"):
            assert variant["overall"][measure] == v1[name]["overall"][measure]
    assert corrected["cells_found"] == official["cells_found"]
    assert record["changes"]["answers_changed"] == 2
    assert all(path.read_bytes() == data for path, data in before.items())
    assert not (opened / score_corrected.OUT).exists()

    text = score_corrected.render_open(
        {
            "provenance": {"tag": "run-real-openw", "commit": "c" * 40, "scorers_sha256": {"labelling/score_openw.py": "s" * 64}},
            "files_sha256": {"labels.jsonl": "f" * 64},
            **record,
        }
    )
    rows = [line for line in text.splitlines() if line.startswith("| kept/as_run | Wrong among accepted |")]
    assert "**official**" in rows[0] and "corrected" in rows[1]  # the official score always first
    assert text.index("**O1** (official") < text.index("**O1** (corrected key") and "O1 stands as scored" in text
    assert "Coverage (the same under both keys)" in text


def test_open_weights_refuses_unless_its_official_score_is_reproduced(tmp_path: Path, monkeypatch) -> None:
    from archivist.templates import real_openw

    _records(tmp_path, monkeypatch)
    path = tmp_path / real_openw.OUT_DIR / score.SIDE / "score" / "score.json"
    official = json.loads(path.read_text())
    official["open_weights"]["kept/as_run"]["overall"]["archivist_error"]["value"] = 0.5
    path.write_text(json.dumps(official))
    with pytest.raises(ValueError, match="does not reproduce the official open_weights"):
        score_corrected.open_weights(tmp_path)
    official["provenance"]["rules_sha256"] = "0" * 64
    path.write_text(json.dumps(official))
    with pytest.raises(score_corrected.NotReady, match="not the rules the official score recorded"):
        score_corrected.open_weights(tmp_path)


def test_open_weights_runs_only_with_the_tags_own_labelling(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # not the checkout labelling/ was imported from
    with pytest.raises(SystemExit):
        score_corrected.main(["open_weights", "--data", str(tmp_path)])
