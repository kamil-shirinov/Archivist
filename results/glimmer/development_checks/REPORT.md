# Glimmer development checks — 2026-10-30

Development only. No held-out page/result/frame, OCR or owner label was opened; no sample
was drawn. The fallback and reservations were committed in PLAN.md (40763f8) before GPU
submission. One L4 was allocated promptly; L40S was never submitted. The app is stopped
with zero tasks (stopped_app.json). Nothing was retrained or selected on these results.

## Precision and input comparability

Phase 1 and this check use the unchanged pinned `glimmer_runtime.load_model`: 4-bit NF4,
double quantisation, bf16 compute and quantised storage, bf16 unquantised load dtype, SDPA,
all parameters on CUDA. This is a compressed 30B base, not a full-bf16 base fitting 24 GB.
The observed L4 has 23,689,363,456 bytes VRAM (22.06 GiB / 23.69 GB); base footprint is
18,928,972,480 bytes. Actual checks found 720 NF4 linear modules with bf16 compute/storage
and no CPU offload in both arms. The saved adapter is bf16; PEFT's default inference load
promotes adapter parameters to fp32, as the identical phase-1 loader also permits.
Phase 1 did not log every live tensor dtype; same precision is established from its
unchanged loader/configuration, with live module/device evidence added in this check.

Input differs: phase 1 retained 12,000 OCR characters; this check retained 1,024. Sixteen
of the same 40 validation strings change. Phase 1 used H100/batch 1; this check L4/batch 8.
Prompt, base revision, saved adapter, chat template, greedy decoding, low reasoning and
512-output-token limit are unchanged. Both new arms use the prospective declared parser
`native-assistant-header-v1`. Comparability details are in comparability.json.

## Results beside phase 1

| Evaluation | Untrained | Trained |
|---|---:|---:|
| Phase 1, original strict primary | 39/40 | **0/40** |
| Phase 1, **post hoc framing diagnostic** | 39/40 | **40/40** |
| **Development check**, L4 / batch 8 / 1,024 characters / declared parser | **39/40** | **39/40** |

All 34 preserved phase-1 files match their prior SHA256 values (phase1_preservation.json).
No original score, answer or diagnostic label changed. Both new arms have zero invalid
or missing responses. The untrained arm has one false short-term-liabilities assignment;
the trained arm misses the sole total-claims positive, answering `other`. The new result
is not an isolated training-effect estimate: crop, batching, hardware and parser differ
from the original primary evaluation. Do not use it to select another checkpoint or crop.

| Family | Support | Untrained precision / recall | Trained precision / recall |
|---|---:|---:|---:|
| `short_term_foreign_liabilities_as` | 1 | 0.500 / 1.000 | 1.000 / 1.000 |
| `security_transactions_as_reported_by` | 1 | 1.000 / 1.000 | 1.000 / 1.000 |
| `outstanding_forward_exchange_contracts` | 1 | 1.000 / 1.000 | 1.000 / 1.000 |
| `receipts_and_expenditures_under_railroad` | 1 | 1.000 / 1.000 | 1.000 / 1.000 |
| `total_claims_by_country` | 1 | 1.000 / 1.000 | undefined / 0.000 |
| `other` | 35 | 1.000 / 0.971 | 0.972 / 1.000 |

The same saved Muse Spark image-based validation sweep scored 39/40 before its title check
and 40/40 after it. These are pipeline-derived proxy labels: each family has only one
validation positive; `other` has 35. The Spark comparator is also the source of supervision,
not independent ground truth. Detailed confusion counts and raw outputs are in benchmark.json.

## Complete development title-offset audit

Audited the full joined PDF-layer OCR of all **1,596 Treasury development pages**, checking
split membership and resolving/hash-checking the development page before opening its PDF.
No 12,000-character cut was applied to this audit. Offsets below are 1-based Unicode
characters in the original OCR, mapped back from the approved title-check folding.

| Family | Pages matching approved title patterns | Matches starting after 1,024 | Latest start |
|---|---:|---:|---:|
| `short_term_foreign_liabilities_as` | 10 | 0 | 4 |
| `security_transactions_as_reported_by` | 12 | 0 | 4 |
| `outstanding_forward_exchange_contracts` | 12 | 0 | 6 |
| `receipts_and_expenditures_under_railroad` | 4 | 0 | 4 |
| `total_claims_by_country` | 3 | 0 | 41 |

There are 41 approved-pattern occurrences, none starting after or crossing 1,024. Broader
anchors and OCR-context review also found two early short-term title variants missed by
the approved regex, and five early retirement-only headings (a shorter, unapproved variant).
None of those starts after 1,024. No recognized target-family printed table heading was late.
This is an OCR audit, not a visual census: missing/badly corrupted headings can evade matching.
All candidate contexts, offsets, full-page lengths and review decisions are retained in
title_audit.json and title_audit_review.json; no supervision label was changed.

Three **contents-page references** to CM-II-2 Total Claims by Country begin late:

