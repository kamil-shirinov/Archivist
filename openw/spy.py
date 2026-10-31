"""Recording for the P33 measurement: what each call cost, how long it took and how it ended.

The committed backends (baseten_api.py, fireworks_api.py) return a text and a usage and nothing
else: no finish reason, no reasoning-token count, no cached-input count, no model id from the
response, no wall time, no record of a retry. Three small pieces add them without editing
anything committed, and every call still goes registry -> cache -> budget -> backend:

* SpyClient stands in for the OpenAI client of a backend. It forwards chat.completions.create
  unchanged (payload, schema in the prompt, repairs: the backend's) and notes each HTTP attempt.
  It also sets the timeout, which the committed backends fix at 60 s: version 1's extractor had
  1200 s (config/real_test.toml), and a whole table does not come back in 60.
* OpenwBaseten and OpenwFireworks are the committed backends with that client, plus one change:
  their constructors refuse "none" and "minimal", and a measurement of whether those are honoured
  has to send them. The shim builds the backend at "low" and then sets the effort it was given;
  build_payload, the answer's repairs and the cost are the committed code's. Their name is the
  committed backend's, so the ledger lines, the caps and the cache keys are the committed ones.
* Recorder is a role's outermost layer. It times the whole call (cache, spend cap, retries and
  all), and writes one line to calls.jsonl for it.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openai

from archivist.models import LLMRequest, LLMResponse, load_roles
from archivist.models import baseten_api, fireworks_api
from archivist.models.budget import Price
from archivist.models.cache import cache_key
from archivist.models.registry import register_backend

Validator = Callable[[str], tuple[bool, str | None]]


@dataclass
class Notes:
    """What one Recorder.complete() saw below it."""

    attempts: list[dict] = field(default_factory=list)  # every HTTP attempt, failures included
    brackets_closed: list[int] = field(default_factory=list)  # D28 repairs


class _Local(threading.local):
    def __init__(self) -> None:
        self.notes: Notes | None = None
        self.tags: dict[str, Any] = {}


_LOCAL = _Local()


@contextmanager
def tagged(**tags: Any) -> Iterator[None]:
    """Fields every call made in this thread, inside the block, carries in its record. A tag named
    "validate" is a function from the answer's text to (parsed, why not): it is not recorded."""
    before = _LOCAL.tags
    _LOCAL.tags = {**before, **tags}
    try:
        yield
    finally:
        _LOCAL.tags = before


class _RepairHandler(logging.Handler):
    """baseten_api.close_brackets logs a warning each time it closes brackets (D28)."""

    _COUNT = re.compile(r"^(\d+) bracket")

    def emit(self, record: logging.LogRecord) -> None:
        notes = _LOCAL.notes
        found = self._COUNT.match(record.getMessage())
        if notes is not None and found:
            notes.brackets_closed.append(int(found.group(1)))


def _install_repair_handler() -> None:
    log = logging.getLogger(baseten_api.__name__)
    if not any(isinstance(h, _RepairHandler) for h in log.handlers):
        log.addHandler(_RepairHandler())


_install_repair_handler()


def scrub(text: str, limit: int = 300) -> str:
    """An error message with anything long and opaque taken out, cut to limit."""
    return re.sub(r"[A-Za-z0-9_\-]{28,}", "[long token]", text)[:limit]


def _attr(obj: Any, name: str) -> Any:
    return getattr(obj, name, None) if obj is not None else None


class SpyClient:
    """The one method of the OpenAI client a backend uses, with every attempt noted."""

    def __init__(self, real: Any, timeout_s: float) -> None:
        self._real = real
        self._timeout_s = timeout_s
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        kwargs["timeout"] = self._timeout_s
        notes = _LOCAL.notes
        started = time.perf_counter()
        try:
            completion = self._real.chat.completions.create(**kwargs)
        except Exception as error:
            if notes is not None:
                notes.attempts.append(
                    {
                        "ok": False,
                        "http_s": round(time.perf_counter() - started, 3),
                        "error": type(error).__name__,
                        "status": _attr(error, "status_code"),
                        "message": scrub(str(error)),
                    }
                )
            raise
        elapsed = time.perf_counter() - started
        if notes is not None:
            notes.attempts.append(self._summary(kwargs, completion, elapsed))
        return completion

    @staticmethod
    def _summary(kwargs: Mapping[str, Any], completion: Any, elapsed: float) -> dict:
        usage = completion.usage
        choice = completion.choices[0]
        message = choice.message
        answer = message.content or ""
        reasoning = _attr(message, "reasoning_content")
        if not isinstance(reasoning, str):
            reasoning = _attr(message, "reasoning")
        return {
            "ok": True,
            "http_s": round(elapsed, 3),
            "effort_sent": kwargs.get("reasoning_effort"),
            "response_model": _attr(completion, "model"),
            "finish_reason": _attr(choice, "finish_reason"),
            "input_tokens": _attr(usage, "prompt_tokens"),
            "cached_input_tokens": _attr(_attr(usage, "prompt_tokens_details"), "cached_tokens"),
            "output_tokens": _attr(usage, "completion_tokens"),
            "reasoning_tokens": _attr(
                _attr(usage, "completion_tokens_details"), "reasoning_tokens"
            ),
            "answer_chars": len(answer),
            "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
            "fence_removed": baseten_api._FENCE.match(answer) is not None,
        }


