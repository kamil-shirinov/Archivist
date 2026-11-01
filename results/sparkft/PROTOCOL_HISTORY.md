# P34 — Spark Open archive reader, development only

Written 2026-10-31 before any training, new hosted inference or validation scoring.
The earlier cached geometry diagnostic is governed separately by BOX_PLAN.md.
**Original decision (superseded by the owner-approved amendment below): stop
under the original $40 cap. No model had been trained at that decision.**

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
short scale-down, and be explicitly stopped on success or failure. Only Modal apps started by this task may be stopped. Never stop the concurrent
Glimmer task or any other app.

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
before any training. The amendment below authorises the bounded training attempt.


## Owner-approved training amendment — 2026-10-31, before training

The owner now authorises **$95 total Modal credits for preparation, training and
validation**, with **$20 kept separately for serving** an accepted adapter in the
later open-weights run. Baseten remains capped at $5; no new hosted call is
planned. No Fireworks/Meta spend is authorised. The previous $40 stop and its
three separately loaded GPU jobs are superseded. Preserve the original diagnostic,
401 training answers, four training pages and five fixed validation pages.
The serving reserve cannot fund training, retries, validation or debugging.

### Allocation and cost limits

Combine matching-base validation, training, adapter save/reload and tuned validation
in one four-B300 allocation so the large frozen base loads only once. Use one
container, 16 physical CPU cores, 256 GiB hard-capped RAM, execution timeout 9,600 s,
startup timeout 300 s, shutdown/transport allowance 15 s, no automatic retries,
no warm containers, and five-second scale-down. The checked resource rate remains
$.00866592/s. Reserve **(9,600 + 300 + 15) × .00866592 = $85.9225968** before launch.
Retain that whole reservation for any failed/aborted attempt; a failure does not
silently release money for a retry. Add **$5** for CPU preparation, builds and
storage: retained maximum **$90.9225968**, leaving **$4.0774032** under $95.
This is a hard experiment ceiling, not evidence that the run will finish on time.

CPU metadata/download preparation uses task-owned resources with hard timeouts:
at most 1,800 s execution, 60 s startup, 15 s shutdown, eight physical cores and
64 GiB hard-capped RAM, one container, no retries, at $.00024688/s: at most
$0.4629, charged inside the $5 preparation reserve. Stop before any allocation
whose full reservation would exceed its envelope. Do not replace a failed compressed
runtime with an unbudgeted BF16 cluster. Persist stage progress and any completed
base results/adapter before shutdown. A partial run cannot pass the adoption gate.

Official BF16/NVFP4 repositories currently require gated access; no Hugging Face
token is configured. Public Unsloth mirrors are available without credentials.
Pin the NVFP4 candidate `unsloth/Muse-Spark-Open-816B-A42B-NVFP4` to
`fc6908f53c6882d4ec48fca5ba144e41d21e1f92`. Pin its official Transformers
integration candidate to `585946e8dbfc114a5f45e62b41e35a468e9e85b9`.
Check licence/processor parity and kernel gradient support on CPU first. This
candidate is not presumed trainable merely because it can serve. If its kernels
cannot backpropagate into language attention adapters, establish a documented
trainable compressed path and commit that loader amendment before training;
do not misreport an inference-only run as training. Do not substitute a smaller
model. Keep the original LoRA settings unless an explicit prospective amendment
is committed before a run, with its reason and cost impact.

### Validation references and framing, before either arm

Prepare and freeze validation references before running the compressed base.
Reuse only existing development Muse Spark 1.3 page reads through the zero-cap
registry/cache/budget path, where available, to assign semantic row/column IDs;
match those figures to unique, exact canonical numbers in the PDF OCR layer.
These closed-model outputs are used for evaluation only, never as training data.
They are independent of both evaluated Spark Open arms, although still model-assisted
OCR proxy references rather than human truth. Record provenance and coverage;
do not select by the evaluated base's answers or boxes. Any absent cache entry
aborts rather than making a paid teacher call.

