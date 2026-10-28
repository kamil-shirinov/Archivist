"""Document types from template files: hand-written templates and canned extractions in tmp_path.

No model is called: extraction and re-reads are MockLLM, answering from the page image alone.
"""

import io
import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from archivist.doctypes import REGISTRY, UNSUPPORTED, is_unresolvable
from archivist.doctypes.template import (
    TemplateError,
    TemplateType,
    cell_id,
    load_templates,
    number,
    read_template,
)
from archivist.export import bundle, database, rules
from archivist.models.budget import BudgetGuard
from archivist.models.mock import MockLLM, MockSegmenter
from archivist.pipeline import extract, verify
from archivist.pipeline.checks import run_checks
from archivist.schema import ExtractedValue, PageExtraction

ROOT = Path(__file__).resolve().parents[1]

RECEIPTS = """\
identity:
  family: receipts
  title: Receipts by Source
  description: A table of receipts by source for two months, in millions of dollars.
  title_patterns: ['receipts\\s+by\\s+source']
layout:
  unit: millions of dollars
  precision: "0.1"
  rows:
    - {key: customs, printed: Customs}
    - {key: income_tax, printed: Income tax}
    - {key: other, printed: All other}
    - {key: total, printed: Total}
  columns:
    - {key: july, printed: July, kind: money}
    - {key: august, printed: August, kind: money}
    - {key: both, printed: Two months, kind: money}
    - {key: change, printed: Change, kind: money}
    - {key: note, printed: Note, kind: text}
identities:
  - id: total_is_sum
    description: the total is the sum of the sources
    for_each: column
    left: {cell: {row: total}}
    right: {sum: {rows: [customs, income_tax, other]}}
  - id: both_months
    description: the two months add up
    for_each: row
    left: {cell: {column: both}}
    right: {sum: {columns: [july, august]}}
  - id: change
    description: the change is August less July
    for_each: row
    left: {cell: {column: change}}
    right: {difference: [{cell: {column: august}}, {cell: {column: july}}]}
provenance:
  status: approved
  drafted_by: {kind: model, id: muse-spark-1.3}
  drafted_on: 2026-10-20
  approved_by: a reviewer
  approved_on: 2026-10-21
  evidence: [three development pages, every identity holds]
"""

SUMMARY = """\
identity:
  family: summary
  title: Summary of Receipts
  description: A one-line summary of the month's total receipts.
  title_patterns: ['summary\\s+of\\s+receipts']
layout:
  unit: millions of dollars
  precision: "0.1"
  rows: [{key: total, printed: Total receipts}]
  columns: [{key: august, printed: August, kind: money}]
identities:
  - id: same_total
    description: the summary repeats the receipts table's total
    left: {cell: {row: total, column: august}}
    right: {cell: {table: receipts, row: total, column: august}}
provenance:
  status: approved
  drafted_by: {kind: person, id: a reviewer}
  drafted_on: 2026-10-20
  approved_by: a second reviewer
  approved_on: 2026-10-22
  evidence: [the same three pages]
"""

PRINTED = {  # customs, income tax, all other, total; every identity holds exactly
    "customs": ("10.4", "12.0", "22.4", "1.6", "a"),
    "income_tax": ("5.3", "7.1", "12.4", "1.8", ""),
    "other": ("1.0", ".5", "1.5", "-.5", ""),
    "total": ("16.7", "19.6", "36.3", "2.9", ""),
}
COLUMNS = ("july", "august", "both", "change", "note")
DCB = ("debit", "credit", "balance")
PAGE, OTHER = "issue-a_p001", "issue-a_p002"


