"""Page X-rays (P24): how a page was read, drawn on the page. No model is called.

    python -m archivist.templates.xray [--out results/templates/xray] [--workers 8]

One development page of each approved template family, and one synthetic ledger card of the committed
test run test-archivist-A, each drawn with:

- every cell's box, outlined by where the box came from: the archive PDF's OCR layer (S0+ocr), the
  table's grid found in the page (S0+grid) or the model's own box, the fallback; on the ledger card,
  the model's box corrected from the page's ink (S0+ink) or kept;
- the grid's columns and row bands, found again by plain code from the page (the same code the
  S0+grid strategy runs); for a family tested under S0+ocr, before the grid existed, they are drawn
  for context and its boxes did not come from them;
- every SAM occluder recorded for the page, as the segmenter's boxes (its backend keeps a box and a
  score, not a mask): for a card, those in the run's verdicts; for a template page, any in the cache;
- each cell's outcome: whether its two reads agree, and whether the rule that covers it held, failed
  or was not evaluated, by the arithmetic test's own judgement (test.judge); on the card, the run's
  recorded re-read status and checks.

Only cached reads are used. Both spend caps are set to zero before any model role is built, so a
read that is not in the cache stops that family, which is skipped and said so; a call is never made.
A family is replayed on the strategy and config its evidence file records, through the arithmetic
test's own steps (test.read_pages), and the page is drawn only if the replay's boxes are the ones
the cache gives again. The first page its evidence lists is the one drawn.

The card is chosen by a rule fixed here, not by looking: the first ledger card, in page order, that
has an occluded field, a field with a failed check and a field whose re-read balances, so that every
mark appears; failing that, the first with an occluder; failing that, the first card.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from archivist.doctypes.template import (
    NUMERIC,
    TEMPLATES_DIR,
    TemplateType,
    evidence_path,
    load_templates,
)
from archivist.models import BudgetExceeded, describe_config, load_roles
from archivist.models.budget import BACKEND_CAPS
from archivist.pipeline import extract, occlusion, reread
from archivist.schema import BBox, ExtractedValue, PageExtraction, VerdictRecord
from archivist.templates import grid, ocr, test
from archivist.templates.draft import CONFIG
from archivist.templates.pages import resolve

OUT = Path("results/templates/xray")
RUNS_DIR = Path("results/runs")
CARD_RUN = "test-archivist-A"
FONT = Path(__file__).resolve().parents[3] / "assets" / "fonts" / "courierprime" / "CourierPrime-Regular.ttf"
SEGMENTER_CONFIG = Path("config/models.toml")

AGREE, DISAGREE, NOT_REREAD = "agree", "disagree", "not re-read"
PASSED, FAILED, NOT_EVALUATED = "passed", "failed", "not evaluated"
CHECK_KINDS = ("arithmetic", "words_figures", "crossdoc")  # a check that failed, as opposed to a re-read or occlusion note

# Okabe-Ito colours, which stay apart for the common kinds of colour blindness.
BLUE, PURPLE, BLACK, SKY = (0, 114, 178), (204, 121, 167), (0, 0, 0), (86, 180, 233)
GREEN, VERMILION, YELLOW, ORANGE, GREY = (0, 158, 115), (213, 94, 0), (240, 228, 66), (230, 159, 0), (110, 110, 110)
SOURCES = {  # key -> (outline colour, dashed, the legend's words)
    "ocr": (BLUE, False, "OCR anchor"),
    "grid": (PURPLE, False, "grid"),
    "model": (BLACK, True, "model fallback"),
    "ink": (SKY, False, "model box corrected by ink"),
    "kept": (BLACK, True, "model box kept"),
}
FILL_ALPHA, COLUMN_ALPHA, BAND_ALPHA, OUTLINE = 85, 45, 150, 3


class Skipped(Exception):
    """A family whose reads can't be replayed from the cache, with why."""


