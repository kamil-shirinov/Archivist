# P34 — Spark Open archive-reader attempt: no adapter qualified

**The GPU job timed out loading the BF16 base. No optimizer update, adapter,
checkpoint or validation prediction was produced. Keep the existing base reader.**
No fine-tuning gain or held-out result is claimed. No further GPU attempt fits the
remaining budget at the observed loading rate.

The frozen experiment was committed before launch (final runtime commit
`5ce375d`). Its detached call `fc-01M6A9Y805QG5J1VTP8M0K00DC` was submitted
2026-11-01 01:00:18 UTC; its app finished at 02:18:23 UTC. The synthetic native
BF16 expert-gradient test passed, but the last loader progress was **364/2,000
weight tensors (18%)** after about 75 minutes. The function reached its 4,650-second
hard timeout during `from_pretrained`, before `loaded.json` or base inference.
Only `identity.json` and `gradient_preflight.json` were saved. Checkpointing after
every optimizer update was implemented; there were no updates to checkpoint.
Failure evidence is in `training/failure_summary.json` and `gradient_preflight.json`.

The owner's two additions were added to PLAN.md on 2026-11-01 **after this GPU job
had launched and timed out**, before this post-attempt cached comparison. Training
itself never began. Glimmer's branch/files/apps were not changed. No held-out
page content or owner labels were opened. A real-scan run requires its own separate
pre-registration afterwards and is outside this task.

## Fixed development data and three-reader comparison

The coverage rule preceded the development OCR census. Validation is **15 fixed
pages / 270 OCR-supported figure fields**, three pages in every approved Treasury
family/layout. Each of the five families has one supported portrait single-panel
layout; per-layout counts/signatures and per-page details are in
`training/comparison_v2/comparison.json` and `validation_v2/draw.json`. This does
not claim coverage of unknown or unapproved archive layouts. One claims page has
only one supported figure and remains in the frozen draw.

Withdrawing all three claims pages for validation left **283 two-host-plus-OCR
agreed training answers**, 37 conversations on three development pages: security,
forward exchange and railroad. There were no short-term or claims training
examples. Teachers were the same open model on two independent hosts, so agreement
is correlated pseudo-supervision. All target boxes came from OCR. Planned training
was attention-only rank-16 LoRA, one epoch, five accumulated optimizer updates.

| Reader | Completed validation coverage | Result |
| --- | --- | --- |
| Fine-tuned Muse Spark Open | 0/15 pages | No adapter; every family unavailable |
| Matching untrained local BF16 Muse Spark Open | 0/15 pages | Loading timed out; every family unavailable |
| Cached hosted Muse Spark 1.3 | 8/15 pages, 133 fields | Cached context below; no new Meta call |

Unavailable local arms are **not scored as zero or as empty**. There is no
completed paired base/adapter evaluation, so the adoption gate fails. The gate
still requires strict pooled improvement in both value accuracy and full-figure
containment, no regression in any family/layout, and at least three scorable pages
per layout. Hosted 1.3 never substitutes for that gate.

Cached 1.3 results on the frozen requested fields (counts, not whole-table accuracy):

| Family / supported layout | Available pages | Values matching reference | Full figure contained | Empty/missing usable answers |
| --- | ---: | ---: | ---: | ---: |
| Forward exchange | 1/3 | 20/20 | 0/20 | 0/20 |
| Railroad | 2/3 | 32/32 | 13/32 | 0/32 |
| Security transactions | 1/3 | 20/20 | 10/20 | 0/20 |
| Short-term liabilities | 1/3 | 20/20 | 2/20 | 0/20 |
| Claims by country | 3/3 | 41/41 | 0/41 | 0/41 |
| Pooled cached subset | 8/15 | 133/133 | 25/133 | 0/133 |

**Reference conditioning:** these eight pages' selected values came from the same
cached 1.3 read plus unique OCR agreement. Consequently 133/133 value agreement
and zero empty selected values follow from reference construction; they are not
an independent accuracy/abstention estimate. Figure containment uses the original
model box against the OCR figure, without OCR replacement. These are OCR proxies,
not human labels. No missing cached page is replaced or treated as a model error.

To expose empties outside that selected subset, counts among **all returned figure
fields** on those same available pages are below. Legitimately blank printed cells
can be included; omitted rows are unknown. These denominators differ from the
OCR-reference subset and do not establish whether an empty answer is an error.

| Family | Returned null/blank/abstained figure fields |
| --- | ---: |
| Forward exchange | 78/390 |
| Railroad | 0/170 |
| Security transactions | 156/780 |
| Short-term liabilities | 130/650 |
| Claims by country | 168/2232 |
| Pooled | 532/4,222 |

P33's pre-existing Baseten Open read overlaps the draw on only **1982-06_p094**.
The approved template is byte-identical between P33 and this checkout. On the
same twenty frozen fields of that page:

| Historical reader | Values matching reference | Full figure contained | Empty/abstained |
| --- | ---: | ---: | ---: |
| Untrained Open, P33 Baseten cache | 0/20 | 0/20 | 1/20 |
| Hosted Muse Spark 1.3 cache | 20/20 | 0/20 | 0/20 |

This supplementary comparison is reference-conditioned, uses historical full-table
prompts, and has no established checkpoint/decoding equivalence to the local BF16
base. It is not a replacement base arm or evidence of a fine-tuning gain. The Open
cache had 142 null/blank/abstained fields among all 744 returned figure fields on
that page. Exact source hashes, raw cached values, per-family/layout scores and
empty/missing/invalid distinctions are saved under `training/comparison_v2/`.

## Cached boxes: no reusable conversion found