def _write(folder: Path, family: str, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{family}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def types(tmp_path) -> dict[str, TemplateType]:
    folder = tmp_path / "templates"
    _write(folder, "receipts", RECEIPTS)
    _write(folder, "summary", SUMMARY)
    return {t.name: t for t in load_templates(folder)}


@pytest.fixture
def registered(types, monkeypatch) -> dict[str, TemplateType]:
    for name, doc_type in types.items():
        monkeypatch.setitem(REGISTRY, name, doc_type)
    return types


def _cells(changes: dict[tuple[str, str], str | None] | None = None) -> dict:
    cells = {(row, c): text for row, texts in PRINTED.items() for c, text in zip(COLUMNS, texts)}
    return cells | (changes or {})


def _page(doc_type: TemplateType, page_id: str, cells: dict) -> PageExtraction:
    values = []
    for field_id in doc_type.field_ids(page_id):
        *_, row, column = field_id.split(":")
        text = cells.get((row, column), "")
        values.append(
            ExtractedValue(
                field_id=field_id,
                value=text,
                citation=None,
                abstained=text is None,
            )
        )
    return PageExtraction(page_id=page_id, doc_type=doc_type.name, values=values)


def _receipts(types, changes=None, page_id=PAGE) -> PageExtraction:
    return _page(types["receipts"], page_id, _cells(changes))


def _summary(types, august="19.6", page_id=OTHER) -> PageExtraction:
    return _page(types["summary"], page_id, {("total", "august"): august})


def _id(row: str, column: str, family: str = "receipts", page_id: str = PAGE) -> str:
    return cell_id(family, page_id, row, column)


def _flags(types, pages):
    return [f for t in types.values() for f in t.checks(pages)]


# --- Reading figures ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("1,234.5", "money", Decimal("1234.5")),
        ("-12", "money", Decimal(-12)),
        ("(12.0)", "money", Decimal(-12)),
        (".4", "money", Decimal("0.4")),
        ("-.5", "money", Decimal("-0.5")),
        ("-", "money", Decimal(0)),
        ("12.5%", "percent", Decimal("12.5")),
        ("1,200", "count", Decimal(1200)),
        ("1.5", "count", None),
        ("1,23", "money", None),
        ("29, 139", "money", Decimal(29139)),  # a space after a thousands comma, between digits
        ("1, 234,567.5", "money", Decimal("1234567.5")),
        ("(29,  139)", "money", Decimal(-29139)),
        ("29, 139", "count", Decimal(29139)),
        ("29, 13", "money", None),  # not a thousands comma
        ("29, 1390", "money", None),
        ("29 ,139", "money", None),
        ("29,139, 5", "money", None),
        ("12a", "money", None),
        ("", "money", None),
        (".", "money", None),
    ],
)
def test_figures_are_read_as_a_statistical_table_prints_them(text, kind, value):
    assert number(text, kind) == value


def test_a_spaced_thousands_comma_is_read_through_by_templates_only(types):
    assert types["receipts"].money("29, 139") == Decimal(29139)
    for name in ("ledger_card", "payment_memo"):  # their figures are read by their own rules
        assert REGISTRY[name].money("29, 139.00") is None
        assert REGISTRY[name].money("29,139.00") == Decimal("29139.00")


def test_readings_compare_as_figures_dates_or_text(types):
    receipts = types["receipts"]
    july, note = _id("total", "july"), _id("customs", "note")
    assert receipts.canonical(july, "1,234.50") == receipts.canonical(july, "1234.5") == "1234.5"
    assert receipts.canonical(july, "29, 139") == receipts.canonical(july, "29,139") == "29139"
    assert receipts.canonical(july, "-") == receipts.canonical(july, "0.0") == "0"
    assert receipts.canonical(note, " see  Note ") == "SEE NOTE"
    assert receipts.money_fields == frozenset({"july", "august", "both", "change"})


# --- The type ----------------------------------------------------------------------------------


def test_the_schema_prompt_and_parser_cover_exactly_the_cells(types):
    receipts = types["receipts"]
    ids = receipts.field_ids(PAGE)
    assert len(ids) == 4 * 5 and ids[0] == "T.receipts:issue-a_p001:customs:july"
    schema = receipts.extraction_schema()
    assert list(schema["properties"]["rows"]["properties"]) == list(PRINTED)
    prompt = receipts.extraction_prompt()
    for text in ("Receipts by Source", "millions of dollars", '"All other"', '"Two months"'):
        assert text in prompt
    assert receipts.extraction_prompt(grounding=True) != prompt
    data = {
        "rows": {
            row: {c: {"value": t, "box": [10, 10, 50, 20]} for c, t in zip(COLUMNS, texts)}
            for row, texts in PRINTED.items()
        }
    }
    values = receipts.parse(PAGE, data, 1000, 1000)
    assert [v.field_id for v in values] == ids
    assert values[1].value == "12.0" and values[1].citation.bbox.x0 == 10
    del data["rows"]["other"]
    with pytest.raises(ValueError):
        receipts.parse(PAGE, data, 1000, 1000)


def test_reread_prompts_name_the_column_and_table_and_hold_no_digits(types, tmp_path):
    example = TemplateType(read_template(ROOT / "templates" / "gold_assets_and_liabilities.yaml"))
    for doc_type in (*types.values(), example):
        for field_id in doc_type.field_ids("1939-09_p057"):
            prompt = doc_type.reread_prompt(field_id)
            assert not any(c.isdigit() for c in prompt), prompt
    prompt = example.reread_prompt(example.field_ids("p")[2])
    assert '"Liabilities - Gold Certificates" column' in prompt


def test_title_patterns_recognise_the_printed_title(types):
    assert types["receipts"].matches_title("Table 4. - RECEIPTS  BY SOURCE")
    assert not types["receipts"].matches_title("Summary of Receipts")


# --- Identities: each kind holds, fails, and rounds at its tolerance -------------------------


