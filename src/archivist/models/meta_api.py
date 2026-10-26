"""Muse Spark on the Meta Model API: a VisionLLM over the OpenAI SDK's Chat Completions.

The key is env META_API_KEY, from the environment or from .env in the working directory, and it
is read only when the first call is made: roles load, and cached answers replay, without one.
The SDK's own retries are off; 429 and 5xx are retried here with exponential backoff and jitter,
waiting at least as long as any Retry-After header asks, as the rate-limits page advises.

Usage follows the reasoning page: reasoning tokens are billed as completion tokens and
completion_tokens already counts them (completion_tokens_details.reasoning_tokens is only a
breakdown), so output_tokens is completion_tokens. Cached input is priced as ordinary input, so
the ledger can overstate spend but never understate it.
"""

from __future__ import annotations

import base64
import os
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import openai
from dotenv import load_dotenv

from archivist.models.base import LLMRequest, LLMResponse, Usage
from archivist.models.budget import Price

BASE_URL = "https://api.meta.ai/v1"
KEY_ENV = "META_API_KEY"
DOTENV_PATH = Path(".env")
TIMEOUT_S = 60.0
MAX_RETRIES = 3
FIRST_BACKOFF_S = 0.5  # doubled after each retry, plus up to as much again in jitter
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")  # "none" is a 400
SCHEMA_NAME = "answer"


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
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(f"reasoning_effort must be one of {REASONING_EFFORTS}")
        self.model_id = model_id
        self.price = price
        self.settings = {"reasoning_effort": reasoning_effort}  # part of the cache key
        self._client = client
        self._sleep = sleep

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = openai.OpenAI(
                api_key=api_key(), base_url=BASE_URL, timeout=TIMEOUT_S, max_retries=0
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
        attempt = 0
        while True:
            try:
                return self.client.chat.completions.create(**payload, timeout=TIMEOUT_S)
            except openai.APIStatusError as error:
                if attempt >= MAX_RETRIES or not _retryable(error):
                    raise
                backoff = FIRST_BACKOFF_S * 2**attempt
                self._sleep(max(backoff + random.uniform(0, backoff), _retry_after(error)))
                attempt += 1
