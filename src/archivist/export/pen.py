"""Pen loops: a hand-drawn ring around a value, clear of its own ink and of every other word's.

The review UI circles a value the way a clerk would with a pen (design mockup v7). The geometry is
worked out here, once, from the page image, so that the UI only draws it and the same loop appears
wherever the value is pointed at:

1. words(): every word of ink on the page, found by plain code from the scan alone (the ink and
   word logic of S0+ink, pipeline/citations.py, at the page's own text height).
2. own_ink(): the words a field's corrected citation box holds, with the other words of its line
   that the blind re-read's crop took in, since a box snapped to one word of a value leaves the
   rest out ("BANK" for a box on "CHARGES"); never a word another field's box holds.
3. fit_loop(): a superellipse around that ink with a margin, round for a short value and flatter
   for a long one, drawn as a pen would (a start, a sweep a little past a full turn, a wobble, an
   overshoot). Its clearance from every other word is exact, not sampled: the shape is convex, so
   a word's box meets it only if the box's nearest corner to the centre does. On a crowded page
   the margin is tightened and the shape changed, and where no loop fits the value gets an
   underline instead.
4. box_outline(): where neither fits (a table packed too tight), the cited box itself as a thin
   rounded outline, run inside its edge so that it is no bigger than the box (a little further
   in where a neighbouring word comes right up to the edge). It marks the cell, not the ink, so
   it may touch the value's own ink, but never another word's; where a word straddles the box it
   is not drawn, and the value has no mark at all.

Nothing here reads ground truth, calls a model or varies between runs: a loop depends on the page
image, the field's box and its id.
"""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from archivist.pipeline import citations
from archivist.schema import BBox

Box = tuple[float, float, float, float]

# Words. The text height is the page's own (the median height of its small marks of ink).
RULE_RUN_X, RULE_RUN_Y = citations.RULE_RUN_X, citations.RULE_RUN_Y  # × text height
FIRST_RULE_X, FIRST_RULE_Y = 0.06, 0.05  # × page width, height: the first pass that finds the text
TEXT_INK, TEXT_MIN = 25, 9  # pixels and height (px) of a mark that counts towards the text height
WORD_GAP = 0.3  # ink closer than 2 × this × text height sideways joins into one word
WORD_HEIGHT = (0.3, 3.2)  # × text height: shorter is a speck, taller a blot or a ring
WORD_MIN_INK = 0.1  # × text height²
WORD_MAX_FILL = 0.85  # a solid block is not a word
DEFAULT_TEXT_HEIGHT = 16.0

# Own ink.
OVERLAP = 0.3  # a word is a field's when this share of it lies in the field's box
SAME_LINE = 0.5  # share of the shorter word's height that two words of one line must overlap

# The loop.
MARGINS = (1.0, 0.8, 0.65)  # × the margin: normal, then tighter on a crowded page
STEPS = 72  # segments in a loop's path
STROKE = 0.2  # × text height
UNDERLINE_AT = (0.25, 0.4, 0.6)  # × the ink's height below it
MAX_TALL = 3.0  # a loop is never taller than this × the ink with its margin
BOX_STROKE, BOX_MIN_STROKE = 0.1, 1.5  # a box's outline: × text height, at least this many pixels
BOX_RADIUS = 3.0  # px, at most; a quarter of the shorter side where the box is small
NEIGHBOUR = 0.5  # px of clear space a stroke keeps from another word
ROUNDING = 0.15  # px: the path's coordinates are given to a tenth, which can move a point this far


@dataclass(frozen=True)
class PenLoop:
    kind: str  # "loop" or "underline"
    points: list[float]  # x, y, x, y, ... in page pixels
    width: float  # the stroke's width in page pixels, which the clearance allows for
    ink: Box  # the value's own ink


def _union(boxes: Sequence[Box]) -> Box:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _overlap(a: Box, b: Box) -> float:
    """The area of the box a lies in b, as a share of a's."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / max((a[2] - a[0]) * (a[3] - a[1]), 1e-9)


# --- words ----------------------------------------------------------------------------------------


def text_height(gray: np.ndarray) -> float:
    """The page's text height: the median height of its marks of ink, ruled lines removed."""
    height, width = gray.shape
    mask = citations.ink_mask(gray)
    mask = citations._without_long_runs(mask, max(40, round(FIRST_RULE_X * width)))
    mask = citations._without_long_runs(mask.T, max(30, round(FIRST_RULE_Y * height))).T
    heights = [
        y1 - y0
        for _, y0, _, y1, pixels in citations.components(mask)
        if pixels >= TEXT_INK and TEXT_MIN <= y1 - y0 <= 0.1 * height  # not dust, not punctuation
    ]
    return float(np.median(heights)) if heights else DEFAULT_TEXT_HEIGHT


