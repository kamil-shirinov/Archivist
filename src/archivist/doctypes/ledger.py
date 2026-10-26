"""The one document family built so far (D2): running-balance ledger cards and payment memos.

Both ask for every field as a cell {"value", "box"}: the value exactly as printed, "" for a blank
cell, null when it can't be read, and a box on the 0–1000 grid that parse() turns into page pixels.
A response missing any field raises: a page is extracted whole or not at all.
"""

from __future__ import annotations

import math

from archivist.schema import (
    BBox,
    Citation,
    ExtractedValue,
    ledger_header_id,
    ledger_line_id,
    memo_field_id,
)

GRID = 1000
LINES = range(1, 19)  # pre-printed line numbers on every card (D9)
# Field order follows the page, top to bottom.
HEADER_TOP = ("account_no", "holder", "sheet_no", "brought_forward")
HEADER_BOTTOM = ("carried_forward",)
COLUMNS = ("date", "description", "debit", "credit", "balance")
MEMO_FIELDS = (
    "memo_no",
    "date",
    "account_no",
    "counterparty",
    "amount",
    "amount_words",
    "ledger_ref",
)

RULES = (
    "Rules for every value:\n"
    "- Copy it exactly as printed or written, character for character, including commas, "
    "leading zeros and punctuation. Never correct arithmetic, spelling or formatting, even when "
    "a figure looks wrong.\n"
    '- A blank cell is "" (an empty string).\n'
    "- If a value is there but can't be read (covered, smudged, torn), its value is null. Never "
    "guess.\n"
    "- Every value gets a box [x_min, y_min, x_max, y_max] on a 0-1000 grid, where (0, 0) is the "
    "top-left corner of the image and (1000, 1000) the bottom-right: a tight box around the "
    "value, or around the empty cell when it is blank."
)
# The grounding variant (strategy S1) follows Muse Spark's grounding guidance: it opens with a
# role and asks for the box around the ink, not the cell. Everything else is word for word S0.
GROUNDING_ROLE = "You are an object grounding expert. "
GROUNDED_RULES = RULES.replace(
    "a tight box around the value, or around the empty cell when it is blank.",
    "a tight box around the ink of the value itself, not around its cell; around the empty "
    "cell only when it is blank.",
)


def _prompt(body: str, grounding: bool) -> str:
    return GROUNDING_ROLE + body + GROUNDED_RULES if grounding else body + RULES

CELL_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {"type": ["string", "null"]},
        "box": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 4,
            "maxItems": 4,
        },
    },
    "required": ["value", "box"],
    "additionalProperties": False,
}


def _object(properties: dict[str, dict]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _cells(names: tuple[str, ...]) -> dict:
    return _object({name: CELL_SCHEMA for name in names})


def grid_to_bbox(box: object, width: int, height: int) -> BBox | None:
    """A 0–1000 grid box as page pixels, clamped to the page; None if it encloses nothing.

    The model may answer slightly outside the grid, so values are clamped first. Pixels are
    rounded outwards, so the box never shrinks.
    """
    if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int) for v in box)):
        raise ValueError(f"box must be four integers, got {box!r}")
    x0, y0, x1, y1 = (min(max(v, 0), GRID) for v in box)
    if x1 <= x0 or y1 <= y0:
        return None
    return BBox(
        x0=math.floor(x0 * width / GRID),
        y0=math.floor(y0 * height / GRID),
        x1=math.ceil(x1 * width / GRID),
        y1=math.ceil(y1 * height / GRID),
    )


def _value(page_id: str, field_id: str, cell: object, width: int, height: int) -> ExtractedValue:
    if not (isinstance(cell, dict) and set(cell) == {"value", "box"}):
        raise ValueError(f"{field_id}: expected {{value, box}}, got {cell!r}")
    value = cell["value"]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field_id}: value must be a string or null, got {value!r}")
    bbox = grid_to_bbox(cell["box"], width, height)
    return ExtractedValue(
        field_id=field_id,
        value=value,
        citation=None if bbox is None else Citation(page_id=page_id, bbox=bbox),
        abstained=value is None,
    )


def _section(data: object, key: str, names: tuple[str, ...]) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get(key), dict):
        raise ValueError(f"response has no {key!r} object")
    section = data[key]
    if set(section) != set(names):
        raise ValueError(f"{key!r} has keys {sorted(section)}, expected {sorted(names)}")
    return section


