# P31 — Muse Glimmer archive sorting, phase 1

Recorded before baseline inference or training. Phase 2 requires the owner's explicit go-ahead.

## Scope and labels

Input: one public-domain Treasury Bulletin page's OCR text. Output: exactly one of the
five approved Treasury template family IDs in config/real_test.toml, or `other`.
OCC and Federal Reserve templates are drafts, so they are not targets for this experiment.

The development sweep covers 178 pages, in development issues 1939-12 and 1984-06:
168 unsupported, five confirmed (one per family), and five title-check rejections.
Read only results/real_test/development/, with the owner's explicit read-only exception;
validate every reference against data/real/split.json before opening a page or PDF.
Never read labelling/, the real scorer, any git tag, or any held-out result or page.

Targets are the pipeline's confirmed family, or `other` for unsupported and title-rejected
pages. Add the approved templates' development drafting pages as positive examples,
checking their titles against the approved patterns. Deduplicate by page ID and refuse
conflicting targets. These are development supervision / proxy labels, not human truth.

## Fixed data preparation

Keep the sweep's one confirmed page per family for validation. Within each negative
stratum (classifier unsupported; title rejection), sort by SHA256 of `glimmer-3101:<page>`
and put the first ceil(20%) in validation, the rest in training. Additional approved drafting
pages not already present go to training. Freeze page IDs, labels, sources, input hashes,
PDF hashes, template hashes, prompt hash and dataset hashes in results/glimmer/data_manifest.json
before inference. Refuse later changes. No validation example enters training, including
through duplicate OCR text. Training positives are repeated four times; negatives once.

OCR follows the existing PDFium OCR layer (templates/ocr.py and real_test.words), not a new
OCR model. Resolve and hash-check the development image first, then open only its development
PDF and page. Join OCR words in reading order. Retain the first 12,000 characters consistently
for all arms; record original length and truncation. Empty OCR is a valid empty input,
retained with its existing label, not silently dropped. Send no page IDs, file paths or provenance
to a model, only the fixed family descriptions and OCR text.

## Baseline, training and validation

Pin meta-models/Muse-Glimmer-30B to a4e59da52a7bc87ae7251dd5545c0dd437c44b68.
Verify anonymous access first; stop if a licence acceptance or token is required.
Use one Modal H100, a frozen NF4 base with bf16 compute, and LoRA (QLoRA): rank 16,
alpha 32, dropout .05, q/k/v/o language projections only; freeze vision. Three epochs,
learning rate .0002, microbatch 1, gradient accumulation 8, seed 3101, assistant-only loss,
maximum 4096 tokens. No hyperparameter search or checkpoint selection on validation;
use the final adapter. Fail if token truncation would remove the assistant target.

Serve inference through an ephemeral Modal service, with one container and automatic scale
down. Every inference goes through archivist.models registry → cache → budget → backend.
Use the same tokenizer chat template, low reasoning strength, greedy decoding, maximum
512 new tokens, system prompt, family list and OCR truncation before and after training.
Parse the final user-facing answer as exactly one family ID or `other`; invalid / truncated
answers remain errors, never silently become `other`. Save raw answers and failures.
Measure the untrained model first, save its results before training, train once, save the
adapter, reload it, then evaluate the same validation page IDs and prompt.

Report per-family TP/FP/FN, precision, recall and support (also `other`), confusion counts,
macro precision/recall, accuracy and invalid/failure counts, for untrained and trained.
A zero denominator is null / undefined, never a fabricated perfect score. Include Muse
Spark's original image-based sweep sorting alongside, before and after its title check;
this is an existing teacher comparator, with a modality difference, not an independent gold
standard. The validation set is small: only one positive per family; no generalisation claim.

## Cost and stop rules

Total new phase-1 spend must stay below $25, counting failed jobs, startup, CPU, memory,
GPU time, model/API calls and storage. Record an estimate and worst-case reservation before
every GPU job; no automatic GPU retries. Modal list prices checked 2026-10-30:
H100 $0.001097/s, physical CPU core $0.0000131/s, memory $0.00000222/GiB/s.
A job with one H100, four physical cores and 64 GiB is at most $0.00129148/s
($4.649328/hour). Initial budget: baseline <=30 minutes ($2.325), training <=2 hours
($9.299), trained validation <=30 minutes ($2.325), plus $2 for builds/storage and
$0.50 API contingency: <=$16.45. Cold startup must be included in the reservation.
Use timeouts and single-container limits, stop/tear down on completion or failure, and
reserve conservatively before launch; record actual measured duration separately from
billed cost. Do not claim an estimated cost is a reconciled invoice.

