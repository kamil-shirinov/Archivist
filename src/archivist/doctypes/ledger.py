"""The one document family built so far (D2): running-balance ledger cards and payment memos.

Both ask for every field as a cell {"value", "box"}: the value exactly as printed, "" for a blank
cell, null when it can't be read, and a box on the 0–1000 grid that parse() turns into page pixels.
A response missing any field raises: a page is extracted whole or not at all.

The links between them are public, read as the checks read them: LedgerCard.cards and
LedgerCard.accounts (Card, Line), and PaymentMemo.postings (Memo, Posting).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from archivist.doctypes.words import parse_amount_words
from archivist.schema import (
    BBox,
    Citation,
    ExtractedValue,
    Flag,
    PageExtraction,
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
DIGIT_FIELDS = frozenset({"account_no", "memo_no"})  # compared as their digits
CITATIONS = "S0+ink"  # adopted for both types in results/citation_validation.json (D23)

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


# Blind re-reads (D4): the prompt names the document and the field, never the value read before.
# No digits appear in these prompts, so none can hint at a value.
LEDGER_REREAD = {
    "account_no": "the account number at the top of a bank ledger card",
    "holder": "the account holder's name at the top of a bank ledger card",
    "sheet_no": "the sheet number at the top right of a bank ledger card",
    "brought_forward": 'the balance on the "Brought forward" row of a bank ledger card',
    "carried_forward": 'the balance on the "Carried forward" row of a bank ledger card',
    "date": "the Date column of a ledger card line",
    "description": "the Particulars column of a ledger card line",
    "debit": "the Debit column of a ledger card line",
    "credit": "the Credit column of a ledger card line",
    "balance": "the Balance column of a ledger card line",
}
MEMO_REREAD = {
    "memo_no": "the memo number of a payment memorandum",
    "date": "the date of a payment memorandum",
    "account_no": "the account number on a payment memorandum",
    "counterparty": 'the payee on the "Pay to" line of a payment memorandum',
    "amount": "the amount in figures on a payment memorandum, without the currency sign or "
    "any tick mark",
    "amount_words": "the amount in words on a payment memorandum",
    "ledger_ref": "the ledger reference (a sheet and a line) on a payment memorandum",
}
REREAD_RULES = (
    "The image is a crop of a scanned page, centred on that value; parts of neighbouring cells "
    "or lines may show at its edges. Read only the value in the middle.\n"
    "- Copy it exactly as printed or written, character for character, including commas, "
    "leading zeros and punctuation. Never correct arithmetic, spelling or formatting.\n"
    '- If the cell is blank, the value is "" (an empty string).\n'
    "- If a value is there but can't be read (covered, smudged, torn), the value is null. Never "
    "guess."
)


def _reread_prompt(what: str) -> str:
    return f"Read {what}.\n\n{REREAD_RULES}"


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


class _Family:
    """What both types share: amounts and dates as a clerk writes them, and how readings compare."""

    money_fields: frozenset[str] = frozenset()
    citations = CITATIONS

    def money(self, text: str) -> Decimal | None:
        return money(text)

    def calendar_date(self, text: str) -> date | None:
        return calendar_date(text)

    def canonical(self, field_id: str, text: str) -> str:
        """The form two readings of a field are compared in (D22): money as an amount, dates as a
        calendar date, account and memo numbers as digits, the amount in words as its letters,
        anything else as text with spacing and case ignored.
        """
        if not text.strip():
            return ""
        kind = field_id.rsplit(":", 1)[-1]
        if kind in self.money_fields and (amount := money(text)) is not None:
            return str(amount)
        if kind == "date" and (day := calendar_date(text)) is not None:
            return day.isoformat()
        if kind in DIGIT_FIELDS and (digits := re.sub(r"\D", "", text)):
            return digits
        if kind == "amount_words" and (letters := re.sub(r"[^A-Z]", "", text.upper())):
            return letters
        return " ".join(text.split()).upper()


class LedgerCard(_Family):
    name = "ledger_card"
    description = (
        "A bank ledger card: one sheet of an account's running record, with an account number, "
        "holder and sheet number at the top and numbered lines of date, particulars, debit, "
        "credit and balance between a brought-forward and a carried-forward balance."
    )
    money_fields = frozenset({"brought_forward", "carried_forward", "debit", "credit", "balance"})

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

    def reread_prompt(self, field_id: str) -> str:
        """The blind re-read of one field from a crop of it; never mentions any value."""
        return _reread_prompt(LEDGER_REREAD[field_id.rsplit(":", 1)[-1]])

    def extraction_schema(self) -> dict:
        lines = {f"{line:02d}": _cells(COLUMNS) for line in LINES}
        return _object({"header": _cells(HEADER_TOP + HEADER_BOTTOM), "lines": _object(lines)})

    def checks(self, pages: list[PageExtraction]) -> list[Flag]:
        """Every card on its own, then each account's cards in sheet order."""
        flags: list[Flag] = []
        cards = [_read_card(p, flags) for p in pages if p.doc_type == self.name]
        for card in cards:
            flags += _card_checks(card)
        flags += _account_checks(_accounts(cards, flags))
        return flags

    def balanced(self, pages: Sequence[PageExtraction]) -> set[str]:
        """The fields some equation of the cards' own arithmetic holds for, every value in it read.

        The equations are a line's running balance (the balance before it, its debit, credit and
        balance), the carried forward against the last balance, and the next sheet's brought
        forward against it. The checks say only where values fail; this says where they hold, so
        values that add up can be told from values nothing could check.
        """
        out: set[str] = set()
        ignored: list[Flag] = []
        cards = [_read_card(p, ignored) for p in pages if p.doc_type == self.name]
        for card in cards:
            prev_id, prev = card.hdr("brought_forward"), card.brought
            for line in card.lines:
                if _adds_up(prev, line):
                    out |= {prev_id, line.ids["debit"], line.ids["credit"], line.ids["balance"]}
                prev_id, prev = line.ids["balance"], line.balance
            if _known(card.carried, prev) and card.carried == prev:
                out |= {prev_id, card.hdr("carried_forward")}
        for sheets in _accounts(cards, ignored).values():
            for a, b in zip(sheets, sheets[1:], strict=False):
                carries = _known(a.carried, b.brought) and a.carried == b.brought
                if b.sheet == a.sheet + 1 and carries:
                    out |= {a.hdr("carried_forward"), b.hdr("brought_forward")}
        return out

    def cards(self, pages: Sequence[PageExtraction]) -> dict[str, Card]:
        """Every card in the batch by page id, in batch order, read as the checks read it."""
        ignored: list[Flag] = []
        return {p.page_id: _read_card(p, ignored) for p in pages if p.doc_type == self.name}

    def accounts(self, cards: Sequence[Card]) -> dict[str, list[Card]]:
        """The cards of each account in sheet order, strays placed as the checks place them."""
        return _accounts(cards, [])

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


