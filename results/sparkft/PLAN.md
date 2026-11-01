# P34 — Spark Open development-only fine-tune: operative plan

This supersedes the initial $40 stop and earlier five-page/NVFP4 proposals.
The owner authorizes **$95 total Modal training and validation**, **$20 reserved
separately for serving**, and the original **$5 Baseten** ceiling. Commit this plan
and its executable protocol before archive training. No held-out access is allowed.

## Pages and references, fixed before archive inference

The rule was written in `training/validation_v2/RULE.md` before the development
OCR census or selection. `draw.json` freezes the selected pages, source PDF hashes,
image hashes, approved-template layout signatures and the complete matching-page
inventory. Every PDF/image access passes the development gate from
`data/real/split.json`. No user labels, held-out pages/results, or Glimmer files are
inputs. Development-only links under data/real are ignored and never committed.

Scope is every **approved Treasury table family and supported layout** in
config/real_test.toml: five single-panel portrait templates. A layout signature
records template row mode, column schema, panel structure and orientation. The
census checks all development PDFs; it does not claim coverage of unknown or
unapproved archive layouts. Selection preserves the original validation pages,
then sorts remaining candidates by SHA256 of
`sparkft-coverage-3402:<family>:<layout>:<page>` until three pages per stratum.
Selection is independent of reference support and model performance.

| Family | Fixed validation pages |
| --- | --- |
| Forward exchange | 1939-04_p075, 1939-08_p097, 1939-12_p060 |
| Railroad receipts/expenditures | 1939-09_p024, 1939-10_p024, 1939-12_p025 |
| Security transactions | 1939-02_p083, 1939-08_p087, 1939-12_p055 |
| Short-term foreign liabilities | 1939-06_p083, 1939-10_p047, 1939-12_p053 |
| Claims by country | 1982-06_p094, 1983-06_p092, 1984-06_p058 |

All three available claims pages are validation-only. Withdraw its 118 candidate
training answers before any optimizer update. Training pages are exactly
**1939-01_p055 (security), 1939-01_p061 (forward), 1939-08_p043 (railroad)**:
**283 answers**, grouped by field ID into at most eight requested cells per
conversation (**37 conversations**). No claims or short-term training examples
are available. This limitation will be reported per family.

Training answers come only from P33's cached open-model reads on branch
openw-measure, pinned to commit 633cdffc7797fecc1f8a9adf5ac38ef1d6b28fc9:
Baseten and Fireworks must independently return the same normalized number and
that number must match one unambiguous OCR word. Both hosts use the same open
model: host agreement is not independent-model truth. Boxes come entirely from
the OCR layer, transformed outward onto a 0–1000 grid. No new training labels or
closed Meta API outputs are generated. Signs, ambiguous duplicates and unsupported
values are excluded. `training_answers.jsonl` records the evidence and OCR boxes.

Validation references use the prewritten deterministic unique-number/OCR matching
rule, up to twenty fields per page. A cached independent semantic read supplies
field identity where available; otherwise a single registry/cache/budget Baseten
open-model read may supply it. These public-domain Treasury images are authorized
for model calls, with at most sixteen $0.30 request reservations ($4.80). No new
Meta or Fireworks call is allowed. The draw is never replaced based on support:
**every selected family/layout must retain at least three scorable pages** or
training is blocked. Frozen dataset/reference hashes precede base inference.
OCR support is an imperfect proxy, especially on claims; this is development
validation, not a held-out generalization claim.

## Method and fixed comparison

Model: `unsloth/Muse-Spark-Open-816B-A42B`, revision
`49cade7b0c6ed297f0434229ac67eea5f9ae1220`. All 65 shard hashes match Meta's
BF16 release `0fb02478b02565b2ce7fc57e6051c91172774ac9`; see
training/bf16_provenance.json. The ungated mirror retains the original licence.
Terms and attribution requirements are recorded in TERMS.md.

