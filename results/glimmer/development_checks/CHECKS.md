# Development-check verification — 2026-10-30

The requested Check ran unpiped and exited 0:

```sh
uv run pytest -q && uv run python -m archivist.replay
```

- 1,136 tests passed in 53.70 seconds.
- All 11 committed runs reproduced identical extractions/verdicts; both exports checked.
- The spend ledger stayed at 81,152 lines before/after replay; no model call or new spend.
- The separate targeted development/phase-2 tests passed: 15 tests.
- Pre-commit: gitleaks, trailing-whitespace and end-of-file checks passed.
- All 34 preserved phase-1 artifacts match the prior SHA256 snapshot.
- The Modal development app is stopped with zero tasks; no fallback GPU was submitted.

As declared in PLAN.md, sparse checkout excludes tests/test_labelling.py and
tests/test_score.py, which import prohibited labelling/scorer code. Neither was restored
or executed. No held-out page/result/frame, OCR or owner label was opened, and no actual
held-out sample was drawn. All commands and new files stayed in the glimmer worktree.