| Development page | Start | Characters beyond 1,024 | End |
|---|---:|---:|---:|
| 1982-06_p011 | 4,235 | 3,211 | 4,257 |
| 1983-06_p011 | 3,166 | 2,142 | 3,188 |
| 1984-06_p011 | 3,088 | 2,064 | 3,110 |

These are references to the table, not pages printing the table. Other late broad-anchor
hits are two narrative phrases, six headings for a different receipts table, and one
CM-IV-4 contents reference. They are separately adjudicated, not counted as target tables.
If the owner wants the excerpt to include the late family-title references too, the proposed
length is **5,120 characters**: latest target-reference end 4,257 plus at least 256 context
characters, rounded up to 1,024. **Proposal only; not adopted.** It requires owner approval
and another development fit/timing check. Today's results and estimates remain for 1,024.
No finite development-based length guarantees held-out coverage.

## Batch fit, timing and measured estimate

All ten batches (five per arm, eight pages each) completed without OOM. Peak allocated:
20,914,915,840 bytes untrained; 21,031,301,120 trained (21.03 GB / 19.59 GiB).
Peak reserved was 21,604,859,904 bytes trained, leaving about 2.08 GB outside PyTorch's
reservation; observed free memory after that arm was 1,828,126,720 bytes. Batch 8 fits
these development prompts but does not guarantee every unseen batch will fit.

Untrained generation: 264.3355 s; trained: 36.6422 s; paired: 300.9777 s for 40 pages,
**7.5244421 seconds per paired page**. Overall model function: 378.4488 s, including
77.4711 s of model/adapter load and other overhead. Client completion was 403.7884 s.
Different output lengths and padding can change throughput on another population.

For N sampled pages, at L4 + 4 physical cores + 32 GiB RAM ($0.00034544/s):

- Expected dollars = (77.4711 + 7.5244421 × N + 300 startup + 15 shutdown) × 0.00034544.
- Conservative forecast multiplies only the page-time term by 1.5 (the declared 50% margin).

| Shared sample N | Expected cost | With 50% timing margin | Fits new retained limit |
|---|---:|---:|---|
| 500 | $1.44 | $2.09 | yes |
| 757 | $2.10 | $3.09 | yes |
| 1,000 | $2.73 | $4.03 | stop |
| 1,500 | $4.03 | $5.98 | stop |
| 4,569 | $12.01 | $17.95 | stop |

N=757 is solely the earlier development-rate planning extrapolation, not a known held-out
count. The actual sample is still every named-family sweep page (confirmed or rejected)
plus 500 classifier-set-aside pages with seed 4005, drawn only after go. Both arms must
use that same sample. The mathematical maximum 4,569 is not feasible within this budget.

The old **$5.0796952** future-job placeholder is superseded. Retaining old failed/cancelled
ceilings plus both new GPU maxima (including the unused fallback) leaves **$20.461749**
retained before phase 2, with **$3.848251** available. The future L4 function may run at
most **10,825 seconds**, plus 300 startup and 15 shutdown: maximum **$3.8482016**.
Combined retained bound is **$24.3099506**, under $24.31. This deliberately leaves very
little extra reservation: no additional GPU call, retry or upgrade is funded.
At this measured conservative forecast, at most **952 pages** fit. After go, check the
actual metadata-only sample size before opening OCR or submitting any GPU; if it fails
this forecast or retained budget, stop without shrinking the sample. Future code must
set this timeout rather than inherit the old 4-hour configuration. The measured estimate
applies only to the L4/1,024-character setup; another GPU or crop needs a new timed
check and budget declaration. No L40S throughput claim is made.

## Cost reconciliation

The new registry/cache/budget-backed call logged $0.13073135 of measured function-runtime
compute in spend_ledger.jsonl and appended the same event to results/spend_ledger.jsonl.
Modal's resource billing reports **$0.14020297** for this app including startup/CPU/RAM/
egress at the recorded query; billing may lag. With preserved phase-1 reported charges
$1.40809042 and the prior preparation's reported zero, cumulative reported charges are
**$1.54829339**. This is separate from the conservative retained maxima above.
Billing rows and query time are retained in billing.json. Both new reservations remain
retained, and overhead reserve covers builds/storage/egress and billing lag. No GPU
service remains running.

## Verification and next step

CPU-only tests exercise the 15-minute allocation gate, cancellation acknowledgement,
allocated/unknown-state refusal, offset mapping and crossing boundary, retained old
reservations, selected-hardware pricing and hard budget stops. Existing tests verify the
declared parser on both models' saved outputs and deterministic sampling on invented frames.
The requested full Check and pre-commit results are recorded in CHECKS.md.
As in phase 1, the sparse checkout excludes tests/test_labelling.py and tests/test_score.py
because they import prohibited labelling/scorer code; neither was restored or executed.

Phase 2 still needs the owner's completed 50-page check and explicit go. A non-code label
export must be explicitly authorised; labelling/ stays closed. No held-out work has begun.