def _shim(base: type, api: Any, label: str) -> type:
    class Shim(base):  # type: ignore[misc, valid-type]
        def __init__(
            self,
            model_id: str,
            price: Price,
            *,
            reasoning_effort: str = "low",
            timeout_s: float = baseten_api.TIMEOUT_S,
            client: Any = None,
        ) -> None:
            super().__init__(model_id, price, reasoning_effort="low", client=client)
            # The committed constructor allows low, medium, high and xhigh. The probe also
            # sends "none" and "minimal"; the effort is part of the cache key as ever.
            self.settings = {**self.settings, "reasoning_effort": reasoning_effort}
            self.timeout_s = timeout_s
            if client is not None:
                self._client = SpyClient(client, timeout_s)

        @property
        def client(self) -> Any:
            if self._client is None:
                real = openai.OpenAI(
                    api_key=api.api_key(),
                    base_url=api.BASE_URL,
                    timeout=self.timeout_s,
                    max_retries=0,
                )
                self._client = SpyClient(real, self.timeout_s)
            return self._client

    Shim.__name__ = Shim.__qualname__ = label
    return Shim


OpenwBaseten = _shim(baseten_api.BasetenLLM, baseten_api, "OpenwBaseten")
OpenwFireworks = _shim(fireworks_api.FireworksLLM, fireworks_api, "OpenwFireworks")


def _register() -> None:
    for name, factory in (("openw_baseten", OpenwBaseten), ("openw_fireworks", OpenwFireworks)):
        try:
            register_backend(name, "llm", factory, priced=True)
        except ValueError:  # imported twice
            pass


_register()


class Sink:
    """calls.jsonl: one line for every Recorder.complete(), in the order the calls ended."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = sum(1 for _ in path.open(encoding="utf-8")) if path.exists() else 0

    def write(self, record: dict) -> None:
        with self._lock:
            self._seq += 1
            line = json.dumps({"seq": self._seq, **record}, separators=(",", ":"))
            with self.path.open("a", encoding="utf-8") as out:
                out.write(line + "\n")


class Flights:
    """How many calls to each host are in flight, this one included."""

    def __init__(self) -> None:
        self._n: Counter[str] = Counter()
        self._lock = threading.Lock()

    def enter(self, host: str) -> int:
        with self._lock:
            self._n[host] += 1
            return self._n[host]

    def leave(self, host: str) -> None:
        with self._lock:
            self._n[host] -= 1


class Recorder:
    """Cache(Budget(backend)) with a line written for every call through it."""

    def __init__(self, inner: Any, *, host: str, effort: str, sink: Sink, flights: Flights) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self.host, self.effort, self.sink, self.flights = host, effort, sink, flights

    @property
    def guard(self) -> Any:
        return self.inner.inner.guard  # Cache -> Budget -> the guard every role shares

    def complete(self, request: LLMRequest) -> LLMResponse:
        tags = dict(_LOCAL.tags)
        validate: Validator | None = tags.pop("validate", None)
        notes, outer = Notes(), _LOCAL.notes
        _LOCAL.notes = notes
        in_flight = self.flights.enter(self.host)
        started = time.perf_counter()
        response: LLMResponse | None = None
        failure: BaseException | None = None
        try:
            response = self.inner.complete(request)
            return response
        except BaseException as error:
            failure = error
            raise
        finally:
            wall = time.perf_counter() - started
            self.flights.leave(self.host)
            _LOCAL.notes = outer
            self.sink.write(
                self._record(request, response, failure, notes, wall, in_flight, tags, validate)
            )

    def _record(
        self,
        request: LLMRequest,
        response: LLMResponse | None,
        failure: BaseException | None,
        notes: Notes,
        wall: float,
        in_flight: int,
        tags: dict,
        validate: Validator | None,
    ) -> dict:
        hit = bool(response is not None and response.cached)
        good = [a for a in notes.attempts if a["ok"]]
        last = good[-1] if good else {}
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "host": self.host,
            "effort": self.effort,
            **tags,
            "role": request.role,
            "variant": "retry_note" if "Your previous answer" in request.prompt else "first",
            "max_output_tokens": request.max_output_tokens,
            "request_sha256": cache_key(
                self.name, self.model_id, request, getattr(self.inner, "settings", None)
            ),
            "cache_hit": hit,
            "wall_s": round(wall, 3),
            "in_flight_at_start": in_flight,
        }
        if not hit:
            record |= {
                "http_attempts": len(notes.attempts),
                "retries": max(0, len(notes.attempts) - 1),
                "http_s": round(sum(a["http_s"] for a in notes.attempts), 3),
                "failed_attempts": [a for a in notes.attempts if not a["ok"]],
                **{k: v for k, v in last.items() if k not in ("ok", "http_s")},
                "brackets_closed": sum(notes.brackets_closed),
            }
        if response is not None:
            record["response_model_configured"] = response.model_id
            record["cost_usd"] = response.usage.cost_usd
            text = response.text
            record["empty"] = not text.strip()
            if validate is not None:
                parsed, why = validate(text)
                record["parse_ok"], record["parse_error"] = parsed, why
            if not record.get("parse_ok", True) and not record["empty"]:
                record["answer_head"], record["answer_tail"] = text[:120], text[-120:]
        if failure is not None:
            record["error"] = {
                "type": type(failure).__name__,
                "status": _attr(failure, "status_code"),
                "message": scrub(str(failure)),
            }
        return record


def split_role(name: str) -> tuple[str, str, bool]:
    """"fireworks.low.long" -> ("fireworks", "low", True)."""
    host, effort, *rest = name.split(".")
    return host, effort, bool(rest)


def build_roles(
    config: Path, *, cache_dir: Path, ledger_path: Path, sink: Sink
) -> dict[str, Recorder]:
    """Every role of the config as Recorder(Cache(Budget(backend))), sharing one spend guard."""
    flights = Flights()
    roles = load_roles(config, cache_dir=cache_dir, ledger_path=ledger_path)
    out = {}
    for name, role in roles.items():
        host, effort, _ = split_role(name)
        out[name] = Recorder(role, host=host, effort=effort, sink=sink, flights=flights)
    return out
