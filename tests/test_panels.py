"""Tables printed in panels (P21d): the template language, the panelled type, panel finding and the
arithmetic test panel by panel.

No model is called: the extractor and the re-reader are MockLLM, SAM is MockSegmenter. Every file
is written under tmp_path.
"""

import io
import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw
from pydantic import ValidationError

from archivist.doctypes import template as template_module
from archivist.doctypes.template import (
    PanelledType,
    Template,
    TemplateError,
    TemplateType,
    load_templates,
    read_template,
)
from archivist.models import Region
from archivist.models.mock import MockLLM, MockSegmenter
from archivist.schema import BBox, PageExtraction
from archivist.templates import approve, draft, ocr, panels
from archivist.templates import test as arithmetic
from archivist.templates.pages import Page, PageRefused

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "receipts_in_panels"
REFS = ["1939-01_p010", "1939-02_p012"]
TODAY = date(2026, 10, 29)


def _layout(rows=("a", "b", "total")) -> dict:
    return {
        "unit": "millions of dollars",
        "precision": "1",
        "rows": [{"key": r, "printed": r.title()} for r in rows],
        "columns": [
            {"key": "item", "printed": "Item", "kind": "text"},
            {"key": "amount", "printed": "Amount", "kind": "money"},
        ],
    }


TOTAL = {
    "id": "total",
    "description": "the total is the sum of the items",
    "for_each": "column",
    "left": {"cell": {"row": "total"}},
    "right": {"sum": {"rows": ["a", "b"]}},
}


def _data(**changes) -> dict:
    data = {
        "identity": {
            "family": FAMILY,
            "title": "Receipts",
            "description": "Receipts, printed in an upper and a lower panel.",
            "title_patterns": ["receipts"],
        },
        "panels": [
            {"key": "upper", "title": "Upper", "layout": _layout(), "identities": [TOTAL]},
            {"key": "state", "title": "A State", "repeats": 2, "layout": _layout()},
        ],
        "provenance": {
            "status": "draft",
            "drafted_by": {"kind": "person", "id": "a test"},
            "drafted_on": "2026-10-29",
        },
    }
    data.update(changes)
    return data


# --- The template language ------------------------------------------------------------------------


def test_a_table_printed_in_panels_names_each_copy_of_each_panel():
    template = Template.model_validate(_data())
    assert template.layout is None and template.identities == []
    assert [c for p in template.panels for c in p.copies] == ["upper", "state_1", "state_2"]


@pytest.mark.parametrize(
    "change, error",
    [
        ({"layout": _layout()}, "a layout, or panels, not both"),
        ({"identities": [TOTAL]}, "keeps its identities in its panels"),
        ({"panels": []}, "at least one panel"),
    ],
)
def test_a_table_printed_in_panels_has_panels_alone(change, error):
    with pytest.raises(ValidationError, match=error):
        Template.model_validate(_data(**change))


def test_a_panels_identity_names_only_its_own_cells():
    other = {**TOTAL, "right": {"sum": {"table": "elsewhere", "rows": ["a", "b"]}}}
    data = _data()
    data["panels"][0]["identities"] = [other]
    with pytest.raises(ValidationError, match="names only its own cells"):
        Template.model_validate(data)
    data["panels"][0]["identities"] = [{**TOTAL, "left": {"cell": {"row": "nowhere"}}}]
    with pytest.raises(ValidationError, match="panel 'upper'"):
        Template.model_validate(data)


def test_a_copy_of_a_panel_can_not_take_another_panels_key():
    data = _data()
    data["panels"][0]["key"] = "state_1"
    with pytest.raises(ValidationError, match="panel keys repeat"):
        Template.model_validate(data)


def test_every_committed_template_is_one_table_and_reads_as_before():
    for path in sorted((ROOT / "templates").glob("*.yaml")):
        template = read_template(path)
        if template.panels is None:
            doc_type = TemplateType(template)
            assert doc_type.panel is None and doc_type.rule_name == template.family
            assert doc_type.extraction_prompt().startswith("This is a scanned page with the table")