@dataclass(frozen=True)
class Cell:
    field_id: str
    box: BBox
    text: str
    source: str  # a key of SOURCES
    reads: str  # AGREE, DISAGREE or NOT_REREAD
    rule: str  # PASSED, FAILED or NOT_EVALUATED


@dataclass(frozen=True)
class Occluder:
    label: str
    box: BBox
    detail: str  # the share of a field it covers, or the segmenter's score


@dataclass
class XRay:
    stem: str  # the file name without .png
    title: str
    notes: list[str]  # what the legend says about this page
    image: Image.Image
    cells: list[Cell]
    blanks: int  # cells with a box that read as blank, not drawn
    grid: grid.Grid | None = None
    occluders: list[Occluder] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)  # for the README

    def count(self, name: str) -> dict[str, int]:
        return dict(Counter(getattr(c, name) for c in self.cells))


# --- outcomes ---------------------------------------------------------------------------------


def cell_states(
    doc_type: TemplateType, extraction: PageExtraction, second: Mapping[str, test.Reading]
) -> dict[str, tuple[str, str]]:
    """For each cell of the page: (whether its two reads agree, how the rules covering it came out).

    Reads agree or disagree where the cell was read twice, as the arithmetic test compares them;
    a cell never read twice (no rule needs it, a blank, an illegible re-read) is "not re-read". A
    rule's verdict is test.judge's on every place it applies: a cell is "failed" if any place that
    holds it failed, "passed" if one held and none failed, else "not evaluated" (its reads disagree,
    a neighbour was not read twice, all blank, or no rule covers it).
    """
    first = {v.field_id: None if v.abstained else v.value for v in extraction.values}
    both = test.agreed(doc_type, extraction, second)
    verdicts: dict[str, set[str]] = defaultdict(set)
    for instance in doc_type.instances([extraction]):
        verdict, _ = test.judge(doc_type, instance, first, second, both)
        for field_id, *_ in instance.fields:
            verdicts[field_id].add(verdict)
    out = {}
    for value in extraction.values:
        reading = second.get(value.field_id)
        if reading is None or reading.text is None:
            reads = NOT_REREAD
        else:
            reads = AGREE if both[value.field_id] is not None else DISAGREE
        seen = verdicts.get(value.field_id, set())
        rule = FAILED if "failed" in seen else PASSED if "held" in seen else NOT_EVALUATED
        out[value.field_id] = (reads, rule)
    return out


def page_grid(
    values: Sequence[ExtractedValue], doc_type: TemplateType, image: bytes, layer: Sequence[ocr.Word]
) -> grid.Grid | None:
    """The table's grid as S0+grid finds it on the page: the first steps of grid.assign, which
    returns what it found only as counts."""
    anchored_values, anchored = ocr.anchor(values, layer)
    figure_columns = [c.key for c in doc_type.layout.columns if c.kind in NUMERIC]
    figures: dict[str, list[ExtractedValue]] = {c: [] for c in figure_columns}
    printed = 0
    for row in doc_type.layout.row_keys:
        shown = False
        for v in anchored_values:
            r, column = grid._row_col(v.field_id)
            if r == row and column in figures and not v.abstained and v.value and v.value.strip():
                figures[column].append(v)
                shown = True
        printed += shown
    return grid.find_grid(image, figures, anchored, printed, True)


def box_sources(
    values: Sequence[ExtractedValue],
    doc_type: TemplateType,
    image: bytes,
    layer: Sequence[ocr.Word],
    citations: str,
    check: grid.Check | None,
) -> tuple[list[ExtractedValue], dict[str, str]]:
    """The values with the boxes the strategy gives them and each one's source, as the arithmetic
    test made them."""
    if citations == grid.STRATEGY:
        boxed, sources, _ = grid.assign(values, doc_type, image, layer, check)
        return boxed, sources
    if citations == ocr.STRATEGY:
        boxed, anchored = ocr.anchor(values, layer)
        return boxed, {v.field_id: "ocr" if v.field_id in anchored else "model" for v in values}
    return list(values), {v.field_id: "model" for v in values}


