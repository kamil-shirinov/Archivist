"""Muse Spark Open on two hosts, on the same development pages (P30): results/hosts_compare.json.

    python -m archivist.eval.compare_hosts [--every 3] [--workers 4] [--report-only]

The pages are every third of the synthetic development split (data/dev, sorted by name; the rule
was fixed before any page was read), the same for both hosts. Each host reads them through the
single-pass extraction (archivist.pipeline.extract: classify, then read every field) with its own
config, config/models_open.toml for Baseten and config/models_fireworks.toml for Fireworks, which
differ in the host and nothing else: the same model, prompts and reasoning_effort "low". Both go
through load_roles, so each call is budgeted against its backend's cap and recorded in the ledger.
The cache is a scratch one (results/scratch/hosts/cache), not the project's: the project's would
answer Baseten's reads of these pages from P13 free and untimed, and every call here is meant to be
live. Hosts run one after the other, not at the same time.

Every call is logged to results/scratch/hosts/calls_<host>.jsonl as it ends (how long it took,
what it cost, whether it was a second ask, how it failed), with each retry a host made and each
closing-bracket repair (baseten_api.close_brackets, which both hosts use), so a run interrupted and
resumed keeps what it measured. The report is built from those logs, the runs' predictions and the
development split's ground truth (archivist.eval may read gt/); --report-only builds it without
a call. Two values are the same when metrics.normalise makes them equal (both hosts giving none, or
abstaining, is the same too), and a field is right as metrics.score_page says; a host's accuracy counts a page it failed to read as omitted. As a noise
floor, Baseten's fresh reads are also compared with its own P13 reads of the same pages
(results/runs/baseline-dev-open), made with the same model at the same effort and settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import random
import shutil
import statistics
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from archivist.doctypes import from_config
from archivist.eval import metrics
from archivist.eval.run_eval import DATA_ROOT, load_gt
from archivist.models import LLMRequest, LLMResponse, VisionLLM, describe_config, load_roles
from archivist.pipeline import extract
from archivist.schema import ExtractedValue, PageExtraction, PageGT

SPLIT = "dev"
HOSTS = {  # host -> the config whose roles run on it; first is the reference
    "baseten": Path("config/models_open.toml"),
    "fireworks": Path("config/models_fireworks.toml"),
}
SCRATCH = Path("results/scratch/hosts")
OUT_PATH = Path("results/hosts_compare.json")
MD_PATH = Path("results/hosts_compare.md")
NOISE_RUN = "baseline-dev-open"  # Baseten's own P13 reads of the dev split
BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED = 2_000, 3030
REPAIR_WORDS = "left open were closed"  # baseten_api.close_brackets' warning
WHAT = (
    "Muse Spark Open on Baseten and on Fireworks, single-pass extraction of the same development "
    "pages, same prompts, same effort, read live (scratch cache) and timed. 95% intervals are "
    "page-bootstrap."
)
CAVEATS = [
    "Development data only: synthetic ledger cards and payment memos from data/dev, every third "
    "page. Nothing here was scored on the frozen test set or on a held-out real page.",
    "The two hosts are not known to serve the same checkpoint: Baseten's slug ends in -1026, "
    "Fireworks lists one id with no revision suffix.",
    "Hosts ran one after the other, not at the same time, so speed carries whatever load each had "
    "in its few minutes; four pages were read at once on each.",
    "Cost is tokens times the price in the config (both $1.25 input, $4.25 output per 1M, cached "
    "input billed as ordinary input), not either host's invoice.",
    "Cards and memos are pooled in the agreement figures; a card has 95 values and a memo about "
    "ten, so cards weigh most. 'by_doc_type' separates them.",
]


# --- logging the calls -------------------------------------------------------------------------


class CallLog:
    """An append-only JSONL file shared by the threads of a run."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, entry: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(entry) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]


class TimedLLM:
    """A VisionLLM that logs every call it passes on. The extraction's classify call is the one with
    extract.CLASSIFY_TOKENS as its limit; any other is the read of the page's values."""

    def __init__(self, inner: VisionLLM, log: CallLog, page_of: Mapping[str, str]) -> None:
        self.inner = inner
        self.name, self.model_id = inner.name, inner.model_id
        self._log = log
        self._page_of = page_of  # sha256 of an image -> its page id

    def complete(self, request: LLMRequest) -> LLMResponse:
        digest = hashlib.sha256(request.images[0]).hexdigest()
        entry = {
            "event": "call",
            "host": self.name,
            "page_id": self._page_of.get(digest, digest[:12]),
            "kind": "classify" if request.max_output_tokens == extract.CLASSIFY_TOKENS else "read",
            "second_ask": request.prompt.endswith(extract.RETRY_NOTE),
        }
        started = time.monotonic()
        try:
            response = self.inner.complete(request)
        except BaseException as error:
            self._log.write({**entry, "elapsed_s": _since(started), "error": type(error).__name__})
            raise
        usage = response.usage
        self._log.write(
            {
                **entry,
                "elapsed_s": _since(started),
                "cached": response.cached,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": usage.cost_usd,
            }
        )
        return response


