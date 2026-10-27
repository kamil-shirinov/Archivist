# Archivist
Turns scanned financial archives into a verified database: every value cited to its page and region, cross-checked, and flagged when unsure.

## Hard rules
- New work only, built during the Meta Global AI Developer Hackathon (26 Oct – 4 Nov 2026). Never copy code from other projects.
- Public repo. Never read, print or commit .env or any key. No real bank or customer data, ever.
- Only synthetic or public-domain pages are ever sent to a model.
- Assets only with clear rights: OFL/Apache fonts with their licence files, procedural textures, invented names.
- Every model call goes through archivist.models (registry → cache → budget → backend). No HTTP calls anywhere else.
- archivist.pipeline must never import archivist.synth (keeps ground truth out of predictions).
- The pipeline reads only data/<split>/images/; only archivist.eval may read data/<split>/gt/.
- The UI never calls a model; it only renders exported run bundles.
- Tests never touch the network. One task per session; never edit files the task doesn't name.
- Finish every task by committing ("Pn: …") and pushing, only after its Check passes and pre-commit is clean. Never use --no-verify, never force-push, never rewrite history.
- Nothing runs on data/test except the pre-registered runs. PREREGISTRATION.md may only change in its Deviations section.

## Layout (planned)
src/archivist/schema.py — data contracts
src/archivist/synth/ — world.py, render.py, degrade.py, build.py
src/archivist/models/ — base.py, mock.py, cache.py, budget.py, meta_api.py, registry.py
src/archivist/pipeline/ — segment, extract, citations, verify/, confidence, db
src/archivist/eval/ — metrics.py, run_eval.py, analyse.py, citation_experiment.py
ui/ — static review app (Vite + React + TypeScript), reads data/bundles/<run_id>/bundle.json; types generated from schema.py
data/dev, data/test — test is frozen and hashed; never used for tuning

## Run
uv run pytest -q

## Export
- `uv run python -m archivist.export.bundle --run <run> [--truth] [--check]` writes data/bundles/<run>/bundle.json; `archivist.export.database --run <run>` writes exports/<run>/archivist.sqlite and one CSV per table (accounts, documents, transactions, memos, values, links). In SQL, `values` must be quoted.
- Purely derived from committed runs and the split's images: export never changes a run, never imports archivist.eval or archivist.synth, and reads gt/ only for `--truth`, which writes a separate truth.json for the demo.
- Rule ids come from flag wording (export/rules.py) and must agree with eval.run_eval.check_rule; accounts and postings come from the ledger's own readers, so they match what the checks saw.
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
