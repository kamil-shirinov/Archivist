"""Clean page renderer: ledger cards and payment memos with exact ground-truth boxes.

Pages come out pristine: no noise, skew or artefacts (degradation is a later stage). A field's
box is the ImageDraw.textbbox of its entry padded by PAD; a blank debit or credit cell gets the
cell interior instead, kept clear of the ruling. All randomness comes from the rng passed in.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import itertools
import math
import random
from decimal import Decimal
from pathlib import Path
from typing import Literal, NamedTuple

from PIL import Image, ImageDraw, ImageFont

from archivist.schema import (
    LEDGER_COLUMNS,
    LEDGER_HEADER_NAMES,
    MEMO_FIELD_NAMES,
    BBox,
    FieldGT,
    PageGT,
    ledger_header_id,
    ledger_line_id,
    memo_field_id,
)
from archivist.synth.world import BANKS, LedgerCard, Memo, World, generate_world

FONTS_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
FORM_FONT = "librebaskerville/LibreBaskerville[wght].ttf"
FORM_FONT_ITALIC = "librebaskerville/LibreBaskerville-Italic[wght].ttf"

PAPER = (246, 242, 230)
FORM_INK = (86, 108, 96)  # green-grey
RULE_RED = (190, 62, 58)
TYPED_INK = (30, 30, 34)
HAND_INK = (26, 36, 74)  # blue-black

PAD = 2  # added around every text box
JITTER = 3  # max random offset of an entry, each axis
INSET = 4  # gap kept between ruling and a cell's interior
MIN_SIZE = 10


class Fill(NamedTuple):
    kind: Literal["typed", "handwritten"]
    font: str
    size: int  # starting size; shrunk until the entry fits its cell
    ink: tuple[int, int, int]


FILLS = (
    Fill("typed", "courierprime/CourierPrime-Regular.ttf", 28, TYPED_INK),
    Fill("typed", "specialelite/SpecialElite-Regular.ttf", 28, TYPED_INK),
    Fill("handwritten", "homemadeapple/HomemadeApple-Regular.ttf", 28, HAND_INK),
    Fill("handwritten", "nanumpenscript/NanumPenScript-Regular.ttf", 40, HAND_INK),
)


def _pick_fill(rng: random.Random) -> Fill:
    kind = "typed" if rng.random() < 0.5 else "handwritten"
    return rng.choice([fill for fill in FILLS if fill.kind == kind])


def _money(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _date(day: dt.date) -> str:
    return day.strftime("%d/%m/%y")


@functools.cache
def _font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(
        str(FONTS_DIR / name), size, layout_engine=ImageFont.Layout.BASIC
    )
    if weight is not None:
        font.set_variation_by_axes([weight])
    return font


class _Box(NamedTuple):
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def inset(self, d: int) -> _Box:
        return _Box(self.x0 + d, self.y0 + d, self.x1 - d, self.y1 - d)


def _print(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    size: int,
    anchor: str = "ls",
    weight: int | None = None,
    italic: bool = False,
) -> None:
    """Pre-printed form text in the form's own ink."""
    font = _font(FORM_FONT_ITALIC if italic else FORM_FONT, size, weight)
    draw.text(xy, text, font=font, fill=FORM_INK, anchor=anchor)


def _fit(fill: Fill, text: str, region: _Box) -> ImageFont.FreeTypeFont:
    for size in range(fill.size, MIN_SIZE - 1, -1):
        font = _font(fill.font, size)
        left, top, right, bottom = font.getbbox(text, anchor="ls")
        if right - left <= region.width and bottom - top <= region.height:
            return font
    raise ValueError(f"{text!r} does not fit {region.width}x{region.height} px in {fill.font}")


class _Writer:
    """Writes the clerk's entries in one fill style and records a FieldGT for each."""

    def __init__(self, draw: ImageDraw.ImageDraw, fill: Fill, rng: random.Random) -> None:
        self.draw = draw
        self.fill = fill
        self.rng = rng
        self.fields: list[FieldGT] = []

    def entry(
        self, field_id: str, text: str, cell: _Box, align: Literal["left", "right"] = "left"
    ) -> None:
        # Room for the jitter and the padding stays inside the interior, so padded boxes
        # never reach the ruling or a neighbouring cell.
        region = cell.inset(INSET + JITTER + PAD)
        font = _fit(self.fill, text, region)
        left, top, right, bottom = font.getbbox(text, anchor="ls")
        _, ref_top, _, ref_bottom = font.getbbox("Hg", anchor="ls")
        baseline = region.y0 + (region.height - (ref_bottom - ref_top)) // 2 - ref_top
        baseline = max(region.y0 - top, min(baseline, region.y1 - bottom))
        x = region.x0 - left if align == "left" else region.x1 - right
        xy = (
            x + self.rng.randint(-JITTER, JITTER),
            baseline + self.rng.randint(-JITTER, JITTER),
        )
        self.draw.text(xy, text, font=font, fill=self.fill.ink, anchor="ls")
        left, top, right, bottom = self.draw.textbbox(xy, text, font=font, anchor="ls")
        bbox = BBox(
            x0=math.floor(left) - PAD,
            y0=math.floor(top) - PAD,
            x1=math.ceil(right) + PAD,
            y1=math.ceil(bottom) + PAD,
        )
        self.fields.append(FieldGT(field_id=field_id, printed=text, bbox=bbox))

    def blank(self, field_id: str, cell: _Box) -> None:
        interior = cell.inset(INSET)
        bbox = BBox(x0=interior.x0, y0=interior.y0, x1=interior.x1, y1=interior.y1)
        self.fields.append(FieldGT(field_id=field_id, printed="", bbox=bbox))