# --- replaying a template family --------------------------------------------------------------


def no_spend() -> None:
    """Set every backend's spend cap to zero: a read that is not in the cache raises BudgetExceeded
    and a call is never made."""
    for variable, _ in BACKEND_CAPS.values():
        os.environ[variable] = "0"


def recorded_occluders(image: bytes, segmenter: object | None) -> list[Occluder]:
    """The SAM occluders in the cache for this page, with the caps at zero; none if there are none."""
    if segmenter is None:
        return []
    try:
        regions = occlusion.detect(image, segmenter)  # type: ignore[arg-type]
    except BudgetExceeded:
        return []
    return [Occluder(r.label, r.bbox, f"score {r.score:.2f}") for r in regions]


def replay_family(
    doc_type: TemplateType,
    roles: Mapping[str, object],
    segmenter: object | None,
    workers: int = 8,
) -> XRay:
    """The X-ray of the first page of the family's committed evidence, from the cache alone; raises
    Skipped with the reason if the page can't be replayed."""
    family = doc_type.name
    committed = json.loads(evidence_path(TEMPLATES_DIR / f"{family}.yaml").read_text(encoding="utf-8"))
    if committed["config"] != describe_config(CONFIG):
        raise Skipped(f"tested with another config than {CONFIG}")
    recorded = committed["pages"][0]
    citations = committed["citations"]
    try:
        page = resolve(recorded["ref"])
    except ValueError as error:
        raise Skipped(str(error)) from error
    image = page.path.read_bytes()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            extracted, seconds, records = test.read_pages(doc_type, [page], roles, workers, citations)
            llm, rereader = roles[extract.ROLE], roles[reread.ROLE]
            values = extract.read_page(
                image, page.page_id, llm, doc_type, "S0", test.output_tokens(doc_type)
            )
            layer = ocr.words(page.ref)
            check = test.blind_check(image, page.page_id, doc_type, rereader, workers)
            boxed, sources = box_sources(values, doc_type, image, layer, citations, check)
            regions = recorded_occluders(image, segmenter)
    except BudgetExceeded as error:
        raise Skipped(
            "a read it needs is not in the cache under the current code: the lookup missed with both "
            "spend caps at zero, so nothing was called"
        ) from error
    if not extracted or records[0].get("read") != "ok":
        raise Skipped(f"the page's read failed: {records[0].get('read')}")
    extraction = extracted[0]
    if boxed != extraction.values:
        raise Skipped("the replay's boxes differ from the test's own: not the same read")
    states = cell_states(doc_type, extraction, seconds[page.page_id])
    cells, blanks = [], 0
    for v in extraction.values:
        if v.citation is None:
            continue
        if v.abstained or not (v.value or "").strip():
            blanks += 1
            continue
        reads, rule = states[v.field_id]
        cells.append(Cell(v.field_id, v.citation.bbox, v.value or "", sources[v.field_id], reads, rule))
    found = page_grid(values, doc_type, image, layer)
    used = citations == grid.STRATEGY
    notes = [
        f"{family}: approved template, page {page.ref}, boxes by {citations}",
        "the grid was used for the boxes"
        if used
        else "the grid is found by plain code for context; this family was tested under "
        f"{citations}, so its boxes did not come from it",
    ]
    return XRay(
        stem=page.ref,
        title=f"{family} - {page.ref}",
        notes=notes,
        image=Image.open(io.BytesIO(image)).convert("RGB"),
        cells=cells,
        blanks=blanks,
        grid=found,
        occluders=regions,
        facts={
            "family": family,
            "page": page.ref,
            "citations": citations,
            "grid_used": used,
            "record_diff": record_diff(recorded, json.loads(json.dumps(records[0]))),
            "grid_columns": len(found.columns) if found else 0,
            "grid_bands": len(found.bands) if found else 0,
            "occluders_in_cache": len(regions),
        },
    )


