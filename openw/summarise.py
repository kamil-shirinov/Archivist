"""The report's numbers, from the measurement's records. No model, no network.

    uv run python -m openw.summarise    # -> results/openw_measure/summary.json and tables.md

Everything here is arithmetic over calls.jsonl (one line for every call, hits included), the page
reads, the boxes, the draw, the re-reads, the speed runs and the spend ledger.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from archivist.doctypes import from_config
from archivist.models.budget import LEDGER_PATH, BudgetGuard

from openw import analyse
from openw.analyse import median, percentile

ROOT = Path("results/openw_measure")
CONFIG = Path("openw/models.toml")
HOSTS = ("baseten", "fireworks")
# Version 1's size (PREREGISTRATION_REAL.md and its Deviations): 12 pages in each of four families
# and 10 of total claims; their cells are the templates' (700, 840, 420, 102, 837).
HELD_OUT_PAGES = {
    "short_term_foreign_liabilities_as": 12,
    "security_transactions_as_reported_by": 12,
    "outstanding_forward_exchange_contracts": 12,
    "receipts_and_expenditures_under_railroad": 12,
    "total_claims_by_country": 10,
}
V1_PAGES, V1_CELLS, V1_REREADS = 58, 33_114, 29_018
STANDING_CAPS = {"baseten": 80.0, "fireworks": 40.0}  # budget.py's defaults and .env.example's


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(centre - half, 4), round(centre + half, 4)


def mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def spend(calls: Sequence[dict], **where) -> float:
    """What the answered, non-cached calls matching where cost, as the ledger counts it."""
    return sum(
        c["cost_usd"]
        for c in calls
        if not c.get("cache_hit") and "cost_usd" in c and all(c.get(k) == v for k, v in where.items())
    )


def live(calls: Iterable[dict], **where) -> list[dict]:
    return [
        c
        for c in calls
        if not c.get("cache_hit") and all(c.get(k) == v for k, v in where.items())
    ]


# --- Page reads ---------------------------------------------------------------------------------


def page_reads(calls: list[dict], doc_types: dict) -> tuple[list[dict], dict]:
    rows, reads = [], {}
    for host in HOSTS:
        for path in sorted((ROOT / "reads" / host).glob("*.json")) if (ROOT / "reads" / host).is_dir() else []:
            read = json.loads(path.read_text())
            reads[(host, read["ref"])] = read
            mine = live(calls, step="page_read", host=host, page=read["ref"])
            good = [c for c in mine if "error" not in c]
            values = read.get("values", [])
            row = {
                "host": host,
                "page": read["ref"],
                "family": read["family"],
                "ok": read["ok"],
                "seconds": read["seconds"],
                "allowance": read["allowance"],
                "asks": len(mine),
                "failed_asks": sum("error" in c for c in mine),
                "unparseable_asks": sum(c.get("parse_ok") is False for c in good),
                "http_retries": sum(c.get("retries", 0) for c in mine),
                "input_tokens": sum(c.get("input_tokens") or 0 for c in good),
                "cached_input_tokens": sum(c.get("cached_input_tokens") or 0 for c in good),
                "output_tokens": sum(c.get("output_tokens") or 0 for c in good),
                "reasoning_tokens": sum(c.get("reasoning_tokens") or 0 for c in good),
                "cost_usd": round(sum(c["cost_usd"] for c in good), 5),
                "first_ask_cost_usd": round(good[0]["cost_usd"], 5) if good else None,
                "finish_reasons": [c.get("finish_reason") for c in good],
                "brackets_closed": sum(c.get("brackets_closed", 0) for c in good),
                "response_models": sorted({c["response_model"] for c in good if c.get("response_model")}),
                "http_s": [c["http_s"] for c in good],
                "error": read.get("error"),
                "errors": [c["error"]["type"] for c in mine if "error" in c],
                "cells": len(values),
                "abstained": sum(v["abstained"] for v in values),
                "blank": sum((not v["abstained"]) and v["value"] in ("", None) for v in values),
                "boxed": sum(v["citation"] is not None for v in values),
            }
            rows.append(row)
    return rows, reads


def agree_reads(reads: dict, doc_types: dict) -> list[dict]:
    """Page reads of the same page by the two hosts, cell by cell under the template's own
    comparison."""
    out = []
    for ref in sorted({r for _, r in reads}):
        a, b = reads.get((HOSTS[0], ref)), reads.get((HOSTS[1], ref))
        if not (a and b and a["ok"] and b["ok"]):
            continue
        doc_type = doc_types[a["family"]]
        va, vb = {v["field_id"]: v for v in a["values"]}, {v["field_id"]: v for v in b["values"]}
        both = sorted(set(va) & set(vb))
        same = differ = abstain_mismatch = 0
        by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        examples = []
        for f in both:
            x, y = va[f], vb[f]
            if x["abstained"] != y["abstained"]:
                abstain_mismatch += 1
                continue
            if x["abstained"]:
                continue
            kind = doc_type.layout.column(f.rsplit(":", 1)[-1]).kind
            equal = doc_type.canonical(f, x["value"] or "") == doc_type.canonical(f, y["value"] or "")
            same += equal
            differ += not equal
            by_kind[kind][0] += equal
            by_kind[kind][1] += 1
            if not equal and len(examples) < 6:
                examples.append({"cell": f, "baseten": x["value"], "fireworks": y["value"]})
        compared = same + differ
        out.append(
            {
                "page": ref,
                "cells_in_both": len(both),
                "compared": compared,
                "same": same,
                "agreement": round(same / compared, 4) if compared else None,
                "ci95": wilson(same, compared),
                "abstain_mismatch": abstain_mismatch,
                "by_kind": {k: v for k, v in sorted(by_kind.items())},
                "examples": examples,
            }
        )
    return out


# --- Re-reads -----------------------------------------------------------------------------------


def reread_rows(calls: list[dict]) -> dict:
    out: dict = {}
    records = lines(ROOT / "rereads.jsonl")
    for host in HOSTS:
        for effort in sorted({r["effort"] for r in records if r["host"] == host}):
            mine = [r for r in records if r["host"] == host and r["effort"] == effort]
            first = Counter(r["first"]["kind"] for r in mine)
            retried = [r for r in mine if "double" in r]
            fixed = [r for r in retried if r["double"]["kind"] in ("ok", "null")]
            asked = live(calls, step="reread", host=host, effort=effort, attempt="first")
            answered = [c for c in asked if "error" not in c]
            double = live(calls, step="reread", host=host, effort=effort, attempt="double")
            n = len(mine)
            bad = first["empty"] + first["unparseable"]
            out[f"{host}.{effort}"] = {
                "cells": n,
                "kinds": dict(first),
                "empty": first["empty"],
                "empty_rate": round(first["empty"] / n, 4) if n else None,
                "empty_ci95": wilson(first["empty"], n),
                "unparseable": first["unparseable"],
                "errors": first["error"],
                "null_illegible": first["null"],
                "retried_double": len(retried),
                "fixed_by_double": len(fixed),
                "still_bad_after_double": len(retried) - len(fixed),
                "final_bad_rate": round((len(retried) - len(fixed) + first["error"]) / n, 4) if n else None,
                "bad_first_rate": round((bad + first["error"]) / n, 4) if n else None,
                "output_tokens_median": median(c["output_tokens"] for c in answered),
                "output_tokens_mean": round(mean(c["output_tokens"] for c in answered) or 0, 1),
                "output_tokens_p90": percentile([c["output_tokens"] for c in answered], 0.9),
                "reasoning_tokens_median": median(c["reasoning_tokens"] for c in answered if c.get("reasoning_tokens") is not None),
                "input_tokens_median": median(c["input_tokens"] for c in answered),
                "cached_input_median": median(c.get("cached_input_tokens") or 0 for c in answered),
                "finish_reasons": dict(Counter(c.get("finish_reason") for c in answered)),
                "cost_first_mean": round(mean(c["cost_usd"] for c in answered) or 0, 6),
                "cost_first_total": round(sum(c["cost_usd"] for c in answered), 5),
                "cost_double_total": round(sum(c["cost_usd"] for c in double if "error" not in c), 5),
                "cost_per_cell_incl_retry": round(
                    (sum(c["cost_usd"] for c in answered) + sum(c["cost_usd"] for c in double if "error" not in c)) / n, 6
                )
                if n
                else None,
                "http_s_median": median(c["http_s"] for c in answered),
                "http_s_p90": percentile([c["http_s"] for c in answered], 0.9),
                "http_s_max": max((c["http_s"] for c in answered), default=None),
                "http_retries": sum(c.get("retries", 0) for c in asked),
                "d28_repairs": sum(c.get("brackets_closed", 0) for c in answered),
                "fences_removed": sum(bool(c.get("fence_removed")) for c in answered),
                "error_types": dict(Counter(c["error"]["type"] for c in asked + double if "error" in c)),
                "response_models": sorted({c["response_model"] for c in answered if c.get("response_model")}),
            }
    return out


def reread_agreement(doc_types: dict, reads: dict) -> dict:
    """Same value between the hosts' re-reads of the same crop, and between a re-read and a page
    read, under the template's own comparison. A re-read that gave no value is left out."""
    records = lines(ROOT / "rereads.jsonl")
    draw = json.loads((ROOT / "draw.json").read_text()) if (ROOT / "draw.json").exists() else {"pages": {}}
    family_of = {r["ref"]: r["family"] for r in reads.values()}
    value = {}
    for r in records:
        final = r["first"] if r["first"]["kind"] in ("ok", "null") else r.get("double", r["first"])
        value[(r["host"], r["effort"], r["cell"])] = (r["ref"], final)
    out: dict = {}
    efforts = sorted({e for _, e, _ in value})
    for effort in efforts:
        a = {c: v for (h, e, c), v in value.items() if h == HOSTS[0] and e == effort}
        b = {c: v for (h, e, c), v in value.items() if h == HOSTS[1] and e == effort}
        same = differ = one_empty = 0
        examples = []
        for cell in sorted(set(a) & set(b)):
            (ref, x), (_, y) = a[cell], b[cell]
            if x["kind"] != "ok" or y["kind"] != "ok":
                one_empty += 1
                continue
            doc_type = doc_types[family_of[ref]]
            equal = doc_type.canonical(cell, x["value"]) == doc_type.canonical(cell, y["value"])
            same += equal
            differ += not equal
            if not equal and len(examples) < 8:
                examples.append({"cell": cell, "baseten": x["value"], "fireworks": y["value"]})
        out[f"hosts@{effort}"] = {
            "both_gave_a_value": same + differ,
            "same": same,
            "differ": differ,
            "agreement": round(same / (same + differ), 4) if same + differ else None,
            "ci95": wilson(same, same + differ),
            "at_least_one_gave_none": one_empty,
            "examples": examples,
        }
        for host in HOSTS:
            mine = {c: v for (h, e, c), v in value.items() if h == host and e == effort}
            for reader in HOSTS:
                same = differ = 0
                for cell, (ref, y) in mine.items():
                    read = reads.get((reader, ref))
                    if y["kind"] != "ok" or not read or not read["ok"]:
                        continue
                    first = next((v for v in read["values"] if v["field_id"] == cell), None)
                    if first is None or first["abstained"]:
                        continue
                    doc_type = doc_types[family_of[ref]]
                    equal = doc_type.canonical(cell, y["value"]) == doc_type.canonical(cell, first["value"] or "")
                    same += equal
                    differ += not equal
                out[f"{host}.{effort} re-read vs {reader}'s page read"] = {
                    "compared": same + differ,
                    "same": same,
                    "agreement": round(same / (same + differ), 4) if same + differ else None,
                    "ci95": wilson(same, same + differ),
                }
    return out


