"""The open-weights run on the Treasury Bulletin's real scans (PREREGISTRATION_OPENW.md, P46).

    python -m archivist.templates.real_openw deep --side held_out [--workers 8]
    python -m archivist.templates.real_openw deep --side development --pages <ref> <ref> \
        [--per-page 20] [--allowance 3] [--workers 8]

Muse Spark Open on Baseten (config/real_openw.toml) reads each of version 1's deep-check pages in
context, its boxes made by S0+table-v2 (templates/table_v2.py, which keeps S0+grid's box, the
order fallback's blind guard included, for any cell it cannot settle), and re-reads blind only the
drawn cells; policy v2 then decides those cells. Nothing is chosen again:

- The pages and their families are version 1's: sample.json of results/real_test/<side>/, drawn
  from the pages the classifier names and the title check confirms. No page is classified.
- The cells are version 1's draw (labels/draw.json, 400 cells), each found in Open's read by the
  rule below. On the development side, which has no draw, a stand-in is drawn here from version
  1's read of the pages given, per_page cells a page by random.Random(SEED).sample over the page's
  figure cells as labelling.draw counts them (rows not returned or left empty are not sampled).
- SAM 3.1's detections are version 1's, replayed from the cache: the Meta cap is the Meta total of
  the spend ledger, so a SAM call that is not cached is refused, never made. The run keeps its own
  cache (OWN_CACHE/<side>/cache), seeded entry by entry from cache/, which it never writes.

How a drawn cell is found in Open's read (match()): the labeller found a cell by its section, its
row's printed label and which occurrence of that label it is, and its column (Deviations of
PREREGISTRATION_REAL.md); the row's position was only a hint. So a fixed row is the template's row
of that key; a read row is the row of Open's read with the same label, folded to its letters and
digits (leader dots dropped), that is the same occurrence of it, counted from the top of the table
or, in a table read in sections, of the same section, over the rows the read gave a label; a drawn
row the first read gave no label is found by its position, as the labeller found it. The column is
the same. A cell whose row has no match, or whose page Open did not read, gets no value from Open.

Policy v2 is unchanged (verify.verify, no second looks), and every value of every page goes into
the identities as in version 1. Only the drawn cells keep their boxes, so only they are re-read:
a cell's status (accepted or review) depends on its own re-read, the identities on the in-context
values and what covers it, so it is the status a full run would give it. Proposals use the re-read
values of neighbouring cells, which are not asked here, so none is reported.

Each start resumes: a page read is never read again, a page that failed is tried again on each
start up to PAGE_TRIES starts in all, and verification runs over every page read, every answered
re-read coming from the cache. A run whose verdicts have no failed re-read is finished and refuses
to start again; one with failed re-reads may be started again, so that only those are asked, up to
PASSES verification passes in all, each pass's verdicts kept (verdicts.pass<n>.jsonl). A stall, no
answer for STALL_S seconds while a call is in flight, stops the run (stall.json).

Writes results/real_openw/<side>/: caps.json, draw.json (development side only), predictions.jsonl
(Open's single read with its boxes), boxes.jsonl (each page's box sources and what table_v2
found), failed.jsonl, cells.json (each drawn cell and the field of Open's read it is, or why
none), verdicts.jsonl (the drawn cells' verdicts) and run.json. The held-out side takes no option
and runs only on the code tagged TAG (frozen()), checked before anything is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from archivist.doctypes import DocType, recorded
from archivist.doctypes.template import ReadRows, Sections, TemplateType
from archivist.ingest.fraser import DEFAULT_ROOT
from archivist.models import BudgetExceeded, describe_config, load_roles
from archivist.models.budget import BACKEND_CAPS, LEDGER_PATH, BudgetGuard
from archivist.models.cache import CACHE_DIR, cache_key
from archivist.pipeline import extract, occlusion, reread, verify
from archivist.schema import PageExtraction, VerdictRecord
from archivist.templates import ocr, real_test, table_v2
from archivist.templates import test as arithmetic
from archivist.templates.pages import Page

CONFIG = Path("config/real_openw.toml")
OUT_DIR = Path("results/real_openw")
SOURCE_DIR = real_test.OUT_DIR  # version 1's records: its pages, its draw and its first read
DRAW = Path("labels/draw.json")
SIDES = real_test.SIDES
SEED = real_test.SEED
TAG = "run-real-openw"
FROZEN = ("src", "config", "templates", "labelling", "pyproject.toml", "uv.lock")
ALLOWANCE = 20.0  # USD on Baseten, the held-out run
DEV_ALLOWANCE = 3.0
PER_PAGE = 20  # the development side's stand-in draw
PAGE_TRIES = 3
PASSES = 3
STALL_S = 1800.0
STRATEGY = table_v2.STRATEGY
OWN_CACHE = Path("results/scratch/real_openw")  # <side>/cache: this run's answers; cache/ is only read
STRATA = {f: ("total_claims" if f == "total_claims_by_country" else "1939_1942") for f in real_test.FAMILIES}


class NotFrozen(RuntimeError):
    pass


class Finished(RuntimeError):
    pass


def frozen(git: Callable[..., subprocess.CompletedProcess] = real_test._git) -> None:
    """Raises NotFrozen unless TAG exists and nothing under FROZEN differs from it, tracked or
    untracked."""
    if git("rev-parse", "-q", "--verify", f"refs/tags/{TAG}").returncode != 0:
        raise NotFrozen(f"no tag {TAG}: the held-out side runs only on the tagged code")
    if git("diff", "--quiet", TAG, "--", *FROZEN).returncode != 0:
        raise NotFrozen(f"the code differs from {TAG} under {FROZEN}")
    untracked = git("status", "--porcelain", "--untracked-files=all", "--", *FROZEN).stdout
    if untracked.strip():
        raise NotFrozen(f"files under {FROZEN} not in {TAG}:\n{untracked}")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _lines(path: Path) -> list[dict]:
    return real_test._lines(path)


def _dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def caps(out: Path, allowance: float, ledger: Path = LEDGER_PATH) -> dict[str, float]:
    """The side's caps, recorded at its first start and read back on every later one: Baseten's
    at its ledger total plus the allowance, Meta's at its total, so SAM only replays, and no
    other backend may spend."""
    path = out / "caps.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    guard = BudgetGuard(0.0, ledger)
    record = {
        "meta": round(guard.spent("meta"), 6),
        "baseten": round(guard.spent("baseten") + allowance, 6),
        "allowance": allowance,
        "recorded_at": _now(),
    }
    out.mkdir(parents=True, exist_ok=True)
    _dump(path, record)
    return record


def set_caps(record: Mapping[str, float]) -> None:
    for backend, (variable, _) in BACKEND_CAPS.items():
        os.environ[variable] = str(record.get(backend, 0.0))  # a backend not recorded: no spend


# --- Version 1's pages and cells ----------------------------------------------------------------


def _parts(cell: str) -> tuple[str, str, str, str]:
    """family, page, row and column of a template cell id, as labelling.draw.parts."""
    head, page, row, column = cell.split(":")
    return head.removeprefix("T."), page, row, column


def pages_of(side: str, source: Path, wanted: Sequence[str] | None = None) -> dict[str, str]:
    """Each page to read and its family, from version 1's records: on the held-out side its
    deep-check sample; on the development side the pages wanted, each one version 1 read and
    the title check confirmed."""
    if side == "held_out":
        drawn = json.loads((source / "sample.json").read_text(encoding="utf-8"))
        if drawn.get("drawn_from") != real_test.DRAWN_FROM:
            raise ValueError(f"{source / 'sample.json'} was not drawn after the title check")
        return {ref: family for family, refs in drawn["pages"].items() for ref in refs}
    read = {p.page_id: p.doc_type for p in extract.load_predictions(source / "predictions.jsonl")}
    counted = real_test.confirmed(source)
    chosen = {}
    for ref in wanted or ():
        if ref not in read or counted.get(ref) != read[ref]:
            raise ValueError(f"{ref}: not a page version 1 read and the title check confirmed")
        chosen[ref] = read[ref]
    if not chosen:
        raise ValueError("the development side needs --pages")
    return chosen


def first_reads(source: Path, refs: Sequence[str]) -> dict[str, PageExtraction]:
    """Version 1's first read of the pages: only its row labels are used here."""
    wanted = set(refs)
    return {
        p.page_id: p for p in extract.load_predictions(source / "predictions.jsonl") if p.page_id in wanted
    }


