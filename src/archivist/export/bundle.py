"""A verification run as one bundle for the review UI.

    python -m archivist.export.bundle --run test-archivist-A [--truth] [--check]

Reads results/runs/<run>/ (run.json, verdicts.jsonl), the extraction run it verified (its
predictions.jsonl and run.json) and the split's page images, and writes
data/bundles/<run>/bundle.json (schema.py). Nothing here calls a model or changes a run: every
derived value (rule ids, equations, reasons, accounts, postings, links) is worked out here from
what the runs recorded, and the same inputs always give the same bytes.

The bundle holds every page with its image and size; every field with its value, status,
confidence, corrected and original boxes, re-read, flags (each with its rule and the other fields
in its equation), proposal, occluders and, when not accepted, its reasons; and the documents
joined as a clerk would: each account's cards in sheet order, its used ledger lines as
transactions with the memos posted to them, and links (memo to ledger line, card to account,
sheet to the next sheet) that say whether they agree. Accounts and postings are found as the
checks found them (rules.Reading), from the extracted values; the extracted value is the one in
the database, whatever its status.

The static review UI draws from the bundle alone (D12), so it also holds, for each page, a
downsized copy of its image (images.py, in data/pages/<split>/, shared by the runs on that split),
the page's words of ink and a pen loop for each value (pen.py), SAM's detections that cover a value
and the steps the page went through; for the run, every rule's result, passed or failed
(rule_results.py), what the run is (its collection, kind of pages, arm and models) and, on the test
split, the pre-registered test report as written. All of it is worked out from the committed runs
and the images; none of it needs the model cache, a model call or ground truth.

--truth also writes data/bundles/<run>/truth.json for the demo: each page's damage level and the
values as printed, from data/<split>/gt/. It is the only thing here that reads ground truth, and
it never goes into the bundle. --check writes nothing: it rebuilds the bundle and fails unless
the file on disk is byte-identical and valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from archivist.doctypes import Card, Posting
from archivist.doctypes.ledger import MEMO_LEAD, date_items
from archivist.export import images as web
from archivist.export import pen, rule_results, rules
from archivist.export.schema import (
    SCHEMA_VERSION,
    Account,
    Accuracy,
    Bundle,
    BundleField,
    BundleFlag,
    BundleOccluder,
    Detection,
    Document,
    Link,
    Loop,
    ModelUse,
    Page,
    PageImage,
    Reason,
    RuleResult,
    RunInfo,
    Sheet,
    Step,
    Transaction,
    Truth,
    TruthPage,
)
from archivist.pipeline.extract import IMAGE_SUFFIXES, RUNS_DIR, load_predictions
from archivist.pipeline.verify import VERDICTS_FILE, field_kind, load_verdicts
from archivist.schema import Flag, PageExtraction, PageGT, VerdictRecord

BUNDLES_DIR = Path("data/bundles")
BUNDLE_FILE = "bundle.json"
INDEX_FILE = "index.json"  # in data/bundles/: the runs there, which the UI opens first
TRUTH_FILE = "truth.json"
STATUS_ORDER = ("abstained", "review", "accepted")  # worst first
FAILED = "failed"
REAL_SPLIT_PREFIX = "real"  # data/real, data/real_occ, data/real_frb: public-domain scans
COLLECTIONS = {
    "test": "Box 14"
}  # what the app calls a split's pages; the design's name for the test set
REPORT_FILE = "test_report.json"  # in results/, beside runs/
REPORT_SOURCE = f"results/{REPORT_FILE}"  # how the bundle names it, whatever the working directory
OPEN_WEIGHTS = frozenset({"baseten", "fireworks"})


def _json(model: Bundle | Truth) -> str:
    return model.model_dump_json(indent=1) + "\n"


def _known(checks: dict[str, bool | None]) -> bool | None:
    known = [v for v in checks.values() if v is not None]
    return all(known) if known else None


def worst(statuses: Sequence[str]) -> str:
    return min(statuses, key=STATUS_ORDER.index)


def _flags(flags: Sequence[Flag], reading: rules.Reading) -> list[BundleFlag]:
    return [
        BundleFlag(
            check=f.check,
            rule=rules.rule_id(f),
            detail=f.detail,
            suggested=f.suggested,
            related=rules.related(f, reading),
        )
        for f in flags
    ]


def _field(
    v: VerdictRecord, extracted: rules.Reading, reread: rules.Reading, loop: Loop | None
) -> BundleField:
    e = v.evidence
    citation = e.citation
    return BundleField(
        field_id=v.field_id,
        page_id=v.page_id,
        doc_type=v.doc_type,
        name=field_kind(v.field_id),
        line=rules.line_of(v.field_id),
        value=v.value,
        status=v.status,
        confidence=v.confidence,
        box=citation.bbox if citation else None,
        original_box=(citation.raw_bbox or citation.bbox) if citation else None,
        crop=e.crop,
        route=e.route,
        reread=e.reread,
        reread_status=e.reread_status,
        second_look=e.second_look,
        flags=_flags(v.flags, extracted),
        reread_flags=_flags(e.reread_flags, reread),
        reread_balances=e.reread_balances,
        proposal=e.proposed,
        proposed_by=e.proposed_by,
        occluders=[BundleOccluder(label=o.label, box=o.bbox, cover=o.cover) for o in e.occluded_by],
        reasons=[
            Reason(code=code, rule=rule)
            for code, rule in rules.reasons(v.status, e.reread_status, v.flags, bool(e.occluded_by))
        ],
        loop=loop,
    )


def reread_pages(
    pages: Sequence[PageExtraction], verdicts: Sequence[VerdictRecord]
) -> list[PageExtraction]:
    """The pages as the blind re-reader read them, as verify.reread_values builds them."""
    read = {v.field_id: v.evidence.reread for v in verdicts}
    out = []
    for page in pages:
        values = []
        for v in page.values:
            text = read.get(v.field_id)
            values.append(v.model_copy(update={"value": text, "abstained": text is None}))
        out.append(page.model_copy(update={"values": values}))
    return out


def _accounts(reading: rules.Reading, text: dict[str, str | None]) -> list[Account]:
    out = []
    for key, group in reading.accounts.items():
        own = [c for c in group if c.account == key]
        sheets = [c.sheet for c in group]
        present = set(sheets)
        out.append(
            Account(
                account_no=key,
                printed=own[0].account_text if own else key,
                holder=text.get(group[0].hdr("holder")),
                sheets=[
                    Sheet(
                        sheet=c.sheet,
                        page_id=c.page_id,
                        account_reads=c.account_text,
                        agrees=c.account == key,
                    )
                    for c in group
                ],
                missing_sheets=[s for s in range(min(sheets), max(sheets) + 1) if s not in present],
            )
        )
    return out


def _memo_link(page_id: str, p: Posting) -> Link:
    memo = p.memo
    source_fields = [memo.ids[n] for n in ("ledger_ref", "account_no", "amount", "date")]
    if p.line is None:
        return Link(
            link_id=f"memo_line:{page_id}",
            kind="memo_line",
            source=page_id,
            target=p.card.page_id if p.card else None,
            source_fields=source_fields,
            target_fields=[],
            checks={},
            agrees=None,
            note=p.unresolved,
        )
    line = p.line
    amount = None
    if memo.amount is not None and line.debit is not None and line.credit is not None:
        amount = line.debit != 0 and line.debit == memo.amount
    date = None
    if memo.date is not None and line.date is not None:
        date = memo.date <= line.date and line.date - memo.date <= MEMO_LEAD
    checks = {"account": not p.by_amount, "amount": amount, "date": date}
    return Link(
        link_id=f"memo_line:{page_id}",
        kind="memo_line",
        source=page_id,
        target=p.card.page_id,
        source_fields=source_fields,
        target_fields=[
            p.card.hdr("account_no"),
            *(line.ids[c] for c in ("date", "debit", "credit")),
        ],
        checks=checks,
        agrees=_known(checks),
        note=(
            f"found by the amount sheet {p.card.sheet} line {line.no:02d} of account "
            f"{p.account} debits, not by the memo's account"
            if p.by_amount
            else None
        ),
    )


def _card_link(card: Card, reading: rules.Reading) -> Link:
    key = reading.account_of.get(card.page_id)
    group = reading.accounts.get(key, []) if key else []
    note = None
    if key is None:
        note = "no sheet number can be read" if card.sheet is None else "no account"
    elif card.account != key:
        note = f"reads account {card.account_text!r}, but fills the gap in account {key}'s sheets"
    agrees = None if key is None else card.account == key
    return Link(
        link_id=f"card_account:{card.page_id}",
        kind="card_account",
        source=card.page_id,
        target=key,
        source_fields=[card.hdr("account_no")],
        target_fields=[c.hdr("account_no") for c in group if c is not card and c.account == key],
        checks={} if key is None else {"account": agrees},
        agrees=agrees,
        note=note,
    )


def _sheet_links(reading: rules.Reading) -> list[Link]:
    out = []
    for key, group in reading.accounts.items():
        for a, b in zip(group, group[1:], strict=False):
            consecutive = b.sheet == a.sheet + 1
            carry = None
            if consecutive and a.carried is not None and b.brought is not None:
                carry = a.carried == b.brought
            a_dates, b_dates = date_items(a), date_items(b)
            dates = b_dates[0][1] >= a_dates[-1][1] if a_dates and b_dates else None
            checks = {"carry": carry, "dates": dates}
            note = None
            if not consecutive:
                missing = ", ".join(str(s) for s in range(a.sheet + 1, b.sheet))
                note = f"sheet {missing} of account {key} is missing: balances not compared"
            out.append(
                Link(
                    link_id=f"sheet_sheet:{a.page_id}:{b.page_id}",
                    kind="sheet_sheet",
                    source=a.page_id,
                    target=b.page_id,
                    source_fields=[a.hdr("carried_forward")],
                    target_fields=[b.hdr("brought_forward")],
                    checks=checks,
                    agrees=_known(checks),
                    note=note,
                )
            )
    return out


def _transactions(
    reading: rules.Reading, status: dict[str, str], text: dict[str, str | None], links: dict
) -> list[Transaction]:
    on_line: dict[tuple[str, int], list[str]] = {}
    for page_id, p in reading.postings.items():
        if p.line is not None:
            on_line.setdefault((p.card.page_id, p.line.no), []).append(page_id)
    in_order = [c for group in reading.accounts.values() for c in group]
    in_order += [c for c in reading.cards.values() if c.page_id not in reading.account_of]
    out = []
    for card in in_order:
        for line in card.lines:
            memos = sorted(on_line.get((card.page_id, line.no), []))
            agree = [links[f"memo_line:{m}"].agrees for m in memos]
            out.append(
                Transaction(
                    txn_id=f"{card.page_id}:{line.no:02d}",
                    account_no=reading.account_of.get(card.page_id),
                    page_id=card.page_id,
                    sheet=card.sheet,
                    line=line.no,
                    **{c: text.get(field_id) for c, field_id in line.ids.items()},
                    field_ids=dict(line.ids),
                    status=worst([status[f] for f in line.ids.values()]),
                    memos=memos,
                    memos_agree=None if not memos or None in agree else all(agree),
                )
            )
    return out


def _documents(
    pages: Sequence[Page], fields: Sequence[BundleField], reading: rules.Reading
) -> list[Document]:
    by_page: dict[str, Counter] = {p.page_id: Counter() for p in pages}
    for f in fields:
        by_page[f.page_id][f.status] += 1
    text = {f.field_id: f.value for f in fields}
    out = []
    for page in pages:
        card = reading.cards.get(page.page_id)
        posting = reading.postings.get(page.page_id)
        account = None
        if card is not None:
            account = reading.account_of.get(page.page_id)
        elif posting is not None:
            account = posting.account or posting.memo.account
        out.append(
            Document(
                page_id=page.page_id,
                doc_type=page.doc_type,
                account_no=account,
                sheet=card.sheet if card is not None else None,
                memo_no=text.get(posting.memo.ids["memo_no"]) if posting is not None else None,
                fields=len(page.field_ids),
                by_status=dict(sorted(by_page[page.page_id].items())),
            )
        )
    return out


Ink = tuple[float, list[tuple[int, int, int, int]], tuple[int, int]]  # text height, words, size


@lru_cache(maxsize=None)
def _ink_of(path: str, mtime_ns: int, size: int) -> tuple[float, tuple, tuple[int, int]]:
    with Image.open(path) as scan:
        gray = np.asarray(scan.convert("L"))
    text_height, found = pen.words(gray)
    return text_height, tuple(found), (gray.shape[1], gray.shape[0])


def _ink(path: Path) -> Ink:
    """A page's text height, words of ink and size (once, for a scan that hasn't changed)."""
    stat = path.stat()
    text_height, found, size = _ink_of(str(path), stat.st_mtime_ns, stat.st_size)
    return text_height, list(found), size


def _scans(images: Path) -> dict[str, Path]:
    return {p.stem: p for p in sorted(images.iterdir()) if p.suffix.lower() in IMAGE_SUFFIXES}


def _loops(verdicts: Sequence[VerdictRecord], ink: dict[str, Ink]) -> dict[str, Loop]:
    """A pen loop for each value that has a box and something written in it."""
    boxes: dict[str, dict[str, tuple]] = {}
    for v in verdicts:
        if v.evidence.citation is not None and v.value:
            boxes.setdefault(v.page_id, {})[v.field_id] = (
                v.evidence.citation.bbox,
                v.evidence.crop,
            )
    out: dict[str, Loop] = {}
    for page_id, fields in boxes.items():
        text_height, found, size = ink[page_id]
        for field_id, loop in pen.loops_for(fields, found, text_height, size).items():
            out[field_id] = Loop(
                kind=loop.kind,
                d=pen.path_data(loop.points),
                width=loop.width,
                ink=[round(x) for x in loop.ink],
            )
    return out


def _detections(fields: Sequence[BundleField]) -> list[Detection]:
    """The stamps and stains that cover values, each once, with the values they cover."""
    found: dict[tuple, Detection] = {}
    for f in fields:
        for o in f.occluders:
            key = (o.label, o.box.x0, o.box.y0, o.box.x1, o.box.y1)
            found.setdefault(key, Detection(label=o.label, box=o.box, fields=[])).fields.append(
                f.field_id
            )
    return sorted(found.values(), key=lambda d: (d.box.y0, d.box.x0, d.label))


def _steps(
    page: PageExtraction,
    fields: Sequence[BundleField],
    results: Sequence[RuleResult],
    sam: Sequence[Detection],
    models: dict[str, str],
) -> list[Step]:
    """What each step of the pipeline did on this page, from what the run recorded of it."""
    reread = Counter(f.reread_status for f in fields)
    status = Counter(f.status for f in fields)
    failed = [r for r in results if not r.ok]
    return [
        Step(key="recognise", model=models.get("extractor"), facts={"doc_type": page.doc_type}),
        Step(
            key="read",
            model=models.get("extractor"),
            facts={"values": len(fields), "not_read": sum(f.value is None for f in fields)},
        ),
        Step(
            key="snap",
            model=None,
            facts={
                "boxes": sum(f.box is not None for f in fields),
                "moved": sum(f.box is not None and f.box != f.original_box for f in fields),
            },
        ),
        Step(
            key="sam",
            model=models.get("segmenter"),
            facts={
                "detections": len(sam),
                "stamps": sum(d.label == "stamp" for d in sam),
                "stains": sum(d.label == "stain" for d in sam),
                "values_covered": sum(bool(f.occluders) for f in fields),
            },
        ),
        Step(
            key="blind",
            model=models.get("rereader"),
            facts={
                "agree": reread["agrees"],
                "disagree": reread["disagrees"],
                "illegible": reread["illegible"],
                "failed": reread["failed"] + reread["no_citation"],
                "not_reread": reread["not_reread"],
            },
        ),
        Step(
            key="rules",
            model=None,
            facts={
                "applied": len(results),
                "failed": len(failed),
                "failed_rules": ", ".join(sorted({r.label for r in failed})) or None,
            },
        ),
        Step(
            key="decide",
            model=None,
            facts={k: status[k] for k in ("accepted", "review", "abstained")},
        ),
    ]


def _pages(
    scans: dict[str, Path],
    extracted: Sequence[PageExtraction],
    failed: dict[str, str],
    ink: dict[str, Ink],
    fields: Sequence[BundleField],
    results: Sequence[RuleResult],
    models: dict[str, str],
    pages_dir: Path,
    bundle_dir: Path,
    split: str,
) -> list[Page]:
    doc_types = {p.page_id: p.doc_type for p in extracted}
    by_page = {p.page_id: p for p in extracted}
    field_ids = {p.page_id: [v.field_id for v in p.values] for p in extracted}
    page_fields: dict[str, list[BundleField]] = {}
    for f in fields:
        page_fields.setdefault(f.page_id, []).append(f)
    page_results: dict[str, list[RuleResult]] = {}
    for r in results:
        page_results.setdefault(r.page_id, []).append(r)
    out = []
    for page_id, path in scans.items():
        copy = web.web_image(path)
        text_height, words, (width, height) = ink[page_id]
        sam = _detections(page_fields.get(page_id, []))
        read = page_id in doc_types
        out.append(
            Page(
                page_id=page_id,
                image_path=path.as_posix(),
                width=width,
                height=height,
                doc_type=doc_types.get(page_id, FAILED),
                failure=None if read else failed.get(page_id, "not extracted"),
                field_ids=field_ids.get(page_id, []),
                image=PageImage(
                    url=Path(
                        os.path.relpath(pages_dir / split / f"{page_id}.jpg", bundle_dir)
                    ).as_posix(),
                    width=copy.width,
                    height=copy.height,
                    bytes=len(copy.data),
                    sha256=copy.sha256,
                ),
                text_height=text_height,
                words=[list(w) for w in words],
                sam=sam,
                steps=_steps(
                    by_page[page_id],
                    page_fields.get(page_id, []),
                    page_results.get(page_id, []),
                    sam,
                    models,
                )
                if read
                else [],
            )
        )
    return out


_VERSION = re.compile(r"muse-spark-(\d+(?:\.\d+)*)")


def model_name(model_id: str) -> str:
    """A model as a person says it: muse-spark-1.3-contributor is Muse Spark 1.3."""
    low = model_id.lower()
    if low.startswith("sam-"):
        return f"SAM {low[4:]}"
    if "muse-spark-open" in low:
        return "Muse Spark Open"
    if (match := _VERSION.search(low)) is not None:
        return f"Muse Spark {match.group(1)}"
    return model_id


def _models(config: dict) -> list[ModelUse]:
    return [
        ModelUse(
            role=role,
            backend=config[role]["backend"],
            model_id=config[role]["model_id"],
            name=model_name(config[role]["model_id"]),
        )
        for role in ("extractor", "rereader", "segmenter")
        if role in config
    ]


def _arm(models: Sequence[ModelUse]) -> str:
    """Where the models that read run: Meta's API (hosted), open-weights hosts, or one of each. The
    segmenter is SAM 3.1 on Meta's API in every arm, so it does not decide."""
    backends = {m.backend for m in models if m.role in ("extractor", "rereader")}
    if not backends:
        return "unknown"
    if backends <= OPEN_WEIGHTS:
        return "open-weights"
    return "hosted" if backends.isdisjoint(OPEN_WEIGHTS) else "mixed"


