import io
import json
import random

import numpy as np
import pytest
from PIL import Image, ImageDraw

from archivist.schema import BBox, PageGT
from archivist.synth import degrade, render
from archivist.synth.world import generate_world

SEED = 7
SEVERITIES = range(len(degrade.LEVELS))
DARKER = 40  # grey levels below the page's median paper that count as ink
MIN_INK_PIXELS = 20


@pytest.fixture(scope="module")
def clean():
    world = generate_world(SEED)
    return [
        render.render_card(world.cards[0], random.Random(SEED)),
        render.render_memo(world.memos[0], random.Random(SEED)),
    ]


@pytest.fixture(scope="module")
def degraded(clean):
    """(severity, clean ground truth, degraded image, degraded ground truth) for every page."""
    return [
        (severity, gt, *degrade.degrade_page(image, gt, severity, random.Random(f"{SEED}:{severity}")))
        for severity in SEVERITIES
        for image, gt in clean
    ]


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _name(field_id: str) -> str:
    return field_id.rsplit(":", 1)[1]


def test_size_severity_values_and_artefact_counts(degraded):
    for severity, before, image, gt in degraded:
        assert image.size == (gt.width, gt.height) == (before.width, before.height)
        assert gt.severity == severity
        assert [(f.field_id, f.printed) for f in gt.fields] == [
            (f.field_id, f.printed) for f in before.fields
        ]
        lo, hi = degrade.LEVELS[severity].artefacts
        extra = [a for a in gt.artefacts if a.kind != "signature"]
        assert lo <= len(extra) <= hi, (severity, gt.page_id)
        assert len({a.artefact_id for a in gt.artefacts}) == len(gt.artefacts)


def test_boxes_inside_image(degraded):
    for severity, _, _, gt in degraded:
        for item, box in [(f.field_id, f.bbox) for f in gt.fields] + [
            (a.artefact_id, a.bbox) for a in gt.artefacts
        ]:
            assert 0 <= box.x0 and 0 <= box.y0, (severity, item)
            assert box.x1 <= gt.width and box.y1 <= gt.height, (severity, item)


def test_severity_0_keeps_every_field_box(degraded):
    for severity, before, _, gt in degraded:
        if severity == 0:
            assert [f.bbox for f in gt.fields] == [f.bbox for f in before.fields]


def test_ink_survives_in_every_filled_box(degraded):
    for severity, _, image, gt in degraded:
        lum = np.asarray(image.convert("L"), np.int16)
        paper = int(np.median(lum))
        for f in gt.fields:
            if not f.printed:
                continue
            region = lum[f.bbox.y0 : f.bbox.y1, f.bbox.x0 : f.bbox.x1]
            ink = int((region < paper - DARKER).sum())
            assert ink >= MIN_INK_PIXELS, (severity, f.field_id, ink)


def test_quarter_turn_lands_where_expected():
    # Counter-clockwise about (50, 50): the box's left edge becomes its bottom edge.
    box = BBox(x0=10, y0=20, x1=30, y1=60)
    assert degrade.map_bbox(box, 90, (100, 100)) == BBox(x0=20, y0=70, x1=60, y1=90)
    assert degrade.map_bbox(box, 0, (100, 100)) == box


def test_mapped_box_matches_rotated_pixels():
    size, box = (400, 300), BBox(x0=150, y0=100, x1=250, y1=160)
    for angle in (-7.0, 2.5, 30.0):
        image = Image.new("RGB", size, (255, 255, 255))
        ImageDraw.Draw(image).rectangle((box.x0, box.y0, box.x1 - 1, box.y1 - 1), fill=(0, 0, 0))
        dark = np.asarray(degrade.rotate(image, angle).convert("L")) < 128
        ys, xs = np.nonzero(dark)
        found = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        mapped = degrade.map_bbox(box, angle, size)
        expected = (mapped.x0, mapped.y0, mapped.x1, mapped.y1)
        assert all(abs(a - b) <= 1 for a, b in zip(found, expected, strict=True)), angle


def test_mapped_box_is_clipped_to_the_image():
    # At 45° the top-left corner swings to x = 50 - 50·√2 ≈ -20.7, off the left edge.
    corner = BBox(x0=0, y0=0, x1=40, y1=40)
    assert degrade.map_bbox(corner, 45, (100, 100)) == BBox(x0=0, y0=21, x1=36, y1=79)