LEADERS = re.compile(r"(\s*[.·…]){2,}\s*$")  # labelling.draw's


def printed(label: str | None) -> str:
    """A row label as printed, as labelling.draw has it: leader dots and surrounding space dropped."""
    return LEADERS.sub("", label or "").strip()


def figure_cells(page: PageExtraction, doc_type: TemplateType) -> list[str]:
    """The page's figure cells the draw samples from, as labelling.draw.cells_of counts them: in
    every row the read returned (not every cell abstained) and did not leave empty (a label or a
    figure); sorted by id."""
    label = next(c.key for c in doc_type.layout.columns if c.kind == "text")
    rows: dict[str, list] = defaultdict(list)
    for value in page.values:
        rows[_parts(value.field_id)[2]].append(value)
    cells = []
    for values in rows.values():
        figures = [v for v in values if _parts(v.field_id)[3] in doc_type.money_fields]
        if all(v.abstained for v in values):
            continue
        text = next(v.value for v in values if _parts(v.field_id)[3] == label)
        if not printed(text) and not any((v.value or "").strip() for v in figures):
            continue
        cells += [v.field_id for v in figures]
    return sorted(cells)


def stand_in(first: Mapping[str, PageExtraction], doc_types: Mapping[str, DocType], per_page: int) -> list[dict]:
    """The development side's draw: per_page figure cells a page, by random.Random(SEED).sample."""
    sample = []
    for ref in sorted(first):
        cells = figure_cells(first[ref], doc_types[first[ref].doc_type])
        for cell in random.Random(SEED).sample(cells, min(per_page, len(cells))):
            family = first[ref].doc_type
            sample.append({"cell": cell, "stratum": STRATA[family], "family": family, "page": ref})
    return sample