Use at most 20 scorable figures per validation page, sorted by SHA256 of
`sparkft-validation-3401:<field_id>`, taking the first 20; retain a page with fewer
figures and report its support. This limits inference time while preserving the
fixed page slice. Freeze field IDs, OCR boxes, reference values, prompts, processor
settings and image hashes before base inference. Retain missing/unscorable coverage.
Decode the final native assistant-to-user channel only, handling an already-open
assistant header prospectively for both arms. Reasoning alone, malformed JSON,
truncation and missing cells are failures. No parser repair after seeing results.
Both value accuracy and complete OCR-box containment must strictly beat the base;
otherwise the adapter is not used. Report every page, failures and joint correctness.

### Serving the accepted adapter: separate $20 reserve

Use **Modal**, with the same pinned compressed base, image processor, adapter,
prompt, strict parser and native precision that pass validation. Save adapter
safetensors, configuration and hashes to task-owned storage; preserve licence,
usage policy and attribution. Reload that exact adapter during validation.
Serve via a task-specific ephemeral Modal function registered in archivist.models,
wrapped by the normal cache and budget layer. Model requests contain only the
permitted image and prompt, never local paths or reference answers. No Fireworks
adapter deployment or extra provider bill is assumed.

The future serving reservation is one four-B300 container with the same CPU/RAM
caps, at most **1,800 s execution + 300 s startup + 15 s shutdown**, compute ceiling
**$18.3284208**, plus **$1.6715792** reserved for storage/CPU overhead, total **$20**.
Keep min_containers=0, max_containers=1, automatic retries=0 and short scale-down;
enforce the aggregate lifetime as well as each call's timeout. This is about 30
execution minutes, not a claim the complete open-weights run fits. Measure throughput
on development requests, forecast the later run and refuse a run exceeding the
reserve before opening any newly authorised data. The current task remains
**development only** and does not launch the later open-weights run or a standing
endpoint. If validation fails, preserve the reserve and serve the existing base.

### Task ownership and cleanup

Use app names prefixed `archivist-sparkft-p34-` and unique run IDs. Record each
server-returned app ID in this task's ledger immediately at creation. Cancellation
and stop code must accept only IDs in that ledger; never stop by an app-name search
or by enumerating and stopping the workspace. The concurrent Glimmer app is outside
this task's ownership and must remain untouched. Record owned-app termination on
success, failure, timeout or allocation cancellation; do not require an empty
workspace app list. All model calls continue through archivist.models.

Commit this amendment after the exact Check and clean pre-commit, **before training**.
Commit and push completed artifacts on sparkft without merging. Runtime, allocation,
billing estimates, actual reported usage and retained ceilings must be distinguishable.

### Concrete runtime protocol — before the GPU attempt

The public mirror's 127 weight-shard hashes equal the official release's public
hashes (training/weight_provenance.json). Keep that exact NVFP4 base and its frozen
BF16 attention/perception layers; no re-quantisation, smaller replacement, CPU
weight offload or library guard override. The official fine-grained integration
routes gradient-bearing operations to its Triton kernels. Its quantizer advertises
`is_trainable=False`; we do not change that flag or train packed weights. Use a
plain PyTorch AdamW loop over PEFT attention-adapter parameters only, rather than
asking Trainer to update a quantized base. Before loading the full base, test
finite, nonzero input gradients through synthetic frozen NVFP4 experts on the
selected GPU. This test contains no archive example and makes no optimizer update.
If it fails, the training route fails; record the failure and do not invent a result.

Use a fixed single-process model partition: language layers 0–15 / 16–31 / 32–47 /
48–61 on GPUs 0 / 1 / 2 / 3; perception and embeddings on GPU 0, final norm and
language head on GPU 3. The checkpoint's packed experts remain in NVFP4. Disable
DeepGEMM dispatch and use the integration's eager experts path for gradients;
retain SDPA and bf16 compute. Record actual placement, quantized module classes,
dtypes, trainable names and peak memory. The allocation and $90.9225968 ceiling
above are unchanged. Kernels 0.18.0, Torch 2.15.0, torchvision 0.29.2, PEFT 0.21.2,
Accelerate 1.15.0, safetensors 0.8.0, Pillow 13.0.0 and huggingface_hub 2.4.0 are
pinned alongside the Transformers commit already declared.

