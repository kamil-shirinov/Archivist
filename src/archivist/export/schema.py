"""The run bundle the review UI reads: pydantic models, and the JSON Schema its TypeScript types are
generated from.

    python -m archivist.export.schema

writes ui/schema/bundle.schema.json. SCHEMA_VERSION changes whenever a model here does: the major
number when a field is removed, renamed or changes meaning, the minor when one is added.

Boxes are page pixels, origin top-left, of the page as scanned (Page.width, Page.height), whatever
size its downsized image is. Every value is a string exactly as the extractor read it (or None when
it didn't), never a number: the database adds parsed amounts beside the text.

1.2 adds the second collection and the document types: what a run's pages are (the publication, each
page's printed title, issue and page number, and whether the run is a pre-registered test or only
development pages), the row of each cell of a table, and every registered document type with its
rules, the evidence each rule held on and who approved it.

1.1 adds what the static review UI draws from: each page's downsized image, its words of ink, SAM's
detections and the steps it went through; each field's route and pen loop; every rule's result,
passed or failed; what the run is (the collection, what kind of pages, which models, which arm);
and, for the test split, the pre-registered test report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from archivist.schema import BBox

SCHEMA_VERSION = "1.2"
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


class ModelUse(BaseModel):
    role: str  # extractor, rereader or segmenter
    backend: str  # meta, baseten, fireworks
    model_id: str  # as the run's config names it
    name: str  # as a person would say it: Muse Spark 1.3, SAM 3.1


class Publication(BaseModel):
    """Where real pages come from."""

    title: str  # Treasury Bulletin
    publisher: str
    url: str
    rights: str  # the statement the archive shows


class RunInfo(BaseModel):
    run_id: str  # the verification run
    extraction_run: str
    split: str
    images: str  # the folder the page images are in, relative to the repository
    policy: str  # whose outcome each field's status, confidence and proposal are
    citations: str
    verification: dict[str, Any]  # the verification run's run.json, as written
    extraction: dict[str, Any]  # the extraction run's run.json, as written
    collection: str  # what the pages are called in the app: "Box 14" for the synthetic test set
    source: Literal["synthetic", "public-domain scans"]  # what the pages are
    # where the reading models run: Meta's API, open-weights hosts, one of each, or not recorded
    arm: Literal["hosted", "open-weights", "mixed", "unknown"]
    models: list[ModelUse]  # each role's model, from the run's config
    stage: Literal[
        "test", "development"
    ]  # the pre-registered test, or pages used to build the rules
    publication: Publication | None  # for real pages


class PageImage(BaseModel):
    url: str  # relative to this bundle file, in the folder of downsized page images
    width: int  # the downsized image's size; boxes are in the scan's pixels (Page.width, height)
    height: int
    bytes: int
    sha256: str


class Detection(BaseModel):
    """A stamp or a stain SAM 3.1 found that covers a value: the regions are known only through the
    verdicts, which record those covering at least a tenth of a value's box."""

    label: str
    box: BBox
    fields: list[str]  # the values it covers


class Step(BaseModel):
    """One step the page went through, and what it found, as numbers the UI words."""

    key: Literal["recognise", "read", "snap", "sam", "blind", "rules", "decide"]
    model: str | None  # the model that did it; None for plain code
    facts: dict[str, int | float | str | None]


class Page(BaseModel):
    page_id: str
    image_path: str  # relative to the repository
    width: int
    height: int
    doc_type: str  # a registered type, "unsupported", or "failed" when extraction failed
    failure: str | None = None  # why extraction failed
    field_ids: list[str]  # in the order the page is read
    title: str | None  # the printed title of the table on it, for a table type
    issue: str | None  # the issue a page of a periodical is in, "1939-12"
    number: int | None  # its page in that issue's file
    image: PageImage
    text_height: float  # the page's own text height in pixels, which sizes its words and loops
    words: list[list[int]]  # every word of ink: x0, y0, x1, y1
    sam: list[Detection]
    steps: list[Step]  # in order; empty for a page that failed extraction


class BundleFlag(BaseModel):
    check: Literal["arithmetic", "words_figures", "crossdoc", "reread", "occlusion"]
    rule: str  # rules.RULES: e.g. running_balance, memo_amount, reread_mismatch, unresolvable
    detail: str
    suggested: str | None  # the value the check implies, as it would be printed
    related: list[str]  # the other fields in its equation