def record_diff(committed: Mapping, replayed: Mapping) -> dict[str, list]:
    """The counts of a page's record that the replay gives otherwise than the committed evidence:
    {key: [committed, replayed]}; empty when the replay is the committed record."""
    return {
        k: [committed.get(k), replayed.get(k)]
        for k in sorted(set(committed) | set(replayed))
        if committed.get(k) != replayed.get(k)
    }


# --- the ledger card --------------------------------------------------------------------------


def failed_check(record: VerdictRecord) -> bool:
    return any(flag.check in CHECK_KINDS for flag in record.flags)


def choose_card(records: Sequence[VerdictRecord]) -> str | None:
    """The page of the card to draw, by the rule in the module's docstring."""
    pages: dict[str, list[VerdictRecord]] = defaultdict(list)
    for r in records:
        if r.doc_type == "ledger_card":
            pages[r.page_id].append(r)
    ordered = sorted(pages.items())
    for tests in (all, lambda h: h[0], lambda h: True):
        for page_id, rs in ordered:
            if tests(marks(rs)):
                return page_id
    return None


def marks(records: Sequence[VerdictRecord]) -> tuple[bool, bool, bool]:
    """Whether a card has an occluded field, a field with a failed check, and one whose re-read balances."""
    return (
        any(r.evidence.occluded_by for r in records),
        any(failed_check(r) for r in records),
        any(r.evidence.reread_balances for r in records),
    )


def card_cells(records: Sequence[VerdictRecord]) -> tuple[list[Cell], int, list[Occluder], list[BBox]]:
    """A card's cells from its run's verdicts: the corrected box (and the model's own, where it
    moved), the re-read status, the checks, the occluders."""
    cells, blanks, raws = [], 0, []
    occluders: dict[tuple[str, tuple[int, int, int, int]], Occluder] = {}
    for r in records:
        for o in r.evidence.occluded_by:
            key = (o.label, (o.bbox.x0, o.bbox.y0, o.bbox.x1, o.bbox.y1))
            occluders.setdefault(key, Occluder(o.label, o.bbox, f"covers {o.cover:.0%} of a field"))
        citation = r.evidence.citation
        if citation is None:
            continue
        if not (r.value or "").strip():
            blanks += 1
            continue
        moved = citation.raw_bbox is not None and citation.raw_bbox != citation.bbox
        if moved:
            raws.append(citation.raw_bbox)
        reads = {"agrees": AGREE, "disagrees": DISAGREE}.get(r.evidence.reread_status, NOT_REREAD)
        rule = FAILED if failed_check(r) else PASSED if r.evidence.reread_balances else NOT_EVALUATED
        cells.append(
            Cell(r.field_id, citation.bbox, r.value or "", "ink" if moved else "kept", reads, rule)
        )
    return cells, blanks, list(occluders.values()), raws