# --- The panelled type ----------------------------------------------------------------------------


def _panelled(**changes) -> PanelledType:
    return PanelledType(Template.model_validate(_data(**changes)))


def test_a_panelled_types_cells_lead_each_row_with_the_copy():
    doc_type = _panelled()
    ids = doc_type.field_ids("1939-01_p010")
    assert ids[0] == f"T.{FAMILY}:1939-01_p010:upper.a:item"
    assert f"T.{FAMILY}:1939-01_p010:state_2.total:amount" in ids
    assert len(ids) == 3 * 3 * 2
    assert doc_type.money_fields == {"amount"}
    assert doc_type.part(ids[-1]) is doc_type.parts["state_2"]


def _page(values: dict[str, dict[str, str]], page_id="1939-01_p010") -> PageExtraction:
    """A page whose copies print these amounts (row -> amount), labels as the row key."""
    doc_type = _panelled()
    found = []
    for field_id in doc_type.field_ids(page_id):
        row, column = field_id.split(":")[2:]
        copy, key = row.split(".")
        text = key if column == "item" else values.get(copy, {}).get(key, "")
        found.append({"field_id": field_id, "value": text, "citation": None})
    return PageExtraction(page_id=page_id, doc_type=FAMILY, values=found)


def test_each_copys_identities_are_checked_on_its_own_cells():
    doc_type = _panelled(
        panels=[
            {"key": "upper", "title": "Upper", "layout": _layout(), "identities": [TOTAL]},
            {"key": "state", "title": "A State", "repeats": 2, "layout": _layout(),
             "identities": [TOTAL]},
        ]
    )
    page = _page(
        {
            "upper": {"a": "1", "b": "2", "total": "3"},
            "state_1": {"a": "4", "b": "5", "total": "9"},
            "state_2": {"a": "1", "b": "1", "total": "5"},
        }
    )
    flags = doc_type.checks([page])
    assert {f.field_id.split(":")[2].split(".")[0] for f in flags} == {"state_2"}
    opening = f"identity {FAMILY}.state_2.total on column amount"
    assert all(f.detail.startswith(opening) for f in flags)
    assert doc_type.rule(flags[0]) == f"{FAMILY}.state_2.total"
    assert set(doc_type.equation(flags[0], [page])) == {f.field_id for f in flags}
    labels = {doc_type.label(i) for i in doc_type.instances([page])}
    assert labels == {"upper.total", "state.total"}
    assert len(doc_type.balanced([page])) == 6


def test_the_pipeline_reads_every_panel_of_the_page_at_once():
    doc_type = _panelled()
    prompt = doc_type.extraction_prompt()
    assert '"upper": the panel "Upper"' in prompt
    assert '"state_2": the panel "A State" (millions of dollars), the second such panel' in prompt
    rows = {"a": {}, "b": {}, "total": {}}
    cell = {"value": "1", "box": [0, 0, 10, 10]}
    answer = {
        "panels": {
            c: {"rows": {r: {"item": cell, "amount": cell} for r in rows}}
            for c in ("upper", "state_1", "state_2")
        }
    }
    values = doc_type.parse("p", answer, 100, 100)
    assert [v.field_id for v in values] == doc_type.field_ids("p")
    assert set(doc_type.extraction_schema()["properties"]["panels"]["required"]) == set(
        doc_type.copies
    )


