"""The existing pipeline on one page, step by step, for the local app (P35).

Nothing here is a new way of reading. Each flow calls the pipeline's own functions in the pipeline's
own order and says, between them, which of the seven steps is under way and what it found:

- a synthetic page (ledger card or payment memo) as extract.extract_page and verify.verify read it,
  under the arm's config (config/arms/*.toml): classify, read and cite (each type's own boxes),
  stamps and stains, a blind re-read of every value, the checks, the decision;
- a Treasury Bulletin page as the pre-registered real-pages test reads it
  (templates.real_test.read_one and deep): classify among the five approved tables, read in
  context, boxes from the archive PDF's OCR layer and the page's grid, then the same verification.

Policy v2 alone decides, with no second looks, as in the real-pages test (D29: the second look
was not adopted). Every model call goes through the roles it is given, which are the cached,
capped roles of archivist.models, wrapped only to report (events.Observed). A test checks that a
flow's extraction and verdicts equal the pipeline's own on the same answers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from archivist.doctypes import UNSUPPORTED, DocType
from archivist.live.events import Recorder
from archivist.live.pages import LivePage
from archivist.pipeline import extract, reread, verify
from archivist.schema import ExtractedValue, PageExtraction, VerdictRecord
from archivist.templates import grid, ocr
from archivist.templates import test as arithmetic


@dataclass
class Outcome:
    page: LivePage
    doc_type: str  # what the page was classified as, possibly "unsupported"
    extraction: PageExtraction | None = None
    verdicts: list[VerdictRecord] = field(default_factory=list)
    calls: dict = field(default_factory=dict)
    citations: object = None  # what run.json records of how the boxes were made
    box_sources: dict[str, str] = field(default_factory=dict)
    title_confirmed: bool | None = None

    @property
    def unsupported(self) -> bool:
        return self.extraction is None


def _box(value: ExtractedValue) -> dict | None:
    return value.citation.bbox.model_dump() if value.citation else None


def _announce_values(rec: Recorder, values: Sequence[ExtractedValue], *, cited_as: str) -> None:
    """The values as read, each with the box it was first cited at: they appear on the page."""
    shown = []
    for v in values:
        box = v.citation.raw_bbox or v.citation.bbox if v.citation else None
        shown.append(
            {
                "field_id": v.field_id,
                "name": verify.field_kind(v.field_id),
                "value": v.value,
                "abstained": v.abstained or v.value is None,
                "box": box.model_dump() if box else None,
            }
        )
    rec.log.emit(
        "values",
        cited_as=cited_as,
        count=len(shown),
        to_reread=sum(v.citation is not None and verify.needs_reread(v) for v in values),
        fields=shown,
    )


def _announce_boxes(rec: Recorder, before: Mapping[str, dict | None], after) -> int:
    """Where the boxes moved to, for the values whose box changed; returns how many."""
    moved = {
        v.field_id: _box(v)
        for v in after
        if _box(v) is not None and _box(v) != before.get(v.field_id)
    }
    rec.log.emit("boxes", moved=moved)
    return len(moved)


def _decide(rec: Recorder, verdicts: Sequence[VerdictRecord], calls: dict) -> None:
    """The last three steps, which are plain code on what the re-reads gave: covered ink is read off
    the verdicts, the checks' flags counted, every value's decision announced."""
    covered = {
        (o.label, o.bbox.x0, o.bbox.y0, o.bbox.x1, o.bbox.y1): o
        for v in verdicts
        for o in v.evidence.occluded_by
    }
    rec.steps.finish(
        "sam",
        detections=len(covered),
        stamps=sum(label == "stamp" for label, *_ in covered),
        stains=sum(label == "stain" for label, *_ in covered),
        values_covered=sum(bool(v.evidence.occluded_by) for v in verdicts),
    )
    reads = Counter(v.evidence.reread_status for v in verdicts)
    rec.steps.finish(
        "blind",
        agree=reads["agrees"],
        disagree=reads["disagrees"],
        illegible=reads["illegible"],
        failed=reads["failed"] + reads["no_citation"],
    )
    rec.log.emit(
        "verdicts",
        fields=[
            {
                "field_id": v.field_id,
                "status": v.status,
                "reread_status": v.evidence.reread_status,
                "reread": v.evidence.reread,
                "proposed": v.evidence.proposed,
            }
            for v in verdicts
        ],
    )
    rec.steps.start("rules")
    checks = {"reread", "occlusion"}
    flagged = sum(any(f.check not in checks for f in v.flags) for v in verdicts)
    rec.steps.finish("rules", flagged=flagged)
    status = Counter(v.status for v in verdicts)
    rec.steps.finish("decide", **{k: status[k] for k in ("accepted", "review", "abstained")})


def _verified(
    rec: Recorder,
    extraction: PageExtraction,
    page: LivePage,
    roles: Mapping[str, object],
    doc_types: Mapping[str, DocType],
    *,
    correct_citations: bool | set[str],
    workers: int,
) -> tuple[list[VerdictRecord], dict]:
    rec.steps.route({"segmenter": "sam", "rereader": "blind"})
    verdicts, calls = verify.verify(
        [extraction],
        {page.page_id: page.path},
        roles,
        correct_citations=correct_citations,
        doc_types=doc_types,
        workers=workers,
        policy="v2",
        second_looks=False,
    )
    _decide(rec, verdicts, calls)
    return verdicts, calls


def read_synthetic(
    page: LivePage,
    roles: Mapping[str, object],
    doc_types: Mapping[str, DocType],
    rec: Recorder,
    *,
    workers: int = 4,
) -> Outcome:
    """A ledger card or payment memo, as extract.extract_page and verify.verify read it."""
    steps, llm = rec.steps, roles[extract.ROLE]
    image = page.path.read_bytes()
    recorded = extract.recorded_citations(doc_types)  # refuses an unknown strategy, before any call
    corrected, cited = verify.to_correct(recorded, doc_types)

    steps.route({"extractor": "recognise"})
    steps.start("recognise")
    kind = extract.classify(image, llm, doc_types)
    steps.finish("recognise", doc_type=kind)
    if kind == UNSUPPORTED:
        steps.close()
        return Outcome(page, kind)

    steps.route({"extractor": "read"})
    steps.start("read")
    values = extract.read_page(image, page.page_id, llm, doc_types[kind])
    steps.finish("read", values=len(values), not_read=sum(v.value is None for v in values))
    _announce_values(rec, values, cited_as=doc_types[kind].citations)
    extraction = PageExtraction(page_id=page.page_id, doc_type=kind, values=values)

    # S0+ink already moved the boxes inside read_page; the first box is kept as raw_bbox.
    moved = {
        v.field_id: _box(v)
        for v in values
        if v.citation is not None and v.citation.raw_bbox not in (None, v.citation.bbox)
    }
    rec.log.emit("boxes", moved=moved)
    steps.start("snap")
    steps.finish("snap", boxes=sum(v.citation is not None for v in values), moved=len(moved))

    verdicts, calls = _verified(
        rec, extraction, page, roles, doc_types, correct_citations=corrected, workers=workers
    )
    return Outcome(page, kind, extraction, verdicts, calls, cited)


def read_treasury(
    page: LivePage,
    roles: Mapping[str, object],
    doc_types: Mapping[str, DocType],
    rec: Recorder,
    *,
    workers: int = 4,
    layer_of: Callable[[LivePage], Sequence[ocr.Word]],
) -> Outcome:
    """A Treasury Bulletin page, as templates.real_test reads one: classified among the five
    approved tables, read in context (S0), boxed by S0+grid from the PDF's OCR layer and the page's
    grid, then verified under policy v2 with SAM on the page and no second looks."""
    from archivist.templates import real_test  # imported late: it loads the five templates

    steps, llm = rec.steps, roles[extract.ROLE]
    image = page.path.read_bytes()

    steps.route({"extractor": "recognise"})
    steps.start("recognise")
    kind = extract.classify(image, llm, doc_types)
    layer = layer_of(page) if kind != UNSUPPORTED else ()
    # The pre-registered title check: the page counts for the table only if its own OCR text
    # matches one of the table's approved title patterns. The app reads the page either way.
    confirmed = None
    if kind != UNSUPPORTED:
        text = " ".join(word.text for word in layer)
        confirmed = real_test.title_match(doc_types[kind], text) is not None
    steps.finish("recognise", doc_type=kind, title_confirmed=confirmed)
    if kind == UNSUPPORTED:
        steps.close()
        return Outcome(page, kind)
    doc_type = doc_types[kind]

    steps.route({"extractor": "read"})
    steps.start("read")
    values = extract.read_page(
        image, page.page_id, llm, doc_type, "S0", arithmetic.output_tokens(doc_type)
    )
    steps.finish("read", values=len(values), not_read=sum(v.value is None for v in values))
    _announce_values(rec, values, cited_as="S0")
    first = {v.field_id: _box(v) for v in values}

    # The boxes: the OCR layer where the figure is found there, else the page's grid, else the
    # model's own (S0+grid). Its guard re-reads some cells blind, which are rereader calls.
    steps.route({"rereader": "snap"})
    steps.start("snap")
    check = arithmetic.blind_check(image, page.page_id, doc_type, roles[reread.ROLE], workers)
    values, sources, found = grid.assign(values, doc_type, image, layer, check)
    moved = _announce_boxes(rec, first, values)
    steps.finish(
        "snap",
        boxes=sum(v.citation is not None for v in values),
        moved=moved,
        sources=dict(sorted(Counter(sources.values()).items())),
    )
    extraction = PageExtraction(page_id=page.page_id, doc_type=kind, values=values)

    verdicts, calls = _verified(
        rec, extraction, page, roles, doc_types, correct_citations=False, workers=workers
    )
    return Outcome(
        page, kind, extraction, verdicts, calls, extract.ARCHIVE_GRID, sources, confirmed
    )


def words_of(page: LivePage, real_root: Path | None = None) -> Sequence[ocr.Word]:
    """The page's OCR layer, from the archive PDF in data/real/pdf (the PDFs are not committed)."""
    from archivist.templates import real_test

    return real_test.words(page.page, real_root or real_test.DEFAULT_ROOT)