def card_xray(run_dir: Path = RUNS_DIR / CARD_RUN) -> XRay:
    records = [
        VerdictRecord.model_validate_json(line)
        for line in (run_dir / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    page_id = choose_card(records)
    if page_id is None:
        raise Skipped(f"{run_dir.name} has no ledger card")
    mine = [r for r in records if r.page_id == page_id]
    cells, blanks, occluders, raws = card_cells(mine)
    image = Image.open(Path(run["images"]) / f"{page_id}.jpg").convert("RGB")
    return XRay(
        stem=f"{run['run_id']}_{page_id}",
        title=f"{page_id} - synthetic ledger card, run {run['run_id']}",
        notes=[
            f"run {run['run_id']} (committed), citations {run['citations']}; boxes, re-read status, "
            "checks and occluders are the run's own record",
            f"{len(raws)} boxes moved by the ink fit (the model's own box is the thin grey one)",
        ],
        image=image,
        cells=cells,
        blanks=blanks,
        occluders=occluders,
        facts={
            "page": page_id,
            "run": run["run_id"],
            "citations": run["citations"],
            "moved": len(raws),
            "marks": list(marks(mine)),
            "raw_boxes": [b.model_dump() for b in raws],
        },
    )


# --- drawing ----------------------------------------------------------------------------------


def _dashed(draw: ImageDraw.ImageDraw, box: BBox, colour: tuple[int, ...], width: int, dash: int = 8) -> None:
    for (xa, ya), (xb, yb) in (
        ((box.x0, box.y0), (box.x1, box.y0)),
        ((box.x1, box.y0), (box.x1, box.y1)),
        ((box.x1, box.y1), (box.x0, box.y1)),
        ((box.x0, box.y1), (box.x0, box.y0)),
    ):
        length = max(abs(xb - xa), abs(yb - ya))
        for start in range(0, length, 2 * dash):
            end = min(start + dash, length)
            f0, f1 = start / length, end / length
            draw.line(
                [(xa + (xb - xa) * f0, ya + (yb - ya) * f0), (xa + (xb - xa) * f1, ya + (yb - ya) * f1)],
                fill=colour,
                width=width,
            )


def _marker(draw: ImageDraw.ImageDraw, cell: Cell) -> None:
    """A mark inside the box's left end: tick (rule passed), cross (failed), not-equal (reads
    disagree), a ring (reads agree, rule not evaluated); nothing when not re-read."""
    box = cell.box
    size = max(6, min(16, box.y1 - box.y0 - 4, box.x1 - box.x0 - 4))
    x, y = box.x0 + 3, box.y0 + (box.y1 - box.y0 - size) // 2
    colour = (*BLACK, 255)
    if cell.reads == DISAGREE:
        draw.line([(x, y + size * 0.35), (x + size, y + size * 0.35)], fill=colour, width=2)
        draw.line([(x, y + size * 0.7), (x + size, y + size * 0.7)], fill=colour, width=2)
        draw.line([(x + size * 0.8, y), (x + size * 0.2, y + size)], fill=colour, width=2)
    elif cell.rule == FAILED:
        draw.line([(x, y), (x + size, y + size)], fill=colour, width=3)
        draw.line([(x, y + size), (x + size, y)], fill=colour, width=3)
    elif cell.rule == PASSED:
        draw.line([(x, y + size * 0.55), (x + size * 0.4, y + size), (x + size, y)], fill=colour, width=3)
    elif cell.reads == AGREE:
        draw.ellipse([x, y, x + size, y + size], outline=colour, width=2)


def _fill(cell: Cell) -> tuple[int, int, int, int] | None:
    if cell.reads == DISAGREE:
        return (*YELLOW, FILL_ALPHA)
    if cell.rule == FAILED:
        return (*VERMILION, FILL_ALPHA)
    if cell.rule == PASSED:
        return (*GREEN, FILL_ALPHA)
    return None


def _draw_grid(draw: ImageDraw.ImageDraw, g: grid.Grid, width: int) -> None:
    """Columns as translucent stripes and each row band's edges, on the skewed page."""
    if not g.bands or not g.columns:
        return
    top, bottom = min(a for a, _ in g.bands), max(b for _, b in g.bands)
    left, right = min(a for a, _ in g.columns.values()), max(b for _, b in g.columns.values())

    def page_y(x: float, deskewed: float) -> float:
        return deskewed + g.shear * (x - g.centre)

    for a, b in g.columns.values():
        draw.polygon(
            [(a, page_y(a, top)), (b, page_y(b, top)), (b, page_y(b, bottom)), (a, page_y(a, bottom))],
            fill=(*SKY, COLUMN_ALPHA),
            outline=(*SKY, 200),
        )
    edges = sorted({y for band in g.bands for y in band})
    for y in edges:
        draw.line([(left, page_y(left, y)), (right, page_y(right, y))], fill=(*GREY, BAND_ALPHA), width=1)


def _hatch(layer: Image.Image, box: BBox) -> None:
    """Diagonal lines inside the box, nowhere else."""
    w, h = box.x1 - box.x0, box.y1 - box.y0
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pen = ImageDraw.Draw(tile)
    for k in range(-h, w, 24):
        pen.line([(k, h), (k + h, 0)], fill=(*ORANGE, 90), width=2)
    layer.alpha_composite(tile, (box.x0, box.y0))


def _wrap(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, width: int) -> list[str]:
    """The text broken at spaces into lines no wider than width."""
    lines, line = [], ""
    for word in text.split(" "):
        trial = f"{line} {word}".strip()
        if line and ImageDraw.Draw(Image.new("L", (1, 1))).textlength(trial, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return [*lines, line]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT), size)
    except OSError:
        return ImageFont.load_default()


def _legend_rows(x: XRay) -> list[list[tuple[str, str]]]:
    """The legend: rows of (swatch, label), the swatches drawn by _swatch."""
    present = [k for k in SOURCES if any(c.source == k for c in x.cells)]
    rows = [[(f"line:{k}", SOURCES[k][2]) for k in present]]
    rows.append(
        [
            ("pass", "rule passed"),
            ("fail", "rule failed"),
            ("disagree", "two reads disagree"),
            ("ring", "reads agree, rule not evaluated"),
            ("none", "not re-read"),
        ]
    )
    overlays = []
    if x.grid is not None:
        overlays += [("column", "grid column"), ("band", "grid row band edge")]
    overlays.append(("occluder", f"SAM occluder ({len(x.occluders)} recorded)"))
    rows.append(overlays)
    return rows


def _swatch(draw: ImageDraw.ImageDraw, kind: str, x: int, y: int, h: int) -> None:
    w = 3 * h // 2
    box = [x, y, x + w, y + h]
    if kind.startswith("line:"):
        colour, dashed, _ = SOURCES[kind[5:]]
        if dashed:
            _dashed(draw, BBox(x0=x, y0=y, x1=x + w, y1=y + h), (*colour, 255), OUTLINE)
        else:
            draw.rectangle(box, outline=(*colour, 255), width=OUTLINE)
    elif kind in ("pass", "fail", "disagree", "ring", "none"):
        fills = {"pass": GREEN, "fail": VERMILION, "disagree": YELLOW}
        draw.rectangle(box, outline=(*GREY, 255), fill=(*fills[kind], 200) if kind in fills else None)
        cell = Cell(
            "", BBox(x0=x, y0=y, x1=x + w, y1=y + h), "", "kept",
            DISAGREE if kind == "disagree" else AGREE if kind != "none" else NOT_REREAD,
            {"pass": PASSED, "fail": FAILED}.get(kind, NOT_EVALUATED),
        )
        _marker(draw, cell)
    elif kind == "column":
        draw.rectangle(box, fill=(*SKY, 120), outline=(*SKY, 255))
    elif kind == "band":
        draw.line([(x, y + h // 2), (x + w, y + h // 2)], fill=(*GREY, 255), width=2)
    elif kind == "occluder":
        draw.rectangle(box, outline=(*ORANGE, 255), width=OUTLINE)
        draw.line([(x, y + h), (x + w, y)], fill=(*ORANGE, 255), width=2)


def draw(x: XRay) -> Image.Image:
    """The page with the X-ray over it, under a header holding the legend."""
    page = x.image.convert("RGBA")
    layer = Image.new("RGBA", page.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    if x.grid is not None:
        _draw_grid(pen, x.grid, page.width)
    for box in x.facts.get("raw_boxes", []):  # the model's own box where the ink fit moved it
        b = BBox(**box)
        pen.rectangle([b.x0, b.y0, b.x1, b.y1], outline=(*GREY, 200), width=1)
    for cell in x.cells:
        b = cell.box
        if (fill := _fill(cell)) is not None:
            pen.rectangle([b.x0, b.y0, b.x1, b.y1], fill=fill)
        colour, dashed, _ = SOURCES[cell.source]
        if dashed:
            _dashed(pen, b, (*colour, 255), OUTLINE)
        else:
            pen.rectangle([b.x0, b.y0, b.x1, b.y1], outline=(*colour, 255), width=OUTLINE)
        _marker(pen, cell)
    label = _font(18)
    for o in x.occluders:
        b = o.box
        pen.rectangle([b.x0, b.y0, b.x1, b.y1], outline=(*ORANGE, 255), width=OUTLINE + 1)
        _hatch(layer, b)
        pen.text((b.x0 + 4, b.y0 + 2), f"{o.label} ({o.detail})", fill=(*ORANGE, 255), font=label)
    body = Image.alpha_composite(page, layer)

    size = 20
    font, small = _font(size), _font(size - 2)
    width = max(page.width, 1100)
    row_h, margin = size + 14, 14
    lines = [(x.title, font)] + [
        (part, small) for text in (*x.notes, _summary(x)) for part in _wrap(text, small, width - 2 * margin)
    ]
    rows = _legend_rows(x)
    header_h = margin + (len(lines) + len(rows)) * row_h + margin
    canvas = Image.new("RGBA", (width, header_h + page.height), (255, 255, 255, 255))
    pen = ImageDraw.Draw(canvas)
    y = margin
    for line, face in lines:
        pen.text((margin, y), line, fill=(0, 0, 0, 255), font=face)
        y += row_h
    for row in rows:
        cursor = margin
        for kind, text in row:
            _swatch(pen, kind, cursor, y, size)
            cursor += 3 * size // 2 + 8
            pen.text((cursor, y), text, fill=(0, 0, 0, 255), font=small)
            cursor += int(pen.textlength(text, font=small)) + 28
        y += row_h
    canvas.paste(body, ((width - page.width) // 2, header_h))
    return canvas.convert("RGB")


def _summary(x: XRay) -> str:
    sources = x.count("source")
    reads, rules = x.count("reads"), x.count("rule")
    return (
        f"{len(x.cells)} cells drawn ({x.blanks} blank not drawn). "
        f"boxes: {', '.join(f'{n} {k}' for k, n in sorted(sources.items()))}. "
        f"reads: {reads.get(AGREE, 0)} agree, {reads.get(DISAGREE, 0)} disagree, {reads.get(NOT_REREAD, 0)} not re-read. "
        f"rules: {rules.get(PASSED, 0)} passed, {rules.get(FAILED, 0)} failed, {rules.get(NOT_EVALUATED, 0)} not evaluated."
    )


# --- the README and the command ---------------------------------------------------------------


def readme(xrays: Sequence[XRay], skipped: Mapping[str, str]) -> str:
    out = [
        "# Page X-rays (P24)",
        "",
        "Each image is one page drawn with how it was read. Made by `python -m archivist.templates.xray` "
        "from the cache and the committed run alone: both spend caps are set to zero first, so a read "
        "that is not cached stops that family, and no model is called. Each image has its legend at the top.",
        "",
        "What the marks mean:",
        "",
        "- **Box outline, by where the box came from.** Blue: OCR anchor, the figure's own box in the "
        "archive PDF's OCR layer. Purple: grid, the cell of the table's grid found in the page by plain code. "
        "Black dashed: the model's own box, the fallback. On the ledger card, sky blue is the model's box corrected "
        "from the page's ink (the model's own, before the fit, is the thin grey box) and black dashed is a box the fit left as it was.",
        "- **Grid.** Sky-blue stripes are the table's columns, grey lines the edges of its row bands, "
        "skewed with the page. Found again by the same plain code the S0+grid strategy runs. A family "
        "tested under S0+ocr, before the grid existed, has its grid drawn for context only.",
        "- **Occluders.** Orange boxes, hatched, are SAM boxes recorded for the page. The segmenter's "
        "backend keeps a box, a label and a score, not a mask, so a box is what is drawn.",
        "- **Outcome of a cell, from the arithmetic test's own judgement.** Fill: green, a rule that "
        "covers the cell held; vermillion, a rule failed; yellow, the cell's two reads disagree. Mark: "
        "tick (passed), cross (failed), not-equal sign (reads disagree), ring (reads agree, no rule "
        "evaluated). A cell never read twice has neither. Blank cells are not drawn.",
        "",
        "## Images",
        "",
    ]
    for x in xrays:
        f = x.facts
        out += [f"### `{x.stem}.png` - {x.title}", ""]
        if "family" in f:
            out += [
                f"A page of the approved template `{f['family']}`, page {f['page']} of the Treasury Bulletin, "
                f"development side of the split; the first page its committed evidence lists. Boxes by "
                f"{f['citations']}. {'The grid was used for the boxes.' if f['grid_used'] else 'The grid is for context only.'} "
                f"The grid found {f['grid_columns']} columns and {f['grid_bands']} row bands. "
                + (
                    f"{f['occluders_in_cache']} SAM occluders are in the cache for it."
                    if f["occluders_in_cache"]
                    else "No SAM occluder is recorded for it: the template test never runs the segmenter, and the cache holds none for this page."
                )
                + diff_sentence(f["record_diff"]),
                "",
            ]
        else:
            out += [
                f"Synthetic ledger card {f['page']} of the committed run {f['run']} (citations {f['citations']}), "
                f"chosen by the fixed rule in the module: the first card, in page order, with an occluded "
                f"field, a failed check and a re-read that balances"
                + ("." if all(f["marks"]) else " (no card has all three, so this is the fallback).")
                + " Boxes, re-read status, checks and occluders are the "
                f"run's own record (`results/runs/{f['run']}/verdicts.jsonl`); {f['moved']} boxes were moved by the ink fit. "
                "A rule \"passed\" here means the field's re-read balances (an equation holds for it); "
                "\"failed\" means a check flagged the extracted value (arithmetic, words against figures, or "
                "against the memo); anything else is not evaluated. The image is read from the split's "
                "images; nothing is run on it.",
                "",
            ]
        out += [x_summary_line(x), ""]
    if skipped:
        out += ["## Skipped", ""]
        out += [f"- `{family}`: {why}" for family, why in skipped.items()]
        out += [""]
    return "\n".join(out)


def diff_sentence(diff: Mapping[str, Sequence]) -> str:
    """What the README says about the replay against the committed page record."""
    if not diff:
        return " The replay's page record is the committed one, count for count."
    changed = ", ".join(f"{k} {old} then, {new} now" for k, (old, new) in diff.items())
    sentence = f" The replay's page record differs from the committed one in {changed}"
    if set(diff) == {"agree"} and diff["agree"][1] > diff["agree"][0]:
        sentence += (
            "; P26 reads a space after a thousands comma (\"29, 139\") as part of the figure, so more "
            "reads agree now (results/templates/recount.md)"
        )
    return sentence + ". The cells drawn are what the cache gives now."


def x_summary_line(x: XRay) -> str:
    return "Cells: " + _summary(x)


def approved_types() -> list[TemplateType]:
    return load_templates(TEMPLATES_DIR)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    no_spend()  # before any role is built
    roles = load_roles(CONFIG)
    try:
        segmenter = load_roles(SEGMENTER_CONFIG).get(occlusion.ROLE)
    except Exception:  # a config or key that can't be loaded means no cached SAM answer to look for
        segmenter = None
    xrays: list[XRay] = []
    skipped: dict[str, str] = {}
    for doc_type in approved_types():
        print(f"{doc_type.name}: replaying from the cache", flush=True)
        try:
            xrays.append(replay_family(doc_type, roles, segmenter, args.workers))
        except Skipped as error:
            skipped[doc_type.name] = str(error)
            print(f"  skipped: {error}", flush=True)
    try:
        xrays.append(card_xray())
    except Skipped as error:
        skipped[CARD_RUN] = str(error)
    args.out.mkdir(parents=True, exist_ok=True)
    for x in xrays:
        draw(x).save(args.out / f"{x.stem}.png", optimize=True)
        print(f"-> {args.out / f'{x.stem}.png'}", flush=True)
    (args.out / "README.md").write_text(readme(xrays, skipped), encoding="utf-8")
    print(f"-> {args.out / 'README.md'}")


if __name__ == "__main__":
    main()
