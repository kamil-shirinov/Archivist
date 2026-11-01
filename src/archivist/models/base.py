"""Model-layer contracts: one request/response pair and one protocol per capability.

A VisionLLM reads text and images and answers in text; a Segmenter finds regions on a page.
Backends implement these protocols and nothing else. The cache and the spend cap wrap them
(cache.py, budget.py), so neither can be bypassed by choosing a different backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from archivist.schema import BBox


@dataclass(frozen=True)
class LLMRequest:
    role: str
    prompt: str
    images: tuple[bytes, ...] = ()
    system: str | None = None
    json_schema: dict | None = None
    max_output_tokens: int = 4096
    temperature: float = 0.0


@dataclass(frozen=True)
class SegmentRequest:
    role: str
    image: bytes
    prompts: tuple[str, ...]


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int  # including reasoning tokens
    cost_usd: float


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: Usage
    backend: str
    model_id: str
    cached: bool = False


@dataclass(frozen=True)
class Region:
    label: str
    bbox: BBox
    score: float


@dataclass(frozen=True)
class SegmentResponse:
    regions: tuple[Region, ...]
    usage: Usage
    backend: str
    model_id: str
    cached: bool = False


class VisionLLM(Protocol):
    name: str
    model_id: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class Segmenter(Protocol):
    name: str
    model_id: str

    def segment(self, request: SegmentRequest) -> SegmentResponse: ...


@dataclass(frozen=True)
class SortFamily:
    family: str
    title: str
    description: str


@dataclass(frozen=True)
class SortRequest:
    role: str
    texts: tuple[str, ...]
    families: tuple[SortFamily, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self):
        if not 1 <= len(self.texts) <= 16 or len(self.source_refs) != len(self.texts):
            raise ValueError("sort one to sixteen texts with one source reference each")
        if not self.families or len({f.family for f in self.families}) != len(self.families):
            raise ValueError("unique enabled families required")
        # Only the fixed decision input enters the cache or is sent to the backend.
        object.__setattr__(self, "texts", tuple(text[:1024] for text in self.texts))


@dataclass(frozen=True)
class SortAnswer:
    family: str  # an enabled family, "other", or the explicit "invalid" sentinel
    raw_text: str
    input_tokens: int
    output_tokens: int
    at_token_limit: bool


@dataclass(frozen=True)
class SortResponse:
    answers: tuple[SortAnswer, ...]
    usage: Usage
    backend: str
    model_id: str
    cached: bool = False
    details: dict = field(default_factory=dict)


class TextSorter(Protocol):
    name: str
    model_id: str

    def sort(self, request: SortRequest) -> SortResponse: ...
