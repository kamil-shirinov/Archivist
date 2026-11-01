"""Reserve worst-case compute before launch; failed jobs keep their whole reservation."""
from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

CAP = 25.0
RATE = .001097 + 4*.0000131 + 64*.00000222
LIMITS = {'baseline':1800,'train':7200,'trained':1800}
STARTUP_SECONDS = 300
OVERHEAD_RESERVE = 2.50


@contextmanager
def _locked(path: Path):
    with path.with_suffix('.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def reserve(stage: str, path: Path) -> dict:
    with _locked(path):
        return _reserve(stage, path)


def _reserve(stage: str, path: Path) -> dict:
    entries = json.loads(path.read_text()) if path.exists() else []
    maximum = (LIMITS[stage]+STARTUP_SECONDS+5)*RATE
    if any(e['stage']==stage for e in entries):
        raise ValueError('job already reserved: inspect its record; no automatic reruns')
    if OVERHEAD_RESERVE + sum(e['maximum_usd'] for e in entries) + maximum >= CAP:
        raise ValueError('worst-case total reaches the $25 cap')
    record = {'stage':stage,'maximum_usd':maximum,'gpu':'H100!',
              'rate_per_second_usd':RATE,'timeout_seconds':LIMITS[stage],
              'startup_allowance_seconds':STARTUP_SECONDS,'state':'reserved',
              'reserved_at':datetime.now(UTC).isoformat(),
              'note':'Includes GPU, 4 physical cores, 64 GiB; measured cost is not an invoice.'}
    entries.append(record)
    path.write_text(json.dumps(entries,indent=2)+'\n')
    return record


def finish(stage: str, result: dict | None, path: Path, error: str | None = None) -> None:
    with _locked(path):
        _finish(stage, result, path, error)


def _finish(stage: str, result: dict | None, path: Path, error: str | None) -> None:
    entries=json.loads(path.read_text())
    entry=next(e for e in entries if e['stage']==stage)
    entry.update(state='completed' if result is not None else 'failed',
                 finished_at=datetime.now(UTC).isoformat())
    if result is not None:
        entry['runtime_seconds']=result['runtime_seconds']
        entry['estimated_compute_usd']=result['runtime_seconds']*RATE
    if error:
        entry['error']=error
    path.write_text(json.dumps(entries,indent=2)+'\n')
