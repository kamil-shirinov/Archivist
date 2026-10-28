"""Drafted templates (P21b): the drafter's parsing, the arithmetic test's bookkeeping, the approval
file, the family choice, the rediscovery matcher and the per-run scoping of document types.

No model is called: the drafter, the extractor and the re-reader are MockLLM. Every file is written
under tmp_path.
"""

import copy
import io
import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image, ImageDraw

from archivist.doctypes import BUILT_IN, LEGACY, REGISTRY, enabled, from_config, recorded
from archivist.doctypes import template as template_module
from archivist.doctypes.template import (
    ReadRows,
    Template,
    TemplateError,
    TemplateType,
    cell_id,
    evidence_path,
    file_sha256,
    load_templates,
    read_template,
    written,
)
from archivist.models.budget import BudgetGuard
from archivist.models.mock import MockLLM, MockSegmenter
from archivist.pipeline import checks, extract, verify
from archivist.schema import BBox, Citation, ExtractedValue, PageExtraction
from archivist.templates import (
    approve,
    compare_citations,
    draft,
    families,
    grid_probe,
    ocr,
    pages,
    rediscover,
)
from archivist.templates import test as arithmetic
from archivist.templates.pages import Page, PageRefused

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "receipts_by_source"
REFS = ["1939-01_p010", "1939-02_p012"]
TODAY = date(2026, 10, 28)

ANSWER = {
    "identity": {
        "title": "Receipts  by Source",
        "description": "A table of receipts by source for two months,\n in millions of dollars.",
        "title_patterns": ["receipts\\s+by\\s+source", "(unclosed"],
    },
    "layout": {
        "unit": "millions of dollars",
        "precision": "0.1",
        "rows": [
            {"key": "customs", "printed": "Customs"},
            {"key": "income_tax", "printed": "Income tax"},
            {"key": "other", "printed": "All other"},
            {"key": "total", "printed": "Total"},
        ],
        "columns": [
            {"key": "source", "printed": "Source", "kind": "text"},
            {"key": "july", "printed": "July", "kind": "money"},
            {"key": "august", "printed": "August", "kind": "money"},
            {"key": "both", "printed": "Two months", "kind": "money"},
        ],
    },
    "identities": [
        {
            "id": "total_is_sum",
            "description": "the total is the sum of the sources",
            "for_each": "column",
            "over": None,
            "left": {"cell": {"row": "total", "column": None}},
            "right": {
                "sum": {
                    "rows": ["customs", "income_tax", "other"],
                    "columns": None,
                    "row": None,
                    "column": None,
                }
            },
        },
        {
            "id": "both_months",
            "description": "the two months add up",
            "for_each": "row",
            "over": None,
            "left": {"cell": {"row": None, "column": "both"}},
            "right": {
                "sum": {"rows": None, "columns": ["july", "august"], "row": None, "column": None}
            },
        },
        {
            "id": "Both Months",  # repeats the id above once made a key
            "description": "july is august",
            "for_each": "row",
            "over": None,
            "left": {"cell": {"row": None, "column": "july"}},
            "right": {"cell": {"row": None, "column": "august"}},
        },
        {
            "id": "bad",
            "description": "names a column the layout doesn't have",
            "for_each": "row",
            "over": None,
            "left": {"cell": {"row": None, "column": "september"}},
            "right": {"cell": {"row": None, "column": "july"}},
        },
    ],
}
# customs, income tax, all other, total: the totals hold; income tax's two months don't add up.
PRINTED = {
    "customs": ("Customs", "10.4", "12.0", "22.4"),
    "income_tax": ("Income tax", "5.3", "7.1", "12.9"),
    "other": ("All other", "1.0", ".5", "1.5"),
    "total": ("Total", "16.7", "19.6", "36.8"),
}
COLUMNS = ("source", "july", "august", "both")


def _image(path: Path, shade: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), (shade, shade, shade)).save(path)
    return path


@pytest.fixture
def fake_pages(tmp_path, monkeypatch) -> dict[str, Page]:
    """The two references resolve to small images in tmp_path; anything else is refused."""
    found = {
        ref: Page(ref, ref, _image(tmp_path / "pages" / f"{ref}.png", 40 + 20 * n))
        for n, ref in enumerate(REFS)
    }

    def resolve(ref):
        if ref not in found:
            raise PageRefused(f"{ref}: refused")
        return found[ref]

    monkeypatch.setattr(draft, "resolve", resolve)
    monkeypatch.setattr(arithmetic, "resolve", resolve)
    return found


def _drafter(*answers) -> MockLLM:
    queue = list(answers)
    return MockLLM(lambda request: queue.pop(0) if len(queue) > 1 else queue[0])


@pytest.fixture
def drafted(tmp_path, fake_pages) -> Path:
    llm = _drafter(json.dumps(ANSWER))
    return draft.draft(FAMILY, REFS, llm, directory=tmp_path / "templates", today=TODAY)


# --- The drafter --------------------------------------------------------------------------------


