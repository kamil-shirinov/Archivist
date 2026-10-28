"""Which pages the template commands may send to a model, and where their images are.

A real page is "<issue>_p<NNN>" (data/real/pages/<issue>/p<NNN>.jpg). Only an issue on the
development side of data/real/split.json is allowed, and its image must match the manifest's
sha256; a held-out page is refused before its file is opened. A synthetic page is "dev/<stem>"
or "val/<stem>" (data/<split>/images/<stem>.jpg: the dev split, seed 1001, or val, seed 2002);
test, the frozen split, is never allowed. Anything else is refused. A page's id in its field
ids is the real id, or the synthetic page's stem.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from archivist.ingest.fraser import DEFAULT_ROOT, Manifest, Split

REAL = re.compile(r"(?P<issue>\d{4}-\d{2})_p(?P<page>\d{3})")
SYNTHETIC = re.compile(r"(?P<split>dev|val)/(?P<stem>[A-Za-z0-9][A-Za-z0-9_-]*)")
SYNTHETIC_ROOT = Path("data")


class PageRefused(ValueError):
    pass


@dataclass(frozen=True)
class Page:
    ref: str  # as given: "1939-07_p071", "dev/card-01-1" or "val/memo-0003"
    page_id: str  # as the field ids name it
    path: Path


@cache
def _split(root: Path) -> Split:
    return Split.model_validate_json((root / "split.json").read_text(encoding="utf-8"))


@cache
def _hashes(root: Path) -> dict[tuple[str, int], str]:
    manifest = Manifest.model_validate_json((root / "manifest.json").read_text(encoding="utf-8"))
    return {(p.issue, p.page): p.sha256 for p in manifest.pages}


def resolve(ref: str, root: Path = DEFAULT_ROOT, synthetic: Path = SYNTHETIC_ROOT) -> Page:
    """The page a reference names, if it may be sent to a model; raises PageRefused if not."""
    if (real := REAL.fullmatch(ref)) is not None:
        issue, number = real["issue"], int(real["page"])
        if issue not in _split(root).development:
            raise PageRefused(f"{ref}: issue {issue} is not a development issue")
        expected = _hashes(root).get((issue, number))
        if expected is None:
            raise PageRefused(f"{ref}: not in {root / 'manifest.json'}")
        path = root / "pages" / issue / f"p{number:03d}.jpg"
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise PageRefused(f"{ref}: {path} is missing or does not match the manifest")
        return Page(ref, ref, path)
    if (found := SYNTHETIC.fullmatch(ref)) is not None:
        split, stem = found["split"], found["stem"]
        path = synthetic / split / "images" / f"{stem}.jpg"
        if not path.is_file():
            raise PageRefused(
                f"{ref}: {path} is missing; rebuild {split} with archivist.synth.build"
            )
        return Page(ref, stem, path)
    raise PageRefused(
        f"{ref}: neither a development page (1939-07_p071) nor a dev or val page (dev/x, val/x)"
    )
