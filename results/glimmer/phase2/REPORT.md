# Glimmer phase 2 — both raw arms complete, before comparison

2026-10-31. Both arms produced 791 raw answers in the same frozen page order. All 198
batch checkpoints were saved; neither generated text parsing nor output/reference
comparison has run. The required Check, commit and push of these raw artifacts comes first.
No human label, cell draw, deep-check record, original scorer or git tag was read.

## Frozen experiment

The validated frame contains 291 named pages (136 confirmed, 155 title-rejected) and
4,278 classifier-set-aside pages, with zero failures. One seed-4005 draw selected 500
set-aside pages: 791 pages total. No sample was redrawn. Both arms used the same first
1,024 OCR characters, pinned NF4/double-quant/bf16 base, saved final adapter, original
prompt, low reasoning, greedy decoding, batch 8 and 512-new-token limit. There are 78
empty OCR inputs and 370 truncated inputs; none was dropped. No held-out image was
opened or rendered. All 34 preserved phase-1 artifacts remain unchanged, including
strict trained 0/40 and its separately labelled post hoc diagnostic 40/40.

## Interruption retained in full

The first app, ap-90heG0Xt09CZ8lLTAhSns9, stopped on client disconnection after 79/99
observed complete untrained batches (632 pages). It saved only at full-arm completion,
so no answers survived; the trained arm never started. That checkpoint granularity was
an implementation mistake. No lost answer was scored, inferred from logs or fabricated.
Its reported $1.21407010 charge and entire $3.8482016 maximum remain included. The original
function was checked at zero runners, running inputs and backlog. See interruption.json
and interrupted_billing.json. No other Modal app was stopped by this task.

## Approved recovery

The owner explicitly raised the retained ceiling to $28.16 and approved recovery. The
unchanged native generator ran at the original batch memberships/tensor order, with atomic
volume commits after each full batch and a detached app. Because zero prior answers
survived, all 99 untrained batches were recomputed and all 99 trained batches ran for the
first time. Completed saved batches are never regenerated; both current reuse counts are
zero. This is one approved recovery job, not a checkpoint or hyperparameter search.

Recovery app ap-Sw3Cab71JzfWFel9XEyGUI has finished. Only that recorded app was checked/
stopped; it was already stopped when queried. Zero runners, running inputs and backlog
are recorded in recovery_stopped_app.json. Complete cloud checkpoint counts are recorded
in complete_checkpoint_inventory.json. The first checkpoint durability check confirmed
files in the volume before proceeding; no raw content was read for those inspections.

Untrained arm runtime: 4719.192 s;
trained: 919.848 s;
whole function: 5717.032 s. Live precision records show 720 NF4 modules,
double quantisation, bf16 compute/storage and all parameters on CUDA in each arm. PEFT
adapter parameters load as fp32, as in the original inference setup. Raw outputs,
runtime, peak allocated/reserved memory and generation bookkeeping are retained in
raw_response.json and raw_manifest.json. No crop, precision or decoding setting changed.

## Budget and records

This job's expected/conservative estimates were $2.2952/$3.3232. It had hard execution/
startup timeouts of 10,825/300 seconds, plus 15 seconds shutdown allowance, on one L4
with four physical CPU cores and 32 GiB RAM. Its maximum $3.8482016 remains
retained alongside the first failed attempt and all earlier maxima/overhead: combined
**$28.1581522**, below the approved **$28.16**. No additional retry is funded.

The recovery ledger records $1.97489156 of measured function-runtime compute,
which excludes some startup/transport; it is not a reconciled invoice. The same event
was appended once to results/spend_ledger.jsonl. App-specific provider billing will be
saved separately; the previously reported total before recovery is $2.76236349 including
the interrupted first attempt. The failed job's token usage was unrecovered, explicitly
marked unknown rather than measured zero. No other task's charges are included.

Raw response SHA256: `3f3456aec4ac1448c1652f919151da909ec0942b58e1fca1b9d3d77873ab338b`.
The metadata check verified 791 outputs per arm, indices 0..790, matching sample/input
hashes, and unchanged phase-1 files; it did not parse answers or compare with references.

After Check and the raw-output commit/push, the declared parser and aggregate-only
pipeline-proxy comparison may run. The owner's 50-page human comparison remains deferred
until separately requested with its committed main-branch file. No label export was read.

Provider billing queried 2026-10-31T22:08:20.204112+00:00: recovery **$1.98611708**;
interrupted first attempt **$1.21407010**; phase 2 combined
**$3.20018718**; cumulative Glimmer reported charges
**$4.74848057**. Only the two recorded phase-2 apps
were included. Billing may lag; retained bound stays $28.1581522 under $28.16.
See completed_billing.json for the app-specific resource rows and query time.