def _accuracy(run_dir: Path, split: str) -> Accuracy | None:
    path = run_dir.parent.parent / REPORT_FILE
    if split != "test" or not path.exists():
        return None
    raw = path.read_bytes()
    return Accuracy(
        source=REPORT_SOURCE, sha256=hashlib.sha256(raw).hexdigest(), report=json.loads(raw)
    )


def build(
    run_dir: Path, pages_dir: Path = web.PAGES_DIR, bundles_dir: Path = BUNDLES_DIR
) -> Bundle:
    """The bundle of one verification run; reads no ground truth."""
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    source_dir = run_dir.parent / record["source_run"]
    source = json.loads((source_dir / "run.json").read_text(encoding="utf-8"))
    images = Path(record["images"])
    split = images.parent.name
    extracted = load_predictions(source_dir / "predictions.jsonl")
    verdicts = load_verdicts(run_dir / VERDICTS_FILE)

    scans = _scans(images)
    ink = {page_id: _ink(path) for page_id, path in scans.items()}
    loops = _loops(verdicts, ink)
    reading = rules.Reading(extracted)
    reread = rules.Reading(reread_pages(extracted, verdicts))
    fields = [_field(v, reading, reread, loops.get(v.field_id)) for v in verdicts]
    flags = [flag for v in verdicts for flag in v.flags]
    results = rule_results.rule_results(reading, flags)
    models = _models(record.get("config", {}))
    pages = _pages(
        scans,
        extracted,
        source.get("failed_pages", {}),
        ink,
        fields,
        results,
        {m.role: m.name for m in models},
        pages_dir,
        bundles_dir / record["run_id"],
        split,
    )
    text = {f.field_id: f.value for f in fields}
    status = {f.field_id: f.status for f in fields}

    memo_links = [_memo_link(page_id, p) for page_id, p in reading.postings.items()]
    card_links = [_card_link(card, reading) for card in reading.cards.values()]
    links = [*memo_links, *card_links, *_sheet_links(reading)]
    by_id = {link.link_id: link for link in links}
    return Bundle(
        run=RunInfo(
            run_id=record["run_id"],
            extraction_run=record["source_run"],
            split=split,
            images=images.as_posix(),
            policy=record["policy"]["version"],
            citations=record["citations"],
            verification=record,
            extraction=source,
            collection=COLLECTIONS.get(split, split),
            source="public-domain scans" if split.startswith(REAL_SPLIT_PREFIX) else "synthetic",
            arm=_arm(models),
            models=models,
        ),
        pages=pages,
        fields=fields,
        documents=_documents(pages, fields, reading),
        accounts=_accounts(reading, text),
        transactions=_transactions(reading, status, text, by_id),
        links=links,
        rule_results=results,
        rule_labels=rule_results.labels(results, flags),
        accuracy=_accuracy(run_dir, split),
    )


