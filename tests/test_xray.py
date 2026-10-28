"""Page X-rays: outcomes, drawing and replay, with hand-made reads. No model is called."""

import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image

from archivist.doctypes.template import TemplateType, cell_id, load_templates
from archivist.models import BudgetExceeded, describe_config
from archivist.models.budget import BACKEND_CAPS
from archivist.schema import BBox, Citation, ExtractedValue, PageExtraction, VerdictRecord
from archivist.templates import grid, ocr, test, xray
from archivist.templates.draft import CONFIG
from archivist.templates.pages import Page

REPO = Path(__file__).resolve().parents[1]
FAMILY = "tiny"
PAGE = "1939-01_p001"

TINY = """\
identity:
  family: tiny
  title: Tiny Table
  description: A small table of two items and their total for two months.
  title_patterns: ['tiny\\s+table']
layout:
  unit: millions of dollars
  precision: "1"
  rows:
    - {key: a, printed: Item A}
    - {key: b, printed: Item B}
    - {key: total, printed: Total}
  columns:
    - {key: july, printed: July, kind: money}
    - {key: august, printed: August, kind: money}
    - {key: both, printed: Two months, kind: money}
identities:
  - id: total_is_sum
    description: the total is the sum of the items
    for_each: column
    left: {cell: {row: total}}
    right: {sum: {rows: [a, b]}}
  - id: both_months
    description: the two months add up
    for_each: row
    left: {cell: {column: both}}
    right: {sum: {columns: [july, august]}}
provenance:
  status: approved
  drafted_by: {kind: model, id: muse-spark-1.3}
  drafted_on: 2026-10-20
  approved_by: a reviewer
  approved_on: 2026-10-21
  evidence: [three development pages]
"""

PRINTED = {"a": (1, 2, 3), "b": (4, 5, 9), "total": (5, 7, 12)}
COLUMNS = ("july", "august", "both")


