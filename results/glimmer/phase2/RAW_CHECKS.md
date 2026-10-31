# Raw-output Check — 2026-10-31, before any output/reference comparison

Both frozen arms contain 791 raw answers in original index order, with matching sample
and input SHA256 values. All 198 batch checkpoints are present in this task's volume
prefix. No generated answer has been parsed or compared with a reference label.

The exact command ran unpiped and exited 0:

```sh
uv run pytest -q && uv run python -m archivist.replay
```

- 1,152 tests passed in 55.58 seconds.
- All 11 committed runs and both exports were identical.
- Ledger stayed at 81,154 lines before/after replay; no model calls or new spend.
- Pre-commit passed; the raw-response contents passed the secret scan.
- All 34 original phase-1 artifact checksums remain unchanged.
- Only the recorded recovery app was checked/stopped; it was already stopped, and its
  function reports zero runners, running inputs and backlog. No other app was stopped.
- The two existing sparse exclusions importing prohibited labelling/scorer code remain.
- The 50-page human comparison is deferred; no labels, cell draw or deep records were read.

Billing reconciliation after this Check changes financial metadata only; inference,
parsing/scoring definitions, raw responses and frozen inputs are unchanged. The next
step is to commit and push both raw arms before invoking compare_phase2.
