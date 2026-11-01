"""P33: Muse Spark Open's cost, speed and empty answers, measured on development pages only.

    uv run python -m openw.measure pick      # which five pages; no model, no page opened
    uv run python -m openw.measure probe     # step 3: one-cell re-reads at every reasoning setting
    uv run python -m openw.measure pages     # step 4: five page reads a host, 40 cells a page re-read
    uv run python -m openw.measure speed     # step 5: 40 re-reads at 1, 4 and 8 calls at once

Each command is resumable: what is in the cache is not asked again, and what a command has
already written is not redone. Every call goes through archivist.models (openw/spy.py), is
recorded in results/openw_measure/calls.jsonl and is in the spend ledger as usual. The caps are
this task's own, recorded in caps.json at the first start: each host's total in the ledger then,
plus ALLOWANCE (the two together stay under the task's $8), and Meta's at zero, so no Meta call can
be made. Every page is checked against data/real/split.json's development issues before any file
is opened or any call made; nothing held out is read, listed or sent.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from archivist.doctypes import from_config
from archivist.doctypes.template import TemplateType, cell_id
from archivist.models import BudgetExceeded, LLMRequest
from archivist.models.budget import BACKEND_CAPS, LEDGER_PATH, BudgetGuard
from archivist.pipeline import extract, reread
from archivist.schema import BBox, Citation, ExtractedValue
from archivist.templates import grid, real_test
from archivist.templates import test as arithmetic
from archivist.templates.pages import REAL

from openw import analyse, spy

ROOT = Path("results/openw_measure")
SCRATCH = Path("results/scratch/openw")  # gitignored: the cache of this measurement
CACHE = SCRATCH / "cache"
CONFIG = Path("openw/models.toml")
SPLIT = Path("data/real/split.json")
HOSTS = ("baseten", "fireworks")
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
ALLOWANCE = 3.8  # USD a host: 2 x 3.8 stays under the task's $8
SEED = 33
CELLS_PER_PAGE = 40
SPEED_PER_PAGE_LEVEL = 8  # five pages x eight = the 40 re-reads of a speed level
LEVELS = (1, 4, 8)
PROBE_PAGE = "1939-12_p053"  # a short-term foreign liabilities page that is not one of the five
PROBE_CELLS = 4
PICK_RULE = (
    "For each of version 1's five families (config/real_test.toml), the lowest page id among the "
    "pages its committed evidence file (templates/<family>.evidence.json) lists as tested, which "
    "is also the first page it was drafted from; each checked to be a page of an issue in the "
    "development list of data/real/split.json before any call."
)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- Pages: development only ----------------------------------------------------------------


def development(ref: str):
    """The page named by ref, but only if its issue is a development issue of the split: checked
    here, from split.json, before real_test.resolve opens anything."""
    found = REAL.fullmatch(ref)
    development_issues = read_json(SPLIT)["development"]
    if found is None or found["issue"] not in development_issues:
        raise SystemExit(f"{ref}: not a page of a development issue; nothing was opened")
    return real_test.resolve(ref, "development")


def pick() -> dict:
    """The five pages, by PICK_RULE; writes pick.json. Opens no page and calls no model."""
    chosen = {}
    for family in real_test.FAMILIES:
        evidence = read_json(Path("templates") / f"{family}.evidence.json")
        refs = sorted(p["ref"] for p in evidence["pages"])
        found = REAL.fullmatch(refs[0])
        if found is None or found["issue"] not in read_json(SPLIT)["development"]:
            raise SystemExit(f"{refs[0]}: not a development page")
        chosen[family] = {"ref": refs[0], "issue": found["issue"], "evidence_pages": refs}
    record = {"rule": PICK_RULE, "picked_at": now(), "pages": chosen}
    write_json(ROOT / "pick.json", record)
    return record


def picks() -> dict[str, str]:
    """ref -> family, from pick.json."""
    return {v["ref"]: family for family, v in read_json(ROOT / "pick.json")["pages"].items()}


# --- Caps and roles -------------------------------------------------------------------------


def start(allowance: float = ALLOWANCE) -> dict:
    """Set this task's caps (recorded at the first start, read back on every later one)."""
    path = ROOT / "caps.json"
    if path.exists():
        record = read_json(path)
    else:
        guard = BudgetGuard(0.0, LEDGER_PATH)
        spent = {b: round(guard.spent(b), 6) for b in ("baseten", "fireworks")}
        record = {
            "baseten": round(spent["baseten"] + allowance, 6),
            "fireworks": round(spent["fireworks"] + allowance, 6),
            "meta": 0.0,  # nothing in this task calls Meta's API
            "allowance_per_host": allowance,
            "spent_at_start": spent,
            "ledger_lines_at_start": len(LEDGER_PATH.read_text().splitlines()),
            "recorded_at": now(),
        }
        write_json(path, record)
    for backend, (variable, _) in BACKEND_CAPS.items():
        os.environ[variable] = str(record[backend])
    return record


