"""Scan degradation: ageing, scanner geometry and artefacts, with ground truth kept exact.

degrade_page takes a clean render from render.py. Paper-side effects (ink bleed and fade,
artefacts, yellowing, a fold, grain) are applied in page coordinates; the page is then
"scanned": rotated about its centre, lit unevenly, blurred, resampled, speckled and passed
through JPEG. Only the rotation moves anything, so every field and artefact box is mapped
through that one rotation. Everything is procedural, and all randomness comes from the rng
passed in.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import math
import random
import string
from pathlib import Path
from typing import Literal, NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from archivist.schema import Artefact, BBox, PageGT
from archivist.synth import render
from archivist.synth.world import generate_world

LID_GREY = (128, 128, 124)  # what the scanner sees where the rotated page leaves the glass
YELLOWING = np.array([0.0, 0.035, 0.13], np.float32)  # share of R, G, B lost by aged paper
SIGNATURE_INK = (24, 32, 80)
PENCIL = (88, 88, 94)
STAIN_BROWN = (128, 82, 40)
STAMP_INKS = ((178, 34, 46), (96, 52, 150))  # red, violet
STAMP_WORDS = ("PAID", "ENTERED", "CHECKED")
STAMP_FONT = "courierprime/CourierPrime-Bold.ttf"
INITIALS_FONT = "homemadeapple/HomemadeApple-Regular.ttf"
SIGNATURE_LINE_X = (290, 760)  # x extent of the memo's "Authorised by" rule in render.py

MONEY_FIELDS = frozenset(
    {"debit", "credit", "balance", "brought_forward", "carried_forward", "amount"}
)
OCCLUSION_PERCENT = 10  # an artefact occludes a field it covers by at least this much
ALPHA_FLOOR = 8  # artefact alpha below this is dropped, so a box holds only visible marks
MARGIN = 20  # artefacts stay this far inside the page
SS = 3  # supersampling for pen strokes
ARTEFACT_OUTLINE = (0, 0, 0)

ArtefactKind = Literal["stamp", "signature", "stain", "handwritten_amendment"]
RANDOM_KINDS: tuple[ArtefactKind, ...] = ("stamp", "stain", "handwritten_amendment")
RANDOM_WEIGHTS = (4, 3, 3)


class Level(NamedTuple):
    grain: float  # std of the paper grain, grey levels
    yellow: float  # strength of the ageing tint, 0–1
    fade: float  # share of ink contrast lost
    bleed: float  # strength of ink spreading into the fibres, 0–1
    fold: bool
    lighting: float  # deepest darkening by uneven illumination, 0–1
    blur: float  # Gaussian radius, px
    rescale: float  # downscale to this share and back; 1 for none
    noise: float  # std of the scanner's per-pixel noise, grey levels
    speckle: float  # dust specks per pixel
    max_rotation: float  # degrees, either way
    jpeg_quality: int
    artefacts: tuple[int, int]  # inclusive count range, not counting the memo signature
    cover_money: bool  # the first artefact is a stamp or stain over a money field


# Each level keeps what the one below has and adds or strengthens the listed effects.
LEVELS = (
    Level(  # 0 clean scan
        grain=1.5, yellow=0.0, fade=0.0, bleed=0.0, fold=False, lighting=0.0, blur=0.0,
        rescale=1.0, noise=0.0, speckle=0.0, max_rotation=0.0, jpeg_quality=90,
        artefacts=(0, 0), cover_money=False,
    ),
    Level(  # 1 light ageing
        grain=2.5, yellow=0.5, fade=0.0, bleed=0.0, fold=False, lighting=0.0, blur=0.5,
        rescale=1.0, noise=3.0, speckle=0.0, max_rotation=0.5, jpeg_quality=80,
        artefacts=(0, 1), cover_money=False,
    ),
    Level(  # 2 moderate
        grain=3.0, yellow=0.7, fade=0.3, bleed=0.0, fold=False, lighting=0.12, blur=1.0,
        rescale=1.0, noise=4.0, speckle=0.00015, max_rotation=1.5, jpeg_quality=65,
        artefacts=(1, 2), cover_money=False,
    ),
    Level(  # 3 heavy
        grain=4.0, yellow=1.0, fade=0.5, bleed=0.5, fold=True, lighting=0.18, blur=1.0,
        rescale=0.6, noise=6.0, speckle=0.0005, max_rotation=2.5, jpeg_quality=50,
        artefacts=(2, 4), cover_money=True,
    ),
)  # fmt: skip


# --- geometry ---------------------------------------------------------------------------


def rotate(image: Image.Image, angle: float) -> Image.Image:
    """Rotate counter-clockwise by angle degrees about the centre, keeping the size."""
    return image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=LID_GREY)


def map_point(x: float, y: float, angle: float, size: tuple[int, int]) -> tuple[float, float]:
    """Where rotate() sends the page point (x, y); pixel corners sit on integers."""
    cx, cy = size[0] / 2, size[1] / 2
    a = math.radians(angle)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) + dy * math.sin(a), cy - dx * math.sin(a) + dy * math.cos(a)


def map_bbox(box: BBox, angle: float, size: tuple[int, int]) -> BBox:
    """Axis-aligned box of the rotated corners, clipped to the image."""
    corners = [map_point(x, y, angle, size) for x in (box.x0, box.x1) for y in (box.y0, box.y1)]
    xs = [round(x, 6) for x, _ in corners]  # so float noise never moves a box by a pixel
    ys = [round(y, 6) for _, y in corners]
    return BBox(
        x0=max(0, math.floor(min(xs))),
        y0=max(0, math.floor(min(ys))),
        x1=min(size[0], math.ceil(max(xs))),
        y1=min(size[1], math.ceil(max(ys))),
    )


def overlap(a: BBox, b: BBox) -> int:
    """Area shared by two boxes."""
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(w, 0) * max(h, 0)


def occludes(artefact: BBox, field: BBox) -> bool:
    return 100 * overlap(artefact, field) >= OCCLUSION_PERCENT * field.area()


# --- procedural textures ----------------------------------------------------------------


def _smooth_noise(nrng: np.random.Generator, size: tuple[int, int], cell: int) -> np.ndarray:
    """Values in [0, 1] varying over roughly `cell` pixels, shape (height, width)."""
    w, h = size
    small = nrng.random((h // cell + 2, w // cell + 2))
    image = Image.fromarray((small * 255).astype(np.uint8))
    return np.asarray(image.resize(size, Image.Resampling.BICUBIC), np.float32) / 255


def _to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).round().astype(np.uint8))


def _patch(ink: tuple[int, int, int], alpha: np.ndarray) -> Image.Image:
    """An RGBA patch of one ink colour; alpha is on the 0–255 scale."""
    a = np.clip(alpha, 0, 255).round().astype(np.uint8)
    a[a < ALPHA_FLOOR] = 0
    rgba = np.empty((*a.shape, 4), np.uint8)
    rgba[..., :3] = ink
    rgba[..., 3] = a
    return Image.fromarray(rgba)


def _spline(points: list[tuple[float, float]], steps: int = 8) -> list[tuple[float, float]]:
    """Catmull-Rom curve through the points."""
    p = np.array([points[0], *points, points[-1]], np.float64)
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1 : i + 3]
        for t in np.linspace(0, 1, steps, endpoint=False):
            q = 0.5 * (
                2 * p1
                + (p2 - p0) * t
                + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
                + (3 * p1 - p0 - 3 * p2 + p3) * t**3
            )
            out.append((float(q[0]), float(q[1])))
    out.append((float(p[-2][0]), float(p[-2][1])))
    return out


def _stroke(size: tuple[int, int], points: list[tuple[float, float]], width: int) -> np.ndarray:
    """An antialiased pen stroke through the points as a 0–255 mask."""
    mask = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    scaled = [(x * SS, y * SS) for x, y in _spline(points)]
    ImageDraw.Draw(mask).line(scaled, fill=255, width=width * SS, joint="curve")
    return np.asarray(mask.resize(size, Image.Resampling.LANCZOS), np.float32)


# --- artefacts --------------------------------------------------------------------------


def _signature(rng: random.Random) -> tuple[Image.Image, int]:
    """A blue-black scribble and the y of its baseline within the patch."""
    width = rng.randint(200, 320)
    pad, baseline = 12, 80
    x = pad + rng.uniform(0, 6)
    # A tall opening capital, a run of small loops, then a flourish back under the name.
    points = [
        (x, baseline - rng.uniform(4, 12)),
        (x + rng.uniform(8, 16), baseline - rng.uniform(48, 62)),
        (x + rng.uniform(12, 22), baseline + rng.uniform(4, 10)),
        (x + rng.uniform(2, 8), baseline - rng.uniform(18, 28)),
    ]
    x = points[-1][0] + rng.uniform(16, 26)
    while x < pad + width - 30:
        letter = rng.choices(("hump", "loop", "tall"), weights=(5, 3, 1))[0]
        top = baseline - (rng.uniform(32, 46) if letter == "tall" else rng.uniform(10, 22))
        if letter == "hump":
            points += [(x, top), (x + rng.uniform(5, 9), baseline - rng.uniform(0, 4))]
        else:  # up, curl back to the left, down
            points += [
                (x + rng.uniform(4, 8), top),
                (x - rng.uniform(1, 4), top + rng.uniform(6, 12)),
                (x + rng.uniform(6, 10), baseline - rng.uniform(0, 4)),
            ]
        x += rng.uniform(12, 20)
    points += [
        (x + rng.uniform(4, 12), baseline - rng.uniform(10, 20)),
        (pad + rng.uniform(20, 70), baseline + rng.uniform(10, 18)),
    ]
    size = (2 * pad + width + 20, baseline + 40)
    alpha = _stroke(size, points, rng.randint(2, 3)) * rng.uniform(0.85, 0.95)
    return _patch(SIGNATURE_INK, alpha), baseline


def _stamp(rng: random.Random, nrng: np.random.Generator, date: dt.date) -> Image.Image:
    """A ring or box rubber stamp with a word and a date, patchy and slightly askew."""
    ink = rng.choice(STAMP_INKS)
    word = rng.choice(STAMP_WORDS)
    word_font = render._font(STAMP_FONT, rng.randint(26, 32))
    date_font = render._font(STAMP_FONT, 18)
    date_text = date.strftime("%d/%m/%y")
    word_w = word_font.getlength(word)
    if rng.random() < 0.5:
        r = max(word_w / 2 + 24, 72)
        side = int(2 * r) + 10
        c = side / 2
        mask = Image.new("L", (side, side), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((c - r, c - r, c + r, c + r), outline=255, width=4)
        draw.ellipse((c - r + 9, c - r + 9, c + r - 9, c + r - 9), outline=255, width=2)
        draw.text((c, c - 6), word, font=word_font, fill=255, anchor="ms")
        draw.text((c, c + 10), date_text, font=date_font, fill=255, anchor="mt")
    else:
        w, h = int(word_w) + 44, 92
        mask = Image.new("L", (w + 10, h + 10), 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((5, 5, w + 4, h + 4), outline=255, width=4)
        draw.rectangle((12, 12, w - 3, h - 3), outline=255, width=1)
        draw.text(((w + 10) / 2, 54), word, font=word_font, fill=255, anchor="ms")
        draw.text(((w + 10) / 2, 62), date_text, font=date_font, fill=255, anchor="mt")

    alpha = np.asarray(mask, np.float32) * rng.uniform(0.7, 0.9)
    patchy = np.clip(1.6 * _smooth_noise(nrng, mask.size, 9) - 0.05, 0, 1)
    alpha *= patchy * (nrng.random(alpha.shape) > 0.1)
    tilted = _patch(ink, alpha).rotate(
        rng.uniform(-15, 15), resample=Image.Resampling.BICUBIC, expand=True
    )
    return _patch(ink, np.asarray(tilted.getchannel("A"), np.float32))


def _stain(rng: random.Random, nrng: np.random.Generator) -> Image.Image:
    """A translucent brown ring with an irregular edge, as left by a cup."""
    radius = rng.uniform(50, 110)
    side = int(2.5 * radius) + 8
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32) + 0.5 - side / 2
    rho, theta = np.hypot(xx, yy), np.arctan2(yy, xx)
    edge = np.full_like(theta, radius)
    along = np.full_like(theta, 0.5)
    for k in range(2, 12):
        edge += radius * rng.uniform(0, 0.12) / k * np.cos(k * theta + rng.uniform(0, 2 * math.pi))
        if k < 5:
            along += rng.uniform(0, 0.4) * np.cos(k * theta + rng.uniform(0, 2 * math.pi))
    d = rho - edge
    width = rng.uniform(3, 6)
    # Coffee rings are dark and sharp on the outside, feathering towards the middle.
    ring = np.where(d < 0, np.exp(-((d / width) ** 2)), np.exp(-((d / (0.35 * width)) ** 2)))
    fill = np.where(d < 0, 0.12, 0.0)
    alpha = ring * np.clip(along, 0.05, 1) + fill
    alpha *= 255 * rng.uniform(0.35, 0.5) * (0.75 + 0.5 * _smooth_noise(nrng, (side, side), 6))
    return _patch(STAIN_BROWN, alpha)


def _amendment(rng: random.Random, nrng: np.random.Generator) -> Image.Image:
    """A pencil tick or a clerk's initials."""
    if rng.random() < 0.6:
        j = [rng.uniform(-2, 2) for _ in range(5)]
        points = [(3 + j[0], 15 + j[1]), (11 + j[2], 24 + j[3]), (27, 4 + j[4])]
        mask = _stroke((30, 28), points, 2)
    else:
        text = rng.choice(string.ascii_uppercase) + rng.choice(string.ascii_uppercase)
        font = render._font(INITIALS_FONT, 20)
        left, top, right, bottom = font.getbbox(text)
        image = Image.new("L", (right - left + 8, bottom - top + 8), 0)
        ImageDraw.Draw(image).text((4 - left, 4 - top), text, font=font, fill=255)
        mask = np.asarray(image, np.float32)
    grain = 0.55 + 0.45 * nrng.random(mask.shape)  # graphite skips over the paper's tooth
    return _patch(PENCIL, mask * rng.uniform(0.6, 0.75) * grain)