def test_every_identity_holds_on_the_printed_table(types):
    pages = [_receipts(types), _summary(types)]
    assert _flags(types, pages) == []
    numeric = {f for p in pages for f in (v.field_id for v in p.values) if "note" not in f}
    assert set().union(*(t.balanced(pages) for t in types.values())) == numeric


def test_a_sum_over_rows_fails_and_implies_each_cell(types):
    pages = [_receipts(types, {("income_tax", "july"): "5.8"})]
    flags = [f for f in _flags(types, pages) if "total_is_sum" in f.detail]
    assert {f.field_id: f.suggested for f in flags} == {
        _id("total", "july"): "17.2",
        _id("customs", "july"): "9.9",
        _id("income_tax", "july"): "5.3",
        _id("other", "july"): "0.5",
    }
    detail = flags[0].detail
    assert detail.startswith("identity receipts.total_is_sum on column july: total is 16.7, ")
    assert "customs + income_tax + other is 17.2" in detail and "tolerance of 0.2 for 4" in detail
    assert {f.check for f in flags} == {"arithmetic"}


def test_a_sum_over_columns_and_a_difference_fail(types):
    flags = _flags(types, [_receipts(types, {("customs", "august"): "13.0"})])
    by_rule: dict[str, dict] = {}
    for flag in flags:
        rule = flag.detail.split(" on ")[0].removeprefix("identity ")
        by_rule.setdefault(rule, {})[flag.field_id] = flag.suggested
    assert by_rule["receipts.both_months"] == {
        _id("customs", "both"): "23.4",
        _id("customs", "july"): "9.4",
        _id("customs", "august"): "12.0",
    }
    assert by_rule["receipts.change"] == {
        _id("customs", "change"): "2.6",
        _id("customs", "august"): "12.0",
        _id("customs", "july"): "11.4",
    }
    assert by_rule["receipts.total_is_sum"][_id("customs", "august")] == "12.0"


@pytest.mark.parametrize(
    ("cell", "at_edge", "past_edge", "rule"),
    [
        (("total", "july"), "16.9", "17.0", "total_is_sum"),  # 4 values: 0.2
        (("customs", "both"), "22.55", "22.56", "both_months"),  # 3 values: 0.15
        (("customs", "change"), "1.75", "1.76", "change"),  # 3 values: 0.15
    ],
)
def test_rounding_holds_exactly_at_the_tolerance_and_fails_just_past_it(
    types, cell, at_edge, past_edge, rule
):
    def failing(text: str) -> list:
        flags = _flags(types, [_receipts(types, {cell: text})])
        return [f for f in flags if f.detail.startswith(f"identity receipts.{rule} on ")]

    assert failing(at_edge) == []
    assert failing(past_edge)


def test_the_same_cell_in_another_table_of_the_issue(types):
    receipts = _receipts(types)
    assert _flags(types, [receipts, _summary(types, "19.7")]) == []  # 2 values: 0.1
    flags = _flags(types, [receipts, _summary(types, "19.8")])
    assert {f.field_id: f.suggested for f in flags} == {
        _id("total", "august", "summary", OTHER): "19.6",
        _id("total", "august"): "19.8",
    }
    assert {f.check for f in flags} == {"crossdoc"}
    assert flags[0].detail.startswith("identity summary.same_total on the table: ")


@pytest.mark.parametrize(
    "pages",
    [
        lambda t: [_summary(t)],  # no receipts page in the batch
        lambda t: [_summary(t), _receipts(t, page_id="issue-b_p001")],  # another issue's
        lambda t: [_summary(t), _receipts(t), _receipts(t, page_id="issue-a_p009")],  # two
        lambda t: [_summary(t, page_id="p002"), _receipts(t, page_id="p001")],  # no issue
    ],
)
def test_another_table_that_cannot_be_found_is_unresolvable(types, pages):
    flags = [f for f in _flags(types, pages(types)) if "same_total" in f.detail]
    assert len(flags) == 1 and is_unresolvable(flags[0]) and flags[0].check == "crossdoc"
    assert rules.rule_id(flags[0]) == "unresolvable"


def test_unread_blank_and_unreadable_values_leave_identities_unchecked(types):
    unread = _receipts(types, {("customs", "july"): None, ("income_tax", "both"): ""})
    assert _flags(types, [unread]) == []
    flags = _flags(types, [_receipts(types, {("customs", "july"): "1O.4"})])
    assert [(f.field_id, f.detail) for f in flags] == [
        (_id("customs", "july"), "'1O.4' can't be read as an amount in millions of dollars")
    ]
    assert rules.rule_id(flags[0]) == "unreadable"


