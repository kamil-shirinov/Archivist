# Glimmer phase 2 — aggregate pipeline-proxy comparison

2026-10-31. The raw-output commit **a33ace9bb020e2701769c86c2a8a89a66f22b345** was
pushed to origin/glimmer before the declared parser or any output/reference comparison ran.
The comparison guard verified pushed raw/frozen bytes and unchanged source hashes first.
No human label, cell draw, deep-check record, original scorer or git tag was read. The
owner's 50-page human comparison is deferred; no model was selected for deployment here.

## Summary on the same frozen 791 pages

Reference = pipeline-confirmed family, otherwise `other` for title rejection or classifier
set-aside. These are **teacher-derived proxy labels**, not independent human truth.

| Arm | Agreements | Sample agreement | Design-weighted population-proxy agreement | Invalid / missing |
|---|---:|---:|---:|---:|
| Untrained Glimmer | 708/791 | 89.51% | 97.36% | 0 / 0 |
| Trained Glimmer | 744/791 | 94.06% | 98.97% | 0 / 0 |
| Muse Spark raw | 636/791 | 80.40% | 96.61% | 0 / 0 |
| Muse Spark + title check (reference construction) | 791/791 | 100.00% | 100.00% | 0 / 0 |

Trained sample agreement rises by **4.55 percentage points**, with fewer proxy family
false positives (**83 to 28**), but confirmed-family recall falls from **136/136 (100%)**
to **117/136 (86.03%)**. It misses **19** confirmed positives, including **all 10 total-claims
positives**, eight security-transactions positives and one forward-exchange positive.
This is a precision/recall tradeoff, not an unqualified improvement. No page-level errors
were inspected and no checkpoint, crop, prompt, parser or generation setting was changed.

Spark raw is its saved image-based sweep, a modality difference. Spark plus title check
is exactly how the reference is defined, so its 100% is **by construction**, not an
independent accuracy result. Spark is also the source of the development supervision.

## Confirmed, title-rejected and sampled set-aside strata

Agreements mean correct family for confirmed pages and `other` for the other two strata.

| Stratum | Pages | Untrained | Trained | Spark raw | Spark + title check |
|---|---:|---:|---:|---:|---:|
| confirmed | 136 | 136 | 117 | 136 | 136 |
| title_rejected | 155 | 77 | 127 | 0 | 155 |
| classifier_set_aside | 500 | 495 | 500 | 500 | 500 |

Both Glimmer arms have zero invalid, truncated-output or missing answers. On the 500
sampled classifier-set-aside pages, untrained makes five family assignments and trained
makes zero. This does not establish zero false assignments in the entire set-aside pool.
On the 155 title rejections, untrained retains 78 family assignments and trained retains
28; every retained assignment is the original rejected family, with zero alternate-family
assignments or invalid answers. The proxy treats each as `other`; human correctness of
those family assignments is not established by a failed title check alone.

## Per-family sample precision / recall

Percentages; support is the unweighted pipeline-proxy positive count. `Other` is included
as declared. A zero denominator would be undefined, never a fabricated perfect score.

| Family | Support | Untrained P / R | Trained P / R | Spark raw P / R | Spark + title P / R |
|---|---:|---:|---:|---:|---:|
| Short-term foreign liabilities | 44 | 80.00% / 100.00% | 86.27% / 100.00% | 81.48% / 100.00% | 100.00% / 100.00% |
| Security transactions | 42 | 54.55% / 100.00% | 80.95% / 80.95% | 44.21% / 100.00% | 100.00% / 100.00% |
| Forward exchange contracts | 19 | 70.37% / 100.00% | 69.23% / 94.74% | 70.37% / 100.00% | 100.00% / 100.00% |
| Railroad receipts/expenditures | 21 | 50.00% / 100.00% | 84.00% / 100.00% | 33.33% / 100.00% | 100.00% / 100.00% |
| Total claims by country | 10 | 55.56% / 100.00% | 0.00% / 0.00% | 19.23% / 100.00% | 100.00% / 100.00% |
| Other | 655 | 100.00% / 87.33% | 97.06% / 95.73% | 100.00% / 76.34% | 100.00% / 100.00% |

