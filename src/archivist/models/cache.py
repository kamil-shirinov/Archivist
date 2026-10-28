"""Response cache: one wrapper for both protocols, also the replay log of a run.

The key covers the backend, the model, the backend's settings (such as reasoning_effort) and
every field of the request, so changing any of them is a miss. A hit returns the stored response
with cached=True and never reaches the backend. It still carries the usage of the original call:
spend is what the ledger says, not what responses say.

Writes are atomic: an entry is written whole to a temporary file beside it (<key>.json.<pid>.tmp),
flushed to disk, and only then renamed onto its name, so an entry is either absent or complete,
even across a power cut. A write that fails removes its temporary file. A process killed
mid-write can leave a stray temporary file, never a partial entry: only <key>.json is ever read,
and the call is asked again next time.

One answer per request (single-flight by key): identical requests made at once, by threads or by
separate processes, through any Cache over the same directory, share one call. The first asks the
backend and stores the answer; the others wait for it and are answered from the stored entry,
cached=True, exactly as a replay would be. Without this, two workers re-reading identical crops
could each get their own answer while the cache kept only the last written, and a replay would
not reproduce the run. If the first call fails, the next waiter asks in its place.

A miss is asked under a thread lock for its key and an exclusive flock on <key>.json.lock beside
the entry, and the entry is looked for again once both are held. The lock file is removed once the
entry exists, when no caller can need it: a later caller finds the entry, and one that opens a
fresh lock file finds it on looking again. A failed call leaves the lock file for the next waiter.
The operating system releases the flock of a process that dies, so a killed run can leave a stray
lock file, never a held lock. A hit takes no lock: an entry that exists is complete.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

from pydantic import BaseModel

from archivist.models.base import (
    LLMRequest,
    LLMResponse,
    Region,
    Segmenter,
    SegmentRequest,
    SegmentResponse,
    Usage,
    VisionLLM,
)
from archivist.schema import BBox

CACHE_DIR = Path("cache")
_FLIGHTS: dict[Path, threading.Lock] = {}  # an entry's path -> the lock its threads queue on
_FLIGHTS_LOCK = threading.Lock()


def _thread_lock(path: Path) -> threading.Lock:
    with _FLIGHTS_LOCK:
        return _FLIGHTS.setdefault(path.resolve(), threading.Lock())


@contextlib.contextmanager
def _flight(path: Path) -> Iterator[None]:
    """Held by one caller of the entry at a time, in this process and across processes."""
    with _thread_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_name(f"{path.name}.lock")
        with lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)  # waits while another process asks
            try:
                yield
            finally:
                if path.exists():
                    lock.unlink(missing_ok=True)  # no caller needs it once the entry exists
                fcntl.flock(handle, fcntl.LOCK_UN)


def _canonical(value: object) -> object:
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    if isinstance(value, tuple | list):
        return [_canonical(item) for item in value]
    return value


def cache_key(
    backend: str,
    model_id: str,
    request: LLMRequest | SegmentRequest,
    settings: Mapping[str, object] | None = None,
) -> str:
    fields = {f.name: _canonical(getattr(request, f.name)) for f in dataclasses.fields(request)}
    payload = {
        "backend": backend,
        "model_id": model_id,
        "settings": dict(settings or {}),
        "request": fields,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _encode(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump()
    raise TypeError(f"cannot serialise {type(value).__name__}")


def _load_llm(data: dict) -> LLMResponse:
    return LLMResponse(**{**data, "usage": Usage(**data["usage"])})


def _load_segment(data: dict) -> SegmentResponse:
    regions = tuple(
        Region(label=r["label"], bbox=BBox.model_validate(r["bbox"]), score=r["score"])
        for r in data["regions"]
    )
    return SegmentResponse(**{**data, "regions": regions, "usage": Usage(**data["usage"])})


class Cache:
    def __init__(
        self,
        inner: VisionLLM | Segmenter,
        cache_dir: Path = CACHE_DIR,
        settings: Mapping[str, object] | None = None,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self.cache_dir = cache_dir
        self.settings = dict(settings or {})

    def complete(self, request: LLMRequest) -> LLMResponse:
        return self._through(request, self.inner.complete, _load_llm)

    def segment(self, request: SegmentRequest) -> SegmentResponse:
        return self._through(request, self.inner.segment, _load_segment)

    def _through[Req: (LLMRequest, SegmentRequest), Resp: (LLMResponse, SegmentResponse)](
        self, request: Req, call: Callable[[Req], Resp], load: Callable[[dict], Resp]
    ) -> Resp:
        key = cache_key(self.name, self.model_id, request, self.settings)
        path = self.cache_dir / key[:2] / f"{key}.json"

        def stored() -> Resp:
            return dataclasses.replace(load(json.loads(path.read_text())), cached=True)

        if path.exists():
            return stored()
        with _flight(path):  # a caller asking the same thing waits here, then reads the entry
            if path.exists():
                return stored()
            response = call(request)
            _write_atomically(path, json.dumps(dataclasses.asdict(response), default=_encode))
            return response


def _write_atomically(path: Path, text: str) -> None:
    """text at path, whole or not at all: written and flushed beside it, then renamed onto it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with partial.open("w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        partial.replace(path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