def test_a_panelled_template_loads_as_a_panelled_type_and_cannot_be_named_by_another(tmp_path):
    approved = {
        "status": "approved",
        "drafted_by": {"kind": "person", "id": "a test"},
        "drafted_on": "2026-10-29",
        "approved_by": "a test",
        "approved_on": "2026-10-29",
        "evidence": ["a note"],
    }
    (tmp_path / f"{FAMILY}.yaml").write_text(yaml.safe_dump(_data(provenance=approved)))
    [loaded] = load_templates(tmp_path)
    assert isinstance(loaded, PanelledType) and loaded.name == FAMILY
    other = {
        "identity": {
            "family": "other",
            "title": "Other",
            "description": "another table",
            "title_patterns": ["other"],
        },
        "layout": _layout(),
        "identities": [
            {**TOTAL, "right": {"sum": {"table": FAMILY, "rows": ["a", "b"]}}},
        ],
        "provenance": approved,
    }
    (tmp_path / "other.yaml").write_text(yaml.safe_dump(other))
    with pytest.raises(TemplateError, match="printed in panels"):
        load_templates(tmp_path)


# --- Finding the panels ---------------------------------------------------------------------------


def _blocks(boxes, size=(1000, 1000), double_at=None) -> bytes:
    """A page with a framed block of lines at each box; a double rule at x=double_at."""
    image = Image.new("L", size, 255)
    canvas = ImageDraw.Draw(image)
    for x0, y0, x1, y1 in boxes:
        canvas.rectangle([x0, y0, x1, y1], outline=0, width=2)
        for y in range(y0 + 20, y1 - 10, 30):
            canvas.rectangle([x0 + 20, y, x1 - 20, y + 8], fill=0)
        if double_at is not None:
            canvas.line([double_at, y0, double_at, y1], fill=0, width=2)
            canvas.line([double_at + 6, y0, double_at + 6, y1], fill=0, width=2)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_plain_code_cuts_the_page_at_its_gutters_and_drops_headings():
    image = _blocks([(100, 100, 900, 400), (100, 470, 900, 800), (100, 850, 300, 870)])
    found = panels.by_layout(image)
    assert [f.method for f in found] == ["layout", "layout"]
    assert [(f.box.y0, f.box.y1) for f in found] == [(100, 401), (470, 801)]


def test_plain_code_cuts_a_band_side_by_side_at_a_double_rule():
    found = panels.by_layout(_blocks([(100, 100, 900, 600)], double_at=497))
    assert len(found) == 2
    assert found[0].box.x1 == found[1].box.x0 and 490 <= found[0].box.x1 <= 510


def test_sam_is_asked_for_tables_and_its_parts_and_specks_are_not_panels():
    big, part, speck = BBox(x0=0, y0=0, x1=600, y1=600), BBox(x0=10, y0=10, x1=500, y1=500), BBox(
        x0=700, y0=700, x1=710, y1=710
    )
    other = BBox(x0=0, y0=650, x1=900, y1=990)
    segmenter = MockSegmenter(
        lambda request: [Region("table", b, 0.9) for b in (part, big, speck, other)]
    )
    found = panels.find(_blocks([]), segmenter)
    assert segmenter.calls[0].prompts == ("table",) and segmenter.calls[0].role == "segmenter"
    assert [(f.box, f.method) for f in found] == [(big, "sam"), (other, "sam")]
    assert panels.find(_blocks([(100, 100, 900, 400)]), MockSegmenter())[0].method == "layout"


def test_panels_are_placed_in_reading_order_only_when_the_counts_allow_it():
    def at(x0, y0, x1, y1):
        return panels.Found(BBox(x0=x0, y0=y0, x1=x1, y1=y1), "sam")

    right, left, below = at(500, 0, 900, 400), at(0, 10, 480, 390), at(0, 500, 900, 900)
    assert panels.reading_order([below, right, left]) == [left, right, below]
    doc_type = _panelled()  # upper, state_1, state_2
    assert panels.place([below, right, left], doc_type) == {
        "upper": left,
        "state_1": right,
        "state_2": below,
    }
    assert panels.place([left, right], doc_type) == {}  # two of three, two kinds: none placed
    one_kind = _panelled(panels=[{"key": "state", "title": "A State", "repeats": 3,
                                  "layout": _layout()}])
    assert panels.place([below, left], one_kind) == {"state_1": left, "state_2": below}


