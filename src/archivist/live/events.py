"""The event stream of a live read: one event per step and per model call (P35).

An EventLog is the record of one read, append-only and safe to follow from several threads (the
server streams it). Events are plain dicts: seq (their place), t (seconds since the read began) and
type, with these types:

    session     the page, the mode ("live" or "replay"), the arm and the models of each role
    step        one of the seven steps (STEPS) starting or finishing, in the pipeline's order
    call_start  a model call has been asked: id, role, model, step
    call        it was answered (or failed): model, role, step, source ("live" or "cache"), latency,
                tokens, cost (what this read spent on it: nothing for a cache hit)
    values      the values read, with the boxes they were cited at
    detections  stamps and stains SAM 3.1 found
    verdicts    each value's decision
    done / error  how the read ended; the stream is closed after one of them

Observed wraps a role that load_roles() built, outermost: Observed(Cache(Budget(Backend))). It asks
the wrapped role the very same request and returns the very same answer, so the cache, the spend
cap and the ledger apply exactly as for any other run (D5, D8, D18); all it adds is the event. It
never makes a call of its own and is never given a key.

A cache hit carries no latency of its own. A live call's latency is therefore kept, by the cache
key of the request, in a LatencyLog beside the read's other scratch files, and a replay (Replay)
plays each hit at the pace its original took, or faster by a factor; a hit whose original was never
timed is played at NOMINAL_S and says so.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from archivist.export.bundle import model_name
from archivist.models.budget import BudgetExceeded
from archivist.models.cache import cache_key

STEPS = ("recognise", "read", "snap", "sam", "blind", "rules", "decide")
# The role whose model does each step, None where plain code does.
STEP_ROLE = {
    "recognise": "extractor",
    "read": "extractor",
    "snap": None,
    "sam": "segmenter",
    "blind": "rereader",
    "rules": None,
    "decide": None,
}
# Seconds a replayed call is played for when its original was never timed: stand-ins for a
# rehearsal, marked as such in the call's event ("pace": "nominal").
NOMINAL_S = {"extractor": 4.0, "rereader": 1.2, "segmenter": 1.5}
KEY_VARIABLES = ("META_API_KEY", "BASETEN_API_KEY", "FIREWORKS_API_KEY")


class Cancelled(BudgetExceeded):
    """The read was stopped. It is a BudgetExceeded so that the pipeline, which re-raises that one
    and nothing else out of a worker, stops at once instead of counting each call as a failed one.
    """


def redact(text: str) -> str:
    """text without the value of any API key in this process's environment."""
    for variable in KEY_VARIABLES:
        secret = os.environ.get(variable, "").strip()
        if len(secret) >= 8:
            text = text.replace(secret, "[key]")
    return text


class EventLog:
    def __init__(
        self,
        session_id: str,
        *,
        clock: Callable[[], float] = time.monotonic,
        sink: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.cancelled = threading.Event()
        self._clock, self._t0 = clock, clock()
        self._events: list[dict] = []
        self._cond = threading.Condition()
        self._closed = False
        self._sink = sink
        if sink is not None:
            sink.parent.mkdir(parents=True, exist_ok=True)
            sink.write_text("", encoding="utf-8")

    def emit(self, type: str, **fields: object) -> dict:
        with self._cond:
            event = {
                "seq": len(self._events),
                "t": round(self._clock() - self._t0, 3),
                "type": type,
                **fields,
            }
            self._events.append(event)
            if self._sink is not None:
                with self._sink.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(event) + "\n")
            self._cond.notify_all()
            return event

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        return self._closed

    def events(self) -> list[dict]:
        with self._cond:
            return list(self._events)

    def since(self, after: int, timeout: float = 15.0) -> tuple[list[dict], bool]:
        """The events after seq `after`, waiting up to `timeout` seconds for one; and whether the
        log is closed with nothing left to give."""
        with self._cond:
            self._cond.wait_for(lambda: len(self._events) > after + 1 or self._closed, timeout)
            fresh = self._events[after + 1 :]
            return fresh, self._closed and not fresh


