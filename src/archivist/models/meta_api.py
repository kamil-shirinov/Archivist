"""Meta Model API backends over the OpenAI SDK: Muse Spark, a VisionLLM over Chat Completions, and
SAM 3.1, a Segmenter over the Responses API (parsed with meta_sam_parser, as the docs advise).

The key is env META_API_KEY, from the environment or from .env in the working directory, and it
is read only when the first call is made: roles load, and cached answers replay, without one.
The SDK's own retries are off; 429 and 5xx are retried here with exponential backoff and jitter,
waiting at least as long as any Retry-After header asks, as the rate-limits page advises.

Usage follows the reasoning page: reasoning tokens are billed as completion tokens and
completion_tokens already counts them (completion_tokens_details.reasoning_tokens is only a
breakdown), so output_tokens is completion_tokens. Cached input is priced as ordinary input, so
the ledger can overstate spend but never understate it.

A role may wait longer than TIMEOUT_S for an answer (settings timeout_s: a whole statistical table
read at once, say). How long a call may take is not part of what it asks, so it is not one of the
backend's settings and not part of the cache key.
"""

from __future__ import annotations

import base64
import io
import math
import os
import random
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import openai
from dotenv import load_dotenv
from meta_sam_parser import CompletedOutcome, image_segmentation_format
from PIL import Image

from archivist.models.base import (
    LLMRequest,
    LLMResponse,
    Region,
    SegmentRequest,
    SegmentResponse,
    Usage,
)
from archivist.models.budget import Price
from archivist.schema import BBox

BASE_URL = "https://api.meta.ai/v1"
KEY_ENV = "META_API_KEY"
DOTENV_PATH = Path(".env")
TIMEOUT_S = 60.0
MAX_RETRIES = 3
FIRST_BACKOFF_S = 0.5  # doubled after each retry, plus up to as much again in jitter
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")  # "none" is a 400
SCHEMA_NAME = "answer"
_FRAME_SIZE = re.compile(r"<\|box;[^|]*?;w=(\d+);h=(\d+)")  # the box token's frame width, height


class MissingAPIKey(RuntimeError):
    pass


def api_key() -> str:
    """The key, or MissingAPIKey. The message names the variable and never any value."""
    load_dotenv(DOTENV_PATH)  # never overrides a variable that is already set
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise MissingAPIKey(f"{KEY_ENV} is not set: export it or put it in .env")
    return key


def _mime(image: bytes) -> str:
    if image.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    if image[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    raise ValueError("image is not a JPEG, PNG, WebP or GIF")


def data_url(image: bytes) -> str:
    return f"data:{_mime(image)};base64,{base64.b64encode(image).decode('ascii')}"


def build_payload(model_id: str, request: LLMRequest, *, reasoning_effort: str) -> dict[str, Any]:
    """Keyword arguments for chat.completions.create; images follow the prompt in one user turn."""
    messages: list[dict[str, Any]] = []
    if request.system is not None:
        messages.append({"role": "system", "content": request.system})
    content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
    content += [{"type": "image_url", "image_url": {"url": data_url(i)}} for i in request.images]
    messages.append({"role": "user", "content": content})
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "max_tokens": request.max_output_tokens,  # caps reasoning and visible output together
        "temperature": request.temperature,
        "reasoning_effort": reasoning_effort,
    }
    if request.json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": SCHEMA_NAME, "schema": request.json_schema},
        }
    return payload


def _retryable(error: openai.APIStatusError) -> bool:
    return error.status_code == 429 or error.status_code >= 500


def _retry_after(error: openai.APIStatusError) -> float:
    try:
        return max(0.0, float(error.response.headers.get("retry-after", 0)))
    except ValueError:  # an HTTP date: fall back to the backoff alone
        return 0.0