The compressed NVFP4 route failed seven bounded synthetic preflights before any
archive inference or optimizer update. Preserve every attempt and its entire
reservation. Native BF16 experts avoid the unsupported quantized backward route;
no quantizer trainability flag or kernel mathematics is overridden. This fallback
is prospective: no archive comparison output has been inspected.

Use one eight-B300 container, 16 CPU cores, 256 GiB host memory, explicit language
layer placement in consecutive groups of eight, all parameters on GPUs. Native
BF16 `grouped_mm` experts and SDPA attention; pinned Transformers commit
585946e8dbfc114a5f45e62b41e35a468e9e85b9, Torch 2.15.0, PEFT 0.21.2.
A native synthetic expert input-gradient preflight must pass before model loading.
Record actual placement, versions, memory and all trainable parameters.

Attention q/k/v/o projections only: LoRA rank 16, alpha 32, dropout .05; AdamW
learning rate .0002, weight decay zero, gradient clip 1, accumulation eight with
partial final group flushed. **One epoch, seed 3401: five optimizer updates**.
Freeze every base weight, vision/audio components and experts. Mask all prompt
and image tokens; train only the assistant JSON answer. Reject any conversation
that fails the frozen 16,384-token context; never silently drop one. CPU native
processor tokenization checks every training and validation conversation first.
Completed check: 37 training conversations (4,607–4,977 tokens), 15 validation
prefixes (4,061–6,041); the largest prefix plus generation bound is 10,137 tokens.

Base and final saved/reloaded adapter see identical images, cell prompts and
native low-reasoning framing, greedy decoding, maximum 4,096 new tokens. No
validation answer enters an inference conversation. Parse strict final-channel
JSON; malformed/truncated output scores zero. No prompt, epoch, checkpoint or
hyperparameter selection from validation outcomes. No further paid retry is funded.

## Detached execution and recovery

Run `.venv/bin/python -m sparkft.launch_when_ready` under `nohup` to preserve the
handoff if the interactive client disconnects during CPU staging. This launcher
waits on the already recorded task-owned preparation call, requires the exact
BF16 revision and all 65 shards, then invokes the frozen registry backend. A file
lock prevents duplicate controllers. If the initial preparation reaches its hard timeout, stop only its recorded owned
app (to exclude concurrent writers), retain its cost ceiling, and permit exactly
two declared continuations on the same cache. The first continuation has a 3,600-second bound; a final continuation has a
3,600-second bound on a non-preemptible CPU allocation. Any other failure, or failure after the final continuation,
exits without GPUs. A restart reconnects to the recorded
continuation instead of starting another download.

Launch the archive experiment with `app.run(detach=True)`, `.spawn()`, and persist
the owned app ID, call ID, frozen request/dataset hash and checkpoint location in
training/experiment_call.json **before waiting locally**. A client usage limit or
disconnect does not stop the submitted input. Re-running
`.venv/bin/python -m sparkft.backend` reconnects to that recorded call rather than
allocating another GPU job. A recorded reservation with no call ID blocks retries.

After **every optimizer update**, save adapter safetensors, optimizer state,
Torch/CUDA RNG states, deterministic sample orders, completed-step log and frozen
experiment identity. Atomically replace `experiment-v1/latest.json` only after
the step files exist, then commit the task-owned Modal volume. Save/commit base
and adapter predictions after every validation page too. Checkpoints live in
`archivist-sparkft-p34-v1:/experiment-v1/checkpoint-NNN/`; the final adapter is
`/experiment-v1/adapter/`. Resume code verifies the experiment identity and skips
completed groups. A new paid allocation for recovery requires a fresh budget
calculation; reconnection alone starts none. Stop only explicitly recorded owned
app IDs after their work finishes. Never stop or edit Glimmer resources.

## Adoption rule and reporting

Report pooled and **per-family and per-layout** value accuracy and full OCR figure
containment, with page/field denominators, invalid outputs, joint accuracy and box
area ratios. A containing box must include the entire OCR figure, not only its
center. Record area ratios because oversized boxes can game containment.

