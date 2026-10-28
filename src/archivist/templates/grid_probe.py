"""Can a table's grid be found from the page alone? A feasibility probe, not a reader (P21b).

    python -m archivist.templates.grid_probe   # -> results/templates/grid_dev.md

On the pages each draft in templates/ was drafted from (development pages only, as pages.py
allows), plain image code with no model call looks for the table's rows and columns:

- ink: a pixel darker than the page's Otsu threshold (scans differ: the 1980s pages are printed
  light grey, the 1939 ones dark);
- ruled lines: a horizontal rule is a pixel row with an unbroken run of ink at least
  RULE_SHARE of the page's width long, a vertical rule a pixel column with one at least
  RULE_SHARE of its height (each counted once however thick it is printed; a line of figures,
  however dense, is broken between them);
- the body: where the draft's figures are, the envelope of the first read's S0 boxes of its
  figure cells (the only thing taken from the model, and only to know where to look);
- inside the body, the rules are taken out by their length: an unbroken vertical run of ink at
  least DOWN_RUN pixels long, or a horizontal one at least ACROSS_RUN long, is a rule, never a
  figure (a printed digit is about 25 pixels tall), however the rule leans or wobbles;
- columns: the runs of pixel columns carrying more ink than the page's floor (the 10th
  percentile pixel column: paper texture on a light scan) plus COL_LEVEL of the way to a full
  column (the 95th percentile), closer than COL_GAP pixels merged (the gaps inside a figure
  are narrower), those under MIN_COL pixels wide dropped;
- rows: within each column found, the bands of pixel rows carrying more than ROW_LEVEL of a full
  line's ink (that column's 95th percentile), closer than ROW_GAP pixels merged, those under
  MIN_ROW pixels tall dropped as specks. Counting column by column keeps a page's skew from
  smearing neighbouring lines together; the rows found are the median over the columns.

Each is set against what the draft's first read found there: the rows with at least one figure,
and the figure columns with at least one figure, and against the layout. Also: the share of the
first read's S0 figure boxes whose vertical centre falls inside a found row band. The first read
is taken from the cache only; a page whose read is not cached is reported as not read. Writes
results/templates/grid_dev.md, whatever it shows.
"""

from __future__ import annotations

import argparse
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from archivist.doctypes.template import (
    NUMERIC,
    TEMPLATES_DIR,
    TemplateType,
    drafted_types,
)
from archivist.models import load_roles
from archivist.pipeline import extract
from archivist.templates.draft import CONFIG
from archivist.templates.ink import (  # re-exported: the report and the tests use them here
    ACROSS_RUN,
    COL_GAP,
    COL_LEVEL,
    DOWN_RUN,
    MIN_COL,
    MIN_ROW,
    RULE_SHARE,
    ROW_GAP,
    ROW_LEVEL,
    otsu,
    rules,
    runs,
    without_long_runs,
)
from archivist.templates.pages import resolve
from archivist.templates.test import output_tokens

REPORT = Path("results/templates/grid_dev.md")


class NotCached(RuntimeError):
    pass


class _CacheOnly:
    """Stands behind a role's cache: a miss is refused, so the probe never makes a call."""

    def complete(self, request):
        raise NotCached("the first read is not in the cache")


def grid(ink: np.ndarray, body: tuple[int, int, int, int]) -> dict:
    """Columns, and each column's row bands, inside body (x0, y0, x1, y1), its rules taken out."""
    x0, y0, x1, y1 = body
    part = without_long_runs(ink[y0:y1, x0:x1], DOWN_RUN)
    part = without_long_runs(part.T, ACROSS_RUN).T
    profile = part.sum(axis=0)
    floor, full = np.percentile(profile, [10, 95])
    columns = runs(profile > floor + COL_LEVEL * (full - floor), COL_GAP, MIN_COL)
    by_column = []
    for a, b in columns:
        profile = part[:, a:b].sum(axis=1)
        level = ROW_LEVEL * np.percentile(profile[profile > 0], 95) if profile.any() else 1
        by_column.append([(c + y0, d + y0) for c, d in runs(profile > level, ROW_GAP, MIN_ROW)])
    counts = sorted(len(bands) for bands in by_column)
    return {
        "columns": [(a + x0, b + x0) for a, b in columns],
        "rows_by_column": by_column,
        "rows": int(np.median(counts)) if counts else 0,
        "rows_range": [counts[0], counts[-1]] if counts else [0, 0],
    }


