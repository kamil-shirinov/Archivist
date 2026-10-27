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
- 2026-10-27, run 2 (arm A, `test-archivist-A`). This is not a departure from the plan: the pre-registered rule "A failed re-read sends its field to review" covers it, and it is recorded for completeness. 1 of the 4,251 first-pass re-reads failed, the one for field `L:card-09-2:01:description` on page `card-09-2`. The model's answer did not parse as JSON on either attempt (`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`); it was not an HTTP 429 or 5xx or a timeout. It was therefore not retried, as the rules for the runs require, and the field went to review, as a failed re-read does. All 790 second looks succeeded. No code, prompt, threshold or configuration was changed.
- 2026-10-27, run 3 (arm C, `test-archivist-C`), stopped and resumed. This is not a departure from the plan: the run was stopped by hand at about 10:18Z, after 2,785 re-reads, and resumed with the identical command (`--workers 3`). Completed answers replayed from the cache, so none were regenerated: the ledger holds 4,945 model calls for the run and 4,945 cache entries were written, so no call was made twice.
- 2026-10-27, run 3 (arm C, `test-archivist-C`), did not finish. All of its model calls completed (4,251 first-pass re-reads and about 694 second looks), and then the document-check stage crashed with an uncaught `StopIteration` at `src/archivist/doctypes/ledger.py` line 878 (`_memo_ledger_check`, a `next(...)` with no default), while checking arm C's re-read values. It was not a transport failure (no HTTP 429 or 5xx, no timeout). No `verdicts.jsonl` or `run.json` was written, so arm C has no result yet. Per the rules for the runs, work stopped there: no code, prompt, threshold or configuration was changed, and the failure was reported to the project owner. The answers are in the cache ($6.05 of Baseten spend in the ledger); the same command would replay them and, the checks being deterministic, reach the same error. How to proceed is the owner's decision.
- 2026-10-27, run 3 (arm C): **a code fix, which is a departure from the plan** (the first change to the frozen code, made on the project owner's decision because arm B's reads could reach the same line, and H4 depends on arm B). *Correction to the previous entry:* it said all of arm C's model calls had completed; that was wrong. A failed call leaves no ledger line and no cache entry, so counting ledger lines counted only the answered calls. A replay from the cache shows all 4,251 first-pass re-reads were answered, but 205 of the 899 second looks were not (they failed in the first or the resumed session; the cause was not recorded, as the run crashed before its summary). Second looks only decide policy v3, which was not adopted, so no v2 verdict depends on them; completing arm C re-asks those 205 calls. *Cause of the crash:* on arm C's re-reads of `card-01-1`, `card-01-2` and `card-01-3` (one holder, sheets 43 to 45) the re-reader read the account number of the second and third cards differently (`84808901` and `84088901`; the extractor had read `84608901` on all three). Each card was then a group of one, and `_accounts` moves such strays into a neighbouring group of the same holder: the first card joined the second's group, then the second moved on to the third's, leaving a group keyed `84808901` that holds only the first card, which reads `84608901`. A memo citing sheet 43 found its posting in that group, and `_memo_ledger_check` looked for a card in it reading the group's own key and found none. *Fix* (`src/archivist/doctypes/ledger.py`, `_memo_ledger_check`; 5 lines added, 2 changed): a posting counts only if some card in its group reads the group's key; otherwise the memo is handled as one whose ledger card cannot be found, with the existing "no card for sheet S of account A in this batch" note, which is unresolvable and never a reason for review. Nothing that did not crash can change, as the new condition holds whenever the old lookup found a card. Test: `test_a_memo_posted_to_a_group_no_card_reads_is_unresolvable_not_a_crash` in `tests/test_checks.py` reproduces the `StopIteration` on a synthetic example with the unfixed code and passes with the fix; all 382 tests pass. *Evidence that nothing else changed*, from replays out of the cache with no paid call (the spend ledger stayed at 18,390 lines and both spend caps were set far below it, so a cache miss would have aborted the replay): for dev and val, arms A, B and C (six runs, 1,385 and 668 verdicts each), the verdicts from the frozen code and from the fixed code are byte-identical to each other and to the committed P14 files; for arm A on the test set (4,267 verdicts), the verdicts from the fixed code are byte-identical to the committed `test-archivist-A/verdicts.jsonl`, and the frozen code's replay is identical as well (only run metadata differs: cache-hit counts and spend). The baseline and arm A results are therefore unchanged. Arms C and B run with the fixed code.
- 2026-10-27, run 3 (arm C, `test-archivist-C`), completed with the fixed code. This is not a departure from the plan: the pre-registered rule for transport failures covers it. The first complete pass (committed as `c8b2e51`) answered all 4,251 first-pass re-reads, but 205 of the 899 second looks failed with `APIConnectionError` (no answer came back; nothing was spent, and Baseten was reachable again afterwards). They were re-asked by resuming the same run at `--workers 2`: all 205 answered ($0.28), and no re-read or second look has failed. Answers already given replayed from the cache. The policy v2 verdicts of the resumed run are identical to those of the first pass (second looks decide only policy v3, which was not adopted); 154 fields' v3 outcomes changed as their second looks were answered.
