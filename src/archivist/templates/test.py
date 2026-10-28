"""The arithmetic test of a drafted template: does each identity hold on the pages? (P21b)

    python -m archivist.templates.test --family <name> [--pages <id> ...] [--workers 8]

Reads <dir>/<family>.yaml (default templates/) and its sample pages, by default the pages it was
drafted from (pages.py decides which may be sent), through the pipeline's own steps and the roles
of --config (default config/templates.toml), every call cached and budgeted:

1. classify: is the page the draft's kind, by the draft's description alone, or unsupported?
   Recorded as evidence; the page is read as the draft either way.
2. read and cite: the draft's extraction of the whole table, its boxes corrected from the image
   (extract.read_page with the template types' own citation strategy, template.CITATIONS, unless
   --citations picks another; the evidence records which). S0+ocr reads with S0 and anchors each
   value's box to the page's OCR text layer where it can (ocr.py; the evidence records how many).
   A big table gets a larger output allowance: OUTPUT_PER_CELL tokens per cell beyond the
   pipeline's own EXTRACT_TOKENS.
3. blind second read: every cell some identity needs, re-read from a crop of its corrected box
   with the draft's re-read prompt, which never shows the first reading (reread.py).

Then every identity is evaluated wherever it applies (TemplateType.instances, rows used as the
first read has them), using only cells whose two reads agree as the draft compares them. An
instance whose cells all agree and are figures holds or fails within the rounding tolerance;
any other is not evaluated, with the reason (the reads disagree; a cell was not read twice; a
cell is blank where a blank is unknown, or not a figure). For each identity the evidence says
how often it held, and:

- "rejected": it was evaluated and never held. It is dropped at approval without being asked.
- "sometimes fails": it held and failed. Kept for the person to judge, with every failing
  instance's cells and both reads.
- "holds": it never failed.
- "untested": it was never evaluated. Kept for the person, who sees there is no evidence.

Writes <dir>/<family>.evidence.json, with the draft's sha256 so the approval can tell the evidence
is the draft's. An approved template is never retested in place.
"""

from __future__ import annotations

import argparse
import io
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image

from archivist.doctypes import UNSUPPORTED
from archivist.doctypes.template import (
    TEMPLATES_DIR,
    Instance,
    TemplateType,
    evidence_path,
    figure,
    file_sha256,
    read_template,
    written,
)
from archivist.models import BudgetExceeded, describe_config, load_roles
from archivist.pipeline import extract, reread
from archivist.pipeline.extract import (
    CITATION_STRATEGIES,
    EXTRACT_TOKENS,
    ExtractionFailed,
)
from archivist.schema import ExtractedValue, PageExtraction
from archivist.templates import ocr
from archivist.templates.draft import CONFIG
from archivist.templates.pages import Page, resolve

OUTPUT_PER_CELL = 40  # tokens: a cell's key, value and box, with room to spare
DISAGREE, ONCE, BLANK = (
    "the two reads of a cell disagree",
    "a cell was not read twice",
    "a cell is blank or not a figure",
)
OUTCOMES = ("rejected", "sometimes fails", "holds", "untested")


@dataclass(frozen=True)
class Reading:
    """A cell's second read: its text, or None with why there is none."""

    text: str | None
    why: str | None = None


def output_tokens(doc_type: TemplateType) -> int:
    cells = len(doc_type.layout.row_keys) * len(doc_type.layout.columns)
    return max(EXTRACT_TOKENS, EXTRACT_TOKENS // 4 + OUTPUT_PER_CELL * cells)


def needed(doc_type: TemplateType, page: PageExtraction) -> set[str]:
    """The cells some identity needs on the page, as the checks would apply it."""
    return {field_id for i in doc_type.instances([page]) for field_id, *_ in i.fields}


def reread_cells(
    image: bytes,
    values: Sequence[ExtractedValue],
    wanted: set[str],
    doc_type: TemplateType,
    llm: object,
    workers: int,
) -> dict[str, Reading]:
    """The blind second read of each wanted cell that has a box and was read the first time."""
    picture = Image.open(io.BytesIO(image))
    picture.load()

    def one(value: ExtractedValue) -> Reading:
        if value.abstained or value.value is None:
            return Reading(None, "not read the first time")
        if value.citation is None:
            return Reading(None, "no box to re-read")
        box = reread.region(value.citation)
        try:
            text, _ = reread.reread(picture, box, doc_type.reread_prompt(value.field_id), llm)
        except BudgetExceeded:
            raise
        except Exception as error:  # one cell failing must not stop the others
            return Reading(None, f"the re-read failed: {type(error).__name__}: {error}"[:300])
        return Reading(text) if text is not None else Reading(None, "illegible to the re-read")

    chosen = [v for v in values if v.field_id in wanted]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip((v.field_id for v in chosen), pool.map(one, chosen), strict=True))