def drawn_cells(
    side: str,
    source: Path,
    out: Path,
    first: Mapping[str, PageExtraction],
    doc_types: Mapping[str, DocType],
    per_page: int,
) -> list[dict]:
    """The drawn cells: version 1's draw, or on the development side a stand-in drawn once."""
    if side == "held_out":
        draw = json.loads((source / DRAW).read_text(encoding="utf-8"))
        if draw["side"] != "held_out":
            raise ValueError(f"{source / DRAW} is the {draw['side']} side's draw")
        sample = draw["sample"]
    else:
        path = out / "draw.json"
        if not path.exists():
            record = {"seed": SEED, "per_page": per_page, "sample": stand_in(first, doc_types, per_page)}
            _dump(path, record | {"drawn_at": _now()})
        sample = json.loads(path.read_text(encoding="utf-8"))["sample"]
    strays = sorted({s["page"] for s in sample} - set(first))
    if strays:
        raise ValueError(f"cells drawn on pages version 1 did not read: {strays}")
    return sample


# --- Finding a drawn cell in Open's read --------------------------------------------------------


def folded(label: str | None) -> str:
    """A row label as compared: leader dots dropped, then its letters and digits, lower case."""
    return re.sub(r"[^a-z0-9]", "", printed(label).lower())


def signatures(doc_type: TemplateType, page: PageExtraction) -> dict[str, tuple[str, str, int]] | None:
    """Each read row's section ("" in a table not read in sections), folded label and which
    occurrence of that label it is, counted from the top of its table or section over the rows
    with a label (0 for a row with none). None where the template fixes its rows."""
    rows = doc_type.layout.rows
    if not isinstance(rows, ReadRows | Sections):
        return None
    column = next(c.key for c in doc_type.layout.columns if c.kind == "text")
    read = {_parts(v.field_id)[2]: v.value for v in page.values if _parts(v.field_id)[3] == column}
    seen: Counter[tuple[str, str]] = Counter()
    out = {}
    for key in doc_type.layout.row_keys:
        section = key.rsplit("_", 1)[0] if isinstance(rows, Sections) else ""
        label = folded(read.get(key))
        if label:
            seen[section, label] += 1
        out[key] = (section, label, seen[section, label] if label else 0)
    return out


def match(doc_type: TemplateType, first: PageExtraction, read: PageExtraction | None, cell: str) -> dict:
    """The field of Open's read a drawn cell is, and how it was found; field None if none."""
    family, page, row, column = _parts(cell)
    if read is None:
        return {"field": None, "how": "page_not_read"}
    ids = {v.field_id for v in read.values}
    mine = signatures(doc_type, first)
    if mine is None:
        key, how = row, "fixed_row"
    elif not mine[row][1]:
        key, how = row, "position_no_label"
    else:
        theirs = signatures(doc_type, read)
        found = [k for k, sig in theirs.items() if sig == mine[row]]
        if not found:
            return {"field": None, "how": "row_not_found"}
        (key,) = found  # an occurrence count names one row
        how = "label"
    field = f"T.{family}:{page}:{key}:{column}"
    if field not in ids:
        return {"field": None, "how": "row_not_found"}
    return {"field": field, "how": how, "same_position": key == row}