| Arm | Macro precision (including Other) | Macro recall (including Other) |
|---|---:|---:|
| Untrained Glimmer | 68.41% | 97.89% |
| Trained Glimmer | 69.59% | 78.57% |
| Muse Spark raw | 58.10% | 96.06% |
| Muse Spark + title check (reference construction) | 100.00% | 100.00% |

Raw confusion counts and all metric denominators are in summary.json. Sample TP/FP/FN:

| Family | Untrained TP/FP/FN | Trained TP/FP/FN | Spark raw TP/FP/FN | Spark + title TP/FP/FN |
|---|---:|---:|---:|---:|
| Short-term foreign liabilities | 44/11/0 | 44/7/0 | 44/10/0 | 44/0/0 |
| Security transactions | 42/35/0 | 34/8/8 | 42/53/0 | 42/0/0 |
| Forward exchange contracts | 19/8/0 | 18/8/1 | 19/8/0 | 19/0/0 |
| Railroad receipts/expenditures | 21/21/0 | 21/4/0 | 21/42/0 | 21/0/0 |
| Total claims by country | 10/8/0 | 0/1/10 | 10/42/0 | 10/0/0 |
| Other | 572/0/83 | 627/19/28 | 500/0/155 | 655/0/0 |

## Design-weighted population-proxy estimates

Every named-family page is included with weight 1. Each of the 500 sampled classifier-
set-aside pages represents 4,278/500 = **8.556** pages. Weighted totals therefore represent
4,569 successfully classified pages: 136 proxy family positives and 4,433 `other`.
Weights apply to TP/FP/FN before forming precision and recall; these are estimates against
the pipeline proxy, not human/population truth. All confirmed positives are a census,
so family recall matches the unweighted family recall. No interval claiming independent
human accuracy was constructed from this teacher check.

| Family | Untrained weighted P / R | Trained weighted P / R | Spark raw weighted P / R | Spark + title weighted P / R |
|---|---:|---:|---:|---:|
| Short-term foreign liabilities | 70.34% / 100.00% | 86.27% / 100.00% | 81.48% / 100.00% | 100.00% / 100.00% |
| Security transactions | 45.60% / 100.00% | 80.95% / 80.95% | 44.21% / 100.00% | 100.00% / 100.00% |
| Forward exchange contracts | 70.37% / 100.00% | 69.23% / 94.74% | 70.37% / 100.00% | 100.00% / 100.00% |
| Railroad receipts/expenditures | 42.38% / 100.00% | 84.00% / 100.00% | 33.33% / 100.00% | 100.00% / 100.00% |
| Total claims by country | 39.13% / 100.00% | 0.00% / 0.00% | 19.23% / 100.00% | 100.00% / 100.00% |
| Other | 100.00% / 97.28% | 99.57% / 99.37% | 100.00% / 96.50% | 100.00% / 100.00% |

## Title-check rejections by original assigned family

Counts predicted `other`, agreeing with the declared negative proxy:

| Original assigned family | Rejected pages | Untrained | Trained | Spark raw | Spark + title check |
|---|---:|---:|---:|---:|---:|
| Short-term foreign liabilities | 10 | 0 | 3 | 0 | 10 |
| Security transactions | 53 | 20 | 45 | 0 | 53 |
| Forward exchange contracts | 8 | 0 | 0 | 0 | 8 |
| Railroad receipts/expenditures | 42 | 22 | 38 | 0 | 42 |
| Total claims by country | 42 | 35 | 41 | 0 | 42 |

## Frozen setup, interruption and approved recovery

Before any draw, independent checks of the permitted sweep/classification/title records
matched **291 named = 136 confirmed + 155 rejected**, plus 4,278 classifier-set-aside pages
and no failures. A single seed-4005 draw of 500 set-aside pages froze **791** page IDs.
Both arms used the identical original order and the same first **1,024 Unicode OCR
characters**. There were 78 empty inputs and 370 truncated inputs; none was dropped.
No sample was redrawn, and no held-out image was opened or rendered. No extra OCR was
opened during recovery. Only sweep.json, sweep.jsonl and titles.jsonl were read from the
held-out results directory. The 5,120-character proposal was not adopted.