def spent_since_start() -> dict[str, float]:
    record = read_json(ROOT / "caps.json")
    guard = BudgetGuard(0.0, LEDGER_PATH)
    return {
        b: round(guard.spent(b) - record["spent_at_start"][b], 6) for b in ("baseten", "fireworks")
    }


def make_roles() -> dict[str, spy.Recorder]:
    start()
    return spy.build_roles(CONFIG, cache_dir=CACHE, ledger_path=LEDGER_PATH, sink=spy.Sink(ROOT / "calls.jsonl"))


class Tagged:
    """A role that tags every call made through it, from whichever thread (a thread pool inside
    the pipeline's code does not inherit this thread's tags)."""

    def __init__(self, inner: Any, **tags: Any) -> None:
        self.inner, self.tags = inner, tags
        self.name, self.model_id = inner.name, inner.model_id

    def complete(self, request: LLMRequest):
        with spy.tagged(**self.tags):
            return self.inner.complete(request)


# --- One blind re-read ----------------------------------------------------------------------


def parsed(text: str) -> tuple[bool, str | None]:
    try:
        reread._parse(text)
    except (ValueError, TypeError) as error:
        return False, f"{type(error).__name__}: {error}"[:200]
    return True, None


def ask(llm: Any, png: bytes, prompt: str, *, tokens: int = reread.REREAD_TOKENS, **tags: Any) -> dict:
    """One re-read request, built as reread.reread builds its first one (so it has the same cache
    key), and how it ended: ok, null (illegible), empty, unparseable or error."""
    request = LLMRequest(
        role=reread.ROLE,
        prompt=prompt,
        images=(png,),
        json_schema=reread.SCHEMA,
        max_output_tokens=tokens,
    )
    started = time.perf_counter()
    with spy.tagged(validate=parsed, **tags):
        try:
            response = llm.complete(request)
        except BudgetExceeded:
            raise
        except Exception as error:
            return {
                "kind": "error",
                "value": None,
                "error": f"{type(error).__name__}: {error}"[:200],
                "wall_s": round(time.perf_counter() - started, 3),
            }
    wall = round(time.perf_counter() - started, 3)
    text = response.text
    if not text.strip():
        return {"kind": "empty", "value": None, "wall_s": wall, "cached": response.cached}
    try:
        value = reread._parse(text)
    except (ValueError, TypeError) as error:
        return {
            "kind": "unparseable",
            "value": None,
            "error": f"{type(error).__name__}: {error}"[:200],
            "wall_s": wall,
            "cached": response.cached,
        }
    return {
        "kind": "null" if value is None else "ok",
        "value": value,
        "wall_s": wall,
        "cached": response.cached,
    }


# --- Step 3: reasoning settings --------------------------------------------------------------


def probe_boxes(page) -> list[tuple[BBox, str]]:
    """PROBE_CELLS figures of the page, evenly spread down it, as the PDF's own text layer boxes
    them: a crop and the text printed there. No model read is needed to have a cell to re-read."""
    layer = real_test.words(page)
    figures = sorted(
        (w for w in layer if re.fullmatch(r"\d{1,3}(?:,\d{3})+", w.text)),
        key=lambda w: (w.box.y0, w.box.x0),
    )
    step = len(figures) // (PROBE_CELLS + 1)
    return [(w.box, w.text) for w in (figures[step * k] for k in range(1, PROBE_CELLS + 1))]


