"""S0+ocr: a value's box taken from the archive's own OCR text layer, not the model (P21b).

The Treasury Bulletin PDFs from FRASER carry an OCR text layer with each character's position, as
do the Comptroller of the Currency's reports (data/real_occ, read from their own PDFs). For a
development page (pages.py refuses any other before its PDF is opened), words() reads that
layer: characters grouped into words at whitespace, each word's box converted to the pixels of
the stored 200 dpi image with pdfium's own page-to-device transform (FPDF_PageToDevice, the one
its renderer uses, at the image's size), so a box lands on the ink exactly.

anchor() then looks, for each value the model read with a box (S0), for the same figure in the
layer near that box: a word whose digits are the value's digits (at least MIN_DIGITS of them),
whose centre is within WINDOW pixels above or below the box's centre (the row region) and which
overlaps the box widened by its own width either side (the column). The layer's OCR of the 1939
typeface confuses some glyphs in fixed ways (a 4 printed as "1*", "lt", "U", ...; a 1 as "i" or
"l"); digits() undoes those listed in CONFUSIONS, as seen on development pages. The match is
confident only when exactly one word qualifies and no other value claims it; the value then takes
that word's box. Any other value keeps the model's box and is unanchored. Nothing is guessed: no
partial or near match anchors. A synthetic page has no OCR layer: on it S0+ocr is S0.
"""

from __future__ import annotations

import ctypes
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image

from archivist.ingest import occ
from archivist.ingest.fraser import DEFAULT_ROOT, pdf_name
from archivist.pipeline.extract import ARCHIVE_OCR
from archivist.schema import BBox, ExtractedValue
from archivist.templates.pages import OCC, OCC_ROOT, REAL, resolve

STRATEGY = ARCHIVE_OCR
WINDOW = 100  # pixels above and below the model's box centre: about four printed lines
MIN_DIGITS = 2
CONFUSIONS = (  # the OCR's readings of the 1939 typeface, undone in this order
    ("1*", "4"),
    ("l*", "4"),
    ("i*", "4"),
    ("lt", "4"),
    ("l»", "4"),
    ("1»", "4"),
    ("l«", "4"),
    ("i«", "4"),
    ("*", "4"),
    ("»", "4"),
    ("«", "4"),
    ("U", "4"),
    ("i", "1"),
    ("l", "1"),
    ("I", "1"),
    ("|", "1"),
    ("O", "0"),
    ("o", "0"),
)


@dataclass(frozen=True)
class Word:
    text: str  # as the layer has it
    box: BBox  # in the stored image's pixels

    @property
    def digits(self) -> str:
        return digits(self.text)


def digits(text: str) -> str:
    """A word's digits once the layer's known confusions are undone."""
    for wrong, right in CONFUSIONS:
        text = text.replace(wrong, right)
    return re.sub(r"\D", "", text)


@cache
def words(ref: str, root: Path = DEFAULT_ROOT) -> tuple[Word, ...]:
    """Every word of a development page's OCR layer, boxed in the stored image's pixels; none for
    a synthetic page, which has no layer, so its values all keep the model's boxes."""
    page_ref = resolve(ref, root)  # refuses a page that may not be read, before the PDF is opened
    if (found := REAL.fullmatch(ref)) is not None:
        path = root / "pdf" / pdf_name(found["issue"])
    elif (found := OCC.fullmatch(ref)) is not None:  # a Comptroller's report: its own root
        path = occ.pdf_path(OCC_ROOT, found["issue"])
    else:
        return ()
    width, height = Image.open(page_ref.path).size
    pdf = pdfium.PdfDocument(path)
    try:
        page = pdf[int(found["page"]) - 1]
        text = page.get_textpage()

        def pixel(x: float, y: float) -> tuple[int, int]:
            dx, dy = ctypes.c_int(), ctypes.c_int()
            pdfium_c.FPDF_PageToDevice(
                page.raw, 0, 0, width, height, 0, x, y, ctypes.byref(dx), ctypes.byref(dy)
            )
            return dx.value, dy.value

        out, chars = [], []
        for i in range(text.count_chars() + 1):
            char = text.get_text_range(i, 1) if i < text.count_chars() else " "
            if char and not char.isspace():
                chars.append((char, text.get_charbox(i)))
                continue
            if chars:
                left = min(b[0] for _, b in chars)
                bottom = min(b[1] for _, b in chars)
                right = max(b[2] for _, b in chars)
                top = max(b[3] for _, b in chars)
                (x0, y1), (x1, y0) = pixel(left, bottom), pixel(right, top)
                if x1 > x0 and y1 > y0:
                    box = BBox(x0=x0, y0=y0, x1=x1, y1=y1)
                    out.append(Word("".join(c for c, _ in chars), box))
                chars = []
        return tuple(out)
    finally:
        pdf.close()


def _candidates(value: ExtractedValue, layer: Sequence[Word]) -> list[int]:
    wanted = re.sub(r"\D", "", value.value or "")
    if len(wanted) < MIN_DIGITS or value.citation is None:
        return []
    box = value.citation.bbox
    centre, reach = (box.y0 + box.y1) / 2, box.x1 - box.x0
    return [
        i
        for i, word in enumerate(layer)
        if word.digits == wanted
        and abs((word.box.y0 + word.box.y1) / 2 - centre) <= WINDOW
        and word.box.x1 > box.x0 - reach
        and word.box.x0 < box.x1 + reach
    ]


def anchor(
    values: Sequence[ExtractedValue], layer: Sequence[Word]
) -> tuple[list[ExtractedValue], set[str]]:
    """The values with each confidently matched one's box taken from the layer, and the field ids
    so anchored; every other value keeps the model's box."""
    claims: dict[int, list[str]] = defaultdict(list)
    chosen: dict[str, int] = {}
    for value in values:
        if value.abstained:
            continue
        found = _candidates(value, layer)
        if len(found) == 1:
            chosen[value.field_id] = found[0]
            claims[found[0]].append(value.field_id)
    anchored = {f for f, i in chosen.items() if len(claims[i]) == 1}
    out = []
    for value in values:
        if value.field_id in anchored:
            word = layer[chosen[value.field_id]]
            citation = value.citation.model_copy(update={"bbox": word.box, "raw_bbox": None})
            value = value.model_copy(update={"citation": citation})
        out.append(value)
    return out, anchored