class Loop(BaseModel):
    """A pen loop round a value's ink (export/pen.py): clear of its own ink by a margin and of every
    other word, round for a short value and flatter for a long one, or an underline where the page
    is too crowded for a loop. Absent where the value has no ink or nothing fits."""

    kind: Literal["loop", "underline"]
    d: str  # the path as SVG data, "M x y L x y ...", in page pixels
    width: float  # the stroke's width in page pixels, which the clearance allows for
    ink: list[int]  # the value's own ink: x0, y0, x1, y1


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
    row: str | None  # the row of a table cell, as its type keys it
    value: str | None
    status: Status
    confidence: float
    box: BBox | None  # the corrected citation box
    original_box: BBox | None  # the extractor's own box (the same box when it was not corrected)
    crop: BBox | None  # the region the blind re-read saw
    route: Literal["arithmetic", "reread"]  # arithmetic: a money field, checked by sums as well
    reread: str | None  # None when illegible, failed or not re-read
    reread_status: Literal[
        "agrees", "disagrees", "illegible", "failed", "no_citation", "not_reread"
    ]
    second_look: str | None  # policy v3's second look, kept as evidence
    flags: list[BundleFlag]  # checks on the extracted values, then the verification's notes
    reread_flags: list[BundleFlag]  # checks on the re-read values
    reread_balances: bool  # an equation holds for the re-read value
    proposal: str | None
    proposed_by: Literal["reread_chain", "check", "second_look"] | None
    occluders: list[BundleOccluder]
    reasons: list[Reason]  # why it is not accepted; empty when accepted
    loop: Loop | None  # the pen loop round its ink


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


class RuleResult(BaseModel):
    """One rule applied to the values as the extractor read them, passed or failed."""

    rule_id: str  # <rule>:<page>:<the last cell of its equation>
    rule: str  # rules.RULES: running_balance, carried_forward, date_order, ...
    label: str  # plain words for the rule
    page_id: str  # the page of its target, the field it is about
    fields: list[str]  # the cells in its equation, in the order its equation is written
    ok: bool
    equation: str | None  # the sum with the values as read, e.g. "2,434.75 − 41.58 = 2,393.17"
    detail: str | None  # the check's own wording, when it failed
    suggested: str | None  # the value it implies, when it failed and says so


class DocColumn(BaseModel):
    key: str
    printed: str  # as the page prints it
    kind: str  # money, count, percent, date, text


class RuleEvidence(BaseModel):
    """What the arithmetic test of a template found for one rule, as its evidence file records."""

    applies: int  # where the rule applies on the tested pages
    evaluated: int  # of those, where every cell was read twice and agreed
    held: int
    failed: int
    hold_rate: float | None
    outcome: str  # holds, sometimes fails, rejected, untested
    not_evaluated: dict[str, int]  # why the rest were not evaluated, and how many


class DocRule(BaseModel):
    id: str  # the rule's name in a flag: <family>.<id> for a template
    label: str  # in plain words
    equation: str | None  # the identity, by cell keys
    for_each: str | None  # table, row, column or position
    evidence: RuleEvidence | None


class Approval(BaseModel):
    approved_by: str
    approved_on: str
    drafted_by: str  # the model that drafted it
    drafted_on: str
    drafted_from: list[str]  # the development pages it was drafted from
    tested_on: str | None
    tested_pages: list[str]  # the pages its arithmetic test read
    evidence_file: str | None
    evidence_sha256: str | None  # the evidence file's, recorded at approval
    dropped: list[str]  # identities the draft proposed that were left out, and why


class DocTypeInfo(BaseModel):
    name: str
    title: str  # the printed title for a template, a plain name for a built-in
    description: str
    kind: Literal["built-in", "template"]
    unit: str | None
    precision: str | None
    columns: list[DocColumn]
    rows: str  # how the rows are read, in words
    rules: list[DocRule]
    approval: (
        Approval | None
    )  # a template's; a built-in type is measured in the test report instead
    enabled: bool  # whether this run reads pages of this type
    pages: int  # how many pages of this type are in this run


class Accuracy(BaseModel):
    """The pre-registered test report of the synthetic test split, as written (results/)."""

    source: str  # the report's path in the repository
    sha256: str
    report: dict[str, Any]


class Bundle(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run: RunInfo
    pages: list[Page]
    fields: list[BundleField]
    documents: list[Document]
    accounts: list[Account]
    transactions: list[Transaction]
    links: list[Link]
    rule_results: list[RuleResult]
    rule_labels: dict[str, str]  # every rule id a flag or result carries -> plain words
    doc_types: list[DocTypeInfo]  # every registered document type: built-in, and approved templates
    accuracy: Accuracy | None  # the test report, for a run on the test split


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
