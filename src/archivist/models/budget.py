"""Spend caps. The ledger is the single source of truth: spent() is the sum of its lines.

BudgetGuard owns the ledger and the caps; Budget wraps a backend and consults the guard before
each call, so the caps hold for every role that shares a guard. Each backend has its own cap,
checked against that backend's lines in the ledger: Meta's from env BUDGET_CAP_USD (default 120),
Baseten's from env BASETEN_CAP_USD (default 80) and Fireworks' from env FIREWORKS_CAP_USD (default
40), so spending on one never uses up another.
The ledger is committed (D18): cost per page is part of the evidence, and the caps survive
restarts because they are read from the same file.
"""

from __future__ import annotations

import json
import math
import os
import threading
from collections.abc import Callable, Mapping
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
# Backend name -> (env variable holding its cap in USD, the cap when the variable is unset).
BACKEND_CAPS = {
    "meta": ("BUDGET_CAP_USD", 120.0),
    "baseten": ("BASETEN_CAP_USD", 80.0),
    "fireworks": ("FIREWORKS_CAP_USD", 40.0),
}
IMAGE_TOKENS = 2_000  # projected input tokens per image, on the high side
# A SegmentRequest has no output limit; project the LLM default. SAM 3.1 is billed per image, not
# per token, so its token prices are zero and this only matters to a token-priced segmenter.
SEGMENT_OUTPUT_TOKENS = 4_096


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Price:
    """USD per million tokens, plus USD per image sent to a segmenter (one image per prompt)."""

    input_per_mtok: float
    output_per_mtok: float
    per_image_usd: float = 0.0


def caps_from_env() -> dict[str, float]:
    """Every backend's cap in USD, from its environment variable or its default."""
    return {
        backend: float(os.environ.get(variable, default))
        for backend, (variable, default) in BACKEND_CAPS.items()
    }


class BudgetGuard:
    """Thread-safe: a call reserves its projected cost before it starts and releases it when it
    is recorded or fails, so calls in flight on parallel workers count against the cap too.

    `caps` gives each named backend its own cap, checked against that backend's ledger lines and
    reservations alone; `cap_usd` caps every other backend the same way. Without a backend, check()
    and spent() look at the whole ledger against cap_usd.
    """

    def __init__(
        self,
        cap_usd: float,
        ledger_path: Path = LEDGER_PATH,
        *,
        caps: Mapping[str, float] | None = None,
    ) -> None:
        self.cap_usd = cap_usd
        self.caps = dict(caps or {})
        self.ledger_path = ledger_path
        self._lock = threading.Lock()
        self._reserved: dict[str | None, float] = {}

    def cap_for(self, backend: str | None = None) -> float:
        return self.caps.get(backend, self.cap_usd) if backend is not None else self.cap_usd

    def spent(self, backend: str | None = None) -> float:
        """Total cost in the ledger, or that of one backend's lines. An unreadable line raises:
        undercounting spend is worse.
        """
        try:
            with self.ledger_path.open(encoding="utf-8") as ledger:
                entries = (json.loads(line) for line in ledger if line.strip())
                return math.fsum(
                    e["cost_usd"] for e in entries if backend is None or e["backend"] == backend
                )
        except FileNotFoundError:
            return 0.0

    def check(self, projected: float, backend: str | None = None) -> None:
        with self._lock:
            self._check(projected, backend)

    def reserve(self, projected: float, backend: str | None = None) -> None:
        """check(), then hold `projected` against the cap until record() or release()."""
        with self._lock:
            self._check(projected, backend)
            self._reserved[backend] = self._reserved.get(backend, 0.0) + projected

    def release(self, projected: float, backend: str | None = None) -> None:
        with self._lock:
            self._reserved[backend] = self._reserved.get(backend, 0.0) - projected

    def _check(self, projected: float, backend: str | None) -> None:
        cap, spent = self.cap_for(backend), self.spent(backend)
        reserved = self._reserved.get(backend, 0.0)
        if spent + reserved + projected > cap:
            raise BudgetExceeded(
                f"{backend or 'all backends'} cap ${cap:.2f}: ${spent:.4f} spent "
                f"+ ${reserved:.4f} in flight + ${projected:.4f} projected"
            )

    def record(
        self, role: str, backend: str, model_id: str, usage: Usage, *, reserved: float = 0.0
    ) -> None:
        """Append the call to the ledger and release what it reserved, in one step."""
        with self._lock:
            self._record(role, backend, model_id, usage)
            self._reserved[backend] = self._reserved.get(backend, 0.0) - reserved

    def _record(self, role: str, backend: str, model_id: str, usage: Usage) -> None:
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
    an LLMRequest that is the system prompt and the JSON schema as well as the prompt. A
    SegmentRequest also pays per_image_usd once per prompt: a segmenter sends the page with each.
    """
    per_image = 0.0
    if isinstance(request, LLMRequest):
        chars = len(request.prompt) + len(request.system or "")
        if request.json_schema is not None:
            chars += len(json.dumps(request.json_schema))
        input_tokens = chars / 4 + IMAGE_TOKENS * len(request.images)
        output_tokens = request.max_output_tokens
    else:
        input_tokens = sum(len(prompt) for prompt in request.prompts) / 4 + IMAGE_TOKENS
        output_tokens = SEGMENT_OUTPUT_TOKENS
        per_image = price.per_image_usd * len(request.prompts)
    tokens = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1e6
    return tokens + per_image


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
        projected = project_cost(request, self.price)
        self.guard.reserve(projected, self.name)
        try:
            response = call(request)
        except BaseException:
            self.guard.release(projected, self.name)
            raise
        self.guard.record(
            request.role, self.name, response.model_id, response.usage, reserved=projected
        )
        return response
