"""The labels' draw and the labelling pages' server (labelling/): no model, no network, records
written in tmp_path from the approved templates' own cell ids."""

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # labelling/ sits beside src/

from archivist.schema import BBox, Citation, ExtractedValue, PageExtraction  # noqa: E402
from archivist.templates import real_test  # noqa: E402
from labelling import draw, serve  # noqa: E402

TYPES = real_test._types(real_test.CONFIG)
RAILROAD, CLAIMS = "receipts_and_expenditures_under_railroad", "total_claims_by_country"


def _page(family: str, page_id: str, *, abstain_rows: frozenset[str] = frozenset()) -> PageExtraction:
    values = []
    for field in TYPES[family].field_ids(page_id):
        row = draw.parts(field)[2]
        gone = row in abstain_rows
        values.append(
            ExtractedValue(
                field_id=field,
                value=None if gone else "1",
                citation=None if gone else Citation(page_id=page_id, bbox=BBox(x0=1, y0=2, x1=30, y1=12)),
                abstained=gone,
            )
        )
    return PageExtraction(page_id=page_id, doc_type=family, values=values)


def _records(out: Path, pages: list[PageExtraction], *, finished: bool = True) -> None:
    out.mkdir(parents=True)
    (out / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    by_family = {f: {"classified": 3, "confirmed": 2, "type_unconfirmed": 1} for f in real_test.FAMILIES}
    (out / "sweep.json").write_text(json.dumps({"by_family": by_family}))
    titles = [
        {"page": p.page_id, "classified_as": p.doc_type, "pattern": "x"} for p in pages
    ] + [{"page": "1940-01_p099", "classified_as": RAILROAD, "pattern": None}]
    (out / "titles.jsonl").write_text("".join(json.dumps(t) + "\n" for t in titles))
    if finished:
        (out / "verdicts.jsonl").write_text("")
        (out / "run.json").write_text("{}")


@pytest.fixture
def records(tmp_path: Path) -> Path:
    out = tmp_path / "held_out"
    railroad = [_page(RAILROAD, f"1940-{m:02d}_p026") for m in range(1, 7)]  # 510 figure cells
    claims = _page(CLAIMS, "1993-06_p097", abstain_rows=frozenset(TYPES[CLAIMS].layout.row_keys[:45]))
    _records(out, [*railroad, claims])
    return out


def test_the_draw_waits_for_both_runs(tmp_path: Path) -> None:
    out = tmp_path / "held_out"
    _records(out, [_page(RAILROAD, "1940-01_p026")], finished=False)
    with pytest.raises(FileNotFoundError, match="after both runs"):
        draw.draw(out)


def test_cells_are_figure_cells_of_returned_rows_sorted_by_id(records: Path) -> None:
    from archivist.pipeline import extract

    pages = extract.load_predictions(records / "predictions.jsonl")
    cells, coverage = draw.cells_of(pages, TYPES)
    railroad_money = TYPES[RAILROAD].money_fields
    assert cells["1939_1942"] == sorted(cells["1939_1942"])
    assert {draw.parts(c)[3] for c in cells["1939_1942"]} == railroad_money
    assert len(cells["1939_1942"]) == 6 * len(TYPES[RAILROAD].layout.row_keys) * len(railroad_money)
    claims_rows = TYPES[CLAIMS].layout.row_keys
    claims_money = len(TYPES[CLAIMS].money_fields)
    assert coverage["1993-06_p097"] == {
        "family": CLAIMS,
        "rows": len(claims_rows),
        "rows_not_returned": 45,
        "rows_left_empty": 0,
        "figure_cells": len(claims_rows) * claims_money,
        "figure_cells_not_returned": 45 * claims_money,
        "figure_cells_left_empty": 0,
    }
    assert {draw.parts(c)[2] for c in cells["total_claims"]} == set(claims_rows[45:])


def test_rows_the_read_left_empty_are_counted_not_sampled() -> None:
    forward = "outstanding_forward_exchange_contracts"
    money = TYPES[forward].money_fields
    page = _labelled(forward, "1940-02_p062", {"total_purchase_01": "Sept. 6....", "total_purchase_02": "Sept. 13"})
    for value in page.values:
        _, _, row, column = draw.parts(value.field_id)
        if column in money and row in ("total_purchase_02", "total_purchase_05", "total_sale_05"):
            value.value = ""  # 02 keeps its label: a row of blanks, sampled
        if column == "france" and row == "total_sale_05":
            value.value = "5"  # a figure with no label: sampled
    cells, coverage = draw.cells_of([page], TYPES)
    rows = {draw.parts(c)[2] for c in cells["1939_1942"]}
    assert {"total_purchase_01", "total_purchase_02", "total_sale_05"} <= rows
    assert "total_purchase_05" not in rows
    assert len(rows) == len(TYPES[forward].layout.row_keys) - 1  # unlabelled rows with figures stay
    assert coverage["1940-02_p062"]["rows_left_empty"] == 1
    assert coverage["1940-02_p062"]["figure_cells_left_empty"] == len(money)
    family = draw.by_family(coverage)[forward]
    assert family["pages"] == 1 and family["rows_left_empty"] == 1 and family["rows_not_returned"] == 0


def test_the_draw_is_seeded_as_preregistered(records: Path) -> None:
    record = draw.draw(records)
    from archivist.pipeline import extract

    cells, _ = draw.cells_of(extract.load_predictions(records / "predictions.jsonl"), TYPES)
    first = [s["cell"] for s in record["sample"] if s["stratum"] == "1939_1942"]
    second = [s["cell"] for s in record["sample"] if s["stratum"] == "total_claims"]
    assert first == random.Random(4004).sample(cells["1939_1942"], 300)
    assert second == random.Random(4004).sample(cells["total_claims"], 100)
    assert [s["order"] for s in record["sample"]] == list(range(1, 401))
    assert record["relabel"] == random.Random(4004).sample(sorted(first + second), 40)
    counted = sorted(p.page_id for p in extract.load_predictions(records / "predictions.jsonl"))
    assert [p["page"] for p in record["pages_checked"]] == random.Random(4004).sample(counted, 7)
    assert "1940-01_p099" not in {p["page"] for p in record["pages_checked"]}  # title rejected
    assert record["strata"]["total_claims"] == {"families": [CLAIMS], "cells": len(cells["total_claims"]), "sampled": 100}
    assert record["families"][RAILROAD] == {"classified": 3, "confirmed": 2, "deep_pages": 6}


def test_the_draw_keeps_no_figure_and_records_coverage(records: Path) -> None:
    record = draw.draw(records)
    text = json.dumps(record)
    assert '"value"' not in text and "verdict" not in text and "ocr" not in text
    assert record["coverage_by_page"]["1993-06_p097"]["rows_not_returned"] == 45
    assert record["coverage_by_family"][CLAIMS]["rows_not_returned"] == 45
    assert record["coverage_by_family"][RAILROAD]["pages"] == 6
    claims = next(s for s in record["sample"] if s["stratum"] == "total_claims")
    row = next(r for r in TYPES[CLAIMS].layout.rows if r.key == claims["row"])
    assert claims["row_label"] == row.printed
    assert claims["column_heading"] == TYPES[CLAIMS].layout.column(claims["column"]).printed


def _labelled(family: str, page_id: str, labels: dict[str, str]) -> PageExtraction:
    column = next(c.key for c in TYPES[family].layout.columns if c.kind == "text")
    page = _page(family, page_id)
    for value in page.values:
        _, _, row, col = draw.parts(value.field_id)
        if col == column:
            value.value = labels.get(row, "")
    return page


def test_read_rows_are_named_by_their_label_and_heading_as_read() -> None:
    family = "short_term_foreign_liabilities_as"
    read = {
        "10": "Sept. 27................",
        "11": "Deposits for foreign account:",
        "12": "Sept. 6................",
        "13": "  Sept. 13................  ",
        "14": "Sept. 20 . . . . .",
    }
    named = draw.names(TYPES[family], _labelled(family, "1940-01_p051", read))
    assert named["13"] == {
        "label": "Sept. 13",
        "heading": "Deposits for foreign account:",
        "hint": "row 13 from the top of the table",
    }
    assert named["14"]["label"] == "Sept. 20"
    assert named["11"]["heading"] == "" and named["10"]["heading"] == ""
    assert named["20"] == {"label": "", "heading": "Deposits for foreign account:", "hint": "row 20 from the top of the table"}


def test_section_and_fixed_rows_take_their_headings_from_the_template() -> None:
    forward = "outstanding_forward_exchange_contracts"
    named = draw.names(TYPES[forward], _labelled(forward, "1940-02_p062", {"total_sale_03": "Sept. 20....."}))
    assert named["total_sale_03"] == {
        "label": "Sept. 20",
        "heading": "TOTAL SALES CONTRACTS:",
        "hint": "row 3 under it",
    }
    fixed = draw.names(TYPES[CLAIMS], _page(CLAIMS, "1985-06_p058"))
    assert fixed["austria"] == {"label": "Austria", "heading": "Europe:", "hint": "row 2 of the template"}
    assert fixed["europe_hdr"]["heading"] == ""
    assert draw.printed(None) == "" and draw.printed("1938-Nov......") == "1938-Nov"
    assert draw.printed("Sept.") == "Sept."


def test_the_draw_is_made_once(records: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(real_test, "OUT_DIR", tmp_path)
    draw.main(["--side", "held_out"])
    with pytest.raises(SystemExit):
        draw.main(["--side", "held_out"])


@pytest.fixture
def labels(records: Path, tmp_path: Path, monkeypatch) -> serve.Labels:
    monkeypatch.setattr(real_test, "OUT_DIR", tmp_path)
    draw.main(["--side", "held_out"])
    return serve.Labels("held_out", records / "labels")


def test_the_page_is_never_sent_a_read(labels: serve.Labels) -> None:
    shown = labels.cells("first")
    assert len(shown["cells"]) == 400 and shown["answers"] == {}
    for cell in shown["cells"]:
        assert set(cell) == {
            "n", "cell", "page", "title", "unit", "row_label", "row_heading", "row_hint",
            "occurrence", "column", "box",
        }  # fmt: skip
    assert shown["cells"][0]["box"] == {"x0": 1.0, "y0": 2.0, "x1": 30.0, "y1": 12.0}


def _rows(*labels: str) -> dict[str, dict[str, str]]:
    return {f"{n:02d}": {"label": label, "heading": "", "hint": ""} for n, label in enumerate(labels, 1)}


def test_a_repeated_row_label_is_counted_in_the_draws_row_order_from_the_top() -> None:
    rows = _rows("Dec. 4", "Dec. 18", "Deposits:", "Dec. 4", "Dec. 18", "Dec. 18", "TOTAL", "Dec. 4")

    assert serve.counted(rows) == {
        "01": (1, 3), "04": (2, 3), "08": (3, 3),  # Dec. 4
        "02": (1, 3), "05": (2, 3), "06": (3, 3),  # Dec. 18
    }  # fmt: skip
    # a label that occurs once is not listed, and neither is a row the read gave no label
    assert "03" not in serve.counted(rows) and "07" not in serve.counted(rows)
    assert serve.counted(_rows("", "", "A", "")) == {}


def test_rows_without_a_label_are_not_counted_and_spaces_do_not_make_labels_differ() -> None:
    rows = _rows("Jan. 8", "", "Jan.  8", " Jan. 8 ", "")

    assert serve.counted(rows) == {"01": (1, 3), "03": (2, 3), "04": (3, 3)}
    assert serve.counted({}) == {}


def test_labels_differing_in_case_or_punctuation_are_different_labels() -> None:
    assert serve.counted(_rows("Total", "TOTAL", "Total:", "Total")) == {"01": (1, 2), "04": (2, 2)}


def test_each_cell_carries_which_occurrence_of_its_repeated_row_label_it_is(labels: serve.Labels) -> None:
    shown = labels.cells("first")["cells"]
    by_page: dict[str, list[dict]] = {}
    for cell in shown:
        by_page.setdefault(cell["page"], []).append(cell)

    for cells in by_page.values():
        for cell in cells:
            row = draw.parts(cell["cell"])[2]
            rows = labels.repeats[cell["page"]]
            assert (cell["occurrence"] is None) == (row not in rows)
            if cell["occurrence"]:
                n, of = rows[row]
                assert cell["occurrence"] == {"n": n, "of": of}
                assert 1 <= n <= of and cell["row_label"]
    # the fixture's pages read the label "1" in every row they returned, so those repeat
    railroad = next(c for c in shown if c["page"].endswith("_p026"))
    assert railroad["occurrence"]["of"] == len(TYPES[RAILROAD].layout.row_keys)
    assert railroad["occurrence"]["n"] == int(draw.parts(railroad["cell"])[2])
    # fixed rows take their labels from the template, which prints each country once
    claims = [c for c in shown if c["page"] == "1993-06_p097"]
    assert claims and all(c["occurrence"] is None for c in claims)


def test_answers_are_kept_as_given_and_the_last_stands(labels: serve.Labels) -> None:
    cell = labels.draw["sample"][0]["cell"]
    with pytest.raises(ValueError, match="typed as printed"):
        labels.answer({"pass": "first", "cell": cell, "choice": "value", "value": "  "})
    with pytest.raises(ValueError, match="not drawn"):
        labels.answer({"pass": "first", "cell": "T.x:y:01:z", "choice": "blank"})
    with pytest.raises(ValueError, match="choice"):
        labels.answer({"pass": "first", "cell": cell, "choice": "zero"})
    labels.answer({"pass": "first", "cell": cell, "choice": "value", "value": " 1,234 "})
    labels.answer({"pass": "first", "cell": cell, "choice": "blank"})
    labels.answer({"pass": "first", "cell": cell, "choice": "not_on_page", "value": "9"})
    labels.answer({"pass": "first", "cell": cell, "choice": "column_not_on_page"})
    lines = (labels.labels / "labels.jsonl").read_text().splitlines()
    assert [json.loads(line)["choice"] for line in lines] == [
        "value", "blank", "not_on_page", "column_not_on_page"
    ]
    assert json.loads(lines[0])["value"] == "1,234" and json.loads(lines[2])["value"] is None
    assert labels.cells("first")["answers"] == {cell: {"choice": "column_not_on_page", "value": None}}


def test_the_relabel_pass_opens_24_hours_after_the_last_first_label(
    labels: serve.Labels, monkeypatch
) -> None:
    start = datetime(2026, 11, 1, 9, tzinfo=UTC)
    monkeypatch.setattr(serve, "_now", lambda: start)
    assert "400 cells have no first label" in labels.cells("relabel")["blocked"]
    for sampled in labels.draw["sample"]:
        labels.answer({"pass": "first", "cell": sampled["cell"], "choice": "value", "value": "7"})
    assert "opens at 2026-11-02T09:00" in labels.cells("relabel")["blocked"]
    with pytest.raises(ValueError, match="not a pass open"):
        labels.answer({"pass": "relabel", "cell": labels.draw["relabel"][0], "choice": "blank"})
    monkeypatch.setattr(serve, "_now", lambda: start + timedelta(hours=24))
    shown = labels.cells("relabel")
    assert shown["blocked"] is None and shown["answers"] == {}  # never the first labels
    assert [c["cell"] for c in shown["cells"]] == labels.draw["relabel"]
    labels.answer({"pass": "relabel", "cell": labels.draw["relabel"][0], "choice": "cant_read"})
    assert (labels.labels / "relabels.jsonl").exists()


def test_the_page_check_takes_right_or_wrong_for_drawn_pages(labels: serve.Labels) -> None:
    pages = labels.checks()["pages"]
    assert [p["page"] for p in pages] == [p["page"] for p in labels.draw["pages_checked"]]
    assert pages[0]["title"] == TYPES[pages[0]["family"]].template.identity.title
    with pytest.raises(ValueError, match="verdict"):
        labels.check({"page": pages[0]["page"], "verdict": "maybe"})
    with pytest.raises(ValueError, match="not drawn"):
        labels.check({"page": "1940-01_p099", "verdict": "wrong"})
    labels.check({"page": pages[0]["page"], "verdict": "wrong"})
    assert labels.checks()["answers"] == {pages[0]["page"]: {"verdict": "wrong"}}


def test_only_drawn_pages_are_served(labels: serve.Labels) -> None:
    with pytest.raises(ValueError, match="not drawn"):
        labels.image("1940-01_p099")


def _record(path: Path) -> Path:
    pages = [
        {"page": "1940-01_p051", "family": "short_term_foreign_liabilities_as", "ocr": "cannot be checked: 17 words", "check_by_eye": True},
        {"page": "1940-04_p055", "family": "short_term_foreign_liabilities_as", "ocr": "changed", "check_by_eye": False},
        {"page": "1985-06_p058", "family": CLAIMS, "ocr": "cannot be checked: 19 words", "check_by_eye": True},
    ]
    path.write_text(json.dumps({"pages": pages}))
    return path


def test_the_layout_check_needs_no_draw_and_shows_only_pages_left_to_the_eye(tmp_path: Path) -> None:
    layouts = serve.Layouts("held_out", tmp_path / "labels", _record(tmp_path / "layout_check.json"))
    shown = layouts.state()
    assert [p["page"] for p in shown["pages"]] == ["1940-01_p051", "1985-06_p058"]
    claims = shown["pages"][1]
    assert claims["columns"] == [c.printed for c in TYPES[CLAIMS].layout.columns]
    assert claims["title"] == TYPES[CLAIMS].template.identity.title
    assert claims["ocr"] == "cannot be checked: 19 words" and shown["answers"] == {}
    with pytest.raises(ValueError, match="not a page to check"):
        layouts.image("1940-04_p055")


def test_a_layout_is_marked_same_changed_or_different_with_a_note(tmp_path: Path) -> None:
    layouts = serve.Layouts("held_out", tmp_path / "labels", _record(tmp_path / "layout_check.json"))
    with pytest.raises(ValueError, match="layout must be"):
        layouts.mark({"page": "1940-01_p051", "layout": "maybe"})
    with pytest.raises(ValueError, match="not a page to check"):
        layouts.mark({"page": "1940-04_p055", "layout": "same"})
    with pytest.raises(ValueError, match="at most 2,000"):
        layouts.mark({"page": "1940-01_p051", "layout": "same", "note": "x" * 2001})
    layouts.mark({"page": "1940-01_p051", "layout": "changed", "note": " Grand total first "})
    layouts.mark({"page": "1985-06_p058", "layout": "same"})
    assert layouts.state()["answers"] == {
        "1940-01_p051": {"layout": "changed", "note": "Grand total first"},
        "1985-06_p058": {"layout": "same", "note": ""},
    }
    assert (tmp_path / "labels" / "layouts_checked.jsonl").read_text().count("\n") == 2