def _stamp_date(page: PageGT, rng: random.Random) -> dt.date:
    """A few days after the latest date written on the page."""
    dates = [
        dt.datetime.strptime(f.printed, "%d/%m/%y").date()
        for f in page.fields
        if f.field_id.endswith(":date") and f.printed
    ]
    latest = max(dates) if dates else dt.date(1985, 1, 1)
    return latest + dt.timedelta(days=rng.randint(0, 4))


def _name(field_id: str) -> str:
    return field_id.rsplit(":", 1)[1]


def _anywhere(rng: random.Random, patch: Image.Image, size: tuple[int, int]) -> tuple[int, int]:
    return (
        rng.randint(MARGIN, size[0] - patch.width - MARGIN),
        rng.randint(MARGIN, size[1] - patch.height - MARGIN),
    )


def _over(
    rng: random.Random, patch: Image.Image, box: BBox, size: tuple[int, int]
) -> tuple[int, int]:
    """Roughly centred on box."""
    cx = (box.x0 + box.x1) / 2 + rng.uniform(-0.25, 0.25) * (box.x1 - box.x0)
    cy = (box.y0 + box.y1) / 2 + rng.uniform(-0.25, 0.25) * (box.y1 - box.y0)
    x = max(MARGIN, min(round(cx - patch.width / 2), size[0] - patch.width - MARGIN))
    y = max(MARGIN, min(round(cy - patch.height / 2), size[1] - patch.height - MARGIN))
    return x, y