def test_a_draft_is_saved_with_its_provenance_and_its_valid_identities(tmp_path, fake_pages):
    llm = _drafter(json.dumps(ANSWER))
    path = draft.draft(FAMILY, REFS, llm, directory=tmp_path / "templates", today=TODAY)

    assert path == tmp_path / "templates" / f"{FAMILY}.yaml"
    template = read_template(path)
    assert template.identity.title == "Receipts by Source"
    assert template.identity.description == (
        "A table of receipts by source for two months, in millions of dollars."
    )
    assert template.identity.title_patterns == ["receipts\\s+by\\s+source"]  # one didn't compile
    assert [i.id for i in template.identities] == ["total_is_sum", "both_months", "both_months_2"]
    provenance = template.provenance
    assert (provenance.status, provenance.drafted_by.kind) == ("draft", "model")
    assert (provenance.drafted_by.id, provenance.drafted_on) == ("mock-llm", TODAY)
    assert provenance.drafted_from == REFS
    assert provenance.approved_by is None and provenance.evidence_sha256 is None
    assert any("left out at drafting: identity 'bad'" in note for note in provenance.evidence)
    assert path.read_text().startswith("# Drafted by mock-llm from 1939-01_p010, 1939-02_p012")
    assert load_templates(tmp_path / "templates") == []  # validated, never registered

    (request,) = llm.calls
    assert request.role == draft.ROLE and request.json_schema == draft.SCHEMA
    assert request.images == tuple(p.path.read_bytes() for p in fake_pages.values())


def test_the_drafter_is_never_shown_our_document_types_or_the_family_name(drafted):
    prompt = draft.PROMPT.format(n=3).lower()
    for word in ("ledger", "memo", "card", "treasury", "bulletin", FAMILY, "receipts"):
        assert word not in prompt
    for word in ("balance", "debit", "credit", "brought", "carried", "running"):  # our rules
        assert word not in prompt
    for doc_type in REGISTRY.values():
        assert doc_type.description.lower() not in prompt
    assert '"previous_row": true' in prompt  # what the language can express, and only that


def test_a_previous_row_is_kept_and_a_false_one_is_dropped():
    answer = copy.deepcopy(ANSWER)
    answer["identities"] = [
        {
            "id": "carried",
            "description": "each month's both is the row above's plus its july",
            "for_each": "row",
            "over": None,
            "left": {"cell": {"row": None, "column": "both", "previous_row": False}},
            "right": {
                "difference": [
                    {"cell": {"row": None, "column": "both", "previous_row": True}},
                    {"cell": {"row": None, "column": "july", "previous_row": None}},
                ]
            },
        }
    ]
    provenance = {"status": "draft", "drafted_by": {"kind": "model", "id": "m"}}
    template, left_out = draft.parse_draft(answer, FAMILY, provenance | {"drafted_on": TODAY})
    assert left_out == []
    (identity,) = template.identities
    assert identity.left.cell.previous_row is None
    assert identity.right.difference[0].cell.previous_row is True
    assert written(identity) == "both = both (row above) − july"
    assert "previous_row: true" in draft.to_yaml(template, "x")
    assert "previous_row: false" not in draft.to_yaml(template, "x")


def test_an_unusable_answer_is_asked_again_once_with_what_was_wrong(tmp_path, fake_pages):
    broken = copy.deepcopy(ANSWER)
    broken["layout"]["precision"] = "0.5"
    llm = _drafter(json.dumps(broken), json.dumps(ANSWER))
    draft.draft(FAMILY, REFS, llm, directory=tmp_path, today=TODAY)
    first, second = llm.calls
    assert draft.RETRY_NOTE.split("{")[0] in second.prompt and "precision" in second.prompt
    assert second.prompt.startswith(first.prompt)

    with pytest.raises(draft.DraftFailed):
        draft.draft(FAMILY, REFS, _drafter("not json"), directory=tmp_path, today=TODAY)


def test_a_page_that_may_not_be_sent_is_refused_before_any_call(tmp_path, fake_pages):
    llm = _drafter(json.dumps(ANSWER))
    with pytest.raises(PageRefused):
        draft.draft(FAMILY, [REFS[0], "1940-01_p010"], llm, directory=tmp_path, today=TODAY)
    assert llm.calls == []


@pytest.mark.parametrize(
    ("family", "refs"),
    [("ledger_card", REFS), ("Not A Key", REFS), (FAMILY, REFS[:1]), (FAMILY, [REFS[0]] * 2)],
)
def test_a_draft_needs_a_new_family_name_and_two_or_three_pages(tmp_path, family, refs):
    with pytest.raises(ValueError):
        draft.draft(family, refs, _drafter("{}"), directory=tmp_path, today=TODAY)