class PaymentMemo(_Family):
    name = "payment_memo"
    description = (
        "A payment memorandum: a single payment slip with a memo number, date, account number, "
        "payee, the amount in figures and in words, and a reference to a ledger sheet and line."
    )
    money_fields = frozenset({"amount"})

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

    def reread_prompt(self, field_id: str) -> str:
        """The blind re-read of one field from a crop of it; never mentions any value."""
        return _reread_prompt(MEMO_REREAD[field_id.rsplit(":", 1)[-1]])

    def extraction_schema(self) -> dict:
        return _object({"fields": _cells(MEMO_FIELDS)})

    def checks(self, pages: list[PageExtraction]) -> list[Flag]:
        """Each memo's words against its figures, then against the ledger line it cites."""
        flags: list[Flag] = []
        unflagged: list[Flag] = []  # the cards' own problems are LedgerCard's to report
        cards = [_read_card(p, unflagged) for p in pages if p.doc_type == LedgerCard.name]
        accounts = _accounts(cards, unflagged)
        for page in pages:
            if page.doc_type == self.name:
                memo = _read_memo(page, flags)
                flags += _words_check(memo)
                flags += _memo_ledger_check(memo, accounts)
        return flags

    def balanced(self, pages: Sequence[PageExtraction]) -> set[str]:
        """The memos whose figures and words agree, both read: the one equation a memo holds."""
        out: set[str] = set()
        ignored: list[Flag] = []
        for page in pages:
            if page.doc_type == self.name:
                memo = _read_memo(page, ignored)
                if _known(memo.amount, memo.words) and memo.amount == memo.words:
                    out |= {memo.ids["amount"], memo.ids["amount_words"]}
        return out

    def postings(
        self, pages: Sequence[PageExtraction], accounts: Mapping[str, list[Card]]
    ) -> dict[str, Posting]:
        """Where each memo in the batch is posted, by page id in batch order, as the checks find
        it in these accounts (LedgerCard.accounts).
        """
        ignored: list[Flag] = []
        memos = {p.page_id: _read_memo(p, ignored) for p in pages if p.doc_type == self.name}
        return {page_id: _posting_of(memo, accounts) for page_id, memo in memos.items()}

    def parse(self, page_id: str, data: object, width: int, height: int) -> list[ExtractedValue]:
        fields = _section(data, "fields", MEMO_FIELDS)
        return [
            _value(page_id, memo_field_id(page_id, name), fields[name], width, height)
            for name in MEMO_FIELDS
        ]