# --- ledger card ------------------------------------------------------------------------

CARD_SIZE = (1700, 1100)
CARD_ROWS = 18
COL_X = (60, 140, 310, 920, 1160, 1400, 1640)
COL_TITLES = ("Line", "Date", "Particulars", "Debit", "Credit", "Balance")
LINE, DATE, PARTICULARS, DEBIT, CREDIT, BALANCE = range(6)
TABLE_TOP = 160
HEAD_H = 38
ROW_H = 43
HEADER_LINE_Y = 136
CARD_HEADER = {
    # name: (label, label x, entry cell)
    "account_no": ("Account No.", 60, _Box(210, 92, 470, HEADER_LINE_Y)),
    "holder": ("Holder", 510, _Box(600, 92, 1220, HEADER_LINE_Y)),
    "sheet_no": ("Sheet No.", 1260, _Box(1380, 92, 1640, HEADER_LINE_Y)),
}


def _row_top(row: int) -> int:
    """Row 0 is "Brought forward", rows 1–18 the pre-numbered lines, row 19 "Carried forward"."""
    return TABLE_TOP + HEAD_H + row * ROW_H


def _card_cell(row: int, col: int) -> _Box:
    return _Box(COL_X[col], _row_top(row), COL_X[col + 1], _row_top(row + 1))