def words(gray: np.ndarray) -> tuple[float, list[tuple[int, int, int, int]]]:
    """The page's text height and every word of ink on it, as boxes in page pixels, ordered by
    their top then left. A ring or a blot (a stain) is taller than a word and is left out."""
    th = text_height(gray)
    mask = citations.ink_mask(gray)
    mask = citations._without_long_runs(mask, round(RULE_RUN_X * th))
    mask = citations._without_long_runs(mask.T, round(RULE_RUN_Y * th)).T
    ink = np.zeros_like(mask)
    for x0, y0, x1, y1, pixels in citations.components(mask):
        if pixels >= max(3, citations.SPECK_AREA * th * th):
            ink[y0:y1, x0:x1] |= mask[y0:y1, x0:x1]
    radius = max(1, round(WORD_GAP * th))
    found = []
    for x0, y0, x1, y1, _ in citations.components(citations._dilate_x(ink, radius)):
        x0, x1 = x0 + radius, x1 - radius  # the smear widened it by radius on each side
        height = y1 - y0
        pixels = int(ink[y0:y1, x0:x1].sum())
        if (
            WORD_HEIGHT[0] * th <= height <= WORD_HEIGHT[1] * th
            and pixels >= WORD_MIN_INK * th * th
            and pixels <= WORD_MAX_FILL * (x1 - x0) * height
        ):
            found.append((int(x0), int(y0), int(x1), int(y1)))
    return th, sorted(found, key=lambda w: (w[1], w[0]))


# --- own ink --------------------------------------------------------------------------------------


def claims(words_: Sequence[Box], boxes: dict[str, BBox]) -> dict[int, set[str]]:
    """For each word, the fields whose corrected box holds it."""
    out: dict[int, set[str]] = {}
    for i, word in enumerate(words_):
        for field_id, b in boxes.items():
            if _overlap(word, (b.x0, b.y0, b.x1, b.y1)) >= OVERLAP:
                out.setdefault(i, set()).add(field_id)
    return out


def own_ink(
    words_: Sequence[Box],
    field_id: str,
    box: BBox,
    crop: BBox | None,
    held: dict[int, set[str]],
) -> tuple[list[int], Box] | None:
    """The indices of the words that are this field's, and the box round them; None if its box
    holds no ink. The corrected box is often one word of a value ("CHARGES" of "BANK CHARGES"), so
    the words on its line that the blind re-read's crop took in belong to it too, unless another
    field's box holds them."""
    own = [i for i in range(len(words_)) if field_id in held.get(i, ())]
    if not own:
        return None
    lo, hi = (crop.x0, crop.x1) if crop is not None else (box.x0, box.x1)
    for j, w in enumerate(words_):
        if j in own or held.get(j):
            continue
        line = min(w[3], box.y1) - max(w[1], box.y0)
        if line < SAME_LINE * min(w[3] - w[1], box.y1 - box.y0):
            continue
        if lo <= (w[0] + w[2]) / 2 <= hi:
            own.append(j)
    return sorted(own), _union([words_[i] for i in own])


# --- the loop -------------------------------------------------------------------------------------


def _clear(obstacles: np.ndarray, cx: float, cy: float, a: float, b: float, n: float) -> bool:
    """Whether no obstacle (rows of x0, y0, x1, y1) meets the superellipse |x/a|^n + |y/b|^n < 1
    centred on (cx, cy). The shape is convex, so a box meets it exactly when its corner nearest the
    centre is inside."""
    if not len(obstacles):
        return True
    x0, y0, x1, y1 = (obstacles[:, i] - (cx if i % 2 == 0 else cy) for i in range(4))
    nx = np.where((x0 <= 0) & (x1 >= 0), 0.0, np.minimum(np.abs(x0), np.abs(x1)))
    ny = np.where((y0 <= 0) & (y1 >= 0), 0.0, np.minimum(np.abs(y0), np.abs(y1)))
    return not bool((((nx / a) ** n + (ny / b) ** n) < 1).any())


def _inside(bounds: tuple[int, int] | None, x0: float, y0: float, x1: float, y1: float) -> bool:
    return bounds is None or (x0 >= 0 and y0 >= 0 and x1 <= bounds[0] and y1 <= bounds[1])


