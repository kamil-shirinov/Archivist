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

## Layout (planned)
src/archivist/schema.py — data contracts
src/archivist/synth/ — world.py, render.py, degrade.py, build.py
src/archivist/models/ — base.py, mock.py, cache.py, budget.py, meta_api.py, registry.py
src/archivist/pipeline/ — segment, extract, verify/, confidence, db
src/archivist/eval/ — metrics.py, run_eval.py
ui/ — static review app (Vite + React + TypeScript), reads data/bundles/<run_id>/bundle.json; types generated from schema.py
data/dev, data/test — test is frozen and hashed; never used for tuning

## Run
uv run pytest -q

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
