"""A blind re-read of one field from a crop of its corrected citation box (D4).

The crop is the box padded by PAD_Y of its height above and below and PAD_X of its width left and
right, clamped to the page, and sent as PNG. The correction snaps a box to one word of ink, so a
box around "STANDING ORDER INSURANCE" can come back around "ORDER" alone; the extractor's own box
spans the cell but drifts vertically (citations.py). So the corrected box is first widened to the
extractor's horizontal extent, which every corrected citation keeps as raw_bbox (region): on dev
this took the share of crops holding the whole printed description from 0.86 to 0.99, the payee
from 0.77 to 1.00.

The prompt comes from the field's document type: it names the document and the field (e.g. "the
Balance column of a ledger card line") and never the value the extractor read, so agreement is
evidence and not an echo. Each call sees one cell, so the re-reader can't make values agree across
rows the way a reading of the whole page can (D26). The re-reader is the rereader role. It answers
{"value": string or null}: the value as printed, "" for a blank cell, null when it can't be read.
An answer that
doesn't parse is asked for once more, with a note; if that fails too, ReReadFailed is raised.
"""

from __future__ import annotations

import io
import json
import math

from PIL import Image

from archivist.models import LLMRequest, VisionLLM
from archivist.schema import BBox, Citation

ROLE = "rereader"
PAD_Y = 0.5  # × the box height, above and below
PAD_X = 0.2  # × the box width, left and right
REREAD_TOKENS = 2_048
SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": ["string", "null"]}},
    "required": ["value"],
    "additionalProperties": False,
}
RETRY_NOTE = (
    '\n\nYour previous answer did not match the JSON schema. Answer again as {"value": ...}, '
    "the value as a string, or null."
)


class ReReadFailed(RuntimeError):
    pass


def widen(box: BBox, reach: BBox | None) -> BBox:
    """box, stretched sideways to cover reach's horizontal extent; its rows stay as they are."""
    if reach is None:
        return box
    return BBox(x0=min(box.x0, reach.x0), y0=box.y0, x1=max(box.x1, reach.x1), y1=box.y1)


def region(citation: Citation) -> BBox:
    """The box to crop around: the corrected box, widened to the extractor's own."""
    return widen(citation.bbox, citation.raw_bbox)


def crop_box(box: BBox, width: int, height: int) -> BBox:
    """The box padded by PAD_X and PAD_Y on each side, rounded outwards, clamped to the page."""
    pad_x, pad_y = PAD_X * (box.x1 - box.x0), PAD_Y * (box.y1 - box.y0)
    return BBox(
        x0=max(0, math.floor(box.x0 - pad_x)),
        y0=max(0, math.floor(box.y0 - pad_y)),
        x1=min(width, math.ceil(box.x1 + pad_x)),
        y1=min(height, math.ceil(box.y1 + pad_y)),
    )


def crop(image: Image.Image, box: BBox) -> bytes:
    """The padded crop around box, as PNG bytes."""
    area = crop_box(box, *image.size)
    buffer = io.BytesIO()
    image.crop((area.x0, area.y0, area.x1, area.y1)).save(buffer, format="PNG")
    return buffer.getvalue()


def _parse(text: str) -> str | None:
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != {"value"}:
        raise ValueError(f'expected {{"value": ...}}, got {data!r}')
    value = data["value"]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"value must be a string or null, got {value!r}")
    return value


def reread(image: Image.Image, box: BBox, prompt: str, llm: VisionLLM) -> tuple[str | None, bool]:
    """The value in the crop around box, or None if illegible; and whether it came from cache."""
    picture = crop(image, box)
    errors = []
    for attempt in (prompt, prompt + RETRY_NOTE):
        request = LLMRequest(
            role=ROLE,
            prompt=attempt,
            images=(picture,),
            json_schema=SCHEMA,
            max_output_tokens=REREAD_TOKENS,
        )
        response = llm.complete(request)
        try:
            return _parse(response.text), response.cached
        except (ValueError, TypeError) as error:
            errors.append(f"{type(error).__name__}: {error}"[:300])
    raise ReReadFailed(" | retry: ".join(errors))