HOST_EFFORTS = {
    "baseten": ("max",),
    "fireworks": ("max", "adaptive", "int64", "false"),
}  # probed second, after the APIs' error texts named them


def probe(workers: int = 4, extra: bool = False) -> dict:
    page = development(PROBE_PAGE)
    roles = make_roles()
    doc_type = from_config(CONFIG)["short_term_foreign_liabilities_as"]
    picture = Image.open(page.path)
    picture.load()
    column = next(c.key for c in doc_type.layout.columns if c.kind == "money")
    prompt = doc_type.reread_prompt(
        cell_id(doc_type.name, page.page_id, doc_type.layout.row_keys[0], column)
    )
    cells = probe_boxes(page)
    pngs = [reread.crop(picture, box) for box, _ in cells]
    jobs = [
        (host, effort, i)
        for host in HOSTS
        for effort in (HOST_EFFORTS[host] if extra else (*EFFORTS, "bogus"))
        for i in range(len(cells) if effort != "bogus" else 1)
    ]

    def one(job: tuple[str, str, int]) -> None:
        host, effort, i = job
        ask(roles[f"{host}.{effort}"], pngs[i], prompt, step="probe", cell=f"probe{i}", page=PROBE_PAGE)

    with ThreadPoolExecutor(max_workers=workers * len(HOSTS)) as pool:
        for future in as_completed([pool.submit(one, job) for job in jobs]):
            future.result()
    summary = analyse.probe_summary(lines(ROOT / "calls.jsonl"))
    record = {
        "page": PROBE_PAGE,
        "prompt": prompt,
        "cells": [{"id": f"probe{i}", "printed": text, "box": box.model_dump()} for i, (box, text) in enumerate(cells)],
        "max_output_tokens": reread.REREAD_TOKENS,
        "rule": analyse.__doc__,
        "hosts": summary,
        "finished_at": now(),
    }
    write_json(ROOT / "probe.json", record)
    return record


def reread_effort(host: str) -> str:
    return read_json(ROOT / "probe.json")["hosts"][host]["reread_effort"]


# --- Step 4: five pages, two hosts ------------------------------------------------------------


def _values(path: Path) -> list[ExtractedValue]:
    return [ExtractedValue.model_validate(v) for v in read_json(path)["values"]]


def read_task(host: str, ref: str, family: str, roles: dict, doc_types: dict) -> dict:
    """The single read of one page by one host, as real_test.read_one's first step makes it."""
    page = development(ref)
    image = page.path.read_bytes()
    doc_type = doc_types[family]
    width, height = Image.open(io.BytesIO(image)).size

    def valid(text: str) -> tuple[bool, str | None]:
        try:
            doc_type.parse(page.page_id, json.loads(text), width, height)
        except (ValueError, TypeError) as error:
            return False, f"{type(error).__name__}: {error}"[:200]
        return True, None

    started = time.perf_counter()
    out: dict = {
        "host": host,
        "ref": ref,
        "family": family,
        "allowance": arithmetic.output_tokens(doc_type),
        "effort": "low",
        "started_at": now(),
    }
    try:
        with spy.tagged(step="page_read", page=ref, family=family, validate=valid):
            values = extract.read_page(
                image,
                page.page_id,
                roles[f"{host}.low.long"],
                doc_type,
                "S0",
                arithmetic.output_tokens(doc_type),
            )
    except BudgetExceeded:
        raise
    except Exception as error:
        out |= {"ok": False, "error": f"{type(error).__name__}: {error}"[:600]}
    else:
        out |= {"ok": True, "values": [v.model_dump() for v in values]}
    out["seconds"] = round(time.perf_counter() - started, 1)
    write_json(ROOT / "reads" / host / f"{ref}.json", out)
    return out