def _beside(rng: random.Random, patch: Image.Image, page: PageGT) -> tuple[int, int]:
    """Just left or right of an amount, touching no field."""
    targets = [f.bbox for f in page.fields if _name(f.field_id) in MONEY_FIELDS and f.printed]
    rng.shuffle(targets)
    for box in targets:
        y = (box.y0 + box.y1) // 2 - patch.height // 2 + rng.randint(-3, 3)
        gap = rng.randint(4, 12)
        sides = [box.x1 + gap, box.x0 - gap - patch.width]
        rng.shuffle(sides)
        for x in sides:
            if not (
                MARGIN <= x <= page.width - patch.width - MARGIN
                and MARGIN <= y <= page.height - patch.height - MARGIN
            ):
                continue
            spot = BBox(x0=x, y0=y, x1=x + patch.width, y1=y + patch.height)
            if not any(overlap(spot, f.bbox) for f in page.fields):
                return x, y
    raise ValueError(f"{page.page_id}: no free space beside any amount")


def _paste(canvas: Image.Image, patch: Image.Image, xy: tuple[int, int]) -> BBox:
    canvas.alpha_composite(patch, dest=xy)
    inked = patch.getchannel("A").getbbox()
    if inked is None:
        raise ValueError("artefact patch has no visible ink")
    left, top, right, bottom = inked
    return BBox(x0=xy[0] + left, y0=xy[1] + top, x1=xy[0] + right, y1=xy[1] + bottom)


