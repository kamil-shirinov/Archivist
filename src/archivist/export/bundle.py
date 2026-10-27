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

--truth also writes data/bundles/<run>/truth.json for the demo: each page's damage level and the
values as printed, from data/<split>/gt/. It is the only thing here that reads ground truth, and
it never goes into the bundle. --check writes nothing: it rebuilds the bundle and fails unless
the file on disk is byte-identical and valid.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from archivist.doctypes import Card, Posting
from archivist.doctypes.ledger import MEMO_LEAD, date_items
from archivist.export import rules
from archivist.export.schema import (
    Account,
    Bundle,
    BundleField,
    BundleFlag,
    BundleOccluder,
    Document,
    Link,
    Page,
    Reason,
    RunInfo,
    Sheet,
    Transaction,
    Truth,
    TruthPage,
)
from archivist.pipeline.extract import IMAGE_SUFFIXES, RUNS_DIR, load_predictions
from archivist.pipeline.verify import VERDICTS_FILE, field_kind, load_verdicts
from archivist.schema import Flag, PageExtraction, PageGT, VerdictRecord

BUNDLES_DIR = Path("data/bundles")
BUNDLE_FILE = "bundle.json"
TRUTH_FILE = "truth.json"
STATUS_ORDER = ("abstained", "review", "accepted")  # worst first
FAILED = "failed"


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


def _field(v: VerdictRecord, extracted: rules.Reading, reread: rules.Reading) -> BundleField:
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
        reread=e.reread,
        reread_status=e.reread_status,
        second_look=e.second_look,
        flags=_flags(v.flags, extracted),
        reread_flags=_flags(e.reread_flags, reread),
        proposal=e.proposed,
        proposed_by=e.proposed_by,
        occluders=[BundleOccluder(label=o.label, box=o.bbox, cover=o.cover) for o in e.occluded_by],
        reasons=[
            Reason(code=code, rule=rule)
            for code, rule in rules.reasons(v.status, e.reread_status, v.flags, bool(e.occluded_by))
        ],
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


def _pages(images: Path, extracted: Sequence[PageExtraction], failed: dict[str, str]) -> list[Page]:
    doc_types = {p.page_id: p.doc_type for p in extracted}
    field_ids = {p.page_id: [v.field_id for v in p.values] for p in extracted}
    out = []
    for path in sorted(p for p in images.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES):
        with Image.open(path) as image:
            width, height = image.size
        page_id = path.stem
        out.append(
            Page(
                page_id=page_id,
                image_path=path.as_posix(),
                width=width,
                height=height,
                doc_type=doc_types.get(page_id, FAILED),
                failure=None if page_id in doc_types else failed.get(page_id, "not extracted"),
                field_ids=field_ids.get(page_id, []),
            )
        )
    return out


def build(run_dir: Path) -> Bundle:
    """The bundle of one verification run; reads no ground truth."""
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    source_dir = run_dir.parent / record["source_run"]
    source = json.loads((source_dir / "run.json").read_text(encoding="utf-8"))
    images = Path(record["images"])
    extracted = load_predictions(source_dir / "predictions.jsonl")
    verdicts = load_verdicts(run_dir / VERDICTS_FILE)

    reading = rules.Reading(extracted)
    reread = rules.Reading(reread_pages(extracted, verdicts))
    fields = [_field(v, reading, reread) for v in verdicts]
    pages = _pages(images, extracted, source.get("failed_pages", {}))
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
            split=images.parent.name,
            images=images.as_posix(),
            policy=record["policy"]["version"],
            citations=record["citations"],
            verification=record,
            extraction=source,
        ),
        pages=pages,
        fields=fields,
        documents=_documents(pages, fields, reading),
        accounts=_accounts(reading, text),
        transactions=_transactions(reading, status, text, by_id),
        links=links,
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
    out_dir.mkdir(parents=True, exist_ok=True)
    written = [out_dir / BUNDLE_FILE]
    written[0].write_text(_json(bundle), encoding="utf-8")
    if with_truth:
        written.append(out_dir / TRUTH_FILE)
        written[1].write_text(_json(truth(bundle)), encoding="utf-8")
    return written


def check(bundle: Bundle, out_dir: Path) -> list[str]:
    """What is wrong with the bundle on disk: empty when it is this bundle, byte for byte."""
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
    return problems


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
    counts = Counter(f.status for f in bundle.fields)
    print(
        f"{len(bundle.pages)} pages, {len(bundle.fields)} fields {dict(sorted(counts.items()))}, "
        f"{len(bundle.accounts)} accounts, {len(bundle.transactions)} transactions, "
        f"{len(bundle.links)} links"
    )


if __name__ == "__main__":
    main()