def agreed(
    doc_type: TemplateType, page: PageExtraction, second: Mapping[str, Reading]
) -> dict[str, str | None]:
    """Each cell's text where both reads agree, else None."""
    out: dict[str, str | None] = {}
    canonical = doc_type.canonical
    for value in page.values:
        reading = second.get(value.field_id)
        first = None if value.abstained else value.value
        same = (
            first is not None
            and reading is not None
            and reading.text is not None
            and canonical(value.field_id, first) == canonical(value.field_id, reading.text)
        )
        out[value.field_id] = first if same else None
    return out


def _cell(field_id: str) -> tuple[str, str]:
    *_, row, column = field_id.split(":")
    return row, column


def judge(
    doc_type: TemplateType,
    instance: Instance,
    first: Mapping[str, str | None],
    second: Mapping[str, Reading],
    both: Mapping[str, str | None],
) -> tuple[str, dict | None]:
    """("held" | "failed" | a reason it wasn't evaluated, the failure's record if it failed)."""
    ids = [field_id for field_id, *_ in instance.fields]

    def read_twice(field_id: str) -> bool:
        reading = second.get(field_id)
        return first.get(field_id) is not None and reading is not None and reading.text is not None

    if any(read_twice(f) and both.get(f) is None for f in ids):
        return DISAGREE, None
    if any(both.get(f) is None for f in ids):
        return ONCE, None
    result = doc_type.evaluate(instance, both)
    if result is None:
        return BLANK, None
    left, right, tolerance = result
    if abs(left - right) <= tolerance:
        return "held", None
    cells = []
    for n, (field_id, coef, _, kind) in enumerate(instance.fields):
        row, column = _cell(field_id)
        left_side = n < instance.left
        cells.append(
            {
                "field_id": field_id,
                "row": row,
                "column": column,
                "side": "left" if left_side else "right",
                "sign": "+" if (coef > 0) == left_side else "-",  # within its own side
                "read": first.get(field_id),
                "reread": second[field_id].text,
                "value": str(figure(both[field_id], kind, field_id in instance.zero)),
            }
        )
    page_id = ids[0].split(":")[1]
    return "failed", {
        "page": page_id,
        "where": instance.where,
        "left": str(left),
        "right": str(right),
        "difference": str(abs(left - right)),
        "tolerance": str(tolerance),
        "cells": cells,
    }


def outcome(held: int, failed: int) -> str:
    if held + failed == 0:
        return "untested"
    if held == 0:
        return "rejected"
    return "holds" if failed == 0 else "sometimes fails"


def tally(
    doc_type: TemplateType,
    pages: Sequence[PageExtraction],
    seconds: Mapping[str, Mapping[str, Reading]],
) -> list[dict]:
    """Every identity's bookkeeping over the pages: where it applies, how it fared, its failures."""
    counts: dict[str, Counter] = defaultdict(Counter)
    failures: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        second = seconds[page.page_id]
        first = {v.field_id: None if v.abstained else v.value for v in page.values}
        both = agreed(doc_type, page, second)
        for instance in doc_type.instances([page]):
            name = instance.rule.split(".", 1)[1]
            verdict, failure = judge(doc_type, instance, first, second, both)
            counts[name]["applies"] += 1
            counts[name][verdict] += 1
            if failure is not None:
                failures[name].append(failure)
    out = []
    for identity in doc_type.template.identities:
        c = counts[identity.id]
        held, failed = c["held"], c["failed"]
        out.append(
            {
                "id": identity.id,
                "description": identity.description,
                "for_each": identity.for_each,
                "over": identity.over,
                "equation": written(identity),
                "applies": c["applies"],
                "evaluated": held + failed,
                "held": held,
                "failed": failed,
                "hold_rate": round(held / (held + failed), 4) if held + failed else None,
                "not_evaluated": {r: c[r] for r in (DISAGREE, ONCE, BLANK) if c[r]},
                "outcome": outcome(held, failed),
                "failures": failures[identity.id],
            }
        )
    return out


