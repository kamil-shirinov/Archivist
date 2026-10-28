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
templates/ — one <family>.yaml per template type, and its <family>.evidence.json once tested; only approved ones are registered
src/archivist/templates/ — families.py (which Treasury families to draft, by a fixed rule), pages.py (which pages may be sent), draft.py, test.py (the arithmetic test), approve.py (for a person), rediscover.py, compare_citations.py (which box strategy suits template tables), ocr.py (S0+ocr: boxes from the PDFs' OCR text layer), grid_probe.py (is a table's grid findable from the page alone)
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
uv run python -m archivist.templates.draft --family <name> --pages <id> <id> [<id>]  # Muse Spark drafts templates/<family>.yaml (status draft) from 2-3 development pages
uv run python -m archivist.templates.test --family <name>  # read, cite, blind second read; every identity evaluated -> templates/<family>.evidence.json
uv run python -m archivist.templates.approve --family <name>  # interactive, for a person only
uv run python -m archivist.templates.compare_citations  # S0 vs S0+ocr on the drafts' development pages -> results/templates/citations_dev_v2.md (citations_dev.md, S0 vs S0+ink, is the first measurement)
uv run python -m archivist.templates.rediscover  # drafts cards and memos from val pages (seed 2002) -> results/templates/rediscovery_v2.md

## Document types
- A new type implements DocType and registers in doctypes/__init__.py; verify.py and the exporter need no edit. A type whose pages link to others also implements AccountReader or PostingReader; one that doesn't is exported page by page.
- A table type can instead be a template, templates/<family>.yaml (doctypes/template.py): identity (family, printed title, classifier description, title patterns), layout (unit, printed precision, fixed or read rows, columns with kind money/count/percent/date/text and, for a figure's column, blank_means: zero or unknown, the default), identities and provenance. Identities are structured expressions (cell, sum over named rows or columns, difference, a cell of another table of the same issue, a cell of the previous row in an identity for each row, which then skips the first row), worked out in Decimal and never eval'd; each holds within n half-units of the printed precision for n printed values (a blank counted as zero is not printed). A blank where blank_means is unknown leaves the identity unchecked; the drafter may propose zero, and the approver accepts it or sets it back, column by column. A failed one flags every cell with the value it implies; its detail names its rule ("identity <family>.<id> on ..."), which the exporter reads through RuleReader.
- Every template file must validate, drafts included, or the import fails; only status "approved" (with approver, date and evidence) is registered, and an approved template may refer only to approved ones. A page's issue, for cross-table identities, is its id up to the last "_".
- Registered is not enabled. A run enables only the types its config names ([doc_types] enabled; every committed config names ledger_card and payment_memo): the classifier prompt and the money fields come from that set, and run.json records it (built-in, or the template file's sha256). Approving a template therefore never changes a committed run; to use one, name it in a new run's config. A run from before P21b recorded no set and is read as LEGACY.
- Each type names how its boxes are made (DocType.citations): the ledger family keeps S0+ink (D23); every template uses template.CITATIONS, chosen on development pages in results/templates/citations_dev*.md. S0+ocr (templates/ocr.py) takes a value's box from the archive PDF's OCR layer (pdfium's page-to-device transform at the stored image's size) where exactly one matching figure lies near the model's box, else keeps the model's box, unanchored; it reads PDFs, so it lives outside archivist.pipeline and only the arithmetic test and the measurement use it. Template re-reads run at reasoning "minimal" (config/templates.toml); the committed configs keep "low". extract and the arithmetic test use the type's own unless --citations overrides; run.json records one strategy, or each type's when they differ; verify corrects only the types whose own strategy corrects.
- Drafting (archivist.templates): Muse Spark drafts from 2-3 development pages (data/real/split.json) or synthetic dev or val pages only (never test); pages.py refuses anything else before any call, and the prompt describes only what the template language can express, never our types or their rules. The arithmetic test rejects an identity that never holds and keeps one that sometimes fails, with its failing cells and both reads. Only a person approves, with archivist.templates.approve, which records approved_by, the date, the evidence file's sha256 and what was dropped; an approved template whose evidence file changes no longer loads. Never run approve and never mark a template approved yourself.

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
- [x] P21b Muse Spark drafts document types, the arithmetic test checks them, a person approves (six Treasury drafts awaiting approval; results/real/family_choice.md, results/templates/citations_dev_v2.md, results/templates/rediscovery.md and rediscovery_v2.md)
- [ ] P21c grid-based citations for the 1980s country tables, whose OCR layer lacks the figures but whose grid columns are found exactly (results/templates/grid_dev.md); the grid reader was not built in P21b
- [ ] P21d multi-panel templates: one template describes a table printed as two or more panels on one page (side by side, or one above the other), since a page is classified as one type. Collections of Internal Revenue was set aside for this (results/real/family_choice.md, amendment); its draft is in results/templates/set_aside/
