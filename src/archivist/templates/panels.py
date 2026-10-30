"""Where a table's panels lie on a page, and each panel read on its own (P21d).

A table printed in panels (template.PanelledType) is read panel by panel, each found first:

1. "sam": SAM 3.1, the segmenter role, prompted with PROMPT ("table"), through archivist.models, so
   the call is cached and budgeted (one image a prompt). A region is kept as a panel when it covers
   at least MIN_AREA of the page and is not mostly (CONTAINED) inside a larger kept region, which
   it would be a part of.
2. "layout", only when SAM keeps no region: plain code, no model. The page's ink (Otsu's threshold,
   as grid.py) is cut into bands at its blank pixel rows: GUTTER of the page's height or more of
   them in a row is a gutter, and a band shorter than MIN_BAND of the page is a heading, a caption
   or a footnote, not a panel. Each band is then cut in two side by side, in the middle part of its
   width (SPLIT), at a double vertical rule (two rules each inked over RULE_RUN of the band's
   height, at most DOUBLE pixels apart) or else at a blank gutter of GUTTER of the page's width.

Each panel records the method that found it; a panel plain code found is never called SAM's.

The panels found are put in reading order (rows of panels from the top, side by side from the
left) and given to the template's copies in its order: all of them when as many are found as the
template has copies, or, for a template of one panel printed several times, as many copies as
panels found. Otherwise no copy is placed. A placed copy is read on its crop (padded by PAD
pixels) and told it sees one panel; the box strategy runs inside the crop (grid.assign on the
crop's image and the OCR words inside it); its boxes are put back on the page. A copy not placed
is read on the whole page, told which panel to read. Either way its field ids lead each row with
the copy's key.

    python -m archivist.templates.panels --pages <id> ... [--out results/templates/panels_dev]

measures panel finding on development pages against the panels each prints (PRINTED, counted by
eye from the page images), both methods on every page, and puts beside it how many cells' two
reads agree before (BEFORE: the same pages read as one table) and after (each family's evidence).
"""

from __future__ import annotations

import argparse
import io
import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from archivist.doctypes.template import TEMPLATES_DIR, PanelledType, TemplateType, evidence_path
from archivist.models import Segmenter, SegmentRequest, load_roles
from archivist.pipeline import extract
from archivist.pipeline.extract import ExtractionFailed
from archivist.schema import BBox, Citation, ExtractedValue
from archivist.templates import grid, ocr
from archivist.templates.ink import otsu, runs
from archivist.templates.pages import resolve

ROLE = "segmenter"
PROMPT = "table"
METHODS = ("sam", "layout")
MIN_AREA = 0.03  # of the page
CONTAINED = 0.8  # of a region's area inside a larger one: a part of it
GUTTER = 0.006  # of the page's height (rows) or width (columns), blank
MIN_BAND = 0.08  # of the page's height
SPLIT = (0.3, 0.7)  # where in a band's width a side-by-side cut may fall
RULE_RUN, DOUBLE = 0.8, 14
PAD = 12  # pixels around a panel's crop
CONFIG = Path("config/templates_panels.toml")  # templates.toml's roles and the segmenter
OUT = Path("results/templates/panels_dev")

# How many panels each measured page prints, counted by eye from the page images (by Claude, when
# P21d was built; the counts are a person's to check): a panel is a block with its own column
# headings.
PRINTED = {
    "1939-02_p029": 2,
    "1939-03_p019": 2,
    "1939-07_p023": 2,
    "1939-07_p025": 2,
    "1939-12_p018": 2,
    "1939-12_p019": 2,
    "1905_p186": 1,
    "1905_p239": 1,
    "1905_p395": 3,
    "1905_p398": 3,
    "1905_p507": 3,
    "1925_p326": 2,
    "1925_p342": 1,
}

# The same pages read as one table, before P21d: the evidence each family's test left then.
BEFORE = {
    "collections_of_internal_revenue": Path(
        "results/templates/set_aside/collections_of_internal_revenue.evidence.json"
    ),
    "occ_abstract_by_states": OUT / "before" / "occ_abstract_by_states.evidence.json",
    "occ_aggregate_resources_liabilities": OUT
    / "before"
    / "occ_aggregate_resources_liabilities.evidence.json",
    "occ_banks_in_charge_of_receivers": evidence_path(
        TEMPLATES_DIR / "occ_banks_in_charge_of_receivers.yaml"
    ),
    "occ_earnings_and_dividends": evidence_path(TEMPLATES_DIR / "occ_earnings_and_dividends.yaml"),
}
AFTER = (
    "collections_by_period",
    "collections_by_source",
    "occ_abstract_by_states",
    "occ_aggregate_resources_liabilities",
)


