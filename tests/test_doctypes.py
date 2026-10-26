"""Document-type plug-ins: fields, prompts, schemas and parsers, with no model involved."""

import pytest

from archivist.doctypes import REGISTRY, UNSUPPORTED, register
from archivist.doctypes.ledger import (
    COLUMNS,
    HEADER_BOTTOM,
    HEADER_TOP,
    LINES,
    MEMO_FIELDS,
    LedgerCard,
    PaymentMemo,
    grid_to_bbox,
)
from archivist.schema import BBox, ledger_header_id, ledger_line_id, memo_field_id

PAGE = "scan-0042"  # page ids are opaque: nothing may depend on their shape
WIDTH, HEIGHT = 1700, 1100
CELL = {"value": "1.00", "box": [100, 200, 300, 400]}


def _is_cell(schema: dict) -> bool:
    return set(schema.get("properties", {})) == {"value", "box"}


def _canned(schema: dict, cell: dict) -> dict:
    """A complete answer to a schema: `cell` at every leaf."""
    if _is_cell(schema):
        return dict(cell)
    return {key: _canned(child, cell) for key, child in schema["properties"].items()}


def _leaves(schema: dict) -> int:
    if _is_cell(schema):
        return 1
    return sum(_leaves(child) for child in schema["properties"].values())


def _required_everywhere(schema: dict) -> bool:
    if schema.get("type") != "object":
        return True
    props = schema["properties"]
    return (
        schema["required"] == list(props)
        and schema["additionalProperties"] is False
        and all(_required_everywhere(child) for child in props.values())
    )


# --- registry ----------------------------------------------------------------------------------


def test_registry_holds_the_ledger_family_with_one_line_descriptions():
    assert set(REGISTRY) == {"ledger_card", "payment_memo"}
    for name, doc_type in REGISTRY.items():
        assert doc_type.name == name
        assert doc_type.description and "\n" not in doc_type.description


def test_unsupported_and_duplicate_names_are_refused():
    class Fake:
        name = UNSUPPORTED

    with pytest.raises(ValueError):
        register(Fake())
    with pytest.raises(ValueError):
        register(LedgerCard())


# --- field ids ---------------------------------------------------------------------------------


def test_ledger_card_fields_are_the_header_and_18_lines_of_5_columns():
    ids = LedgerCard().field_ids(PAGE)
    expected = {ledger_header_id(PAGE, n) for n in HEADER_TOP + HEADER_BOTTOM} | {
        ledger_line_id(PAGE, line, column) for line in range(1, 19) for column in COLUMNS
    }
    assert len(ids) == len(set(ids)) == 95
    assert set(ids) == expected
    assert ids[0] == f"L:{PAGE}:hdr:account_no" and ids[-1] == f"L:{PAGE}:hdr:carried_forward"


def test_payment_memo_fields_are_the_seven_memo_fields():
    assert PaymentMemo().field_ids(PAGE) == [memo_field_id(PAGE, n) for n in MEMO_FIELDS]
    assert len(MEMO_FIELDS) == 7


# --- prompts and schemas -----------------------------------------------------------------------


@pytest.mark.parametrize("doc_type", [LedgerCard(), PaymentMemo()], ids=lambda d: d.name)
def test_schema_covers_exactly_the_field_ids(doc_type):
    schema = doc_type.extraction_schema()
    assert _leaves(schema) == len(doc_type.field_ids(PAGE))
    assert _required_everywhere(schema)
    values = doc_type.parse(PAGE, _canned(schema, CELL), WIDTH, HEIGHT)
    assert [v.field_id for v in values] == doc_type.field_ids(PAGE)


@pytest.mark.parametrize(
    ("doc_type", "names"),
    [
        (LedgerCard(), HEADER_TOP + HEADER_BOTTOM + COLUMNS),
        (PaymentMemo(), MEMO_FIELDS),
    ],
    ids=lambda d: getattr(d, "name", ""),
)
def test_prompt_names_every_field_and_states_the_rules(doc_type, names):
    prompt = doc_type.extraction_prompt()
    for name in names:
        assert f"- {name}:" in prompt
    assert "exactly as printed" in prompt
    assert "Never correct arithmetic, spelling" in prompt
    assert 'A blank cell is ""' in prompt
    assert "its value is null" in prompt
    assert "[x_min, y_min, x_max, y_max] on a 0-1000 grid" in prompt


