"""S0+grid: a value's box from the table's own grid, found in the page by plain code (P21c).

Each value keeps the most trustworthy box there is, and says where it came from (SOURCES):

1. "ocr": the figure itself, found in the archive's OCR text layer (ocr.anchor, S0+ocr);
2. "grid": the cell of the table's grid, found in the page image without a model:
   - the body is where the read's figure cells are: the envelope of the model's (S0) boxes,
     widened by BODY_LINES box heights above and below, since those boxes can sit lines off;
   - ink is what is darker than the page's Otsu threshold, ruled lines taken out as unbroken
     strokes too long for a printed figure (grid_probe);
   - columns are the runs of pixel columns carrying ink (grid_probe's rule), and each figure
     column of the layout takes the run under the median centre of its anchored figures, else of
     the model's boxes (the model places columns far better than rows); two columns on one run,
     or a column on no run, are not mapped;
   - the page's skew is the shear, within MAX_SKEW, that makes the figures' row profile sharpest
     (rules lean, and a leaning row smears into its neighbours); rows are the bands of that
     profile, a band over MERGED times the usual height (faint print joins lines) cut into as
     many as the lines it holds, by the median line pitch;
   - a row of the read is fixed to a band by an anchored figure in it, or by its label found in
     the OCR layer left of the figure columns (the layers of the 1980s pages print the labels
     but not the figures); the read's rows that print a figure are aligned to the bands in
     order, and a row is mapped only when it is fixed, or lies between two fixed rows with as
     many bands between them as rows: then order alone decides, and nothing is guessed;
   - the cell's box is its band across its column's run, put back on the skewed page;
3. "model": the model's own box, where neither of the others is found.
"""

from __future__ import annotations

import io
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from PIL import Image

from archivist.doctypes.template import NUMERIC, TemplateType
from archivist.pipeline.extract import ARCHIVE_GRID
from archivist.schema import BBox, ExtractedValue
from archivist.templates import ocr
from archivist.templates.ink import (
    ACROSS_RUN,
    COL_GAP,
    COL_LEVEL,
    DOWN_RUN,
    MIN_COL,
    MIN_ROW,
    ROW_GAP,
    ROW_LEVEL,
    otsu,
    runs,
    without_long_runs,
)

STRATEGY = ARCHIVE_GRID
SOURCES = ("ocr", "grid", "model")
BODY_LINES = 4
MAX_SKEW, SKEW_STEP = 1.5, 0.05  # degrees
LABEL_WINDOW = 120  # pixels: how far a label found in the OCR layer may lie from the model's row
MERGED = 1.6  # a band this many times the usual height holds more than one line


@dataclass(frozen=True)
class Grid:
    """The table's grid in the page's pixels: columns as x ranges, rows as bands in deskewed y."""

    columns: dict[str, tuple[int, int]]  # figure column key -> (x0, x1)
    bands: list[tuple[int, int]]  # (y0, y1) after deskewing
    shear: float  # y on the page = deskewed y + shear * (x - centre)
    centre: float

    def box(self, column: str, band: int) -> BBox:
        x0, x1 = self.columns[column]
        y0, y1 = self.bands[band]
        lift = self.shear * ((x0 + x1) / 2 - self.centre)
        return BBox(x0=x0, y0=round(y0 + lift), x1=x1, y1=round(y1 + lift))

    def deskew(self, x: float, y: float) -> float:
        return y - self.shear * (x - self.centre)


def _row_col(field_id: str) -> tuple[str, str]:
    *_, row, column = field_id.split(":")
    return row, column


def _centre(box: BBox) -> tuple[float, float]:
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def _skew(ink: np.ndarray) -> float:
    """The shear, in y per x, that makes the row profile of the ink sharpest."""
    ys, xs = np.nonzero(ink)
    if len(ys) == 0:
        return 0.0
    xs = xs - ink.shape[1] / 2
    best, score = 0.0, -1.0
    for step in range(-round(MAX_SKEW / SKEW_STEP), round(MAX_SKEW / SKEW_STEP) + 1):
        shear = math.tan(math.radians(step * SKEW_STEP))
        rows = np.round(ys - shear * xs).astype(int)
        rows -= rows.min()
        profile = np.bincount(rows).astype(float)
        value = float((profile**2).sum())
        if value > score:
            best, score = shear, value
    return best