def test_pages_are_sent_only_from_development_issues_and_the_dev_and_val_splits(tmp_path):
    root = tmp_path / "real"
    (root / "pages" / "1939-01").mkdir(parents=True)
    (root / "pages" / "1940-01").mkdir(parents=True)
    (root / "split.json").write_text((ROOT / "data/real/split.json").read_text())
    real = json.loads((ROOT / "data/real/manifest.json").read_text())
    entries = []
    for issue in ("1939-01", "1940-01"):
        image = _image(root / "pages" / issue / "p010.jpg", 90)
        entry = next(p for p in real["pages"] if p["issue"] == issue)
        entries.append(entry | {"page": 10, "sha256": file_sha256(image)})
    manifest = real | {"pages": entries}
    (root / "manifest.json").write_text(json.dumps(manifest))
    synth = tmp_path / "synth"
    for split in ("dev", "val", "test"):
        _image(synth / split / "images" / "card-01-1.jpg", 120)

    page = pages.resolve("1939-01_p010", root, synth)
    assert (page.page_id, page.path) == ("1939-01_p010", root / "pages/1939-01/p010.jpg")
    assert pages.resolve("dev/card-01-1", root, synth).page_id == "card-01-1"
    val = pages.resolve("val/card-01-1", root, synth)
    assert (val.page_id, val.path) == ("card-01-1", synth / "val/images/card-01-1.jpg")
    with pytest.raises(PageRefused, match="not a development issue"):
        pages.resolve("1940-01_p010", root, synth)
    (root / "pages/1939-01/p010.jpg").write_bytes(b"changed")
    for ref in ("1939-01_p010", "1939-01_p011", "test/card-01-1", "dev/missing", "../x"):
        with pytest.raises(PageRefused):
            pages.resolve(ref, root, synth)


# --- The arithmetic test's bookkeeping ----------------------------------------------------------


def _extraction(doc_type: TemplateType, page_id: str, printed=PRINTED) -> PageExtraction:
    values = []
    for row, texts in printed.items():
        for column, text in zip(COLUMNS, texts, strict=True):
            values.append(
                ExtractedValue(
                    field_id=cell_id(doc_type.name, page_id, row, column),
                    value=text,
                    citation=None,
                    abstained=text is None,
                )
            )
    return PageExtraction(page_id=page_id, doc_type=doc_type.name, values=values)


def _second(page: PageExtraction, changes=None) -> dict[str, arithmetic.Reading]:
    out = {v.field_id: arithmetic.Reading(v.value) for v in page.values}
    return out | (changes or {})


def _type(path: Path) -> TemplateType:
    return TemplateType(read_template(path), sha256=file_sha256(path))


def test_each_identity_is_counted_where_it_applies_on_cells_both_reads_agree_on(drafted):
    doc_type = _type(drafted)
    a, b = _extraction(doc_type, "p-a"), _extraction(doc_type, "p-b")
    july = cell_id(FAMILY, "p-b", "customs", "july")
    seconds = {
        "p-a": _second(a),
        "p-b": _second(b, {july: arithmetic.Reading("10.9")}),  # the two reads disagree
    }
    by_id = {i["id"]: i for i in arithmetic.tally(doc_type, [a, b], seconds)}

    total = by_id["total_is_sum"]  # down each of the 3 figure columns of 2 pages
    assert (total["applies"], total["evaluated"], total["held"]) == (6, 5, 5)
    assert total["not_evaluated"] == {arithmetic.DISAGREE: 1}
    assert total["outcome"] == "holds" and total["hold_rate"] == 1.0

    both = by_id["both_months"]  # along each of 4 rows of 2 pages; income tax and the total fail
    assert (both["applies"], both["held"], both["failed"]) == (8, 3, 4)
    assert both["not_evaluated"] == {arithmetic.DISAGREE: 1}
    assert both["outcome"] == "sometimes fails"
    failure = both["failures"][0]
    assert (failure["page"], failure["where"]) == ("p-a", "row income_tax")
    assert (failure["left"], failure["right"], failure["difference"]) == ("12.9", "12.4", "0.5")
    assert failure["tolerance"] == "0.15"
    cells = [(c["column"], c["side"], c["sign"], c["read"], c["reread"]) for c in failure["cells"]]
    assert cells == [
        ("both", "left", "+", "12.9", "12.9"),
        ("july", "right", "+", "5.3", "5.3"),
        ("august", "right", "+", "7.1", "7.1"),
    ]

    never = by_id["both_months_2"]  # july is never august
    assert (never["held"], never["outcome"]) == (0, "rejected")


def test_an_identity_with_no_cell_read_twice_is_untested(drafted):
    doc_type = _type(drafted)
    page = _extraction(doc_type, "p-a")
    illegible = arithmetic.Reading(None, "illegible to the re-read")
    seconds = {"p-a": dict.fromkeys(_second(page), illegible)}
    by_id = {i["id"]: i for i in arithmetic.tally(doc_type, [page], seconds)}
    assert {i["outcome"] for i in by_id.values()} == {"untested"}
    assert by_id["total_is_sum"]["not_evaluated"] == {arithmetic.ONCE: 3}

    blank = {row: (t[0], "", "", "") if row == "other" else t for row, t in PRINTED.items()}
    page = _extraction(doc_type, "p-a", blank)
    by_id = {i["id"]: i for i in arithmetic.tally(doc_type, [page], {"p-a": _second(page)})}
    assert by_id["total_is_sum"]["not_evaluated"] == {arithmetic.BLANK: 3}


SIZE = 1000


def _box(row: int, column: int) -> list[int]:
    x0, y0 = 60 + 200 * column, 100 + 100 * row
    return [x0, y0, x0 + 150, y0 + 50]


