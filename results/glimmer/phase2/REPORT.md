# Glimmer phase 2 — interrupted; recovery prepared, not submitted

2026-10-31. No model-comparison result is available. No human label, cell draw, deep-check
record or original scorer was read. The 50-page comparison remains deferred.

## Frame and frozen inputs

Independent checks of the permitted sweep classification/title records matched the owner:
291 named pages = 136 confirmed + 155 title-rejected. All 4,569 pages were classified,
4,278 were classifier-set-aside, and none failed. The one seed-4005 draw selected 500
set-aside pages, giving the frozen 791-page sample. No redraw occurred.

The first 1,024 OCR characters were retained for both arms; 78 inputs have empty OCR and
370 were truncated. Only sampled pages' PDF text layers were accessed, with manifest
dimensions reproducing the existing word filter without opening or rendering images.
The original sample, prefixes, adapter, code and configuration remain frozen and committed
in ae2505f. All 34 phase-1 artifacts remain byte-for-byte unchanged, including strict trained
0/40 and the separately labelled post hoc diagnostic 40/40.

## What happened

Original app: `ap-90heG0Xt09CZ8lLTAhSns9`; original call:
`fc-01M68Z9GEC7XSC5KHXWW28CG1J`.

Modal allocated the L4 before the 15-minute allocation cutoff. The model loaded and
untrained inference logged 79 complete batches (632 pages). While the client was paused,
Modal logged "Stopping app - local client disconnected" and terminated the runner. The
function result is a terminal RemoteError. The trained arm did not start.

The original wrapper persisted only after an entire arm, not after each batch. That was
an implementation mistake: its persisted run directory is empty, and there is no local
raw response or recoverable function result. The 632 computed answers cannot be reused.
Thus **zero complete raw batches survive**, and all 791 untrained answers plus all 791
trained answers are missing. No accuracy, precision or recall is reported from lost answers.
No attempt was made to infer answers from progress logs or inspect pages to recreate them.

Inspection confirmed the original function has zero runners, running inputs and backlog.
Only this task's original app was affected. No other Modal app was stopped by this task.
The scoped inspection and failure are retained in interruption.json and failure.json.

## Cost and why recovery has not run

Modal's app-specific report shows:

| Resource | Reported dollars |
|---|---:|
| L4 | 0.78000006 |
| CPU | 0.18447002 |
| Memory | 0.24960002 |
| Interrupted run total | **1.21407010** |
| Cumulative reported Glimmer total | **2.76236349** |

These are reported charges at the saved query, subject to billing lag, not reservation
ceilings. No other task's charges are included. Token usage was not recovered: ledger
integer placeholders are explicitly marked `token_usage_unknown`, not measured zero usage.
The failed paid job is logged in this phase's ledger and the committed project ledger.

The original job's full **$3.8482016** maximum remains retained. Together with all earlier
maxima/overhead, retained cost is **$24.3099506** under the owner's **$24.31** ceiling.
Only **$0.0000494** remains. The owner's new request authorises missing-batch recovery,
but does not raise that ceiling. No new GPU was submitted.

Concrete recovery proposal, awaiting explicit budget approval:

| Quantity | Dollars |
|---|---:|
| New job expected estimate, including checkpoint allowance | 2.2952 |
| New job conservative estimate, including checkpoint allowance | 3.3232 |
| New job hard maximum | **3.8482016** |
| Existing retained maxima | **24.3099506** |
| Required combined retained bound | **28.1581522** |
| Proposed rounded approval | **28.16** |

The estimate uses the previously declared 791-page development timing extrapolation, with
300 additional seconds for checkpoint I/O. The hard bound still uses 10,825 seconds
execution + 300 startup + 15 shutdown, one L4, four physical CPU cores and 32 GiB RAM.
Rates were checked on 2026-10-31 at https://modal.com/pricing . No extra retry is funded.

## Prepared recovery

The new wrapper leaves the original model loader and generator unchanged. It preserves
the original token-length/index sort, batch memberships, tensor order, left-padding width,
NF4/bf16 precision, prompt, 1,024-character input, greedy decoding, low reasoning and
512-output-token limit. It validates saved checkpoint identity/membership/token counts,
reuses each complete batch and generates only missing groups. Each group is written
atomically and committed to the volume before proceeding. A corrupt saved batch stops
recovery instead of silently being replaced. A detached app survives loss of the local
client; the existing call can be collected without launching another GPU job.

All 99 untrained groups currently lack persisted answers and must be computed again if
the owner approves recovery; then the trained arm runs on exactly the same 791 pages.
The interruption and repeated computation will remain part of the report and cost.
Recovery source is separately frozen in recovery_freeze.json. The submit command refuses
the current $24.31 retained limit before creating a Modal call. No proposed budget has
been treated as approved. No generated answer has been parsed or compared with references.

Offline tests demonstrate interruption after a complete saved batch, reuse without
regeneration, identical original group ordering, refusal of corrupt/foreign checkpoints,
and refusal to allocate under an unraised cap. The exact Check and pre-commit results
are recorded in CHECKS.md. The two existing sparse exclusions importing prohibited
labelling/scorer code remain in place.

After approved recovery completes, the original ordering remains mandatory: Check, commit
and push both raw arms first; only then report aggregate pipeline-proxy comparisons,
Check, commit and push, and stop. Human comparison waits for the separate committed file.
