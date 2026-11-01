# P37: untrained Glimmer sorts archive pages

The new text-sort capability is registered as `modal_glimmer_sorter`, exposed through the optional `sorter` role in `config/archive_glimmer.toml`. It is always Cache → Budget → backend, with the canonical ledger and a $10 default cap. Classification uses the unchanged phase-2 prompt/parser and first 1,024 OCR characters, then the existing approved-title check. An invalid answer fails visibly, `other` is unsupported, and pages without an OCR layer keep the existing image classifier. No adapter or training is used.

The title-check helper was moved verbatim to a pure module shared by the pipeline and original runner, retaining the original runner's import aliases. No PDF is opened by the generic pipeline: its archive caller supplies OCR. All previous configs, results and frozen experiments retain Spark's classification; replay verifies their unchanged outputs. No file in results/real_test/, labelling/, the scorer or a git tag was read or changed for P37.

## Ten-page live integration check

The selection, hashes, inference settings and worst-case cost were frozen and pushed in **9fe2eb0d95ad6cbf2978cfb4e6b1566e655d9ef9 before deployment/GPU submission**. Five fixed validation positives (one per enabled family), plus all five frozen title-check rejections: Treasury development pages only, checked against split.json before any call. Existing Spark classifications came only from the already-frozen development dataset, without reopening a sweep or making Spark calls.

| Comparison | Result |
|---|---:|
| Raw Glimmer versus saved raw Spark assignments | 8/10 |
| Confirmed family pages found by Glimmer | 5/5 |
| Glimmer plus unchanged title check versus saved confirmed types | 10/10 |
| Title-rejected pages finally treated as other | 5/5 |
| Invalid / missing answers | 0 / 0 |

On the five title rejections, Glimmer itself answered other twice; the title check rejected the other three assignments. This is a small development integration check against teacher-derived proxy labels, not independent accuracy or another held-out measurement. Exact outputs were saved before comparison in live-check-raw.json, with the summary in live-check.json. Immediate replay returned the same answers with cached=True and made no second GPU call. The paid-call ledger gained exactly one entry.

Live precision evidence: 720 NF4 linear modules, double quantisation, bfloat16 compute and quantisation storage, all parameters on CUDA, and no adapter parameters. The pinned phase-2 base loader and batch generator are reused directly. Two native batches (eight and two) completed in **82.942932408 seconds** of inference. Modal queued the L4; it was first observed allocated at 543.868 seconds and the call completed at 664.497 seconds. No fallback, retry, different precision, longer excerpt or training was used.

## Cost and serving

| P37 accounting | Dollars |
|---|---:|
| Modal app-specific reported charges at saved query | **0.06225994** |
| Conservative charge in canonical model ledger | **0.13815629** |
| Full retained request maximum plus deployment/storage allowance | **0.52040048** |
| Live-check limit / task limit | 2.00 / 10.00 |

Billing may lag; billing.json includes only this app's resource rows. The model ledger deliberately charges measured inference plus a full 300-second cold-start allowance and 17 seconds for idle/transport/shutdown even when less is billed. These two accounting figures are alternatives, not additive charges. The entire $0.42040048 request maximum and $0.10 overhead allowance remain retained. Earlier Glimmer experiments and other tasks are excluded from this P37 cap and report.

Private deployed app **ap-KDG2khyUIKIkwekBeEPVDv**, name `archivist-glimmer-sorter-p37`, class `GlimmerSorter.infer`: one L4, four physical CPUs, 32 GiB host RAM, zero minimum/one maximum container, two-second idle window, no retries, 900-second hard execution and 300-second startup timeouts. Allocation waiting has its own 900-second cancellation bound. Endpoint lookup is lazy and no GPU is created by loading a config or replaying cached requests. The backend refuses non-development/non-Treasury sources before endpoint lookup.

After the check, the service returned to **zero runners, running inputs and backlog**, recorded in idle.json. The private deployment remains available for new calls; no app was stopped and no other task's app was affected. D44 records why the untrained model is used: phase 2 found all 136 confirmed pages, versus 117 for the adapter, which missed every total-claims positive. No phase-1/phase-2 artifact or reported number was changed.

## Integration and verification

The glimmer branch has no live-reading package. **After the branches are merged, apply the tested live-reading.patch** as described in MERGE_HANDOFF.md, and run with the glimmer dependency group so Modal is installed. Its four edits switch new Treasury reads to archive_glimmer.toml, obtain OCR before sorting, retain title confirmation before field extraction, and report the sorter in call/recognition events and model names. The endpoint is already deployed. Old committed configurations and synthetic arm configs retain their original roles. The batched live-check cache entry does not prefill individual new live-reading requests.

The unpiped requested Check passed before deployment (1,163 tests, all eleven runs and both exports identical, ledger unchanged at 81,154 lines), with clean pre-commit. It is run again with these live artifacts before the final commit; CHECKS.md records the result. Mocks cover the protocol, truncation, lazy lookup, zero cap, uncertain-failure accounting, cache replay, source refusal, unsupported/invalid answers, unchanged image classification, title confirmation, resume protection and the actual patched live-reading paths. The existing sparse exclusions of tests/test_labelling.py and tests/test_score.py remain. Main/ui/live-reading had no D44 at the final recheck. No merge was performed.