def _fit(
    own: Box,
    obstacles: np.ndarray,
    stroke: float,
    bounds: tuple[int, int] | None,
) -> tuple[float, float, float, float, float] | None:
    """The (a, b, n, wobble, margin) of the first superellipse that clears every obstacle and stays
    on the page."""
    cx, cy = (own[0] + own[2]) / 2, (own[1] + own[3]) / 2
    iw, ih = own[2] - own[0], own[3] - own[1]
    for k in MARGINS:  # normal margin, then tighter on a crowded page
        m = min(8.0, max(3.0, ih * 0.28)) * k  # the room between the ink and the stroke's edge
        wobble, gap = m * 0.28, max(1.5, m * 0.5)
        hw, hh = iw / 2 + m + stroke / 2 + wobble, ih / 2 + m + stroke / 2 + wobble
        n0 = min(4.0, max(2.0, 2 + (hw / hh - 1.6) * 0.55))  # round for short, flatter for long
        reach = stroke / 2 + wobble * 1.5 + gap  # what the stroke, the wobble and the gap need
        for n in (n0, min(6.0, n0 + 1), 6.0):
            f0 = 2 ** (1 / n)
            factors = [f0]
            for d in np.arange(0.05, 0.6, 0.05):
                factors.append(f0 * (1 + d))
                if f0 * (1 - d) > 1.015:
                    factors.append(f0 * (1 - d))
            factors.append(1.015)
            for f in factors:
                t = 1 - (1 / f) ** n
                if t <= 0:
                    continue
                a, b = hw * f, hh / t ** (1 / n)
                if b > hh * MAX_TALL:
                    continue
                far = a + stroke / 2 + wobble * 1.5, b + stroke / 2 + wobble * 1.5
                if not _inside(bounds, cx - far[0], cy - far[1], cx + far[0], cy + far[1]):
                    continue
                if _clear(obstacles, cx, cy, a + reach, b + reach, n):
                    return a, b, n, wobble, m
    return None


def _path(own: Box, a: float, b: float, n: float, wobble: float, rng: random.Random) -> list[float]:
    cx, cy = (own[0] + own[2]) / 2, (own[1] + own[3]) / 2
    t0 = -2.3 + (rng.random() - 0.5) * 0.6
    sweep = math.pi * 2 + 0.38 + rng.random() * 0.22
    p1, p2 = rng.random() * 6.3, rng.random() * 6.3
    out: list[float] = []
    for i in range(STEPS + 1):
        u = i / STEPS
        t = t0 + sweep * u
        c, s = math.cos(t), math.sin(t)
        ex = math.copysign(abs(c) ** (2 / n), c) * a
        ey = math.copysign(abs(s) ** (2 / n), s) * b
        length = math.hypot(ex, ey) or 1.0
        # a hand's wobble, and the overshoot at the end
        j = wobble * (0.6 * math.sin(2 * t + p1) + 0.4 * math.sin(3 * t + p2))
        if u > 0.86:
            j += (u - 0.86) / 0.14 * wobble * 1.5
        out += [cx + ex * (1 + j / length), cy + ey * (1 + j / length)]
    return out


def _underline(
    own: Box,
    obstacles: np.ndarray,
    stroke: float,
    bounds: tuple[int, int] | None,
    rng: random.Random,
) -> list[float] | None:
    ih = own[3] - own[1]
    sag = min(0.6, ih * 0.05)  # the line's little waves
    reach = stroke / 2 + sag + 1.0
    x0, x1 = own[0] - 3, own[2] + 3
    for share in UNDERLINE_AT:
        y = own[3] + stroke / 2 + sag + max(2.0, ih * share)
        if not _inside(bounds, x0, y - reach, x1, y + reach):
            continue
        hit = (
            (obstacles[:, 0] < x1 + reach)
            & (obstacles[:, 2] > x0 - reach)
            & (obstacles[:, 1] < y + reach)
            & (obstacles[:, 3] > y - reach)
        )
        if len(obstacles) and hit.any():
            continue
        wave = rng.random() * 2
        out: list[float] = []
        for i in range(13):
            u = i / 12
            out += [x0 + (x1 - x0) * u, y + math.sin(u * 9 + wave) * sag]
        return out
    return None


def _rounded(x0: float, y0: float, x1: float, y1: float, r: float) -> list[float]:
    """The outline of a rounded rectangle as points, clockwise from the top edge's left end."""
    out: list[float] = []
    for cx, cy, start in (
        (x1 - r, y0 + r, -90),
        (x1 - r, y1 - r, 0),
        (x0 + r, y1 - r, 90),
        (x0 + r, y0 + r, 180),
    ):
        for k in range(5):
            a = math.radians(start + 90 * k / 4)
            out += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return out + out[:2]


def _band(points: Sequence[float], step: float = 1.0) -> np.ndarray:
    """The points of a path of straight segments, a point every `step` pixels or so."""
    corners = np.array(points, dtype=float).reshape(-1, 2)
    parts = [corners[:1]]
    for a, b in zip(corners, corners[1:], strict=False):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / step)))
        parts.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    return np.vstack(parts)


