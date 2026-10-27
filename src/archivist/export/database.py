"""The verified database of a run: SQLite and CSVs, built from its bundle.

    python -m archivist.export.database --run test-archivist-A [--check]

Writes exports/<run>/archivist.sqlite and one CSV per table, with the same rows and columns:

- accounts: each account's holder and sheets in order, with any gaps.
- documents: one row per page, with its account, sheet or memo number and its fields by status.
- transactions: the used ledger lines, joined to the memos posted to them.
- memos: one row per payment memo, with the ledger line it is posted to.
- values: one row per extracted field, with its status, confidence, page, citation box, checks,
  reasons and proposal. In SQL the table is "values", quoted: VALUES is a keyword.
- links: memo to ledger line, card to account, sheet to the next sheet, and whether each agrees.

Text is as the extractor read it; money columns are added beside it in pence (*_pence), parsed as
the checks parse it, and empty when the text isn't an amount. Booleans are 1, 0 or empty (not
known). Lists are joined with ";", and flags and checks are JSON. Every row comes from the bundle
(bundle.py), so the database and the review UI never disagree. --check rebuilds every file and
fails unless the ones on disk are byte-identical.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import tempfile
from collections.abc import Sequence
from pathlib import Path

from archivist.doctypes.ledger import money
from archivist.export import bundle as B
from archivist.export.schema import Bundle, BundleFlag
from archivist.pipeline.extract import RUNS_DIR
from archivist.schema import BBox

EXPORTS_DIR = Path("exports")
DATABASE_FILE = "archivist.sqlite"

# Table -> columns as (name, SQL type); the first is the key. The last column of every table is
# never free text, so no CSV line ends in a space.
TABLES: dict[str, tuple[tuple[str, str], ...]] = {
    "accounts": (
        ("account_no", "TEXT"),
        ("printed", "TEXT"),
        ("holder", "TEXT"),
        ("sheets", "TEXT"),
        ("page_ids", "TEXT"),
        ("missing_sheets", "TEXT"),
        ("cards", "INTEGER"),
    ),
    "documents": (
        ("page_id", "TEXT"),
        ("doc_type", "TEXT"),
        ("image_path", "TEXT"),
        ("width", "INTEGER"),
        ("height", "INTEGER"),
        ("account_no", "TEXT"),
        ("sheet", "INTEGER"),
        ("memo_no", "TEXT"),
        ("accepted", "INTEGER"),
        ("review", "INTEGER"),
        ("abstained", "INTEGER"),
        ("fields", "INTEGER"),
    ),
    "transactions": (
        ("txn_id", "TEXT"),
        ("account_no", "TEXT"),
        ("page_id", "TEXT"),
        ("sheet", "INTEGER"),
        ("line", "INTEGER"),
        ("date", "TEXT"),
        ("description", "TEXT"),
        ("debit", "TEXT"),
        ("credit", "TEXT"),
        ("balance", "TEXT"),
        ("debit_pence", "INTEGER"),
        ("credit_pence", "INTEGER"),
        ("balance_pence", "INTEGER"),
        ("status", "TEXT"),
        ("memos", "TEXT"),
        ("memos_agree", "INTEGER"),
    ),
    "memos": (
        ("page_id", "TEXT"),
        ("memo_no", "TEXT"),
        ("date", "TEXT"),
        ("account_no", "TEXT"),
        ("counterparty", "TEXT"),
        ("amount", "TEXT"),
        ("amount_words", "TEXT"),
        ("ledger_ref", "TEXT"),
        ("status", "TEXT"),
        ("posted_account_no", "TEXT"),
        ("txn_id", "TEXT"),
        ("amount_pence", "INTEGER"),
        ("agrees", "INTEGER"),
    ),
    "values": (
        ("field_id", "TEXT"),
        ("page_id", "TEXT"),
        ("doc_type", "TEXT"),
        ("name", "TEXT"),
        ("line", "INTEGER"),
        ("value", "TEXT"),
        ("status", "TEXT"),
        ("confidence", "REAL"),
        ("x0", "INTEGER"),
        ("y0", "INTEGER"),
        ("x1", "INTEGER"),
        ("y1", "INTEGER"),
        ("original_x0", "INTEGER"),
        ("original_y0", "INTEGER"),
        ("original_x1", "INTEGER"),
        ("original_y1", "INTEGER"),
        ("reread", "TEXT"),
        ("reread_status", "TEXT"),
        ("checks", "TEXT"),  # the rules of the checks that failed on it
        ("flags", "TEXT"),  # every flag, as JSON
        ("reread_flags", "TEXT"),
        ("reasons", "TEXT"),
        ("proposal", "TEXT"),
        ("proposed_by", "TEXT"),
        ("occluded", "INTEGER"),
    ),
    "links": (
        ("link_id", "TEXT"),
        ("kind", "TEXT"),
        ("source", "TEXT"),
        ("target", "TEXT"),
        ("source_fields", "TEXT"),
        ("target_fields", "TEXT"),
        ("checks", "TEXT"),
        ("note", "TEXT"),
        ("agrees", "INTEGER"),
    ),
}

Row = tuple[object, ...]


def _pence(text: str | None) -> int | None:
    amount = None if text is None else money(text)
    return None if amount is None else int(amount * 100)


def _bool(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _box(box: BBox | None) -> tuple[int | None, ...]:
    return (None,) * 4 if box is None else (box.x0, box.y0, box.x1, box.y1)


def _flags(flags: Sequence[BundleFlag]) -> str:
    return json.dumps([f.model_dump() for f in flags], ensure_ascii=False)


def rows(bundle: Bundle) -> dict[str, list[Row]]:
    """Every table's rows, in the bundle's order."""
    text = {f.field_id: f.value for f in bundle.fields}
    status = {f.field_id: f.status for f in bundle.fields}
    links = {link.link_id: link for link in bundle.links}
    txn_of = {memo: t for t in bundle.transactions for memo in t.memos}
    pages = {p.page_id: p for p in bundle.pages}

    accounts = [
        (
            a.account_no,
            a.printed,
            a.holder,
            ";".join(str(s.sheet) for s in a.sheets),
            ";".join(s.page_id for s in a.sheets),
            ";".join(str(s) for s in a.missing_sheets),
            len(a.sheets),
        )
        for a in bundle.accounts
    ]
    documents = [
        (
            d.page_id,
            d.doc_type,
            pages[d.page_id].image_path,
            pages[d.page_id].width,
            pages[d.page_id].height,
            d.account_no,
            d.sheet,
            d.memo_no,
            *(d.by_status.get(s, 0) for s in ("accepted", "review", "abstained")),
            d.fields,
        )
        for d in bundle.documents
    ]
    transactions = [
        (
            t.txn_id,
            t.account_no,
            t.page_id,
            t.sheet,
            t.line,
            t.date,
            t.description,
            t.debit,
            t.credit,
            t.balance,
            _pence(t.debit),
            _pence(t.credit),
            _pence(t.balance),
            t.status,
            ";".join(t.memos),
            _bool(t.memos_agree),
        )
        for t in bundle.transactions
    ]
    memos = []
    for d in bundle.documents:
        if d.doc_type != "payment_memo":
            continue
        ids = pages[d.page_id].field_ids
        named = {f.rsplit(":", 1)[-1]: f for f in ids}
        link = links.get(f"memo_line:{d.page_id}")
        txn = txn_of.get(d.page_id)
        memos.append(
            (
                d.page_id,
                *(
                    text.get(named[n])
                    for n in ("memo_no", "date", "account_no", "counterparty", "amount")
                ),
                text.get(named["amount_words"]),
                text.get(named["ledger_ref"]),
                B.worst([status[f] for f in ids]),
                txn.account_no if txn else None,
                txn.txn_id if txn else None,
                _pence(text.get(named["amount"])),
                _bool(link.agrees) if link else None,
            )
        )
    values = [
        (
            f.field_id,
            f.page_id,
            f.doc_type,
            f.name,
            f.line,
            f.value,
            f.status,
            f.confidence,
            *_box(f.box),
            *_box(f.original_box),
            f.reread,
            f.reread_status,
            ";".join(dict.fromkeys(r.rule for r in f.reasons if r.code == "rule_failed")),
            _flags(f.flags),
            _flags(f.reread_flags),
            ";".join(r.code if r.rule is None else f"{r.code}:{r.rule}" for r in f.reasons),
            f.proposal,
            f.proposed_by,
            int(bool(f.occluders)),
        )
        for f in bundle.fields
    ]
    link_rows = [
        (
            link.link_id,
            link.kind,
            link.source,
            link.target,
            ";".join(link.source_fields),
            ";".join(link.target_fields),
            json.dumps(link.checks),
            link.note,
            _bool(link.agrees),
        )
        for link in bundle.links
    ]
    return {
        "accounts": accounts,
        "documents": documents,
        "transactions": transactions,
        "memos": memos,
        "values": values,
        "links": link_rows,
    }


def csv_text(table: str, table_rows: Sequence[Row]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(name for name, _ in TABLES[table])
    writer.writerows(["" if v is None else v for v in row] for row in table_rows)
    return out.getvalue()


def _sqlite(path: Path, tables: dict[str, list[Row]]) -> None:
    """A fresh database file: the same rows give the same bytes."""
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        for table, columns in TABLES.items():
            names = ", ".join(f'"{name}" {kind}' for name, kind in columns)
            db.execute(f'CREATE TABLE "{table}" ({names}, PRIMARY KEY ("{columns[0][0]}"))')
            marks = ", ".join("?" for _ in columns)
            db.executemany(f'INSERT INTO "{table}" VALUES ({marks})', tables[table])
        db.commit()
    finally:
        db.close()


def write(bundle: Bundle, out_dir: Path) -> list[Path]:
    """Writes the database and the CSVs; returns their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = rows(bundle)
    written = []
    for table, table_rows in tables.items():
        path = out_dir / f"{table}.csv"
        path.write_text(csv_text(table, table_rows), encoding="utf-8")
        written.append(path)
    temp = out_dir / f".{DATABASE_FILE}.tmp"
    _sqlite(temp, tables)
    os.replace(temp, out_dir / DATABASE_FILE)
    written.append(out_dir / DATABASE_FILE)
    return written