@dataclass(frozen=True)
class Found:
    box: BBox
    method: str  # "sam" or "layout"
    score: float | None = None  # SAM's confidence; None for plain code

    def record(self) -> dict:
        b = self.box
        out: dict = {"method": self.method, "box": [b.x0, b.y0, b.x1, b.y1]}
        if self.score is not None and not math.isnan(self.score):
            out["score"] = round(self.score, 3)
        return out


def _area(box: BBox) -> int:
    return (box.x1 - box.x0) * (box.y1 - box.y0)


def _inside(inner: BBox, outer: BBox) -> float:
    """The share of inner's area that lies inside outer."""
    w = min(inner.x1, outer.x1) - max(inner.x0, outer.x0)
    h = min(inner.y1, outer.y1) - max(inner.y0, outer.y0)
    return 0.0 if w <= 0 or h <= 0 else w * h / _area(inner)


def by_sam(image: bytes, segmenter: Segmenter) -> list[Found]:
    """SAM's regions for PROMPT, kept as MIN_AREA and CONTAINED say."""
    width, height = Image.open(io.BytesIO(image)).size
    request = SegmentRequest(role=ROLE, image=image, prompts=(PROMPT,))
    regions = segmenter.segment(request).regions
    big = sorted(
        (r for r in regions if _area(r.bbox) >= MIN_AREA * width * height),
        key=lambda r: -_area(r.bbox),
    )
    kept: list = []
    for region in big:
        if all(_inside(region.bbox, k.bbox) < CONTAINED for k in kept):
            kept.append(region)
    return [Found(r.bbox, "sam", r.score) for r in kept]


def _rules(band: np.ndarray) -> list[float]:
    """The x of each vertical rule in a band of ink: pixel columns inked over RULE_RUN of it."""
    need = RULE_RUN * band.shape[0]
    longest = np.array([max((b - a for a, b in runs(col, 1, 1)), default=0) for col in band.T])
    return [(a + b - 1) / 2 for a, b in runs(longest >= need, 1, 1)]


def _split(band: np.ndarray, gutter: int) -> int | None:
    """Where a band is cut side by side: a double rule, else a blank gutter, nearest the middle
    of its inked width; None if neither."""
    inked = np.flatnonzero(band.any(axis=0))
    if len(inked) == 0:
        return None
    left, right = int(inked[0]), int(inked[-1]) + 1
    lo, hi = (left + f * (right - left) for f in SPLIT)
    middle = (left + right) / 2
    lines = _rules(band)
    pairs = zip(lines, lines[1:], strict=False)
    doubles = [(a + b) / 2 for a, b in pairs if b - a <= DOUBLE and lo <= a <= hi]
    if doubles:
        return round(min(doubles, key=lambda x: abs(x - middle)))
    blank = [(a + b) / 2 for a, b in runs(~band.any(axis=0), 0, gutter) if lo <= (a + b) / 2 <= hi]
    if blank:
        return round(min(blank, key=lambda x: abs(x - middle)))
    return None


def by_layout(image: bytes) -> list[Found]:
    """The panels plain code finds: bands between blank gutters, each cut side by side at a
    double rule or a blank gutter in its middle."""
    gray = np.asarray(Image.open(io.BytesIO(image)).convert("L"))
    height, width = gray.shape
    ink = gray <= otsu(gray)
    rows = runs(ink.any(axis=1), math.ceil(GUTTER * height), math.ceil(MIN_BAND * height))
    found = []
    for y0, y1 in rows:
        band = ink[y0:y1]
        inked = np.flatnonzero(band.any(axis=0))
        x0, x1 = int(inked[0]), int(inked[-1]) + 1
        cut = _split(band, math.ceil(GUTTER * width))
        spans = [(x0, cut), (cut, x1)] if cut is not None else [(x0, x1)]
        found += [Found(BBox(x0=a, y0=y0, x1=b, y1=y1), "layout") for a, b in spans if b > a]
    return found