## Phase 2 measurement (fixed now; do not execute in phase 1)

After explicit permission, freeze the adapter, base revision, code, prompt and configuration
before opening the Treasury held-out pages. Sort all held-out Treasury pages; compare the
untrained and trained models with Muse Spark's existing sweep, the pipeline's confirmed
family assignments and title-check rejections, and the owner's pre-registered 50-page hand
check where available. Report per-family precision and recall against the pipeline proxy
labels, both arms and Muse Spark alongside, rejected-page behaviour, failures and total cost.
The 50-page check samples pipeline-confirmed pages: it can inform precision on that sample;
it cannot establish recall across all held-out pages. Name this coverage limitation and
teacher dependence; report human agreement separately. Do not tune on held-out outputs.
No original pre-registration, tags, scorer or labelling records are changed by this work.

## Checks and artifacts

Add offline tests for split gates before file access, source-specific issue namespaces,
label reconciliation, deterministic/disjoint slicing, duplicate inputs, strict parsing and
precision/recall counts (including failures and zero denominators). Run exactly:

`uv run pytest -q && uv run python -m archivist.replay`

The sparse checkout omits tests/test_labelling.py and tests/test_score.py because they import
the prohibited labelling package and scorer; do not restore or execute those two suites.
Report that exclusion explicitly. All remaining discovered tests run with the exact command.

Run pre-commit cleanly; commit the plan before GPU inference/training, then commit and push
the completed phase-1 artifacts on glimmer without merging. Keep adapters, predictions,
metrics, cost reservations and the final report under results/glimmer/.

Sources: https://dev.meta.ai/docs/muse-glimmer/get-the-model ;
https://dev.meta.ai/docs/muse-glimmer/post-training ;
https://dev.meta.ai/docs/muse-glimmer/prompting ; https://modal.com/pricing

## Deviations recorded during phase 1

2026-10-30: The single training run completed all 57 optimizer steps (three epochs) and
saved its adapter, then a NameError in the Modal return wrapper prevented the response from
reaching the client. An accidental CPU-preflight block was removed from that return wrapper.
The existing adapter and training metrics were recovered on CPU, without retraining.
Baseline and trained inference functions were compared as Python ASTs and are identical;
the model runtime, prompt, tokenizer settings, scorer and training settings are unchanged.
The old/new code fingerprints and the failed job are retained in recovery.json and cost.json.
The failed job keeps its entire worst-case reservation. A CPU recovery helper was added,
and that CPU module's trailing blank line was normalised for pre-commit.

2026-10-30, after trained validation: the frozen parser marked all 40 trained responses invalid
because they directly continue the open assistant header with `to=user`. The original strict
scores (0/40 trained) and raw answers are retained without change. A separately tested,
post hoc protocol-framing diagnostic reattaches only the fixed open assistant header and
reuses the original strict label parser and scoring formulas. It gives 39/40 untrained and
40/40 trained. It is explicitly a diagnostic, not a pre-registered gain. No model was called
again, no training was repeated, and no label, prompt, training setting or primary scorer
was changed. The report renderer was extended to show both results. Adapter config/model-card
whitespace was normalised for pre-commit; original and committed hashes are recorded, with
adapter tensors unchanged. Phase 2 must settle response framing before any measurement.

## Declared phase-2 amendment — 2026-10-30, before any held-out access

This amendment supersedes only the original phase-2 all-pages design and its input/serving
settings. It is prospective for phase 2. Phase-1 trained strict **0/40** remains exactly as
reported; its **40/40** native-framing result remains labelled a **post hoc diagnostic**.
No phase-1 metric, prediction, adapter, or report is replaced. The owner has authorised
preparation only: no held-out result/page/OCR may be opened and no real sample may be drawn
until the owner explicitly says go. All work remains in the glimmer worktree/branch.

### Parser declared for phase 2