def check(bundle: Bundle, out_dir: Path, scratch: Path) -> list[str]:
    """Files on disk that differ from a fresh export written to scratch; empty when none do."""
    fresh = write(bundle, scratch)
    problems = []
    for path in fresh:
        on_disk = out_dir / path.name
        if not on_disk.exists():
            problems.append(f"{on_disk} is missing")
        elif on_disk.read_bytes() != path.read_bytes():
            problems.append(f"{on_disk} differs from a fresh export of {bundle.run.run_id}")
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run", required=True, help="the verification run to export")
    parser.add_argument("--check", action="store_true", help="verify the files on disk instead")
    args = parser.parse_args(argv)

    bundle = B.build(RUNS_DIR / args.run)
    out_dir = EXPORTS_DIR / args.run
    if args.check:
        with tempfile.TemporaryDirectory() as scratch:
            problems = check(bundle, out_dir, Path(scratch))
        if problems:
            raise SystemExit("\n".join(problems))
        print(f"{out_dir}: identical to a fresh export")
        return
    for path in write(bundle, out_dir):
        print(f"-> {path} ({path.stat().st_size:,} bytes)")
    tables = rows(bundle)
    print(", ".join(f"{len(r)} {table}" for table, r in tables.items()))


if __name__ == "__main__":
    main()