def _card_form(draw: ImageDraw.ImageDraw, card: LedgerCard) -> None:
    width = CARD_SIZE[0]
    _print(draw, (width // 2, 22), card.bank, 38, anchor="mt", weight=700)
    _print(draw, (width // 2, 68), f"{card.branch} Branch", 20, anchor="mt", italic=True)
    for label, label_x, cell in CARD_HEADER.values():
        _print(draw, (label_x, HEADER_LINE_Y - 4), label, 22)
        draw.line((cell.x0, HEADER_LINE_Y, cell.x1, HEADER_LINE_Y), fill=FORM_INK, width=1)

    rows = CARD_ROWS + 2
    bottom = _row_top(rows)
    for title, x0, x1 in zip(COL_TITLES, COL_X, COL_X[1:], strict=False):
        _print(draw, ((x0 + x1) // 2, TABLE_TOP + HEAD_H // 2), title, 20, anchor="mm")
    draw.line((COL_X[0], TABLE_TOP, COL_X[-1], TABLE_TOP), fill=FORM_INK, width=2)
    draw.line((COL_X[0], _row_top(0), COL_X[-1], _row_top(0)), fill=FORM_INK, width=2)
    for row in range(1, rows):
        y = _row_top(row)
        draw.line((COL_X[0], y, COL_X[-1], y), fill=FORM_INK, width=1)
    draw.line((COL_X[0], bottom, COL_X[-1], bottom), fill=FORM_INK, width=2)
    for col, x in enumerate(COL_X):
        if col >= DEBIT:  # either side of every money column
            draw.line((x, TABLE_TOP, x, bottom), fill=RULE_RED, width=2)
        else:
            draw.line((x, TABLE_TOP, x, bottom), fill=FORM_INK, width=2 if col == 0 else 1)

    for row, text in ((0, "Brought forward"), (rows - 1, "Carried forward")):
        cell = _card_cell(row, PARTICULARS)
        _print(draw, (cell.x0 + 14, (cell.y0 + cell.y1) // 2), text, 20, anchor="lm", italic=True)
    for line_no in range(1, CARD_ROWS + 1):
        cell = _card_cell(line_no, LINE)
        _print(draw, ((cell.x0 + cell.x1) // 2, (cell.y0 + cell.y1) // 2), str(line_no), 18, "mm")


def render_card(card: LedgerCard, rng: random.Random) -> tuple[Image.Image, PageGT]:
    """Landscape 200 DPI ledger card. PageGT.source_errors is left empty for the caller."""
    if [line.line_no for line in card.lines] != list(range(1, CARD_ROWS + 1)):
        raise ValueError(f"{card.doc_id}: the printed form has exactly {CARD_ROWS} lines")
    fill = _pick_fill(rng)
    image = Image.new("RGB", CARD_SIZE, PAPER)
    draw = ImageDraw.Draw(image)
    _card_form(draw, card)

    writer = _Writer(draw, fill, rng)
    doc = card.doc_id
    header_values = {
        "account_no": card.account_no,
        "holder": card.holder,
        "sheet_no": str(card.sheet_no),
    }
    for name, (_, _, cell) in CARD_HEADER.items():
        writer.entry(ledger_header_id(doc, name), header_values[name], cell)
    writer.entry(
        ledger_header_id(doc, "brought_forward"),
        _money(card.brought_forward),
        _card_cell(0, BALANCE),
        "right",
    )
    for line in card.lines:
        row = line.line_no
        writer.entry(ledger_line_id(doc, row, "date"), _date(line.date), _card_cell(row, DATE))
        writer.entry(
            ledger_line_id(doc, row, "description"), line.description, _card_cell(row, PARTICULARS)
        )
        for column, col, amount in (("debit", DEBIT, line.debit), ("credit", CREDIT, line.credit)):
            field_id = ledger_line_id(doc, row, column)
            if amount is None:
                writer.blank(field_id, _card_cell(row, col))
            else:
                writer.entry(field_id, _money(amount), _card_cell(row, col), "right")
        writer.entry(
            ledger_line_id(doc, row, "balance"),
            _money(line.balance),
            _card_cell(row, BALANCE),
            "right",
        )
    writer.entry(
        ledger_header_id(doc, "carried_forward"),
        _money(card.carried_forward),
        _card_cell(CARD_ROWS + 1, BALANCE),
        "right",
    )
    return image, _page_gt(doc, "ledger", image, writer.fields)


# --- payment memorandum -----------------------------------------------------------------

MEMO_SIZE = (1100, 1400)
AMOUNT_BOX = _Box(430, 535, 760, 605)
MEMO_FIELDS = {
    # name: (label, label x, label baseline, entry cell, underlined)
    "memo_no": ("Memo No.", 110, 296, _Box(255, 248, 520, 300), True),
    "date": ("Date", 590, 296, _Box(660, 248, 990, 300), True),
    "account_no": ("Account No.", 110, 386, _Box(290, 338, 640, 390), True),
    "counterparty": ("Pay to", 110, 476, _Box(210, 428, 990, 480), True),
    "amount": ("Amount in figures", 110, 586, AMOUNT_BOX, False),
    "amount_words": ("Amount in words", 110, 676, _Box(110, 690, 990, 750), True),
    "ledger_ref": ("Ledger ref.", 110, 846, _Box(270, 798, 640, 850), True),
}
AUTHORISED_Y = 1064


def _memo_form(draw: ImageDraw.ImageDraw, bank: str) -> None:
    width, height = MEMO_SIZE
    draw.rectangle((50, 50, width - 51, height - 51), outline=FORM_INK, width=2)
    draw.rectangle((58, 58, width - 59, height - 59), outline=FORM_INK, width=1)
    _print(draw, (width // 2, 100), bank, 34, anchor="mt", weight=700)
    _print(draw, (width // 2, 155), "Payment Memorandum", 28, anchor="mt", italic=True)
    draw.line((110, 210, width - 110, 210), fill=FORM_INK, width=2)
    for label, label_x, baseline, cell, underlined in MEMO_FIELDS.values():
        _print(draw, (label_x, baseline), label, 22)
        if underlined:
            draw.line((cell.x0, cell.y1, cell.x1, cell.y1), fill=FORM_INK, width=1)
    _print(draw, (AMOUNT_BOX.x0 - 14, MEMO_FIELDS["amount"][2]), "£", 30, anchor="rs")
    draw.rectangle(
        (AMOUNT_BOX.x0, AMOUNT_BOX.y0, AMOUNT_BOX.x1, AMOUNT_BOX.y1), outline=FORM_INK, width=2
    )
    _print(draw, (110, AUTHORISED_Y - 4), "Authorised by", 22)
    draw.line((290, AUTHORISED_Y, 760, AUTHORISED_Y), fill=FORM_INK, width=1)
    _print(
        draw,
        (width // 2, height - 120),
        "This memorandum is to be retained with the ledger card.",
        16,
        anchor="ms",
        italic=True,
    )


def render_memo(
    memo: Memo, rng: random.Random, *, bank: str | None = None
) -> tuple[Image.Image, PageGT]:
    """Portrait payment memorandum. render_world passes the bank of the referenced card;
    without it a bank is drawn from rng. PageGT.source_errors is left empty for the caller."""
    fill = _pick_fill(rng)
    if bank is None:
        bank = rng.choice(BANKS)
    image = Image.new("RGB", MEMO_SIZE, PAPER)
    draw = ImageDraw.Draw(image)
    _memo_form(draw, bank)

    writer = _Writer(draw, fill, rng)
    values = {
        "memo_no": memo.memo_no,
        "date": _date(memo.date),
        "account_no": memo.account_no,
        "counterparty": memo.counterparty,
        "amount": _money(memo.amount),
        "amount_words": memo.amount_words,
        "ledger_ref": memo.ledger_ref,
    }
    for name, (_, _, _, cell, _) in MEMO_FIELDS.items():
        writer.entry(
            memo_field_id(memo.doc_id, name), values[name], cell,
            "right" if name == "amount" else "left",
        )  # fmt: skip
    return image, _page_gt(memo.doc_id, "memo", image, writer.fields)


# --- pages, overlays, world -------------------------------------------------------------


def _page_gt(
    doc_id: str, doc_type: Literal["ledger", "memo"], image: Image.Image, fields: list[FieldGT]
) -> PageGT:
    return PageGT(
        page_id=doc_id,
        doc_type=doc_type,
        image_path=f"pages/{doc_id}.png",  # relative to the output directory
        width=image.width,
        height=image.height,
        severity=0,
        fields=fields,
        artefacts=[],
        source_errors=[],
    )


_PALETTE = (
    (230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180),
    (70, 200, 200), (240, 50, 230), (128, 128, 0), (170, 110, 40), (0, 0, 128),
)  # fmt: skip
_FIELD_COLOURS = dict(
    zip(
        sorted(LEDGER_COLUMNS | LEDGER_HEADER_NAMES | MEMO_FIELD_NAMES),
        itertools.cycle(_PALETTE),
        strict=False,
    )
)
_BLANK_COLOUR = (150, 150, 150)


def overlay(image: Image.Image, gt: PageGT) -> Image.Image:
    """The page with every ground-truth box outlined, coloured by field name."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    for field in gt.fields:
        name = field.field_id.rsplit(":", 1)[1]
        colour = _FIELD_COLOURS[name] if field.printed else _BLANK_COLOUR
        box = field.bbox
        draw.rectangle((box.x0, box.y0, box.x1 - 1, box.y1 - 1), outline=colour, width=1)
    return out


def render_world(
    world: World,
    out_dir: Path,
    n_cards: int | None = None,
    n_memos: int | None = None,
    seed: int = 0,
) -> list[PageGT]:
    """Render the first n_cards cards and n_memos memos (all by default).

    Writes out_dir/pages/<doc_id>.png and .json, and out_dir/overlays/<doc_id>.png. Each page
    gets its own rng seeded from (seed, doc_id), so a page renders the same however many
    others are rendered alongside it.
    """
    pages_dir = out_dir / "pages"
    overlays_dir = out_dir / "overlays"
    pages_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)
    banks = {card.doc_id: card.bank for card in world.cards}

    renders = [(card.doc_id, functools.partial(render_card, card)) for card in world.cards[:n_cards]]
    for memo in world.memos[:n_memos]:
        bank = banks[memo.ledger_ref.rsplit(":", 1)[0]]
        renders.append((memo.doc_id, functools.partial(render_memo, memo, bank=bank)))

    pages: list[PageGT] = []
    for doc_id, render in renders:
        image, gt = render(random.Random(f"{seed}:{doc_id}"))
        on_page = {field.field_id for field in gt.fields}
        errors = [e for e in world.source_errors if on_page.intersection(e.field_ids)]
        gt = gt.model_copy(update={"source_errors": errors})
        image.save(pages_dir / f"{doc_id}.png")
        (pages_dir / f"{doc_id}.json").write_text(gt.model_dump_json(indent=2) + "\n")
        overlay(image, gt).save(overlays_dir / f"{doc_id}.png")
        pages.append(gt)
    return pages


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.synth.render",
        description="Render clean pages with ground-truth boxes from a generated world.",
    )
    parser.add_argument("--seed", type=int, required=True, help="world and rendering seed")
    parser.add_argument("--cards", type=int, default=None, help="number of cards (default all)")
    parser.add_argument("--memos", type=int, default=None, help="number of memos (default all)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    pages = render_world(generate_world(args.seed), args.out, args.cards, args.memos, args.seed)
    print(f"wrote {len(pages)} pages to {args.out}")


if __name__ == "__main__":
    main()