Use `archivist.glimmer.phase2.parse_phase2`, version `native-assistant-header-v1`, for both
untrained and trained answers. Muse Glimmer's generation prompt ends with
`<|start|>assistant`. A continuation beginning exactly ` to=user<|message|>` or
` to=self<|message|>` gets that already-open header reattached. Then the unchanged strict
parser takes the final `assistant to=user` body and requires exactly one approved family ID
or `other`. Complete final headers and bare exact labels remain accepted. Reasoning alone,
tool recipients, prose, unknown labels, missing answers and output-token-limit exhaustion
are errors, never silently converted to `other`.

Why changed: phase 1 exposed an interface bug. The trained model directly emitted a final
recipient continuation; the frozen parser only handled a later complete final-turn header.
This prospective amendment specifies native framing before held-out measurement; it does
not retrospectively promote the phase-1 diagnostic into a primary result.
`tests/test_glimmer_phase2.py` verifies parsing every saved development output from both
models, checks malformed/truncated frames, and asserts that phase-1 strict-score hashes and
the diagnostic label are unchanged. No held-out example was used to write these rules.

### Input, batching and GPU

Use exactly the first **1,024 Unicode characters** of each page's PDF-layer OCR words joined
in their original reading order. Preserve empty OCR; record original and retained lengths.
This fixed header excerpt retains the approved title on all 15 development positives (even
512 characters did), while retaining extra heading context. Do not choose excerpts using a
sweep label, title-check result, model answer or confidence; no adaptive fallback to more text.
Missing/later titles remain a declared limitation, not an excuse to inspect held-out pages now.
Use this identical excerpt, original family descriptions and system prompt for both arms.

Use the pinned phase-1 NF4/bf16 base and final saved adapter, native tokenizer template,
reasoning strength low, greedy decoding and the same 512-new-token limit. No retraining.
Sort prompts by token length with original index as tie-break, left-pad, and run batches
of **8** on one **L4 (24 GB)**. Restore original page order; strip only per-sequence tokens
after its actual EOS, not valid answers. Load the base once, run the untrained arm, then
attach the saved adapter and run the trained arm on the identical ordered sample. Cache and
budget both arms through archivist.models. No hidden CPU offload, GPU upgrade or automatic retry.

The phase-1 observed peak allocation was 20.3 GB. The lower-priced T4 has 16 GB; L4 has
24 GB and is cheaper than the equally sized A10. Verify batch fit and timing using only the
40 development validation pages before any held-out access or measurement. This cost
declaration is a hard ceiling until that development check succeeds. This is a new
development configuration check, not a replacement phase-1 or phase-2 result.

### Sample — draw only when phase 2 starts after go

After permission, validate the successful held-out Treasury sweep map against split.json,
record its source hashes, failures and source population counts, then draw once and save a
frozen sample manifest before opening a sampled page or making a model call. Do not rerun
the sweep, title check or any original scorer. No frame, count of held-out assignments,
held-out OCR, human label, or actual sample is inspected during this preparation.

Let A be every held-out page the sweep named one of the five approved families, **including
both title-confirmed and title-rejected assignments**. Include all A, without subsampling.
Let U be only pages the sweep classified `unsupported` (set aside by the classifier).
From U sorted lexicographically by page ID draw 500 without replacement with
`random.Random(4005).sample(sorted_U, 500)`. If fewer than 500 exist, take all and report it.
The final sample is A union that draw, deduplicated and sorted by page ID. Title rejections
are in A and never in U. Failed/unclassified pages are counted separately, not called other
and not used as replacement draws. Freeze this one sample for both Glimmer arms and all
comparisons. No additional page is added based on an answer or a hand-check result.

The sampler is a pure function with `go=False` by default; it raises before examining the
frame. Tests draw only invented synthetic frames. There is no held-out execution command
in this preparation entrypoint and no actual sample manifest is created now.

### Measurements on that shared sample

Report both arms and Muse Spark's original raw and title-confirmed assignments alongside:
per-family TP/FP/FN, precision/recall, supports, confusion counts, failures/invalid answers,
and cost. Proxy reference = pipeline-confirmed family, otherwise `other` for a title
rejection or classifier-set-aside page. Report confirmed pages, title rejections (also by
original assigned family), and sampled classifier-set-aside pages separately.