def test_a_row_of_blanks_is_unused(tmp_path):
    template = yaml.safe_load(RECEIPTS)
    template["layout"]["rows"] = {"read": 6}
    template["layout"]["columns"] = [c for c in template["layout"]["columns"] if c["key"] != "note"]
    template["identities"] = template["identities"][1:]  # per row only
    path = _write(tmp_path, "receipts", yaml.safe_dump(template, sort_keys=False))
    doc_type = TemplateType(read_template(path))
    cells = {
        (f"{n:02d}", c): text
        for n, texts in enumerate(PRINTED.values(), 1)
        for c, text in zip(COLUMNS, texts)
    }
    page = _page(doc_type, PAGE, cells)
    assert doc_type.checks([page]) == []
    assert not any(":05:" in f or ":06:" in f for f in doc_type.balanced([page]))
    assert len(doc_type.balanced([page])) == 4 * 4


RUNNING = """\
identity:
  family: running
  title: Running Account
  description: A running account of debits and credits, one balance per line.
  title_patterns: ['running\\s+account']
layout:
  unit: dollars
  precision: "0.01"
  rows: {read: 4}
  columns:
    - {key: debit, printed: Debit, kind: money}
    - {key: credit, printed: Credit, kind: money}
    - {key: balance, printed: Balance, kind: money}
identities:
  - id: running
    description: each balance is the one above, less the debit, plus the credit
    for_each: row
    left: {difference: [{cell: {column: balance}}, {cell: {column: credit}}]}
    right: {difference: [{cell: {column: balance, previous_row: true}}, {cell: {column: debit}}]}
provenance:
  status: draft
  drafted_by: {kind: person, id: a reviewer}
  drafted_on: 2026-10-28
"""


def test_a_cell_of_the_previous_row_carries_a_figure_down_the_table(tmp_path):
    doc_type = TemplateType(read_template(_write(tmp_path, "running", RUNNING)))
    lines = {"01": ("", "", "100.00"), "02": ("30.00", "-", "70.00"), "03": ("-", "5.50", "75.50")}
    cells = {(row, c): t for row, texts in lines.items() for c, t in zip(DCB, texts)}
    page = _page(doc_type, PAGE, cells)
    where = [i.where for i in doc_type.instances([page])]
    assert where == ["row 02", "row 03"]  # 01 has no row above
    assert doc_type.checks([page]) == []

    wrong = _page(doc_type, PAGE, cells | {("03", "balance"): "75.00"})
    flags = doc_type.checks([wrong])
    assert {f.field_id.rsplit(":", 2)[-2] for f in flags} == {"02", "03"}
    assert flags[0].detail.startswith(
        "identity running.running on row 03: balance − credit is 69.50, but "
        "balance (row above) − debit is 70.00"
    )
    implied = {f.field_id: f.suggested for f in flags}
    assert implied[cell_id("running", PAGE, "03", "balance")] == "75.50"
    assert implied[cell_id("running", PAGE, "02", "balance")] == "69.50"


def test_a_blank_counts_as_zero_only_where_its_column_says_so(tmp_path):
    zero = RUNNING.replace(
        "{key: debit, printed: Debit, kind: money}",
        "{key: debit, printed: Debit, kind: money, blank_means: zero}",
    ).replace(
        "{key: credit, printed: Credit, kind: money}",
        "{key: credit, printed: Credit, kind: money, blank_means: zero}",
    )
    lines = {"01": ("", "", "100.00"), "02": ("30.00", "", "70.00"), "03": ("", "5.50", "75.50")}
    cells = {(row, c): t for row, texts in lines.items() for c, t in zip(DCB, texts)}
    unknown = TemplateType(read_template(_write(tmp_path / "a", "running", RUNNING)))
    counted = TemplateType(read_template(_write(tmp_path / "b", "running", zero)))
    page = _page(unknown, PAGE, cells)
    texts = {v.field_id: v.value for v in page.values}
    assert [unknown.evaluate(i, texts) for i in unknown.instances([page])] == [None, None]
    results = [counted.evaluate(i, texts) for i in counted.instances([page])]
    assert results == [
        (Decimal("70.00"), Decimal("70.00"), Decimal("0.015")),  # 3 printed values, not 4
        (Decimal("70.00"), Decimal("75.50") - Decimal("5.50"), Decimal("0.015")),
    ]
    wrong = _page(counted, PAGE, cells | {("03", "balance"): "76.50"})
    flags = counted.checks([wrong])
    assert "for 3 printed values" in flags[0].detail
    implied = {f.field_id: f.suggested for f in flags}
    assert implied[cell_id("running", PAGE, "03", "debit")] == "-1.00"  # the blank, read as 0


