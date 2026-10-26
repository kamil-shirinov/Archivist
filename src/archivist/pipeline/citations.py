"""Citation correction from the page image alone: the S1+ink strategy.

The extractor's boxes drift down a page by a scale and an offset that differ from page to page
(results/runs/baseline-dev-v1/analysis.md, section 2), so a box can sit two or three lines away
from its ink. This puts each box back on its ink without any knowledge of the form's layout:

1. Binarise the page against its local paper brightness, drop ruled lines and specks, and smear
   the ink sideways into word boxes.
2. Group the predicted boxes into columns by horizontal overlap; a word belongs to the column its
   centre falls in.
3. Seed y = α·y_pred + β by a vote over a grid of (α, β): how many inked values land on a word of
   their column. Blank cells make each column's pattern of ink distinctive, so a shift by one line
   loses votes. Ties go to the smallest move.
4. Match predicted boxes to words by order within each column (a monotone alignment that may skip
   words, such as stamps and stains, and values with no word nearby), and fit α and β to the
   matched pairs with the Theil–Sen estimator; twice, re-aligning under the first fit.
5. Move every box by the fit, then snap each matched one to its word box.

Only values with something written ("" is a blank cell, None an unreadable one) take part in the
matching; every box still moves with the fit. A page with too few matches is left as it was.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from archivist.schema import BBox, Citation, ExtractedValue

BACKGROUND_BLOCK = 32  # px; the paper brightness is the 90th percentile of each block
INK_RATIO = 0.75  # a pixel is ink when darker than this share of the paper around it
# Sizes relative to the text height, the median height of the predicted boxes.
RULE_RUN_X = 2.5  # a horizontal run of ink at least this long is a ruled line
RULE_RUN_Y = 1.8  # likewise a vertical run
SPECK_AREA = 0.02  # components smaller than this (× height²) are specks
WORD_GAP = 0.35  # ink closer than this sideways joins into one word
WORD_MIN_HEIGHT, WORD_MAX_HEIGHT = 0.35, 2.5
WORD_MIN_INK = 0.1  # × height²
WORD_MAX_FILL = 0.8  # a solid block (a scanner edge, a blot) is not a word
# The seed grid, and the matching.
ALPHAS = np.arange(0.8, 1.3001, 0.005)
BETA_RANGE = 0.2  # β within ± this share of the page height, in 2 px steps
VOTE_TOLERANCE = 0.5  # a value lands on a word whose centre is within this (× height)
MATCH_GATE = 1.0  # pairs further apart than this (× height) are never matched
SKIP_VALUE = 1.0  # cost of leaving a value unmatched (× height)
SKIP_WORD = 0.05  # cost of passing over a word (× height)
X_WEIGHT = 0.25  # horizontal distance counts this much in a match's cost
MIN_MATCHES = 3


@dataclass(frozen=True)
class Correction:
    values: list[ExtractedValue]
    alpha: float | None  # None when the page was left as it was
    beta: float | None
    inked: int  # values that took part in the matching
    matched: int  # of those, the ones snapped to a word


Box = tuple[float, float, float, float]


def _centre_y(box: Box) -> float:
    return (box[1] + box[3]) / 2


def _centre_x(box: Box) -> float:
    return (box[0] + box[2]) / 2


def ink_mask(gray: np.ndarray) -> np.ndarray:
    """True where a pixel is darker than INK_RATIO of the paper around it."""
    h, w = gray.shape
    bh, bw = -(-h // BACKGROUND_BLOCK), -(-w // BACKGROUND_BLOCK)
    padded = np.pad(
        gray, ((0, bh * BACKGROUND_BLOCK - h), (0, bw * BACKGROUND_BLOCK - w)), mode="edge"
    )
    blocks = padded.reshape(bh, BACKGROUND_BLOCK, bw, BACKGROUND_BLOCK).transpose(0, 2, 1, 3)
    paper = np.percentile(blocks.reshape(bh, bw, -1), 90, axis=2).astype(np.float32)
    paper = np.asarray(Image.fromarray(paper).resize((w, h), Image.Resampling.BILINEAR))
    return gray < INK_RATIO * np.maximum(paper, 1.0)


def _runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Horizontal runs of True, ordered by row: row, start and end (exclusive) of each."""
    edges = np.diff(np.pad(mask, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    rows, starts = np.nonzero(edges == 1)
    _, ends = np.nonzero(edges == -1)
    return rows, starts, ends


def _without_long_runs(mask: np.ndarray, length: int) -> np.ndarray:
    rows, starts, ends = _runs(mask)
    out = mask.copy()
    for row, start, end in zip(rows, starts, ends, strict=True):
        if end - start >= length:
            out[row, start:end] = False
    return out


def components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """8-connected components as (x0, y0, x1, y1, pixels), from runs joined across rows."""
    rows, starts, ends = _runs(mask)
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first = np.searchsorted(rows, np.arange(mask.shape[0] + 1))
    for row in range(1, mask.shape[0]):
        i, i_end = first[row - 1], first[row]
        j, j_end = first[row], first[row + 1]
        while i < i_end and j < j_end:
            if starts[i] <= ends[j] and starts[j] <= ends[i]:  # touching diagonally counts
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
            if ends[i] < ends[j]:
                i += 1
            else:
                j += 1

    boxes: dict[int, list[int]] = {}
    for k, (row, start, end) in enumerate(zip(rows, starts, ends, strict=True)):
        box = boxes.setdefault(find(k), [start, row, end, row + 1, 0])
        box[0], box[1] = min(box[0], start), min(box[1], row)
        box[2], box[3] = max(box[2], end), max(box[3], row + 1)
        box[4] += end - start
    return [(int(a), int(b), int(c), int(d), int(n)) for a, b, c, d, n in boxes.values()]


def _dilate_x(mask: np.ndarray, radius: int) -> np.ndarray:
    total = np.cumsum(np.pad(mask, ((0, 0), (radius + 1, radius))).astype(np.int32), axis=1)
    return (total[:, 2 * radius + 1 :] - total[:, : -2 * radius - 1]) > 0


def word_boxes(gray: np.ndarray, text_height: float) -> list[Box]:
    """Boxes around the words of ink on a page, whose text is about text_height pixels tall."""
    mask = ink_mask(gray)
    mask = _without_long_runs(mask, round(RULE_RUN_X * text_height))
    mask = _without_long_runs(mask.T, round(RULE_RUN_Y * text_height)).T
    ink = np.zeros_like(mask)
    for x0, y0, x1, y1, pixels in components(mask):
        if pixels >= SPECK_AREA * text_height**2:
            ink[y0:y1, x0:x1] |= mask[y0:y1, x0:x1]
    radius = max(1, round(WORD_GAP * text_height))
    words = []
    for x0, y0, x1, y1, _ in components(_dilate_x(ink, radius)):
        x0, x1 = x0 + radius, x1 - radius  # the smear widened it by radius on each side
        height = y1 - y0
        pixels = int(ink[y0:y1, x0:x1].sum())
        if (
            WORD_MIN_HEIGHT * text_height <= height <= WORD_MAX_HEIGHT * text_height
            and pixels >= WORD_MIN_INK * text_height**2
            and pixels <= WORD_MAX_FILL * (x1 - x0) * height
        ):
            words.append((float(x0), float(y0), float(x1), float(y1)))
    return words


def _columns(boxes: list[Box]) -> list[tuple[float, float, list[int]]]:
    """Groups of boxes whose horizontal extents overlap, as (x0, x1, indices)."""
    columns: list[tuple[float, float, list[int]]] = []
    for i in sorted(range(len(boxes)), key=lambda k: boxes[k][0]):
        x0, _, x1, _ = boxes[i]
        if columns and x0 < columns[-1][1]:
            c0, c1, members = columns[-1]
            columns[-1] = (c0, max(c1, x1), [*members, i])
        else:
            columns.append((x0, x1, [i]))
    return columns


def _seed(
    ys: list[np.ndarray], word_ys: list[np.ndarray], page_height: int, text_height: float
) -> tuple[float, float]:
    """The (α, β) on the grid that lands the most values on a word, nearest the identity."""
    betas = np.arange(-BETA_RANGE * page_height, BETA_RANGE * page_height + 1, 2.0)
    votes = np.zeros((len(ALPHAS), len(betas)))
    for y, wy in zip(ys, word_ys, strict=True):
        if not len(wy) or not len(y):
            continue
        moved = ALPHAS[:, None, None] * y[None, None, :] + betas[None, :, None]
        at = np.searchsorted(wy, moved)
        below = np.abs(moved - wy[np.clip(at - 1, 0, len(wy) - 1)])
        above = np.abs(moved - wy[np.clip(at, 0, len(wy) - 1)])
        votes += (np.minimum(below, above) <= VOTE_TOLERANCE * text_height).sum(axis=2)
    y_all = np.concatenate(ys)
    shift = np.abs((ALPHAS[:, None, None] - 1) * y_all + betas[None, :, None]).mean(axis=2)
    best = np.argwhere(votes == votes.max())
    a, b = min(best, key=lambda ab: shift[ab[0], ab[1]])
    return float(ALPHAS[a]), float(betas[b])


def _align(
    values: list[Box], words: list[Box], alpha: float, beta: float, text_height: float
) -> list[tuple[int, int]]:
    """Monotone matching of values to words within one column, as (value, word) index pairs.

    Both are taken top to bottom; a pair costs its distance once the value is moved by the fit,
    and a value may go unmatched or a word be passed over at a price.
    """
    vs = sorted(range(len(values)), key=lambda i: _centre_y(values[i]))
    ws = sorted(range(len(words)), key=lambda j: _centre_y(words[j]))
    gate, skip_v, skip_w = (k * text_height for k in (MATCH_GATE, SKIP_VALUE, SKIP_WORD))
    n, m = len(vs), len(ws)
    cost = np.full((n + 1, m + 1), np.inf)
    move = np.zeros((n + 1, m + 1), dtype=np.int8)  # 1 skip value, 2 skip word, 3 match
    cost[0, :] = np.arange(m + 1) * skip_w
    cost[:, 0] = np.arange(n + 1) * skip_v
    move[1:, 0], move[0, 1:] = 1, 2
    for a in range(1, n + 1):
        value = values[vs[a - 1]]
        y = alpha * _centre_y(value) + beta
        for b in range(1, m + 1):
            word = words[ws[b - 1]]
            options = [cost[a - 1, b] + skip_v, cost[a, b - 1] + skip_w]
            dy = abs(y - _centre_y(word))
            if dy <= gate:
                options.append(
                    cost[a - 1, b - 1] + dy + X_WEIGHT * abs(_centre_x(value) - _centre_x(word))
                )
            choice = int(np.argmin(options))
            cost[a, b], move[a, b] = options[choice], choice + 1
    pairs = []
    a, b = n, m
    while a or b:
        step = move[a, b]
        if step == 3:
            pairs.append((vs[a - 1], ws[b - 1]))
        a, b = (a - 1, b - 1) if step == 3 else (a - 1, b) if step == 1 else (a, b - 1)
    return pairs[::-1]


def theil_sen(x: np.ndarray, y: np.ndarray, min_dx: float) -> tuple[float, float]:
    """Median slope over pairs at least min_dx apart in x, and the median intercept."""
    i, j = np.triu_indices(len(x), k=1)
    far = np.abs(x[j] - x[i]) >= min_dx
    slope = float(np.median((y[j] - y[i])[far] / (x[j] - x[i])[far])) if far.any() else 1.0
    return slope, float(np.median(y - slope * x))


def _box(value: ExtractedValue) -> Box:
    bbox = value.citation.bbox
    return (bbox.x0, bbox.y0, bbox.x1, bbox.y1)


def _bbox(box: Box, width: int, height: int) -> BBox:
    x0, y0 = max(0, int(np.floor(box[0]))), max(0, int(np.floor(box[1])))
    x1, y1 = min(width, int(np.ceil(box[2]))), min(height, int(np.ceil(box[3])))
    return BBox(x0=x0, y0=y0, x1=max(x1, x0 + 1), y1=max(y1, y0 + 1))


def correct(image: bytes, values: list[ExtractedValue]) -> Correction:
    """Every cited value of one page, its box moved by the page's fit and snapped to its ink."""
    gray_image = Image.open(io.BytesIO(image)).convert("L")
    width, height = gray_image.size
    cited = [i for i, v in enumerate(values) if v.citation is not None]
    inked = [i for i in cited if values[i].value]
    unchanged = Correction(list(values), None, None, len(inked), 0)
    if len(inked) < MIN_MATCHES:
        return unchanged
    boxes = {i: _box(values[i]) for i in cited}
    text_height = float(np.median([boxes[i][3] - boxes[i][1] for i in inked]))
    words = word_boxes(np.asarray(gray_image, dtype=np.float32), text_height)

    columns = []  # (indices into values, indices into words), per column
    for x0, x1, members in _columns([boxes[i] for i in inked]):
        in_column = [j for j, w in enumerate(words) if x0 <= _centre_x(w) < x1]
        columns.append(([inked[k] for k in members], in_column))
    ys = [np.array([_centre_y(boxes[i]) for i in vs]) for vs, _ in columns]
    word_ys = [np.sort([_centre_y(words[j]) for j in ws]) for _, ws in columns]
    alpha, beta = _seed(ys, word_ys, height, text_height)

    matches: dict[int, int] = {}
    for _ in range(2):
        matches = {}
        for vs, ws in columns:
            pairs = _align([boxes[i] for i in vs], [words[j] for j in ws], alpha, beta, text_height)
            matches.update({vs[a]: ws[b] for a, b in pairs})
        if len(matches) < MIN_MATCHES:
            return unchanged
        x = np.array([_centre_y(boxes[i]) for i in matches])
        y = np.array([_centre_y(words[j]) for j in matches.values()])
        alpha, beta = theil_sen(x, y, min_dx=text_height)

    out = list(values)
    for i in cited:
        if i in matches:
            box = words[matches[i]]
        else:
            x0, y0, x1, y1 = boxes[i]
            box = (x0, alpha * y0 + beta, x1, alpha * y1 + beta)
        citation = Citation(page_id=values[i].citation.page_id, bbox=_bbox(box, width, height))
        out[i] = values[i].model_copy(update={"citation": citation})
    return Correction(out, alpha, beta, len(inked), len(matches))
