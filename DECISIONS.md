# Decisions — one line each: decision — why
D1 Indie track, "Build for Your World" — a problem seen first-hand during a bank internship.
D2 One document family: running-balance ledger cards plus the payment memos that reference them — they carry built-in checksums (balances, words vs figures, memo vs ledger).
D3 Data: synthetic with exact ground truth plus public-domain scans — rights-clean, nothing private.
D4 Checks independent of the extractor: arithmetic in plain code; blind re-reads never see the claimed value — correlated checks add no information.
D5 One interface per capability (VisionLLM, Segmenter), wrapped as Cache(Budget(Backend)), roles mapped in models.toml — swaps are config changes, the cap can't be bypassed, the cache doubles as replay.
D6 Plan A runs entirely on the Meta Model API (Muse Spark + SAM 3.1) — partner credits only ever add a second arm.
D7 Models chosen per role on dev; each configuration pre-registered and run once on the frozen test set — choosing on test inflates results.
D8 Hard spend cap $120 in code plus $30 untouched buffer — the Billing spend limit only notifies.
D9 Pre-printed line numbers on ledger cards — deterministic row alignment in evaluation.
D10 Source errors are flagged, never auto-corrected; ground truth is the printed value — Archivist reports what the document says.
D11 Python 3.12 with a uv lockfile — reproducible runs.
D12 The UI is a static app over a run bundle exported by the pipeline; the browser never calls a model — it can't break live, exposes no key, spends nothing, and can be built against a fixture.
D13 No public live mode — an upload box invites documents outside our one family; live runs are shown in the video and documented for local use.
D14 Only synthetic or public-domain pages are ever sent to a model — free-credit traffic may be used by Meta for product improvement.