class LatencyLog:
    """How long each live call took, by cache key, for a replay to play at the same pace."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._ms: dict[str, float] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                    self._ms[entry["key"]] = float(entry["ms"])
                except (ValueError, KeyError, TypeError):
                    continue  # a torn line: that call is simply untimed

    def get(self, key: str) -> float | None:
        return self._ms.get(key)

    def record(self, key: str, ms: float, role: str) -> None:
        with self._lock:
            self._ms[key] = ms
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as out:
                out.write(json.dumps({"key": key, "ms": round(ms, 1), "role": role}) + "\n")


class Steps:
    """Which of the seven steps is under way. A step starts when the flow says so or when the first
    call of a role the flow has routed to it is asked; starting one finishes any other still open,
    so the steps light up in the order the pipeline takes them. What a step found is told when the
    flow knows it, which for a step already finished is a "facts" event."""

    def __init__(self, log: EventLog, names: Mapping[str, str]) -> None:
        self._log = log
        self._names = dict(names)  # role -> the model's name
        self._route: dict[str, str] = {}
        self._open: list[str] = []
        self._finished: set[str] = set()
        self._lock = threading.Lock()

    def route(self, mapping: Mapping[str, str]) -> None:
        """From now on, a call by this role belongs to this step."""
        self._route = dict(mapping)

    def on_call(self, role: str) -> str | None:
        step = self._route.get(role)
        if step is not None:
            self.start(step)
        return step

    @property
    def current(self) -> str | None:
        return self._open[-1] if self._open else None

    def start(self, step: str) -> None:
        with self._lock:
            if step in self._open or step in self._finished:
                return
            self._close_others(step)
            self._open.append(step)
            self._emit(step, "start", {})

    def finish(self, step: str, **facts: object) -> None:
        with self._lock:
            if step in self._finished:
                return self._emit(step, "facts", facts)
            if step not in self._open:
                self._close_others(step)
                self._emit(step, "start", {})
            else:
                self._open.remove(step)
            self._finished.add(step)
            self._emit(step, "done", facts)

    def close(self) -> None:
        with self._lock:
            self._close_others(None)

    def _close_others(self, keep: str | None) -> None:
        for other in [s for s in self._open if s != keep]:
            self._open.remove(other)
            self._finished.add(other)
            self._emit(other, "done", {})

    def _emit(self, step: str, state: str, facts: Mapping[str, object]) -> None:
        role = STEP_ROLE[step]
        self._log.emit(
            "step",
            step=step,
            state=state,
            index=STEPS.index(step),
            model=self._names.get(role) if role else None,
            facts=dict(facts),
        )


class Recorder:
    """What one read shares: its log, its steps, how calls are timed and what they add up to."""

    def __init__(
        self,
        log: EventLog,
        steps: Steps,
        latency: LatencyLog,
        *,
        mode: str,
        speed: float = 1.0,
    ) -> None:
        if mode not in ("live", "replay"):
            raise ValueError(f"mode must be 'live' or 'replay', not {mode!r}")
        self.log, self.steps, self.latency, self.mode = log, steps, latency, mode
        self.speed = max(speed, 0.1)
        self._lock = threading.Lock()
        self._next = 0
        self.totals = {"calls": 0, "live": 0, "cache": 0, "failed": 0, "cost_usd": 0.0}
        self.cost_by_step: dict[str, float] = {}
        self.live_seconds = 0.0

    def next_id(self) -> int:
        with self._lock:
            self._next += 1
            return self._next

    def add(
        self, step: str | None, source: str | None, ok: bool, cost: float, seconds: float
    ) -> None:
        with self._lock:
            self.totals["calls"] += 1
            self.totals["failed"] += not ok
            if ok:
                self.totals[source] += 1
            self.totals["cost_usd"] = round(self.totals["cost_usd"] + cost, 6)
            self.cost_by_step[step or "?"] = self.cost_by_step.get(step or "?", 0.0) + cost
            if source == "live":
                self.live_seconds += seconds


class Observed:
    """A role that says what it is asked and what it answers, and changes neither."""

    def __init__(self, inner: object, role: str, recorder: Recorder) -> None:
        self.inner, self.role, self._rec = inner, role, recorder
        self.name = inner.name
        self.model_id = inner.model_id

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)

    def complete(self, request: object) -> object:
        return self._call(request, self.inner.complete, "llm")

    def segment(self, request: object) -> object:
        return self._call(request, self.inner.segment, "segmenter")

    def _call(self, request: object, ask: Callable, kind: str) -> object:
        rec = self._rec
        if rec.log.cancelled.is_set():
            raise Cancelled("stopped")
        step = rec.steps.on_call(self.role)
        call_id = rec.next_id()
        key = cache_key(
            self.inner.name, self.inner.model_id, request, getattr(self.inner, "settings", None)
        )
        who = {
            "id": call_id,
            "role": self.role,
            "step": step,
            "model": model_name(self.model_id),
            "model_id": self.model_id,
            "backend": self.name,
            "detail": ", ".join(request.prompts) if kind == "segmenter" else None,
        }
        rec.log.emit("call_start", **who)
        began = time.perf_counter()
        try:
            response = ask(request)
        except BaseException as error:
            seconds = time.perf_counter() - began
            rec.add(step, None, False, 0.0, seconds)
            rec.log.emit(
                "call",
                **who,
                ok=False,
                source=None,
                latency_ms=round(seconds * 1000, 1),
                latency_of="measured",
                error=redact(f"{type(error).__name__}: {error}")[:300],
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                cost_full_usd=0.0,
            )
            raise
        measured = time.perf_counter() - began
        source = "cache" if response.cached else "live"
        recorded = rec.latency.get(key)
        pace = "measured"
        if source == "live":
            rec.latency.record(key, measured * 1000, self.role)
            shown = measured * 1000
        else:
            if rec.mode == "replay":
                pace = "recorded" if recorded is not None else "nominal"
                shown = recorded if recorded is not None else None
                seconds = (recorded / 1000 if recorded is not None else NOMINAL_S[self.role])
                rec.log.cancelled.wait(seconds / rec.speed)
                if rec.log.cancelled.is_set():
                    raise Cancelled("stopped")
            else:
                pace = "recorded" if recorded is not None else "none"
                shown = recorded
        if rec.mode == "replay" and source == "live":
            raise RuntimeError(f"a replay reached {self.name}: the call is not in the cache")
        usage = response.usage
        cost = usage.cost_usd if source == "live" else 0.0
        rec.add(step, source, True, cost, measured)
        if kind == "segmenter":
            rec.log.emit(
                "detections",
                call=call_id,
                prompt=request.prompts[0],
                regions=[
                    {"label": r.label, "box": r.bbox.model_dump(), "score": round(r.score, 3)}
                    for r in response.regions
                ],
            )
        rec.log.emit(
            "call",
            **who,
            ok=True,
            source=source,
            latency_ms=None if shown is None else round(shown, 1),
            latency_of="measured" if source == "live" else pace,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=round(cost, 6),
            cost_full_usd=round(usage.cost_usd, 6),
        )
        return response
