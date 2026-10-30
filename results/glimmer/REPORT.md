# P31 — phase 1 completed

**Frozen strict result:** untrained 39/40 (97.5%); trained 0/40, with 40 framing-invalid answers.
**Post hoc native-framing diagnostic:** untrained 39/40; trained 40/40 (100%).
These are separate results. The diagnostic is not a pre-registered improvement claim.

The trained model directly continues the open `assistant` header with `to=user`; the frozen
parser only recognised a final answer after a new complete assistant-turn header.
Reattaching the already-open header decodes those saved responses. The original strict
metrics, scorer and raw outputs are retained unchanged; no inference or training was repeated.
The diagnostic was tested on synthetic native frames before applying it to the saved answers.
[Native protocol reference](https://dev.meta.ai/docs/muse-glimmer/prompting).

| Arm | Frozen strict accuracy | Invalid / missing | Native-framing diagnostic |
|---|---:|---:|---:|
| baseline | 97.5% | 0 / 0 | 97.5% |
| trained | 0.0% | 40 / 0 | 100.0% |
| spark_raw | 97.5% | 0 / 0 | not applicable |
| spark_confirmed | 100.0% | 0 / 0 | not applicable |

Muse Spark is `muse-spark-1.3-contributor` from the existing image-based development sweep.
Its title-confirmed assignments define the proxy labels, so 100% confirmed agreement is a
teacher-agreement ceiling. The Glimmer arms see only OCR text.

## Per-family validation precision / recall

| Family | Support | Untrained P / R | Trained strict P / R | Trained native diagnostic P / R |
|---|---:|---:|---:|---:|
| short_term_foreign_liabilities_as | 1 | 50.0% / 100.0% | undefined / 0.0% | 100.0% / 100.0% |
| security_transactions_as_reported_by | 1 | 100.0% / 100.0% | undefined / 0.0% | 100.0% / 100.0% |
| outstanding_forward_exchange_contracts | 1 | 100.0% / 100.0% | undefined / 0.0% | 100.0% / 100.0% |
| receipts_and_expenditures_under_railroad | 1 | 100.0% / 100.0% | undefined / 0.0% | 100.0% / 100.0% |
| total_claims_by_country | 1 | 100.0% / 100.0% | undefined / 0.0% | 100.0% / 100.0% |
| other | 35 | 100.0% / 97.1% | undefined / 0.0% | 100.0% / 100.0% |

All TP/FP/FN counts, confusion matrices and Spark family metrics are in the adjacent JSON files.
Undefined precision has no predicted positives; it is not a perfect score.

## Data and training

Frozen data: 115 unique training pages; 40 validation pages.
Training has two approved development positives per family and 105 `other` pages.
Validation has one positive per family and 35 `other` pages. These are proxy labels, not human truth.
Removed 33 training pages whose OCR duplicated validation inputs.
QLoRA: three epochs, 145 expanded examples, 57 optimizer steps,
29,392,896 adapter parameters across 208 language attention projections; vision frozen.
Training runtime 380.23s; final aggregate training loss 0.062529.
Base revision, hyperparameters, prompt, input hashes and splits are in PLAN.md and the manifests.
One positive per family is too little evidence for a generalisation claim.

## Failures and recovery

Training completed and saved the adapter, then a return-wrapper NameError discarded its response.
The existing 58.8 MB adapter was recovered and SHA256-verified on CPU; training ran once.
Only the return wrapper and CPU recovery support were corrected; inference-function ASTs and
the model runtime, prompt, scorer and training settings were unchanged. See recovery.json and
training_return_failure.json. The failed GPU job retains its full worst-case reservation.
The native-framing issue is a separate measurement limitation, reported above, with original scores preserved.
Metadata whitespace normalisation for pre-commit does not change adapter tensors or JSON meaning.

## Cost

Modal reported resource charges so far: **$1.408090** (billing may lag; before any credits).
| GPU job | Reported app cost, including CPU/memory/egress | Worst-case reservation |
|---|---:|---:|
| baseline | $0.568480 | $2.7186 |
| train | $0.572183 | $9.6926 |
| trained | $0.117892 | $2.7186 |

Other setup/build/recovery charges: $0.149535.
All GPU reservations plus the $2.50 overhead reserve: $17.6297, below $25.
The experiment ledger is reconciled to the reported app charges and mirrored in the canonical branch ledger.
All experiment Modal apps are stopped; no service is left running.

## Checks

Run `uv run pytest -q && uv run python -m archivist.replay`; final check records are in CHECKS.md.
The sparse checkout excludes tests/test_labelling.py and tests/test_score.py because they import
the prohibited labelling/scorer code. Every other discovered test runs. No held-out page/result,
labelling code, original scorer or git tag was opened.

## Phase 2 remains closed

Needs explicit owner permission after freezing the adapter, inference code, prompt and configuration.
Resolve and pre-register native response framing before phase-2 measurement.
Then compare untrained, trained and Muse Spark sorting on Treasury held-out pages with pipeline-confirmed
types, title-check rejections and the owner's 50-page hand check where available. Report per-family
precision/recall against proxy labels, human agreement separately and total cost. The 50-page check
cannot measure recall outside pipeline-confirmed pages.

A new budget estimate is required: extrapolating the current sequential validation runtimes to the
4,569 held-out pages specified by PREREGISTRATION_REAL.md gives roughly $76 for both Glimmer arms.
That exceeds the remaining $25 cap; a budget-compliant serving plan or an explicitly raised cap is needed
before any held-out GPU job. This is an extrapolation from development timings, not a held-out run.
No original pre-registration, scorer, labelling record or tag was changed.