# --- Checks ------------------------------------------------------------------------------------
#
# Only rules a bank clerk would apply to the documents themselves (D24): a running balance adds
# up, a card carries forward its last balance and the next sheet brings it forward, a line is a
# debit or a credit, dates and cheque numbers only move forward, words agree with figures, and a
# memo matches the ledger line it cites. They read only the values they are given, which may be
# the extractor's or the blind re-reads (D26), never the page or ground truth. A card whose
# account number is misread is still placed by its holder and the gap it fills in an account's
# sheets, and a memo by the posting it cites, as a clerk would find them.
#
# A value of None was not read (abstained): it is already for review, so a check that needs it is
# skipped rather than flagged. A blank where a value must be, or text that isn't a value of its
# kind, is flagged. check is "arithmetic" for a card's own rules and anything unreadable,
# "words_figures" for a memo's words against its figures, and "crossdoc" for one document
# against another. A cross-document check that can't find what it needs flags the reference with
# a detail starting UNRESOLVABLE: the reference may be fine and the page simply not in the batch.

UNRESOLVABLE = "unresolvable: "
MEMO_LEAD = timedelta(days=30)  # how long before the posting a payment may be dated
_MONEY = re.compile(r"(-)?£?\s*(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(\s*(?:DR|OD))?", re.IGNORECASE)
_DATE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})")
_ACCOUNT = re.compile(r"[\d \-]+")
_CHEQUE = re.compile(r"CHQ\s*(\d+)", re.IGNORECASE)
_REF = re.compile(r"sheet\s*(\d+)\s*/\s*line\s*(\d+)\W*", re.IGNORECASE)


def money(text: str) -> Decimal | None:
    """Pounds and pence as a clerk writes them, "1,234.56"; overdrawn as "-", "DR" or "OD"."""
    match = _MONEY.fullmatch(text.strip())
    if match is None:
        return None
    sign, pounds, pence, overdrawn = match.groups()
    value = Decimal(pounds.replace(",", "") + "." + pence)
    return -value if sign or overdrawn else value


def calendar_date(text: str) -> date | None:
    """Day/month/year; a two-digit year is read as 19yy, as on paper records of the period."""
    match = _DATE.fullmatch(text.strip())
    if match is None:
        return None
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year if year >= 100 else 1900 + year, month, day)
    except ValueError:
        return None


def fmt(value: Decimal) -> str:
    return f"{value:,.2f}"


def _flag(field_id: str, check: str, detail: str, suggested: str | None = None) -> Flag:
    return Flag(field_id=field_id, check=check, detail=detail, suggested=suggested)


class _Reader:
    """A page's values by field id, parsed on request; what can't be parsed is flagged once."""

    def __init__(self, page: PageExtraction, flags: list[Flag]) -> None:
        self.page_id = page.page_id
        self.text = {v.field_id: None if v.abstained else v.value for v in page.values}
        self.flags = flags

    def raw(self, field_id: str) -> str | None:
        return self.text.get(field_id)

    def parse[T](
        self, field_id: str, parse: Callable[[str], T | None], kind: str, required: bool
    ) -> T | None:
        text = self.raw(field_id)
        if text is None:
            return None
        if not text.strip():
            if required:
                self.flags.append(_flag(field_id, "arithmetic", f"blank, but must hold {kind}"))
            return None
        value = parse(text)
        if value is None:
            self.flags.append(_flag(field_id, "arithmetic", f"{text!r} can't be read as {kind}"))
        return value

    def money(self, field_id: str, required: bool = True) -> Decimal | None:
        return self.parse(field_id, money, "an amount in pounds and pence", required)

    def date(self, field_id: str, required: bool = True) -> date | None:
        return self.parse(field_id, calendar_date, "a date", required)

    def account(self, field_id: str) -> str | None:
        return self.parse(
            field_id,
            lambda t: (re.sub(r"\D", "", t) or None) if _ACCOUNT.fullmatch(t.strip()) else None,
            "an account number",
            True,
        )

    def number(self, field_id: str) -> int | None:
        return self.parse(
            field_id, lambda t: int(t) if t.strip().isdigit() else None, "a number", True
        )


