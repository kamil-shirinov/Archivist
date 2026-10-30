# Phase-2 preparation — no go yet

Declared protocol: ../PLAN.md, "Declared phase-2 amendment".

- Parser accepts both models' native frames and retains strict exact-label matching.
- Both models use the same first 1,024 OCR characters, original prompt, low reasoning,
  greedy decoding, 512-new-token limit and length-sorted batches of eight.
- L4 is the lowest-priced GPU candidate with enough memory for the observed phase-1 peak.
  T4's 16 GB is below that peak. L4 batch-eight fit is not yet verified.
- At go only: include every family-named sweep page, confirmed or title-rejected, plus
  500 classifier-set-aside pages sampled without replacement with seed 4005.
- One frozen sample is shared by both models; report sample and design-weighted proxy
  precision/recall, title-rejection behaviour, Muse Spark and hand-check coverage separately.
- No sample was drawn, held-out frame counted, or held-out result/page/OCR/label read.

## Cost estimate and outstanding check

One L4 + four physical CPU cores + 32 GiB host memory costs $1.243584/hour at the checked rates.
With 300 seconds startup and five seconds scale-down:

| Function time | Resource cost bound |
|---|---:|
| 1 hour | $1.35 |
| 2 hours | $2.59 |
| 3 hours | $3.84 |
| 4 hours | $5.08 |

The planned GPU job has a $5.0796952 ceiling and must stop at four hours. Including all
retained phase-1 and preparation ceilings and the $2.50 overhead reserve gives $24.313225.
Provider-reported additional preparation charges are currently $0.00; phase-1 charges remain
$1.40809042. Billing may lag. Read estimate.json and billing.json for precise provenance.

**There is no measured L4 completion-time estimate yet.** Two development-only requests
(64 GiB then 32 GiB host RAM) stayed queued, with no containers. Both were stopped so they
cannot begin later. No GPU inference ran and no new accuracy result was produced.

Before held-out access, complete a development-only L4 fit/timing check and budget its new
reservation with all earlier records retained. After go, use the actual sample count in
phase2_cost.require_budget_fit; it applies a 50% throughput margin and refuses a forecast
above the four-hour limit or $25 project cap. Never silently reduce the sample or upgrade GPU.
The development-rate example N≈757 is not an inspected held-out count. No automatic retry is
implemented; archive cancelled-attempt records and recheck the combined budget explicitly.

## Checks

`uv run pytest -q && uv run python -m archivist.replay`

1,129 tests passed (55.27 s). The two prohibited labelling/scorer suites remain excluded by
sparse checkout. Replay reproduced all 11 existing runs and both exports, with 81,151 ledger
lines before and after. Pre-commit passed. Phase-1 artifact hashes were checked unchanged,
including the trained strict 0/40 and explicitly post hoc 40/40 diagnostic.

No change was made to the original scorer, labelling code, any tag, original pre-registration,
or main-checkout files. This preparation is not permission to start phase 2.

Sources: https://modal.com/pricing ; https://www.nvidia.com/en-us/data-center/l4/ ;
https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-product-literature/T4%20Product%20Brief.pdf
