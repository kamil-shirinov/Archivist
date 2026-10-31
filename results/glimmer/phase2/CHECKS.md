# Interruption/recovery preparation checks — 2026-10-31

The exact Check ran unpiped and exited 0:

```sh
uv run pytest -q && uv run python -m archivist.replay
```

- 1,152 tests passed in 57.72 seconds.
- All 11 committed runs reproduced identical extractions/verdicts; both exports identical.
- Spend ledger stayed at 81,153 lines before/after replay; replay made no model calls.
- Five new checkpoint/budget tests passed on invented inputs: interrupted save/reuse,
  original batch/tensor ordering, corrupt/foreign checkpoint refusal, and insufficient-cap refusal.
- Pre-commit passed: gitleaks, trailing whitespace and end-of-file checks.
- Original phase-2 source/config/sample checksums still match freeze.json; all 34 original
  phase-1 artifact hashes still match their preserved snapshot.
- Only the original task function was queried for running state: zero runners, running
  inputs and backlog. Its result is a terminal RemoteError; no raw output was recoverable.
- No new GPU job was launched during recovery preparation; the budget gate remains active.
- No output/reference or human-label comparison ran.

The existing sparse exclusions of tests/test_labelling.py and tests/test_score.py remain;
no prohibited scorer or labelling code was restored or executed. No held-out image,
additional page, cell draw, deep-check record or human label was accessed. All commands
and new files stayed inside the glimmer worktree, on branch glimmer.