def truth(bundle: Bundle) -> Truth:
    """Each page's damage level and printed values, from data/<split>/gt/: for the demo only."""
    gt_dir = Path(bundle.run.images).parent / "gt"
    pages = []
    for page in bundle.pages:
        gt = PageGT.model_validate_json((gt_dir / f"{page.page_id}.json").read_text("utf-8"))
        values = {f.field_id: f.printed for f in gt.fields}
        pages.append(TruthPage(page_id=page.page_id, severity=gt.severity, values=values))
    return Truth(run_id=bundle.run.run_id, split=bundle.run.split, pages=pages)


def write(bundle: Bundle, out_dir: Path, with_truth: bool = False) -> list[Path]:
    """The bundle (and truth.json) in out_dir, and the page images it names where its URLs say."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = [out_dir / BUNDLE_FILE]
    written[0].write_text(_json(bundle), encoding="utf-8")
    if with_truth:
        written.append(out_dir / TRUTH_FILE)
        written[1].write_text(_json(truth(bundle)), encoding="utf-8")
    write_images(bundle, out_dir)
    return written


def _image_path(page: Page, out_dir: Path) -> Path:
    return out_dir / page.image.url


def write_images(bundle: Bundle, out_dir: Path) -> int:
    """The downsized page images the bundle names, beside it as its URLs say; those already on
    disk with the right bytes are left alone. Returns how many were written."""
    count = 0
    for page in bundle.pages:
        dest = _image_path(page, out_dir)
        data = web.web_image(Path(page.image_path)).data
        if dest.exists() and dest.read_bytes() == data:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        count += 1
    return count


def check(bundle: Bundle, out_dir: Path) -> list[str]:
    """What is wrong with the bundle on disk: empty when it is this bundle, byte for byte, and
    every page image it names is there with the bytes it records."""
    path = out_dir / BUNDLE_FILE
    if not path.exists():
        return [f"{path} is missing"]
    on_disk = path.read_text(encoding="utf-8")
    problems = []
    try:
        Bundle.model_validate_json(on_disk)
    except ValueError as error:
        problems.append(f"{path} does not validate: {str(error)[:300]}")
    if on_disk != _json(bundle):
        problems.append(f"{path} differs from a fresh export of {bundle.run.run_id}")
    for page in bundle.pages:
        image = _image_path(page, out_dir)
        if not image.exists():
            problems.append(f"{image} is missing")
        elif hashlib.sha256(image.read_bytes()).hexdigest() != page.image.sha256:
            problems.append(f"{image} is not the image the bundle records")
    return problems


def index_entry(bundle: Bundle) -> dict:
    """What the UI needs to list a run and open its bundle: nothing that is in the bundle's body."""
    run = bundle.run
    return {
        "run_id": run.run_id,
        "path": f"{run.run_id}/{BUNDLE_FILE}",
        "collection": run.collection,
        "split": run.split,
        "source": run.source,
        "arm": run.arm,
        "models": [m.name for m in run.models],
        "policy": run.policy,
        "pages": len(bundle.pages),
        "fields": len(bundle.fields),
    }