@pytest.fixture
def tested(drafted, tmp_path, monkeypatch) -> Path:
    """The draft's arithmetic test on its two pages, with a mock extractor and re-reader."""
    monkeypatch.setattr(template_module, "CITATIONS", "S0")  # boxes as drawn: a crop shows its cell
    doc_type = _type(drafted)
    shade, printed_of, page_of = {}, {}, {}
    for ref in REFS:
        image = Image.new("RGB", (SIZE, SIZE), "white")
        canvas = ImageDraw.Draw(image)
        for r, (row, texts) in enumerate(PRINTED.items()):
            for c, (column, text) in enumerate(zip(COLUMNS, texts, strict=True)):
                field_id = cell_id(FAMILY, ref, row, column)
                shade[field_id] = len(shade) + 1
                printed_of[field_id] = text
                x0, y0, x1, y1 = _box(r, c)
                canvas.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(shade[field_id], 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        draft.resolve(ref).path.write_bytes(buffer.getvalue())
        page_of[buffer.getvalue()] = ref
    by_shade = {s: f for f, s in shade.items()}

    def extractor(request) -> str:
        ref = page_of[request.images[0]]
        if request.prompt.startswith("Which kind of document"):
            assert doc_type.description in request.prompt
            return json.dumps({"doc_type": FAMILY if ref == REFS[0] else "unsupported"})
        rows = {
            row: {
                column: {"value": text, "box": _box(r, c)}
                for c, (column, text) in enumerate(zip(COLUMNS, texts, strict=True))
            }
            for r, (row, texts) in enumerate(PRINTED.items())
        }
        return json.dumps({"rows": rows})

    def rereader(request) -> str:
        crop = Image.open(io.BytesIO(request.images[0])).convert("RGB")
        field_id = by_shade[crop.getpixel((crop.width // 2, crop.height // 2))[0]]
        return json.dumps({"value": printed_of[field_id]})

    roles = {"extractor": MockLLM(extractor), "rereader": MockLLM(rereader)}
    return arithmetic.run_test(
        FAMILY, roles, directory=drafted.parent, config={"x": {}}, workers=2, today=TODAY
    )


def test_the_test_reads_the_pages_through_the_pipeline_and_writes_its_evidence(drafted, tested):
    assert tested == drafted.with_name(f"{FAMILY}.evidence.json")
    evidence = json.loads(tested.read_text())
    assert evidence["template_sha256"] == file_sha256(drafted)
    assert (evidence["family"], evidence["tested_on"], evidence["citations"]) == (
        FAMILY,
        "2026-10-28",
        "S0",
    )
    first, second = evidence["pages"]
    assert (first["ref"], first["classified_as"], second["classified_as"]) == (
        REFS[0],
        FAMILY,
        "unsupported",  # recorded as evidence; the page is read as the draft all the same
    )
    assert first["cells"] == 16 and first["read_twice"] == first["agree"] == 12  # figures only
    assert evidence["outcomes"] == {"rejected": 1, "sometimes fails": 1, "holds": 1, "untested": 0}
    by_id = {i["id"]: i for i in evidence["identities"]}
    assert by_id["both_months"]["failed"] == 4 and by_id["total_is_sum"]["held"] == 6


def test_a_big_table_gets_a_bigger_output_allowance(drafted):
    assert arithmetic.output_tokens(_type(drafted)) == extract.EXTRACT_TOKENS
    small = _type(drafted).template
    layout = small.layout.model_copy(update={"rows": ReadRows(read=99)})
    big = TemplateType(small.model_copy(update={"layout": layout}))
    assert arithmetic.output_tokens(big) == 4_000 + 40 * 99 * 4


# --- The approval -------------------------------------------------------------------------------


def _answers(*answers):
    queue = list(answers)
    asked = []

    def ask(question: str) -> str:
        asked.append(question)
        return queue.pop(0)

    return ask, asked


def test_approval_asks_about_each_identity_the_test_kept_and_signs_the_file(tested, drafted):
    ask, asked = _answers("x", "a", "d", "", "me@example.org", "  a   reviewer ", "y")
    shown = []
    path = approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=shown.append, today=TODAY)

    assert len([q for q in asked if "[a]ccept" in q]) == 3  # one unclear answer, then a and d
    assert any("dropped by the arithmetic test" in line for line in shown)
    assert any("FAILED on 1939-01_p010, row income_tax" in line for line in shown)
    approved = read_template(path)
    provenance = approved.provenance
    assert (provenance.status, provenance.approved_by, provenance.approved_on) == (
        "approved",
        "a reviewer",
        TODAY,
    )
    assert provenance.evidence_sha256 == file_sha256(tested)
    assert [i.id for i in approved.identities] == ["total_is_sum"]
    assert [(d.id, d.by) for d in provenance.dropped] == [
        ("both_months", "approver"),
        ("both_months_2", "arithmetic test"),
    ]
    assert provenance.dropped[0].why == "dropped by the approver"
    assert provenance.drafted_from == REFS and provenance.drafted_on == TODAY
    data = yaml.safe_load(path.read_text())
    assert data["provenance"]["evidence_sha256"] == file_sha256(tested)

    (registered,) = load_templates(drafted.parent)
    assert (registered.name, registered.sha256) == (FAMILY, file_sha256(path))
    tested.write_text(tested.read_text().replace('"held": 6', '"held": 7'))
    with pytest.raises(TemplateError, match="not what it was approved on"):
        read_template(path)


@pytest.fixture
def zero_july(monkeypatch):
    """The drafter proposes that a blank in the july column is zero."""
    columns = copy.deepcopy(ANSWER["layout"]["columns"])
    columns[1]["blank_means"] = "zero"
    columns[0]["blank_means"] = "zero"  # a text column's means nothing, and is dropped
    monkeypatch.setitem(ANSWER["layout"], "columns", columns)


def test_a_blank_that_is_zero_is_drafted_and_approved_like_the_rest(zero_july, tested, drafted):
    layout = read_template(drafted).layout
    assert [c.blank_means for c in layout.columns] == ["unknown", "zero", "unknown", "unknown"]
    ask, asked = _answers("u", "a", "d", "", "a reviewer", "y")
    shown = []
    path = approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=shown.append, today=TODAY)
    assert "a blank leaves an identity unchecked" in asked[0]
    assert any("july (money, a blank is zero)" in line for line in shown)
    approved = read_template(path)
    assert approved.layout.column("july").blank_means == "unknown"
    assert any("column 'july' is unknown, not zero" in n for n in approved.provenance.evidence)


def test_nothing_is_written_unless_the_person_confirms(tested, drafted):
    before = drafted.read_text()
    ask, _ = _answers("a", "a", "a reviewer", "n")
    with pytest.raises(approve.NotApproved, match="nothing was written"):
        approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=lambda _: None, today=TODAY)
    assert drafted.read_text() == before


def test_evidence_from_another_draft_is_refused_before_anything_is_asked(tested, drafted):
    drafted.write_text(drafted.read_text().replace("the two months add up", "they add up"))
    ask, asked = _answers()
    with pytest.raises(approve.NotApproved, match="not this draft's"):
        approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=lambda _: None)
    assert asked == []
    evidence_path(drafted).unlink()
    with pytest.raises(approve.NotApproved, match="missing"):
        approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=lambda _: None)