# --- Speed --------------------------------------------------------------------------------------


def speed_rows(calls: list[dict]) -> list[dict]:
    """Each speed run, over its live calls only: a cell whose crop and prompt another cell of the
    run had already sent is answered from the cache, costs nothing and takes no time."""
    path = ROOT / "speed.json"
    if not path.exists():
        return []
    out = []
    for run in json.loads(path.read_text())["runs"]:
        mine = [c for c in calls if c.get("step") == f"speed{run['level']}" and c["host"] == run["host"]]
        fresh = [c for c in mine if not c.get("cache_hit")]
        good = [c for c in fresh if "error" not in c]
        overhead = [c["wall_s"] - c["http_s"] for c in good]
        walls = [c["wall_s"] for c in fresh]
        out.append(
            {
                "host": run["host"],
                "effort": run["effort"],
                "at_once": run["level"],
                "cells": run["cells"],
                "live_calls": len(fresh),
                "cache_hits": run["cache_hits"],
                "wall_s": run["wall_s"],
                "calls_per_s": round(len(fresh) / run["wall_s"], 3),
                "call_s_median": median(walls),
                "call_s_p90": percentile(walls, 0.9),
                "call_s_max": max(walls, default=None),
                "kinds": run["kinds"],
                "http_retries": sum(c.get("retries", 0) for c in fresh),
                "errors": dict(Counter(c["error"]["type"] for c in fresh if "error" in c)),
                "layer_overhead_s_mean": round(mean(overhead) or 0, 3),
                "layer_overhead_s_max": round(max(overhead, default=0), 3),
                "ledger_parse_s": run["ledger_parse_s"],
                "output_tokens_mean": round(mean(c["output_tokens"] for c in good) or 0, 1),
                "cost_per_call": round(mean(c["cost_usd"] for c in good) or 0, 6),
                "valid": True,
            }
        )
    return out