def read_phase(workers: int) -> None:
    roles, doc_types = make_roles(), from_config(CONFIG)
    jobs = []
    for host in HOSTS:
        for ref, family in picks().items():
            path = ROOT / "reads" / host / f"{ref}.json"
            if path.exists() and (read_json(path).get("ok") or read_json(path).get("final")):
                continue  # read; or failed and left as it is (stopped by hand, not to be asked again)
            jobs.append((host, ref, family))
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)) if jobs else 1)) as pool:
        futures = {pool.submit(read_task, h, r, f, roles, doc_types): (h, r) for h, r, f in jobs}
        for future in as_completed(futures):
            out = future.result()
            host, ref = futures[future]
            print(
                f"read {host:<9} {ref}: {'ok' if out['ok'] else 'FAILED'}"
                f"{'' if not out['ok'] else ', ' + str(len(out['values'])) + ' cells'}"
                f" in {out['seconds']} s  {spent_since_start()}",
                flush=True,
            )


def box_phase() -> None:
    """The boxes, from the first host whose read of the page succeeded (HOSTS order), by the
    steps of real_test.read_one: the order fallback's blind guard, then grid.assign."""
    roles, doc_types = make_roles(), from_config(CONFIG)
    for ref, family in picks().items():
        path = ROOT / "boxes" / f"{ref}.json"
        if path.exists():
            continue
        crop_host = next(
            (h for h in HOSTS if (ROOT / "reads" / h / f"{ref}.json").exists() and read_json(ROOT / "reads" / h / f"{ref}.json").get("ok")),
            None,
        )
        if crop_host is None:
            print(f"boxes {ref}: no host read it", flush=True)
            continue
        page = development(ref)
        image = page.path.read_bytes()
        doc_type = doc_types[family]
        values = _values(ROOT / "reads" / crop_host / f"{ref}.json")
        rereader = Tagged(roles[f"{crop_host}.{reread_effort(crop_host)}"], step="guard", page=ref)
        check = arithmetic.blind_check(image, page.page_id, doc_type, rereader, 8)
        boxed, sources, found = grid.assign(values, doc_type, image, real_test.words(page), check)
        cells = {}
        for v in boxed:
            if v.citation is not None and not v.abstained and v.value is not None:
                cells[v.field_id] = {
                    "region": reread.region(v.citation).model_dump(),
                    "source": sources.get(v.field_id),
                }
        write_json(
            ROOT / "boxes" / f"{ref}.json",
            {"ref": ref, "crop_host": crop_host, "grid": found, "eligible": len(cells), "cells": cells},
        )
        print(f"boxes {ref}: from {crop_host}'s read, {len(cells)} cells to re-read; grid {found}", flush=True)


def draw_phase() -> dict:
    """40 cells of each page for the main re-reads, with random.Random(SEED).sample over the
    page's eligible cells sorted (read, boxed, not abstained: what verify re-reads), and 24 more
    that no other step uses, for the speed test: eight a level."""
    path = ROOT / "draw.json"
    if path.exists():
        return read_json(path)
    pages = {}
    for ref in picks():
        boxes = ROOT / "boxes" / f"{ref}.json"
        if not boxes.exists():
            continue
        record = read_json(boxes)
        eligible = sorted(record["cells"])
        main = random.Random(SEED).sample(eligible, min(CELLS_PER_PAGE, len(eligible)))
        rest = sorted(set(eligible) - set(main))
        spare = random.Random(SEED + 1).sample(
            rest, min(SPEED_PER_PAGE_LEVEL * len(LEVELS), len(rest))
        )
        speed = {
            str(level): sorted(spare[i * SPEED_PER_PAGE_LEVEL : (i + 1) * SPEED_PER_PAGE_LEVEL])
            for i, level in enumerate(LEVELS)
        }
        pages[ref] = {
            "crop_host": record["crop_host"],
            "eligible": len(eligible),
            "cells": sorted(main),
            "speed": speed,
        }
    draw = {"seed": SEED, "per_page": CELLS_PER_PAGE, "drawn_at": now(), "pages": pages}
    write_json(path, draw)
    return draw


_REREADS = threading.Lock()


def arms(host: str) -> tuple[str, ...]:
    """The settings the same crops are re-read at on a host: the one step 3 chose, and "minimal",
    version 1's, which both hosts take (HTTP 200) and neither honours: added after the probe, to
    see on 200 cells what it showed on four."""
    return tuple(dict.fromkeys((reread_effort(host), "minimal")))


