# P31 setup and resumption

Worktree: `.worktrees/glimmer`, branch `glimmer`. All commands below run from that worktree.
The main checkout is read-only, except the explicitly requested `.git/info/exclude` entry.

## Access and data

Glimmer's pinned public config, tokenizer config and weight index were accessible anonymously.
No Hugging Face credential or licence acceptance was requested. See `access.json`.
Only `results/real_test/development/` was read, with the owner's explicit narrow exception;
every reference was validated against the development split before page/PDF access.
No held-out page/result, labelling package, scorer or git tag was opened.

The fixed validation set has 40 pages: five family positives and 35 `other` pages.
Training has 115 unique pages: two positives per family and 105 `other` pages.
33 training pages were removed because their OCR matched a validation input.
The manifests and data hashes are frozen. Do not regenerate to improve a result.

## Modal blocker

The first app creation was rejected before GPU allocation:
`InvalidError: Please add a payment method to use H100! GPU functions.`
The CPU preparation app is separate, so it can run without registering a GPU function.
The owner added a payment method and explicitly authorised continuing. The billing blocker
is resolved; the rejection remains recorded as part of setup history.
This does not increase the $25 experiment cap. Never delete `cost.json` or the spend ledger
in order to rerun a job. Failed jobs keep their full worst-case reservation.

## Commands

The model/data modules do not load `.env`. Glimmer is downloaded anonymously; Modal uses its
already configured profile. No API key is required for reusing the committed Spark comparator.

```bash
uv sync --frozen --group glimmer
uv run --group glimmer python -m archivist.glimmer.run prepare
uv run --group glimmer python -m archivist.glimmer.run baseline
uv run --group glimmer python -m archivist.glimmer.run train
uv run --group glimmer python -m archivist.glimmer.run trained
uv run python -m archivist.glimmer.report
uv run pytest -q && uv run python -m archivist.replay
```

Estimate and record each GPU job before launch: baseline at most $2.72; training at most
$9.70; trained validation at most $2.72, including startup, CPU/memory and scale-down allowance.
Combined conservative reservation is $17.63 with $2.50 for CPU preparation/builds/storage.
CPU and memory have explicit upper limits (4 physical cores, 64 GiB) on future jobs.
The service is ephemeral, one container per function, no GPU retries and no public endpoint.
The final adapter is downloaded and its archive hash checked; the trained arm reloads it over
the same pinned, quantized base in a fresh GPU process.

After each run, refresh Modal's billing report, retaining only this experiment's app records.
Billing can lag; `billing.json` records its query time, resource costs and source command.
Measured runtime estimates and worst-case reservations are reported separately from charges.
The registry writes a dedicated experiment spend ledger, mirrored into the branch's canonical
results/spend_ledger.jsonl before the final checks and commit (D18).

The exact pytest command excludes two suites through sparse checkout:
`tests/test_labelling.py` and `tests/test_score.py` import the prohibited labelling/scorer code.
They were not restored or run. All other discovered tests run; replay uses only the existing
synthetic pre-registered cache and spends nothing. Cache entries are hardlinked into this
worktree; new writes replace local entries atomically and cannot mutate main-checkout entries.

Phase 2 remains closed. There is no held-out command in the new modules.

## Completed phase-1 audit

See REPORT.md for both the untouched frozen scores and the separately labelled native-framing
diagnostic. The return-wrapper failure was recovered without retraining; its records and
before/after code fingerprints are retained. The adapter tensors are unchanged from Modal;
metadata-only newline normalisation is documented in artifact_manifest.json.
No more phase-1 jobs are needed. Before phase 2, settle response framing prospectively and
estimate a budget-compliant serving run; the current sequential projection exceeds $25.