@dataclass
class Line:
    no: int
    ids: dict[str, str]  # column -> field id
    date: date | None
    date_text: str | None
    debit_text: str | None
    credit_text: str | None
    debit: Decimal | None  # 0 when blank, None when unread or unreadable
    credit: Decimal | None
    balance: Decimal | None
    cheque: int | None
    cheque_text: str


@dataclass
class Card:
    page_id: str
    account: str | None
    account_text: str | None
    holder: str | None
    sheet: int | None
    brought: Decimal | None
    carried: Decimal | None
    carried_text: str | None
    lines: list[Line]  # the used lines, in order
    by_no: dict[int, Line] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"sheet {self.sheet}"

    def hdr(self, name: str) -> str:
        return ledger_header_id(self.page_id, name)


_Card = Card  # the name tests/test_checks.py builds cards by


def _amount(reader: _Reader, field_id: str) -> Decimal | None:
    text = reader.raw(field_id)
    if text is not None and not text.strip():
        return Decimal(0)
    return reader.money(field_id)


def _read_card(page: PageExtraction, flags: list[Flag]) -> Card:
    r = _Reader(page, flags)
    pid = page.page_id
    lines = []
    for no in LINES:
        ids = {column: ledger_line_id(pid, no, column) for column in COLUMNS}
        texts = {column: r.raw(ids[column]) for column in COLUMNS}
        if all(t is not None and not t.strip() for t in texts.values()):
            continue  # an unused line
        cheque = _CHEQUE.fullmatch((texts["description"] or "").strip())
        lines.append(
            Line(
                no=no,
                ids=ids,
                date=r.date(ids["date"]),
                date_text=texts["date"],
                debit_text=texts["debit"],
                credit_text=texts["credit"],
                debit=_amount(r, ids["debit"]),
                credit=_amount(r, ids["credit"]),
                balance=r.money(ids["balance"]),
                cheque=int(cheque.group(1)) if cheque else None,
                cheque_text=cheque.group(0) if cheque else "",
            )
        )
    card = Card(
        page_id=pid,
        account=r.account(ledger_header_id(pid, "account_no")),
        account_text=r.raw(ledger_header_id(pid, "account_no")),
        holder=_holder(r.raw(ledger_header_id(pid, "holder"))),
        sheet=r.number(ledger_header_id(pid, "sheet_no")),
        brought=r.money(ledger_header_id(pid, "brought_forward")),
        carried=r.money(ledger_header_id(pid, "carried_forward"), required=False),
        carried_text=r.raw(ledger_header_id(pid, "carried_forward")),
        lines=lines,
    )
    card.by_no = {line.no: line for line in lines}
    return card


def _movement(line: Line) -> str:
    return f"{fmt(line.debit)} + {fmt(line.credit)}"


def _known(*values: object) -> bool:
    return all(v is not None for v in values)


def _adds_up(prev: Decimal | None, line: Line, balance: Decimal | None = None) -> bool | None:
    """Whether prev − debit + credit = balance (the line's own unless given); None if unknown."""
    balance = line.balance if balance is None else balance
    if not _known(prev, line.debit, line.credit, balance):
        return None
    return prev - line.debit + line.credit == balance


def _implied_amount(prev: Decimal, line: Line) -> list[Flag]:
    """Flags on the line's amount column(s), suggesting the amount its balance implies."""
    change = line.balance - prev
    detail = (
        f"line {line.no:02d}: {fmt(prev)} − {_movement(line)} = "
        f"{fmt(prev - line.debit + line.credit)}, but the balance reads {fmt(line.balance)}. "
        "Only this line fails, so its amount or balance is misread, or the clerk's arithmetic "
        f"was wrong; the balances imply a {'credit' if change > 0 else 'debit'} of "
        f"{fmt(abs(change))}"
    )
    debit_blank = line.debit_text is not None and not line.debit_text.strip()
    credit_blank = line.credit_text is not None and not line.credit_text.strip()
    implied = {"debit": -change, "credit": change}
    columns = [c for c, blank in (("debit", debit_blank), ("credit", credit_blank)) if not blank]
    flags = []
    for column in columns or ["debit", "credit"]:
        value = implied[column]
        sure = value > 0 and len(columns) < 2
        flags.append(_flag(line.ids[column], "arithmetic", detail, fmt(value) if sure else None))
    return flags


