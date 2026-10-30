"""Muse Spark Open on Fireworks: the same model as baseten_api.py, a second host (P30).

The id, accounts/fireworks/models/muse-spark-open, is the one Fireworks lists for the key
(GET /inference/v1/models, read 2026-10-30): serverless, state READY, image input supported,
context 1,048,576 tokens. Its description there: an open-weights reasoning model, 816B total /
42B active parameters, text and images in, text out. Fireworks lists one id with no revision
suffix, while Baseten's slug ends in -1026, so the two hosts' checkpoints are not known to be
identical.

Everything about the request is Baseten's, deliberately, so that the same page asks the same
question of both hosts: the JSON Schema is put in the prompt (Fireworks' structured-output guide
warns that response_format json_schema switches reasoning off for a reasoning model), the answer
has a Markdown fence taken off and brackets left open closed under baseten_api's rules, images go
in as base64 data URLs, and reasoning_effort takes low, medium, high or xhigh, never "none" or
"minimal". Only the host differs: the base URL below and the key, env FIREWORKS_API_KEY, read when
the first call is made. The timeout and the retries (429 and 5xx) are meta_api's; any other status,
a 402 or 412 for an account that needs a payment method, say, is raised at once and never retried.

Measured on a synthetic development card, 2026-10-30, through this backend (the docs say nothing
of these for Muse Spark Open): reasoning_effort "low" and "xhigh" are both accepted and change the
reasoning (244 and 738 reasoning tokens for the same three values). The reasoning comes back as
message.reasoning_content and the answer as message.content, and usage.completion_tokens includes
the reasoning (322 = 244 reasoning + 78 answer; completion_tokens_details.reasoning_tokens is only
a breakdown), exactly as on Baseten, so output_tokens is completion_tokens. Only the answer becomes
the response's text. Image input works; the calls were accepted with no payment method asked for.

Prices are Fireworks' serverless row for Muse Spark Open (fireworks.ai/models/fireworks/
muse-spark-open and docs.fireworks.ai/serverless/pricing, read 2026-10-30): $1.25 input, $0.15
cached input, $4.25 output per 1M tokens, the same as Baseten's. Cached input is billed as
ordinary input here, so spend is overstated, never understated. Reasoning tokens are in
completion_tokens, so they are billed as output.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import openai
from dotenv import load_dotenv

from archivist.models.base import LLMRequest, LLMResponse, Usage
from archivist.models.baseten_api import (
    REASONING_EFFORTS,
    STRUCTURED_OUTPUT,
    build_payload,
    close_brackets,
    json_answer,
)
from archivist.models.budget import Price
from archivist.models.meta_api import DOTENV_PATH, TIMEOUT_S, MissingAPIKey, _with_retries

BASE_URL = "https://api.fireworks.ai/inference/v1"
KEY_ENV = "FIREWORKS_API_KEY"
MUSE_SPARK_OPEN = "accounts/fireworks/models/muse-spark-open"


def api_key() -> str:
    """The key, or MissingAPIKey. The message names the variable and never any value."""
    load_dotenv(DOTENV_PATH)  # never overrides a variable that is already set
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise MissingAPIKey(f"{KEY_ENV} is not set: export it or put it in .env")
    return key


class FireworksLLM:
    name = "fireworks"

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
        # Part of the cache key, as for Baseten: how the schema is asked for changes the answers.
        self.settings = {
            "reasoning_effort": reasoning_effort,
            "structured_output": STRUCTURED_OUTPUT,
        }
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
        choice = completion.choices[0]
        text = choice.message.content or ""
        if request.json_schema is not None:
            text = json_answer(text)
            if choice.finish_reason == "stop":  # not one cut off by max_tokens
                text = close_brackets(text)
        return LLMResponse(
            text=text,
            usage=Usage(input_tokens, output_tokens, cost),
            backend=self.name,
            model_id=self.model_id,
        )
