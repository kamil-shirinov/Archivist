"""Watch the held-out deep check from outside; stop it before verdicts if a re-read went unanswered.

A re-read that ends without an answer leaves its cache .lock file and no entry. Verify writes
verdicts the moment its last re-read returns, so the runner is stopped (SIGTERM, the process
itself) while fewer than MARGIN re-reads are left to ask and at least one has gone unanswered.
Calls no model; writes only the failed list and this watcher's log.
Run from archivist/: python3 -I <this> <reread_keys.jsonl> <resume start, ISO> <failed out.jsonl>
"""

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

MARGIN = 300
POLL = 10
keys_path, since, failed_path = sys.argv[1], datetime.fromisoformat(sys.argv[2]).timestamp(), sys.argv[3]

first = {}
for line in open(keys_path):
    row = json.loads(line)
    first.setdefault(row["key"], row["index"])
order = sorted(first, key=first.get)


def entry(key):
    return f"cache/{key[:2]}/{key}.json"


def runner():
    found = subprocess.run(
        ["pgrep", "-f", r"\.venv/bin/python -m archivist\.templates\.real_test deep --side held_out"],
        capture_output=True, text=True,
    ).stdout.split()
    return int(found[0]) if found else None


def held(lock):
    try:
        fd = os.open(lock, os.O_RDONLY)
    except FileNotFoundError:
        return True  # answered and removed in between
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


seen, polls = {}, {}
while True:
    pid = runner()
    frontier, answered = -1, set()
    for key in order:
        try:
            stamp = os.stat(entry(key)).st_mtime
        except FileNotFoundError:
            if os.path.exists(entry(key) + ".lock") and held(entry(key) + ".lock"):
                frontier = max(frontier, first[key])
            continue
        answered.add(key)
        if stamp >= since:
            frontier = max(frontier, first[key])
    failed = [
        k for k in order
        if first[k] < frontier and k not in answered
        and os.path.exists(entry(k) + ".lock") and not held(entry(k) + ".lock")
    ]
    for k in failed:
        seen.setdefault(k, now())
        polls[k] = polls.get(k, 0) + 1
    for k in [k for k in seen if k in answered]:
        del seen[k]  # a slow call, not a failure
        polls.pop(k, None)
    sure = [k for k in seen if polls.get(k, 0) >= 2]  # twice in a row: not one just picked up
    left = sum(1 for k in order if first[k] > frontier and k not in answered)
    print(f"{now()} pid={pid} answered={len(answered)} frontier={frontier} left={left} "
          f"unanswered={len(seen)}", flush=True)
    if pid is None:
        break
    if sure and left <= MARGIN:
        os.kill(pid, signal.SIGTERM)
        print(f"{now()} stopped the runner (pid {pid}): {len(seen)} unanswered, {left} left", flush=True)
        while runner() is not None:
            time.sleep(0.5)
        break
    time.sleep(POLL)

with open(failed_path, "w") as sink:
    for k in sorted(seen, key=first.get):
        sink.write(json.dumps({"key": k, "first_seen_unanswered": seen[k]}) + "\n")
print(f"{now()} done: {len(seen)} unanswered written to {failed_path}", flush=True)