CONTRACTS = """\
identity:
  family: contracts
  title: Outstanding Contracts
  description: Outstanding contracts by date, in sections.
  title_patterns: ['outstanding\\s+contracts']
layout:
  unit: thousands of dollars
  precision: "1"
  rows:
    sections:
      - {key: total, printed: TOTAL PURCHASE CONTRACTS, read: 3}
      - {key: foreign, printed: Purchases from foreign customers, read: 3}
      - {key: domestic, printed: Purchases from domestic customers, read: 3}
  columns:
    - {key: date, printed: Contracts as of, kind: text}
    - {key: europe, printed: Europe, kind: money}
    - {key: canada, printed: Canada, kind: money}
identities:
  - id: total_is_both
    description: total purchase contracts are those with foreign and domestic customers
    for_each: position
    left: {cell: {section: total}}
    right: {sum: {sections: [foreign, domestic]}}
provenance:
  status: draft
  drafted_by: {kind: person, id: a reviewer}
  drafted_on: 2026-10-28
"""
SECTIONED = {  # two dates this month: the third row of every section is blank
    "total": [("Apr. 5", "300", "90"), ("Apr. 12", "310", "92")],
    "foreign": [("Apr. 5", "100", "40"), ("Apr. 12", "105", "41")],
    "domestic": [("Apr. 5", "200", "50"), ("Apr. 12", "205", "51")],
}


def _sectioned(doc_type, changes=None):
    cells = {
        (f"{key}_{n:02d}", c): text
        for key, rows in SECTIONED.items()
        for n, texts in enumerate(rows, 1)
        for c, text in zip(("date", "europe", "canada"), texts)
    }
    return _page(doc_type, PAGE, cells | (changes or {}))


def test_sections_are_read_from_their_headings_and_summed_position_by_position(tmp_path):
    doc_type = TemplateType(read_template(_write(tmp_path, "contracts", CONTRACTS)))
    assert doc_type.layout.row_keys[:4] == ["total_01", "total_02", "total_03", "foreign_01"]
    prompt = doc_type.extraction_prompt()
    assert 'under the heading "Purchases from foreign customers": "foreign_01" to "foreign_03"' in (
        prompt
    )
    page = _sectioned(doc_type)
    where = [i.where for i in doc_type.instances([page])]
    assert where == [  # position 03 prints no row in any section, so it is skipped
        "position 01 in column europe",
        "position 02 in column europe",
        "position 01 in column canada",
        "position 02 in column canada",
    ]
    assert doc_type.checks([page]) == []

    flags = doc_type.checks([_sectioned(doc_type, {("domestic_02", "canada"): "40"})])
    assert {f.field_id.split(":")[-2] for f in flags} == {"total_02", "foreign_02", "domestic_02"}
    assert flags[0].detail.startswith(
        "identity contracts.total_is_both on position 02 in column canada: total is 92, but "
        "foreign + domestic is 81"
    )
    assert doc_type.rule(flags[0]) == "contracts.total_is_both"
    ids = doc_type.equation(flags[0], [_sectioned(doc_type, {("domestic_02", "canada"): "40"})])
    assert [i.split(":")[-2] for i in ids] == ["total_02", "foreign_02", "domestic_02"]