def _add_artefacts(
    paper: Image.Image,
    page: PageGT,
    level: Level,
    rng: random.Random,
    nrng: np.random.Generator,
) -> tuple[Image.Image, list[Artefact]]:
    canvas = paper.convert("RGBA")
    marks: list[tuple[ArtefactKind, BBox]] = []
    if page.doc_type == "memo":
        patch, baseline = _signature(rng)
        lo, hi = SIGNATURE_LINE_X
        xy = (rng.randint(lo, hi - patch.width), render.AUTHORISED_Y - baseline + rng.randint(-4, 2))
        marks.append(("signature", _paste(canvas, patch, xy)))

    money = [f.bbox for f in page.fields if _name(f.field_id) in MONEY_FIELDS and f.printed]
    for k in range(rng.randint(*level.artefacts)):
        cover = k == 0 and level.cover_money
        if cover:
            kind: ArtefactKind = rng.choice(("stamp", "stain"))
        else:
            kind = rng.choices(RANDOM_KINDS, weights=RANDOM_WEIGHTS)[0]
        if kind == "stamp":
            patch = _stamp(rng, nrng, _stamp_date(page, rng))
        elif kind == "stain":
            patch = _stain(rng, nrng)
        else:
            patch = _amendment(rng, nrng)
        if kind == "handwritten_amendment":
            xy = _beside(rng, patch, page)
        elif cover:
            xy = _over(rng, patch, rng.choice(money), canvas.size)
        else:
            xy = _anywhere(rng, patch, canvas.size)
        marks.append((kind, _paste(canvas, patch, xy)))

    artefacts = [
        Artefact(artefact_id=f"A:{page.page_id}:{n:02d}", kind=kind, bbox=bbox)
        for n, (kind, bbox) in enumerate(marks, start=1)
    ]
    return canvas.convert("RGB"), artefacts