def test_ledger_prompt_keys_lines_by_the_printed_number():
    prompt = LedgerCard().extraction_prompt()
    assert '"01" to "18"' in prompt and "pre-printed" in prompt
    assert list(LedgerCard().extraction_schema()["properties"]["lines"]["properties"]) == [
        f"{line:02d}" for line in LINES
    ]


# --- parse -------------------------------------------------------------------------------------


def test_grid_boxes_become_page_pixels():
    assert grid_to_bbox([100, 200, 300, 400], WIDTH, HEIGHT) == BBox(x0=170, y0=220, x1=510, y1=440)
    # rounded outwards, so a box never shrinks
    assert grid_to_bbox([1, 1, 2, 2], WIDTH, HEIGHT) == BBox(x0=1, y0=1, x1=4, y1=3)


def test_grid_boxes_outside_the_grid_are_clamped_to_the_page():
    assert grid_to_bbox([-5, 990, 1010, 1200], WIDTH, HEIGHT) == BBox(
        x0=0, y0=1089, x1=1700, y1=1100
    )


def test_a_box_that_encloses_nothing_gives_no_citation():
    assert grid_to_bbox([500, 500, 500, 600], WIDTH, HEIGHT) is None
    assert grid_to_bbox([1100, 0, 1200, 10], WIDTH, HEIGHT) is None  # both edges clamp to 1000
    data = _canned(PaymentMemo().extraction_schema(), {"value": "x", "box": [5, 5, 5, 5]})
    values = PaymentMemo().parse(PAGE, data, WIDTH, HEIGHT)
    assert all(v.citation is None and v.value == "x" for v in values)


@pytest.mark.parametrize("box", [[1, 2, 3], [1.5, 2, 3, 4], "1,2,3,4", None])
def test_a_malformed_box_raises(box):
    with pytest.raises(ValueError):
        grid_to_bbox(box, WIDTH, HEIGHT)


def test_parse_keeps_values_verbatim_cites_the_page_and_abstains_on_null():
    data = _canned(PaymentMemo().extraction_schema(), CELL)
    data["fields"]["amount"] = {"value": "1,O00.5", "box": [0, 0, 10, 10]}  # misprint kept
    data["fields"]["counterparty"] = {"value": "", "box": [0, 0, 10, 10]}
    data["fields"]["amount_words"] = {"value": None, "box": [0, 0, 10, 10]}
    values = {v.field_id: v for v in PaymentMemo().parse(PAGE, data, WIDTH, HEIGHT)}

    amount = values[memo_field_id(PAGE, "amount")]
    assert amount.value == "1,O00.5" and not amount.abstained
    assert amount.citation.page_id == PAGE
    assert amount.citation.bbox == BBox(x0=0, y0=0, x1=17, y1=11)
    blank = values[memo_field_id(PAGE, "counterparty")]
    assert blank.value == "" and not blank.abstained
    unreadable = values[memo_field_id(PAGE, "amount_words")]
    assert unreadable.value is None and unreadable.abstained


def test_ledger_values_are_keyed_by_the_line_number_given():
    data = _canned(LedgerCard().extraction_schema(), CELL)
    data["lines"]["07"]["debit"] = {"value": "58.16", "box": [0, 0, 10, 10]}
    values = {v.field_id: v.value for v in LedgerCard().parse(PAGE, data, WIDTH, HEIGHT)}
    assert values[ledger_line_id(PAGE, 7, "debit")] == "58.16"
    assert values[ledger_line_id(PAGE, 6, "debit")] == "1.00"


def _without_line(data: dict) -> dict:
    del data["lines"]["18"]
    return data


def _extra_column(data: dict) -> dict:
    data["lines"]["03"]["note"] = CELL
    return data


def _number_value(data: dict) -> dict:
    data["header"]["sheet_no"] = {"value": 36, "box": [0, 0, 10, 10]}
    return data


@pytest.mark.parametrize("damage", [_without_line, _extra_column, _number_value])
def test_an_incomplete_or_malformed_answer_raises_rather_than_returning_part(damage):
    data = damage(_canned(LedgerCard().extraction_schema(), CELL))
    with pytest.raises(ValueError):
        LedgerCard().parse(PAGE, data, WIDTH, HEIGHT)


def test_an_answer_that_is_not_an_object_raises():
    with pytest.raises(ValueError):
        PaymentMemo().parse(PAGE, ["not", "an", "object"], WIDTH, HEIGHT)
