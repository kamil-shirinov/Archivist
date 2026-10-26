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
D15 Rubric weights (kickoff): Impact 30, Meta tooling 25, Demo 25, Technical depth 20 — optimise in that order; rigour exists to make the impact claims credible.
D16 Datasets keep images and ground truth in separate folders, with a hashed manifest — the pipeline can't see answers by accident, and any change to the data is detectable.
D17 Scans are stored as JPEG at their level's quality — that is what a real scan file is, at about a quarter of the size. Dev images are rebuilt from the seed rather than committed; only the frozen test set is committed in full.
D18 Every paid model call is logged in results/spend_ledger.jsonl, which is committed — cost per page is part of the evidence, and the cap is enforced from the same file.
D19 Muse Spark runs as muse-spark-1.3-contributor: the same 1.3 model in Contributor mode, at Contributor prices. Allowed because only synthetic or public-domain pages are ever sent (D14); real deployments would use Standard mode or open weights.
D20 Scoring rules are written and tested before any model output is scored — the definitions can't drift toward flattering results.
D21 Document types are plug-ins (fields, prompt, schema, parser; checks come next). One is built: ledger cards with their payment memos. Each page is classified first; anything unrecognised is reported as unsupported, never forced into a template.
D22 Amount in words is compared on its letters only — spelling variants of the same words aren't errors. Fixed on dev after the baseline exposed it, before the test set exists.
D23 Citations default to S0+ink: S0's boxes corrected from the page image with a per-page skew-aware fit (y = α·y + β + γ·x), which raised citation accuracy from 63.4% to 92.6% with fewer citations in another field's box (9.9% to 4.0%) — built and tuned on dev, frozen, then validated once on a separate split (val, seed 2002) it had never seen, under a rule fixed in advance; the frozen test set gives the final number.
D24 Deterministic checks use only rules a bank clerk would recognise — balances, dates, cheque sequences, words against figures, memos against the ledger — never constants from our generator, so they carry over to real archives.
D25 Arithmetic verifies the money; an independent blind re-read verifies everything else. Archivist never changes a value: it proposes a correction with its evidence, and a person decides.
D26 Every value is read twice: once in context and once in isolation. Validation showed in-context reading can make a mistake add up — a misread debit carried through every later balance — so the arithmetic alone passed it. An isolated re-read sees one cell at a time and can't make numbers agree. Dev and val are now both development data; the test set will be frozen before the final policy runs on it once.
