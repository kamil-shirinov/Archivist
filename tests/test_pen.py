"""Pen loops (export/pen.py): hand-built pages whose words are obvious, and every loop in the
committed bundles.

No model, no network. The geometry is checked here by a measure that shares no code with the fit:
the distance from a loop's path, drawn as the UI draws it, to the boxes of ink.
"""

import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from archivist.export import bundle, pen
from archivist.schema import BBox

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted(p.parent.name for p in (ROOT / bundle.BUNDLES_DIR).glob("*/" + bundle.BUNDLE_FILE))

# What a loop must leave between the stroke's edge and a box of ink, in page pixels.
OWN_CLEAR = 1.5  # its own ink: a margin
UNDERLINE_CLEAR = 1.0  # an underline sits close beneath
NEIGHBOUR_CLEAR = 0.5  # every other word: not touched


# --- a measure of a loop that shares nothing with the fit -----------------------------------------


def path_points(d: str, step: float = 1.0) -> np.ndarray:
    """The points of an SVG path of straight segments, "M x y L x y ...", every `step` pixels."""
    assert d.startswith("M"), d
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    assert len(nums) % 2 == 0
    corners = np.array(nums).reshape(-1, 2)
    out = [corners[:1]]
    for a, b in zip(corners, corners[1:], strict=False):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / step)))
        out.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    return np.vstack(out)


def distance_to_box(points: np.ndarray, box) -> float:
    """The shortest distance from any of the points to the box (0 inside it)."""
    x0, y0, x1, y1 = box
    dx = np.maximum(np.maximum(x0 - points[:, 0], points[:, 0] - x1), 0)
    dy = np.maximum(np.maximum(y0 - points[:, 1], points[:, 1] - y1), 0)
    return float(np.hypot(dx, dy).min())


