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