def test_an_approved_template_is_neither_retested_nor_redrafted(tested, drafted, fake_pages):
    ask, _ = _answers("a", "a", "a reviewer", "y")
    approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=lambda _: None, today=TODAY)
    with pytest.raises(ValueError, match="approved"):
        arithmetic.run_test(FAMILY, {}, directory=drafted.parent)
    with pytest.raises(ValueError, match="approved"):
        draft.draft(FAMILY, REFS, _drafter(json.dumps(ANSWER)), directory=drafted.parent)
    with pytest.raises(approve.NotApproved, match="only a draft"):
        approve.approve(FAMILY, directory=drafted.parent, ask=ask, say=lambda _: None)


def test_approval_evidence_belongs_only_to_an_approved_template(drafted):
    data = yaml.safe_load(drafted.read_text())
    data["provenance"]["evidence_sha256"] = "0" * 64
    drafted.write_text(yaml.safe_dump(data))
    with pytest.raises(TemplateError, match="no approval evidence"):
        read_template(drafted)


# --- Document types are enabled per run (step 0) ------------------------------------------------


def test_every_committed_run_config_enables_the_built_in_types_alone():
    for config in ("models.toml", "models_open.toml", "arms/a.toml", "arms/b.toml", "arms/c.toml"):
        types = from_config(ROOT / "config" / config)
        assert recorded(types) == LEGACY == {"ledger_card": BUILT_IN, "payment_memo": BUILT_IN}


def test_only_registered_types_can_be_enabled(tmp_path):
    for names in ([], ["ledger_card", "ledger_card"], ["ledger_card", "receipts_by_source"]):
        with pytest.raises(ValueError):
            enabled(names)
    config = tmp_path / "c.toml"
    config.write_text("[roles]\n")
    with pytest.raises(ValueError, match="names no document types"):
        from_config(config)


def _approved_copy(drafted: Path, folder: Path) -> TemplateType:
    data = yaml.safe_load(drafted.read_text())
    data["provenance"] |= {
        "status": "approved",
        "approved_by": "a reviewer",
        "approved_on": "2026-10-29",
        "evidence": ["a test"],
    }
    folder.mkdir()
    path = folder / drafted.name
    path.write_text(yaml.safe_dump(data))
    (doc_type,) = load_templates(folder)
    return doc_type


def test_approving_a_template_changes_nothing_an_old_run_asks(drafted, tmp_path, monkeypatch):
    image = _image(tmp_path / "p.png", 50).read_bytes()

    def asked() -> tuple[str, dict]:
        llm = MockLLM(lambda request: json.dumps({"doc_type": "unsupported"}))
        extract.classify(image, llm, enabled(["ledger_card", "payment_memo"]))
        return llm.calls[0].prompt, llm.calls[0].json_schema

    before = asked()
    approved = _approved_copy(drafted, tmp_path / "approved")
    monkeypatch.setitem(REGISTRY, FAMILY, approved)
    assert asked() == before
    assert "july" not in verify.money_fields(enabled(list(LEGACY)))
    assert "july" in verify.money_fields(enabled([FAMILY]))
    assert recorded(enabled([FAMILY, "ledger_card"])) == {
        FAMILY: file_sha256(tmp_path / "approved" / drafted.name),
        "ledger_card": BUILT_IN,
    }
    with pytest.raises(ValueError, match="not read from its file"):
        recorded({FAMILY: TemplateType(approved.template)})