# --- paper and scanner effects ----------------------------------------------------------

_PAPER = np.array(render.PAPER, np.float32)


def _bleed(image: Image.Image, strength: float) -> Image.Image:
    """Ink wicking into the fibres: a soft dark halo around every stroke."""
    spread = image.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.5))
    halo = _PAPER + (np.asarray(spread, np.float32) - _PAPER) * strength
    return _to_image(np.minimum(np.asarray(image, np.float32), halo))


def _fade(image: Image.Image, fade: float) -> Image.Image:
    return _to_image(_PAPER + (np.asarray(image, np.float32) - _PAPER) * (1 - fade))


def _fold(rng: random.Random, size: tuple[int, int]) -> np.ndarray:
    """Brightness factor of a crease across the middle of the longer side."""
    w, h = size
    tilt = math.radians(rng.uniform(-2, 2))
    if w >= h:
        px, py, phi = w * rng.uniform(0.4, 0.6), h / 2, math.pi / 2 + tilt
    else:
        px, py, phi = w / 2, h * rng.uniform(0.4, 0.6), tilt
    xs = np.arange(w, dtype=np.float32)[None, :] + 0.5 - px
    ys = np.arange(h, dtype=np.float32)[:, None] + 0.5 - py
    d = -xs * math.sin(phi) + ys * math.cos(phi)  # signed distance from the crease
    crease = 0.22 * np.exp(-((d / 1.3) ** 2))
    shadow = 0.07 * np.exp(-(((d - 5) / 5) ** 2))
    highlight = 0.035 * np.exp(-(((d + 6) / 6) ** 2))
    return 1 - crease - shadow + highlight


