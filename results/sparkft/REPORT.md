# P34 — Spark Open archive-reader feasibility (development only)

**Stopped before training: the conservative Modal reservation is $106.78, above the $40 cap.**
New spend: Modal $0, Baseten $0, Fireworks $0, Meta $0. No adapter or deployment exists.

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

## Prepared training data and fixed validation

PLAN.md fixes the page rule, targets, method, budget and adoption gate before any training.
Four development training candidates produce **401** unsigned integer/decimal answers:
156 security, 114 forward exchange, 13 railroad, 118 claims. Each agrees between the two
independently issued P33 hosted reads and a unique OCR word; its target box comes solely
from OCR. No whole-table target is fabricated from omitted cells. training_answers.jsonl
stores the answers; data_manifest.json stores source hashes, exclusions and page IDs.

The two teachers are the same model on different hosts, with unidentified checkpoints.
Agreement is correlated pseudo-supervision. There is no short-term-liabilities training
page because its second read failed. No new teacher call was made.

Validation is one lexicographically last evidence page per family (five development pages),
selected by page ID alone. Their images, OCR and answers were not opened here. Reference
construction must be independent of the two evaluated arms; filtering validation to
base-correct/teacher-agreed answers would make a claimed gain circular.

| Arm | Validation value accuracy | Validation full-figure containment | Adoption |
| --- | --- | --- | --- |
| Matching compressed base | Not run: budget stop | Not run | Keep existing base pending a valid comparison |
| Fine-tuned model | Not trained | Not trained | Rejected: no qualifying comparison |

The P33 diagnostic above is not the frozen validation comparison. No fine-tuning gain,
validation baseline or held-out result is claimed.

## Feasibility and options

At [Modal list prices](https://modal.com/pricing), the proposed four-B300 allocation with
16 physical CPU cores and 256 GiB RAM costs $31.197312/hour. Reserving 30 minutes for
base inference, two hours for training, 30 minutes for tuned inference, startup/shutdown
and $5 overhead gives **$106.7812304**. This is an unbenchmarked planning envelope, not
a minimum possible price or reconciled invoice. No paid attempt is justified under $40.

The [published checkpoints](https://dev.meta.ai/docs/muse-spark-open/get-the-model)
are far larger than Glimmer. Its single-H100 recipe cannot fit this base. A four-GPU
NVFP4 serving recipe is not proof that image LoRA training works at that footprint.
The [NeMo image-LoRA reference](https://github.com/NVIDIA-NeMo/Automodel/blob/main/docs/model-coverage/vlm/meta-models/muse_spark_open.mdx)
uses 32 GB200 GPUs. No local compressed image-training implementation was validated here.

Options requiring a separate decision:

1. Keep the hosted base and investigate OCR-anchored per-page calibration as its own
   development experiment; the saved diagnostic identifies promising pages and failures.
2. Obtain a tested compressed image-LoRA recipe and a measured startup/throughput forecast
   whose entire base/train/evaluation reservation fits $40. Shorter timeouts alone do not
   demonstrate that the experiment will finish. Do not substitute Glimmer for Spark Open.
3. Investigate Fireworks pooled NVFP4 LoRA with a separately authorised dollar cap and
   verified image-input support. No unbudgeted Fireworks job is launched by this task.
4. Increase the compute allowance for a validated larger-GPU training route, after
   reviewing its concrete reservation. No increased allowance is assumed.

## Terms, serving and isolation

TERMS.md records the [weight licence](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B/blob/main/LICENSE.md)
and [Meta API terms](https://dev.meta.ai/legal/terms-of-service). Fine-tuning the licensed
open weights is permitted subject to its conditions; closed API outputs do not thereby
become unrestricted training data. No closed Muse Spark output is used for training.

If a later adapter passes both validation gates, serve the same pinned base+adapter on
Modal through archivist.models with bounded lifetime, or use a Fireworks promoted sampler
checkpoint on a dedicated deployment after checking image support and deployment pricing.
The [post-training guide](https://dev.meta.ai/docs/muse-spark-open/post-training) says
private adapters are not served on Fireworks per-token serverless inference. No endpoint
or adapter is created here.

All commands after worktree creation ran inside `.worktrees/sparkft`. Only that worktree
registration and one `.git/info/exclude` line changed the main checkout. Main data links
are used for reading only: real ignored pages/pdf directories contain links to the 15
development issues only. No link is staged. Validation page hashes come from metadata,
not opened validation files. No held-out scan/result or owner label was opened.

The replay cache was staged by exact keys requested by the existing synthetic replay,
never by scanning/opening unrelated shared-cache entries. The initial preparation
reproduced all 11 runs with no spend; it then reported the new, as-yet-unstaged results
as untracked. Final verification stages the task artifacts before the exact Check.
An earlier pytest setup attempt found third-party tests inside the non-hidden uv cache;
moving that cache to `cache/.uv` fixes discovery without excluding repository tests.
No pre-existing test suite is omitted.

Reproduce preparation without paid calls:

```sh
uv run python -m sparkft.boxes
uv run python -m sparkft.prepare
```

The code pins P33 to a commit and records input hashes in the saved artifacts. Review any change to
the source branch before regenerating. No command here launches training.

## Completed verification

The exact unpiped Check passed: **1,169 tests passed**, and all **11** replayed runs
were identical. The spend ledger stayed at 81,148 lines; both committed exports
passed their checks. No repository test suite was excluded. All configured
pre-commit hooks passed. checks.json records the command and counts.
No production file, original result, label, pre-registration or data link is staged.
The provider's final app inventory is empty (modal_apps.json); no Modal job was launched.
