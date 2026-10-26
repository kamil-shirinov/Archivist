"""Which fields a stamp or a stain covers, found by the segmenter role (SAM 3.1).

Each page is segmented once for "stamp" and once for "stain", the two artefacts that covered
money fields in the spike (results/sam_spike.json). Each prompt is its own request, as in the
spike, so the spike's answers are replayed from the cache rather than asked again. A field is
occluded when one detected box covers at least COVER of its corrected citation box. A field
without a citation can't be placed, so it is never called occluded.
"""

from __future__ import annotations

from collections.abc import Sequence

from archivist.models import Region, Segmenter, SegmentRequest
from archivist.schema import BBox, ExtractedValue

ROLE = "segmenter"
PROMPTS = ("stamp", "stain")
COVER = 0.10  # share of a field's box that one detected box must cover


def detect(image: bytes, segmenter: Segmenter) -> list[Region]:
    """Every stamp and stain on the page: one segmenter call per prompt."""
    regions: list[Region] = []
    for prompt in PROMPTS:
        request = SegmentRequest(role=ROLE, image=image, prompts=(prompt,))
        regions += segmenter.segment(request).regions
    return regions


def covered(box: BBox, region: BBox) -> float:
    """The share of box that region covers."""
    iw = min(box.x1, region.x1) - max(box.x0, region.x0)
    ih = min(box.y1, region.y1) - max(box.y0, region.y0)
    if iw <= 0 or ih <= 0:
        return 0.0
    return iw * ih / box.area()


def occluders(value: ExtractedValue, regions: Sequence[Region]) -> list[tuple[Region, float]]:
    """The detected regions covering at least COVER of the value's box, with their cover."""
    if value.citation is None:
        return []
    found = [(r, covered(value.citation.bbox, r.bbox)) for r in regions]
    return [(r, share) for r, share in found if share >= COVER]
