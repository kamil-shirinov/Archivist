"""The labels' draw, as PREREGISTRATION_REAL.md fixes it, once both configurations have run.

- The cells: every cell of a figure column (kind money) in every row the first read returned, on
  every deep-check page read without failure. The read's schema asks for every row, so a row it
  did not find comes back with every cell abstained: a row not returned. A row it returned with
  no label and no figure is a row the read left empty. Neither is sampled; both are counted, rows
  and figure cells, by page and by family, to show how much of each page the read covered
  (Deviations). A cell's id is family, page, row and column.
- How a person finds the cell (Deviations): by its row's printed label and the heading it sits
  under, as the first read returned them, and by its column heading; the row's position is only
  a hint. A read row's label is the first read's text in the table's label column, its leader
  dots dropped; its heading is the nearest row above it whose label ends in a colon. A row of a
  table read in sections takes its section's printed heading from the template, and a fixed row
  its printed label and heading (the nearest such row above it ending in a colon) from the
  template, which fixes it.
- 300 cells by random.Random(4004).sample from the four 1939–1942 families' cells sorted by id,
  then, with a fresh random.Random(4004), 100 from total_claims_by_country's. A stratum with fewer
  gives all of them. A page counts in the stratum of the family it was classified as.
- 40 of the 400 to label again, random.Random(4004).sample from the 400 sorted by id; the order
  sample returns them in is the shuffled order they are labelled in.
- 50 pages for the classification check, random.Random(4004).sample from the pages that count
  (classified and confirmed by the title check, Deviations), sorted by page id.

It records what the weights need (each family's pages, each stratum's cells) and the coverage
counts; of the first read it keeps only the row labels, and no figure, verdict or box
source. It draws once: it refuses to run where a draw is already recorded.

uv run python -m labelling.draw --side held_out  # -> results/real_test/held_out/labels/draw.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
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


LEADERS = re.compile(r"(\s*[.·…]){2,}\s*$")


def printed(label: str | None) -> str:
    """A row label as printed: leader dots and surrounding space dropped; "" if none was read."""
    return LEADERS.sub("", label or "").strip()


def heads(labels: list[str]) -> list[str]:
    """Each row's heading: the nearest label above it ending in a colon; "" for a heading itself."""
    found, current = [], ""
    for label in labels:
        if label.endswith(":"):
            found.append("")
            current = label
        else:
            found.append(current)
    return found


def names(doc_type: TemplateType, page: PageExtraction) -> dict[str, dict[str, str]]:
    """How a person finds each row of a page: its label, its heading and a position as a hint."""
    rows = doc_type.layout.rows
    if not isinstance(rows, ReadRows | Sections):
        labels = [r.printed for r in rows]
        return {
            r.key: {"label": label, "heading": head, "hint": f"row {n} of the template"}
            for n, (r, label, head) in enumerate(zip(rows, labels, heads(labels), strict=True), 1)
        }
    column = next(c.key for c in doc_type.layout.columns if c.kind == "text")
    read = {parts(v.field_id)[2]: printed(v.value) for v in page.values if parts(v.field_id)[3] == column}
    keys = doc_type.layout.row_keys
    if isinstance(rows, ReadRows):
        labels = [read.get(k, "") for k in keys]
        return {
            k: {"label": label, "heading": head, "hint": f"row {int(k)} from the top of the table"}
            for k, label, head in zip(keys, labels, heads(labels), strict=True)
        }
    named = {}
    for k in keys:
        section, number = k.rsplit("_", 1)
        heading = doc_type.layout.section(section).printed
        named[k] = {"label": read.get(k, ""), "heading": heading, "hint": f"row {int(number)} under it"}
    return named


COUNTS = (
    "rows",
    "rows_not_returned",
    "rows_left_empty",
    "figure_cells",
    "figure_cells_not_returned",
    "figure_cells_left_empty",
)


def cells_of(
    pages: list[PageExtraction], doc_types: dict
) -> tuple[dict[str, list[str]], dict[str, dict[str, int]]]:
    """Each stratum's figure cells, sorted by id; and, by page, how many rows and figure cells the
    read did not return (every cell abstained) or left empty (no label and no figure), neither
    of which is sampled."""
    stratum_of = {family: name for name, families in STRATA.items() for family in families}
    cells: dict[str, list[str]] = defaultdict(list)
    coverage: dict[str, dict[str, int]] = {}
    for page in pages:
        doc_type = doc_types[page.doc_type]
        label = next(c.key for c in doc_type.layout.columns if c.kind == "text")
        rows: dict[str, list] = defaultdict(list)
        for value in page.values:
            rows[parts(value.field_id)[2]].append(value)
        counts = dict.fromkeys(COUNTS, 0)
        for values in rows.values():
            figures = [v for v in values if parts(v.field_id)[3] in doc_type.money_fields]
            counts["rows"] += 1
            counts["figure_cells"] += len(figures)
            if all(v.abstained for v in values):
                counts["rows_not_returned"] += 1
                counts["figure_cells_not_returned"] += len(figures)
                continue
            text = next(v.value for v in values if parts(v.field_id)[3] == label)
            if not printed(text) and not any((v.value or "").strip() for v in figures):
                counts["rows_left_empty"] += 1
                counts["figure_cells_left_empty"] += len(figures)
                continue
            cells[stratum_of[page.doc_type]] += [v.field_id for v in figures]
        coverage[page.page_id] = {"family": page.doc_type, **counts}
    return {name: sorted(cells[name]) for name in STRATA}, dict(sorted(coverage.items()))


def by_family(coverage: dict[str, dict]) -> dict[str, dict[str, int]]:
    """The by-page counts summed by family, with the pages they come from."""
    totals: dict[str, dict[str, int]] = {}
    for counts in coverage.values():
        total = totals.setdefault(counts["family"], {"pages": 0, **dict.fromkeys(COUNTS, 0)})
        total["pages"] += 1
        for key in COUNTS:
            total[key] += counts[key]
    return dict(sorted(totals.items()))


def draw(out: Path) -> dict:
    """The draw for one side's records in out; refuses before both configurations have run."""
    for name in ("predictions.jsonl", verify.VERDICTS_FILE, "run.json", "sweep.json"):
        if not (out / name).exists():
            raise FileNotFoundError(f"no {name} in {out}: the labels are drawn after both runs")
    doc_types = real_test._types(real_test.CONFIG)
    pages = sorted(extract.load_predictions(out / "predictions.jsonl"), key=lambda p: p.page_id)
    by_stratum, coverage = cells_of(pages, doc_types)

    rows_named = {p.page_id: names(doc_types[p.doc_type], p) for p in pages}
    sample: list[dict] = []
    for name, cells in by_stratum.items():
        chosen = random.Random(real_test.SEED).sample(cells, min(SIZES[name], len(cells)))
        for cell in chosen:
            family, page, row, column = parts(cell)
            named = rows_named[page][row]
            sample.append(
                {
                    "order": len(sample) + 1,
                    "cell": cell,
                    "stratum": name,
                    "family": family,
                    "page": page,
                    "row": row,
                    "column": column,
                    "row_label": named["label"],
                    "row_heading": named["heading"],
                    "row_hint": named["hint"],
                    "column_heading": doc_types[family].layout.column(column).printed,
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
        "coverage_by_family": by_family(coverage),
        "coverage_by_page": coverage,
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
