# P34 — Spark Open archive reader, development only

Written 2026-10-31 before any training, new hosted inference or validation scoring.
The earlier cached geometry diagnostic is governed separately by BOX_PLAN.md.
**Decision: do not allocate a GPU. The conservative Modal experiment estimate
exceeds the owner's $40 cap. No fine-tuned model is eligible for use.**

## Page rule, before applying it

The population is the five approved Treasury families in config/real_test.toml.
For each family, sort the development page IDs in its committed template evidence;
reserve the lexicographically greatest page for validation. Never choose a page
using its values, boxes, OCR quality or model score. Training candidates are only
P33's cached pages where both Baseten and Fireworks returned a successful page
read, excluding any validation page. No replacement for a failed read, no new
teacher call. Check every ID against data/real/split.json before response/image/PDF
access. Keep the complete validation page even if no scorable figure can be found.
Refuse duplicate image hashes across the two sets. Freeze IDs and input/response
hashes in data_manifest.json; freeze eligible answers in training_answers.jsonl.

The rule gives these training pages:

- 1939-01_p055 — security transactions
- 1939-01_p061 — outstanding forward exchange contracts
- 1939-08_p043 — railroad receipts and expenditures
- 1982-06_p094 — claims by country

The fixed validation slice is:

- 1939-12_p053 — short-term foreign liabilities
- 1939-12_p055 — security transactions
- 1939-12_p060 — outstanding forward exchange contracts
- 1939-12_p025 — railroad receipts and expenditures
- 1984-06_p058 — claims by country

1939-01_p051 is excluded from training: P33's Fireworks read failed. Thus this
small pilot has no short-term-liabilities training page. No replacement examples are invented, and no claim of broad generalisation is made.
Validation images/OCR and reference answers remain unopened at the budget stop.

## Training answers and reference limitations

Use only non-abstained figure fields with identical canonical numerical answers
in the two separately issued hosted page reads, at least three digits, a unique
matching word in the whole page's OCR layer, and a single field claiming that
word. Use unsigned integer/decimal tokens only; exclude signs and footnotes rather
than inferring them. Record raw teacher values, canonical value, raw OCR text, OCR word box,
page/field IDs and source response hashes. No nearest-word matching or model box
is allowed to choose the target box. Exclude blanks, uncertain signs, one/two-digit
figures, OCR disagreements and repeated figures rather than inventing labels.
Use the OCR box in original page pixels, converted outwards to the prompt's
0–1000 grid only when rendering the assistant answer. The image remains the input;
do not give the model OCR answers in its prompt. Train on selected cells, with
explicit requested row/column IDs, and loss only on their assistant answer tokens;
never fabricate the excluded cells in a complete table target.

These are **independently issued reads on two hosts of the same model**, not two
independent models or human ground truth. P33 does not identify their underlying
checkpoint revisions. Agreement plus OCR is development pseudo-supervision with
selection bias. Do not use closed Muse Spark API outputs as training targets.
The stored answers are preparation artifacts, not evidence training took place.

For future validation, build references from the validation PDF's OCR and printed
row/column alignment independently of either arm's answer; ambiguous alignments
remain unscorable and counted. Do not filter validation down to figures the base
already got right. Freeze references before evaluating the base. Report reference
coverage and exclusions by page, alongside every requested figure (missing/invalid
answers count as wrong; missing/invalid boxes fail containment). Only OCR-backed
references can be scored without authorised human labels; never access the owner's
labels. No such reference set or validation score is claimed in this stopped task.

## Method and decision rule

Preferred investigation: frozen compressed Spark Open base with LoRA rank 16,
alpha 32, dropout .05 on language q/k/v/o projections; freeze vision and experts.
Three epochs, learning rate .0002, seed 3401, microbatch 1, accumulation 8,
assistant-only loss, maximum 4096 rendered tokens per selected-cell example.
Reject examples whose complete image/prompt/answer exceeds that length; report
coverage. No validation-guided hyperparameter search or best-checkpoint selection:
use the final adapter. A working image-capable compressed training implementation,
pinned base revision, libraries and processor must be established before launch.
A GGUF inference footprint alone does not establish trainability.

