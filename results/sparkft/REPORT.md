# P34 — Spark Open development fine-tune

**Status: BF16 weight staging; no archive inference or optimizer update yet.**
The operative plan was committed before training (fc79eaf; bounded detached
handoff amendments 0b8ba01 and d8f2de2). No adapter qualifies for use at this stage.
The initial $40 feasibility stop is superseded by the owner's $95 authorization.

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

## Frozen training and validation

The coverage rule preceded the full development OCR census. Three pages for every
approved Treasury family/layout were frozen before reference reads. All three
claims pages are validation-only, removing 118 previously prepared training answers.
Training now has **283 two-host-plus-OCR-agreed answers on three development pages**,
37 conversations, one fixed epoch (five accumulated optimizer steps). Training
contains security, forward exchange and railroad examples; no short-term or claims
examples. Both teachers are the same open model on independent hosts, so agreement
is correlated pseudo-supervision. Every target box is from OCR.

Validation has **15 pages / 270 uniquely OCR-supported figures**, three pages for
each of the five approved portrait single-panel family/layout combinations. This
covers the supported template layouts; it is not a census of unknown/unapproved
archive layouts. One claims page has only one supported figure; that denominator
is retained rather than replacing the frozen page. OCR references are imperfect
proxies, not human labels. No held-out scan/result or owner label is accessed.

| Family | Pages | Figures | Base value / containment | Adapter value / containment |
| --- | ---: | ---: | --- | --- |
| outstanding_forward_exchange_contracts | 3 | 60 | Pending | Pending |
| receipts_and_expenditures_under_railroad | 3 | 49 | Pending | Pending |
| security_transactions_as_reported_by | 3 | 60 | Pending | Pending |
| short_term_foreign_liabilities_as | 3 | 60 | Pending | Pending |
| total_claims_by_country | 3 | 41 | Pending | Pending |
| Pooled | 15 | 270 | Pending | Pending |

Adoption requires strict pooled gains in both value accuracy and full-figure
containment, **no family/layout decreases in either**, identical references and
at least three scorable pages per layout. Missing or incomplete evaluation rejects
adoption. Area ratios and invalid outputs are reported separately. Baseline and
adapter receive the same prompts/images/decoding and no reference answer.

## Runtime, costs and recovery

Seven synthetic NVFP4 preflights failed before any archive inference/training:
version/trust/transport issues, then a tiny-shape backward division by zero and
two actual-width timeouts. These failures do not establish that every NVFP4
training implementation is unusable. This task's compressed route was not validated.
All failed-attempt ceilings remain charged against the plan.

The fallback is exact original BF16 Muse Spark Open weights, mirrored by Unsloth:
65/65 shard hashes match Meta's release (training/bf16_provenance.json). One
8-B300 allocation, native grouped_mm experts, frozen base, attention-only rank-16
LoRA, 4,650-second execution timeout and no GPU retry. A detached controller
waits for the exact recorded preparation; two bounded continuations are permitted (the final one uses a smaller
non-preemptible CPU allocation).
The GPU app itself is detached and records call/app IDs before waiting. Every
optimizer update commits adapter, optimizer and RNG state to the task-owned Modal
volume. Base/adapter validation predictions are committed after every page.

Retained training/validation ceiling is **$94.2154788 < $95**:
$82.1902128 full GPU allocation + $6.025266 seven probes + $6 preparation/storage.
These are conservative reservations, not reconciled invoices. Modal replaced a
CPU worker during download. Absolute submission-time deadlines now bound all
infrastructure restarts; per-attempt function timeouts alone would reset. The final
CPU stage is non-preemptible, two cores/16 GiB, within the same preparation reserve. **$20 serving is
separate and untouched.** Seven new Baseten validation-reference reads cost
**$0.7237565 < $5**; no new Meta or Fireworks request. Training teachers use cached
P33 reads only. Preparation and all other jobs have hard timeouts; owned app IDs
are recorded. Only apps started by this task may be stopped. Glimmer is untouched.

Reconnection: `.venv/bin/python -m sparkft.backend` retrieves the recorded detached
experiment call; it does not allocate another job. Checkpoints and final adapter
are under `archivist-sparkft-p34-v1:/experiment-v1/`. Preserve adapters/checkpoints
and remove the task's large base cache after bounded work finishes.

## Serving and terms

If and only if the full adoption gate passes, reload the exact BF16 base and saved
PEFT adapter on Modal, through the model registry/cache/budget layer. No permanent
endpoint or open-weights run is launched here. An 800-second later serving batch
plus 300-second startup/15-second shutdown reserves $18.4576208 of the $20; actual
measured throughput and all staging/storage overhead must fit before launch.
Otherwise retain the hosted base or seek a new serving budget. No arbitrary run
is promised to fit $20. Fireworks private per-token serverless adapters are not
assumed to support this model/image path.

[TERMS.md](TERMS.md) records the model licence's fine-tuning grant and attribution,
licence/policy obligations, and Meta API output restrictions. No closed Meta API
output enters training. Treasury Bulletin provenance records FRASER's public-domain
rights. All page accesses are gated against development before file reads.

Latest pre-training Check: **1,185 tests passed**, all **11 replay runs identical**,
spend ledger unchanged at 81,155 lines during replay; pre-commit clean. All work is
inside sparkft; push is plain `git push origin sparkft`, without merging.