def _balance_checks(card: Card) -> list[Flag]:
    """The running balance, line by line from brought forward, then the carried forward.

    A misread balance breaks two equations, its own and the next (or the carried forward), and
    one value mends both: that balance is flagged with the value. A single broken equation is the
    line's amount or balance, misread or miswritten by the clerk; its amount is flagged with the
    amount the balances imply, and its balance too.
    """
    flags: list[Flag] = []
    lines = card.lines
    before = [card.brought, *(line.balance for line in lines)]
    closing_explained = False
    k = 0
    while k < len(lines):
        line, prev = lines[k], before[k]
        if _adds_up(prev, line) is not False:
            k += 1
            continue
        mended = prev - line.debit + line.credit
        if k + 1 < len(lines):
            nxt = lines[k + 1]
            mends_next = _adds_up(line.balance, nxt) is False and _adds_up(mended, nxt) is True
            next_what = f"line {nxt.no:02d}"
        else:
            mends_next = card.carried is not None and card.carried == mended
            next_what = "the carried forward"
        if mends_next:
            detail = (
                f"line {line.no:02d}: {fmt(prev)} − {_movement(line)} = {fmt(mended)}, but the "
                f"balance reads {fmt(line.balance)}; {fmt(mended)} also makes {next_what} add "
                "up, so this balance is most likely misread"
            )
            flags.append(_flag(line.ids["balance"], "arithmetic", detail, fmt(mended)))
            closing_explained = k + 1 == len(lines)
            k += 2
            continue
        amount_flags = _implied_amount(prev, line)
        flags += amount_flags
        flags.append(_flag(line.ids["balance"], "arithmetic", amount_flags[0].detail))
        k += 1

    last = before[-1]
    carried_id = card.hdr("carried_forward")
    if closing_explained or last is None:
        return flags
    if card.carried_text is not None and not card.carried_text.strip():
        detail = f"the carried forward is blank; the last balance is {fmt(last)}"
        flags.append(_flag(carried_id, "arithmetic", detail, fmt(last)))
    elif card.carried is not None and card.carried != last:
        detail = f"carried forward {fmt(card.carried)}, but the last balance is {fmt(last)}"
        flags.append(_flag(carried_id, "arithmetic", detail, fmt(last)))
    return flags


def _one_side_checks(card: Card) -> list[Flag]:
    flags = []
    for line in card.lines:
        texts = (line.debit_text, line.credit_text)
        if any(t is None for t in texts):
            continue
        filled = [bool(t.strip()) for t in texts]
        if filled.count(True) == 1:
            continue
        which = "both a debit and a credit" if all(filled) else "neither a debit nor a credit"
        detail = f"line {line.no:02d} has {which}; a line is one or the other"
        flags += [_flag(line.ids[c], "arithmetic", detail) for c in ("debit", "credit")]
    return flags


def _descents[T](
    items: Sequence[tuple[str, T, str]], what: str, check: str = "arithmetic"
) -> list[Flag]:
    """Flags where a sequence that must never decrease does: (field id, key, as printed) items.

    The value out of line with its neighbours is flagged: the earlier one if it stands above
    both, the later one if it stands below both, both if that can't be told.
    """
    flags = []
    for k in range(1, len(items)):
        (prev_id, prev, prev_text), (this_id, this, this_text) = items[k - 1], items[k]
        if this >= prev:
            continue
        prev_high = k >= 2 and items[k - 2][1] <= this
        this_low = k + 1 < len(items) and items[k + 1][1] >= prev
        if prev_high != this_low:
            blame = [prev_id] if prev_high else [this_id]
        else:
            blame = [prev_id, this_id]
        detail = f"{what} goes backwards: {prev_text} then {this_text}"
        flags += [_flag(b, check, detail) for b in blame]
    return flags