Pack consecutive requested training cells from the same page in groups of up to
eight, sorted by field ID: **52 conversations containing the original 401 answers**.
This amortises the unchanged full-page image; no answer is added or dropped.
Use the same table-layout prompt form for validation, with all frozen requests
on each validation page. Keep microbatch one, three epochs and accumulation eight;
flush and normalise the final partial group of each epoch. AdamW learning rate
.0002, weight decay 0, gradient norm cap 1, deterministic Python/Torch seed 3401,
no scheduler, no hyperparameter search and no intermediate validation. Save only
the final adapter and reload it before tuned inference. Verify nonzero finite
adapter gradients and refuse any trainable non-adapter parameter.

Increase the original preliminary 4096-token context ceiling to **16,384 rendered
tokens**, prospectively, to accommodate full-page image tokens plus table layout.
Use **4,096 new tokens** for both validation arms. Keep the checkpoint processor's
native image preparation; do not choose image resolution from an answer. CPU-only
tokenisation checks all 52 training conversations and five validation requests
before allocating a GPU. Reject oversized examples explicitly; never truncate a
target. Inference receives only the explicit prompt, system and image, never
reference values or boxes. Assistant-only loss masks the complete native prompt
prefix, including image tokens. The same strict native framing parser is fixed
in sparkft/scoring.py before either arm.

The frozen independent validation proxy has supports **20, 16, 20, 20 and 1**
(total **77**). The low support for claims is retained and reported, not replaced.
Its cached Muse Spark 1.3 outputs are evaluation inputs only. dataset.json fixes
prompts/page hashes/field IDs; the five *_reference.json files preserve exact OCR
pixel boxes. No evaluated Spark Open output has been seen. The dataset hash is
`2f55939051eafdf9bed3c1ec79d5dbadba42e35a8c1eb0021bf47be67cb08f79`.
Report box area relative to its OCR figure as a secondary diagnostic, so a very
large enclosing box is visible. The two strict adoption gates remain unchanged.

The first CPU inspection failed on missing torchvision before GPU use. Its full
$0.4629 ceiling is retained; the corrected CPU download/tokenisation attempts
remain inside the original $5 overhead reserve. Task-owned base-cache files will
be removed after recovery/validation; preserve only adapter/provenance artifacts
on the task-owned volume. This prevents indefinite storage charges for hundreds
of GB. Future serving first stages the identical pinned base on CPU, then loads
the saved adapter on the bounded four-B300 Modal runtime; preparation, storage
and serving together must fit the separately protected $20 reserve. Retain adapter
hashes locally even if tensors stay on the task-owned Modal volume rather than
in Git. No serving app is launched by the development experiment.


One prospective bounded **synthetic gradient preflight** is added before the full
four-GPU allocation, while CPU weight staging proceeds. It uses one B300, four
physical CPU cores, 16 GiB hard-capped RAM, 300 s execution, 60 s startup and 15 s
shutdown, one container, zero retries: **$0.77247** worst case. It touches no archive
page or target. Retain this ceiling even on failure. The combined retained ceiling
is now **$91.6950668**, below $95, with the $20 serving reserve unchanged. If the
kernel fails, do not launch the large training job. The synthetic check runs again
inside the eventual full allocation before any archive optimizer update.


### Compatibility correction before archive training

The first synthetic B300 probe stopped before any matrix multiplication: the
pinned Transformers integration requires `0.17.2 <= kernels < 0.18.0` and rejected
the initial 0.18.0 package. Pin **kernels 0.17.2** for the corrected probe and full
runtime. Keep the failed probe's entire $0.77247 reservation and allow one explicitly
recorded corrected probe at the same ceiling. Retained maximum is now
**$92.4675368**, still below $95; the $20 serving reserve is unchanged.
No optimizer update or archive inference occurred in that failed probe.
Pass only floating processor tensors to bf16; keep token IDs/masks/labels integral,
as the upstream deployment example requires. This corrects input dispatch before
any measured arm and does not change images, prompts, values or score definitions.


