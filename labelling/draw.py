"""The labels' draw, as PREREGISTRATION_REAL.md fixes it, once both configurations have run.

- The cells: every cell of a figure column (kind money) in every row the first read returned, on
  every deep-check page read without failure. The read's schema asks for every row, so a row it
  did not find comes back with every cell abstained; such a row is not one it returned. A cell is
  named by its id: family, page, row and column.
- 300 cells by random.Random(4004).sample from the four 1939–1942 families' cells sorted by id,
  then, with a fresh random.Random(4004), 100 from total_claims_by_country's. A stratum with fewer
  gives all of them. A page counts in the stratum of the family it was classified as.
- 40 of the 400 to label again, random.Random(4004).sample from the 400 sorted by id; the order
  sample returns them in is the shuffled order they are labelled in.
- 50 pages for the classification check, random.Random(4004).sample from the pages that count
  (classified and confirmed by the title check, Deviations), sorted by page id.

It records what the weights need (each family's pages, each stratum's cells) and no value, verdict
or box source. It draws once: it refuses to run where a draw is already recorded.

uv run python -m labelling.draw --side held_out  # -> results/real_test/held_out/labels/draw.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from archivist.doctypes.template import ReadRows, Sections, TemplateType
from archivist.pipeline import extract, verify
from archivist.schema import PageExtraction
from archivist.templates import real_test

STRATA = {
    "1939_1942": real_test.FAMILIES[:4],
    "total_claims": ("total_claims_by_country",),
}
SIZES = {"1939_1942": 300, "total_claims": 100}
RELABEL = 40
PAGES_CHECKED = 50
DRAW_FILE = "draw.json"


def parts(cell: str) -> tuple[str, str, str, str]:
    """family, page, row and column of a template cell id: "T.<family>:<page>:<row>:<column>"."""
    head, page, row, column = cell.split(":")
    return head.removeprefix("T."), page, row, column


def row_named(doc_type: TemplateType, row: str) -> str:
    """The row as the labeller finds it: a fixed row's printed label, else its position."""
    rows = doc_type.layout.rows
    if isinstance(rows, ReadRows):
        return f"row {int(row)} from the top of the table"
    if isinstance(rows, Sections):
        key, number = row.rsplit("_", 1)
        return f'row {int(number)} under the heading "{doc_type.layout.section(key).printed}"'
    return next(label.printed for label in rows if label.key == row)


def cells_of(
    pages: list[PageExtraction], doc_types: dict
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Each stratum's figure cells, sorted by id; and how many rows were not returned, by family."""
    stratum_of = {family: name for name, families in STRATA.items() for family in families}
    cells: dict[str, list[str]] = defaultdict(list)
    dropped: Counter[str] = Counter()
    for page in pages:
        doc_type = doc_types[page.doc_type]
        rows: dict[str, list] = defaultdict(list)
        for value in page.values:
            rows[parts(value.field_id)[2]].append(value)
        for row, values in rows.items():
            if all(v.abstained for v in values):
                dropped[page.doc_type] += 1
                continue
            cells[stratum_of[page.doc_type]] += [
                v.field_id for v in values if parts(v.field_id)[3] in doc_type.money_fields
            ]
    return {name: sorted(cells[name]) for name in STRATA}, dict(sorted(dropped.items()))


def draw(out: Path) -> dict:
    """The draw for one side's records in out; refuses before both configurations have run."""
    for name in ("predictions.jsonl", verify.VERDICTS_FILE, "run.json", "sweep.json"):
        if not (out / name).exists():
            raise FileNotFoundError(f"no {name} in {out}: the labels are drawn after both runs")
    doc_types = real_test._types(real_test.CONFIG)
    pages = sorted(extract.load_predictions(out / "predictions.jsonl"), key=lambda p: p.page_id)
    by_stratum, rows_not_returned = cells_of(pages, doc_types)

    sample: list[dict] = []
    for name, cells in by_stratum.items():
        chosen = random.Random(real_test.SEED).sample(cells, min(SIZES[name], len(cells)))
        for cell in chosen:
            family, page, row, column = parts(cell)
            doc_type = doc_types[family]
            sample.append(
                {
                    "order": len(sample) + 1,
                    "cell": cell,
                    "stratum": name,
                    "family": family,
                    "page": page,
                    "row": row,
                    "column": column,
                    "row_named": row_named(doc_type, row),
                    "column_named": doc_type.layout.column(column).printed,
                }
            )
    relabel = random.Random(real_test.SEED).sample(
        sorted(s["cell"] for s in sample), min(RELABEL, len(sample))
    )
    counted = sorted(real_test.confirmed(out))
    checked = random.Random(real_test.SEED).sample(counted, min(PAGES_CHECKED, len(counted)))
    confirmed = real_test.confirmed(out)

    sweep = json.loads((out / "sweep.json").read_text(encoding="utf-8"))
    deep_pages = Counter(p.doc_type for p in pages)
    return {
        "side": out.name,
        "seed": real_test.SEED,
        "drawn_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "families": {
            family: {
                "classified": sweep["by_family"][family]["classified"],
                "confirmed": sweep["by_family"][family]["confirmed"],
                "deep_pages": deep_pages[family],
            }
            for family in real_test.FAMILIES
        },
        "strata": {
            name: {
                "families": list(STRATA[name]),
                "cells": len(cells),
                "sampled": sum(s["stratum"] == name for s in sample),
            }
            for name, cells in by_stratum.items()
        },
        "rows_not_returned": rows_not_returned,
        "sample": sample,
        "relabel": relabel,
        "pages_checked": [{"page": p, "family": confirmed[p]} for p in checked],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--side", choices=real_test.SIDES, required=True)
    parser.add_argument("--out", type=Path, help="default results/real_test/<side>/labels")
    args = parser.parse_args(argv)
    records = real_test.OUT_DIR / args.side
    labels = args.out or records / "labels"
    path = labels / DRAW_FILE
    if path.exists():
        parser.error(f"{path} exists: the labels are drawn once")
    record = draw(records)
    labels.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    for name, stratum in record["strata"].items():
        print(f"{name}: {stratum['sampled']} of {stratum['cells']} cells")
    print(f"{len(record['relabel'])} to relabel, {len(record['pages_checked'])} pages to check")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