BOX_INSETS = (0.0, 1.5, 3.0)  # px: how far inside its edge the outline may be drawn to keep clear


def box_outline(box: BBox, ink: Box | None, obstacles: np.ndarray, text_h: float) -> PenLoop | None:
    """The cited box as a thin rounded outline inside its edge (a little further in where a
    neighbouring word comes right up to the edge), if it keeps clear of every obstacle (rows of x0,
    y0, x1, y1); else None."""
    width = round(max(BOX_MIN_STROKE, BOX_STROKE * text_h), 1)
    if len(obstacles):
        near = obstacles[
            (obstacles[:, 0] < box.x1 + 4)
            & (obstacles[:, 2] > box.x0 - 4)
            & (obstacles[:, 1] < box.y1 + 4)
            & (obstacles[:, 3] > box.y0 - 4)
        ]
    else:
        near = obstacles
    for inset in BOX_INSETS:
        x0, y0 = box.x0 + width / 2 + inset, box.y0 + width / 2 + inset
        x1, y1 = box.x1 - width / 2 - inset, box.y1 - width / 2 - inset
        if x1 - x0 < 2 or y1 - y0 < 2:
            break
        points = _rounded(x0, y0, x1, y1, min(BOX_RADIUS, 0.25 * min(x1 - x0, y1 - y0)))
        band = _band(points)
        clear = True
        for q in near:
            dx = np.maximum(np.maximum(q[0] - band[:, 0], band[:, 0] - q[2]), 0)
            dy = np.maximum(np.maximum(q[1] - band[:, 1], band[:, 1] - q[3]), 0)
            if np.hypot(dx, dy).min() - width / 2 < NEIGHBOUR + ROUNDING:
                clear = False
                break
        if clear:
            rect: Box = (float(box.x0), float(box.y0), float(box.x1), float(box.y1))
            return PenLoop(
                kind="box", points=[round(p, 1) for p in points], width=width, ink=ink or rect
            )
    return None


def path_data(points: Sequence[float]) -> str:
    """The points as an SVG path, "M x y L x y ...", coordinates to a tenth of a pixel."""
    nums = [format(round(p, 1), "g") for p in points]
    return "M" + "L".join(f"{nums[i]} {nums[i + 1]}" for i in range(0, len(nums), 2))


def fit_loop(
    field_id: str,
    own: Box,
    obstacles: np.ndarray,
    text_h: float,
    bounds: tuple[int, int] | None = None,
) -> PenLoop | None:
    """A loop round own that clears every obstacle (rows of x0, y0, x1, y1) and stays within the
    page's bounds (its width and height), an underline where none does, else None."""
    stroke = round(max(2.0, STROKE * text_h), 1)
    rng = random.Random(zlib.crc32(field_id.encode()))
    fit = _fit(own, obstacles, stroke, bounds)
    if fit is not None:
        a, b, n, wobble, _ = fit
        kind, points = "loop", _path(own, a, b, n, wobble, rng)
    else:
        line = _underline(own, obstacles, stroke, bounds, rng)
        if line is None:
            return None
        kind, points = "underline", line
    return PenLoop(kind=kind, points=[round(p, 1) for p in points], width=stroke, ink=own)


def loops_for(
    fields: dict[str, tuple[BBox, BBox | None]],
    words_: Sequence[Box],
    text_h: float,
    size: tuple[int, int] | None = None,
    blanks: dict[str, BBox] | None = None,
) -> dict[str, PenLoop]:
    """A mark for each field (id -> its corrected box and the blind re-read's crop) whose box holds
    ink: a loop round its own ink, else an underline, else, where the page is too tight for either,
    its box as an outline; every word that isn't its own an obstacle, the page (its width and
    height, if given) the limit. `blanks` are fields with nothing written (a blank that went to
    review): they get the box outline alone, against every word."""
    held = claims(words_, {field_id: box for field_id, (box, _) in fields.items()})
    boxes = np.array(words_, dtype=float).reshape(-1, 4)
    out: dict[str, PenLoop] = {}
    for field_id, (box, crop) in fields.items():
        found = own_ink(words_, field_id, box, crop, held)
        if found is None:
            if (outline := box_outline(box, None, boxes, text_h)) is not None:
                out[field_id] = outline
            continue
        indices, ink = found
        keep = np.ones(len(boxes), dtype=bool)
        keep[indices] = False
        mark = fit_loop(field_id, ink, boxes[keep], text_h, size) or box_outline(
            box, ink, boxes[keep], text_h
        )
        if mark is not None:
            out[field_id] = mark
    for field_id, box in (blanks or {}).items():
        if (outline := box_outline(box, None, boxes, text_h)) is not None:
            out[field_id] = outline
    return out