def probe_page(doc_type: TemplateType, ref: str, llm: object) -> dict:
    page = resolve(ref)  # refuses a page that may not be sent, before anything is read
    image = page.path.read_bytes()
    record: dict = {"family": doc_type.name, "ref": ref}
    try:
        values = extract.read_page(
            image, page.page_id, llm, doc_type, "S0", output_tokens(doc_type)
        )
    except (NotCached, extract.ExtractionFailed) as error:
        return {**record, "read": f"not read: {error}"[:200]}
    figures = {c.key for c in doc_type.layout.columns if c.kind in NUMERIC}
    printed = [
        v
        for v in values
        if v.field_id.rsplit(":", 1)[-1] in figures
        and not v.abstained
        and v.value
        and v.value.strip()
        and v.citation is not None
    ]
    gray = np.asarray(Image.open(io.BytesIO(image)).convert("L"))
    ink = gray <= otsu(gray)
    height, width = ink.shape
    boxes = [v.citation.bbox for v in printed]
    body = (
        max(0, min(b.x0 for b in boxes) - 10),
        max(0, min(b.y0 for b in boxes) - 5),
        min(width, max(b.x1 for b in boxes) + 10),
        min(height, max(b.y1 for b in boxes) + 5),
    )
    found = grid(ink, body)
    inside = 0
    for box in boxes:  # in the found column under the box's centre, a band at its height?
        x, y = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
        for (a, b), bands in zip(found["columns"], found["rows_by_column"], strict=True):
            if a <= x < b:
                inside += any(c <= y < d for c, d in bands)
                break
    body = tuple(int(x) for x in body)
    rows_read = {v.field_id.split(":")[-2] for v in printed}
    columns_read = {v.field_id.rsplit(":", 1)[-1] for v in printed}
    across, down = rules(ink)
    return record | {
        "read": "ok",
        "layout_rows": len(doc_type.layout.row_keys),
        "layout_figure_columns": len(figures),
        "rows_read": len(rows_read),
        "columns_read": len(columns_read),
        "rows_found": found["rows"],
        "rows_found_range": found["rows_range"],
        "columns_found": len(found["columns"]),
        "boxes_on_a_row": round(inside / len(boxes), 3) if boxes else None,
        "rules": {"across": across, "down": down},
        "body": list(body),
    }


def report(pages: Sequence[Mapping]) -> str:
    lines = [
        "# Can the table grid be found from the page alone?",
        "",
        "Made by `python -m archivist.templates.grid_probe`: a feasibility probe in plain image "
        "code, no model call, on the development pages the drafts were drafted from; its "
        "thresholds were set by looking at these same pages, so it is not a held-out result. "
        "The body of the table is located from the first read's S0 boxes of its figure cells; "
        "inside it, with every unbroken stroke of a rule's length taken out, columns are the "
        "runs of pixel columns carrying more ink than the paper's floor, and rows are counted "
        "column by column as the bands of pixel rows carrying ink (found: the median over the "
        "columns, with its range). Ink: at or below the page's Otsu threshold. Ruled lines: "
        f"unbroken strokes at least {RULE_SHARE:.0%} of the page's width or height. Read: what "
        "the draft's first read found there (rows and figure columns with at least one figure). "
        "Boxes on a row: the share of the first read's figure boxes whose centre lies in a row "
        "band of the column found under it.",
        "",
        "| Family | Page | Layout rows x figure columns | Rows read / found | Figure columns "
        "read / found | Boxes on a row | Ruled lines (across / down) |",
        "|---|---|---|--:|--:|--:|--:|",
    ]
    for p in pages:
        if p["read"] != "ok":
            lines.append(f"| `{p['family']}` | {p['ref']} | {p['read']} | | | | |")
            continue
        share = "-" if p["boxes_on_a_row"] is None else f"{p['boxes_on_a_row']:.0%}"
        lines.append(
            f"| `{p['family']}` | {p['ref']} | {p['layout_rows']} x "
            f"{p['layout_figure_columns']} | {p['rows_read']} / {p['rows_found']} "
            f"({p['rows_found_range'][0]}-{p['rows_found_range'][1]}) | "
            f"{p['columns_read']} / {p['columns_found']} | {share} | "
            f"{p['rules']['across']} / {p['rules']['down']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dir", type=Path, default=TEMPLATES_DIR)
    args = parser.parse_args(argv)
    llm = load_roles(args.config)[extract.ROLE]
    llm.inner = _CacheOnly()  # the cache answers, or nothing does
    pages = []
    for doc_type in drafted_types(args.dir):
        for ref in doc_type.template.provenance.drafted_from:
            pages.append(probe_page(doc_type, ref, llm))
            print(json.dumps(pages[-1])[:300], flush=True)
    REPORT.write_text(report(pages), encoding="utf-8")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