def test_occluded_by_follows_the_ten_percent_rule(degraded):
    for severity, _, _, gt in degraded:
        for f in gt.fields:
            expected = []
            for a in gt.artefacts:
                w = min(f.bbox.x1, a.bbox.x1) - max(f.bbox.x0, a.bbox.x0)
                h = min(f.bbox.y1, a.bbox.y1) - max(f.bbox.y0, a.bbox.y0)
                if w > 0 and h > 0 and w * h / f.bbox.area() >= 0.10:
                    expected.append(a.artefact_id)
            assert f.occluded_by == expected, (severity, f.field_id)


def _money_covered(gt: PageGT) -> bool:
    covering = {a.artefact_id for a in gt.artefacts if a.kind in ("stamp", "stain")}
    return any(
        covering.intersection(f.occluded_by)
        for f in gt.fields
        if _name(f.field_id) in degrade.MONEY_FIELDS
    )


def test_severity_3_covers_a_money_field(degraded, clean):
    assert all(_money_covered(gt) for severity, _, _, gt in degraded if severity == 3)
    for k in range(3):
        for image, gt in clean:
            _, out = degrade.degrade_page(image, gt, 3, random.Random(f"extra:{k}"))
            assert _money_covered(out), (k, gt.page_id)


def test_every_memo_has_one_signature_clear_of_fields(degraded):
    for severity, _, _, gt in degraded:
        signatures = [a for a in gt.artefacts if a.kind == "signature"]
        if gt.doc_type == "ledger":
            assert signatures == []
            continue
        assert len(signatures) == 1, severity
        for f in gt.fields:
            assert degrade.overlap(signatures[0].bbox, f.bbox) == 0, (severity, f.field_id)


def test_same_rng_same_png(clean):
    for image, gt in clean:
        first = degrade.degrade_page(image, gt, 3, random.Random(SEED))
        second = degrade.degrade_page(image, gt, 3, random.Random(SEED))
        assert _png(first[0]) == _png(second[0])
        assert first[1] == second[1]


def _quantization(quality: int) -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="JPEG", quality=quality)
    with Image.open(io.BytesIO(buffer.getvalue())) as image:
        return image.quantization


@pytest.mark.parametrize("severity", SEVERITIES)
def test_scan_page_returns_a_jpeg_at_the_levels_quality(clean, severity):
    for image, gt in clean:
        jpeg, scan_gt = degrade.scan_page(image, gt, severity, random.Random(SEED))
        with Image.open(io.BytesIO(jpeg)) as scan:
            assert scan.format == "JPEG"
            assert scan.size == (gt.width, gt.height)
            assert scan.quantization == _quantization(degrade.LEVELS[severity].jpeg_quality)
        assert scan_gt.severity == severity


def test_same_rng_same_jpeg_bytes(clean):
    for image, gt in clean:
        first = degrade.scan_page(image, gt, 3, random.Random(SEED))
        second = degrade.scan_page(image, gt, 3, random.Random(SEED))
        assert first[0] == second[0]
        assert first[1] == second[1]


def test_degrade_page_is_scan_page_decoded(clean):
    for image, gt in clean:
        jpeg, scan_gt = degrade.scan_page(image, gt, 3, random.Random(SEED))
        decoded, degraded_gt = degrade.degrade_page(image, gt, 3, random.Random(SEED))
        assert degraded_gt == scan_gt
        with Image.open(io.BytesIO(jpeg)) as scan:
            assert _png(scan.convert("RGB")) == _png(decoded)


def test_cli_writes_every_severity(tmp_path):
    degrade.main(["--seed", str(SEED), "--out", str(tmp_path)])
    for severity in SEVERITIES:
        root = tmp_path / f"sev{severity}"
        pngs = sorted(p.name for p in (root / "pages").glob("*.png"))
        assert len(pngs) == 2
        assert sorted(p.name for p in (root / "overlays").glob("*.png")) == pngs
        for path in (root / "pages").glob("*.json"):
            gt = PageGT.model_validate(json.loads(path.read_text()))
            assert gt.severity == severity
            assert (root / gt.image_path).is_file()