The first app, **ap-90heG0Xt09CZ8lLTAhSns9**, stopped on client disconnection after
**79/99 observed complete untrained batches (632 pages)**. The original wrapper saved
only at full-arm completion, so **no answers survived** and the trained arm never started.
That checkpoint granularity was an implementation mistake. No lost answer was scored,
inferred from logs or fabricated. The failed attempt remains in interruption.json,
interrupted_billing.json, the paid-call ledger and the retained budget in full.

The owner approved raising the retained ceiling to **$28.16** and rerunning the missing
raw batches with the same setup. The separately frozen recovery used the unchanged
native generator at the original batch memberships and tensor order, with atomic volume
commits after each batch and detached execution. Because zero answers survived, all
**99 untrained batches were recomputed**, and all **99 trained batches ran for the first
time**. Current checkpoint counts are 0 reused / 99 new per arm. All 198 complete batch
files are present in the volume. This is one approved recovery, not a search or selection
on held-out results. Only this task's own recorded apps were stopped/affected; no other
Modal app was stopped by this task.

One L4, four physical CPU cores, 32 GiB host RAM; 10,825-second execution and 300-second
startup hard timeouts, with 15 seconds shutdown allowance. The frozen NF4 base uses double
quantisation and bf16 compute/storage, with all parameters on CUDA. The live record found
720 NF4 modules in both arms. PEFT adapter parameters load as fp32, as in the original
inference setup. The prompt, saved adapter, low reasoning, greedy decoding, batch 8 and
512-new-token maximum were unchanged; the declared parser is native-assistant-header-v1.
No retraining or hyperparameter/length/threshold selection occurred in phase 2.

Recovery runtime: **4,719.192 s untrained**, **919.848 s trained**, **5,717.032 s whole
function**. Peak allocated bytes were 21,006,185,984 / 21,124,666,880; peak reserved bytes
22,951,231,488 / 23,249,027,072. Both arms completed all batches on the L4. Detailed
precision, runtime and memory data are in the unchanged raw_manifest.json. That manifest's
"not run yet" parser/comparison flags record its creation before the raw commit; summary.json
records the later comparison and the pushed raw commit ID.

All **34 preserved phase-1 artifacts** remain byte-for-byte unchanged, including strict
trained **0/40** and the separately labelled **post hoc diagnostic 40/40**. The development
check remains 39/40 for both models on the 1,024-character L4 setup. These are separate
measurements; none was retrospectively replaced by this held-out result.

## Cost including the failed attempt

| Cost item | Reported dollars |
|---|---:|
| Interrupted first phase-2 attempt | 1.21407010 |
| Completed recovery | 1.98611708 |
| Phase 2 combined | **3.20018718** |
| Preserved phase 1 + development charges | 1.54829339 |
| Cumulative Glimmer | **4.74848057** |


These are app-specific Modal resource charges at the saved query, subject to billing lag;
no other task's charges are included. See completed_billing.json. The recovery registry/
cache/budget call separately logged **$1.97489156** of measured function-runtime compute,
excluding some startup/transport; it is not a reconciled invoice. The interrupted job's
token usage was unrecovered and is explicitly labelled unknown in its ledger entry.
Both paid events were appended once to the project ledger.

Recovery estimates before submission were **$2.2952 expected / $3.3232 conservative**,
including checkpoint I/O. Its entire **$3.8482016** maximum remains retained, as does the
interrupted job's maximum and every earlier retained maximum/overhead. Combined retained
bound is **$28.1581522**, below the explicitly approved **$28.16** ceiling. No automatic
extra retry is funded. Rates were checked at https://modal.com/pricing . The completed
recovery app, **ap-Sw3Cab71JzfWFel9XEyGUI**, is stopped, with zero runners, inputs and backlog.

## Verification and stopping point

The raw-output Check passed **1,152 tests**, with all 11 runs and both exports replayed
identically and the ledger unchanged at 81,154 lines. Pre-commit passed. Raw outputs
were committed and pushed as a33ace9 before the comparison guard allowed parsing/scoring.
The final comparison Check is recorded in FINAL_CHECKS.md. The existing sparse exclusions
of tests/test_labelling.py and tests/test_score.py remain; neither prohibited package was
restored or executed. No source/model/generation/metric definition was changed after freeze.

This report contains aggregate numbers only, with no page-level error analysis or model-
guided tuning. Stop here. The owner's 50-page human comparison will be a separate task,
after the authorised file is committed on main; no such file or label was read here.
