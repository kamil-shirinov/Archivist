# Phase-2 preflight — 2026-10-31

Before any draw, independent classification/title-record checks matched the owner's
291 named / 136 confirmed / 155 rejected / 791 sampled counts, with no failures.
N=791 forecast: $2.19157664 expected, $3.21957735 with the declared timing margin.
One sample was drawn with seed 4005 and frozen before OCR; only sampled PDF text layers
were read. Prefix remains 1,024 characters. No output comparison has been run.

The exact unpiped Check passed before GPU submission:

```sh
uv run pytest -q && uv run python -m archivist.replay
```

1,147 tests passed in 56.15 seconds. All 11 committed runs and both exports replayed
identically; spend ledger 81,152 lines before/after. Pre-commit passed. The existing
sparse exclusions of tests/test_labelling.py and tests/test_score.py remain in place;
no prohibited scorer/labelling package was restored or executed. All 34 preserved
phase-1 artifacts match their prior SHA256 snapshot. The inference/preparation code,
metric definitions, adapter/base/configuration, sample and 791 OCR prefixes are frozen.

The single L4 job will have a 10,825-second execution timeout, 300-second startup timeout,
15-second shutdown allowance, one container, 4 physical CPU cores and 32 GiB RAM.
Maximum $3.8482016, combined retained bound $24.3099506. Rates rechecked 2026-10-31:
https://modal.com/pricing . No retry, fallback or extra GPU job is funded. Only this
task's explicitly recorded app/call may be stopped; unrelated training apps stay alone.
