"""The local app's core, without the web: which config reads which page, whether it may, and one
read at a time (P35).

A read is Live or a Replay. Live asks the models, so it needs the keys of the backends its config
names (META_API_KEY, BASETEN_API_KEY, FIREWORKS_API_KEY, from the environment or .env, as every
backend reads them) and spends within the caps; the cache still answers anything asked before (D5,
D8, D18). A Replay never asks: every cap is zero while its roles are built, so a call that is not in
the cache is refused before it reaches a backend, exactly as archivist.replay does, and it needs no
key. Either way the roles are the ones archivist.models builds, and only report (events.Observed).

Which config reads a page: a synthetic page, the arm's (config/arms/a.toml, b.toml or c.toml: the
hosted models, the open-weight ones, or one of each); a Treasury Bulletin page, the pre-registered
real-pages test's (config/real_test.toml, the hosted models and the five approved tables).
"""

from __future__ import annotations

import contextlib
import os
import threading
import tomllib
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from archivist.doctypes import from_config
from archivist.export.bundle import model_name
from archivist.ingest.fraser import DEFAULT_ROOT
from archivist.live import artifacts, pages, reader
from archivist.live.events import (
    STEPS,
    Cancelled,
    EventLog,
    LatencyLog,
    Observed,
    Recorder,
    Steps,
    redact,
)
from archivist.models import BudgetExceeded, describe_config, load_roles
from archivist.models.budget import BACKEND_CAPS, LEDGER_PATH, BudgetGuard, caps_from_env
from archivist.models.cache import CACHE_DIR
from archivist.pipeline import extract

ARMS = {
    "a": Path("config/arms/a.toml"),
    "b": Path("config/arms/b.toml"),
    "c": Path("config/arms/c.toml"),
}
ARM_TITLES = {
    "a": "Hosted models",
    "b": "Open-weight models",
    "c": "Hosted reader, open-weight checker",
}
TREASURY_CONFIG = Path("config/real_test.toml")
MODES = ("live", "replay")
KEY_ENV = {
    "meta": "META_API_KEY",
    "baseten": "BASETEN_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
}
_ENV = threading.Lock()  # the caps are read from the environment while roles are built


