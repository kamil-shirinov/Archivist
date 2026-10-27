"""Data contracts shared by the synthetic generator, the pipeline and the evaluator."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """Axis-aligned box in page pixels, origin top-left."""

    x0: int
    y0: int
    x1: int
    y1: int

    @model_validator(mode="after")
    def _non_empty(self) -> BBox:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("BBox requires x1 > x0 and y1 > y0")
        return self

    def area(self) -> int:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def iou(self, other: BBox) -> float:
        iw = min(self.x1, other.x1) - max(self.x0, other.x0)
        ih = min(self.y1, other.y1) - max(self.y0, other.y0)
        if iw <= 0 or ih <= 0:
            return 0.0
        inter = iw * ih
        return inter / (self.area() + other.area() - inter)


class FieldGT(BaseModel):
    field_id: str
    printed: str  # exactly as printed, e.g. "4,375.50"; "" for a blank cell
    bbox: BBox
    occluded_by: list[str] = []


class Artefact(BaseModel):
    artefact_id: str
    kind: Literal["stamp", "signature", "stain", "handwritten_amendment"]
    bbox: BBox


class SourceError(BaseModel):
    kind: Literal["balance_arithmetic", "words_figures_mismatch", "memo_ledger_mismatch"]
    field_ids: list[str]
    note: str


class PageGT(BaseModel):
    page_id: str
    doc_type: Literal["ledger", "memo"]
    image_path: str
    width: int
    height: int
    severity: int = Field(ge=0, le=3)
    fields: list[FieldGT]
    artefacts: list[Artefact]
    source_errors: list[SourceError]


class Citation(BaseModel):
    page_id: str
    bbox: BBox
    raw_bbox: BBox | None = None  # the extractor's own box, kept when bbox has been corrected


class ExtractedValue(BaseModel):
    field_id: str
    value: str | None
    citation: Citation | None
    abstained: bool = False


class Flag(BaseModel):
    field_id: str
    check: Literal["arithmetic", "words_figures", "crossdoc", "reread", "occlusion"]
    detail: str
    suggested: str | None = None  # the value the check implies, as it would be printed


class FieldVerdict(BaseModel):
    field_id: str
    value: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["accepted", "review", "abstained"]
    flags: list[Flag] = []


class PageExtraction(BaseModel):
    page_id: str
    doc_type: str  # a registered DocType name, or "unsupported"
    values: list[ExtractedValue]


# --- Verdicts (pipeline/verify.py) -------------------------------------------------------------

ReReadStatus = Literal["agrees", "disagrees", "illegible", "failed", "no_citation", "not_reread"]
Proposer = Literal["reread_chain", "check", "second_look"]


class Occluder(BaseModel):
    label: str
    bbox: BBox
    cover: float  # share of the field's box this region covers


class Evidence(BaseModel):
    route: Literal["arithmetic", "reread"]  # arithmetic: money, checked by sums as well as re-read
    citation: Citation | None  # the corrected box, and the extractor's own as raw_bbox
    crop: BBox | None = None  # the region of the page the re-reader saw
    occluded_by: list[Occluder] = []
    reread: str | None = None  # the blind re-read; None when illegible or not re-read
    reread_status: ReReadStatus
    reread_flags: list[Flag] = []  # the checks run on the re-read values: the second chain
    reread_balances: bool = False  # an equation holds for the re-read value (DocType.balanced)
    proposed: str | None = None  # the proposed correction, under the verdict's own policy
    proposed_by: Proposer | None = None
    second_look: str | None = None  # v3's second look; None when illegible or not taken
    second_look_status: ReReadStatus = "not_reread"  # compared with the extracted value
    second_crop: BBox | None = None  # the region of the page the second look saw


class PolicyOutcome(BaseModel):
    status: Literal["accepted", "review", "abstained"]
    confidence: float
    proposed: str | None = None
    proposed_by: Proposer | None = None


class VerdictRecord(FieldVerdict):
    page_id: str
    doc_type: str
    evidence: Evidence
    policy: str = "v2"  # whose outcome status, confidence and evidence.proposed are
    policies: dict[str, PolicyOutcome] = {}  # every policy's outcome; empty before v3 existed


LEDGER_COLUMNS = frozenset({"date", "description", "debit", "credit", "balance"})
LEDGER_HEADER_NAMES = frozenset(
    {"account_no", "holder", "sheet_no", "brought_forward", "carried_forward"}
)
MEMO_FIELD_NAMES = frozenset(
    {"memo_no", "date", "account_no", "counterparty", "amount", "amount_words", "ledger_ref"}
)


def _require(name: str, allowed: frozenset[str], what: str) -> None:
    if name not in allowed:
        raise ValueError(f"unknown {what} {name!r}; expected one of {sorted(allowed)}")


def ledger_line_id(doc_id: str, line_no: int, column: str) -> str:
    _require(column, LEDGER_COLUMNS, "ledger column")
    return f"L:{doc_id}:{line_no:02d}:{column}"


def ledger_header_id(doc_id: str, name: str) -> str:
    _require(name, LEDGER_HEADER_NAMES, "ledger header")
    return f"L:{doc_id}:hdr:{name}"


def memo_field_id(doc_id: str, name: str) -> str:
    _require(name, MEMO_FIELD_NAMES, "memo field")
    return f"M:{doc_id}:{name}"