def test_a_run_resumes_and_is_verified_only_with_the_types_it_enabled(tmp_path):
    images = tmp_path / "images"
    _image(images / "p1.png", 30)
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    other = {"receipts_by_source": "0" * 64}
    (run_dir / "run.json").write_text(json.dumps({"doc_types": other}))
    llm = MockLLM()
    with pytest.raises(ValueError, match="start a new run"):
        extract.run(
            images,
            run_dir,
            {"extractor": llm},
            guard=BudgetGuard(1.0, tmp_path / "ledger.jsonl"),
            config={},
            doc_types=enabled(["ledger_card", "payment_memo"]),
        )
    assert llm.calls == []

    (run_dir / "predictions.jsonl").write_text("")
    (run_dir / "run.json").write_text(json.dumps({"images": str(images), "doc_types": other}))
    with pytest.raises(ValueError, match="enabled"):
        verify.run(
            run_dir,
            tmp_path / "runs" / "v1",
            {"segmenter": MockSegmenter(), "rereader": MockLLM()},
            guard=BudgetGuard(1.0, tmp_path / "ledger.jsonl"),
            config={},
            doc_types=enabled(["ledger_card", "payment_memo"]),
        )
    with pytest.raises(ValueError, match="not registered"):
        checks.run(run_dir)


# --- The family choice --------------------------------------------------------------------------


def _candidate(title: str, era: str, held_out_pages: int) -> families.Candidate:
    return families.Candidate(title, era, ["a", "b"], 3, held_out_pages, ["p"], [True], None)


def test_the_family_choice_takes_the_top_two_of_each_era_then_the_best_of_the_rest():
    old = [_candidate(f"Old {n}", "1939-1942", 100 - n) for n in range(5)]
    new = [_candidate(f"New {n}", "1982-1994", 10 - n) for n in range(3)]
    chosen = families.choose([*old, *new])
    assert [c.title for c in chosen] == ["Old 0", "Old 1", "Old 2", "Old 3", "New 0", "New 1"]
    assert [c.title for c in families.choose(new[:1])] == ["New 0"]


def test_a_family_key_is_its_title_cut_at_a_word_and_never_an_existing_template():
    title = "Short-Term Foreign Liabilities as Reported by Banks and Bankers"
    assert families.family_key(title, []) == "short_term_foreign_liabilities_as"
    assert families.family_key("Gold Assets", ["gold_assets"]) == "gold_assets_drafted"
    assert families.family_key("4. Totals", []) == "t_4_totals"
    assert families._spread(list("abcdefg"), 3) == ["a", "d", "g"]
    assert families._spread(list("ab"), 3) == ["a", "b"]


def test_a_held_out_issue_is_never_opened_for_its_text(tmp_path):
    with pytest.raises(ValueError, match="not a development issue"):
        families.ocr_text(tmp_path, "1940-01", 1)


# --- The rediscovery ----------------------------------------------------------------------------

CARD_TEMPLATE = {
    "identity": {
        "family": "drafted_card",
        "title": "A card",
        "description": "a card",
        "title_patterns": ["card"],
    },
    "layout": {
        "unit": "pounds",
        "precision": "0.01",
        "rows": [
            {"key": "brought_forward", "printed": "Brought forward"},
            *({"key": f"line_{n:02d}", "printed": str(n)} for n in (1, 2)),
            {"key": "carried_forward", "printed": "Carried forward"},
        ],
        "columns": [
            {"key": "debit", "printed": "Debit", "kind": "money"},
            {"key": "credit", "printed": "Credit", "kind": "money"},
            {"key": "balance", "printed": "Balance", "kind": "money"},
        ],
    },
    "identities": [
        {
            "id": "line_2",
            "description": "line 2's balance",
            "left": {"cell": {"row": "line_02", "column": "balance"}},
            "right": {
                "difference": [
                    {"sum": {"rows": ["line_01"], "column": "balance"}},
                    {
                        "difference": [
                            {"cell": {"row": "line_02", "column": "debit"}},
                            {"cell": {"row": "line_02", "column": "credit"}},
                        ]
                    },
                ]
            },
        },
        {
            "id": "line_1",
            "description": "line 1's balance, the other way round",
            "left": {
                "difference": [
                    {"cell": {"row": "brought_forward", "column": "balance"}},
                    {"cell": {"row": "line_01", "column": "balance"}},
                ]
            },
            "right": {
                "difference": [
                    {"cell": {"row": "line_01", "column": "debit"}},
                    {"cell": {"row": "line_01", "column": "credit"}},
                ]
            },
        },
        {
            "id": "carried",
            "description": "the carried forward",
            "left": {"cell": {"row": "carried_forward", "column": "balance"}},
            "right": {"cell": {"row": "line_02", "column": "balance"}},
        },
        {
            "id": "debits_are_credits",
            "description": "an extra",
            "for_each": "row",
            "over": ["line_01", "line_02"],
            "left": {"cell": {"column": "debit"}},
            "right": {"cell": {"column": "credit"}},
        },
    ],
    "provenance": {"status": "draft", "drafted_by": {"kind": "person", "id": "a test"},
                   "drafted_on": "2026-10-28"},
}