def date_items(card: Card) -> list[tuple[str, date, str]]:
    return [(ln.ids["date"], ln.date, ln.date_text) for ln in card.lines if ln.date is not None]


def cheque_items(card: Card) -> list[tuple[str, int, str]]:
    return [
        (ln.ids["description"], ln.cheque, ln.cheque_text)
        for ln in card.lines
        if ln.cheque is not None
    ]


def _card_checks(card: Card) -> list[Flag]:
    return [
        *_balance_checks(card),
        *_one_side_checks(card),
        *_descents(date_items(card), "the date"),
        *_descents(cheque_items(card), "the cheque number"),
    ]


def _cross_sequence[T](
    cards: Sequence[Card], items_of: Callable[[Card], list[tuple[str, T, str]]], what: str
) -> list[Flag]:
    """Across an account's cards in sheet order: each card starts no earlier than the last ended.

    When card B starts before card A ends, the card out of line with its other neighbour is
    blamed: B if A agrees with the card after B, A if the card before A agrees with B, else both.
    Only the blamed card's values that are out of line are flagged.
    """
    seq = [(card, items) for card in cards if (items := items_of(card))]
    flags = []
    for k in range(1, len(seq)):
        (a, a_items), (b, b_items) = seq[k - 1], seq[k]
        a_last, b_first = a_items[-1], b_items[0]
        if b_first[1] >= a_last[1]:
            continue
        b_odd = k + 1 < len(seq) and seq[k + 1][1][0][1] >= a_last[1]  # A agrees with C
        a_odd = k >= 2 and seq[k - 2][1][-1][1] <= b_first[1]  # the card before A agrees with B
        blame_b, blame_a = (b_odd, a_odd) if a_odd != b_odd else (True, True)
        detail = (
            f"{b.label} starts with {what} {b_first[2]}, before {a.label} ends with "
            f"{a_last[2]}; {what} never goes backwards along an account"
        )
        if blame_b:
            flags += [_flag(f, "crossdoc", detail) for f, v, _ in b_items if v < a_last[1]]
        if blame_a:
            flags += [_flag(f, "crossdoc", detail) for f, v, _ in a_items if v > b_first[1]]
    return flags


def _carry_check(a: Card, b: Card) -> list[Flag]:
    """Sheet b, the one after a, brings forward what a carried forward."""
    if not _known(a.carried, b.brought) or a.carried == b.brought:
        return []
    a_ok = bool(a.lines) and a.carried == a.lines[-1].balance
    b_ok = bool(b.lines) and _adds_up(b.brought, b.lines[0]) is True
    detail = f"{a.label} carries forward {fmt(a.carried)}, but {b.label} brings forward " + fmt(
        b.brought
    )
    a_id, b_id = a.hdr("carried_forward"), b.hdr("brought_forward")
    if a_ok and not b_ok:
        return [_flag(b_id, "crossdoc", detail, fmt(a.carried))]
    if b_ok and not a_ok:
        return [_flag(a_id, "crossdoc", detail, fmt(b.brought))]
    return [_flag(a_id, "crossdoc", detail), _flag(b_id, "crossdoc", detail)]


def _holder(text: str | None) -> str | None:
    if text is None:
        return None
    return " ".join(text.split()).upper() or None


def _accounts(cards: Sequence[Card], flags: list[Flag]) -> dict[str, list[Card]]:
    """The cards of each account, in sheet order; cards without a sheet number are left out.

    A card whose account number no other card shares (or can't be read) joins the one account
    held by the same holder that has the sheets either side of it, or one of them, and not its
    own: its account number is flagged with that account's. A group that no card reads the account
    of (the moves can leave one) has no account number to flag with, so a card whose account
    number is to be flagged does not join it.
    """
    accounts: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        if card.sheet is not None:
            accounts[card.account or ""].append(card)
    strays = [c for key, group in accounts.items() for c in group if not key or len(group) == 1]
    for card in strays:
        homes = [
            key
            for key, group in accounts.items()
            if key
            and card not in group
            and card.holder is not None
            and all(c.holder == card.holder for c in group)
            and card.sheet not in {c.sheet for c in group}
            and any(abs(c.sheet - card.sheet) == 1 for c in group)
        ]
        if len(homes) != 1:
            continue
        home = accounts[homes[0]]
        if card.account_text is not None and not any(c.account == homes[0] for c in home):
            continue
        accounts[card.account or ""].remove(card)
        detail = (
            f"{card.label} of {card.holder} reads account {card.account_text!r}, but it fills the "
            f"gap in account {homes[0]}'s sheets, held by the same holder"
        )
        if card.account_text is not None:
            printed = next(c.account_text for c in home if c.account == homes[0])
            flags.append(_flag(card.hdr("account_no"), "crossdoc", detail, printed))
        home.append(card)
    return {
        key: sorted(group, key=lambda c: (c.sheet, c.page_id))
        for key, group in sorted(accounts.items())
        if key and group
    }


