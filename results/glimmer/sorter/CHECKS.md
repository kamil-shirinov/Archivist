# P37 checks

Before deploying or asking a GPU: `uv run pytest -q && uv run python -m archivist.replay`, unpiped, exit 0. **1,163 tests passed**; all eleven committed runs and both exports reproduced identically, zero paid calls, ledger unchanged at 81,154 lines. Pre-commit passed (gitleaks, trailing whitespace, final newline). The handoff patch also applies after whitespace normalisation and both reader tests pass.

The existing sparse exclusions of tests/test_labelling.py and tests/test_score.py remain; neither prohibited package was restored or executed. All new tests use mocks and frozen development data, without network calls. Main, ui and live-reading were fetched without tags; highest decision numbers were 42, 43 and 43, reserving D44 for this task. No branches were merged.
