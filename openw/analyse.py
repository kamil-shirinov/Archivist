"""Pure functions over the measurement's records (calls.jsonl and the files beside it): no model,
no network, nothing read but what is passed in. The rules here are fixed before any probe call:

* An effort is ACCEPTED on a host if at least one probe call at it got an answer, and REFUSED if
  every one came back as an HTTP 4xx. (An API that takes a value and silently runs it as another
  is accepted, not honoured.)
* An effort is HONOURED if it spends less than "low" on the same cells: on at least HONOUR_CELLS
  of the cells where both answered, fewer reasoning tokens (or, where the host reports none,
  fewer output tokens), and the median ratio to "low" at most HONOUR_RATIO.
* The setting the re-reads use on a host: "minimal" if honoured (version 1's setting), else "none"
  if honoured, else "low".
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

HONOUR_CELLS = 3  # of the 4 probe cells
HONOUR_RATIO = 0.7
EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh")


def median(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.median(values) if values else None


def percentile(values: Sequence[float], share: float) -> float | None:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(share * len(ordered) + 0.5) - 1))]


def spent_tokens(call: Mapping) -> int | None:
    """What a call spent thinking: the host's reasoning-token count, else its output tokens."""
    value = call.get("reasoning_tokens")
    return value if isinstance(value, int) else call.get("output_tokens")


def _by_cell(calls: Iterable[Mapping]) -> dict[tuple[str, str, str], Mapping]:
    """The first answered probe call of each (host, effort, cell)."""
    out: dict[tuple[str, str, str], Mapping] = {}
    for call in calls:
        if call.get("step") != "probe" or call.get("cache_hit") or "error" in call:
            continue
        out.setdefault((call["host"], call["effort"], call["cell"]), call)
    return out


def probe_summary(calls: Sequence[Mapping]) -> dict:
    """Per host and effort: accepted, honoured, and the numbers behind them."""
    answered = _by_cell(calls)
    errors: dict[tuple[str, str], list[Mapping]] = defaultdict(list)
    other: dict[tuple[str, str], list[Mapping]] = defaultdict(list)
    for call in calls:
        if call.get("step") == "probe" and "error" in call:
            status = call["error"].get("status")
            refused = isinstance(status, int) and 400 <= status < 500
            (errors if refused else other)[(call["host"], call["effort"])].append(call)
    hosts = sorted({h for h, _, _ in answered} | {h for h, _ in errors})
    out: dict = {}
    for host in hosts:
        efforts = sorted(
            {e for h, e, _ in answered if h == host}
            | {e for h, e in errors if h == host}
            | {e for h, e in other if h == host},
            key=lambda e: EFFORT_ORDER.index(e) if e in EFFORT_ORDER else len(EFFORT_ORDER),
        )
        low = {c: call for (h, e, c), call in answered.items() if h == host and e == "low"}
        rows = {}
        for effort in efforts:
            mine = {c: call for (h, e, c), call in answered.items() if h == host and e == effort}
            failed = errors.get((host, effort), [])
            statuses = sorted({str(f["error"].get("status")) for f in failed})
            timeouts = [f["error"]["type"] for f in other.get((host, effort), [])]
            paired = [
                (spent_tokens(mine[c]), spent_tokens(low[c]))
                for c in sorted(mine)
                if c in low and spent_tokens(mine[c]) is not None and spent_tokens(low[c])
            ]
            fewer = sum(a < b for a, b in paired)
            ratio = median(a / b for a, b in paired)
            rows[effort] = {
                "answered": len(mine),
                "refused": len(failed),
                "refused_statuses": statuses,
                "other_errors": timeouts,
                "accepted": bool(mine),
                "reasoning_tokens_median": median(
                    c["reasoning_tokens"] for c in mine.values() if c.get("reasoning_tokens") is not None
                ),
                "output_tokens_median": median(c["output_tokens"] for c in mine.values()),
                "reasoning_reported": all(c.get("reasoning_tokens") is not None for c in mine.values())
                if mine
                else None,
                "empty": sum(bool(c.get("empty")) for c in mine.values()),
                "finish_length": sum(c.get("finish_reason") == "length" for c in mine.values()),
                "paired_with_low": len(paired),
                "fewer_than_low": fewer,
                "median_ratio_to_low": ratio,
                "honoured": effort == "low"
                or (len(paired) >= HONOUR_CELLS and fewer >= HONOUR_CELLS and ratio <= HONOUR_RATIO),
            }
        out[host] = {"efforts": rows, "reread_effort": choose_effort(rows)}
    return out


def choose_effort(rows: Mapping[str, Mapping]) -> str:
    """The setting re-reads use: "minimal" if honoured, else "none" if honoured, else "low"."""
    for effort in ("minimal", "none"):
        if rows.get(effort, {}).get("honoured"):
            return effort
    return "low"