def find_grid(
    image: bytes, figures: Mapping[str, Sequence[ExtractedValue]], anchored: set[str]
) -> Grid | None:
    """The grid of the table whose figure values (by column, with the model's boxes or anchored
    ones) are given; None if no body can be found."""
    boxed = [v for column in figures.values() for v in column if v.citation is not None]
    if not boxed:
        return None
    gray = np.asarray(Image.open(io.BytesIO(image)).convert("L"))
    height, width = gray.shape
    line = statistics.median(v.citation.bbox.y1 - v.citation.bbox.y0 for v in boxed)
    x0 = max(0, min(v.citation.bbox.x0 for v in boxed) - 10)
    x1 = min(width, max(v.citation.bbox.x1 for v in boxed) + 10)
    y0 = max(0, round(min(v.citation.bbox.y0 for v in boxed) - BODY_LINES * line))
    y1 = min(height, round(max(v.citation.bbox.y1 for v in boxed) + BODY_LINES * line))
    part = without_long_runs(gray[y0:y1, x0:x1] <= otsu(gray), DOWN_RUN)
    part = without_long_runs(part.T, ACROSS_RUN).T
    profile = part.sum(axis=0)
    floor, full = np.percentile(profile, [10, 95])
    inked = profile > floor + COL_LEVEL * (full - floor)
    found = [(a + x0, b + x0) for a, b in runs(inked, COL_GAP, MIN_COL)]

    columns: dict[str, tuple[int, int]] = {}
    for column, values in figures.items():
        here = [v for v in values if v.citation is not None]
        preferred = [v for v in here if v.field_id in anchored] or here
        if not preferred:
            continue
        x = statistics.median(_centre(v.citation.bbox)[0] for v in preferred)
        under = [run for run in found if run[0] - COL_GAP <= x <= run[1] + COL_GAP]
        if len(under) == 1:
            columns[column] = under[0]
    taken: dict[tuple[int, int], list[str]] = {}
    for column, run in columns.items():
        taken.setdefault(run, []).append(column)
    columns = {c: r for c, r in columns.items() if len(taken[r]) == 1}
    order = [c for c in figures if c in columns]
    if [columns[c] for c in order] != sorted(columns[c] for c in order):
        return None  # the runs are not in the layout's column order: no grid to trust
    if not columns:
        return None

    mask = np.zeros_like(part)
    for a, b in columns.values():
        mask[:, a - x0 : b - x0] = part[:, a - x0 : b - x0]
    centre = width / 2
    shear = _skew(mask)
    ys, xs = np.nonzero(mask)
    rows = np.round(ys + y0 - shear * (xs + x0 - centre)).astype(int)
    base = rows.min()
    profile = np.bincount(rows - base).astype(float)
    level = ROW_LEVEL * np.percentile(profile[profile > 0], 95)
    bands = [(a + base, b + base) for a, b in runs(profile > level, ROW_GAP, MIN_ROW)]
    return Grid(columns, split(bands), shear, centre)


def split(bands: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Bands with each one that runs over several lines (faint print merges them) cut into as many
    equal bands as lines it holds, by the median line pitch."""
    if len(bands) < 3:
        return list(bands)
    height = statistics.median(b - a for a, b in bands)
    pitch = statistics.median(b[0] - a[0] for a, b in zip(bands, bands[1:]))
    out = []
    for a, b in bands:
        lines = round((b - a + pitch - height) / pitch) if b - a > MERGED * height else 1
        step = (b - a) / max(1, lines)
        out += [(round(a + i * step), round(a + (i + 1) * step)) for i in range(max(1, lines))]
    return out


def _label_lines(layer: Sequence[ocr.Word], left_of: int) -> list[tuple[str, float]]:
    """The OCR layer's text left of the figure columns, joined into lines: (letters, centre y)."""
    stub = sorted(
        (w for w in layer if w.box.x1 <= left_of), key=lambda w: ((w.box.y0 + w.box.y1) / 2)
    )
    lines: list[list[ocr.Word]] = []
    for word in stub:
        y = (word.box.y0 + word.box.y1) / 2
        if lines and abs(y - statistics.mean((w.box.y0 + w.box.y1) / 2 for w in lines[-1])) < (
            (word.box.y1 - word.box.y0) / 2
        ):
            lines[-1].append(word)
        else:
            lines.append([word])
    return [
        (
            _letters(" ".join(w.text for w in sorted(group, key=lambda w: w.box.x0))),
            statistics.mean((w.box.y0 + w.box.y1) / 2 for w in group),
        )
        for group in lines
    ]


def _letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower().split("....")[0])