def test_drafted_identities_are_matched_to_the_known_rules_by_their_printed_headings():
    doc_type = TemplateType(Template.model_validate(CARD_TEMPLATE))
    found = rediscover.match(doc_type)
    assert {k: f.rule for k, f in found.items()} == {
        "line_2": "running_balance",
        "line_1": "running_balance",
        "carried": "carried_forward",
        "debits_are_credits": None,
    }
    assert (found["line_2"].at, found["line_2"].of) == (1, 1)
    assert (found["debits_are_credits"].at, found["debits_are_credits"].of) == (0, 2)
    assert {k.id for k in rediscover.KNOWN} >= set(rediscover.MATCHERS)


def test_a_running_balance_on_the_previous_row_is_found_on_rows_read_from_the_top():
    template = copy.deepcopy(CARD_TEMPLATE)
    template["layout"]["rows"] = {"read": 5}
    template["identities"] = [
        {
            "id": "running",
            "description": "each balance from the one above",
            "for_each": "row",
            "left": {"cell": {"column": "balance"}},
            "right": {
                "difference": [
                    {"cell": {"column": "balance", "previous_row": True}},
                    {
                        "difference": [
                            {"cell": {"column": "debit"}},
                            {"cell": {"column": "credit"}},
                        ]
                    },
                ]
            },
        },
        {
            "id": "wrong_way",
            "description": "credits taken off",
            "for_each": "row",
            "left": {"cell": {"column": "balance"}},
            "right": {
                "difference": [
                    {"cell": {"column": "balance", "previous_row": True}},
                    {"cell": {"column": "credit"}},
                ]
            },
        },
    ]
    doc_type = TemplateType(Template.model_validate(template))
    found = rediscover.match(doc_type)
    assert {k: f.rule for k, f in found.items()} == {"running": "running_balance", "wrong_way": None}
    assert (found["running"].at, found["running"].of) == (4, 4)  # row 01 has no row above


def test_an_identity_is_found_at_the_places_where_it_is_the_rule():
    template = copy.deepcopy(CARD_TEMPLATE)
    template["layout"]["columns"][0]["blank_means"] = "zero"
    template["layout"]["columns"][1]["blank_means"] = "zero"
    template["identities"] = [
        {
            "id": "running",
            "description": "every row from the one above, the carried forward row too",
            "for_each": "row",
            "left": {
                "difference": [
                    {"cell": {"column": "balance"}},
                    {"cell": {"column": "balance", "previous_row": True}},
                ]
            },
            "right": {
                "difference": [{"cell": {"column": "credit"}}, {"cell": {"column": "debit"}}]
            },
        }
    ]
    found = rediscover.match(TemplateType(Template.model_validate(template)))["running"]
    assert (found.rule, found.at, found.of) == ("running_balance", 2, 3)  # not the cf row


def test_the_rediscovery_drafts_from_three_val_pages_of_each_kind():
    drawn = rediscover.sample(ROOT / "data/val/manifest.json")
    assert drawn == rediscover.sample(ROOT / "data/val/manifest.json")
    assert [len(v) for v in drawn.values()] == [3, 3]
    assert all(ref.startswith("val/card-") for ref in drawn["rediscovery_cards"])
    assert all(ref.startswith("val/memo-") for ref in drawn["rediscovery_memos"])
    assert rediscover.OUT_DIR not in (Path("templates"), rediscover.FIRST_DIR)
    assert rediscover.REPORT != rediscover.FIRST_REPORT
    with pytest.raises(ValueError, match="seed"):
        rediscover.sample(ROOT / "data/dev/manifest.json")


# --- Which box strategy suits template tables ----------------------------------------------------


def test_the_box_strategy_with_more_agreeing_cells_wins_and_a_tie_keeps_s0():
    page = {"read": "ok", "sampled": 10}
    better = [page | {"S0": {"agree": 6}, "S0+ocr": {"agree": 7}}]
    assert compare_citations.decide(better) == ("S0+ocr", {"S0": 0.6, "S0+ocr": 0.7})
    tie = [page | {"S0": {"agree": 5}, "S0+ocr": {"agree": 5}}]
    assert compare_citations.decide(tie)[0] == "S0"
    unread = [{"read": "failed: x"}]
    assert compare_citations.decide(unread) == ("S0", {"S0": None, "S0+ocr": None})


# --- S0+ocr: boxes from the archive's OCR layer --------------------------------------------------


def test_the_ocr_layers_known_confusions_are_undone():
    assert ocr.digits("11*8,961") == "148961"
    assert ocr.digits("2,lt61»,05l»") == "2464054"
    assert ocr.digits("i.53i*.579") == "1534579"
    assert ocr.digits("15U.923") == "154923"
    assert ocr.digits("5^.>*33") == "5433"  # an unknown glyph is dropped, so it matches nothing


def _value(field: str, text: str, box: tuple[int, int, int, int]) -> ExtractedValue:
    bbox = BBox(**dict(zip(("x0", "y0", "x1", "y1"), box, strict=True)))
    return ExtractedValue(
        field_id=field, value=text, citation=Citation(page_id="p", bbox=bbox), abstained=False
    )