Use the adapter only if pooled value accuracy **strictly increases**, pooled figure
containment **strictly increases**, and **no family or layout decreases in either
metric**. Require all five families, identical reference sets/denominators and
at least three scorable pages in every layout. Missing/undefined coverage rejects
adoption. A tie on either pooled metric rejects adoption. Failure to finish either
arm yields no qualified adapter. Base remains the open-weights reader unless the
entire gate passes. No held-out evaluation or open-weights run occurs here.

## Cost, hard bounds and serving

[Modal public pricing](https://modal.com/pricing): B300 .001972/GPU/s,
CPU .0000131/core/s, memory .00000222/GiB/s. Eight B300 + 16 cores + 256 GiB
= **.01655392/s**. One full run has **4,650 s execution timeout**, 300 s startup
and 15 s shutdown allowance: **$82.1902128**. Retries zero, max containers one,
minimum zero and scale-down five seconds. All GPU/CPU functions have hard timeouts.

Six failed probes retain 6 × $0.77247; the seventh retains $1.390446.
Preparation reserve is $6, including a $4.50 cumulative CPU-attempt sub-cap, model
storage, image building and cleanup. CPU preparation jobs are bounded at 1,800 s
(or 900 s for tokenization), 60 s startup; each retains $0.4629 even on failure.
One BF16 download and at most two bounded continuations are allowed, reusing
completed files. Progress shows roughly eight 25-GB shards per eight minutes, so
the continuation has a **3,600 s hard timeout**, 60 s startup and 15 s shutdown:
**$0.907284** at .00024688/s for eight CPU cores and 64 GiB. Measured transfer of about 181 GB over thirteen minutes projects a possible
unfinished tail at that bound. Fund one final **3,600-second non-preemptible continuation** at
**$0.680463**, with four parallel file downloads to favor complete, persistent
shards. All declared CPU attempts, including cleanup and the read-only integrity
check, total **$4.3754079**, below the $4.50 sub-cap. The remaining **$1.6245921** of
the **$6 preparation reserve** covers storage/image overhead. Shortening the full
GPU bound by fifty seconds to 4,650 s offsets this larger preparation allowance.
The final download uses two CPU cores and 16 GiB, no GPU. Modal's 3×
non-preemptible CPU/memory multiplier gives **.00018516/s**, still below the
original eight-core/64-GiB allocation; (3600+60+15) × .00018516 = $0.680463.
This amendment precedes all archive inference/training; comparison data, epoch,
decoding and adoption criteria are unchanged. No concurrent model-cache writers.

A CPU worker was replaced during staging. [Modal preemption documentation](https://modal.com/docs/guide/preemption)
and [timeout documentation](https://modal.com/docs/guide/timeouts) confirm that
infrastructure restarts are automatic and execution timeouts apply per attempt.
`retries=0` alone does not enforce the total resource budget. The detached local
controller now enforces an **absolute wall deadline from the original call ULID's
submission timestamp**, including every infrastructure restart. This deadline is
unchanged on reconnect: CPU jobs have their declared execution+startup window;
the GPU call has 4,950 seconds. Poll at most fifteen seconds, cancel the input and
stop only its recorded owned app fifteen seconds before the wall deadline, leaving
shutdown margin inside the reserved cost. Unknown call-ID formats stop the owned
app rather than continue without a budget deadline. Server training also checks
the original deadline before loading, each training microbatch and each validation
page. The detached controller survives the AI client's usage limit. Report a
conservative submission-to-result resource-cost upper bound, including restarts,
rather than only the last worker's runtime. The CPU-only non-preemptible final
stage avoids repeating long partial downloads after another preemption. The initial compressed cache
is removed before/alongside cleanup to avoid indefinite storage charges.

Total retained training/validation maximum:
**$82.1902128 + $6.025266 + $6 = $94.2154788 < $95**.
The $20 serving reserve is additional and cannot fund training or validation.
Keep attempt ceilings in training/budget.json regardless of failures; do not
mistake runtime-rate estimates for reconciled account invoices.

If the gate passes, serve **on Modal**, not Fireworks: reload the exact BF16 base
and saved PEFT adapter with the validated native processor/precision. Preserve the
Muse licence/policy and “Built with Muse Spark Open” attribution. No permanent
endpoint is deployed here. One later bounded eight-B300 batch with 800 s execution,
300 s startup and 15 s shutdown would reserve **$18.4576208**, leaving $1.5423792
for overhead within $20. Actual measured throughput must show the intended
open-weights batch fits that bound before launch; otherwise keep the base reader
or obtain a new serving budget. Do not promise that $20 serves an arbitrary run.
Adapter bytes, hashes and optimizer checkpoints persist independently of the base
weight cache; remove the base cache after this task's bounded work finishes.

Before the pre-training commit and final commit, run the exact unpiped Check:
`uv run pytest -q && uv run python -m archivist.replay`, then clean pre-commit.
Push with plain `git push origin sparkft`; never merge or rewrite history.

## Owner additions recorded 2026-11-01, after the GPU experiment launched

The detached GPU experiment had already launched before these additions were
recorded. Its recorded call is fc-01M6A9Y805QG5J1VTP8M0K00DC, app
ap-i5Jlfzsm9azROYNAD2gnF4; the local driver reports its 4,650-second timeout.
Whether an optimizer update occurred must be established from saved artifacts.
These additions are recorded before inspecting or scoring those artifacts here.

After the attempt, compare on the same frozen fifteen development validation
pages: fine-tuned Muse Spark Open, untrained Muse Spark Open, and hosted Muse Spark
1.3 **only where its development reads already exist in the exact-key cache**.
Make no new Meta call. Report, for each family and layout, values right, boxes
containing the full printed/OCR figure, and empty answers, with explicit page and
field denominators. Separate explicit null/blank values, missing or unusable
answers, invalid outputs and unavailable pages. Preserve raw box scoring (no OCR
box replacement for a model's prediction). Use identical frozen requested fields
and OCR references for every available arm. Also report the common cached-page
subset separately so missing hosted reads cannot masquerade as model errors.
If an arm or page did not finish, mark it unavailable; never fabricate its scores.
Some frozen references derive from the cached 1.3 read plus unique OCR agreement,
so its value score on that subset is reference-conditioned and is not an
independent accuracy estimate. Hosted 1.3 is contextual comparison only; it does
not change the fixed base-versus-adapter adoption gate.

Do not touch the glimmer branch, worktree files or any of its Modal apps. Only
explicitly recorded sparkft-owned app IDs may be stopped. Nothing runs on held-out
pages. A future real-scan/open-weights run requires **its own separate
pre-registration afterwards**, and is outside this task. No deployment or real-scan
run is authorized by a development validation result alone.

The local paired base/adapter arms may be unavailable if loading never finished.
As supplementary context only, score P33's already cached Baseten Open read where
its pages overlap this frozen draw, choosing that host before opening these scores.
Keep it explicitly separate from the matching local BF16 base: checkpoint and
prompt/decoding equivalence are not established. Existing hosted reads use their
historical full-table prompts, whereas the planned local experiment requested a
fixed subset; this is a limitation, not a new matched-prompt experiment. Report
both reference-subset empty/missing counts and, separately, empty/abstained counts
among all returned figure fields (omitted rows are unknown). No hosted result
substitutes for an unfinished paired arm or qualifies an adapter for adoption.

## Post-attempt serving correction

The GPU attempt timed out at 364/2,000 weight tensors loaded, before any archive
inference or optimizer update. There is no adapter. This observed loading path
invalidates the earlier $20 BF16 serving forecast: it must not be used to launch
an endpoint or the open-weights run. The $20 remains reserved and unspent. Any
future serving proposal needs a measured affordable load path and full batch cost,
then the separately required real-scan pre-registration. No held-out run is
started here, and no cached hosted result substitutes for a failed paired gate.