# --- A stall stops the run ----------------------------------------------------------------------


class Watched:
    """A role whose calls the watch sees start and end; everything else passes through."""

    def __init__(self, inner: Any, watch: Watch) -> None:
        self.inner, self.watch = inner, watch

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def complete(self, request: Any) -> Any:
        self.watch.enter()
        try:
            return self.inner.complete(request)
        finally:
            self.watch.leave()


class Watch:
    """Stops the process when calls are in flight and none has ended for stall_s seconds, after
    writing stall.json under the write lock, so no record is left half written."""

    def __init__(self, out: Path, lock: threading.Lock, stall_s: float = STALL_S, poll_s: float = 15.0) -> None:
        self.out, self.lock, self.stall_s, self.poll_s = out, lock, stall_s, poll_s
        self.in_flight, self.last = 0, time.monotonic()
        self._state = threading.Lock()
        self.stop = os._exit

    def enter(self) -> None:
        with self._state:
            if self.in_flight == 0:
                self.last = time.monotonic()
            self.in_flight += 1

    def leave(self) -> None:
        with self._state:
            self.in_flight -= 1
            self.last = time.monotonic()

    def stalled(self) -> bool:
        with self._state:
            return self.in_flight > 0 and time.monotonic() - self.last > self.stall_s

    def start(self) -> None:
        def loop() -> None:
            while True:
                time.sleep(self.poll_s)
                if self.stalled():
                    with self.lock:
                        record = {"stalled_at": _now(), "stall_s": self.stall_s, "in_flight": self.in_flight}
                        _dump(self.out / "stall.json", record)
                        print(f"stalled: no answer for {self.stall_s:.0f} s; stopped", flush=True)
                        self.stop(3)
                    return

        threading.Thread(target=loop, daemon=True).start()


# --- Its own cache, seeded from the shared one --------------------------------------------------


class ReadThrough:
    """A cached role whose own cache is seeded, entry by entry as it is asked, from another cache,
    which is read and never written: SAM's detections and any answer already given come from
    there, and every new answer stays in the run's own cache."""

    def __init__(self, inner: Any, source: Path) -> None:
        self.inner, self.source = inner, source

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _seed(self, request: Any) -> None:
        key = cache_key(self.inner.name, self.inner.model_id, request, self.inner.settings)
        target = self.inner.cache_dir / key[:2] / f"{key}.json"
        found = self.source / key[:2] / f"{key}.json"
        if not target.exists() and found.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(found, target)

    def complete(self, request: Any) -> Any:
        self._seed(request)
        return self.inner.complete(request)

    def segment(self, request: Any) -> Any:
        self._seed(request)
        return self.inner.segment(request)


# --- The run ------------------------------------------------------------------------------------


def read_one(
    page: Page, doc_type: TemplateType, roles: Mapping[str, object], layer: Sequence[ocr.Word], workers: int
) -> tuple[PageExtraction, dict]:
    """Open's single read of one page and its S0+table-v2 boxes; raises ExtractionFailed."""
    image = page.path.read_bytes()
    values = extract.read_page(
        image, page.page_id, roles[extract.ROLE], doc_type, "S0", arithmetic.output_tokens(doc_type)
    )
    check = arithmetic.blind_check(image, page.page_id, doc_type, roles[reread.ROLE], workers)
    values, sources, found = table_v2.assign(values, doc_type, image, layer, check)
    extraction = PageExtraction(page_id=page.page_id, doc_type=doc_type.name, values=values)
    return extraction, {"page": page.ref, "box_sources": sources, "table": found}


def passes_of(out: Path) -> list[Path]:
    return sorted(out.glob("verdicts.pass*.jsonl"), key=lambda p: int(p.stem.rsplit("pass", 1)[1]))


def _failed(verdicts: Sequence[VerdictRecord]) -> list[str]:
    return sorted(v.field_id for v in verdicts if v.evidence.reread_status == "failed")