def _since(started: float) -> float:
    return round(time.monotonic() - started, 3)


class _RepairCounter(logging.Handler):
    def __init__(self, log: CallLog, host: str) -> None:
        super().__init__(level=logging.WARNING)
        self._log, self._host = log, host

    def emit(self, record: logging.LogRecord) -> None:
        if REPAIR_WORDS in record.getMessage():
            self._log.write({"event": "repair", "host": self._host})


def _count_retries(backend: Any, log: CallLog, host: str) -> None:
    """A backend sleeps only to retry a 429 or a 5xx, so each sleep is one retry."""
    sleep: Callable[[float], None] = backend._sleep

    def counted(seconds: float) -> None:
        log.write({"event": "retry", "host": host, "waited_s": round(seconds, 3)})
        sleep(seconds)

    backend._sleep = counted


def collect(host: str, config: Path, images: Path, workers: int, scratch: Path = SCRATCH) -> dict:
    """The pages of `images` read on `host` into scratch/runs/<host>, resuming what is there."""
    roles = load_roles(config, cache_dir=scratch / "cache")
    role = roles[extract.ROLE]
    guard = role.inner.guard  # Cache -> Budget -> the guard
    log = CallLog(scratch / f"calls_{host}.jsonl")
    _count_retries(role.inner.inner, log, host)  # Cache -> Budget -> the backend
    handler = _RepairCounter(log, host)
    logging.getLogger("archivist.models.baseten_api").addHandler(handler)
    page_of = {hashlib.sha256(p.read_bytes()).hexdigest(): p.stem for p in images.iterdir()}
    timed = TimedLLM(role, log, page_of)
    spent, started, clock = guard.spent(host), time.strftime("%Y-%m-%dT%H:%M:%S"), time.monotonic()
    pages_before = len(extract.load_predictions(scratch / "runs" / host / "predictions.jsonl"))
    try:
        return extract.run(
            images,
            scratch / "runs" / host,
            {extract.ROLE: timed},
            guard=guard,
            config=describe_config(config),
            doc_types=from_config(config),
            workers=workers,
        )
    finally:
        logging.getLogger("archivist.models.baseten_api").removeHandler(handler)
        done = len(extract.load_predictions(scratch / "runs" / host / "predictions.jsonl"))
        log.write(
            {
                "event": "session",
                "host": host,
                "started_at": started,
                "wall_s": _since(clock),
                "workers": workers,
                "pages_read": done - pages_before,
                "ledger_cost_usd": guard.spent(host) - spent,
            }
        )


# --- the report --------------------------------------------------------------------------------


def sample(pages: Sequence[Path], every: int) -> list[Path]:
    """Every `every`-th page of the sorted split, starting with the first."""
    if every < 1:
        raise ValueError("every must be at least 1")
    return sorted(pages)[::every]