class StartRefused(Exception):
    """A read that cannot start, with the HTTP status the server answers it with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Request:
    page: str
    mode: str = "live"
    arm: str = "a"
    speed: float = 1.0  # a replay's pace: 1 is as recorded, 4 four times as fast
    workers: int = 4


@contextlib.contextmanager
def zero_caps() -> Iterator[None]:
    """Every backend's spend cap at zero for as long as roles are built under it; the guard those
    roles share keeps the caps it was built with."""
    with _ENV:
        before = {var: os.environ.get(var) for var, _ in BACKEND_CAPS.values()}
        try:
            for var in before:
                os.environ[var] = "0"
            yield
        finally:
            for var, value in before.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value


def key_present(backend: str) -> bool:
    """Whether the backend's key is set. The key is read by the backend's own loader (environment,
    then .env) and dropped at once; it is never kept, shown or sent."""
    from archivist.models import baseten_api, fireworks_api, meta_api

    loader = {"meta": meta_api, "baseten": baseten_api, "fireworks": fireworks_api}[backend]
    try:
        return bool(loader.api_key())
    except Exception:  # the loader raises when the key is not set
        return False


def backends_of(config: Path) -> set[str]:
    with config.open("rb") as handle:
        return {spec["backend"] for spec in tomllib.load(handle)["roles"].values()} - {"mock"}


def missing_keys(config: Path) -> list[str]:
    return sorted(KEY_ENV[b] for b in backends_of(config) if b in KEY_ENV and not key_present(b))


class Session:
    def __init__(self, session_id: str, request: Request, log: EventLog) -> None:
        self.id, self.request, self.log = session_id, request, log
        self.state = "running"  # "running", "done" or "error"
        self.run_id: str | None = None
        self.thread: threading.Thread | None = None


class LiveApp:
    def __init__(
        self,
        root: Path = artifacts.LIVE_ROOT,
        *,
        real_root: Path = DEFAULT_ROOT,
        synthetic_root: Path = pages.SYNTHETIC_ROOT,
        sweep_dir: Path = pages.SWEEP_DIR,
        arms: Mapping[str, Path] = ARMS,
        treasury_config: Path = TREASURY_CONFIG,
        cache_dir: Path = CACHE_DIR,
        ledger_path: Path = LEDGER_PATH,
        keys: Callable[[Path], list[str]] = missing_keys,
        layer_of: Callable[[pages.LivePage], object] | None = None,
    ) -> None:
        self.root = root
        self.real_root, self.synthetic_root, self.sweep_dir = real_root, synthetic_root, sweep_dir
        self.arms, self.treasury_config = dict(arms), treasury_config
        self.cache_dir, self.ledger_path = cache_dir, ledger_path
        self._keys = keys
        self._default_layer = lambda page: reader.words_of(page, real_root)  # noqa: E731
        self._layer_of = layer_of or self._default_layer
        self.latency = LatencyLog(root / "latency.jsonl")
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._running: Session | None = None

    # --- what the browser asks about -----------------------------------------------------------

    def resolve(self, ref: str) -> pages.LivePage:
        return pages.resolve(ref, real_root=self.real_root, synthetic_root=self.synthetic_root)

    def pages(self) -> list[dict]:
        return pages.listing(
            real_root=self.real_root, synthetic_root=self.synthetic_root, sweep_dir=self.sweep_dir
        )

    def config_for(self, page: pages.LivePage, arm: str) -> Path:
        if page.kind == "treasury":
            if arm != "a":
                raise StartRefused(400, "Treasury Bulletin pages are read by the hosted arm only")
            return self.treasury_config
        if arm not in self.arms:
            raise StartRefused(400, f"no arm {arm!r}: choose one of {sorted(self.arms)}")
        return self.arms[arm]

    def has_cache(self) -> bool:
        return self.cache_dir.is_dir() and any(self.cache_dir.iterdir())

    def status(self) -> dict:
        """What the page needs to know before it offers a read: no value of any key, only whether
        each is set."""
        configs = [*self.arms.values(), self.treasury_config]
        backends = sorted(set().union(*(backends_of(c) for c in configs)) & set(KEY_ENV))
        keys = {KEY_ENV[b]: key_present(b) for b in backends}
        with _ENV:
            caps = caps_from_env()
        guard = BudgetGuard(caps["meta"], self.ledger_path, caps=caps)
        arms = []
        for arm, path in self.arms.items():
            used = describe_config(path)
            arms.append(
                {
                    "id": arm,
                    "title": ARM_TITLES.get(arm, arm),
                    "models": sorted({model_name(v["model_id"]) for v in used.values()}),
                    "missing_keys": self._keys(path),
                }
            )
        treasury = describe_config(self.treasury_config)
        running = self._running
        return {
            "keys": keys,
            "live": {"available": all(keys.values()) if keys else False},
            "replay": {"available": self.has_cache()},
            "arms": arms,
            "treasury": {
                "models": sorted({model_name(v["model_id"]) for v in treasury.values()}),
                "missing_keys": self._keys(self.treasury_config),
            },
            "caps": {b: {"cap": caps[b], "spent": round(guard.spent(b), 4)} for b in caps},
            "running": running.id if running else None,
            "steps": list(STEPS),
        }

    # --- reads ---------------------------------------------------------------------------------

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def start(self, request: Request) -> Session:
        """Begin a read on its own thread; raises StartRefused (and PageRefused for a page that is
        not a development page) before anything is asked of a model."""
        if request.mode not in MODES:
            raise StartRefused(400, f"mode must be one of {MODES}")
        if not 0.1 <= request.speed <= 50:
            raise StartRefused(400, "speed must be between 0.1 and 50")
        if not 1 <= request.workers <= 16:
            raise StartRefused(400, "workers must be between 1 and 16")
        page = self.resolve(request.page)
        config = self.config_for(page, request.arm)
        if page.kind == "treasury" and self._layer_of is self._default_layer:
            issue, _, number = page.page_id.rpartition("_p")
            if not pages.downloaded(self.real_root, issue, int(number)):
                raise StartRefused(
                    412,
                    f"{page.page_id}: the scan or its archive PDF is not on this machine "
                    "(uv run python -m archivist.ingest.fraser --source treasury)",
                )
        if request.mode == "live":
            if missing := self._keys(config):
                raise StartRefused(
                    412,
                    f"Live calls need {', '.join(missing)}: set it in the environment or in .env "
                    "(see the README), or choose Replay",
                )
        elif not self.has_cache():
            raise StartRefused(
                412, f"Replay plays the cache, and {self.cache_dir}/ is empty or missing"
            )
        with self._lock:
            if self._running is not None:
                raise StartRefused(409, "a read is already running: stop it or wait for it")
            run_id = artifacts.run_id_for(request.mode, page.page_id, artifacts.stamp())
            taken = {*self._sessions, *(p.name for p in (self.root / "runs").glob("*"))}
            run_id = next(
                r for r in (run_id, *(f"{run_id}-{n}" for n in range(2, 1000))) if r not in taken
            )
            log = EventLog(run_id, sink=self.root / "sessions" / run_id / "events.jsonl")
            session = Session(run_id, request, log)
            self._sessions[run_id] = session
            for old in list(self._sessions)[:-20]:
                del self._sessions[old]
            self._running = session
        names = {
            role: model_name(spec["model_id"]) for role, spec in describe_config(config).items()
        }
        log.emit(
            "session",
            session_id=run_id,
            page=page.ref,
            page_id=page.page_id,
            kind=page.kind,
            mode=request.mode,
            arm=request.arm if page.kind == "synthetic" else "a",
            speed=request.speed,
            config=config.as_posix(),
            models=[
                {"role": r, "name": names[r], "model_id": s["model_id"], "backend": s["backend"]}
                for r, s in describe_config(config).items()
            ],
            steps=list(STEPS),
        )
        session.thread = threading.Thread(
            target=self._run, args=(session, page, config, names), daemon=True, name=run_id
        )
        session.thread.start()
        return session

    def cancel(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None or session.state != "running":
            return False
        session.log.cancelled.set()
        return True

    def _roles(self, config: Path, mode: str) -> dict:
        def build() -> dict:
            return load_roles(config, cache_dir=self.cache_dir, ledger_path=self.ledger_path)

        if mode == "replay":
            with zero_caps():
                return build()
        with _ENV:
            return build()

    def _run(self, session: Session, page: pages.LivePage, config: Path, names: dict) -> None:
        request, log = session.request, session.log
        started = datetime.now(UTC)
        steps = Steps(log, names)
        rec = Recorder(log, steps, self.latency, mode=request.mode, speed=request.speed)
        try:
            doc_types = from_config(config)
            roles = {
                role: Observed(inner, role, rec)
                for role, inner in self._roles(config, request.mode).items()
            }
            if page.kind == "treasury":
                outcome = reader.read_treasury(
                    page, roles, doc_types, rec, workers=request.workers, layer_of=self._layer_of
                )
            else:
                outcome = reader.read_synthetic(
                    page, roles, doc_types, rec, workers=request.workers
                )
            steps.close()
            finished = datetime.now(UTC)
            totals = {**rec.totals, "elapsed_s": round((finished - started).total_seconds(), 2)}
            if outcome.unsupported:
                log.emit("done", outcome="unsupported", doc_type=outcome.doc_type, totals=totals)
            elif not artifacts.has_values(outcome):
                log.emit("done", outcome="no_values", doc_type=outcome.doc_type, totals=totals)
            else:
                run_dir = artifacts.write_run(
                    self.root,
                    session.id,
                    outcome,
                    config=describe_config(config),
                    doc_types=doc_types,
                    rec=rec,
                    started=started,
                    finished=finished,
                )
                session.run_id = artifacts.export_run(
                    self.root,
                    run_dir,
                    mode=request.mode,
                    outcome=outcome,
                    cost=rec.totals["cost_usd"],
                )
                log.emit(
                    "done",
                    outcome="read",
                    run_id=session.run_id,
                    page_id=page.page_id,
                    doc_type=outcome.doc_type,
                    values=len(outcome.verdicts),
                    accepted=sum(v.status == "accepted" for v in outcome.verdicts),
                    review=sum(v.status == "review" for v in outcome.verdicts),
                    totals=totals,
                )
            session.state = "done"
        except Cancelled:
            steps.close()
            log.emit("error", kind="stopped", message="Stopped. Nothing further was asked.")
            session.state = "error"
        except BudgetExceeded as error:
            steps.close()
            replay = request.mode == "replay"
            log.emit(
                "error",
                kind="not_cached" if replay else "budget",
                message=(
                    "This page is not in the cache, so a replay cannot play it. Read it live once, "
                    "or choose a page an earlier run read."
                    if replay
                    else f"The spend cap stopped the read: {redact(str(error))}"
                ),
            )
            session.state = "error"
        except extract.ExtractionFailed as error:
            steps.close()
            log.emit("error", kind="failed", message=redact(str(error))[:400])
            session.state = "error"
        except Exception as error:  # the stream must always end, with the reason
            steps.close()
            message = redact(f"{type(error).__name__}: {error}")[:400]
            log.emit("error", kind="failed", message=message)
            session.state = "error"
        finally:
            with self._lock:
                self._running = None
            log.close()