class MetaLLM:
    name = "meta"

    def __init__(
        self,
        model_id: str,
        price: Price,
        *,
        reasoning_effort: str = "low",
        timeout_s: float = TIMEOUT_S,  # not part of the cache key
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(f"reasoning_effort must be one of {REASONING_EFFORTS}")
        self.model_id = model_id
        self.price = price
        self.settings = {"reasoning_effort": reasoning_effort}  # part of the cache key
        self.timeout_s = timeout_s
        self._client = client
        self._sleep = sleep

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = openai.OpenAI(
                api_key=api_key(), base_url=BASE_URL, timeout=self.timeout_s, max_retries=0
            )
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        completion = self._create(build_payload(self.model_id, request, **self.settings))
        if completion.usage is None:
            raise RuntimeError(f"{self.model_id}: response carries no usage; cost unknown")
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens
        cost = (
            input_tokens * self.price.input_per_mtok + output_tokens * self.price.output_per_mtok
        ) / 1e6
        return LLMResponse(
            text=completion.choices[0].message.content or "",
            usage=Usage(input_tokens, output_tokens, cost),
            backend=self.name,
            model_id=self.model_id,
        )

    def _create(self, payload: dict[str, Any]) -> Any:
        return _with_retries(
            lambda: self.client.chat.completions.create(**payload, timeout=self.timeout_s),
            self._sleep,
        )


# --- SAM 3.1 -----------------------------------------------------------------------------------


def build_sam_payload(model_id: str, prompt: str, image: bytes) -> dict[str, Any]:
    """Keyword arguments for responses.create: one concept prompt and the page, as the docs show.

    Non-streaming returns the same text as the stream, in one response. Confidence is asked for
    so every box carries a score; metadata values are strings, hence "true".
    """
    content = [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": data_url(image)},
    ]
    return {
        "model": model_id,
        "input": [{"type": "message", "role": "user", "content": content}],
        "metadata": {"include_confidence": "true"},
    }


def parse_sam_output(text: str, label: str, width: int, height: int) -> tuple[Region, ...]:
    """One Region per instance, its box scaled from the output's frame to a width x height page.

    meta_sam_parser reads the records and makes x2/y2 half-open, but its box records drop the
    frame size (w, h), so that is read from the box tokens here. The score is the box's c, or NaN
    when the output has none. Anything the parser could not read raises: a silently dropped
    instance would look like a miss.
    """
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    errors = [d for d in result.diagnostics if d.severity == "error"]
    if errors:
        raise ValueError(f"unreadable SAM output: {errors[0].code}: {errors[0].message}")
    if any(record.kind == "text" for record in result.records):
        raise ValueError("SAM output has a line that is not segmentation records")
    boxes = [record for record in result.records if record.kind == "box"]
    sizes = set(_FRAME_SIZE.findall(text))
    if len(sizes) > 1:
        raise ValueError(f"SAM output mixes frame sizes {sorted(sizes)}")
    if not boxes:
        return ()
    source_w, source_h = (int(v) for v in sizes.pop())
    sx, sy = width / source_w, height / source_h
    regions = []
    for box in boxes:
        bbox = BBox(
            x0=max(0, math.floor(box.left * sx)),
            y0=max(0, math.floor(box.top * sy)),
            x1=min(width, math.ceil(box.right * sx)),
            y1=min(height, math.ceil(box.bottom * sy)),
        )
        score = math.nan if box.confidence is None else box.confidence  # unknown is not 0 or 1
        regions.append(Region(label=label, bbox=bbox, score=score))
    return tuple(regions)


class MetaSAM:
    """SAM 3.1 over the Responses API: one request per prompt, since SAM takes one concept each.

    Billed per image, not per token (pricing page), so each request costs price.per_image_usd;
    any token usage the response reports is priced too, at the config's token rates.
    """

    name = "meta"

    def __init__(
        self,
        model_id: str,
        price: Price,
        *,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model_id = model_id
        self.price = price
        self._client = client
        self._sleep = sleep

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = openai.OpenAI(
                api_key=api_key(), base_url=BASE_URL, timeout=TIMEOUT_S, max_retries=0
            )
        return self._client

    def segment(self, request: SegmentRequest) -> SegmentResponse:
        width, height = Image.open(io.BytesIO(request.image)).size
        regions: list[Region] = []
        input_tokens = output_tokens = 0
        for prompt in request.prompts:
            payload = build_sam_payload(self.model_id, prompt, request.image)
            response = _with_retries(
                lambda payload=payload: self.client.responses.create(**payload, timeout=TIMEOUT_S),
                self._sleep,
            )
            if response.status != "completed":
                raise RuntimeError(f"{self.model_id}: response {response.status}, not completed")
            regions += parse_sam_output(response.output_text, prompt, width, height)
            if response.usage is not None:
                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens
        cost = self.price.per_image_usd * len(request.prompts) + (
            input_tokens * self.price.input_per_mtok + output_tokens * self.price.output_per_mtok
        ) / 1e6
        return SegmentResponse(
            regions=tuple(regions),
            usage=Usage(input_tokens, output_tokens, cost),
            backend=self.name,
            model_id=self.model_id,
        )


def _with_retries(create: Callable[[], Any], sleep: Callable[[float], None]) -> Any:
    attempt = 0
    while True:
        try:
            return create()
        except openai.APIStatusError as error:
            if attempt >= MAX_RETRIES or not _retryable(error):
                raise
            backoff = FIRST_BACKOFF_S * 2**attempt
            sleep(max(backoff + random.uniform(0, backoff), _retry_after(error)))
            attempt += 1