@pytest.mark.parametrize(
    "identity",
    [
        {"for_each": "row", "left": {"cell": {"section": "total", "column": "europe"}}},
        {"for_each": "position", "left": {"cell": {"section": "elsewhere"}}},
        {"for_each": "position", "left": {"cell": {"section": "total", "row": "total_01"}}},
    ],
)
def test_a_section_is_named_only_at_a_position_and_must_exist(tmp_path, identity):
    data = yaml.safe_load(CONTRACTS)
    data["identities"][0] |= identity
    _write(tmp_path, "contracts", yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(TemplateError):
        read_template(tmp_path / "contracts.yaml")


def test_a_position_identity_needs_a_table_in_sections(tmp_path):
    data = yaml.safe_load(RECEIPTS)
    data["identities"] = [
        {
            "id": "x",
            "description": "x",
            "for_each": "position",
            "left": {"cell": {"section": "total"}},
            "right": {"cell": {"section": "total"}},
        }
    ]
    _write(tmp_path, "receipts", yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(TemplateError, match="sections"):
        read_template(tmp_path / "receipts.yaml")


def test_the_example_holds_on_the_1939_page_it_was_written_from():
    """Gold Assets and Liabilities of the Treasury, Bulletin of September 1939, page 41, as read
    by hand from data/real/pages/1939-09/p057.jpg."""
    rows = [
        ("1934", "8,238.6", "5,274.0", "1,008.6"),
        ("1935", "10,122.9", "7,679.5", "487.4"),
        ("1936", "11,257.6", "8,959.6", "341.9"),
        ("1937", "12,760.0", "9,212.3", "1,591.6"),
        ("1938", "14,511.2", "11,872.8", "682.4"),
        ("1938-Aug", "13,135.5", "10,717.1", "462.4"),
        ("Sept", "13,759.3", "10,994.5", "808.8"),
        ("Oct", "14,064.3", "11,347.6", "760.6"),
        ("Nov", "14,311.9", "11,688.3", "667.6"),
        ("Dec", "14,511.2", "11,872.8", "682.4"),
        ("1939-Jan", "14,680.9", "12,022.3", "702.5"),
        ("Feb", "14,874.3", "12,199.1", "719.2"),
        ("Mar", "15,258.2", "12,627.0", "675.2"),
        ("Apr", "15,790.6", "13,176.0", "658.4"),
        ("May", "15,956.4", "13,398.8", "601.6"),
        ("June", "16,110.0", "13,595.6", "558.3"),
        ("July", "16,237.5", "13,949.8", "331.7"),
        ("Aug", "16,645.1", "14,391.9", "297.1"),
    ]
    template = read_template(ROOT / "templates" / "gold_assets_and_liabilities.yaml")
    assert template.provenance.status == "example, not approved"
    doc_type = TemplateType(template)
    names = ("period", "gold_assets", "gold_certificates", "gold_in_general_fund")
    cells = {}
    for n, row in enumerate(rows, 1):
        cells |= {(f"{n:02d}", c): text for c, text in zip(names, row)}
        cells |= {
            (f"{n:02d}", "gold_reserve"): "156.0",
            (f"{n:02d}", "stabilization_fund"): "1,800.0",
        }
    page = _page(doc_type, "1939-09_p057", cells)
    assert doc_type.checks([page]) == []
    assert len(doc_type.balanced([page])) == len(rows) * 5
    gaps = sorted(
        number(a, "money") - number(b, "money") - 156 - 1800 - number(c, "money")
        for _, a, b, c in rows
    )
    assert max(gaps) == Decimal("0.2") and gaps.count(Decimal("0.1")) == 6
    # One misread figure is caught, with the value it should have.
    cells[("14", "gold_certificates")] = "13,716.0"
    flags = doc_type.checks([_page(doc_type, "1939-09_p057", cells)])
    implied = {f.field_id.rsplit(":", 1)[-1]: f.suggested for f in flags}
    assert implied["gold_certificates"] == "13,176.2"  # 0.2 off from the printed, within rounding


# --- Templates that are refused, and the one that is ignored ----------------------------------


def _mutate(edit):
    data = yaml.safe_load(RECEIPTS)
    edit(data)
    return data


def _set(path: str, value):
    def edit(data):
        *parents, last = path.split(".")
        node = data
        for key in parents:
            node = node[int(key)] if key.isdigit() else node[key]
        node[int(last) if last.isdigit() else last] = value

    return edit


def _drop(path: str):
    def edit(data):
        *parents, last = path.split(".")
        node = data
        for key in parents:
            node = node[key]
        del node[last]

    return edit


MALFORMED = {
    "unknown section": _set("script", "import os"),
    "no provenance": _drop("provenance"),
    "unknown kind": _set("layout.columns.0.kind", "currency"),
    "precision not a power of ten": _set("layout.precision", "0.5"),
    "precision as a float": _set("layout.precision", 0.1),
    "repeated column": _set("layout.columns.1.key", "july"),
    "key not an identifier": _set("layout.rows.0.key", "Customs duties"),
    "free code as an expression": _set("identities.0.right", "customs + income_tax + other"),
    "unknown expression": _set("identities.0.right", {"product": {"rows": ["customs"]}}),
    "unknown row": _set("identities.0.right.sum.rows", ["customs", "excise"]),
    "unknown column": _set("identities.1.right.sum.columns", ["july", "september"]),
    "a text column in a sum": _set("identities.1.right.sum.columns", ["july", "note"]),
    "a sum over rows and columns": _set("identities.0.right.sum.columns", ["july"]),
    "an empty sum": _set("identities.0.right.sum.rows", []),
    "a cell without a column": _set("identities.0.for_each", "table"),
    "over without for_each": _set(
        "identities.0",
        {
            "id": "x",
            "description": "x",
            "over": ["july"],
            "left": {"cell": {"row": "total", "column": "july"}},
            "right": {"sum": {"rows": ["customs"], "column": "july"}},
        },
    ),
    "over a text column": _set("identities.0.over", ["note"]),
    "repeated identity": _set("identities.1.id", "total_is_sum"),
    "its own table by name": _set(
        "identities.0.left", {"cell": {"table": "receipts", "row": "total"}}
    ),
    "only another table": _set(
        "identities.0",
        {
            "id": "x",
            "description": "x",
            "left": {"cell": {"table": "summary", "row": "total", "column": "august"}},
            "right": {"cell": {"table": "summary", "row": "total", "column": "august"}},
        },
    ),
    "a previous row outside for_each: row": _set(
        "identities.0.left", {"cell": {"row": "total", "previous_row": True}}
    ),
    "a previous row that names its row": _set(
        "identities.1.left", {"cell": {"row": "total", "column": "both", "previous_row": True}}
    ),
    "a previous row in another table": _set(
        "identities.1.left", {"cell": {"table": "summary", "column": "both", "previous_row": True}}
    ),
    "a text column whose blank is zero": _set("layout.columns.4.blank_means", "zero"),
    "approved without an approver": _drop("provenance.approved_by"),
    "approved before drafted": _set("provenance.approved_on", "2026-10-01"),
    "a draft with an approval": _set("provenance.status", "draft"),
    "a bad title pattern": _set("identity.title_patterns", ["receipts ("]),
    "a two-line description": _set("identity.description", "one\ntwo"),
    "a name that isn't the file's": _set("identity.family", "other_receipts"),
}


@pytest.mark.parametrize("edit", MALFORMED.values(), ids=MALFORMED)
def test_a_malformed_template_is_refused(tmp_path, edit):
    _write(tmp_path, "receipts", yaml.safe_dump(_mutate(edit), sort_keys=False))
    with pytest.raises(TemplateError, match="receipts"):
        load_templates(tmp_path)


def test_a_file_that_is_not_yaml_is_refused(tmp_path):
    _write(tmp_path, "receipts", "identity: [unclosed")
    with pytest.raises(TemplateError):
        load_templates(tmp_path)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("table: receipts, row: total", "table: payments, row: total"),  # no such table
        ("table: receipts, row: total", "table: receipts, row: grand_total"),  # no such row
        ("column: august}}", "column: note}}"),  # not a figure
    ],
)
def test_unknown_references_to_another_table_are_refused(tmp_path, old, new):
    _write(tmp_path, "receipts", RECEIPTS)
    _write(tmp_path, "summary", SUMMARY.replace(old, new))
    with pytest.raises(TemplateError, match="same_total"):
        load_templates(tmp_path)