def reread_phase(workers: int) -> None:
    roles, doc_types = make_roles(), from_config(CONFIG)
    draw = draw_phase()
    done = {(r["host"], r["effort"], r["cell"]) for r in lines(ROOT / "rereads.jsonl")}
    pictures: dict[str, Image.Image] = {}
    jobs = []
    for ref, entry in draw["pages"].items():
        page = development(ref)
        picture = Image.open(page.path)
        picture.load()
        pictures[ref] = picture
        boxes = read_json(ROOT / "boxes" / f"{ref}.json")["cells"]
        doc_type = doc_types[picks()[ref]]
        for cell in entry["cells"]:
            box = BBox.model_validate(boxes[cell]["region"])
            png = reread.crop(picture, box)
            for host in HOSTS:
                for effort in arms(host):
                    if (host, effort, cell) not in done:
                        jobs.append((host, effort, ref, cell, png, doc_type.reread_prompt(cell)))

    def one(job: tuple) -> dict:
        host, effort, ref, cell, png, prompt = job
        llm = roles[f"{host}.{effort}"]
        tags = {"step": "reread", "page": ref, "cell": cell}
        first = ask(llm, png, prompt, attempt="first", **tags)
        record = {"host": host, "ref": ref, "cell": cell, "effort": effort, "first": first}
        if first["kind"] in ("empty", "unparseable"):
            record["double"] = ask(
                llm, png, prompt, tokens=2 * reread.REREAD_TOKENS, attempt="double", **tags
            )
        with _REREADS, (ROOT / "rereads.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
        return record

    count = 0
    with ThreadPoolExecutor(max_workers=workers * len(HOSTS)) as pool:
        for future in as_completed([pool.submit(one, job) for job in jobs]):
            future.result()
            count += 1
            if count % 25 == 0:
                print(f"reread {count}/{len(jobs)}  {spent_since_start()}", flush=True)
    print(f"reread done: {count} cells asked  {spent_since_start()}", flush=True)


def pages(workers: int) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "probe.json").exists():
        raise SystemExit("run probe first: the re-read setting comes from it")
    read_phase(workers=len(HOSTS) * len(picks()))
    box_phase()
    reread_phase(workers)


# --- Step 5: speed ---------------------------------------------------------------------------


def speed() -> None:
    roles, doc_types = make_roles(), from_config(CONFIG)
    draw = read_json(ROOT / "draw.json")
    path = ROOT / "speed.json"
    results = read_json(path) if path.exists() else {"levels": list(LEVELS), "runs": []}
    already = {(r["host"], r["level"]) for r in results["runs"]}
    used = {(r["host"], r["effort"], r["cell"]) for r in lines(ROOT / "rereads.jsonl")}
    pngs: dict[str, tuple[bytes, str]] = {}
    for ref, entry in draw["pages"].items():
        picture = Image.open(development(ref).path)
        picture.load()
        boxes = read_json(ROOT / "boxes" / f"{ref}.json")["cells"]
        for level_cells in entry["speed"].values():
            for cell in level_cells:
                png = reread.crop(picture, BBox.model_validate(boxes[cell]["region"]))
                pngs[cell] = (png, doc_types[picks()[ref]].reread_prompt(cell))
    guard = BudgetGuard(0.0, LEDGER_PATH)
    for host in HOSTS:
        effort = reread_effort(host)
        llm = roles[f"{host}.{effort}"]
        for level in LEVELS:
            if (host, level) in already:
                continue
            cells = sorted(c for e in draw["pages"].values() for c in e["speed"][str(level)])
            assert not any((host, effort, c) in used for c in cells), "a speed cell was already re-read"
            parse_started = time.perf_counter()
            guard.spent("baseten")
            ledger_parse_s = round(time.perf_counter() - parse_started, 3)
            started = time.perf_counter()

            def one(cell: str) -> dict:
                png, prompt = pngs[cell]
                return ask(llm, png, prompt, step=f"speed{level}", cell=cell, attempt="first") | {"cell": cell}

            with ThreadPoolExecutor(max_workers=level) as pool:
                outcomes = list(pool.map(one, cells))
            wall = round(time.perf_counter() - started, 2)
            run = {
                "host": host,
                "effort": effort,
                "level": level,
                "cells": len(cells),
                "wall_s": wall,
                "calls_per_s": round(len(cells) / wall, 3),
                "cache_hits": sum(bool(o.get("cached")) for o in outcomes),
                "kinds": {k: sum(o["kind"] == k for o in outcomes) for k in ("ok", "null", "empty", "unparseable", "error")},
                "call_s": [o["wall_s"] for o in outcomes],
                "ledger_parse_s": ledger_parse_s,
                "finished_at": now(),
            }
            results["runs"].append(run)
            write_json(path, results)
            print(f"speed {host} x{level}: {len(cells)} calls in {wall} s = {run['calls_per_s']}/s  {run['kinds']}  {spent_since_start()}", flush=True)