Only P33 cached page reads from the pinned `openw-measure` commit were used; no new model call.
The rule was written in BOX_PLAN.md before OCR matching. The existing parser already converts
the requested 0–1000 grid into image pixels with outward rounding (`ledger.grid_to_bbox`).
Undoing or repeating it does not repair the saved boxes.

| Host | Development page | Anchors | Median model minus OCR (x, y px) | Full figure contained | Page-fitted affine on separate anchors |
| --- | --- | ---: | ---: | ---: | ---: |
| baseten | 1939-01_p051 | 317 | (-39.0, 197.5) | 0/317 | 16/64 |
| baseten | 1939-01_p055 | 258 | (-119.0, 103.2) | 0/258 | 27/52 |
| fireworks | 1939-01_p055 | 269 | (26.0, 113.0) | 5/269 | 28/54 |
| baseten | 1939-01_p061 | 214 | (-56.0, 107.0) | 2/214 | 29/43 |
| fireworks | 1939-01_p061 | 214 | (51.5, 16.5) | 0/214 | 7/43 |
| baseten | 1939-08_p043 | 15 | (-17.5, 16.5) | 4/15 | 0/3 |
| fireworks | 1939-08_p043 | 15 | (-6.0, 78.5) | 0/15 | 0/3 |
| baseten | 1982-06_p094 | 199 | (-31.0, 164.0) | 0/199 | 4/40 |
| fireworks | 1982-06_p094 | 153 | (-102.0, 394.0) | 0/153 | 3/31 |

The boxes have page- and host-dependent scale and displacement. A per-page affine fit
reduces centre error on several pages, but its full-figure containment ranges from 0% to 67%;
it requires OCR anchors on the page itself and fails on the railroad page (only three scoring
anchors). It is not evidence for a universal coordinate conversion. Exact fit parameters,
centre-containment rates and errors are in boxes.json; individual matches are in box_anchors.jsonl.

| Conversion | Figures fully contained | Share |
| --- | ---: | ---: |
| identity | 11/1654 | 0.67% |
| undo_grid_conversion | 0/1654 | 0.00% |
| extra_grid_conversion | 0/1654 | 0.00% |
| pdf_points_to_pixels | 0/1654 | 0.00% |
| vertical_reflection | 0/1654 | 0.00% |
| swapped_axes | 0/1654 | 0.00% |
| other_pages_shift | 29/1654 | 1.75% |
| other_pages_affine | 23/1654 | 1.39% |

The cross-page shift and affine fits learn only from other development pages of that host.
No candidate reaches the prewritten 90% containment threshold on every page. No production
box correction is installed. Values are unchanged by every tested transform.

Anchors require unique digit strings (at least three digits) in the full OCR page, one
claim per read and a figure field. This is stricter than P33, which did not exclude repeated
claims or non-figure fields. These are OCR proxies, with punctuation/sign/row-alignment
limitations, not human-scored correctness. Both hosts read the same pages, so 1,654 is a
count of box observations, not independent examples. Fireworks failed on 1939-01_p051;
that missing read remains missing. Nearest-box matching was never used.

## Runtime feasibility, terms and serving

Seven bounded synthetic NVFP4 probes failed before archive inference/training:
package/trust/transport problems, then a tiny-shape backward division by zero and
actual-width timeouts. This establishes no working compressed backward route in
this task, not impossibility for every implementation. The BF16 fallback's 65
weight-shard hashes match Meta's original release; its native expert gradient
preflight passed. Its measured model-loading path does not fit this budget.

[TERMS.md](TERMS.md) records the open-weight fine-tuning grant, licence/policy and
attribution requirements, and Meta API output restrictions. No closed Meta API
output was used for training. Treasury Bulletin provenance records FRASER's
public-domain rights. Development gates precede page/PDF/cache access.

**There is no fine-tuned model to serve.** The earlier proposed $20 Modal batch
forecast assumed a fast load and is invalidated by the observed loading failure.
Do not deploy this BF16 recipe for the open-weights run on that forecast. Keep the
$20 reserve untouched. A future qualifying adapter would require a measured,
affordable loading/serving path on Modal (or independently verified Fireworks image
adapter support), unchanged development gates, then separate real-scan
pre-registration. No endpoint or real-scan job was launched.

Next options are to profile/repair loading on CPU and validate the quantized
backward implementation before another paid full allocation, or retain the hosted
base. Another attempt needs a new costed plan; no further training is started here.

## Cost and cleanup

The pre-launch retained resource ceiling was **$94.2154788 / $95**. After the job
finished, submission time and the provider's app-finished time give a conservative
GPU resource bound of **$77.789834**, including fifteen extra shutdown seconds.
Retaining all CPU attempt ceilings ($4.3754079), all seven synthetic GPU probe
ceilings ($6.025266), a $4 storage allowance and $0.50 build/network/shutdown
allowance yields **$92.6905079**. This is a resource-based conservative estimate,
**not a reconciled Modal invoice**; its timing/rate/cache-footprint assumptions are
recorded in `training/resource_accounting.json`. The failed archive call's GPU
cost bound is recorded in the spend ledger instead of silently recording zero.

Baseten validation-reference reads cost **$0.7237565 / $5**. New Meta calls: **0**.
New Fireworks calls: **0**. Serving spend: **$0 / $20 reserved**.

All recorded Sparkft-owned apps are stopped/confirmed stopped; no other app was
stopped. Its large model cache was removed at 07:13 UTC; the small experiment
metadata is preserved. See `training/final_apps.json` and `cleanup.json`. Main
checkout changes are limited to the original worktree registration/exclude line;
data and credential links are ignored, read-only in use and never committed.

The final exact unpiped Check and pre-commit results are recorded in
`training/final_checks.json`. Push is plain `git push origin sparkft`; no merge.