@pytest.fixture
def folder(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "templates"
    folder.mkdir()
    (folder / "tiny.yaml").write_text(TINY, encoding="utf-8")
    monkeypatch.setattr(xray, "TEMPLATES_DIR", folder)
    return folder


@pytest.fixture
def doc_type(folder) -> TemplateType:
    return load_templates(folder)[0]


def box(row: int, column: int) -> BBox:
    return BBox(x0=60 + column * 100, y0=40 + row * 40, x1=140 + column * 100, y1=70 + row * 40)


def extraction(doc_type: TemplateType, changes: dict[tuple[str, str], str] | None = None) -> PageExtraction:
    changes = changes or {}
    values = []
    for r, row in enumerate(PRINTED):
        for c, column in enumerate(COLUMNS):
            text = changes.get((row, column), str(PRINTED[row][c]))
            field = cell_id(FAMILY, PAGE, row, column)
            citation = Citation(page_id=PAGE, bbox=box(r, c))
            values.append(ExtractedValue(field_id=field, value=text, citation=citation))
    return PageExtraction(page_id=PAGE, doc_type=FAMILY, values=values)


def field(row: str, column: str) -> str:
    return cell_id(FAMILY, PAGE, row, column)


def second(page: PageExtraction, changes=None, leave_out=()) -> dict[str, test.Reading]:
    changes = changes or {}
    return {
        v.field_id: test.Reading(changes.get(v.field_id, v.value))
        for v in page.values
        if v.field_id not in leave_out
    }


# --- outcomes ---------------------------------------------------------------------------------


def test_every_cell_of_a_table_that_adds_up_and_reads_twice_passes(doc_type):
    page = extraction(doc_type)
    states = xray.cell_states(doc_type, page, second(page))
    assert set(states.values()) == {(xray.AGREE, xray.PASSED)}
    assert len(states) == 9


def test_a_misread_total_fails_every_cell_of_the_rules_that_cover_it(doc_type):
    # three printed values allow 1.5 units of rounding, so a total only one out would still hold
    page = extraction(doc_type, {("total", "both"): "30"})
    states = xray.cell_states(doc_type, page, second(page))
    assert states[field("total", "both")] == (xray.AGREE, xray.FAILED)
    assert states[field("a", "both")] == (xray.AGREE, xray.FAILED)  # in the column's sum
    assert states[field("total", "july")] == (xray.AGREE, xray.FAILED)  # in the row's sum
    assert states[field("a", "july")] == (xray.AGREE, xray.PASSED)  # only in places that hold


def test_a_total_one_out_is_within_the_rounding_the_arithmetic_test_allows(doc_type):
    page = extraction(doc_type, {("total", "both"): "13"})
    states = xray.cell_states(doc_type, page, second(page))
    assert set(states.values()) == {(xray.AGREE, xray.PASSED)}


def test_a_cell_whose_second_read_differs_is_marked_and_the_rest_keep_their_other_places(doc_type):
    page = extraction(doc_type)
    states = xray.cell_states(doc_type, page, second(page, {field("a", "july"): "9"}))
    assert states[field("a", "july")] == (xray.DISAGREE, xray.NOT_EVALUATED)
    assert states[field("b", "july")] == (xray.AGREE, xray.PASSED)  # its row still holds
    assert states[field("a", "august")] == (xray.AGREE, xray.PASSED)  # its column still holds
    assert states[field("total", "july")] == (xray.AGREE, xray.PASSED)  # its row still holds


def test_a_cell_never_read_twice_is_not_re_read_and_only_spoils_the_places_it_is_in(doc_type):
    page = extraction(doc_type)
    states = xray.cell_states(doc_type, page, second(page, leave_out={field("b", "both")}))
    assert states[field("b", "both")] == (xray.NOT_REREAD, xray.NOT_EVALUATED)
    assert states[field("a", "both")] == (xray.AGREE, xray.PASSED)  # its row a holds
    assert states[field("a", "july")] == (xray.AGREE, xray.PASSED)


def test_a_cell_in_no_place_that_could_be_evaluated_agrees_but_is_not_evaluated(doc_type):
    page = extraction(doc_type)
    # a.july disagrees (column july and row a are out) and b.both was not re-read (column both and row b)
    states = xray.cell_states(
        doc_type, page, second(page, {field("a", "july"): "9"}, leave_out={field("b", "both")})
    )
    assert states[field("a", "both")] == (xray.AGREE, xray.NOT_EVALUATED)  # column both, row a
    assert states[field("b", "july")] == (xray.AGREE, xray.NOT_EVALUATED)  # column july, row b
    assert states[field("total", "july")] == (xray.AGREE, xray.PASSED)  # row total is intact


def test_an_illegible_second_read_is_not_a_read(doc_type):
    page = extraction(doc_type)
    reads = second(page)
    reads[field("a", "july")] = test.Reading(None, "illegible to the re-read")
    assert xray.cell_states(doc_type, page, reads)[field("a", "july")][0] == xray.NOT_REREAD


def test_the_difference_between_two_page_records_is_only_what_changed():
    old = {"ref": "x", "agree": 188, "cells": 420}
    assert xray.record_diff(old, dict(old)) == {}
    assert xray.record_diff(old, {**old, "agree": 199}) == {"agree": [188, 199]}
    assert xray.record_diff(old, {**old, "box_sources": {"ocr": 3}}) == {"box_sources": [None, {"ocr": 3}]}


# --- boxes by strategy ------------------------------------------------------------------------


def test_every_box_is_the_models_when_the_strategy_has_no_better_one(doc_type):
    page = extraction(doc_type)
    boxed, sources = xray.box_sources(page.values, doc_type, b"", (), "S0", None)
    assert boxed == page.values and set(sources.values()) == {"model"}


def test_a_figure_found_in_the_ocr_layer_takes_its_box_and_says_so(doc_type):
    page = extraction(doc_type)
    word = ocr.Word("12", BBox(x0=300, y0=140, x1=330, y1=160))
    boxed, sources = xray.box_sources(page.values, doc_type, b"", (word,), ocr.STRATEGY, None)
    mine = field("total", "both")
    assert sources[mine] == "ocr" and {s for f, s in sources.items() if f != mine} == {"model"}
    assert next(v for v in boxed if v.field_id == mine).citation.bbox == word.box


# --- drawing ----------------------------------------------------------------------------------


def blend(colour, alpha, over=(255, 255, 255)):
    return tuple(round(c * alpha / 255 + o * (1 - alpha / 255)) for c, o in zip(colour, over, strict=True))


def made(cells, *, g=None, occluders=(), size=(400, 300), facts=None) -> tuple[Image.Image, int]:
    x = xray.XRay(
        stem="s",
        title="a title",
        notes=["a note"],
        image=Image.new("RGB", size, (255, 255, 255)),
        cells=cells,
        blanks=1,
        grid=g,
        occluders=list(occluders),
        facts=facts or {},
    )
    out = xray.draw(x)
    return out, out.height - size[1]


def at(out: Image.Image, header: int, x: int, y: int) -> tuple[int, int, int]:
    return out.getpixel(((out.width - 400) // 2 + x, header + y))


def cell(source="ocr", reads=xray.AGREE, rule=xray.NOT_EVALUATED, b=(100, 100, 200, 140)) -> xray.Cell:
    return xray.Cell("f", BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]), "5", source, reads, rule)


@pytest.mark.parametrize(
    "source, colour", [("ocr", xray.BLUE), ("grid", xray.PURPLE), ("ink", xray.SKY), ("model", xray.BLACK)]
)
def test_a_boxs_outline_is_the_colour_of_its_source(source, colour):
    out, header = made([cell(source)])
    assert at(out, header, 100, 120) == colour  # the left edge, left of the mark
    if source != "model":  # a dashed outline has gaps
        assert at(out, header, 150, 100) == colour


@pytest.mark.parametrize(
    "state, colour, alpha",
    [
        (dict(rule=xray.PASSED), xray.GREEN, xray.FILL_ALPHA),
        (dict(rule=xray.FAILED), xray.VERMILION, xray.FILL_ALPHA),
        (dict(reads=xray.DISAGREE), xray.YELLOW, xray.FILL_ALPHA),
    ],
)
def test_a_cells_fill_is_its_outcome(state, colour, alpha):
    out, header = made([cell(**state)])
    assert at(out, header, 190, 130) == blend(colour, alpha)


def test_a_cell_with_no_outcome_is_left_unfilled_and_a_disagreement_outranks_a_failure():
    out, header = made([cell(reads=xray.NOT_REREAD)])
    assert at(out, header, 190, 130) == (255, 255, 255)
    out, header = made([cell(reads=xray.DISAGREE, rule=xray.FAILED)])
    assert at(out, header, 190, 130) == blend(xray.YELLOW, xray.FILL_ALPHA)


def test_each_outcome_has_its_own_mark_inside_the_box():
    def marked(**state) -> int:
        out, header = made([cell(**state)])
        return sum(
            at(out, header, x, y) == (0, 0, 0) for x in range(103, 121) for y in range(104, 136)
        )

    none = marked(reads=xray.NOT_REREAD)
    assert none == 0
    assert all(marked(**s) > 0 for s in (dict(rule=xray.PASSED), dict(rule=xray.FAILED), dict(reads=xray.DISAGREE), dict()))


def test_the_grid_is_drawn_as_column_stripes_and_band_edges_skewed_with_the_page():
    g = grid.Grid(columns={"july": (50, 150), "august": (200, 300)}, bands=[(40, 80), (90, 130)], shear=0.0, centre=200)
    out, header = made([], g=g)
    assert at(out, header, 100, 60) == blend(xray.SKY, xray.COLUMN_ALPHA)  # inside a column
    assert at(out, header, 175, 60) == (255, 255, 255)  # between the columns
    assert at(out, header, 100, 80) != blend(xray.SKY, xray.COLUMN_ALPHA)  # a band edge crosses it
    skewed = grid.Grid(columns={"july": (50, 150)}, bands=[(40, 80)], shear=0.1, centre=100)
    out, header = made([], g=skewed)
    # the right end of the top edge is lower than the left end by shear x width
    assert at(out, header, 51, 44) != (255, 255, 255) and at(out, header, 149, 54) != (255, 255, 255)


def test_an_occluder_is_an_orange_hatched_box_with_its_label():
    occluder = xray.Occluder("stamp", BBox(x0=200, y0=100, x1=300, y1=180), "covers 29% of a field")
    out, header = made([], occluders=[occluder])
    assert at(out, header, 200, 140) == xray.ORANGE and at(out, header, 300 - 1, 140) == xray.ORANGE
    assert at(out, header, 250, 100 - 1) == (255, 255, 255)  # nothing outside the box
    out2, _ = made([])
    assert out != out2


def test_the_model_boxes_the_ink_fit_moved_are_drawn_thin_and_grey():
    raw = BBox(x0=100, y0=150, x1=200, y1=170)
    out, header = made([], facts={"raw_boxes": [raw.model_dump()]})
    assert at(out, header, 100, 160)[0] > 100 and at(out, header, 100, 160) != (255, 255, 255)


def test_the_legend_sits_above_the_page_names_each_source_and_lists_the_overlays():
    cells = [cell("ocr"), cell("model", b=(100, 200, 200, 240))]
    out, header = made(cells, g=grid.Grid({"a": (50, 150)}, [(40, 80)], 0.0, 200))
    assert header > 150 and out.width >= 1100
    legend = xray._legend_rows(
        xray.XRay("s", "t", [], Image.new("RGB", (4, 4)), cells, 0, grid.Grid({"a": (1, 2)}, [(1, 2)], 0, 0))
    )
    words = [text for row in legend for _, text in row]
    assert "OCR anchor" in words and "model fallback" in words and "grid" not in words  # no grid cell here
    assert "grid column" in words and any(w.startswith("SAM occluder (0") for w in words)
    plain = xray._legend_rows(xray.XRay("s", "t", [], Image.new("RGB", (4, 4)), cells, 0))
    assert "grid column" not in [text for row in plain for _, text in row]
    assert any(out.getpixel((x, y)) != (255, 255, 255) for x in range(0, 600) for y in range(0, header - 5))


def test_a_long_note_is_wrapped_to_the_width_of_the_page():
    font = xray._font(18)
    lines = xray._wrap("word " * 120, font, 500)
    assert len(lines) > 3 and all(len(line) > 0 for line in lines)
    assert " ".join(lines).split() == ["word"] * 120


# --- replaying a family -----------------------------------------------------------------------


def evidence(folder: Path, record: dict, citations="S0+ocr", config=None) -> None:
    (folder / "tiny.evidence.json").write_text(
        json.dumps(
            {
                "family": FAMILY,
                "config": describe_config(CONFIG) if config is None else config,
                "citations": citations,
                "pages": [record],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def page_file(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "page.jpg"
    Image.new("RGB", (500, 400), (250, 250, 250)).save(path)
    monkeypatch.setattr(xray, "resolve", lambda ref: Page(ref, ref, path))
    return path


def test_a_family_whose_read_is_not_cached_is_skipped_and_says_why(folder, doc_type, page_file, monkeypatch):
    evidence(folder, {"ref": PAGE})

    def miss(*args, **kwargs):
        raise BudgetExceeded("meta cap $0.00: $4.3029 spent")

    monkeypatch.setattr(test, "read_pages", miss)
    with pytest.raises(xray.Skipped) as error:
        xray.replay_family(doc_type, {}, None)
    assert "not in the cache" in str(error.value) and "nothing was called" in str(error.value)
    assert "$" not in str(error.value) and "cap $" not in str(error.value)


def test_a_family_tested_under_another_config_is_skipped(folder, doc_type, page_file):
    evidence(folder, {"ref": PAGE}, config={"extractor": {"model_id": "something else"}})
    with pytest.raises(xray.Skipped, match="another config"):
        xray.replay_family(doc_type, {}, None)


def test_a_page_that_may_not_be_read_is_skipped_before_anything_else(folder, doc_type, monkeypatch):
    evidence(folder, {"ref": PAGE})

    def refuse(ref):
        from archivist.templates.pages import PageRefused

        raise PageRefused(f"{ref}: not a development page")

    monkeypatch.setattr(xray, "resolve", refuse)
    with pytest.raises(xray.Skipped, match="not a development page"):
        xray.replay_family(doc_type, {}, None)


def replayed(doc_type, monkeypatch, page_file, citations="S0+ocr", changes=None, boxes_move=False):
    """A family replayed from fakes standing in for the cache: the test's own read_pages and the
    first read, which the replay asks again."""
    page = extraction(doc_type, changes)
    reads = second(page)
    record = {"ref": PAGE, "read": "ok", "agree": 9}
    first = [v.model_copy(update={"citation": v.citation.model_copy(update={"bbox": box(0, 0)})}) for v in page.values] if boxes_move else list(page.values)
    monkeypatch.setattr(test, "read_pages", lambda *a, **k: ([page], {PAGE: reads}, [dict(record)]))
    monkeypatch.setattr(xray.extract, "read_page", lambda *a, **k: first)
    monkeypatch.setattr(ocr, "words", lambda ref: ())
    monkeypatch.setattr(test, "blind_check", lambda *a, **k: None)
    monkeypatch.setattr(xray, "page_grid", lambda *a, **k: None)
    return page, record


def test_a_replayed_family_gives_every_drawn_cell_its_source_and_outcome(folder, doc_type, page_file, monkeypatch):
    page, record = replayed(doc_type, monkeypatch, page_file, changes={("total", "both"): "30"})
    evidence(folder, record)
    roles = {xray.extract.ROLE: object(), xray.reread.ROLE: object()}
    x = xray.replay_family(doc_type, roles, None)
    assert (x.stem, x.blanks, len(x.cells)) == (PAGE, 0, 9)
    assert {c.source for c in x.cells} == {"model"}  # an empty OCR layer anchors nothing
    failed = [c.field_id for c in x.cells if c.rule == xray.FAILED]
    assert field("total", "both") in failed and field("a", "july") not in failed
    assert x.facts["record_diff"] == {} and x.facts["grid_used"] is False


def test_the_replay_is_refused_when_its_boxes_are_not_the_ones_the_test_made(folder, doc_type, page_file, monkeypatch):
    _, record = replayed(doc_type, monkeypatch, page_file, boxes_move=True)
    evidence(folder, record)
    roles = {xray.extract.ROLE: object(), xray.reread.ROLE: object()}
    with pytest.raises(xray.Skipped, match="not the same read"):
        xray.replay_family(doc_type, roles, None)


def test_a_blank_cell_is_counted_and_not_drawn(folder, doc_type, page_file, monkeypatch):
    replayed(doc_type, monkeypatch, page_file, changes={("a", "july"): ""})
    evidence(folder, {"ref": PAGE, "read": "ok", "agree": 9})
    roles = {xray.extract.ROLE: object(), xray.reread.ROLE: object()}
    x = xray.replay_family(doc_type, roles, None)
    assert (x.blanks, len(x.cells)) == (1, 8)


# --- the segmenter ----------------------------------------------------------------------------


def test_occluders_are_whatever_the_cache_holds_and_none_when_it_holds_none(monkeypatch):
    assert xray.recorded_occluders(b"", None) == []

    def miss(image, segmenter):
        raise BudgetExceeded("miss")

    monkeypatch.setattr(xray.occlusion, "detect", miss)
    assert xray.recorded_occluders(b"", object()) == []
    region = type("Region", (), {"label": "stamp", "bbox": BBox(x0=1, y0=2, x1=3, y1=4), "score": 0.91})()
    monkeypatch.setattr(xray.occlusion, "detect", lambda image, segmenter: [region])
    assert xray.recorded_occluders(b"", object()) == [xray.Occluder("stamp", region.bbox, "score 0.91")]


def test_no_spend_sets_every_backends_cap_to_zero(monkeypatch):
    for variable, _ in BACKEND_CAPS.values():
        monkeypatch.setenv(variable, "50")
    xray.no_spend()
    assert {os.environ[v] for v, _ in BACKEND_CAPS.values()} == {"0"}


# --- the ledger card --------------------------------------------------------------------------


def record(page, n, *, value="1.00", status="agrees", flags=(), balances=False, occluded=False, raw=None, bbox=(10, 10, 60, 30)):
    b = dict(zip(("x0", "y0", "x1", "y1"), bbox))
    return VerdictRecord.model_validate(
        {
            "field_id": f"L:{page}:{n:02d}:debit",
            "value": value,
            "confidence": 0.99,
            "status": "accepted",
            "flags": [{"field_id": f"L:{page}:{n:02d}:debit", "check": c, "detail": "d"} for c in flags],
            "page_id": page,
            "doc_type": "ledger_card",
            "evidence": {
                "route": "arithmetic",
                "citation": {"page_id": page, "bbox": b, "raw_bbox": raw},
                "occluded_by": [{"label": "stamp", "bbox": {"x0": 5, "y0": 5, "x1": 90, "y1": 50}, "cover": 0.4}] if occluded else [],
                "reread": value,
                "reread_status": status,
                "reread_balances": balances,
            },
        }
    )


def test_the_card_is_the_first_with_an_occluded_field_a_failed_check_and_a_balanced_reread():
    records = [
        record("card-01-1", 1, occluded=True),  # an occluder only
        record("card-02-1", 1, flags=["arithmetic"], balances=True),  # no occluder
        record("card-03-1", 1, occluded=True),
        record("card-03-1", 2, flags=["arithmetic"]),
        record("card-03-1", 3, balances=True),  # all three
        record("card-04-1", 1, occluded=True, flags=["crossdoc"], balances=True),
    ]
    assert xray.choose_card(records) == "card-03-1"


def test_failing_that_the_first_card_with_an_occluder_then_the_first_card():
    records = [record("card-01-1", 1), record("card-02-1", 1, occluded=True), record("card-03-1", 1, occluded=True)]
    assert xray.choose_card(records) == "card-02-1"
    assert xray.choose_card([record("card-01-1", 1), record("card-02-1", 1)]) == "card-01-1"
    assert xray.choose_card([]) is None


def test_a_reread_or_occlusion_note_is_not_a_failed_check():
    assert xray.failed_check(record("c", 1, flags=["arithmetic"]))
    assert xray.failed_check(record("c", 1, flags=["words_figures"]))
    assert not xray.failed_check(record("c", 1, flags=["reread", "occlusion"]))


def test_card_cells_take_the_runs_own_record_of_boxes_reads_checks_and_occluders():
    moved = record("c", 1, raw={"x0": 8, "y0": 20, "x1": 60, "y1": 44}, status="disagrees", flags=["arithmetic"])
    kept = record("c", 2, balances=True, raw={"x0": 10, "y0": 10, "x1": 60, "y1": 30})
    blank = record("c", 3, value="")
    illegible = record("c", 4, status="illegible", occluded=True)
    cells, blanks, occluders, raws = xray.card_cells([moved, kept, blank, illegible])
    by = {c.field_id: c for c in cells}
    assert blanks == 1 and len(cells) == 3
    one, two, four = (by[f"L:c:{n:02d}:debit"] for n in (1, 2, 4))
    assert (one.source, one.reads, one.rule) == ("ink", xray.DISAGREE, xray.FAILED)
    assert (two.source, two.reads, two.rule) == ("kept", xray.AGREE, xray.PASSED)
    assert (four.reads, four.rule) == (xray.NOT_REREAD, xray.NOT_EVALUATED)
    assert [(o.label, o.detail) for o in occluders] == [("stamp", "covers 40% of a field")]
    assert raws == [BBox(x0=8, y0=20, x1=60, y1=44)]


def test_the_card_xray_reads_the_run_and_its_image(tmp_path):
    run = tmp_path / "test-run"
    run.mkdir()
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (120, 80), (240, 240, 240)).save(images / "card-01-1.jpg")
    rows = [record("card-01-1", 1, occluded=True, flags=["arithmetic"], balances=True), record("card-01-1", 2)]
    (run / "verdicts.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    (run / "run.json").write_text(
        json.dumps({"run_id": "test-run", "images": str(images), "citations": "S0+ink"}), encoding="utf-8"
    )
    x = xray.card_xray(run)
    assert x.stem == "test-run_card-01-1" and x.facts["marks"] == [True, True, True]
    assert len(x.cells) == 2 and len(x.occluders) == 1 and x.image.size == (120, 80)
    assert xray.draw(x).height > 80


# --- the README and the committed images ------------------------------------------------------


def test_the_readme_names_every_image_what_it_shows_and_every_skipped_family():
    x = xray.XRay("p", "t", [], Image.new("RGB", (4, 4)), [cell()], 0, facts={
        "family": "fam", "page": "p", "citations": "S0+ocr", "grid_used": False, "record_diff": {"agree": [188, 199]},
        "grid_columns": 3, "grid_bands": 5, "occluders_in_cache": 0,
    })
    card = xray.XRay("c", "t", [], Image.new("RGB", (4, 4)), [cell()], 0, facts={
        "page": "card-02-2", "run": "test-run", "citations": "S0+ink", "moved": 3, "marks": [True, True, True],
    })
    text = xray.readme([x, card], {"other_family": "a read is not in the cache"})
    for part in ("`p.png`", "`c.png`", "fam", "188 then, 199 now", "recount.md", "No SAM occluder is recorded",
                 "card-02-2", "## Skipped", "`other_family`: a read is not in the cache"):
        assert part in text
    assert "/Users/" not in text


def test_a_replay_that_is_the_committed_record_says_so():
    assert "count for count" in xray.diff_sentence({})
    assert "recount.md" not in xray.diff_sentence({"cells": [1, 2]})


XRAY_DIR = REPO / "results" / "templates" / "xray"


def test_the_committed_xrays_are_listed_drawn_and_hold_nothing_private():
    if not (XRAY_DIR / "README.md").exists():
        pytest.skip("not made yet")
    readme = (XRAY_DIR / "README.md").read_text(encoding="utf-8")
    images = sorted(XRAY_DIR.glob("*.png"))
    assert images
    for path in images:
        assert f"`{path.name}`" in readme  # every image is described
        with Image.open(path) as picture:
            assert picture.width >= 1100 and picture.height > 1000
            rgb = picture.convert("RGB")
            header = [rgb.getpixel((x, y)) for x in range(0, 400) for y in range(10, 40)]
            assert any(px != (255, 255, 255) for px in header)  # the title and legend are in the image
    for private in ("/Users/", "/private/", "@"):
        assert private not in readme


def test_every_approved_family_is_drawn_or_skipped_with_a_reason_and_the_card_is_drawn():
    if not (XRAY_DIR / "README.md").exists():
        pytest.skip("not made yet")
    readme = (XRAY_DIR / "README.md").read_text(encoding="utf-8")
    for doc_type in load_templates(REPO / "templates"):
        drawn = f"A page of the approved template `{doc_type.name}`" in readme
        skipped = f"- `{doc_type.name}`: " in readme
        assert drawn != skipped, doc_type.name  # one or the other, never both, never neither
    assert "test-archivist-A_" in readme