def run(
    out: Path,
    side: str,
    roles: Mapping[str, object],
    doc_types: Mapping[str, DocType],
    *,
    source: Path,
    wanted: Sequence[str] | None = None,
    per_page: int = PER_PAGE,
    workers: int = 8,
    root: Path = DEFAULT_ROOT,
    layer_of: Callable[[Page], Sequence[ocr.Word]] | None = None,
    lock: threading.Lock | None = None,
) -> tuple[list[VerdictRecord], dict]:
    """Read and box the pages not yet read, find the drawn cells, then verify them; returns their
    verdicts and what goes in run.json, less the costs."""
    layer_of = layer_of or (lambda page: real_test.words(page, root))
    lock = lock or threading.Lock()
    out.mkdir(parents=True, exist_ok=True)
    family_of = pages_of(side, source, wanted)
    predictions, boxes, failures = (out / n for n in ("predictions.jsonl", "boxes.jsonl", "failed.jsonl"))
    read = {line["page_id"] for line in _lines(predictions)}
    tries = Counter(line["page"] for line in _lines(failures))
    todo = [ref for ref in sorted(family_of) if ref not in read and tries[ref] < PAGE_TRIES]
    verdicts_path = out / verify.VERDICTS_FILE
    if verdicts_path.exists():
        if not todo and not _failed(verify.load_verdicts(verdicts_path)):
            raise Finished(f"{out} is finished: every page is read or out of tries, no re-read failed")
        if len(passes_of(out)) + 1 >= PASSES:
            raise Finished(f"{out} is finished: {PASSES} verification passes are the most allowed")

    first = first_reads(source, sorted(family_of))
    sample = drawn_cells(side, source, out, first, doc_types, per_page)

    def one(ref: str) -> None:
        page = real_test.resolve(ref, side, root)
        try:
            extraction, record = read_one(page, doc_types[family_of[ref]], roles, layer_of(page), workers)
        except BudgetExceeded:
            raise
        except Exception as error:  # one page failing must not stop the others
            line = {"page": ref, "failed": f"{type(error).__name__}: {error}"[:1000], "at": _now()}
            with lock, failures.open("a", encoding="utf-8") as log:
                log.write(json.dumps(line) + "\n")
            print(f"{ref}: the read failed", flush=True)
            return
        with lock:
            with boxes.open("a", encoding="utf-8") as log:
                log.write(json.dumps(record) + "\n")
            with predictions.open("a", encoding="utf-8") as log:
                log.write(extraction.model_dump_json() + "\n")
        print(f"{ref}: {len(extraction.values)} cells read", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(one, ref) for ref in todo]):
            future.result()

    pages = {p.page_id: p for p in extract.load_predictions(predictions)}
    found = []
    for s in sample:
        doc_type = doc_types[s["family"]]
        found.append({**{k: s[k] for k in ("cell", "stratum", "family", "page")},
                      **match(doc_type, first[s["page"]], pages.get(s["page"]), s["cell"])})
    _dump(out / "cells.json", {"cells": found})
    targets = {c["field"] for c in found if c["field"] is not None}

    # Only the drawn cells keep their boxes, so only they are re-read; every value still enters
    # the identities, which read values and never boxes.
    kept = [
        p.model_copy(update={"values": [
            v if v.field_id in targets else v.model_copy(update={"citation": None}) for v in p.values
        ]})
        for ref, p in sorted(pages.items())
        if any(c["page"] == ref and c["field"] for c in found)
    ]
    images = {p.page_id: real_test.resolve(p.page_id, side, root).path for p in kept}
    verdicts, calls = verify.verify(
        kept, images, roles, correct_citations=False, doc_types=doc_types, workers=workers,
        policy="v2", second_looks=False,
    )
    verdicts = [v for v in verdicts if v.field_id in targets]
    if verdicts_path.exists():
        verdicts_path.rename(out / f"verdicts.pass{len(passes_of(out)) + 1}.jsonl")
    verdicts_path.write_text("".join(v.model_dump_json() + "\n" for v in verdicts), encoding="utf-8")

    sources = {f: s for line in _lines(boxes) for f, s in line["box_sources"].items()}
    guards = [line["table"]["v1"].get("order") for line in _lines(boxes)]
    tries = Counter(line["page"] for line in _lines(failures))
    read_from = [source / "sample.json", source / DRAW] if side == "held_out" else [out / "draw.json"]
    read_from += [source / "predictions.jsonl", source / "titles.jsonl"]
    record = {
        "side": side,
        "inputs_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in read_from if path.exists()
        },
        "pages": dict(sorted(family_of.items())),
        "pages_read": len(pages),
        "failed": sorted(set(family_of) - set(pages)),
        "page_tries": dict(sorted(tries.items())),
        "cells": len(found),
        "cells_found": dict(sorted(Counter(c["how"] for c in found).items())),
        "cells_at_the_same_position": sum(bool(c.get("same_position")) for c in found),
        "order_guard": {  # the order fallback's blind guard (S0+grid's, kept by table_v2)
            "pages": sum(bool(g) for g in guards),
            "cells_reread": sum(g["sampled"] for g in guards if g),
            "used": sum(bool(g and g["used"]) for g in guards),
        },
        "box_sources_all_cells": dict(sorted(Counter(sources.values()).items())),
        "box_sources_drawn_cells": dict(sorted(Counter(sources.get(f) for f in sorted(targets)).items())),
        "counts": {"pages": len(kept), **verify._counts(verdicts)},
        "rereads_failed": _failed(verdicts),
        "verification_pass": len(passes_of(out)) + 1,
        "calls": calls,
    }
    return verdicts, record


