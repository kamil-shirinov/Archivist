"""Which box strategy suits the template tables, and why cells disagree: development pages (P21c).

    python -m archivist.templates.compare_citations   # -> results/templates/citations_dev_v3.*
    python -m archivist.templates.compare_citations --report   # the report again, no call

The third measurement. The first (results/templates/citations_dev.md: S0 against S0+ink) and the
second (citations_dev_v2.md: S0 against S0+ocr, which became the template strategy) are kept as
written. This one sets S0+ocr against S0+grid (grid.py): each value's box from the archive's OCR
layer where its figure is found there, else from the table's grid found in the page by plain
code, else the model's own. The template re-reader is at reasoning "minimal". It runs on the
pages every template in templates/ was drafted from, drafts and approved ones alike (all
development pages; pages.py refuses any other before a call), with the arithmetic test's calls:

1. read and cite: extract.read_page with S0, the model's boxes; each strategy then puts its own
   boxes on the same read (no second extraction) and says where each box came from: "ocr",
   "grid" or "model".
2. a fixed sample of cells: SAMPLE of the page's cells that some identity needs, read as a figure
   the first time and boxed, drawn with random.Random(SEED) from their sorted field ids (all of
   them on a page with fewer); the same cells as before wherever the draft is the same.
3. the blind second read of each sampled cell from a crop of its box under each strategy
   (test.reread_cells, so a cell's call is the arithmetic test's and is cached for it).

Also reported: the share of cells whose box came from each source, overall, by page and by family,
and how the sampled cells of each source fare.

The measure is the share of sampled cells whose two reads agree, as the draft compares them
(test.agreed); a re-read that fails or finds the crop illegible does not agree. Rule, fixed before
running: the strategy with the higher share over every sampled cell becomes the template types'
(template.CITATIONS); on a tie, the simpler (the first in STRATEGIES). The ledger family keeps
S0+ink either way.

Why cells disagree. Every disagreement gets a cause by rule (cause()), in this order, except a
cell whose every re-read attempt reached the output limit, which is "re-read out of tokens"
(causes_of(), from the cached answers):
- "unreadable crop": the re-read found nothing legible, failed, or read only part of the figure
  (its digits are a part of the first read's, or the other way round: the crop cut it off);
- "formatting only": the two differ only in commas, spaces, dashes, parentheses or footnote marks;
- "neighbouring cell": the re-read is the first read of a cell next to it (up to two rows above
  or below, or the column either side): the crop shows that cell. Whether the box sits on the
  neighbour (a box offset) or the first read put the neighbour's figure here (a misplaced first
  read) the rule cannot tell; the context strip shows which;
- "unexplained": none of these.
DIAGNOSED disagreements per strategy, drawn with random.Random(SEED), are shown with the crop the
re-reader saw and a strip of the page around it (the box in red, the crop in blue); a reviewer's
judgement of each, where given in results/templates/citations_dev_v3_causes.json ({"<strategy>
<field id>": {"cause": ..., "note": ..., "judged_by": ...}}), is shown beside the rule's.

Long re-reads. A re-read may answer in at most reread.REREAD_TOKENS output tokens, reasoning
included. Each sampled cell's re-read request (and its retry, asked when the first answer did not
parse) is rebuilt exactly and looked up in the rereader's cache, never sent: the report counts
the answers that reached the limit or ran past LONG tokens, says how each such cell was counted
(agree, disagree, or no second read), and quotes a few. Writes
results/templates/citations_dev_v3.json (every sampled cell, both reads), the images in
results/templates/citations_dev_v3/, and results/templates/citations_dev_v3.md, whatever they
show.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import re
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from PIL import Image, ImageDraw

from archivist.doctypes.template import TEMPLATES_DIR, TemplateType, cell_id, drafted_types
from archivist.models import BudgetExceeded, LLMRequest, describe_config, load_roles
from archivist.models.cache import cache_key
from archivist.pipeline import extract, reread
from archivist.schema import BBox, ExtractedValue, PageExtraction
from archivist.templates import grid, ocr
from archivist.templates.draft import CONFIG
from archivist.templates.pages import resolve
from archivist.templates.test import agreed, needed, output_tokens, reread_cells

STRATEGIES = (ocr.STRATEGY, grid.STRATEGY)  # simplest first, so a tie keeps the simpler
SAMPLE = 40
DIAGNOSED = 20
LONG = 200  # output tokens: a value and its quotes take about ten
QUOTED = 3
SEED = 2110
OUT = Path("results/templates")
DATA, REPORT = OUT / "citations_dev_v3.json", OUT / "citations_dev_v3.md"
IMAGES, JUDGED = OUT / "citations_dev_v3", OUT / "citations_dev_v3_causes.json"
EARLIER = (OUT / "citations_dev.md", OUT / "citations_dev_v2.md")  # kept as written
OUT_OF_TOKENS = "re-read out of tokens"
CAUSES = (OUT_OF_TOKENS, "unreadable crop", "formatting only", "neighbouring cell", "unexplained")
JUDGEMENTS = (
    "box offset",
    "first read misplaced",
    "first read wrong",
    "unreadable crop",
    "formatting only",
    "re-read wrong",
    "unclear",
)
_FOOTNOTE = re.compile(r"\s*(\d+/|[*†‡]|\b[a-z]/)\s*$")
CONTEXT_ROWS = 3  # box heights above and below the box in the context strip
CONTEXT_WIDTH = 1200  # pixels the strip is scaled to


def sample(doc_type: TemplateType, values: Sequence[ExtractedValue], page_id: str) -> list[str]:
    """The page's sampled cells: needed (so a figure's), read, boxed; SAMPLE of them at most."""
    eligible = sample_all(doc_type, values, page_id)
    if len(eligible) <= SAMPLE:
        return eligible
    return sorted(random.Random(SEED).sample(eligible, SAMPLE))


def sample_all(
    doc_type: TemplateType, values: Sequence[ExtractedValue], page_id: str
) -> list[str]:
    """Every cell the sample is drawn from: needed (so a figure's), read, boxed."""
    page = PageExtraction(page_id=page_id, doc_type=doc_type.name, values=list(values))
    wanted = needed(doc_type, page)
    return sorted(
        v.field_id
        for v in values
        if v.field_id in wanted
        and v.citation is not None
        and not v.abstained
        and v.value
        and v.value.strip()
    )


def neighbours(doc_type: TemplateType, field_id: str) -> list[str]:
    """The cells next to one: up to two rows above and below in its column, the columns beside."""
    *_, page_id, row, column = field_id.split(":")
    rows, columns = doc_type.layout.row_keys, [c.key for c in doc_type.layout.columns]
    r, c = rows.index(row), columns.index(column)
    near = [(rows[r + d], column) for d in (-1, 1, -2, 2) if 0 <= r + d < len(rows)]
    near += [(row, columns[c + d]) for d in (-1, 1) if 0 <= c + d < len(columns)]
    return [cell_id(doc_type.name, page_id, a, b) for a, b in near]


def _plain(text: str) -> str:
    """A figure without its formatting: no footnote mark, comma, space or parenthesis, and any
    dash a hyphen."""
    t = _FOOTNOTE.sub("", text.strip())
    t = re.sub(r"[–—−]", "-", t)
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    return re.sub(r"[,\s()]", "", t)


def _digits(text: str) -> str:
    return re.sub(r"\D", "", _FOOTNOTE.sub("", text))


def cause(first: str, second: str | None, near: Mapping[str, str | None], canon) -> str:
    """Why a cell's two reads disagree, by rule (see the module's docstring)."""
    if second is None or not second.strip():
        return "unreadable crop"
    a, b = _digits(first), _digits(second)
    if a and b and a != b and (a in b or b in a):
        return "unreadable crop"
    if _plain(first) == _plain(second):
        return "formatting only"
    if any(text is not None and canon(f, text) == canon(f, second) for f, text in near.items()):
        return "neighbouring cell"
    return "unexplained"


def _box(bbox: BBox) -> list[int]:
    return [bbox.x0, bbox.y0, bbox.x1, bbox.y1]


def boxes(
    raw: Sequence[ExtractedValue], doc_type: TemplateType, image: bytes, ref: str
) -> dict[str, tuple[list[ExtractedValue], dict[str, str]]]:
    """Each strategy's boxes on the same read, and where each box came from."""
    layer = ocr.words(ref)
    anchored_values, anchored = ocr.anchor(raw, layer)
    by_ocr = {v.field_id: "ocr" if v.field_id in anchored else "model" for v in raw}
    return {
        ocr.STRATEGY: (anchored_values, by_ocr),
        grid.STRATEGY: grid.assign(raw, doc_type, image, layer),
    }


def measure_page(
    doc_type: TemplateType, ref: str, roles: Mapping[str, object], workers: int
) -> dict:
    """One page's sampled cells under each strategy: both reads, the box, the neighbours' first
    reads where the two disagree."""
    page = resolve(ref)  # refuses a page that may not be sent, before any call
    image = page.path.read_bytes()
    llm, rereader = roles[extract.ROLE], roles[reread.ROLE]
    record: dict = {"family": doc_type.name, "ref": ref, "page_id": page.page_id}
    try:
        raw = extract.read_page(image, page.page_id, llm, doc_type, "S0", output_tokens(doc_type))
    except BudgetExceeded:
        raise
    except Exception as error:  # a read that fails or times out is recorded, not fatal
        return {**record, "read": f"failed: {type(error).__name__}: {error}"[:500]}
    boxed = boxes(raw, doc_type, image, ref)
    first = {v.field_id: None if v.abstained else v.value for v in raw}
    ids = sample(doc_type, raw, page.page_id)
    figures = sample_all(doc_type, raw, page.page_id)
    record |= {
        "read": "ok",
        "sampled": len(ids),
        "figures": len(figures),
        "height_px": Image.open(io.BytesIO(image)).height,
    }
    for strategy in STRATEGIES:
        values, sources = boxed[strategy]
        by_id = {v.field_id: v for v in values}
        second = reread_cells(image, values, set(ids), doc_type, rereader, workers)
        extraction = PageExtraction(page_id=page.page_id, doc_type=doc_type.name, values=values)
        both = agreed(doc_type, extraction, second)
        cells = []
        for field_id in ids:
            reading, agree = second[field_id], both.get(field_id) is not None
            cell = {
                "field_id": field_id,
                "first": first[field_id],
                "reread": reading.text,
                "why": reading.why,
                "box": _box(by_id[field_id].citation.bbox),
                "region": _box(reread.region(by_id[field_id].citation)),
                "source": sources[field_id],
                "agree": agree,
            }
            if not agree:
                near = {f: first.get(f) for f in neighbours(doc_type, field_id)}
                cell["neighbours"] = near
                cell["cause"] = cause(first[field_id], reading.text, near, doc_type.canonical)
            cells.append(cell)
        record[strategy] = {
            "sources": {k: sum(sources[f] == k for f in figures) for k in grid.SOURCES},
            "agree": sum(c["agree"] for c in cells),
            "no_second_read": sum(c["reread"] is None for c in cells),
            "cells": cells,
        }
    return record


def decide(pages: Sequence[Mapping]) -> tuple[str, dict[str, float | None]]:
    """The rule: the higher share of agreeing sampled cells; on a tie, the simpler."""
    sampled = sum(p.get("sampled", 0) for p in pages)
    shares: dict[str, float | None] = {
        s: (sum(p[s]["agree"] for p in pages if s in p) / sampled if sampled else None)
        for s in STRATEGIES
    }
    if sampled == 0:
        return STRATEGIES[0], shares
    return max(STRATEGIES, key=lambda s: shares[s]), shares  # max keeps the first on a tie


def disagreements(pages: Sequence[Mapping], strategy: str) -> list[tuple[Mapping, Mapping]]:
    """(page, cell) for every sampled cell whose reads disagree under strategy."""
    return [(p, c) for p in pages if strategy in p for c in p[strategy]["cells"] if not c["agree"]]


def diagnosed(pages: Sequence[Mapping], strategy: str) -> list[tuple[Mapping, Mapping]]:
    found = disagreements(pages, strategy)
    if len(found) <= DIAGNOSED:
        return found
    chosen = sorted(random.Random(SEED).sample(range(len(found)), DIAGNOSED))
    return [found[i] for i in chosen]


def _name(strategy: str, n: int) -> str:
    return f"{strategy.replace('+', '_')}_{n:02d}"


def draw(page: Mapping, cell: Mapping, strategy: str, n: int, images: Path = IMAGES) -> None:
    """The crop the re-reader saw, and a strip of the page around it, as PNGs in images/."""
    picture = Image.open(resolve(page["ref"]).path).convert("RGB")
    box = BBox(**dict(zip(("x0", "y0", "x1", "y1"), cell["region"], strict=True)))
    images.mkdir(parents=True, exist_ok=True)
    (images / f"{_name(strategy, n)}_crop.png").write_bytes(reread.crop(picture, box))
    seen = reread.crop_box(box, *picture.size)
    height = max(1, cell["box"][3] - cell["box"][1])
    top = max(0, cell["box"][1] - CONTEXT_ROWS * height)
    bottom = min(picture.height, cell["box"][3] + CONTEXT_ROWS * height)
    canvas = ImageDraw.Draw(picture)
    canvas.rectangle([seen.x0, seen.y0, seen.x1, seen.y1], outline=(0, 90, 255), width=3)
    canvas.rectangle(cell["box"], outline=(230, 0, 0), width=3)
    strip = picture.crop((0, top, picture.width, bottom))
    scale = CONTEXT_WIDTH / strip.width
    strip = strip.resize((CONTEXT_WIDTH, max(1, round(strip.height * scale))))
    strip.save(images / f"{_name(strategy, n)}_context.png")


def answers(pages: Sequence[Mapping], rereader: object, directory: Path = TEMPLATES_DIR) -> list:
    """Every cached answer to a sampled cell's re-read: (strategy, page, cell, attempt, output
    tokens, text). Looked up by the request's cache key; nothing is sent."""
    types = {t.name: t for t in drafted_types(directory)}
    out = []
    for page in pages:
        if page["read"] != "ok":
            continue
        doc_type = types[page["family"]]
        picture = Image.open(resolve(page["ref"]).path)
        picture.load()
        for strategy in STRATEGIES:
            for cell in page[strategy]["cells"]:
                box = BBox(**dict(zip(("x0", "y0", "x1", "y1"), cell["region"], strict=True)))
                prompt = doc_type.reread_prompt(cell["field_id"])
                for attempt, text in (("first", prompt), ("retry", prompt + reread.RETRY_NOTE)):
                    request = LLMRequest(
                        role=reread.ROLE,
                        prompt=text,
                        images=(reread.crop(picture, box),),
                        json_schema=reread.SCHEMA,
                        max_output_tokens=reread.REREAD_TOKENS,
                    )
                    key = cache_key(rereader.name, rereader.model_id, request, rereader.settings)
                    path = rereader.cache_dir / key[:2] / f"{key}.json"
                    if path.is_file():
                        data = json.loads(path.read_text())
                        tokens = data["usage"]["output_tokens"]
                        out.append((strategy, page, cell, attempt, tokens, data["text"]))
    return out


def _counted(cell: Mapping) -> str:
    if cell["agree"]:
        return "agree"
    return "disagree" if cell["reread"] is not None else "no second read"


def ran_out(found: Sequence) -> set[tuple[str, str]]:
    """(strategy, field id) of each cell with no second read whose every attempt reached the
    output limit: the re-reader spent it all reasoning and wrote nothing to parse."""
    attempts: dict[tuple[str, str], list] = {}
    for strategy, _, cell, _, tokens, _ in found:
        attempts.setdefault((strategy, cell["field_id"]), []).append((tokens, cell))
    return {
        key
        for key, tried in attempts.items()
        if tried[0][1]["reread"] is None
        and all(tokens >= reread.REREAD_TOKENS for tokens, _ in tried)
    }


def causes_of(pages: Sequence[Mapping], found: Sequence) -> dict[tuple[str, str], str]:
    """Each disagreement's cause: the rule's, except a re-read that ran out of tokens."""
    out_of_tokens = ran_out(found)
    return {
        (s, c["field_id"]): OUT_OF_TOKENS if (s, c["field_id"]) in out_of_tokens else c["cause"]
        for s in STRATEGIES
        for _, c in disagreements(pages, s)
    }


def _quote(text: str) -> str:
    text = " ".join(text.split()).replace("`", "'")
    return f"`{text}`" if text else "*(empty)*"


def long_answers(found: Sequence) -> list[str]:
    """The report's section on re-reads that reached the limit or ran long."""
    limit = reread.REREAD_TOKENS
    lines = [
        "",
        "## Long re-reads",
        "",
        "Every cached answer to a sampled cell's re-read (first attempt, and the retry asked when "
        f"it did not parse). Output tokens include the reasoning; the limit is {limit}. An answer "
        f"that reaches it is cut off; an empty or cut answer does not parse, so the re-read is "
        "asked once more, and when that fails too the cell has no second read (counted as not "
        f'agreeing; its cause is "{OUT_OF_TOKENS}"). Answer text: the JSON that came back, '
        f"whose length shows whether the answer itself ran long (over {LONG} tokens is about "
        f"{4 * LONG} characters).",
        "",
        f"| Strategy | Answers | Median tokens | Over {LONG} tokens | At the limit (empty) | "
        f"Answer text over {4 * LONG} chars | Cells with an answer at the limit, counted as |",
        "|---|--:|--:|--:|--:|--:|---|",
    ]
    for s in STRATEGIES:
        mine = [a for a in found if a[0] == s]
        at = [a for a in mine if a[4] >= limit]
        cells = {a[2]["field_id"]: a[2] for a in at}
        counted = Counter(_counted(c) for c in cells.values())
        median = statistics.median(a[4] for a in mine) if mine else 0
        lines.append(
            f"| {s} | {len(mine)} | {median:.0f} | {sum(a[4] > LONG for a in mine)} | "
            f"{len(at)} ({sum(not a[5].strip() for a in at)}) | "
            f"{sum(len(a[5]) > 4 * LONG for a in mine)} | "
            + (", ".join(f"{k} {n}" for k, n in counted.most_common()) or "-")
            + " |"
        )
    at = [a for a in found if a[4] >= limit]
    shown = [a for a in at if a[5].strip()][:2] + [a for a in at if not a[5].strip()][:2]
    longest = sorted(found, key=lambda a: -len(a[5]))[:QUOTED]
    lines += ["", "What some of them say:", ""]
    for strategy, page, cell, attempt, tokens, text in [*shown, *longest]:
        *_, row, column = cell["field_id"].split(":")
        lines.append(
            f"- {strategy}, {page['ref']} row {row}, {column}, {attempt} attempt, {tokens} tokens: "
            f"{_quote(text)} (first read {_cell(cell['first'])}; counted as {_counted(cell)})"
        )
    return lines


def _sources(counts: Mapping[str, int]) -> str:
    total = sum(counts.values())
    return " / ".join(f"{counts.get(k, 0)} ({_pct(counts.get(k, 0), total)})" for k in grid.SOURCES)


def sourcing(pages: Sequence[Mapping]) -> list[str]:
    """Where each strategy's boxes came from, and how the sampled cells of each source fare."""
    ok = [p for p in pages if p["read"] == "ok"]
    lines = [
        "## Where the boxes came from",
        "",
        f"Of the {sum(p['figures'] for p in ok)} figure cells the sample is drawn from, how many "
        "boxes each strategy took from each source (ocr / grid / model):",
        "",
        "| Strategy | ocr / grid / model |",
        "|---|---|",
    ]
    for s in STRATEGIES:
        total = Counter()
        for p in ok:
            total.update(p[s]["sources"])
        lines.append(f"| {s} | {_sources(total)} |")
    lines += [
        "",
        "Agreement among the sampled cells, by where each strategy's box came from:",
        "",
        "| Strategy | Source | Sampled cells | Agree |",
        "|---|---|--:|--:|",
    ]
    for s in STRATEGIES:
        for source in grid.SOURCES:
            cells = [c for p in ok for c in p[s]["cells"] if c["source"] == source]
            if cells:
                n, a = len(cells), sum(c["agree"] for c in cells)
                lines.append(f"| {s} | {source} | {n} | {a} ({_pct(a, n)}) |")
    return lines


def _pct(n: int, d: int) -> str:
    return f"{n / d:.0%}" if d else "-"


def _cell(text: str | None) -> str:
    return "*(none)*" if text is None else f"`{text}`" if text.strip() else "*(blank)*"


def report(
    pages: Sequence[Mapping],
    config: Mapping[str, object],
    judged: Mapping[str, Mapping],
    found: Sequence = (),
) -> str:
    chosen, shares = decide(pages)
    sampled = sum(p.get("sampled", 0) for p in pages)
    lines = [
        "# Box strategy for template tables, measured on development pages",
        "",
        "Made by `python -m archivist.templates.compare_citations`. A measurement, reported "
        "whatever it shows. The pages are those each draft in `templates/` was drafted from, all "
        "on the development side of `data/real/split.json`. On each page, up to "
        f"{SAMPLE} cells that the draft's identities need and that were read as a figure the "
        f"first time are drawn with `random.Random({SEED})`, and each is re-read blind from a "
        "crop of its box under both strategies: **S0+ocr**, the box of the same figure in the "
        "archive's own OCR text layer where it is found with confidence (`ocr.py`), else the "
        "model's; and **S0+grid**, the OCR layer's box, else the cell of the table's grid found "
        "in the page by plain code (columns from the ink, rows from deskewed bands, each read row "
        "fixed by an anchored figure or its label in the OCR layer, the rows between fixed rows "
        "mapped by order only where they are as many as the bands; `grid.py`), else the "
        "model's. The re-reader runs at reasoning \"minimal\" (templates only). The measure is "
        "the share of sampled cells whose two reads agree, as the draft compares them; a failed "
        "or illegible re-read does not agree. Every sampled cell, with both reads, is in "
        f"`{DATA.as_posix()}`. The earlier measurements are kept as written: "
        + ", ".join(f"`{e.as_posix()}`" for e in EARLIER)
        + "; the sample is the same wherever the draft is.",
        "",
        "Rule, fixed before running: the strategy with the higher share over all sampled cells "
        "becomes the template types' strategy; on a tie, the simpler (S0+ocr). The ledger card and "
        "payment memo keep S0+ink, so no committed run changes.",
        "",
        f"Config: `{json.dumps(dict(config))}`",
        "",
        "## Result",
        "",
        "| Strategy | Cells agreeing | Share |",
        "|---|--:|--:|",
        *(
            f"| {s} | {sum(p[s]['agree'] for p in pages if s in p)} / {sampled} | "
            f"{'-' if shares[s] is None else f'{shares[s]:.1%}'} |"
            for s in STRATEGIES
        ),
        "",
        f"**Chosen for templates by the rule: {chosen}.**",
        "",
        *sourcing(pages),
        "",
        "## Why cells disagree, by rule",
        "",
        "Every disagreement, by the rule's cause (the module docstring defines them; "
        '"neighbouring cell" does not tell a box offset from a misplaced first read), except '
        f'that a cell whose every re-read attempt ran out of tokens is "{OUT_OF_TOKENS}", not '
        "an unreadable crop (see Long re-reads).",
        "",
        "| Strategy | Disagree | " + " | ".join(CAUSES) + " |",
        "|---|--:|" + "--:|" * len(CAUSES),
    ]
    causes = causes_of(pages, found)
    for s in STRATEGIES:
        mine = disagreements(pages, s)
        counts = Counter(causes[(s, c["field_id"])] for _, c in mine)
        lines.append(
            f"| {s} | {len(mine)} | "
            + " | ".join(f"{counts[k]} ({_pct(counts[k], len(mine))})" for k in CAUSES)
            + " |"
        )
    lines += long_answers(found)
    lines += [
        "",
        "## Is the table's grid findable from the page alone?",
        "",
        "Measured separately, in plain image code on the same pages: "
        "`results/templates/grid_dev.md` (`python -m archivist.templates.grid_probe`).",
    ]
    lines += [
        "",
        "## By page",
        "",
        "Boxes: where S0+grid's boxes for the page's figure cells came from, ocr / grid / model.",
        "",
        "| Family | Page | Sampled | S0+ocr agree | S0+grid agree | S0+grid boxes (ocr / grid / "
        "model) | No second read (S0+ocr / S0+grid) |",
        "|---|---|--:|--:|--:|---|--:|",
    ]
    o, g = STRATEGIES
    for p in pages:
        if p["read"] != "ok":
            lines.append(f"| `{p['family']}` | {p['ref']} | {p['read'][:120]} | | | | |")
            continue
        n = p["sampled"]
        lines.append(
            f"| `{p['family']}` | {p['ref']} | {n} | {p[o]['agree']} ({_pct(p[o]['agree'], n)}) | "
            f"{p[g]['agree']} ({_pct(p[g]['agree'], n)}) | {_sources(p[g]['sources'])} | "
            f"{p[o]['no_second_read']} / {p[g]['no_second_read']} |"
        )
    families = sorted({p["family"] for p in pages})
    lines += [
        "",
        "## By family",
        "",
        "| Family | Sampled | S0+ocr | S0+grid | S0+ocr boxes (ocr / grid / model) | S0+grid "
        "boxes (ocr / grid / model) |",
        "|---|--:|--:|--:|---|---|",
    ]
    for family in families:
        mine = [p for p in pages if p["family"] == family and p["read"] == "ok"]
        n = sum(p["sampled"] for p in mine)
        a0, a1 = (sum(p[s]["agree"] for p in mine) for s in STRATEGIES)
        by_source = []
        for s in STRATEGIES:
            total = Counter()
            for p in mine:
                total.update(p[s]["sources"])
            by_source.append(_sources(total))
        lines.append(
            f"| `{family}` | {n} | {a0} ({_pct(a0, n)}) | {a1} ({_pct(a1, n)}) | "
            f"{by_source[0]} | {by_source[1]} |"
        )
    for s in STRATEGIES:
        chosen_cells = diagnosed(pages, s)
        tally = Counter(
            judged.get(f"{s} {c['field_id']}", {}).get("cause", "not judged")
            for _, c in chosen_cells
        )
        lines += [
            "",
            f"## {len(chosen_cells)} disagreements under {s}, looked at",
            "",
            f"Drawn with `random.Random({SEED})` from the {len(disagreements(pages, s))} "
            "disagreements. Crop: what the re-reader saw. Context: the page around it, the box in "
            "red and the crop in blue. Judged: a reviewer's reading of the context strip and of "
            "the first read's row labels, where given; "
            + (f"by {by}, " if (by := _judged_by(judged)) else "")
            + f"in `{JUDGED.as_posix()}`: "
            + ", ".join(f"{k} {n}" for k, n in tally.most_common()),
            "",
            "| # | Page, cell | Crop | First read | Re-read | By rule | Judged | Context |",
            "|--:|---|---|---|---|---|---|---|",
        ]
        for n, (page, cell) in enumerate(chosen_cells, 1):
            name = _name(s, n)
            *_, row, column = cell["field_id"].split(":")
            verdict = judged.get(f"{s} {cell['field_id']}", {})
            judgement = verdict.get("cause", "-")
            if verdict.get("note"):
                judgement += f": {verdict['note']}"
            lines.append(
                f"| {n} | {page['ref']} `{page['family']}` row {row}, {column} | "
                f"![]({IMAGES.name}/{name}_crop.png) | {_cell(cell['first'])} | "
                f"{_cell(cell['reread'])} | {causes[(s, cell['field_id'])]} | {judgement} | "
                f"[strip]({IMAGES.name}/{name}_context.png) |"
            )
    lines.append("")
    return "\n".join(lines)


def _judged_by(judged: Mapping[str, Mapping]) -> str:
    return "; ".join(sorted({v["judged_by"] for v in judged.values() if v.get("judged_by")}))


def write_report(config: Mapping[str, object], rereader: object) -> str:
    pages = json.loads(DATA.read_text(encoding="utf-8"))["pages"]
    judged = json.loads(JUDGED.read_text(encoding="utf-8")) if JUDGED.is_file() else {}
    unknown = {v.get("cause") for v in judged.values()} - set(JUDGEMENTS)
    if unknown:
        raise ValueError(f"{JUDGED}: causes {sorted(unknown)} are not among {JUDGEMENTS}")
    REPORT.write_text(report(pages, config, judged, answers(pages, rereader)), encoding="utf-8")
    return decide(pages)[0]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dir", type=Path, default=TEMPLATES_DIR)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--report", action="store_true", help="from the saved data; no call")
    args = parser.parse_args(argv)
    config = describe_config(args.config)
    roles = load_roles(args.config)
    if not args.report:
        guard = roles[extract.ROLE].inner.guard
        before = guard.spent()
        pages = []
        for doc_type in drafted_types(args.dir):
            for ref in doc_type.template.provenance.drafted_from:
                pages.append(measure_page(doc_type, ref, roles, args.workers))
                summary = {k: v for k, v in pages[-1].items() if k not in STRATEGIES}
                agree = {s: pages[-1][s]["agree"] for s in STRATEGIES if s in pages[-1]}
                print(json.dumps(summary | agree)[:400], flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps({"pages": pages}, indent=1) + "\n", encoding="utf-8")
        for s in STRATEGIES:
            for n, (page, cell) in enumerate(diagnosed(pages, s), 1):
                draw(page, cell, s, n)
        print(f"${guard.spent() - before:.4f} spent")
    chosen = write_report(config, roles[reread.ROLE])
    print(f"wrote {REPORT}: {chosen} by the rule")


if __name__ == "__main__":
    main()