def find(image: bytes, segmenter: Segmenter) -> list[Found]:
    """The page's panels: SAM's, else plain code's."""
    return by_sam(image, segmenter) or by_layout(image)


def reading_order(found: Sequence[Found]) -> list[Found]:
    """Rows of panels from the top (panels that share most of their height are one row), each
    row from the left."""
    rows: list[list[Found]] = []
    for f in sorted(found, key=lambda f: f.box.y0):
        for row in rows:
            g = row[0].box
            shared = min(f.box.y1, g.y1) - max(f.box.y0, g.y0)
            if shared > 0.5 * min(f.box.y1 - f.box.y0, g.y1 - g.y0):
                row.append(f)
                break
        else:
            rows.append([f])
    return [f for row in rows for f in sorted(row, key=lambda f: f.box.x0)]


def place(found: Sequence[Found], doc_type: PanelledType) -> dict[str, Found]:
    """Each copy's panel, in order; none placed unless the counts allow it (see the module)."""
    ordered, copies = reading_order(found), doc_type.copies
    single = len(doc_type.template.panels) == 1
    if len(ordered) == len(copies) or (single and 0 < len(ordered) <= len(copies)):
        return dict(zip(copies, ordered, strict=False))
    return {}


def _padded(box: BBox, width: int, height: int) -> BBox:
    return BBox(
        x0=max(0, box.x0 - PAD),
        y0=max(0, box.y0 - PAD),
        x1=min(width, box.x1 + PAD),
        y1=min(height, box.y1 + PAD),
    )


def _crop(image: bytes, box: BBox) -> bytes:
    out = io.BytesIO()
    Image.open(io.BytesIO(image)).crop((box.x0, box.y0, box.x1, box.y1)).save(out, format="PNG")
    return out.getvalue()


def _shift(box: BBox | None, dx: int, dy: int) -> BBox | None:
    if box is None:
        return None
    return BBox(x0=box.x0 + dx, y0=box.y0 + dy, x1=box.x1 + dx, y1=box.y1 + dy)


def _moved(value: ExtractedValue, copy: str, dx: int, dy: int) -> ExtractedValue:
    """A value read on a crop (or the page) as the copy's: its row led by the copy's key, its
    boxes on the page."""
    head, page, row, column = value.field_id.rsplit(":", 3)
    citation = value.citation
    if citation is not None:
        citation = Citation(
            page_id=citation.page_id,
            bbox=_shift(citation.bbox, dx, dy),
            raw_bbox=_shift(citation.raw_bbox, dx, dy),
        )
    return value.model_copy(
        update={"field_id": f"{head}:{page}:{copy}.{row}:{column}", "citation": citation}
    )


def _words_in(layer: Sequence[ocr.Word], box: BBox) -> list[ocr.Word]:
    """The OCR words whose centre lies in box, in the crop's pixels."""
    out = []
    for word in layer:
        x, y = (word.box.x0 + word.box.x1) / 2, (word.box.y0 + word.box.y1) / 2
        if box.x0 <= x < box.x1 and box.y0 <= y < box.y1:
            moved = _shift(word.box, -box.x0, -box.y0)
            out.append(ocr.Word(text=word.text, box=moved))
    return out


Guard = Callable[[bytes, TemplateType], grid.Check]