# --- The arithmetic test, panel by panel ----------------------------------------------------------

PANELS = {"upper": (100, 100, 900, 400), "lower": (100, 500, 900, 800)}
AMOUNTS = {"upper": ("10", "20", "30"), "lower": ("1", "2", "9")}  # the lower total is off


def _cell(panel: str, r: int) -> tuple[int, int, int, int]:
    x0, y0 = PANELS[panel][0] + 400, PANELS[panel][1] + 40 + 80 * r
    return x0, y0, x0 + 200, y0 + 40


@pytest.fixture
def panelled(tmp_path, monkeypatch) -> tuple[Path, dict]:
    """A two-panel draft and its two pages drawn, each amount its own shade; mock roles that read
    each panel's crop as the page prints it."""
    monkeypatch.setattr(template_module, "CITATIONS", "S0")
    monkeypatch.setattr(ocr, "words", lambda ref: ())
    data = _data(
        panels=[
            {"key": "upper", "title": "Upper", "layout": _layout(), "identities": [TOTAL]},
            {"key": "lower", "title": "Lower", "layout": _layout(), "identities": [TOTAL]},
        ]
    )
    data["provenance"]["drafted_from"] = REFS
    data["provenance"]["drafted_by"] = {"kind": "model", "id": "mock-llm"}
    folder = tmp_path / "templates"
    folder.mkdir()
    path = folder / f"{FAMILY}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    shade, text_of = {}, {}
    image = Image.new("RGB", (1000, 1000), "white")
    canvas = ImageDraw.Draw(image)
    for panel, box in PANELS.items():
        canvas.rectangle(box, outline=(0, 0, 0), width=2)
        for r, amount in enumerate(AMOUNTS[panel]):
            shade[(panel, r)] = 10 + len(shade) * 10
            text_of[shade[(panel, r)]] = amount
            canvas.rectangle(_cell(panel, r), fill=(shade[(panel, r)], 0, 0))
    found = {}
    for ref in REFS:
        file = tmp_path / "pages" / f"{ref}.png"
        file.parent.mkdir(parents=True, exist_ok=True)
        image.save(file)
        found[ref] = Page(ref, ref, file)

    def resolve(ref):
        if ref not in found:
            raise PageRefused(ref)
        return found[ref]

    monkeypatch.setattr(arithmetic, "resolve", resolve)

    def extractor(request) -> str:
        if request.prompt.startswith("Which kind of document"):
            return json.dumps({"doc_type": FAMILY})
        panel = "upper" if 'the panel "Upper"' in request.prompt else "lower"
        crop = Image.open(io.BytesIO(request.images[0]))
        assert "cut from a scanned page" in request.prompt
        dx, dy = PANELS[panel][0] - panels.PAD, PANELS[panel][1] - panels.PAD
        rows = {}
        for r, key in enumerate(("a", "b", "total")):
            x0, y0, x1, y1 = _cell(panel, r)
            box = [
                round((x0 - dx) * 1000 / crop.width),
                round((y0 - dy) * 1000 / crop.height),
                round((x1 - dx) * 1000 / crop.width),
                round((y1 - dy) * 1000 / crop.height),
            ]
            amount = {"value": AMOUNTS[panel][r], "box": box}
            rows[key] = {"item": {"value": key, "box": box}, "amount": amount}
        return json.dumps({"rows": rows})

    def rereader(request) -> str:
        crop = Image.open(io.BytesIO(request.images[0])).convert("RGB")
        return json.dumps({"value": text_of[crop.getpixel((crop.width // 2, crop.height // 2))[0]]})

    sam = MockSegmenter(
        lambda request: [Region("table", BBox(x0=a, y0=b, x1=c, y1=d), 0.9) for a, b, c, d in
                         PANELS.values()]
    )
    roles = {"extractor": MockLLM(extractor), "rereader": MockLLM(rereader), "segmenter": sam}
    return path, roles


def test_each_panel_is_read_on_its_crop_and_its_identities_counted(panelled):
    path, roles = panelled
    out = arithmetic.run_test(
        FAMILY, roles, directory=path.parent, config={"x": {}}, workers=2, today=TODAY
    )
    evidence = json.loads(out.read_text())
    page = evidence["pages"][0]
    assert page["read"] == "ok" and page["cells"] == 12 and page["agree"] == page["needed"] == 6
    assert [f["method"] for f in page["panels"]["found"]] == ["sam", "sam"]
    assert page["panels"]["copies"]["lower"] == {"read_on": "its panel", "found_by": "sam"}
    by_id = {i["id"]: i for i in evidence["identities"]}
    assert by_id["upper.total"]["outcome"] == "holds" and by_id["upper.total"]["held"] == 2
    assert by_id["lower.total"]["outcome"] == "rejected"
    failure = by_id["lower.total"]["failures"][0]
    assert {c["row"] for c in failure["cells"]} == {"lower.a", "lower.b", "lower.total"}


def test_a_panel_not_found_is_read_on_the_whole_page(panelled):
    path, roles = panelled
    roles["segmenter"] = MockSegmenter(lambda request: [])
    doc_type = PanelledType(read_template(path))
    values, found = panels.read_panels(
        arithmetic.resolve(REFS[0]).path.read_bytes(),
        REFS[0],
        (),
        doc_type,
        MockLLM(lambda request: json.dumps({"rows": {}})),
        roles["segmenter"],
        arithmetic.output_tokens,
        "S0",
    )
    # the page's two framed blocks are found by plain code, so each panel is still cropped
    assert [f["method"] for f in found["found"]] == ["layout", "layout"]
    assert all(c["read"].startswith("failed") for c in found["copies"].values())
    assert all(v.abstained for v in values) and len(values) == 12


def test_approval_goes_panel_by_panel(panelled):
    path, roles = panelled
    arithmetic.run_test(
        FAMILY, roles, directory=path.parent, config={"x": {}}, workers=2, today=TODAY
    )
    answers = iter(["a", "a person", "y"])
    approve.approve(FAMILY, directory=path.parent, ask=lambda q: next(answers), say=lambda s: None,
                    today=TODAY)
    template = read_template(path)
    assert template.provenance.approved
    assert [len(p.identities) for p in template.panels] == [1, 0]
    assert [d.id for d in template.provenance.dropped] == ["lower.total"]


def test_a_draft_in_panels_is_asked_for_panels_and_saved_with_them(tmp_path, monkeypatch):
    found = {}
    for ref in REFS:
        file = tmp_path / "pages" / f"{ref}.png"
        file.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (50, 50), "white").save(file)
        found[ref] = Page(ref, ref, file)
    monkeypatch.setattr(draft, "resolve", lambda ref: found[ref])
    answer = {
        "identity": {"title": "Receipts", "description": "Receipts in panels",
                     "title_patterns": ["receipts"]},
        "panels": [
            {"key": "Upper Part", "title": "Upper", "repeats": 1, "layout": _layout(),
             "identities": [TOTAL, {**TOTAL, "id": "bad", "left": {"cell": {"row": "nowhere"}}}]},
            {"key": "state", "title": "A State", "repeats": 12, "layout": _layout(),
             "identities": []},
        ],
    }
    llm = MockLLM(lambda request: json.dumps(answer))
    path = draft.draft(FAMILY, REFS, llm, directory=tmp_path / "t", today=TODAY, panelled=True)
    request = llm.calls[0]
    assert "printed in panels" in request.prompt and request.json_schema is draft.PANELS_SCHEMA
    template = read_template(path)
    assert [(p.key, p.repeats) for p in template.panels] == [("upper_part", 1), ("state", 9)]
    assert [i.id for i in template.panels[0].identities] == ["total"]
    assert any("upper_part.bad" in note for note in template.provenance.evidence)
    assert "identities:\n" not in path.read_text().split("panels:")[0]