def _percentile(values: Sequence[float], q: float) -> float | None:
    """The nearest-rank q-th percentile (0 < q <= 100) of values, or None where there are none."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


def _spread(values: Sequence[float]) -> dict:
    return {
        "n": len(values),
        "median": round(statistics.median(values), 3) if values else None,
        "p90": round(_percentile(values, 90), 3) if values else None,
        "max": round(max(values), 3) if values else None,
        "total": round(math.fsum(values), 3),
    }


def _of_kind(calls: Sequence[dict], kind: str) -> list[float]:
    return [c["elapsed_s"] for c in calls if c["kind"] == kind]


def _by_doc_type(answered: Sequence[dict], doc_type_of: Mapping[str, str]) -> dict:
    """How the reads of each kind of page went: how long, how many tokens, and so how fast."""
    out = {}
    for doc_type in sorted(set(doc_type_of.values())):
        reads = [
            e for e in answered if e["kind"] == "read" and doc_type_of.get(e["page_id"]) == doc_type
        ]
        tokens = [e["output_tokens"] for e in reads]
        rates = [e["output_tokens"] / max(e["elapsed_s"], 0.001) for e in reads]
        out[doc_type] = {
            "read_call_seconds": _spread([e["elapsed_s"] for e in reads]),
            "read_output_tokens_median": statistics.median(tokens) if reads else None,
            "read_tokens_per_second_median": round(statistics.median(rates), 1) if reads else None,
        }
    return out


def speed_and_cost(
    events: Sequence[dict], pages_asked: int, doc_type_of: Mapping[str, str] | None = None
) -> dict:
    """What the host's log says: calls, failures, retries, how long calls and pages took, tokens,
    cost and throughput; doc_type_of (page id -> its type) adds the reads' speed for each type.
    A cached call is not a measurement of the host and is left out."""
    calls = [e for e in events if e["event"] == "call" and not e.get("cached")]
    answered = [e for e in calls if "error" not in e]
    per_page: Counter = Counter()
    for call in calls:
        per_page[call["page_id"]] += call["elapsed_s"]
    sessions = [e for e in events if e["event"] == "session"]
    wall = math.fsum(s["wall_s"] for s in sessions)
    pages_read = sum(s["pages_read"] for s in sessions)
    cost = math.fsum(s["ledger_cost_usd"] for s in sessions)
    return {
        "calls": len(calls),
        "calls_failed": dict(Counter(e["error"] for e in calls if "error" in e)),
        "second_asks": sum(e["second_ask"] for e in calls),
        "retries": sum(e["event"] == "retry" for e in events),
        "closing_repairs": sum(e["event"] == "repair" for e in events),
        "call_seconds": _spread([e["elapsed_s"] for e in answered]),
        "classify_call_seconds": _spread(_of_kind(answered, "classify")),
        "read_call_seconds": _spread(_of_kind(answered, "read")),
        "page_seconds": _spread(list(per_page.values())),
        "input_tokens": sum(e["input_tokens"] for e in answered),
        "output_tokens": sum(e["output_tokens"] for e in answered),
        "wall_seconds": round(wall, 1),
        "pages_read_per_minute": round(60 * pages_read / wall, 2) if wall else None,
        "cost_usd": round(cost, 6),
        "cost_usd_per_page": round(cost / pages_read, 6) if pages_read else None,
        "pages_asked": pages_asked,
        "by_doc_type": _by_doc_type(answered, doc_type_of or {}),
    }


def _value(prediction: ExtractedValue | None) -> str | None:
    """What the host said for a field, or None if it said nothing or abstained."""
    if prediction is None or prediction.abstained or prediction.value is None:
        return None
    return prediction.value


def _same(field_id: str, first: str | None, second: str | None) -> bool:
    if first is None or second is None:
        return first is None and second is None
    return metrics.normalise(field_id, first) == metrics.normalise(field_id, second)


def field_rows(
    pages: Sequence[PageGT],
    first: Mapping[str, PageExtraction],
    second: Mapping[str, PageExtraction],
) -> list[dict]:
    """One row per ground-truth field of each page both read: the two values, whether they are the
    same, and whether each is right."""
    rows = []
    for page in pages:
        a, b = first.get(page.page_id), second.get(page.page_id)
        if a is None or b is None:
            continue
        by_a, by_b = {v.field_id: v for v in a.values}, {v.field_id: v for v in b.values}
        out_a = {o.field_id: o.outcome for o in metrics.score_page(page, a.values)}
        out_b = {o.field_id: o.outcome for o in metrics.score_page(page, b.values)}
        for field in page.fields:
            fid = field.field_id
            va, vb = _value(by_a.get(fid)), _value(by_b.get(fid))
            rows.append(
                {
                    "page_id": page.page_id,
                    "doc_type": page.doc_type,
                    "field_id": fid,
                    "printed": field.printed,
                    "first": va,
                    "second": vb,
                    "same": _same(fid, va, vb),
                    "first_outcome": out_a[fid],
                    "second_outcome": out_b[fid],
                }
            )
    return rows


def _rate(rows: Sequence[dict]) -> float | None:
    return sum(r["same"] for r in rows) / len(rows) if rows else None


def _bootstrap(rows: Sequence[dict]) -> list[float] | None:
    """A 95% page-bootstrap interval for the share of fields with the same value."""
    by_page: dict[str, list[dict]] = {}
    for row in rows:
        by_page.setdefault(row["page_id"], []).append(row)
    if len(by_page) < 2:
        return None
    pages, rng, rates = list(by_page.values()), random.Random(BOOTSTRAP_SEED), []
    for _ in range(BOOTSTRAP_SAMPLES):
        drawn = [row for page in rng.choices(pages, k=len(pages)) for row in page]
        rates.append(_rate(drawn))
    rates.sort()
    return [rates[int(0.025 * BOOTSTRAP_SAMPLES)], rates[int(0.975 * BOOTSTRAP_SAMPLES) - 1]]


def agreement(rows: Sequence[dict], first: Mapping, second: Mapping) -> dict:
    """How often the two sets of reads give the same value, and who is right when they differ."""

    def counts(part: Sequence[dict]) -> dict:
        same = [r for r in part if r["same"]]
        differ = [r for r in part if not r["same"]]
        right = "correct"
        return {
            "fields": len(part),
            "same_value": len(same),
            "same_value_rate": _rate(part),
            "same_value_rate_ci95": _bootstrap(part),
            "same_and_right": sum(r["first_outcome"] == right for r in same),
            "same_and_wrong": sum(r["first_outcome"] != right for r in same),
            "differ": len(differ),
            "differ_only_first_right": sum(
                r["first_outcome"] == right and r["second_outcome"] != right for r in differ
            ),
            "differ_only_second_right": sum(
                r["second_outcome"] == right and r["first_outcome"] != right for r in differ
            ),
            "differ_neither_right": sum(
                r["first_outcome"] != right and r["second_outcome"] != right for r in differ
            ),
        }

    both = sorted(set(first) & set(second))
    return {
        "pages_in_both": len(both),
        "same_doc_type": sum(first[p].doc_type == second[p].doc_type for p in both),
        **counts(rows),
        "by_doc_type": {
            kind: counts([r for r in rows if r["doc_type"] == kind])
            for kind in sorted({r["doc_type"] for r in rows})
        },
    }


def accuracy(pages: Sequence[PageGT], predictions: Mapping[str, PageExtraction]) -> dict:
    """metrics.summarise over the pages, a page the host did not read counting as omitted."""
    outcomes = []
    for page in pages:
        prediction = predictions.get(page.page_id)
        outcomes += metrics.score_page(page, prediction.values if prediction else [])
    overall = metrics.summarise(outcomes)["overall"]
    return {
        "pages": len(pages),
        "pages_read": sum(page.page_id in predictions for page in pages),
        "fields": overall["n_fields"],
        "counts": overall["counts"],
        "field_accuracy": overall["field_accuracy"],
        "error_rate_accepted": overall["error_rate_accepted"],
    }


def disagreements(rows: Sequence[dict], first: str, second: str) -> list[dict]:
    return [
        {
            "page_id": r["page_id"],
            "field_id": r["field_id"],
            "printed": r["printed"],
            first: r["first"],
            second: r["second"],
            f"{first}_outcome": r["first_outcome"],
            f"{second}_outcome": r["second_outcome"],
        }
        for r in rows
        if not r["same"]
    ]


def build_report(
    pages: Sequence[PageGT],
    predictions: Mapping[str, Mapping[str, PageExtraction]],
    events: Mapping[str, Sequence[dict]],
    noise: Mapping[str, PageExtraction] | None = None,
) -> dict:
    """Everything in results/hosts_compare.json, from the logs, the predictions and the truth."""
    first, second = HOSTS
    doc_types = {page.page_id: page.doc_type for page in pages}
    rows = field_rows(pages, predictions[first], predictions[second])
    report = {
        "what": WHAT,
        "split": SPLIT,
        "pages": [p.page_id for p in pages],
        "hosts": {
            host: {
                "config": HOSTS[host].as_posix(),
                **speed_and_cost(events[host], len(pages), doc_types),
                "accuracy": accuracy(pages, predictions[host]),
            }
            for host in HOSTS
        },
        "agreement": agreement(rows, predictions[first], predictions[second]),
        "disagreements": disagreements(rows, first, second),
        "caveats": CAVEATS,
    }
    if noise is not None:
        noise_rows = field_rows(pages, predictions[first], noise)
        report["noise_floor"] = {
            "what": f"{first} against its own earlier reads, results/runs/{NOISE_RUN}",
            **agreement(noise_rows, predictions[first], noise),
        }
    return report


def _seconds(spread: dict) -> str:
    return f"{spread['median']} / {spread['p90']} / {spread['max']}"


def _typed(figures: dict) -> str:
    spread = figures["read_call_seconds"]
    return f"{spread['median']} / {spread['max']}; {figures['read_tokens_per_second_median']}"


def _rate_of(host: dict) -> str:
    return f"{host['wall_seconds']} / {host['pages_read_per_minute']}"


def _cost_of(host: dict) -> str:
    return f"${host['cost_usd']:.4f} / ${host['cost_usd_per_page']:.4f}"


def _fixed(value: float | None) -> str:
    return "—" if value is None else f"{value:.4f}"  # undefined is not 0


def _summary(label: str, block: dict) -> list[str]:
    low, high = block["same_value_rate_ci95"] or (None, None)
    return [
        f"## {label}",
        f"- {block['pages_in_both']} pages in both, {block['fields']} fields, "
        f"{block['same_value']} the same value = {_fixed(block['same_value_rate'])} "
        f"(95% {_fixed(low)} to {_fixed(high)})",
        f"- same and right {block['same_and_right']}, same and wrong {block['same_and_wrong']}",
        f"- differ {block['differ']}: only the first right {block['differ_only_first_right']}, "
        f"only the second right {block['differ_only_second_right']}, "
        f"neither right {block['differ_neither_right']}",
        "",
    ]


def table(report: dict) -> str:
    """The report as Markdown."""
    hosts = report["hosts"]

    def line(label: str, get: Callable[[dict], object]) -> str:
        return f"| {label} | " + " | ".join(str(get(h)) for h in hosts.values()) + " |"

    rows = [
        "| | " + " | ".join(hosts) + " |",
        "| --- | " + " | ".join("---" for _ in hosts) + " |",
        line("pages read / asked", lambda h: f"{h['accuracy']['pages_read']} / {h['pages_asked']}"),
        line("calls (failed)", lambda h: f"{h['calls']} ({sum(h['calls_failed'].values())})"),
        line("retries (429, 5xx)", lambda h: h["retries"]),
        line("second asks (answer unusable)", lambda h: h["second_asks"]),
        line("closing-bracket repairs", lambda h: h["closing_repairs"]),
        line("call seconds, median / p90 / max", lambda h: _seconds(h["call_seconds"])),
        line("page seconds, median / p90 / max", lambda h: _seconds(h["page_seconds"])),
        line("wall seconds / pages a minute", _rate_of),
        line("tokens in / out", lambda h: f"{h['input_tokens']} / {h['output_tokens']}"),
        line("cost, total / per page", _cost_of),
        line("field accuracy", lambda h: f"{h['accuracy']['field_accuracy']:.4f}"),
    ]
    for doc_type in next(iter(hosts.values()))["by_doc_type"]:
        rows.insert(
            -1,
            line(
                f"{doc_type} read call seconds, median / max; tokens a second",
                lambda h, t=doc_type: _typed(h["by_doc_type"][t]),
            ),
        )
    out = ["# Muse Spark Open on Baseten and on Fireworks", "", report["what"], "", *rows, ""]
    out += _summary("Host against host", report["agreement"])
    if "noise_floor" in report:
        out += _summary("Baseten against its own P13 reads (noise floor)", report["noise_floor"])
    out += ["## Caveats", *(f"- {c}" for c in report["caveats"]), ""]
    return "\n".join(out)


# --- the command -------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--every", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--report-only", action="store_true", help="no model call")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    images = DATA_ROOT / SPLIT / "images"
    split_pages = [p for p in images.iterdir() if p.suffix.lower() in extract.IMAGE_SUFFIXES]
    chosen = sample(split_pages, args.every)
    pages_dir = SCRATCH / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for stale in pages_dir.iterdir():
        stale.unlink()
    for page in chosen:
        shutil.copy(page, pages_dir / page.name)
    ids = {p.stem for p in chosen}

    if not args.report_only:
        for host, config in HOSTS.items():
            print(f"reading {len(chosen)} pages on {host}", flush=True)
            collect(host, config, pages_dir, args.workers)

    truth = [p for p in load_gt(DATA_ROOT / SPLIT / "gt") if p.page_id in ids]
    predictions = {
        host: {
            p.page_id: p
            for p in extract.load_predictions(SCRATCH / "runs" / host / "predictions.jsonl")
        }
        for host in HOSTS
    }
    events = {host: CallLog(SCRATCH / f"calls_{host}.jsonl").read() for host in HOSTS}
    noise_path = extract.RUNS_DIR / NOISE_RUN / "predictions.jsonl"
    noise = None
    if noise_path.exists():
        noise = {p.page_id: p for p in extract.load_predictions(noise_path)}
    report = build_report(truth, predictions, events, noise)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    MD_PATH.write_text(table(report), encoding="utf-8")
    print(table(report))


if __name__ == "__main__":
    main()
