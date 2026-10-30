"""The page images the static UI shows: each scan downsized once, as a plain JPEG.

A scan is big and the review UI shows whole pages and small crops of them, so the bundle carries a
copy no longer than MAX_SIDE on its longer side. Only the display is smaller: every box in the
bundle stays in the scan's own pixels, and the UI scales them by the page's width. The copy lives
in one folder per split (data/pages/<split>/), shared by every run on that split, and is named by
the page; its bytes depend on the scan alone, so the same scan always gives the same file.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

PAGES_DIR = Path("data/pages")
MAX_SIDE = 1280  # px, the longer side; a smaller scan keeps its size
MAX_SIDE_REAL = 2200  # a page of print is read at its own size: its figures are a few pixels tall
QUALITY = 70


@dataclass(frozen=True)
class WebImage:
    data: bytes
    width: int
    height: int
    sha256: str


def _web_image(path: str, mtime_ns: int, size: int, max_side: int) -> WebImage:
    with Image.open(path) as scan:
        picture = scan.convert("RGB")
    scale = min(1.0, max_side / max(picture.size))
    if scale < 1.0:
        picture = picture.resize(
            (round(picture.width * scale), round(picture.height * scale)), Image.Resampling.LANCZOS
        )
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    data = out.getvalue()
    return WebImage(data, picture.width, picture.height, hashlib.sha256(data).hexdigest())


_cached = lru_cache(maxsize=None)(_web_image)


def web_image(scan: Path, max_side: int = MAX_SIDE) -> WebImage:
    """The downsized copy of a scan (computed once for a scan that hasn't changed)."""
    stat = scan.stat()
    return _cached(str(scan), stat.st_mtime_ns, stat.st_size, max_side)