def assign(
    values: Sequence[ExtractedValue],
    doc_type: TemplateType,
    image: bytes,
    layer: Sequence[ocr.Word],
) -> tuple[list[ExtractedValue], dict[str, str]]:
    """Every value with its box, and each value's box source ("ocr", "grid" or "model")."""
    anchored_values, anchored = ocr.anchor(values, layer)
    figure_columns = [c.key for c in doc_type.layout.columns if c.kind in NUMERIC]
    by_id = {v.field_id: v for v in anchored_values}
    figures: dict[str, list[ExtractedValue]] = {c: [] for c in figure_columns}
    printed_rows: list[str] = []
    for row in doc_type.layout.row_keys:
        cells = [v for v in anchored_values if _row_col(v.field_id)[0] == row]
        printed = False
        for v in cells:
            column = _row_col(v.field_id)[1]
            if column in figures and not v.abstained and v.value and v.value.strip():
                figures[column].append(v)
                printed = True
        if printed:
            printed_rows.append(row)
    grid = find_grid(image, figures, anchored)
    sources = {v.field_id: ("ocr" if v.field_id in anchored else "model") for v in values}
    if grid is None or not grid.bands:
        return anchored_values, sources

    def band_of(y: float) -> int | None:
        hits = [i for i, (a, b) in enumerate(grid.bands) if a - 2 <= y <= b + 2]
        return hits[0] if len(hits) == 1 else None

    fixed: dict[str, int] = {}
    for row in printed_rows:  # an anchored figure fixes its row's band
        found = {
            band_of(grid.deskew(*_centre(by_id[f].citation.bbox)))
            for f in anchored
            if f in by_id and _row_col(f)[0] == row
        }
        if len(found) == 1 and None not in found:
            fixed[row] = found.pop()
    labels = [c for c in doc_type.layout.columns if c.kind == "text"]
    if labels and grid.columns:
        lines = _label_lines(layer, min(a for a, _ in grid.columns.values()))
        for row in printed_rows:
            if row in fixed:
                continue
            label = next(
                (v for v in values if v.field_id.endswith(f":{row}:{labels[0].key}")), None
            )
            text = _letters(label.value or "") if label is not None else ""
            if len(text) < 3 or label.citation is None:
                continue
            y = _centre(label.citation.bbox)[1]
            matches = [
                ly for lt, ly in lines if lt.startswith(text) and abs(ly - y) <= LABEL_WINDOW
            ]
            if len(matches) == 1:
                x = _centre(label.citation.bbox)[0]
                band = band_of(grid.deskew(x, matches[0]))
                if band is not None:
                    fixed[row] = band

    mapped: dict[str, int] = dict(fixed)
    order = [r for r in printed_rows if r in fixed]
    for before, after in zip(order, order[1:]):
        rows = printed_rows[printed_rows.index(before) + 1 : printed_rows.index(after)]
        bands = list(range(fixed[before] + 1, fixed[after]))
        if fixed[after] > fixed[before] and len(rows) == len(bands):
            mapped.update(zip(rows, bands))

    out = []
    for value in anchored_values:
        row, column = _row_col(value.field_id)
        if sources[value.field_id] == "model" and row in mapped and column in grid.columns:
            box = grid.box(column, mapped[row])
            citation = (
                value.citation.model_copy(update={"bbox": box, "raw_bbox": None})
                if value.citation is not None
                else None
            )
            if citation is not None:
                value = value.model_copy(update={"citation": citation})
                sources[value.field_id] = "grid"
        out.append(value)
    return out, sources