The corrected-version probe reached kernel loading but stopped because the kernel
client could not verify the publisher's trust status. No gradients or archive
outputs were produced. Allow a third explicitly recorded synthetic probe, retaining
all three ceilings: **$93.2400068** including the full experiment and preparation
reserves, below $95. Load only `kernels-community/finegrained-kernels` release 0
with explicit trust, then register that loaded module in Transformers' kernel
cache. Global trust of other repositories stays disabled. Record the resolved
revision and entry-point hash; require the identical fingerprint inside the full
allocation. This selects the already required upstream kernel; it does not change
its computation or the quantizer's `is_trainable` flag. The serving $20 remains
protected. The raw publisher-verification error is preserved as attempt 2.


Probe 3 exposed a kernel-client transport bug before computation: with telemetry
disabled, kernels 0.17.2 constructs an empty user agent, which Hub 2.4.0 renders
with an illegal trailing space. Keep telemetry disabled and supply a scoped HfApi
client with the public project User-Agent (and the kernel file-type marker),
using an exact one-repository trust allowlist. No global trust, authentication,
TLS or model-computation setting is changed. One fourth declared probe raises
the retained ceiling to **$94.0124768**, still below $95; preserve every failed
probe ceiling. If CPU checkpoint staging hits its 1,800-second bound, one manual
resume of the same hash-pinned files is allowed at another $0.4629 ceiling, inside
the existing $5 preparation reserve and $2 CPU-attempt sub-cap. Never run two
checkpoint writers together. The $20 serving reserve remains untouched.


The scoped HfApi factory did not cover every kernel resolver request (attempt 4).
A **CPU-only** transport test now succeeds through repository resolution using
Hub's supported HTTP client-factory hook, which applies the project User-Agent to
each outgoing asset request while retaining the SDK's default transport, certificate
checks and hooks. Telemetry remains disabled. The CPU loader then correctly reports
that the kernel has CUDA/XPU/ROCm builds but no CPU build; its resolved revision is
**6ad75fc2a174a02bc1df3db98fe71768e0c8e682**. Pin that exact kernel revision.
Allow the fifth and final declared synthetic B300 probe, retaining all five
$0.77247 ceilings. Retained maximum is **$94.7849468**, below $95; no extra probe
or full-job retry is funded. The CPU download reached its hard 1,800-second bound;
its one declared manual resume reuses completed hash-pinned shards. Neither event
changes training data, validation references, decoding, epochs or adoption metrics.


Probe 5 loaded the pinned kernel and reached its backward function, which divided
by zero for the artificial 128-wide expert fixture. The actual model uses 4,096-wide
expert input/intermediate dimensions. The next synthetic check uses those actual
matrix dimensions with four experts and no archive data, instead of treating an
unsupported tiny shape as proof about the full architecture. Retain all five
previous ceilings and allow one further $0.77247 check. Before any full allocation,
reduce its execution bound from 9,600 to **9,000 seconds**; its worst case is now
**(9,000+300+15) × .00866592 = $80.7230448**. With all six probe ceilings and the
unchanged $5 preparation reserve, the retained maximum is **$90.3578648**. This
prospective ten-minute reduction funds the additional compatibility check under
$95; no failed charge is released and no validation outcome has been inspected.
Serving remains separately capped/reserved at $20. No seventh probe is authorised
by this amendment. The full allocation still must verify gradients before training.


### Weight-only training route, before archive inference or training

The 4096-wide probe reached the pinned backward implementation but did not finish
inside 300 seconds. Inspection shows its dgrad infers a two-dimensional affine
scale grid, whereas the default Blackwell NVFP4 path stores swizzled scales.
Use the integration's **NVFP4 weights with bf16 activations (W4A16)** option for
both the base comparator and adapter: `activation_format="bf16"` at load time
retains an affine scale layout. It does not change packed weight values. The
quantizer flag is untouched, and adapters alone train. This changes the local
comparison's activation precision prospectively, before any archive output.
One 600-second synthetic probe (60 s startup + 15 s shutdown), **$1.390446**, is
funded with all six previous $0.77247 ceilings retained. Including the full
9000-second experiment and $5 preparation reserve, maximum is **$91.7483108**.
The $20 serving reserve is untouched. The owner's later family/layout and detached
checkpoint requirements supersede the earlier five-page validation design.
