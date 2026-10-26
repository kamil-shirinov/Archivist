"""Citation correction from the image alone, on a drawn page with a known drift."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from archivist.pipeline.citations import correct, theil_sen, word_boxes
from archivist.schema import BBox, Citation, ExtractedValue

PAGE = "page-1"
# truth = ALPHA * predicted + BETA, in y: wide enough that matching from the identity fails.
ALPHA, BETA = 1.25, -60.0
ROWS = 10
ROW_TOP, PITCH, TEXT = 100, 50, 24
COLUMNS = {"a": (100, 215), "b": (500, 552)}  # x ranges of the words in each column
BLANK_IN_B = {2, 5, 7}


def _word(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int) -> None:
    """Letter-like strokes 3 px wide, 4 px apart: ink, but never a solid block."""
    for x in range(x0, x1 - 2, 7):
        draw.rectangle([x, y0, x + 2, y0 + TEXT - 1], fill=40)


def _page() -> tuple[bytes, dict[str, BBox]]:
    image = Image.new("L", (1000, 800), 245)
    draw = ImageDraw.Draw(image)
    truth = {}
    for row in range(ROWS):
        y0 = ROW_TOP + PITCH * row
        for column, (x0, x1) in COLUMNS.items():
            if column == "b" and row in BLANK_IN_B:
                truth[f"{column}{row}"] = BBox(x0=x0, y0=y0, x1=x1, y1=y0 + TEXT)
                continue
            _word(draw, x0, y0, x1)
            truth[f"{column}{row}"] = BBox(x0=x0, y0=y0, x1=x1, y1=y0 + TEXT)
    _word(draw, 100, 40, 160)  # a column heading: a word no value claims
    draw.line([(20, 640), (980, 640)], fill=40, width=2)  # a ruled line
    for x, y in ((300, 300), (700, 420), (520, 380)):  # specks
        draw.point((x, y), fill=30)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), truth


def _predicted(box: BBox) -> BBox:
    """Where a drifting extractor puts the box: the inverse of the drift, a little off in x."""
    y0, y1 = ((v - BETA) / ALPHA for v in (box.y0, box.y1))
    return BBox(x0=box.x0 + 4, y0=round(y0), x1=box.x1 + 4, y1=round(y1))


def _values(truth: dict[str, BBox]) -> list[ExtractedValue]:
    values = []
    for key, box in truth.items():
        blank = key[0] == "b" and int(key[1:]) in BLANK_IN_B
        values.append(
            ExtractedValue(
                field_id=key,
                value="" if blank else "1.00",
                citation=Citation(page_id=PAGE, bbox=_predicted(box)),
            )
        )
    return values


def _centre(box: BBox) -> tuple[float, float]:
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def test_the_drift_is_wide_enough_that_nearest_ink_would_pick_the_wrong_line():
    _, truth = _page()
    bottom = truth[f"a{ROWS - 1}"]
    _, y_pred = _centre(_predicted(bottom))
    _, y_true = _centre(bottom)
    _, y_line_above = _centre(truth[f"a{ROWS - 2}"])
    assert abs(y_pred - y_line_above) < abs(y_pred - y_true)


def test_word_boxes_find_every_word_and_drop_rules_and_specks():
    image, truth = _page()
    gray = np.asarray(Image.open(io.BytesIO(image)), dtype=np.float32)
    words = word_boxes(gray, text_height=TEXT)
    inked = [b for k, b in truth.items() if not (k[0] == "b" and int(k[1:]) in BLANK_IN_B)]
    assert len(words) == len(inked) + 1  # and the heading
    for box in inked:
        assert (box.x0, box.y0, box.x1, box.y1) in words


def test_every_inked_box_lands_on_its_own_ink_and_blanks_move_with_the_fit():
    image, truth = _page()
    values = _values(truth)

    fix = correct(image, values)

    assert fix.alpha == pytest.approx(ALPHA, abs=0.01)
    assert fix.beta == pytest.approx(BETA, abs=3)
    assert (fix.inked, fix.matched) == (2 * ROWS - len(BLANK_IN_B),) * 2
    for value in fix.values:
        box, target = value.citation.bbox, truth[value.field_id]
        if value.value:
            assert box == target  # snapped to the word
        else:
            cx, cy = _centre(box)
            assert target.x0 <= cx < target.x1
            assert cy == pytest.approx(_centre(target)[1], abs=2)
    assert [v.field_id for v in fix.values] == [v.field_id for v in values]
    assert {v.value for v in fix.values} == {"", "1.00"}


def test_a_page_without_enough_ink_to_match_is_left_as_it_was():
    blank = io.BytesIO()
    Image.new("L", (400, 300), 245).save(blank, format="PNG")
    box = Citation(page_id=PAGE, bbox=BBox(x0=10, y0=10, x1=60, y1=30))
    values = [
        ExtractedValue(field_id="f1", value="12.00", citation=box),
        ExtractedValue(field_id="f2", value=None, citation=box, abstained=True),
        ExtractedValue(field_id="f3", value="", citation=None),
    ]
    for page in (blank.getvalue(), _page()[0]):
        fix = correct(page, values)
        assert fix.values == values
        assert fix.alpha is None and fix.matched == 0


def test_theil_sen_ignores_a_gross_outlier():
    x = np.arange(10, dtype=float) * 50
    y = 1.1 * x - 20
    y[3] += 400
    slope, intercept = theil_sen(x, y, min_dx=1)
    assert slope == pytest.approx(1.1)
    assert intercept == pytest.approx(-20)