def _account_checks(accounts: dict[str, list[Card]]) -> list[Flag]:
    flags = []
    for sheets in accounts.values():
        for a, b in zip(sheets, sheets[1:], strict=False):
            if b.sheet == a.sheet + 1:  # across a missing sheet the balances can't be compared
                flags += _carry_check(a, b)
        flags += _cross_sequence(sheets, date_items, "the date")
        flags += _cross_sequence(sheets, cheque_items, "the cheque number")
    return flags


@dataclass
class Memo:
    ids: dict[str, str]  # field name -> field id
    raw: dict[str, str | None]
    account: str | None
    date: date | None
    amount: Decimal | None
    words: Decimal | None
    ref: tuple[int, int] | None  # (sheet, line)


def _ref(text: str) -> tuple[int, int] | None:
    match = _REF.fullmatch(text.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def _read_memo(page: PageExtraction, flags: list[Flag]) -> Memo:
    r = _Reader(page, flags)
    ids = {name: memo_field_id(page.page_id, name) for name in MEMO_FIELDS}

    def words(text: str) -> Decimal | None:
        try:
            return parse_amount_words(text)
        except ValueError:
            return None

    # The figures are read without flagging: the words check says what they should be.
    amount_text = r.raw(ids["amount"])
    return Memo(
        ids=ids,
        raw={name: r.raw(ids[name]) for name in MEMO_FIELDS},
        account=r.account(ids["account_no"]),
        date=r.date(ids["date"]),
        amount=None if amount_text is None else money(amount_text),
        words=r.parse(ids["amount_words"], words, "an amount in words", True),
        ref=r.parse(ids["ledger_ref"], _ref, 'a ledger reference "Sheet N / Line M"', True),
    )


def _words_check(memo: Memo) -> list[Flag]:
    figures = memo.raw["amount"]
    amount_id, words_id = memo.ids["amount"], memo.ids["amount_words"]
    if figures is None:
        return []
    said = "" if memo.words is None else f"; the words say {fmt(memo.words)}"
    suggestion = None if memo.words is None else fmt(memo.words)
    if not figures.strip():
        detail = "the amount in figures is blank" + said
        return [_flag(amount_id, "words_figures", detail, suggestion)]
    if memo.amount is None:
        detail = f"{figures!r} can't be read as an amount in pounds and pence" + said
        return [_flag(amount_id, "words_figures", detail, suggestion)]
    if memo.words is None or memo.words == memo.amount:
        return []
    detail = f"the figures say {fmt(memo.amount)}, but the words say {fmt(memo.words)}"
    return [
        _flag(amount_id, "words_figures", detail, suggestion),
        _flag(words_id, "words_figures", detail),
    ]


def _posting(memo: Memo, accounts: dict[str, list[Card]]) -> tuple[str, Card] | None:
    """The one card in the batch whose cited sheet and line debit the memo's amount."""
    sheet, line_no = memo.ref
    amounts = {a for a in (memo.amount, memo.words) if a is not None}
    found = [
        (key, card)
        for key, group in accounts.items()
        for card in group
        if card.sheet == sheet
        and (line := card.by_no.get(line_no)) is not None
        and line.debit in amounts
    ]
    return found[0] if len(found) == 1 else None


def _memo_ledger_check(memo: Memo, accounts: dict[str, list[Card]]) -> list[Flag]:
    """The memo against the line it cites: the same amount, debited no more than 30 days later.

    If the memo's account has no such sheet in the batch, or its account can't be read, the one
    card whose cited line debits the memo's amount is taken as the posting and the memo's account
    number is flagged with that card's. A posting in a group that no card reads the account of
    (the moves in _accounts can leave one) has no account number to flag with: the memo then has
    no card, as below.
    """
    if memo.ref is None or (memo.account is None and memo.raw["account_no"] is None):
        return []
    sheet, line_no = memo.ref
    ref_id = memo.ids["ledger_ref"]
    account = memo.account
    matches = [c for c in accounts.get(account or "", []) if c.sheet == sheet]
    flags = []
    posting = None if matches else _posting(memo, accounts)
    if posting and any(c.account == posting[0] for c in accounts[posting[0]]):
        account, card = posting
        detail = (
            f"the memo's account reads {memo.raw['account_no']!r}, but sheet {sheet} line "
            f"{line_no:02d} of account {account} debits the memo's amount"
        )
        printed = next(c.account_text for c in accounts[account] if c.account == account)
        flags.append(_flag(memo.ids["account_no"], "crossdoc", detail, printed))
        matches = [card]
    where = f"sheet {sheet} of account {account or memo.raw['account_no']}"
    if len(matches) != 1:
        found = "no card" if not matches else f"{len(matches)} cards"
        return [_flag(ref_id, "crossdoc", f"{UNRESOLVABLE}{found} for {where} in this batch")]
    line = matches[0].by_no.get(line_no)
    if line is None:
        detail = f"{UNRESOLVABLE}line {line_no:02d} of {where} is empty or not on the card"
        return [_flag(ref_id, "crossdoc", detail)]

    cited = f"{where}, line {line_no:02d}"
    if memo.amount is not None and line.debit is not None and line.credit is not None:
        if line.debit == 0:
            detail = f"the memo pays {fmt(memo.amount)}, but {cited} is not a debit"
            flags += [_flag(memo.ids["amount"], "crossdoc", detail)]
            flags += [_flag(line.ids[c], "crossdoc", detail) for c in ("debit", "credit")]
        elif line.debit != memo.amount:
            detail = f"the memo pays {fmt(memo.amount)}, but {cited} debits {fmt(line.debit)}"
            if memo.words == line.debit:  # the memo's own words side with the ledger
                flags.append(_flag(memo.ids["amount"], "crossdoc", detail + ", as its words do"))
            else:
                flags += [
                    _flag(memo.ids["amount"], "crossdoc", detail),
                    _flag(line.ids["debit"], "crossdoc", detail),
                ]
    if memo.date is not None and line.date is not None:
        if memo.date > line.date:
            problem = "after the payment was posted"
        elif line.date - memo.date > MEMO_LEAD:
            problem = f"more than {MEMO_LEAD.days} days before it was posted"
        else:
            problem = None
        if problem:
            detail = (
                f"the memo is dated {memo.raw['date']}, {problem} on {cited} ({line.date_text})"
            )
            flags += [
                _flag(memo.ids["date"], "crossdoc", detail),
                _flag(line.ids["date"], "crossdoc", detail),
            ]
    return flags


@dataclass(frozen=True)
class Posting:
    """Where a memo's ledger reference leads, found as _memo_ledger_check finds it."""

    memo: Memo
    account: str | None  # the account group the line was found in
    card: Card | None
    line: Line | None
    by_amount: bool  # found by the amount the line debits, not by the memo's own account
    unresolved: str | None  # why no line was found


def _posting_of(memo: Memo, accounts: Mapping[str, list[Card]]) -> Posting:
    if memo.ref is None:
        return Posting(memo, None, None, None, False, "no ledger reference can be read")
    if memo.account is None and memo.raw["account_no"] is None:
        return Posting(memo, None, None, None, False, "the memo's account was not read")
    sheet, line_no = memo.ref
    account = memo.account
    matches = [c for c in accounts.get(account or "", []) if c.sheet == sheet]
    by_amount = False
    if not matches:
        found = _posting(memo, accounts)
        if found and any(c.account == found[0] for c in accounts[found[0]]):
            (account, card), by_amount = found, True
            matches = [card]
    if len(matches) != 1:
        found = "no card" if not matches else f"{len(matches)} cards"
        where = f"sheet {sheet} of account {account or memo.raw['account_no']}"
        return Posting(memo, account, None, None, by_amount, f"{found} for {where}")
    card = matches[0]
    line = card.by_no.get(line_no)
    if line is None:
        why = f"line {line_no:02d} of sheet {sheet} is empty or not on the card"
        return Posting(memo, account, card, None, by_amount, why)
    return Posting(memo, account, card, line, by_amount, None)
