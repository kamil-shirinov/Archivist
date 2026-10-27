"""The run bundle the review UI reads: pydantic models, and the JSON Schema its TypeScript types are
generated from.

    python -m archivist.export.schema

writes ui/schema/bundle.schema.json. SCHEMA_VERSION changes whenever a model here does: the major
number when a field is removed, renamed or changes meaning, the minor when one is added.

Boxes are page pixels, origin top-left. Every value is a string exactly as the extractor read it
(or None when it didn't), never a number: the database adds parsed amounts beside the text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from archivist.schema import BBox

SCHEMA_VERSION = "1.0"
SCHEMA_PATH = Path("ui/schema/bundle.schema.json")

Status = Literal["accepted", "review", "abstained"]
ReasonCode = Literal[
    "read_mismatch",  # the blind re-read reads something else
    "reread_illegible",
    "reread_failed",
    "no_citation",  # no box to re-read, so it could not be verified
    "rule_failed",  # a check on the extracted values failed; rule names it
    "obscured",  # a stamp or stain covers part of the box
    "not_read",  # the extractor abstained
]


class RunInfo(BaseModel):
    run_id: str  # the verification run
    extraction_run: str
    split: str
    images: str  # the folder the page images are in, relative to the repository
    policy: str  # whose outcome each field's status, confidence and proposal are
    citations: str
    verification: dict[str, Any]  # the verification run's run.json, as written
    extraction: dict[str, Any]  # the extraction run's run.json, as written


class Page(BaseModel):
    page_id: str
    image_path: str  # relative to the repository
    width: int
    height: int
    doc_type: str  # a registered type, "unsupported", or "failed" when extraction failed
    failure: str | None = None  # why extraction failed
    field_ids: list[str]  # in the order the page is read


class BundleFlag(BaseModel):
    check: Literal["arithmetic", "words_figures", "crossdoc", "reread", "occlusion"]
    rule: str  # rules.RULES: e.g. running_balance, memo_amount, reread_mismatch, unresolvable
    detail: str
    suggested: str | None  # the value the check implies, as it would be printed
    related: list[str]  # the other fields in its equation


class Reason(BaseModel):
    code: ReasonCode
    rule: str | None = None  # for rule_failed


class BundleOccluder(BaseModel):
    label: str
    box: BBox
    cover: float  # share of the field's box it covers


class BundleField(BaseModel):
    field_id: str
    page_id: str
    doc_type: str
    name: str  # the column or header name, e.g. debit, holder, amount_words
    line: int | None  # the ledger line, for a line's field
    value: str | None
    status: Status
    confidence: float
    box: BBox | None  # the corrected citation box
    original_box: BBox | None  # the extractor's own box (the same box when it was not corrected)
    crop: BBox | None  # the region the blind re-read saw
    reread: str | None  # None when illegible, failed or not re-read
    reread_status: Literal[
        "agrees", "disagrees", "illegible", "failed", "no_citation", "not_reread"
    ]
    second_look: str | None  # policy v3's second look, kept as evidence
    flags: list[BundleFlag]  # checks on the extracted values, then the verification's notes
    reread_flags: list[BundleFlag]  # checks on the re-read values
    proposal: str | None
    proposed_by: Literal["reread_chain", "check", "second_look"] | None
    occluders: list[BundleOccluder]
    reasons: list[Reason]  # why it is not accepted; empty when accepted


class Document(BaseModel):
    page_id: str
    doc_type: str
    account_no: str | None  # the account it belongs to: a card's group, a memo's posting
    sheet: int | None  # a card's sheet number
    memo_no: str | None
    fields: int
    by_status: dict[str, int]


class Sheet(BaseModel):
    sheet: int
    page_id: str
    account_reads: str | None  # the account number as this card reads it
    agrees: bool  # it reads the account's number


class Account(BaseModel):
    account_no: str  # digits
    printed: str  # as the cards that read it print it
    holder: str | None
    sheets: list[Sheet]  # in sheet order
    missing_sheets: list[int]  # gaps between its first and last sheet


class Transaction(BaseModel):
    """A used ledger line, joined to the memos posted to it."""

    txn_id: str  # <page_id>:<line>
    account_no: str | None
    page_id: str
    sheet: int | None
    line: int
    date: str | None
    description: str | None
    debit: str | None
    credit: str | None
    balance: str | None
    field_ids: dict[str, str]  # column -> field id
    status: Status  # accepted only when every field of the line is
    memos: list[str]  # page ids of the memos posted to this line
    memos_agree: bool | None  # every memo's link agrees; None without memos or when unknown


class Link(BaseModel):
    link_id: str
    kind: Literal["memo_line", "card_account", "sheet_sheet"]
    source: str  # a page id
    target: str | None  # a page id, or an account number for card_account; None if not found
    source_fields: list[str]
    target_fields: list[str]
    checks: dict[str, bool | None]  # each comparison: None when a value in it was not read
    agrees: bool | None  # every known check agrees; None when none is known or nothing found
    note: str | None = None  # why it was not found or not compared


class Bundle(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run: RunInfo
    pages: list[Page]
    fields: list[BundleField]
    documents: list[Document]
    accounts: list[Account]
    transactions: list[Transaction]
    links: list[Link]


class TruthPage(BaseModel):
    page_id: str
    severity: int  # the damage level the page was degraded at, 0–3
    values: dict[str, str]  # field id -> the value as printed


class Truth(BaseModel):
    """For the demo only, from --truth: never part of the bundle."""

    schema_version: str = SCHEMA_VERSION
    run_id: str
    split: str
    pages: list[TruthPage]


def json_schema() -> str:
    return json.dumps(Bundle.model_json_schema(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json_schema(), encoding="utf-8")
    print(f"schema {SCHEMA_VERSION} -> {args.out}")


if __name__ == "__main__":
    main()
