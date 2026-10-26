"""Spend cap. The ledger is the single source of truth: spent() is the sum of its lines.

BudgetGuard owns the ledger and the cap; Budget wraps a backend and consults the guard before
each call, so the cap holds for every role that shares a guard. The ledger is committed
(D18): cost per page is part of the evidence, and the cap survives restarts because it is
read from the same file.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from archivist.models.base import (
    LLMRequest,
    LLMResponse,
    Segmenter,
    SegmentRequest,
    SegmentResponse,
    Usage,
    VisionLLM,
)

LEDGER_PATH = Path("results/spend_ledger.jsonl")
IMAGE_TOKENS = 2_000  # projected input tokens per image, on the high side
SEGMENT_OUTPUT_TOKENS = 4_096  # a SegmentRequest has no output limit; project the LLM default


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input_per_mtok: float
    output_per_mtok: float


class BudgetGuard:
    def __init__(self, cap_usd: float, ledger_path: Path = LEDGER_PATH) -> None:
        self.cap_usd = cap_usd
        self.ledger_path = ledger_path

    def spent(self) -> float:
        """Total cost in the ledger. An unreadable line raises: undercounting spend is worse."""
        try:
            with self.ledger_path.open(encoding="utf-8") as ledger:
                return math.fsum(json.loads(line)["cost_usd"] for line in ledger if line.strip())
        except FileNotFoundError:
            return 0.0

    def check(self, projected: float) -> None:
        spent = self.spent()
        if spent + projected > self.cap_usd:
            raise BudgetExceeded(
                f"cap ${self.cap_usd:.2f}: ${spent:.4f} spent + ${projected:.4f} projected"
            )

    def record(self, role: str, backend: str, model_id: str, usage: Usage) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "role": role,
            "backend": backend,
            "model_id": model_id,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": usage.cost_usd,
        }
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(entry) + "\n")


def project_cost(request: LLMRequest | SegmentRequest, price: Price) -> float:
    """A deliberately pessimistic cost for one call: assume the whole output limit is used.

    Input is 4 characters per token plus IMAGE_TOKENS per image. Everything sent counts, so for
    an LLMRequest that is the system prompt and the JSON schema as well as the prompt.
    """
    if isinstance(request, LLMRequest):
        chars = len(request.prompt) + len(request.system or "")
        if request.json_schema is not None:
            chars += len(json.dumps(request.json_schema))
        input_tokens = chars / 4 + IMAGE_TOKENS * len(request.images)
        output_tokens = request.max_output_tokens
    else:
        input_tokens = sum(len(prompt) for prompt in request.prompts) / 4 + IMAGE_TOKENS
        output_tokens = SEGMENT_OUTPUT_TOKENS
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1e6


class Budget:
    def __init__(self, inner: VisionLLM | Segmenter, guard: BudgetGuard, price: Price) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self.guard = guard
        self.price = price

    def complete(self, request: LLMRequest) -> LLMResponse:
        return self._guarded(request, self.inner.complete)

    def segment(self, request: SegmentRequest) -> SegmentResponse:
        return self._guarded(request, self.inner.segment)

    def _guarded[Req: (LLMRequest, SegmentRequest), Resp: (LLMResponse, SegmentResponse)](
        self, request: Req, call: Callable[[Req], Resp]
    ) -> Resp:
        self.guard.check(project_cost(request, self.price))
        response = call(request)
        self.guard.record(request.role, response.backend, response.model_id, response.usage)
        return response