def _age(
    image: Image.Image, level: Level, rng: random.Random, nrng: np.random.Generator
) -> Image.Image:
    arr = np.array(image, np.float32)
    h, w = arr.shape[:2]
    if level.yellow:
        blotch = 0.6 + 0.8 * _smooth_noise(nrng, (w, h), 90)
        arr *= 1 - level.yellow * blotch[..., None] * YELLOWING
    if level.fold:
        arr *= _fold(rng, (w, h))[..., None]
    fibres = 0.6 * nrng.standard_normal((h, w)) + 2.4 * (_smooth_noise(nrng, (w, h), 6) - 0.5)
    arr += level.grain * fibres[..., None]
    return _to_image(arr)


def _speckle(image: Image.Image, density: float, nrng: np.random.Generator) -> None:
    """Dust on the glass: mostly dark specks, some white dropouts."""
    w, h = image.size
    n = int(density * w * h)
    xs, ys = nrng.uniform(0, w, n), nrng.uniform(0, h, n)
    radii = np.minimum(0.3 + nrng.exponential(0.35, n), 2.0)
    dark = nrng.random(n) < 0.8
    shades = np.where(dark, nrng.uniform(20, 110, n), nrng.uniform(225, 250, n))
    draw = ImageDraw.Draw(image)
    for x, y, r, shade in zip(xs, ys, radii, shades, strict=True):
        grey = int(shade)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(grey, grey, grey))


def _scan(image: Image.Image, level: Level, nrng: np.random.Generator) -> Image.Image:
    w, h = image.size
    if level.lighting:
        a = nrng.uniform(0, 2 * math.pi)
        ramp = np.arange(w)[None, :] * math.cos(a) + np.arange(h)[:, None] * math.sin(a)
        ramp = (ramp - ramp.min()) / (ramp.max() - ramp.min())
        shade = level.lighting * (0.65 * ramp**2 + 0.35 * _smooth_noise(nrng, (w, h), 250))
        image = _to_image(np.asarray(image, np.float32) * (1 - shade)[..., None])
    if level.blur:
        image = image.filter(ImageFilter.GaussianBlur(level.blur))
    if level.rescale < 1:
        small = (round(w * level.rescale), round(h * level.rescale))
        image = image.resize(small, Image.Resampling.BILINEAR).resize(
            (w, h), Image.Resampling.BICUBIC
        )
    if level.noise:
        arr = np.asarray(image, np.float32)
        arr = arr + level.noise * nrng.standard_normal((h, w, 1)).astype(np.float32)
        image = _to_image(arr + 0.3 * level.noise * nrng.standard_normal((h, w, 3)))
    if level.speckle:
        _speckle(image, level.speckle, nrng)
    return image


def _jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    with Image.open(buffer) as decoded:
        return decoded.convert("RGB")


# --- pages ------------------------------------------------------------------------------


