# P31 final checks

Executed from the isolated glimmer worktree:

`uv run pytest -q && uv run python -m archivist.replay`

- Pytest: 1,121 passed in 55.69 seconds.
- Sparse-checkout exclusions: tests/test_labelling.py and tests/test_score.py, which import
  the prohibited labelling package/scorer. They were not restored or run.
- Replay: all 11 current runs identical (two extraction runs and nine verification runs).
- Exports: test-archivist-A and test-archivist-B unchanged.
- Canonical spend ledger: 81,151 lines before and after replay; no paid replay call.
- Pre-commit: gitleaks, trailing-whitespace and end-of-file hooks passed; no bypass.
- Gitleaks retains its original rules and exceptions. One additional exception requires
  both the exact public source-file SHA256 and one of two Glimmer audit-manifest paths.
- Adapter tensor hash and unchanged strict-metric hashes match artifact_manifest.json.
- The reloaded trained arm completed all 40 validation requests. Original strict scores
  and separately labelled post hoc native-framing diagnostic are both retained.
- All experiment Modal apps stopped; no active GPU/service remains.

No held-out page/result, labelling code, original scorer or git tag was opened. The development
results directory was read-only under the owner's explicit exception, after split checks.
The main checkout's source, results and labelling files were not changed.
