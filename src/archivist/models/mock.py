"""Deterministic stand-ins for the real backends, for tests and for building the pipeline offline.

Each takes an optional function from request to answer and a fixed cost per call. Every request
received is kept in `calls`, so a test can tell whether a wrapper let a call through.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from archivist.models.base import (
    LLMRequest,
    LLMResponse,
    Region,
    SegmentRequest,
    SegmentResponse,
    Usage,
)


def _tokens(text: str) -> int:
    return (len(text) + 3) // 4


class MockLLM:
    name = "mock"

    def __init__(
        self,
        respond: Callable[[LLMRequest], str] | None = None,
        cost_usd: float = 0.0,
        model_id: str = "mock-llm",
    ) -> None:
        self.model_id = model_id
        self._respond = respond if respond is not None else lambda request: ""
        self._cost_usd = cost_usd
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        text = self._respond(request)
        usage = Usage(_tokens(request.prompt), _tokens(text), self._cost_usd)
        return LLMResponse(text=text, usage=usage, backend=self.name, model_id=self.model_id)


class MockSegmenter:
    name = "mock"

    def __init__(
        self,
        respond: Callable[[SegmentRequest], Sequence[Region]] | None = None,
        cost_usd: float = 0.0,
        model_id: str = "mock-segmenter",
    ) -> None:
        self.model_id = model_id
        self._respond = respond if respond is not None else lambda request: ()
        self._cost_usd = cost_usd
        self.calls: list[SegmentRequest] = []

    def segment(self, request: SegmentRequest) -> SegmentResponse:
        self.calls.append(request)
        regions = tuple(self._respond(request))
        usage = Usage(_tokens(" ".join(request.prompts)), 0, self._cost_usd)
        return SegmentResponse(
            regions=regions, usage=usage, backend=self.name, model_id=self.model_id
        )
