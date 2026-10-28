"""Plain image code for a printed table's ink: no model, no data of ours (P21b, P21c).

otsu() splits a page into ink and paper; runs() finds runs in a profile; without_long_runs()
clears ruled lines as unbroken strokes too long for a printed figure; rules() counts the ruled
lines. The thresholds were set by looking at development pages (results/templates/grid_dev.md).
"""

from __future__ import annotations

import numpy as np

RULE_SHARE = 0.25
DOWN_RUN, ACROSS_RUN = 60, 150
ROW_LEVEL, ROW_GAP, MIN_ROW = 0.15, 2, 6
COL_LEVEL, COL_GAP, MIN_COL = 0.15, 15, 8


def runs(flags: np.ndarray, gap: int, minimum: int) -> list[tuple[int, int]]:
    """The runs of True in flags, [start, end), those closer than gap merged, those shorter than
    minimum dropped."""
    found: list[list[int]] = []
    for i in np.flatnonzero(flags):
        if found and i - found[-1][1] <= gap:
            found[-1][1] = i + 1
        else:
            found.append([int(i), int(i) + 1])
    return [(a, b) for a, b in found if b - a >= minimum]


def otsu(gray: np.ndarray) -> int:
    """The darkest grey level that is still paper's complement: ink is at or below it
    (Otsu's method)."""
    counts = np.bincount(gray.ravel(), minlength=256).astype(float)
    levels = np.arange(256)
    weight = np.cumsum(counts)
    mean = np.cumsum(counts * levels)
    total, grand = weight[-1], mean[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (grand * weight - total * mean) ** 2 / (weight * (total - weight))
    return int(np.nanargmax(between[:-1]))


def _longest(lines: np.ndarray) -> np.ndarray:
    """Each row's longest unbroken run of True."""
    return np.array([max((b - a for a, b in runs(line, 0, 1)), default=0) for line in lines])


def rules(ink: np.ndarray) -> tuple[int, int]:
    """How many horizontal and vertical ruled lines the page has."""
    height, width = ink.shape
    across = runs(_longest(ink) >= RULE_SHARE * width, 1, 1)
    down = runs(_longest(ink.T) >= RULE_SHARE * height, 1, 1)
    return len(across), len(down)


def without_long_runs(ink: np.ndarray, length: int) -> np.ndarray:
    """ink with every unbroken vertical run of at least length pixels cleared."""
    out = ink.copy()
    for x in range(ink.shape[1]):
        for a, b in runs(ink[:, x], 0, length):
            out[a:b, x] = False
    return out