def test_an_approved_template_may_not_lean_on_a_draft(tmp_path):
    draft = yaml.safe_load(RECEIPTS)
    draft["provenance"] = {
        "status": "draft",
        "drafted_by": {"kind": "model", "id": "muse-spark-1.3"},
        "drafted_on": "2026-10-20",
    }
    _write(tmp_path, "receipts", yaml.safe_dump(draft, sort_keys=False))
    _write(tmp_path, "summary", SUMMARY)
    with pytest.raises(TemplateError, match="approved"):
        load_templates(tmp_path)


def test_an_unapproved_template_is_ignored(tmp_path):
    draft = yaml.safe_load(RECEIPTS)
    draft["provenance"] = {
        "status": "draft",
        "drafted_by": {"kind": "model", "id": "muse-spark-1.3"},
        "drafted_on": "2026-10-20",
        "evidence": ["drafted from one page"],
    }
    _write(tmp_path, "receipts", yaml.safe_dump(draft, sort_keys=False))
    assert load_templates(tmp_path) == []
    _write(tmp_path, "receipts", RECEIPTS)
    assert [t.name for t in load_templates(tmp_path)] == ["receipts"]


def test_a_template_may_not_take_a_built_in_name(tmp_path):
    _write(tmp_path, "ledger_card", RECEIPTS.replace("family: receipts", "family: ledger_card"))
    with pytest.raises(TemplateError, match="reserved"):
        load_templates(tmp_path, reserved=["ledger_card", UNSUPPORTED])


def test_the_committed_templates_validate_and_only_approved_ones_are_registered():
    built_in = ["ledger_card", "payment_memo"]
    found = load_templates(ROOT / "templates", reserved=[*built_in, UNSUPPORTED])
    assert all(t.template.provenance.approved for t in found)
    assert list(REGISTRY) == [*built_in, *(t.name for t in found)]


# --- Through the pipeline and the exporter -----------------------------------------------------

SIZE = 1000  # pixels, so the 0-1000 grid is the page


def _box(row: int, column: int) -> list[int]:
    x0, y0 = 60 + 180 * column, 100 + 80 * row
    return [x0, y0, x0 + 140, y0 + 40]


def _layout(types) -> dict[str, list[tuple[str, list[int], str]]]:
    """Every cell of each page: field id, grid box and the value printed in it."""
    out = {}
    for page_id, doc_type, printed in (
        (PAGE, types["receipts"], _cells()),
        (OTHER, types["summary"], {("total", "august"): "19.6"}),
    ):
        cells = []
        rows, columns = doc_type.layout.row_keys, [c.key for c in doc_type.layout.columns]
        for r, row in enumerate(rows):
            for c, column in enumerate(columns):
                field_id = cell_id(doc_type.name, page_id, row, column)
                cells.append((field_id, _box(r, c), printed.get((row, column), "")))
        out[page_id] = cells
    return out