def degrade_page(
    image: Image.Image, page: PageGT, severity: int, rng: random.Random
) -> tuple[Image.Image, PageGT]:
    """A scanned-looking copy of a clean page and its ground truth with boxes moved to match."""
    if image.size != (page.width, page.height):
        raise ValueError(f"{page.page_id}: image is {image.size}, ground truth says otherwise")
    level = LEVELS[severity]
    nrng = np.random.default_rng(rng.getrandbits(64))

    paper = image.convert("RGB")
    if level.bleed:
        paper = _bleed(paper, level.bleed)
    if level.fade:
        paper = _fade(paper, level.fade)
    paper, artefacts = _add_artefacts(paper, page, level, rng, nrng)
    paper = _age(paper, level, rng, nrng)

    angle = rng.uniform(-level.max_rotation, level.max_rotation) if level.max_rotation else 0.0
    scan = rotate(paper, angle) if angle else paper
    scan = _jpeg(_scan(scan, level, nrng), level.jpeg_quality)

    artefacts = [
        a.model_copy(update={"bbox": map_bbox(a.bbox, angle, scan.size)}) for a in artefacts
    ]
    fields = []
    for field in page.fields:
        bbox = map_bbox(field.bbox, angle, scan.size)
        occluded = [a.artefact_id for a in artefacts if occludes(a.bbox, bbox)]
        fields.append(field.model_copy(update={"bbox": bbox, "occluded_by": occluded}))
    gt = page.model_copy(
        update={"severity": severity, "fields": fields, "artefacts": artefacts}
    )
    return scan, gt


def overlay(image: Image.Image, gt: PageGT) -> Image.Image:
    """Field boxes as in render.overlay, plus artefact boxes outlined in black."""
    out = render.overlay(image, gt)
    draw = ImageDraw.Draw(out)
    for artefact in gt.artefacts:
        box = artefact.bbox
        draw.rectangle((box.x0, box.y0, box.x1 - 1, box.y1 - 1), outline=ARTEFACT_OUTLINE, width=3)
        draw.text((box.x0 + 4, box.y0 + 3), artefact.kind, fill=ARTEFACT_OUTLINE)
    return out


def degrade_samples(seed: int, out_dir: Path) -> list[PageGT]:
    """The first card and first memo of generate_world(seed) at every severity.

    Writes out_dir/sev<k>/pages/<doc_id>.png and .json and out_dir/sev<k>/overlays/<doc_id>.png.
    """
    world = generate_world(seed)
    card, memo = world.cards[0], world.memos[0]
    banks = {c.doc_id: c.bank for c in world.cards}
    clean = [
        render.render_card(card, random.Random(f"{seed}:{card.doc_id}")),
        render.render_memo(
            memo,
            random.Random(f"{seed}:{memo.doc_id}"),
            bank=banks[memo.ledger_ref.rsplit(":", 1)[0]],
        ),
    ]
    pages: list[PageGT] = []
    for severity in range(len(LEVELS)):
        pages_dir = out_dir / f"sev{severity}" / "pages"
        overlays_dir = out_dir / f"sev{severity}" / "overlays"
        pages_dir.mkdir(parents=True, exist_ok=True)
        overlays_dir.mkdir(parents=True, exist_ok=True)
        for image, gt in clean:
            on_page = {f.field_id for f in gt.fields}
            errors = [e for e in world.source_errors if on_page.intersection(e.field_ids)]
            gt = gt.model_copy(update={"source_errors": errors})
            rng = random.Random(f"{seed}:{gt.page_id}:sev{severity}")
            scan, scan_gt = degrade_page(image, gt, severity, rng)
            scan.save(pages_dir / f"{gt.page_id}.png")
            (pages_dir / f"{gt.page_id}.json").write_text(scan_gt.model_dump_json(indent=2) + "\n")
            overlay(scan, scan_gt).save(overlays_dir / f"{gt.page_id}.png")
            pages.append(scan_gt)
    return pages


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.synth.degrade",
        description="Degrade the first card and memo of a world at every severity.",
    )
    parser.add_argument("--seed", type=int, required=True, help="world and degradation seed")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    pages = degrade_samples(args.seed, args.out)
    print(f"wrote {len(pages)} pages to {args.out}")


if __name__ == "__main__":
    main()