# --- The command --------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("stage", choices=("deep",))
    parser.add_argument("--side", choices=SIDES, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--pages", nargs="+", help="development side only: the pages to read")
    parser.add_argument("--per-page", type=int, help=f"development only: default {PER_PAGE}")
    parser.add_argument("--allowance", type=float, help=f"development only: default {DEV_ALLOWANCE}")
    args = parser.parse_args(argv)
    if args.side == "held_out":
        if args.pages or args.per_page is not None or args.allowance is not None:
            parser.error("the held-out side takes the pre-registration's choices alone")
        frozen()  # before any held-out page or record is opened
        allowance = ALLOWANCE
    else:
        allowance = DEV_ALLOWANCE if args.allowance is None else args.allowance
        if allowance > DEV_ALLOWANCE:
            parser.error(f"the development side may spend at most ${DEV_ALLOWANCE:.2f}")

    out = OUT_DIR / args.side
    record = caps(out, allowance)
    set_caps(record)
    roles = load_roles(CONFIG, cache_dir=OWN_CACHE / args.side / "cache")
    doc_types = real_test._types(CONFIG)
    guard = roles[extract.ROLE].inner.guard
    roles = {name: ReadThrough(role, CACHE_DIR) for name, role in roles.items()}
    before = {b: guard.spent(b) for b in BACKEND_CAPS}
    started = _now()
    lock = threading.Lock()
    watch = Watch(out, lock)
    for role in (extract.ROLE, reread.ROLE):
        roles[role] = Watched(roles[role], watch)
    watch.start()
    try:
        verdicts, summary = run(
            out,
            args.side,
            roles,
            doc_types,
            source=SOURCE_DIR / args.side,
            wanted=args.pages,
            per_page=PER_PAGE if args.per_page is None else args.per_page,
            workers=args.workers,
            lock=lock,
        )
    except Finished as done:
        parser.error(str(done))
    cost_full = summary["calls"].pop("cost_full_usd")
    spent = {b: round(guard.spent(b) - before[b], 6) for b in BACKEND_CAPS}
    summary = {
        "config": describe_config(CONFIG),
        "doc_types": recorded(doc_types),
        "caps": record,
        "started_at": started,
        **summary,
        "citations": STRATEGY,
        "policy": {
            "version": "v2",
            "second_looks": False,
            "rereads": "the drawn cells only",
            "occlusion_prompts": list(occlusion.PROMPTS),
            "occlusion_cover": occlusion.COVER,
            "reread_padding": {"vertical": reread.PAD_Y, "horizontal": reread.PAD_X},
        },
        "cost_usd": spent,
        "cost_full_usd": cost_full,
        "finished_at": _now(),
    }
    _dump(out / "run.json", summary)
    counts = summary["counts"]
    print(
        f"{summary['pages_read']} of {len(summary['pages'])} pages read ({len(summary['failed'])} failed); "
        f"{summary['cells']} drawn cells, found {summary['cells_found']}; verdicts {counts['by_status']}; "
        f"{len(summary['rereads_failed'])} re-reads failed; spent {spent}"
    )


if __name__ == "__main__":
    main()