# --- A diagnostic, outside the measurement ---------------------------------------------------------

DIAGNOSE_CELLS = 16
UPSCALE = 3


def diagnose() -> dict:
    """Fireworks answered "can't read" (null) for about half of the crops Baseten read. Is it that
    the crops are tiny? Sixteen of those cells (Fireworks null, Baseten a figure, at "low"), the same
    crop enlarged UPSCALE times with Lanczos. NOT version 1's crop: a diagnostic, reported as one."""
    roles, doc_types = make_roles(), from_config(CONFIG)
    records = lines(ROOT / "rereads.jsonl")
    by = {(r["host"], r["effort"], r["cell"]): r for r in records}
    cells = sorted(
        c
        for (h, e, c), r in by.items()
        if h == "fireworks" and e == "low" and r["first"]["kind"] == "null"
        and by[("baseten", "low", c)]["first"]["kind"] == "ok"
        and (by[("baseten", "low", c)]["first"]["value"] or "").strip()
    )
    chosen = random.Random(SEED).sample(cells, min(DIAGNOSE_CELLS, len(cells)))
    out = []
    for cell in sorted(chosen):
        ref = by[("fireworks", "low", cell)]["ref"]
        picture = Image.open(development(ref).path)
        picture.load()
        box = BBox.model_validate(read_json(ROOT / "boxes" / f"{ref}.json")["cells"][cell]["region"])
        small = Image.open(io.BytesIO(reread.crop(picture, box)))
        big = small.resize((small.width * UPSCALE, small.height * UPSCALE), Image.LANCZOS)
        buffer = io.BytesIO()
        big.save(buffer, format="PNG")
        prompt = doc_types[picks()[ref]].reread_prompt(cell)
        answer = ask(roles["fireworks.low"], buffer.getvalue(), prompt, step="diagnose_upscale", cell=cell, attempt="first")
        out.append(
            {
                "cell": cell,
                "crop_px": [small.width, small.height],
                "baseten": by[("baseten", "low", cell)]["first"]["value"],
                "fireworks_original": "null",
                "fireworks_upscaled": answer,
            }
        )
    record = {
        "what": "diagnostic, not version 1's crops: Fireworks null cells re-sent enlarged",
        "upscale": UPSCALE,
        "candidates": len(cells),
        "cells": out,
        "finished_at": now(),
    }
    write_json(ROOT / "diagnose.json", record)
    return record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=("pick", "probe", "pages", "speed", "diagnose"))
    parser.add_argument("--workers", type=int, default=4, help="re-reads at once on each host")
    parser.add_argument("--extra", action="store_true", help="probe: the settings the error texts named")
    args = parser.parse_args(argv)
    if args.command == "pick":
        record = pick()
        for family, v in record["pages"].items():
            print(f"{family:<44} {v['ref']}")
        return
    if args.command == "probe":
        probe(extra=args.extra)
    elif args.command == "pages":
        pages(args.workers)
    elif args.command == "diagnose":
        diagnose()
    else:
        speed()
    print(f"spent since start: {spent_since_start()}")


if __name__ == "__main__":
    sys.exit(main())