# --- Where the model's own boxes lie ------------------------------------------------------------


def box_offsets(reads: dict) -> list[dict]:
    """For each page read, the model's box against the PDF's own text layer, on the cells whose
    digits occur exactly once in the layer (so the match is not a guess): dx and dy of the box's
    centre from the word's, in pixels of the stored page. Also the box sources the Baseten read
    gave (the crops' source) beside the committed evidence's anchored count for the same page, from
    the Spark 1.3 test those templates were approved on. Development pages only; plain code."""
    from PIL import Image

    from archivist.templates import real_test

    evidence = {}
    for family in HELD_OUT_PAGES:
        record = json.loads((Path("templates") / f"{family}.evidence.json").read_text())
        for page in record["pages"]:
            evidence[page["ref"]] = (page["anchored"], page["cells"], record["citations"])
    out = []
    for (host, ref), read in sorted(reads.items()):
        if not read["ok"]:
            continue
        page = real_test.resolve(ref, "development")
        layer = real_test.words(page)
        width, height = Image.open(page.path).size
        by: dict[str, list] = defaultdict(list)
        for w in layer:
            if len(w.digits) >= 3:
                by[w.digits].append(w)
        dx, dy = [], []
        for v in read["values"]:
            if v["abstained"] or not v["value"] or v["citation"] is None:
                continue
            digits = "".join(ch for ch in v["value"] if ch.isdigit())
            if len(digits) < 3 or len(by.get(digits, [])) != 1:
                continue
            w, b = by[digits][0], v["citation"]["bbox"]
            dx.append((b["x0"] + b["x1"]) / 2 - (w.box.x0 + w.box.x1) / 2)
            dy.append((b["y0"] + b["y1"]) / 2 - (w.box.y0 + w.box.y1) / 2)
        row = {"host": host, "page": ref, "page_px": [width, height], "matched_cells": len(dx)}
        if len(dx) >= 8:
            qx, qy = statistics_quartiles(dx), statistics_quartiles(dy)
            row |= {
                "dx_median": round(qx[1]),
                "dx_iqr": [round(qx[0]), round(qx[2])],
                "dy_median": round(qy[1]),
                "dy_iqr": [round(qy[0]), round(qy[2])],
                "dy_median_share_of_page_height": round(qy[1] / height, 3),
                "within_25px_in_y": sum(abs(d) <= 25 for d in dy),
            }
        boxes = ROOT / "boxes" / f"{ref}.json"
        if host == "baseten" and boxes.exists():
            sources = Counter(c["source"] for c in json.loads(boxes.read_text())["cells"].values())
            row["box_sources_of_eligible_cells"] = dict(sources)
            row["committed_evidence_anchored"] = {"anchored": evidence[ref][0], "cells": evidence[ref][1], "strategy": evidence[ref][2]}
        out.append(row)
    return out


