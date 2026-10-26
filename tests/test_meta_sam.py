"""SAM 3.1 backend against an injected fake client: no network, no key."""

import base64
import io
import math
from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai.types.responses import Response
from PIL import Image

from archivist.models import load_roles
from archivist.models.base import Region, SegmentRequest
from archivist.models.budget import Price, project_cost
from archivist.models.meta_api import (
    BASE_URL,
    FIRST_BACKOFF_S,
    MetaSAM,
    parse_sam_output,
)
from archivist.schema import BBox

CONFIG = Path(__file__).resolve().parents[1] / "config" / "models.toml"
PRICE = Price(input_per_mtok=0.0, output_per_mtok=0.0, per_image_usd=0.0025)

# Frame 0 of the six-frame "button" clip on https://dev.meta.ai/docs/sam/reading-segmentation:
# two matches in a 320 x 334 frame, masks in full. x2 and y2 are inclusive.
DOCS_LINE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>,"
    "1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>"
)
# The same line with include_confidence on: a c on each box and mask, as the grammar allows.
DOCS_LINE_WITH_C = DOCS_LINE.replace("h=334|>", "h=334;c=0.9609375|>").replace(
    "x=0;y=0;data", "x=0;y=0;c=0.9609375;data"
)
# The confidence example on https://dev.meta.ai/docs/sam/segmenting, whose mask is elided.
ELIDED_LINE = (
    "<0f>1<|box;x1=444;y1=625;x2=679;y2=850;w=1800;h=1200;c=0.9609375|>"
    "<|mask;x=0;y=0;c=0.9609375;data=226,236,!...|>"
)


def png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height), 255).save(buffer, format="PNG")
    return buffer.getvalue()


PAGE = png(320, 334)


def response(text: str = DOCS_LINE, status: str = "completed") -> Response:
    content = [{"type": "output_text", "text": text, "annotations": []}] if text else []
    return Response.model_validate(
        {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "model": "sam-3.1",
            "status": status,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": content,
                }
            ],
        }
    )


def status_error(code: int) -> openai.APIStatusError:
    http = httpx2.Response(code, request=httpx2.Request("POST", f"{BASE_URL}/responses"))
    classes = {400: openai.BadRequestError, 429: openai.RateLimitError}
    return classes.get(code, openai.InternalServerError)(f"status {code}", response=http, body=None)


class FakeClient:
    """Plays back outcomes in order: a response is returned, an exception raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def sam(*outcomes, sleeps: list | None = None) -> tuple[MetaSAM, FakeClient]:
    client = FakeClient(*outcomes)
    sleep = sleeps.append if sleeps is not None else lambda seconds: None
    return MetaSAM("sam-3.1", PRICE, client=client, sleep=sleep), client


def request(*prompts: str, image: bytes = PAGE) -> SegmentRequest:
    return SegmentRequest(role="segmenter", image=image, prompts=prompts)


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """Run in an empty cwd, so no real .env is ever loaded."""
    monkeypatch.chdir(tmp_path)


# --- request -----------------------------------------------------------------------------------


def test_one_documented_responses_request_per_prompt():
    segmenter, client = sam(response(), response(""))

    segmenter.segment(request("stamp", "stain"))

    assert [call["input"][0]["content"][0]["text"] for call in client.calls] == ["stamp", "stain"]
    call = client.calls[0]
    assert call["model"] == "sam-3.1"
    (message,) = call["input"]
    assert (message["type"], message["role"]) == ("message", "user")
    text, image = message["content"]
    assert text == {"type": "input_text", "text": "stamp"}
    assert image["type"] == "input_image"
    assert image["image_url"].startswith("data:image/png;base64,")
    assert base64.b64decode(image["image_url"].split(",", 1)[1]) == PAGE
    assert call["metadata"] == {"include_confidence": "true"}  # a string, as metadata requires
    assert call["timeout"] == 60.0
    assert "stream" not in call


# --- output ------------------------------------------------------------------------------------


def test_docs_example_parses_to_half_open_page_boxes_labelled_by_prompt():
    regions = parse_sam_output(DOCS_LINE, "button", 320, 334)

    assert [(r.label, r.bbox) for r in regions] == [
        ("button", BBox(x0=211, y0=228, x1=271, y1=255)),
        ("button", BBox(x0=155, y0=228, x1=203, y1=255)),
    ]
    assert all(math.isnan(r.score) for r in regions)  # no c in the output: the score is unknown


def test_boxes_scale_from_the_output_frame_to_the_page():
    regions = parse_sam_output(DOCS_LINE, "button", 640, 668)  # the page at twice the frame

    assert [r.bbox for r in regions] == [
        BBox(x0=422, y0=456, x1=542, y1=510),
        BBox(x0=310, y0=456, x1=406, y1=510),
    ]


def test_backend_returns_regions_with_confidence_and_a_per_image_cost():
    segmenter, _ = sam(response(DOCS_LINE_WITH_C), response(""))

    result = segmenter.segment(request("button", "stain"))

    assert result.regions == (
        Region("button", BBox(x0=211, y0=228, x1=271, y1=255), 0.9609375),
        Region("button", BBox(x0=155, y0=228, x1=203, y1=255), 0.9609375),
    )
    assert (result.backend, result.model_id) == ("meta", "sam-3.1")
    assert result.usage.cost_usd == pytest.approx(2 * 0.0025)  # billed per image, per request


def test_zero_matches_is_no_regions():
    assert parse_sam_output("", "stamp", 320, 334) == ()


def test_unreadable_output_raises_rather_than_dropping_instances():
    with pytest.raises(ValueError, match="invalid_mask_payload"):
        parse_sam_output(ELIDED_LINE, "glasses", 1800, 1200)
    with pytest.raises(ValueError, match="not segmentation records"):
        parse_sam_output("I cannot segment that.", "stamp", 320, 334)


def test_incomplete_response_raises():
    segmenter, _ = sam(response(status="incomplete"))
    with pytest.raises(RuntimeError, match="incomplete"):
        segmenter.segment(request("stamp"))


# --- retries -----------------------------------------------------------------------------------


def test_429_then_success_retries_once():
    sleeps: list[float] = []
    segmenter, client = sam(status_error(429), response(), sleeps=sleeps)

    result = segmenter.segment(request("button"))

    assert len(result.regions) == 2
    assert len(client.calls) == 2
    (slept,) = sleeps
    assert FIRST_BACKOFF_S <= slept <= 2 * FIRST_BACKOFF_S


def test_client_errors_are_not_retried():
    segmenter, client = sam(status_error(400), response())
    with pytest.raises(openai.BadRequestError):
        segmenter.segment(request("stamp"))
    assert len(client.calls) == 1


# --- config and budget -------------------------------------------------------------------------


def test_shipped_segmenter_is_sam_priced_per_image(tmp_path):
    roles = load_roles(CONFIG, cache_dir=tmp_path / "cache", ledger_path=tmp_path / "l.jsonl")
    backend = roles["segmenter"].inner.inner

    assert isinstance(backend, MetaSAM)
    assert backend.model_id == "sam-3.1"
    assert backend.price == Price(0.0, 0.0, per_image_usd=0.0025)


def test_projection_pays_one_image_per_prompt():
    assert project_cost(request("stamp", "stain", "signature"), PRICE) == pytest.approx(0.0075)