def encloses(points: np.ndarray, x: float, y: float) -> bool:
    """Whether (x, y) lies inside the closed polygon the points make (even-odd rule)."""
    px, py = points[:, 0], points[:, 1]
    qx, qy = np.roll(px, -1), np.roll(py, -1)
    crossing = (py > y) != (qy > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = px + (y - py) * (qx - px) / (qy - py)
    return bool((crossing & (x < at)).sum() % 2)


def centre_in(word, box, slack: float = 1.0) -> bool:
    cx, cy = (word[0] + word[2]) / 2, (word[1] + word[3]) / 2
    return box[0] - slack <= cx <= box[2] + slack and box[1] - slack <= cy <= box[3] + slack


def problems(loop: dict, words: list[list[int]]) -> list[str]:
    """Why a bundle's loop does not clear its own ink and every other word, if it doesn't."""
    ink, half = loop["ink"], loop["width"] / 2
    points = path_points(loop["d"])
    found = []
    if loop["kind"] == "loop":
        if not all(encloses(points, x, y) for x in (ink[0], ink[2]) for y in (ink[1], ink[3])):
            found.append("does not go round its ink")
        own = distance_to_box(points, ink) - half
        if own < OWN_CLEAR:
            found.append(f"{own:.2f}px from its own ink, wanted {OWN_CLEAR}")
    else:
        if points[:, 1].min() < ink[3]:
            found.append("an underline above the bottom of its ink")
        own = distance_to_box(points, ink) - half
        if own < UNDERLINE_CLEAR:
            found.append(f"{own:.2f}px under its own ink, wanted {UNDERLINE_CLEAR}")
    lo, hi = points.min(axis=0) - 40, points.max(axis=0) + 40
    for word in words:
        if centre_in(word, ink):
            continue  # a word of its own ink
        if word[2] < lo[0] or word[0] > hi[0] or word[3] < lo[1] or word[1] > hi[1]:
            continue
        gap = distance_to_box(points, word) - half
        if gap < NEIGHBOUR_CLEAR:
            found.append(f"{gap:.2f}px from the word at {word}, wanted {NEIGHBOUR_CLEAR}")
    return found


# --- pages built by hand --------------------------------------------------------------------------

GLYPH, GAP, SPACE, HEIGHT = 9, 5, 22, 16  # px: a glyph's width, between glyphs, between words


def _glyph(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    """An H: two stems and a bar, about half ink."""
    draw.rectangle([x, y, x + 2, y + HEIGHT - 1], fill=20)
    draw.rectangle([x + GLYPH - 3, y, x + GLYPH - 1, y + HEIGHT - 1], fill=20)
    draw.rectangle([x, y + HEIGHT // 2 - 1, x + GLYPH - 1, y + HEIGHT // 2 + 1], fill=20)


def word_at(draw: ImageDraw.ImageDraw, x: int, y: int, letters: int) -> tuple[int, int, int, int]:
    for i in range(letters):
        _glyph(draw, x + i * (GLYPH + GAP), y)
    return x, y, x + letters * GLYPH + (letters - 1) * GAP, y + HEIGHT


def page(size=(900, 400)) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("L", size, 235)
    return image, ImageDraw.Draw(image)


def found_words(image: Image.Image) -> tuple[float, list[tuple[int, int, int, int]]]:
    return pen.words(np.asarray(image))


def box_of(word, pad: int = 0) -> BBox:
    return BBox(x0=word[0] - pad, y0=word[1] - pad, x1=word[2] + pad, y1=word[3] + pad)


def near(a, b, tolerance: int = 3) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def as_bundle_loop(loop: pen.PenLoop) -> dict:
    return {
        "kind": loop.kind,
        "d": pen.path_data(loop.points),
        "width": loop.width,
        "ink": [round(x) for x in loop.ink],
    }


def test_words_are_found_with_the_pages_text_height_and_rules_dust_and_rings_are_not():
    image, draw = page()
    a = word_at(draw, 100, 100, 4)
    b = word_at(draw, 100 + 4 * (GLYPH + GAP) + SPACE, 100, 3)  # a space later: another word
    draw.line([40, 160, 860, 160], fill=20, width=2)  # a ruled line
    for x, y in ((300, 250), (420, 260), (500, 240)):  # dust
        draw.rectangle([x, y, x + 1, y + 1], fill=20)
    draw.ellipse([600, 220, 760, 360], outline=60, width=5)  # a ring, as a stain's edge
    text_height, found = found_words(image)
    assert text_height == HEIGHT
    assert len(found) == 2
    assert near(found[0], a) and near(found[1], b)


def test_a_boxed_word_gets_a_loop_that_clears_it_and_its_neighbours():
    image, draw = page()
    target = word_at(draw, 300, 180, 5)
    left = word_at(draw, 150, 180, 4)
    right = word_at(draw, 300 + 5 * (GLYPH + GAP) + SPACE, 180, 4)
    above = word_at(draw, 300, 120, 5)
    below = word_at(draw, 300, 245, 5)
    text_height, found = found_words(image)
    assert len(found) == 5
    fields = {"A": (box_of(target), None)}
    loops = pen.loops_for(fields, found, text_height)
    loop = as_bundle_loop(loops["A"])
    assert loop["kind"] == "loop"
    assert near(loops["A"].ink, target, 1)
    assert problems(loop, [list(w) for w in found]) == []
    assert all(box is not None for box in (left, right, above, below))


def test_a_loop_is_rounder_for_a_short_value_and_flatter_for_a_long_one():
    image, draw = page((1000, 400))
    short = word_at(draw, 100, 100, 2)
    long = word_at(draw, 100, 250, 20)
    text_height, found = found_words(image)
    fields = {"S": (box_of(short), None), "L": (box_of(long), None)}
    loops = pen.loops_for(fields, found, text_height)

    def fullness(loop: pen.PenLoop) -> float:
        """The loop's area as a share of its bounding box: a circle fills 0.785, a box 1."""
        pts = path_points(pen.path_data(loop.points))
        x, y = pts[:, 0], pts[:, 1]
        area = abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2
        return float(area / ((x.max() - x.min()) * (y.max() - y.min())))

    assert loops["S"].kind == loops["L"].kind == "loop"
    assert fullness(loops["S"]) < fullness(loops["L"])


def test_the_words_of_a_value_the_box_took_one_word_of_are_ringed_with_it():
    image, draw = page()
    label = word_at(draw, 100, 150, 3)  # a printed label to its left, outside the crop
    first = word_at(draw, 100 + 3 * (GLYPH + GAP) + SPACE, 150, 4)
    second = word_at(draw, first[2] + SPACE, 150, 4)
    text_height, found = found_words(image)
    assert len(found) == 3
    box, crop = box_of(second), BBox(x0=first[0] - 6, y0=140, x1=second[2] + 6, y1=180)
    loops = pen.loops_for({"A": (box, crop)}, found, text_height)
    assert near(loops["A"].ink, (first[0], first[1], second[2], second[3]), 1)
    assert not centre_in(label, loops["A"].ink)
    assert problems(as_bundle_loop(loops["A"]), [list(w) for w in found]) == []


def test_a_word_another_fields_box_holds_is_never_taken_into_a_value():
    image, draw = page()
    first = word_at(draw, 200, 150, 4)
    second = word_at(draw, first[2] + SPACE, 150, 4)
    text_height, found = found_words(image)
    crop = BBox(x0=190, y0=140, x1=second[2] + 10, y1=180)
    fields = {"A": (box_of(first), crop), "B": (box_of(second), crop)}
    loops = pen.loops_for(fields, found, text_height)
    assert near(loops["A"].ink, first, 1) and near(loops["B"].ink, second, 1)


def test_a_crowded_value_gets_an_underline_and_one_with_no_room_gets_none():
    image, draw = page()
    target = word_at(draw, 300, 150, 5)
    word_at(draw, 300 - 12 - 51, 150, 4)  # a word a space away on the left and on the right
    word_at(draw, target[2] + 12, 150, 4)
    word_at(draw, 300, 150 - HEIGHT - 6, 5)  # and a line of words close above
    text_height, found = found_words(image)
    assert len(found) == 4
    fields = {"A": (box_of(target), None)}
    loops = pen.loops_for(fields, found, text_height)
    assert loops["A"].kind == "underline"
    assert problems(as_bundle_loop(loops["A"]), [list(w) for w in found]) == []

    word_at(draw, 300, target[3] + 6, 5)  # and now close below too: nowhere is clear
    text_height, found = found_words(image)
    assert len(found) == 5
    assert pen.loops_for(fields, found, text_height) == {}


def test_a_loop_stays_on_the_page():
    image, draw = page((260, 120))
    target = word_at(draw, 20, 50, 14)  # a long value, close to the left edge
    text_height, found = found_words(image)
    fields = {"A": (box_of(target), None)}
    loop = pen.loops_for(fields, found, text_height, image.size)["A"]
    points = path_points(pen.path_data(loop.points))
    assert points.min() >= 0 and points[:, 0].max() <= 260 and points[:, 1].max() <= 120
    free = pen.loops_for(fields, found, text_height)["A"]  # with no page limit it is the loop
    assert free.kind == "loop"
    assert path_points(pen.path_data(free.points))[:, 0].min() < 0


def test_no_ink_in_the_box_no_loop():
    image, draw = page()
    word_at(draw, 100, 100, 3)
    text_height, found = found_words(image)
    empty = BBox(x0=500, y0=300, x1=600, y1=330)
    assert pen.loops_for({"A": (empty, None)}, found, text_height) == {}


def test_a_loop_depends_on_the_page_the_box_and_the_field_id_alone():
    image, draw = page()
    target = word_at(draw, 300, 180, 5)
    text_height, found = found_words(image)
    fields = {"A": (box_of(target), None)}
    again = pen.loops_for(fields, found, text_height)
    assert pen.loops_for(fields, found, text_height) == again
    other = pen.loops_for({"B": (box_of(target), None)}, found, text_height)
    assert other["B"].points != again["A"].points  # a hand is never the same twice
    assert near(other["B"].ink, again["A"].ink, 0)


def test_path_data_is_a_path_the_ui_can_draw_and_this_module_reads_back():
    d = pen.path_data([1.04, 2.0, 3.25, 4.96])
    assert d == "M1 2L3.2 5"
    assert np.allclose(path_points(d, 100), [[1, 2], [3.2, 5]])


# --- every loop in the committed bundles ----------------------------------------------------------


@pytest.mark.parametrize("run", BUNDLES)
def test_every_loop_in_the_bundle_clears_its_own_word_and_its_neighbours(run):
    data = json.loads((ROOT / bundle.BUNDLES_DIR / run / bundle.BUNDLE_FILE).read_text("utf-8"))
    words = {p["page_id"]: p["words"] for p in data["pages"]}
    kinds = {"loop": 0, "underline": 0}
    wrong = []
    for field in data["fields"]:
        loop = field["loop"]
        if loop is None:
            continue
        kinds[loop["kind"]] += 1
        for why in problems(loop, words[field["page_id"]]):
            wrong.append(f"{field['field_id']}: {why}")
    assert not wrong, f"{len(wrong)} of {sum(kinds.values())} loops: " + "; ".join(wrong[:8])
    assert (
        kinds["loop"] > 10 * kinds["underline"] > 0
    )  # the loop is the rule, the underline the exception


@pytest.mark.parametrize("run", BUNDLES)
def test_a_value_with_a_loop_has_a_box_and_something_written_in_it(run):
    data = json.loads((ROOT / bundle.BUNDLES_DIR / run / bundle.BUNDLE_FILE).read_text("utf-8"))
    for field in data["fields"]:
        if field["loop"] is not None:
            assert field["box"] is not None and field["value"], field["field_id"]
    flagged = [f for f in data["fields"] if f["status"] != "accepted"]
    assert sum(f["loop"] is not None for f in flagged) > 0.7 * len(flagged)