def statistics_quartiles(values: list[float]) -> tuple[float, float, float]:
    import statistics

    q = statistics.quantiles(values, n=4)
    return q[0], q[1], q[2]


# --- The estimate -------------------------------------------------------------------------------


def cell_costs(calls: list[dict], host: str, effort: str, family_of: dict[str, str]) -> dict[str, list[float]]:
    """For each family's measured page, what each cell's re-read cost: the first ask and, where it
    was empty, the retry at double the allowance. A call that returned nothing (a timeout) has no
    cost in the ledger, so none here."""
    records = [r for r in lines(ROOT / "rereads.jsonl") if r["host"] == host and r["effort"] == effort]
    cost: dict[str, float] = defaultdict(float)
    for c in live(calls, step="reread", host=host, effort=effort):
        if "error" not in c:
            cost[c["cell"]] += c["cost_usd"]
    out: dict[str, list[float]] = defaultdict(list)
    for r in records:
        out[family_of[r["ref"]]].append(cost.get(r["cell"], 0.0))
    return out


def weighted(per_family: dict[str, list[float]]) -> float:
    weights = {f: HELD_OUT_PAGES[f] * CELLS[f] for f in HELD_OUT_PAGES}
    total = sum(weights.values())
    return sum(weights[f] / total * (sum(v) / len(v)) for f, v in per_family.items())