def update_index(bundle: Bundle, bundles_dir: Path = BUNDLES_DIR) -> Path:
    """Record this run in bundles_dir/index.json, replacing its earlier entry; entries by run id."""
    bundles_dir.mkdir(parents=True, exist_ok=True)
    path = bundles_dir / INDEX_FILE
    runs = json.loads(path.read_text(encoding="utf-8"))["runs"] if path.exists() else []
    runs = [r for r in runs if r["run_id"] != bundle.run.run_id] + [index_entry(bundle)]
    runs.sort(key=lambda r: r["run_id"])
    payload = {"schema_version": SCHEMA_VERSION, "runs": runs}
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run", required=True, help="the verification run to export")
    parser.add_argument("--truth", action="store_true", help="also write truth.json (demo only)")
    parser.add_argument("--check", action="store_true", help="verify the bundle on disk instead")
    args = parser.parse_args(argv)

    bundle = build(RUNS_DIR / args.run)
    out_dir = BUNDLES_DIR / args.run
    if args.check:
        problems = check(bundle, out_dir)
        if problems:
            raise SystemExit("\n".join(problems))
        print(f"{out_dir / BUNDLE_FILE}: valid and identical to a fresh export")
        return
    for path in write(bundle, out_dir, args.truth):
        print(f"-> {path} ({path.stat().st_size:,} bytes)")
    print(f"{len(bundle.pages)} page images -> {out_dir / bundle.pages[0].image.url}, ...")
    print(f"-> {update_index(bundle)}")
    counts = Counter(f.status for f in bundle.fields)
    print(
        f"{len(bundle.pages)} pages, {len(bundle.fields)} fields {dict(sorted(counts.items()))}, "
        f"{len(bundle.accounts)} accounts, {len(bundle.transactions)} transactions, "
        f"{len(bundle.links)} links"
    )


if __name__ == "__main__":
    main()
