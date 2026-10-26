"""Muse Spark Open on Baseten: a VisionLLM over Chat Completions, through the OpenAI SDK.

Read from docs.baseten.co (Model APIs: overview, reasoning, vision, chat-completions reference).
It differs from Muse Spark on the Meta Model API (meta_api.py) in three ways that matter here:

* It always reasons. The reasoning comes back as message.reasoning_content and the answer as
  message.content; only the answer becomes the response's text, so a reasoning that ran out of
  max_tokens leaves an empty answer, never the reasoning passed off as one. reasoning_effort takes
  low, medium, high or xhigh (the model's default); "none" and "minimal" would silently run at low,
  so they are refused rather than remapped.
* It has no structured outputs or JSON mode ("All except Muse Spark Open support them"). A
  request's json_schema is put in the prompt instead, and the answer is read as JSON; the only
  repair is removing a Markdown fence that wraps the whole of it.
* Baseten includes reasoning tokens in completion_tokens, which is what output_tokens holds. They
  are billed as output, and completion_tokens_details.reasoning_tokens is only a breakdown.

Images go in as base64 data URLs (the reference allows "the URL of the image, or a base64-encoded
data URL"). The key is env BASETEN_API_KEY, read, like the Meta key, when the first call is made;
the timeout and the retries (429 and 5xx, with backoff and Retry-After) are meta_api's.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from typing import Any

import openai
from dotenv import load_dotenv

from archivist.models.base import LLMRequest, LLMResponse, Usage
from archivist.models.budget import Price
from archivist.models.meta_api import DOTENV_PATH, TIMEOUT_S, MissingAPIKey, _with_retries, data_url

BASE_URL = "https://inference.baseten.co/v1"
KEY_ENV = "BASETEN_API_KEY"
MUSE_SPARK_OPEN = "meta-models/muse-spark-open-1026"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
SCHEMA_NOTE = (
    "\n\nAnswer with one JSON object and nothing else, without a Markdown fence. It must "
    "validate against this JSON Schema:\n"
)
_FENCE = re.compile(r"\A\s*```(?:json)?[ \t]*\n(.*?)\n?```\s*\Z", re.DOTALL | re.IGNORECASE)


def api_key() -> str:
    """The key, or MissingAPIKey. The message names the variable and never any value."""
    load_dotenv(DOTENV_PATH)  # never overrides a variable that is already set
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise MissingAPIKey(f"{KEY_ENV} is not set: export it or put it in .env")
    return key


def build_payload(model_id: str, request: LLMRequest, *, reasoning_effort: str) -> dict[str, Any]:
    """Keyword arguments for chat.completions.create; the text comes first, then the images."""
    text = request.prompt
    if request.json_schema is not None:
        text += SCHEMA_NOTE + json.dumps(request.json_schema, separators=(",", ":"))
    messages: list[dict[str, Any]] = []
    if request.system is not None:
        messages.append({"role": "system", "content": request.system})
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    content += [{"type": "image_url", "image_url": {"url": data_url(i)}} for i in request.images]
    messages.append({"role": "user", "content": content})
    return {
        "model": model_id,
        "messages": messages,
        "max_tokens": request.max_output_tokens,  # caps reasoning and visible output together
        "temperature": request.temperature,
        "reasoning_effort": reasoning_effort,
    }


def json_answer(content: str) -> str:
    """The answer with a fence around all of it taken off; anything else is left as it came."""
    fenced = _FENCE.match(content)
    return fenced.group(1) if fenced else content


class BasetenLLM:
    name = "baseten"

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
        # Part of the cache key: how the schema is asked for changes the answers as much as effort.
        self.settings = {"reasoning_effort": reasoning_effort, "structured_output": "prompt"}
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
        payload = build_payload(
            self.model_id, request, reasoning_effort=self.settings["reasoning_effort"]
        )
        completion = _with_retries(
            lambda: self.client.chat.completions.create(**payload, timeout=TIMEOUT_S), self._sleep
        )
        if completion.usage is None:
            raise RuntimeError(f"{self.model_id}: response carries no usage; cost unknown")
        input_tokens = completion.usage.prompt_tokens
        output_tokens = completion.usage.completion_tokens  # reasoning tokens included
        cost = (
            input_tokens * self.price.input_per_mtok + output_tokens * self.price.output_per_mtok
        ) / 1e6
        # message.reasoning_content is the model's reasoning: not the answer, so not read.
        answer = completion.choices[0].message.content or ""
        return LLMResponse(
            text=json_answer(answer) if request.json_schema is not None else answer,
            usage=Usage(input_tokens, output_tokens, cost),
            backend=self.name,
            model_id=self.model_id,
        )
