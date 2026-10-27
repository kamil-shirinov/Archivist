# Pre-registration — Archivist test-set evaluation

Committed before any part of the pipeline has seen the test set. Nothing below may change after this commit; any deviation is recorded at the end of this file and reported in the README.

## What is being tested
Whether Archivist's verification reduces the errors that reach the database compared with reading each page once, and what that costs in human review.

## Test set
- Split `test`, generated once with the frozen generator: seed 3003, 12 accounts, 3 cards per account, memo rate 0.35, source-error rate 0.2; severities 0–3 balanced.
- Manifest: data/test/manifest.json, sha256 78db32f34cdb7a2aa2fb5ab4f24e5d9540d11729460e9657b604b141c250c1e4; 157 pages (36 ledger cards, 121 payment memos), 4267 fields.
- Images and ground truth are committed in full. The test set was not used for any development decision.
- Dev and val were used for development and for choosing the configuration; results on them are not final.

## Frozen system
- Code: commit 63d7d5e7cd6a97c5a46ac8cfe3b9cb63e3f60095. citations.py sha256 857211875e46e750ab02a517254dd6841a230c8719589e5721731fe6424186c2; config/models.toml sha256 dbdd2b4f243e07710ab2f6e456b079a4d46605f86fc0b64ebf7c09601bf39921; config/models_open.toml sha256 755c62ec1169f47dfe0599006a1226a3e19b12ccd888f1187b347461cbee7909.
- Models: muse-spark-1.3-contributor (Meta Model API, reasoning effort low); sam-3.1 (Meta Model API); meta-models/muse-spark-open-1026 (Baseten, reasoning effort low).
- Citations: extractor boxes with the validated per-page ink correction (D23) and the off-page guard.

## Configurations, each run once on the test set
1. Baseline — single-pass extraction by Muse Spark 1.3 Contributor; every value accepted.
2. Archivist (headline) — arm A, policy v2: Muse Spark 1.3 Contributor reads every value in context and again in isolation; document checks; SAM 3.1 occlusion. A value is accepted only when both reads agree and every check involving it passes.
3. Archivist, all open weights — arm B, policy v2: as above, with Muse Spark Open on Baseten for both reads.
4. Archivist, two models — arm C, policy v2: Muse Spark 1.3 Contributor reads in context; Muse Spark Open re-reads in isolation.

## Outcomes
Primary: error rate among accepted fields (wrong values accepted ÷ values accepted), headline against baseline, with 95% intervals from 2,000 page-level bootstrap resamples (seed 0).
Secondary, for every configuration: errors caught and missed; false alarms; review rate, overall and by severity; proposals made and how many are right; source-error detection recall; classification accuracy; citation accuracy; cost per page; risk–coverage points. Scoring rules are those in src/archivist/eval/metrics.py at the frozen commit (D20, D22).

## Hypotheses (criteria fixed now)
- H1: the headline's error rate among accepted fields is lower than the baseline's, with non-overlapping 95% intervals.
- H2: the headline catches at least 85% of wrong values.
- H3: the headline sends at most 20% of fields to review.
- H4: the all-open-weights arm's error rate among accepted fields is below 1%.
- H5: the headline flags at least 90% of the planted source errors.
Each is reported as met or not met, with its numbers, whatever the outcome.

## Rules for the runs
- One run per configuration; no changes to code, prompts, thresholds or configuration between runs.
- Transport failures (HTTP 429 or 5xx, timeouts) may be retried by resuming the same run with fewer workers; answers are never re-requested because of their content.
- A failed re-read sends its field to review; a failed page scores all its fields as omitted.
- All results files are committed, including any failed first passes.

## Deviations
None yet.