def _word(text: str, box: tuple[int, int, int, int]) -> ocr.Word:
    return ocr.Word(text, BBox(**dict(zip(("x0", "y0", "x1", "y1"), box, strict=True))))


def test_a_value_is_anchored_only_to_one_matching_figure_near_its_box():
    layer = [
        _word("11*8,961", (300, 440, 360, 452)),  # 148,961, two lines below the model's box
        _word("12,596", (300, 400, 360, 412)),
        _word("7", (300, 500, 310, 512)),
        _word("8,769", (300, 900, 360, 912)),  # far below: not this row region
        _word("335", (600, 400, 640, 412)),
        _word("335", (600, 430, 640, 442)),  # two candidates: ambiguous
    ]
    values = [
        _value("a", "148,961", (290, 395, 370, 415)),
        _value("b", "7", (290, 495, 370, 515)),  # one digit: never anchored
        _value("c", "8,769", (290, 395, 370, 415)),
        _value("d", "335", (590, 395, 650, 415)),
        _value("e", "-", (290, 395, 370, 415)),
    ]
    out, anchored = ocr.anchor(values, layer)
    assert anchored == {"a"}
    moved = {v.field_id: v.citation for v in out}
    assert moved["a"].bbox == layer[0].box and moved["a"].raw_bbox is None
    assert moved["c"] == values[2].citation  # unanchored: the model's box, untouched


def test_a_synthetic_page_has_no_ocr_layer_so_every_value_keeps_its_box(monkeypatch):
    monkeypatch.setattr(ocr, "resolve", lambda ref, root: Page(ref, "card-01-1", Path("x.jpg")))
    assert ocr.words("val/card-01-1") == ()


def test_two_values_claiming_one_figure_are_both_left_unanchored():
    layer = [_word("12,596", (300, 400, 360, 412))]
    values = [
        _value("a", "12,596", (290, 395, 370, 415)),
        _value("b", "12,596", (290, 420, 370, 440)),
    ]
    assert ocr.anchor(values, layer)[1] == set()


def test_the_sample_is_fixed_and_takes_only_needed_boxed_figures(drafted, monkeypatch):
    doc_type = _type(drafted)
    box = Citation(page_id="p-a", bbox=BBox(x0=0, y0=0, x1=10, y1=10))
    values = [
        v.model_copy(update={"citation": box if ":customs:" not in v.field_id else None})
        for v in _extraction(doc_type, "p-a").values
    ]
    ids = compare_citations.sample(doc_type, values, "p-a")
    assert ids == compare_citations.sample(doc_type, values, "p-a")
    assert not any(":customs:" in f or f.endswith(":source") for f in ids)  # unboxed; text
    assert len(ids) == 9  # 3 rows boxed x the 3 figures
    monkeypatch.setattr(compare_citations, "SAMPLE", 4)
    small = compare_citations.sample(doc_type, values, "p-a")
    assert len(small) == 4 and set(small) < set(ids)


def test_a_disagreement_gets_its_cause_by_rule(drafted):
    doc_type = _type(drafted)
    canon = doc_type.canonical
    here = cell_id(FAMILY, "p-a", "income_tax", "july")
    near = compare_citations.neighbours(doc_type, here)
    assert near == [
        cell_id(FAMILY, "p-a", r, c)
        for r, c in [("customs", "july"), ("other", "july"), ("total", "july"),
                     ("income_tax", "source"), ("income_tax", "august")]
    ]
    first = {near[0]: "10.4", near[1]: "1.0"}
    cause = compare_citations.cause
    assert cause("5.3", None, first, canon) == "unreadable crop"
    assert cause("1,234.5", "234.5", first, canon) == "unreadable crop"  # cut off
    assert cause("(12.0) 1/", "-12.0", first, canon) == "formatting only"
    assert cause("5.3", "10.4", first, canon) == "neighbouring cell"
    assert cause("5.3", "8.8", first, canon) == "unexplained"


# --- Is the grid findable from the page alone ----------------------------------------------------


def test_the_grid_probe_finds_drawn_rows_and_columns_through_ruled_lines():
    image = Image.new("L", (900, 700), 235)  # light paper, as the 1980s scans are
    canvas = ImageDraw.Draw(image)
    for r in range(12):
        for c in range(5):
            x, y = 100 + 150 * c, 80 + 45 * r
            canvas.rectangle([x, y, x + 80, y + 22], fill=60)  # a figure, about 25 px tall
    for c in range(6):
        x = 85 + 150 * c
        canvas.line([x, 60, x + 4, 640], fill=30, width=2)  # leaning rules
    canvas.line([60, 70, 860, 70], fill=30, width=2)
    gray = np.asarray(image)
    ink = gray <= grid_probe.otsu(gray)
    found = grid_probe.grid(ink, (70, 60, 850, 640))
    assert len(found["columns"]) == 5
    assert found["rows"] == 12 and found["rows_range"] == [12, 12]
    assert grid_probe.rules(ink) == (1, 6)  # the figures, however dense, are no rule


def test_runs_merge_small_gaps_and_drop_specks():
    flags = np.array([1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 1], dtype=bool)
    assert grid_probe.runs(flags, 1, 2) == [(0, 4), (12, 15)]
