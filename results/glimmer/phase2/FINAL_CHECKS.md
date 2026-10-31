# Final aggregate-comparison Check — 2026-10-31

The raw arms were committed and pushed in a33ace9bb020e2701769c86c2a8a89a66f22b345
before compare_phase2 ran. Its guard verified pushed raw/frozen bytes and source hashes.
Only aggregate pipeline-proxy comparisons were produced; no page-level error analysis,
new model call, training, tuning or human-label comparison occurred.

The exact final command ran unpiped and exited 0:

```sh
uv run pytest -q && uv run python -m archivist.replay
```

- 1,152 tests passed in 55.50 seconds.
- All 11 committed runs and both checked exports reproduced identically.
- Ledger stayed at 81,154 lines before/after replay; no model calls or new spend.
- Pre-commit passed: gitleaks, trailing whitespace and end-of-file checks.
- Raw-response bytes remain identical to the pushed commit; original source/configuration,
  the frozen 791-page sample and input bytes, and all 34 phase-1 artifacts remain unchanged.
- The interrupted 79/99-batch first attempt, zero surviving answers and its full billed/
  retained costs remain explicitly reported. One approved recovery saved both raw arms
  and all 198 batch checkpoints, with the model/input/generation settings unchanged.
- Only this task's recorded recovery app was checked/stopped. It was already stopped;
  its function reports zero runners, running inputs and backlog. No other app was stopped.
- Existing sparse exclusions of tests/test_labelling.py and tests/test_score.py remain;
  neither prohibited package was restored or executed.
- No labels, cell draw, deep-check records, original scorer or git tag were read. The
  50-page human comparison remains deferred. No new page/OCR access occurred in recovery.

Summary and financial reporting are complete. The retained bound is $28.1581522 under
the explicitly approved $28.16 ceiling; reported cumulative Glimmer charges are $4.74848057
at the saved billing query, including the interrupted attempt (billing may lag).