class LedgerCard:
    name = "ledger_card"
    description = (
        "A bank ledger card: one sheet of an account's running record, with an account number, "
        "holder and sheet number at the top and numbered lines of date, particulars, debit, "
        "credit and balance between a brought-forward and a carried-forward balance."
    )

    def field_ids(self, page_id: str) -> list[str]:
        return [
            *(ledger_header_id(page_id, name) for name in HEADER_TOP),
            *(ledger_line_id(page_id, line, column) for line in LINES for column in COLUMNS),
            *(ledger_header_id(page_id, name) for name in HEADER_BOTTOM),
        ]

    def extraction_prompt(self, grounding: bool = False) -> str:
        line_keys = f'"{LINES[0]:02d}" to "{LINES[-1]:02d}"'
        body = (
            "This is a scanned bank ledger card. Read every field on it.\n\n"
            '"header" holds:\n'
            "- account_no: the account number at the top\n"
            "- holder: the account holder's name\n"
            "- sheet_no: the sheet number at the top right\n"
            '- brought_forward: the balance on the "Brought forward" row, above line 1\n'
            '- carried_forward: the balance on the "Carried forward" row, below the last line\n\n'
            f'"lines" holds one entry for each of the {len(LINES)} lines, keyed {line_keys} by '
            "the line number pre-printed in the left-hand column (never by counting rows). Each "
            "line has:\n"
            "- date: the date\n"
            "- description: the particulars\n"
            "- debit: the amount in the Debit column\n"
            "- credit: the amount in the Credit column\n"
            "- balance: the amount in the Balance column\n"
            'Give every line, even an empty one, with "" for each blank cell.\n\n'
        )
        return _prompt(body, grounding)

    def extraction_schema(self) -> dict:
        lines = {f"{line:02d}": _cells(COLUMNS) for line in LINES}
        return _object({"header": _cells(HEADER_TOP + HEADER_BOTTOM), "lines": _object(lines)})

    def parse(self, page_id: str, data: object, width: int, height: int) -> list[ExtractedValue]:
        header = _section(data, "header", HEADER_TOP + HEADER_BOTTOM)
        lines = _section(data, "lines", tuple(f"{line:02d}" for line in LINES))
        cells: dict[str, object] = {}
        for name, cell in header.items():
            cells[ledger_header_id(page_id, name)] = cell
        for key, line in lines.items():
            if not isinstance(line, dict) or set(line) != set(COLUMNS):
                raise ValueError(f"line {key}: expected the columns {list(COLUMNS)}, got {line!r}")
            for column, cell in line.items():
                cells[ledger_line_id(page_id, int(key), column)] = cell
        return [_value(page_id, f, cells[f], width, height) for f in self.field_ids(page_id)]


class PaymentMemo:
    name = "payment_memo"
    description = (
        "A payment memorandum: a single payment slip with a memo number, date, account number, "
        "payee, the amount in figures and in words, and a reference to a ledger sheet and line."
    )

    def field_ids(self, page_id: str) -> list[str]:
        return [memo_field_id(page_id, name) for name in MEMO_FIELDS]

    def extraction_prompt(self, grounding: bool = False) -> str:
        body = (
            "This is a scanned payment memorandum. Read every field on it.\n\n"
            '"fields" holds:\n'
            "- memo_no: the memo number\n"
            "- date: the date\n"
            "- account_no: the account number\n"
            "- counterparty: the payee on the \"Pay to\" line\n"
            "- amount: the amount in figures, without the currency sign or any tick mark\n"
            "- amount_words: the amount in words\n"
            '- ledger_ref: the ledger reference, e.g. "Sheet 12 / Line 04" as printed\n\n'
        )
        return _prompt(body, grounding)

    def extraction_schema(self) -> dict:
        return _object({"fields": _cells(MEMO_FIELDS)})

    def parse(self, page_id: str, data: object, width: int, height: int) -> list[ExtractedValue]:
        fields = _section(data, "fields", MEMO_FIELDS)
        return [
            _value(page_id, memo_field_id(page_id, name), fields[name], width, height)
            for name in MEMO_FIELDS
        ]