Both arms must use that same pinned compressed checkpoint, processor, image
resolution, prompt, cell requests, low reasoning, greedy decoding, token allowance
and strict final-answer parser, through archivist.models registry → cache → budget
→ backend. Save raw answers and failures. Evaluate the base before training; reload
the final adapter and evaluate on identical validation inputs. Neither P33 hosted
model is a substitute for the matching local compressed base.

Primary value metric: exact canonical numerical value accuracy over the frozen
scorable figure requests. Primary box metric: the predicted box fully contains the
OCR figure box in page pixels; report centre containment separately. Value accuracy
and full containment must **both strictly exceed the base**, pooled and with all
per-page counts shown. A tie or a missing comparison rejects adoption. Also report
joint correct-value-and-containing-box counts, reference coverage, invalid answers,
latency and cost. No fine-tuned arm runs or is selected until this gate is measured.

## GPU and budget estimate: stop before training

This is an 816B-parameter MoE, not Glimmer's 30B checkpoint. All experts must be
resident or sharded even though only 42B parameters are active per token. The
published compressed checkpoint is about 537 GB, so the single-H100 Glimmer
recipe cannot be reused. Meta documents NVFP4 serving on four B300 GPUs; a
published image-LoRA BF16 recipe uses 32 GB200 GPUs. Neither is evidence that
local NVFP4 image LoRA works on four GPUs.

For a *conditional compressed implementation*, plan one four-B300 container,
16 physical CPU cores, 256 GiB host RAM. At Modal's checked list rates:
4 × .001972 + 16 × .0000131 + 256 × .00000222 = **$.00866592/s**
(**$31.197312/hour**). Reserve baseline 1,800 s, training 7,200 s and tuned
validation 1,800 s, each with 300 s startup and 15 s shutdown allowance, no retries.
Compute ceiling = 11,745 × .00866592 = **$101.7812304**, plus $5 overhead reserve
for build/storage/CPU preparation = **$106.7812304**. These runtime allowances are
conservative planning assumptions, not measured throughput, a quote or a lower
bound. Shorter runs may be possible; no evidence currently supports completing
all stages under $40. The documented BF16 multi-node path costs still more.

Therefore **stop**, as the owner requested for an estimate above $40. No paid
preflight, model download, training or fresh validation is launched. Modal new
spend $0; Baseten new spend $0 of $5. No Fireworks or Meta spend is authorised by
this plan. Any future job must reserve its entire worst-case cost before launch,
set a hard execution/startup timeout, one-container cap, no automatic retry and
short scale-down, and be explicitly stopped on success or failure. All Modal apps
must be stopped before this task ends.

## Terms and serving

See TERMS.md for the checked licence, API-output restriction and public-domain
data basis. No blanket permission to train on closed API outputs is inferred.
If subsequently trained and accepted, Modal would load the identical pinned base
and adapter on a proven image-capable sharded runtime, expose an ephemeral endpoint
through archivist.models, and stop after the run. Fireworks is another potential
route: verify image-input training and account access first, then promote a sampler
checkpoint and provision a dedicated adapter deployment. Its per-token serverless
training pool does not imply per-token serverless serving of a private adapter.
No adapter, endpoint or serving capacity is created here.

Sources checked 2026-10-31:
https://dev.meta.ai/docs/muse-spark-open/get-the-model ;
https://dev.meta.ai/docs/muse-spark-open/post-training ;
https://github.com/NVIDIA-NeMo/Automodel/blob/main/docs/model-coverage/vlm/meta-models/muse_spark_open.mdx ;
https://modal.com/pricing

## Completion checks

Run the owner's Check unpiped:
`uv run pytest -q && uv run python -m archivist.replay`

Stage only sparkft/, results/sparkft/ and its offline tests; never stage a data link,
cache, environment or existing result. Run pre-commit cleanly, commit as P34, and
push with exactly `git push origin sparkft`. Never merge. This plan is committed
before any training; the cost stop means no training follows in this task.