def read_pages(
    doc_type: TemplateType,
    pages: Sequence[Page],
    roles: Mapping[str, object],
    workers: int,
    citations: str | None = None,
) -> tuple[list[PageExtraction], dict[str, dict[str, Reading]], list[dict]]:
    """Classify, read and cite (citations, else the type's own strategy), and re-read each page;
    a page that can't be read is recorded."""
    extracted, seconds, records = [], {}, []
    llm, rereader = roles[extract.ROLE], roles[reread.ROLE]
    for page in pages:
        image = page.path.read_bytes()
        record: dict = {"ref": page.ref, "page_id": page.page_id}
        record["classified_as"] = extract.classify(image, llm, {doc_type.name: doc_type})
        try:
            strategy = "S0" if citations == ocr.STRATEGY else citations
            values = extract.read_page(
                image, page.page_id, llm, doc_type, strategy, output_tokens(doc_type)
            )
        except ExtractionFailed as error:
            records.append({**record, "read": f"failed: {error}"[:1000]})
            print(f"{page.ref}: the read failed", flush=True)
            continue
        anchored = None
        if citations == ocr.STRATEGY:
            values, anchored = ocr.anchor(values, ocr.words(page.ref))
        extraction = PageExtraction(page_id=page.page_id, doc_type=doc_type.name, values=values)
        wanted = needed(doc_type, extraction)
        second = reread_cells(image, values, wanted, doc_type, rereader, workers)
        both = agreed(doc_type, extraction, second)
        if anchored is not None:  # of the cells the identities need, those boxed from the OCR layer
            record["anchored"] = len(anchored & wanted)
        record |= {
            "read": "ok",
            "needed": len(wanted),
            "cells": len(values),
            "read_first": sum(not v.abstained and v.value is not None for v in values),
            "read_twice": sum(r.text is not None for r in second.values()),
            "agree": sum(both.get(f) is not None for f in second),
            "no_second_read": dict(
                sorted(Counter(r.why for r in second.values() if r.why).items())
            ),
        }
        records.append(record)
        extracted.append(extraction)
        seconds[page.page_id] = second
        print(
            f"{page.ref}: classified {record['classified_as']}, {record['cells']} cells, "
            f"{record['read_twice']} of {len(second)} needed read twice, {record['agree']} agree",
            flush=True,
        )
    return extracted, seconds, records


def run_test(
    family: str,
    roles: Mapping[str, object],
    *,
    directory: Path = TEMPLATES_DIR,
    refs: Sequence[str] | None = None,
    config: Mapping[str, object] | None = None,
    workers: int = 8,
    citations: str | None = None,
    today: date | None = None,
) -> Path:
    """Test the draft and write its evidence file; returns the evidence file's path."""
    path = directory / f"{family}.yaml"
    template = read_template(path)
    if template.provenance.approved:
        raise ValueError(f"{path} is approved: its evidence is what it was approved on")
    doc_type = TemplateType(template, sha256=file_sha256(path))
    refs = list(refs or template.provenance.drafted_from)
    if not refs:
        raise ValueError(f"{path} names no pages it was drafted from: give --pages")
    pages = [resolve(ref) for ref in refs]  # refuses a page that may not be sent, before any call
    citations = citations or doc_type.citations
    extracted, seconds, records = read_pages(doc_type, pages, roles, workers, citations)
    identities = tally(doc_type, extracted, seconds)
    evidence = {
        "family": family,
        "template": path.as_posix(),
        "template_sha256": doc_type.sha256,
        "tested_on": (today or date.today()).isoformat(),
        "config": dict(config or {}),
        "citations": citations,
        "rule": (
            "every identity evaluated wherever it applies, on cells whose two reads agree; held "
            "within n half-units of the printed precision for n printed values"
        ),
        "pages": records,
        "outcomes": {o: sum(i["outcome"] == o for i in identities) for o in OUTCOMES},
        "identities": identities,
    }
    out = evidence_path(path)
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--family", required=True)
    parser.add_argument("--pages", nargs="+", help="default: the pages it was drafted from")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dir", type=Path, default=TEMPLATES_DIR)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--citations",
        choices=(*CITATION_STRATEGIES, ocr.STRATEGY),
        help="default: the template types' own",
    )
    args = parser.parse_args(argv)
    roles = load_roles(args.config)
    guard = roles[extract.ROLE].inner.guard
    before = guard.spent()
    out = run_test(
        args.family,
        roles,
        directory=args.dir,
        refs=args.pages,
        config=describe_config(args.config),
        workers=args.workers,
        citations=args.citations,
    )
    evidence = json.loads(out.read_text())
    for identity in evidence["identities"]:
        print(
            f"  {identity['id']:<32} {identity['outcome']:<16} held {identity['held']} of "
            f"{identity['evaluated']} evaluated ({identity['applies']} places)"
        )
    print(f"{out}: {evidence['outcomes']}; ${guard.spent() - before:.4f} spent")


if __name__ == "__main__":
    main()