def test_a_template_type_runs_through_extraction_verification_and_export(
    registered, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)  # the runs name their images relative to the repository
    layout = _layout(registered)
    shade = {}  # field id <-> the red its box is filled with, so a crop shows whose cell it is
    images = Path("data/demo/images")
    images.mkdir(parents=True)
    page_of_image = {}
    for page_id, cells in layout.items():
        image = Image.new("RGB", (SIZE, SIZE), "white")
        draw = ImageDraw.Draw(image)
        for field_id, box, _ in cells:
            shade[field_id] = len(shade) + 1
            draw.rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=(shade[field_id], 0, 0))
        path = images / f"{page_id}.png"
        image.save(path)
        page_of_image[path.read_bytes()] = page_id
    by_shade = {s: f for f, s in shade.items()}
    printed = {f: text for cells in layout.values() for f, _, text in cells}
    misread = _id("income_tax", "august")

    def extractor(request) -> str:
        page_id = page_of_image[request.images[0]]
        doc_type = "receipts" if page_id == PAGE else "summary"
        if request.prompt.startswith("Which kind of document"):
            assert registered["receipts"].description in request.prompt
            return json.dumps({"doc_type": doc_type})
        rows: dict = {}
        for field_id, box, text in layout[page_id]:
            *_, row, column = field_id.split(":")
            value = "1.1" if field_id == misread else text
            rows.setdefault(row, {})[column] = {"value": value, "box": box}
        return json.dumps({"rows": rows})

    def rereader(request) -> str:
        crop = Image.open(io.BytesIO(request.images[0])).convert("RGB")
        field_id = by_shade[crop.getpixel((crop.width // 2, crop.height // 2))[0]]
        return json.dumps({"value": printed[field_id]})

    guard = BudgetGuard(1.0, tmp_path / "ledger.jsonl")
    runs = Path("results/runs")
    extract.run(
        images,
        runs / "demo-extract",
        {"extractor": MockLLM(extractor)},
        guard=guard,
        config={},
        doc_types=registered,
        citation_strategy="S0",
    )
    verify.run(
        runs / "demo-extract",
        runs / "demo-verify",
        {"segmenter": MockSegmenter(), "rereader": MockLLM(rereader)},
        guard=guard,
        config={},
        doc_types=registered,
    )
    record = json.loads((runs / "demo-verify" / "run.json").read_text())
    assert record["doc_types"] == {name: t.sha256 for name, t in registered.items()}
    assert record["policy"]["money_fields"] == ["august", "both", "change", "july"]
    verdicts = {
        v.field_id: v for v in verify.load_verdicts(runs / "demo-verify" / "verdicts.jsonl")
    }
    assert len(verdicts) == 4 * 5 + 1
    wrong = verdicts[misread]
    assert (wrong.status, wrong.value) == ("review", "1.1")
    assert (wrong.evidence.proposed, wrong.evidence.proposed_by) == ("7.1", "reread_chain")
    assert wrong.evidence.route == "arithmetic"
    assert verdicts[_id("customs", "note")].evidence.route == "reread"
    assert verdicts[_id("total", "august", "summary", OTHER)].status == "accepted"

    built = bundle.build(runs / "demo-verify")
    field = next(f for f in built.fields if f.field_id == misread)
    summed = next(f for f in field.flags if f.rule == "receipts.total_is_sum")
    assert summed.suggested == "7.1"
    assert summed.related == [_id(r, "august") for r in ("total", "customs", "other")]
    both = next(f for f in field.flags if f.rule == "receipts.both_months")
    assert both.related == [_id("income_tax", "both"), _id("income_tax", "july")]
    assert ("rule_failed", "receipts.total_is_sum") in [(r.code, r.rule) for r in field.reasons]
    assert {d.doc_type for d in built.documents} == {"receipts", "summary"}
    assert built.accounts == [] and built.transactions == [] and built.links == []

    written = database.write(built, Path("exports/demo-verify"))
    assert {p.name for p in written} >= {"field_values.csv", "documents.csv", "archivist.sqlite"}
    tables = database.rows(built)
    assert len(tables["field_values"]) == len(verdicts) and len(tables["documents"]) == 2


def test_the_checks_and_the_rule_reader_see_registered_templates(registered):
    pages = [_receipts(registered, {("other", "july"): "1.5"}), _summary(registered)]
    flags = run_checks(pages)
    assert {rules.rule_id(f) for f in flags} == {
        "receipts.total_is_sum",
        "receipts.both_months",
        "receipts.change",
    }
    reading = rules.Reading(pages)
    flag = next(f for f in flags if f.field_id == _id("total", "july"))
    assert rules.related(flag, reading) == [
        _id(r, "july") for r in ("customs", "income_tax", "other")
    ]
