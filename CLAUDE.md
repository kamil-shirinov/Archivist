# Archivist
Turns scanned financial archives into a verified database: every value cited to its page and region, cross-checked, and flagged when unsure.

## Hard rules
- New work only, built during the Meta Global AI Developer Hackathon (26 Oct – 4 Nov 2026). Never copy code from other projects.
- Public repo. Never read, print or commit .env or any key. No real bank or customer data, ever.
- Never put personal data (an email, a name or a local path) in any outgoing request, header or URL. Identify only with the public repo URL: archivist-hackathon/0.1 (+https://github.com/kamil-shirinov/Archivist).
- Only synthetic or public-domain pages are ever sent to a model.
- Assets only with clear rights: OFL/Apache fonts with their licence files, procedural textures, invented names.
- Every model call goes through archivist.models (registry → cache → budget → backend). No HTTP calls anywhere else.
- archivist.pipeline must never import archivist.synth (keeps ground truth out of predictions).
- The pipeline reads only data/<split>/images/; only archivist.eval may read data/<split>/gt/.
- The UI never calls a model; it only renders exported run bundles.
- Tests never touch the network. One task per session; never edit files the task doesn't name.
- Finish every task by committing ("Pn: …") and pushing, only after its Check passes and pre-commit is clean. Never use --no-verify, never force-push, never rewrite history.
- Nothing runs on data/test except the pre-registered runs. PREREGISTRATION.md may only change in its Deviations section.

## Layout
src/archivist/schema.py — data contracts, including PageExtraction and the verdict models
src/archivist/synth/ — world.py, render.py, degrade.py, build.py
src/archivist/models/ — base.py, mock.py, cache.py, budget.py, meta_api.py, baseten_api.py, registry.py
src/archivist/doctypes/ — __init__.py (DocType protocol, registry, AccountReader/PostingReader/RuleReader), ledger.py (cards and memos), template.py (types from template files), words.py
templates/ — one <family>.yaml per template type; only approved ones are registered
src/archivist/pipeline/ — extract.py, citations.py, checks.py, reread.py, occlusion.py, verify.py
src/archivist/export/ — bundle.py, database.py, rules.py, schema.py
src/archivist/eval/ — metrics.py, run_eval.py, analyse.py, citation_experiment.py, compare_arms.py, compare_extractors.py, sam_spike.py, test_report.py
src/archivist/ingest/ — fraser.py (downloads, renders and records the Treasury Bulletin; resumable, safe to interrupt), survey.py (table families from the OCR title hints; no model)
src/archivist/replay.py — replays every current run from the cache and proves nothing it produced changed
ui/ — static review app (Vite + React + TypeScript), reads data/bundles/<run_id>/bundle.json; types generated from schema.py
data/dev, data/test — test is frozen and hashed; never used for tuning
data/real — Treasury Bulletin from FRASER: pdf/ and pages/ are gitignored; sources.json, manifest.json and split.json are committed. split.json fixes the development and held-out issues before any model has seen a real page; held-out is never used for tuning
results/real/survey.md — the recurring table families, from the manifest's title hints

## Run
uv run pytest -q
uv run python -m archivist.replay  # after any change to code the committed runs depend on; spends nothing, a cache miss aborts
uv run python -m archivist.ingest.fraser  # fetch and render the real pages; Ctrl-C is safe, rerun resumes; --verify checks files against the records, offline

## Document types
- A new type implements DocType and registers in doctypes/__init__.py; verify.py and the exporter need no edit. A type whose pages link to others also implements AccountReader or PostingReader; one that doesn't is exported page by page.
- A table type can instead be a template, templates/<family>.yaml (doctypes/template.py): identity (family, printed title, classifier description, title patterns), layout (unit, printed precision, fixed or read rows, columns with kind money/count/percent/date/text), identities and provenance. Identities are structured expressions (cell, sum over named rows or columns, difference, a cell of another table of the same issue), worked out in Decimal and never eval'd; each holds within n half-units of the printed precision for n printed values. A failed one flags every cell with the value it implies; its detail names its rule ("identity <family>.<id> on ..."), which the exporter reads through RuleReader.
- Every template file must validate, drafts included, or the import fails; only status "approved" (with approver, date and evidence) is registered, and an approved template may refer only to approved ones. Registering one changes the classifier prompt, so committed runs no longer replay: approve templates only for new runs. A page's issue, for cross-table identities, is its id up to the last "_".

## Export
- `uv run python -m archivist.export.bundle --run <run> [--truth] [--check]` writes data/bundles/<run>/bundle.json; `archivist.export.database --run <run>` writes exports/<run>/archivist.sqlite and one CSV per table (accounts, documents, transactions, memos, field_values, links).
- Purely derived from committed runs and the split's images: export never changes a run, never imports archivist.eval or archivist.synth, and reads gt/ only for `--truth`, which writes a separate truth.json for the demo.
- Rule ids come from flag wording (export/rules.py) and must agree with eval.run_eval.check_rule; accounts and postings come from the doc types' public readers (AccountReader, PostingReader), so they match what the checks saw.
- Output is byte-identical for the same inputs. After changing export/schema.py, bump SCHEMA_VERSION, run `python -m archivist.export.schema` (ui/schema/bundle.schema.json) and re-export the committed bundles; tests fail on a stale schema or export.

## Status
- [x] P1 scaffold
- [x] P2 schema
- [x] P3 world generator
- [x] P4 renderer
- [x] P4b realism fixes
- [x] P5 scan degradation and artefacts
- [x] P6 dataset builder and dev set
- [x] P6b JPEG scans; dev images out of git
- [x] P7 model layer: one interface, cache and spend cap
- [x] P8 Muse Spark backend and the first real call
- [x] P8b SAM 3.1 backend and the artefact spike
- [x] P9 scoring rules, written before any model output is scored
- [x] P10 document-type plug-ins and the single-pass baseline
- [x] P10b baseline error analysis
- [x] P10c citations and scorer fix
- [x] P10d validated citation correction
- [x] P11 the documents' own checksums
- [x] P12 verification: blind re-reads, occlusion and verdicts
- [x] P12b read every value twice
- [x] P13 Muse Spark Open on Baseten
- [x] P14 arms and second look
- [x] P15 frozen test set and pre-registration
- [x] P16 pre-registered test runs
- [x] P18 run exporter and verified database
- [x] P19 true plug-ins, proven by replay
- [x] P20 real public-domain pages, ingest only (no model has seen a real page)
- [x] P21a document types from template files (one hand-written example, not approved)