def read_panels(
    image: bytes,
    page_id: str,
    layer: Sequence[ocr.Word],
    doc_type: PanelledType,
    llm: object,
    segmenter: Segmenter,
    tokens: Callable[[TemplateType], int],
    citations: str = grid.STRATEGY,
    guard: Guard | None = None,
) -> tuple[list[ExtractedValue], dict]:
    """Every value of the page, each copy read on its panel's crop where one is placed, else on
    the page; and what was found and done, for the evidence. A copy whose read fails is recorded,
    and its cells are abstained."""
    width, height = Image.open(io.BytesIO(image)).size
    found = find(image, segmenter)
    placed = place(found, doc_type)
    record: dict = {"found": [f.record() for f in reading_order(found)], "copies": {}}
    values: list[ExtractedValue] = []
    for copy in doc_type.copies:
        region = placed.get(copy)
        if region is not None:
            box = _padded(region.box, width, height)
            here, plain = _crop(image, box), doc_type.cropped[copy]
            words, (dx, dy) = _words_in(layer, box), (box.x0, box.y0)
        else:
            here, plain, words, (dx, dy) = image, doc_type.whole[copy], list(layer), (0, 0)
        note: dict = {"read_on": "its panel" if region else "the page"}
        if region is not None:
            note["found_by"] = region.method
        try:
            strategy = "S0" if citations in (ocr.STRATEGY, grid.STRATEGY) else citations
            read = extract.read_page(here, page_id, llm, plain, strategy, tokens(plain))
        except ExtractionFailed as error:
            note["read"] = f"failed: {error}"[:500]
            values += [
                ExtractedValue(field_id=f, value=None, citation=None, abstained=True)
                for f in doc_type.parts[copy].field_ids(page_id)
            ]
            record["copies"][copy] = note
            continue
        if citations == ocr.STRATEGY:
            read, _ = ocr.anchor(read, words)
        elif citations == grid.STRATEGY:
            check = guard(here, plain) if guard is not None else None
            read, sources, info = grid.assign(read, plain, here, words, check)
            note["grid"] = info
            note["box_sources"] = dict(sorted(Counter(sources.values()).items()))
        values += [_moved(v, copy, dx, dy) for v in read]
        record["copies"][copy] = note
    return values, record


# --- The measurement -----------------------------------------------------------------------------


def _agreement(evidence: Mapping) -> dict[str, dict]:
    """Each page's needed cells and how many of them both reads agree on."""
    return {
        p["ref"]: {"needed": p.get("needed", 0), "agree": p.get("agree", 0)}
        for p in evidence["pages"]
        if p.get("read") == "ok"
    }


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def measure(refs: Sequence[str], segmenter: Segmenter) -> dict:
    """Both methods on every page, against PRINTED; agreement before and after from evidence."""
    before = {k: _load(p) for k, p in BEFORE.items()}
    after = {k: _load(evidence_path(TEMPLATES_DIR / f"{k}.yaml")) for k in AFTER}
    rows = []
    for ref in refs:
        image = resolve(ref).path.read_bytes()  # refuses a page that may not be sent
        sam, layout = by_sam(image, segmenter), by_layout(image)
        used = sam or layout
        row: dict = {
            "page": ref,
            "printed": PRINTED.get(ref),
            "sam": len(sam),
            "layout": len(layout),
            "used": used[0].method if used else None,
            "found": [f.record() for f in reading_order(used)],
        }
        for when, files in (("before", before), ("after", after)):
            row[when] = {
                family: counts
                for family, evidence in files.items()
                if evidence is not None and (counts := _agreement(evidence).get(ref))
            }
        rows.append(row)
    return {"prompt": PROMPT, "pages": rows}


def _share(counts: Mapping[str, dict]) -> str:
    if not counts:
        return "—"
    return "; ".join(
        f"{family}: {c['agree']} of {c['needed']}" for family, c in sorted(counts.items())
    )


def report(measured: Mapping) -> str:
    lines = [
        "# Panels found on development pages (P21d)",
        "",
        "Made by `python -m archivist.templates.panels`. SAM 3.1 is prompted with "
        f'"{measured["prompt"]}" through archivist.models; plain code (whitespace gutters and '
        "double rules) is the fallback, used only when SAM keeps no region, and both are run on "
        "every page here so they can be compared. Printed: the panels the page prints, counted by "
        "eye from the page image (a panel is a block with its own column headings). Agreement: of "
        "the cells some identity needs, how many both reads agree on, from each family's evidence: "
        "before, the page read as one table; after, read panel by panel.",
        "",
        "| Page | Printed | SAM | Plain code | Used | Agree before | Agree after |",
        "|---|--:|--:|--:|---|---|---|",
    ]
    for row in measured["pages"]:
        lines.append(
            f"| {row['page']} | {row['printed']} | {row['sam']} | {row['layout']} | "
            f"{row['used'] or 'none'} | {_share(row['before'])} | {_share(row['after'])} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--pages", nargs="+", default=list(PRINTED))
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    roles = load_roles(args.config)
    measured = measure(args.pages, roles[ROLE])
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "panels.json").write_text(
        json.dumps(measured, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out / "panels.md").write_text(report(measured), encoding="utf-8")
    for row in measured["pages"]:
        print(
            f"{row['page']}: printed {row['printed']}, SAM {row['sam']}, plain code "
            f"{row['layout']}, used {row['used']}"
        )


if __name__ == "__main__":
    main()