def bootstrap(per_family: dict[str, list[float]], draws: int = 2000) -> tuple[float, float]:
    """95% percentile interval of the held-out-mix mean, cells resampled with replacement within
    each family's page (the project's bootstrap: numpy.random.default_rng(0))."""
    import numpy as np

    rng = np.random.default_rng(0)
    values = {f: np.array(v) for f, v in per_family.items()}
    means = []
    for _ in range(draws):
        means.append(
            weighted({f: list(rng.choice(v, size=len(v), replace=True)) for f, v in values.items()})
        )
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def page_part(pages: list[dict], host: str) -> dict:
    """Page reads for version 1's 58 pages from one measured page a family. Cost is tokens times
    one price on both hosts, and the same pages' tokens agree between hosts, so a read the host
    never returned takes the other host's cost (flagged); its time is a floor, the time it was
    stopped at."""
    other = HOSTS[1 - HOSTS.index(host)]
    mine = {p["family"]: p for p in pages if p["host"] == host and p["ok"]}
    theirs = {p["family"]: p for p in pages if p["host"] == other and p["ok"]}
    cost_first, cost_all, seconds, substituted = {}, {}, {}, []
    for f in HELD_OUT_PAGES:
        if f in mine:
            cost_first[f], cost_all[f], seconds[f] = mine[f]["first_ask_cost_usd"], mine[f]["cost_usd"], mine[f]["seconds"]
        elif f in theirs:
            failed = next(p for p in pages if p["host"] == host and p["family"] == f)
            cost_first[f], cost_all[f], seconds[f] = theirs[f]["first_ask_cost_usd"], theirs[f]["cost_usd"], failed["seconds"]
            substituted.append(f)
        else:
            return {"incomplete": [f]}
    first = sum(HELD_OUT_PAGES[f] * cost_first[f] for f in HELD_OUT_PAGES)
    measured = sum(HELD_OUT_PAGES[f] * cost_all[f] for f in HELD_OUT_PAGES)
    total_s = sum(HELD_OUT_PAGES[f] * seconds[f] for f in HELD_OUT_PAGES)
    longest = max(seconds.values())
    return {
        "cost_low": round(first, 2),
        "cost_mid": round(measured, 2),
        "cost_high": round(max(measured, 2 * first), 2),  # every page asked twice, as _ask allows
        "hours_low": round(max(total_s / 8, longest) / 3600, 2),  # eight pages at once, as v1 ran
        "hours_high": round(max(total_s / 4, longest) / 3600, 2),
        "substituted_families": substituted,
        "time_is_a_floor": bool(substituted),
    }


def reread_part(calls: list[dict], speed: list[dict], host: str, family_of: dict[str, str]) -> dict:
    per_family = cell_costs(calls, host, "low", family_of)
    if len(per_family) < len(HELD_OUT_PAGES):
        return {"incomplete": sorted(set(HELD_OUT_PAGES) - set(per_family))}
    mid = weighted(per_family)
    low, high = bootstrap(per_family)
    pooled = sum(sum(v) for v in per_family.values()) / sum(len(v) for v in per_family.values())
    runs = {s["at_once"]: s["calls_per_s"] for s in speed if s["host"] == host and s["valid"]}
    out = {
        "usd_per_reread_weighted": round(mid, 6),
        "usd_per_reread_pooled_200": round(pooled, 6),
        "usd_per_reread_ci95": [round(low, 6), round(high, 6)],
        "cost_low": round(V1_REREADS * low, 2),
        "cost_mid": round(V1_REREADS * mid, 2),
        "cost_high": round(V1_REREADS * high, 2),
        "calls_per_s": runs,
    }
    if 8 in runs and 4 in runs:
        out["hours_low"] = round(V1_REREADS / runs[8] / 3600, 2)
        out["hours_high"] = round(V1_REREADS / runs[4] / 3600, 2)
    return out


CELLS = {
    "short_term_foreign_liabilities_as": 700,
    "security_transactions_as_reported_by": 840,
    "outstanding_forward_exchange_contracts": 420,
    "receipts_and_expenditures_under_railroad": 102,
    "total_claims_by_country": 837,
}