Report unweighted sample metrics and design-weighted population-proxy estimates separately.
Each A page has inclusion probability 1 and weight 1. Each sampled U page has probability
min(500, |U|)/|U| and inverse-probability weight |U|/min(500, |U|). Weighted TP/FP/FN are
sums of those weights, with precision TP/(TP+FP) and recall TP/(TP+FN); zero denominators
remain undefined. Proxy positives are a census, so proxy-family recall covers all confirmed
pages, but neither proxy recall nor weighted precision is independent human ground truth.
No confidence interval claiming human/population truth is constructed from this teacher check.

Use the owner's existing 50-page hand check only on its intersection with the frozen sample;
report coverage and unavailable/unreadable labels. Do not add pages, relabel, or infer another
family from a binary "wrong assigned family" mark. If the check records actual family IDs,
report exact agreement on that labelled subset. If it records only correctness of the
pipeline's assigned family, report agreement with that binary question and identify predictions
whose alternate family cannot be scored from that mark. Report Muse Spark on the same labels.
This check samples pipeline-confirmed pages: it cannot establish recall outside that frame.
Read only a non-code label export explicitly authorised at go; never open labelling/, an
original scorer, or any tag. Any necessary departure from the original real-pages
pre-registration is recorded in its Deviations section only after separate go, before a run.

### Cost declaration and hard stop

Modal prices checked 2026-10-30: L4 $0.000222/s; four physical CPU cores $0.0000524/s;
32 GiB RAM $0.00007104/s. Explicit CPU/memory caps give **$0.00034544/s ($1.243584/hour)**.
One development benchmark job is limited to 1,800 s plus 300 s startup and 5 s scale-down:
**at most $0.7271512**. Estimate it before launch; record failed jobs and retain their ceilings.
The future shared-sample job is limited to 14,400 s with the same startup/scale-down allowance:
**at most $5.0796952**. One container, no idle service or automatic retries.
The original 64-GiB development request remained unallocated (zero containers), and was
cancelled before any model result. Its $0.8766904 maximum is retained in cost_attempt1.json.
The retry and future phase-2 configuration use 32 GiB host RAM; GPU, batch, prompts and
model settings are unchanged. Retaining all phase-1 GPU ceilings, its $2.50 overhead reserve,
both preparation attempts and the future job totals **$24.313225**, below the $25 project cap. The overhead reserve covers CPU OCR/preparation,
builds/storage/egress and billing lag. The numeric cost bounds and allocation records are saved under
results/glimmer/phase2_preparation/. No completed L4 throughput result is available yet.

The exact sample size N = |A| + min(500, |U|) is unknown until go. For planning only, the
permitted development sweep named 10/178 pages: applying that rate to the 4,569-page population
already stated in PREREGISTRATION_REAL.md suggests about 257 named pages, hence N about 757.
This is an extrapolation, not an inspected held-out count. Report the measured development
seconds per paired page, startup allowance, a 50% throughput margin and cost as a function
of N, with scenarios including the mathematical maximum N=4,569. At go, count the frozen
sample from metadata first. If its conservative forecast exceeds the 4-hour runtime or
remaining cap, stop **before opening OCR or allocating a GPU**; do not silently shrink the
sample, change the prompt or upgrade the GPU. Preparation is not permission to start phase 2.

Sources: https://modal.com/pricing ; https://www.nvidia.com/en-us/data-center/l4/ ;
https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-product-literature/T4%20Product%20Brief.pdf ;
https://dev.meta.ai/docs/muse-glimmer/prompting

### Preparation status at commit

Both development-only L4 requests remained queued: the immediate provider statistics reported
backlog 1, zero containers/runners, and no completed or failed inputs. The second request was
also stopped before any model result. Both reservation ceilings and stopped-app records are
retained; provider-reported additional preparation charges were $0.00 at the recorded query.
No L4 batch-fit/throughput measurement is claimed, and no new development accuracy is claimed.

Thus the current phase-2 **budget bound is $5.0796952**, including four function-hours,
five minutes startup and five seconds scale-down, on one L4 with four CPU cores and 32 GiB RAM.
Conditional bounds are about $1.35 / $2.59 / $3.84 / $5.08 for one / two / three / four
function-hours. These are resource-cost scenarios, **not measured completion-time forecasts**.
A completed development-only L4 batch-fit/timing check remains mandatory before held-out access.
No actual held-out count, sampled page ID, OCR text or hand-check label has been read here.
The original phase-1 0/40 and post hoc 40/40 records remain byte-for-byte unchanged.