def estimate(
    pages: list[dict], calls: list[dict], speed: list[dict], remaining: dict[str, float]
) -> dict:
    """The full run at version 1's size (58 pages, 33,114 cells read, 29,018 blind re-reads): each
    host alone and the two splits, cost and time as ranges, against each host's remaining cap."""
    family_of = {p["page"]: p["family"] for p in pages}
    reads = {h: page_part(pages, h) for h in HOSTS}
    rereads = {h: reread_part(calls, speed, h, family_of) for h in HOSTS}
    scenarios = {}
    for name, (page_host, reread_host) in {
        "all Baseten": ("baseten", "baseten"),
        "all Fireworks": ("fireworks", "fireworks"),
        "page reads Baseten, re-reads Fireworks": ("baseten", "fireworks"),
        "page reads Fireworks, re-reads Baseten": ("fireworks", "baseten"),
    }.items():
        a, b = reads[page_host], rereads[reread_host]
        if "incomplete" in a or "incomplete" in b or "hours_low" not in b:
            scenarios[name] = {"incomplete": [a.get("incomplete"), b.get("incomplete")]}
            continue
        need: dict[tuple[str, str], float] = defaultdict(float)
        for tag in ("low", "mid", "high"):
            need[page_host, tag] += a[f"cost_{tag}"]
            need[reread_host, tag] += b[f"cost_{tag}"]
        hosts = sorted({page_host, reread_host})
        scenarios[name] = {
            "cost": [round(a["cost_low"] + b["cost_low"], 2), round(a["cost_mid"] + b["cost_mid"], 2), round(a["cost_high"] + b["cost_high"], 2)],
            "hours": [round(a["hours_low"] + b["hours_low"], 2), round(a["hours_high"] + b["hours_high"], 2)],
            "page_reads": {"host": page_host, "cost": [a["cost_low"], a["cost_mid"], a["cost_high"]], "hours": [a["hours_low"], a["hours_high"]], "time_is_a_floor": a["time_is_a_floor"]},
            "rereads": {"host": reread_host, "cost": [b["cost_low"], b["cost_mid"], b["cost_high"]], "hours": [b["hours_low"], b["hours_high"]]},
            "needs_by_host": {h: {"low": round(need[h, "low"], 2), "mid": round(need[h, "mid"], 2), "high": round(need[h, "high"], 2), "remaining_cap": remaining[h]} for h in hosts},
            "fits_at_low": all(need[h, "low"] <= remaining[h] for h in hosts),
            "fits_at_mid": all(need[h, "mid"] <= remaining[h] for h in hosts),
            "fits_at_high": all(need[h, "high"] <= remaining[h] for h in hosts),
        }
    return {"page_reads": reads, "rereads": rereads, "scenarios": scenarios, "remaining": remaining}


def remaining_caps() -> dict[str, float]:
    guard = BudgetGuard(0.0, LEDGER_PATH)
    return {h: round(STANDING_CAPS[h] - guard.spent(h), 2) for h in HOSTS}


def main() -> None:
    calls = lines(ROOT / "calls.jsonl")
    doc_types = from_config(CONFIG)
    pages, reads = page_reads(calls, doc_types)
    rereads = reread_rows(calls)
    speed = speed_rows(calls)
    caps = json.loads((ROOT / "caps.json").read_text())
    guard = BudgetGuard(0.0, LEDGER_PATH)
    summary = {
        "probe": json.loads((ROOT / "probe.json").read_text())["hosts"],
        "page_reads": pages,
        "page_read_agreement": agree_reads(reads, doc_types),
        "rereads": rereads,
        "reread_agreement": reread_agreement(doc_types, reads) if (ROOT / "rereads.jsonl").exists() else {},
        "speed": speed,
        "box_offsets": box_offsets(reads),
        "spend_since_start": {
            h: round(guard.spent(h) - caps["spent_at_start"][h], 4) for h in HOSTS
        },
        "recorded_cost_by_host": {h: round(spend(calls, host=h), 4) for h in HOSTS},
        "calls": {
            "total_records": len(calls),
            "cache_hits": sum(bool(c.get("cache_hit")) for c in calls),
            "errors": dict(Counter((c["host"], c["error"]["type"]) .__repr__() for c in calls if "error" in c)),
        },
        "remaining_caps": remaining_caps(),
    }
    summary["estimate"] = estimate(pages, calls, speed, summary["remaining_caps"])
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("spend_since_start", "recorded_cost_by_host", "calls", "remaining_caps")}, indent=1))


if __name__ == "__main__":
    main()
