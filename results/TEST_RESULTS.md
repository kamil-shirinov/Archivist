# Test results — Archivist

The pre-registered test run, scored once. The test set is 157 synthetic pages with 4267 fields. Every configuration ran on it once, with the code and settings frozen in PREREGISTRATION.md, and nothing below was used to change the system.

Each value is *accepted* (the system lets it into the database without a person looking), *sent to review* (a person checks it first) or *abstained* (the extractor returned no value). Only values sent to review count toward the review rate and H3; abstained values are counted separately (n_abstained in results/test_report.json). The fields of a page that failed to extract are none of these. A *wrong value* is a value that is not the printed one, or a blank where something is printed. An *error among accepted fields* is a wrong value that got in. Intervals are 95% intervals from 2,000 resamples of whole pages.

## The five hypotheses

|  | Claim | Result |
| --- | --- | --- |
| H1 | The headline's error rate among accepted fields is lower than the baseline's, with non-overlapping 95% intervals. | **MET** |
| H2 | The headline catches at least 85% of wrong values. | **MET** |
| H3 | The headline sends at most 20% of fields to review. | **NOT MET** |
| H4 | The all-open-weights arm's error rate among accepted fields is below 1%. | **MET** |
| H5 | The headline flags at least 90% of the planted source errors. | **NOT MET** |

**H1: met.** Archivist (arm A) accepted 3330 values and 12 were wrong: 0.36% (95% interval 0.14% to 0.67%). The baseline accepted 4251 values and 189 were wrong: 4.45% (95% interval 2.28% to 7.14%). Archivist's rate is lower and the intervals do not overlap.

**H2: met.** Of 189 wrong values, Archivist (arm A) sent 177 to review: 93.65% (95% interval 88.31% to 97.28%). The threshold is 85% or more.

**H3: not met.** Archivist (arm A) sent 921 of 4267 fields to review: 21.58% (95% interval 15.44% to 27.87%). The threshold is 20% or less.

**H4: met.** Arm B accepted 3296 values and 10 were wrong: 0.30% (95% interval 0.12% to 0.54%). The threshold is below 1%, judged on the rate itself.

**H5: not met.** Archivist (arm A) sent a field of 23 of 26 planted source errors to review: 88.46%. The threshold is 90% or more.

## Errors that reach the database

| Configuration | Values accepted | Wrong among accepted | Error rate among accepted [95% interval] | Wrong values in all | Caught (sent to review) | Catch rate [95% interval] | False alarms (correct values sent to review) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 4251 | 189 | 4.45% [2.28%, 7.14%] | 189 | 0 | 0.00% [0.00%, 0.00%] | 0 of 4025 |
| Archivist, arm A (headline) | 3330 | 12 | 0.36% [0.14%, 0.67%] | 189 | 177 | 93.65% [88.31%, 97.28%] | 713 of 4025 |
| Archivist, arm B (all open weights) | 3296 | 10 | 0.30% [0.12%, 0.54%] | 202 | 192 | 95.05% [88.89%, 97.96%] | 734 of 4013 |
| Archivist, arm C (two models) | 3224 | 15 | 0.47% [0.22%, 0.81%] | 189 | 174 | 92.06% [86.21%, 95.65%] | 824 of 4025 |

What each arm's extraction would have let in without verification:

| Configuration | Values accepted | Wrong among accepted | Error rate among accepted [95% interval] |
| --- | --- | --- | --- |
| Archivist, arm A (headline) | 4251 | 189 | 4.45% [2.28%, 7.14%] |
| Archivist, arm B (all open weights) | 4253 | 202 | 4.75% [2.33%, 7.78%] |
| Archivist, arm C (two models) | 4251 | 189 | 4.45% [2.28%, 7.14%] |

## How much goes to review

| Configuration | All fields [95% interval] | Severity 0 | Severity 1 | Severity 2 | Severity 3 |
| --- | --- | --- | --- | --- | --- |
| Baseline | 0.00% [0.00%, 0.00%] | 0.00% (0 of 1248) | 0.00% (0 of 1065) | 0.00% (0 of 713) | 0.00% (0 of 1241) |
| Archivist, arm A (headline) | 21.58% [15.44%, 27.87%] | 10.42% (130 of 1248) | 6.95% (74 of 1065) | 23.56% (168 of 713) | 44.24% (549 of 1241) |
| Archivist, arm B (all open weights) | 22.43% [17.01%, 28.33%] | 12.10% (151 of 1248) | 12.58% (134 of 1065) | 22.72% (162 of 713) | 41.10% (510 of 1241) |
| Archivist, arm C (two models) | 24.07% [18.43%, 29.90%] | 14.18% (177 of 1248) | 9.48% (101 of 1065) | 27.77% (198 of 713) | 44.40% (551 of 1241) |

Severity is how badly the scan is degraded, from 0 (mildest) to 3 (worst).

## Proposals, source errors, classification, citations and cost

| Configuration | Proposals right | Source errors found | Classification accuracy | Citation accuracy | Cost per page |
| --- | --- | --- | --- | --- | --- |
| Baseline | — | 0 of 26 (0.00%) | 157 of 157 (100.00%) | 90.05% | $0.0008 |
| Archivist, arm A (headline) | 6 of 17 (35.29%) | 23 of 26 (88.46%) | 157 of 157 (100.00%) | 90.05% | $0.0089 |
| Archivist, arm B (all open weights) | 15 of 25 (60.00%) | 22 of 26 (84.62%) | 157 of 157 (100.00%) | 93.48% | $0.0564 |
| Archivist, arm C (two models) | 6 of 19 (31.58%) | 23 of 26 (88.46%) | 157 of 157 (100.00%) | 90.05% | $0.0461 |

## Risk and coverage

Coverage is the share of fields accepted at a confidence threshold, and risk is the error rate among them. Each point is one threshold, strictest first.

| Configuration | Points (coverage, error rate) |
| --- | --- |
| Baseline | (99.63%, 4.45%) |
| Archivist, arm A (headline) | (76.75%, 0.37%), (78.04%, 0.36%), (78.44%, 0.54%), (99.63%, 4.45%), (100.00%, 4.80%) |
| Archivist, arm B (all open weights) | (75.96%, 0.31%), (77.24%, 0.30%), (77.83%, 0.78%), (99.67%, 4.75%), (100.00%, 5.06%) |
| Archivist, arm C (two models) | (74.22%, 0.47%), (75.56%, 0.47%), (76.00%, 0.68%), (99.63%, 4.45%), (100.00%, 4.80%) |

## What happened in the runs

| Configuration | Extraction run | Pages extracted | Pages failed | Sessions | Verification run | Re-reads failed | Second looks failed | Cost of all calls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | test-baseline | 157 of 157 | 0 | 1 | — | — | — | $0.13 |
| Archivist, arm A (headline) | test-baseline | 157 of 157 | 0 | 1 | test-archivist-A | 1 of 4251 | 0 of 790 | $1.39 |
| Archivist, arm B (all open weights) | test-baseline-open | 157 of 157 | 0 | 2 | test-archivist-B | 0 of 4253 | 0 of 828 | $8.86 |
| Archivist, arm C (two models) | test-baseline | 157 of 157 | 0 | 1 | test-archivist-C | 0 of 4251 | 0 of 899 | $7.24 |

A failed re-read sends its field to review, so failures there raise the review rate. A run with more than one session was resumed. Second looks belong to policy v3, which was not adopted: they are recorded and paid for but do not change a v2 verdict, and their cost is in the cost above.

Deviations recorded in PREREGISTRATION.md:

- 2026-10-27, run 2 (arm A, `test-archivist-A`). This is not a departure from the plan: the pre-registered rule "A failed re-read sends its field to review" covers it, and it is recorded for completeness. 1 of the 4,251 first-pass re-reads failed, the one for field `L:card-09-2:01:description` on page `card-09-2`. The model's answer did not parse as JSON on either attempt (`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`); it was not an HTTP 429 or 5xx or a timeout. It was therefore not retried, as the rules for the runs require, and the field went to review, as a failed re-read does. All 790 second looks succeeded. No code, prompt, threshold or configuration was changed.
- 2026-10-27, run 3 (arm C, `test-archivist-C`), stopped and resumed. This is not a departure from the plan: the run was stopped by hand at about 10:18Z, after 2,785 re-reads, and resumed with the identical command (`--workers 3`). Completed answers replayed from the cache, so none were regenerated: the ledger holds 4,945 model calls for the run and 4,945 cache entries were written, so no call was made twice.
- 2026-10-27, run 3 (arm C, `test-archivist-C`), did not finish. All of its model calls completed (4,251 first-pass re-reads and about 694 second looks), and then the document-check stage crashed with an uncaught `StopIteration` at `src/archivist/doctypes/ledger.py` line 878 (`_memo_ledger_check`, a `next(...)` with no default), while checking arm C's re-read values. It was not a transport failure (no HTTP 429 or 5xx, no timeout). No `verdicts.jsonl` or `run.json` was written, so arm C has no result yet. Per the rules for the runs, work stopped there: no code, prompt, threshold or configuration was changed, and the failure was reported to the project owner. The answers are in the cache ($6.05 of Baseten spend in the ledger); the same command would replay them and, the checks being deterministic, reach the same error. How to proceed is the owner's decision.
- 2026-10-27, run 3 (arm C): **a code fix, which is a departure from the plan** (the first change to the frozen code, made on the project owner's decision because arm B's reads could reach the same line, and H4 depends on arm B). *Correction to the previous entry:* it said all of arm C's model calls had completed; that was wrong. A failed call leaves no ledger line and no cache entry, so counting ledger lines counted only the answered calls. A replay from the cache shows all 4,251 first-pass re-reads were answered, but 205 of the 899 second looks were not (they failed in the first or the resumed session; the cause was not recorded, as the run crashed before its summary). Second looks only decide policy v3, which was not adopted, so no v2 verdict depends on them; completing arm C re-asks those 205 calls. *Cause of the crash:* on arm C's re-reads of `card-01-1`, `card-01-2` and `card-01-3` (one holder, sheets 43 to 45) the re-reader read the account number of the second and third cards differently (`84808901` and `84088901`; the extractor had read `84608901` on all three). Each card was then a group of one, and `_accounts` moves such strays into a neighbouring group of the same holder: the first card joined the second's group, then the second moved on to the third's, leaving a group keyed `84808901` that holds only the first card, which reads `84608901`. A memo citing sheet 43 found its posting in that group, and `_memo_ledger_check` looked for a card in it reading the group's own key and found none. *Fix* (`src/archivist/doctypes/ledger.py`, `_memo_ledger_check`; 5 lines added, 2 changed): a posting counts only if some card in its group reads the group's key; otherwise the memo is handled as one whose ledger card cannot be found, with the existing "no card for sheet S of account A in this batch" note, which is unresolvable and never a reason for review. Nothing that did not crash can change, as the new condition holds whenever the old lookup found a card. Test: `test_a_memo_posted_to_a_group_no_card_reads_is_unresolvable_not_a_crash` in `tests/test_checks.py` reproduces the `StopIteration` on a synthetic example with the unfixed code and passes with the fix; all 382 tests pass. *Evidence that nothing else changed*, from replays out of the cache with no paid call (the spend ledger stayed at 18,390 lines and both spend caps were set far below it, so a cache miss would have aborted the replay): for dev and val, arms A, B and C (six runs, 1,385 and 668 verdicts each), the verdicts from the frozen code and from the fixed code are byte-identical to each other and to the committed P14 files; for arm A on the test set (4,267 verdicts), the verdicts from the fixed code are byte-identical to the committed `test-archivist-A/verdicts.jsonl`, and the frozen code's replay is identical as well (only run metadata differs: cache-hit counts and spend). The baseline and arm A results are therefore unchanged. Arms C and B run with the fixed code.
- 2026-10-27, run 3 (arm C, `test-archivist-C`), completed with the fixed code. This is not a departure from the plan: the pre-registered rule for transport failures covers it. The first complete pass (committed as `c8b2e51`) answered all 4,251 first-pass re-reads, but 205 of the 899 second looks failed with `APIConnectionError` (no answer came back; nothing was spent, and Baseten was reachable again afterwards). They were re-asked by resuming the same run at `--workers 2`: all 205 answered ($0.28), and no re-read or second look has failed. Answers already given replayed from the cache. The policy v2 verdicts of the resumed run are identical to those of the first pass (second looks decide only policy v3, which was not adopted); 154 fields' v3 outcomes changed as their second looks were answered.
- 2026-10-27, before run 4 (arm B's extraction and verification), **a second code fix, a departure from the plan**, made on the project owner's decision as a pre-emptive fix for the same kind of latent bug, so that arm B runs on this code from the start. In `_accounts` (`src/archivist/doctypes/ledger.py`), a card that moves into a neighbouring account's group looks up that account's printed number with `next(...)`, which assumes some card in the group reads the group's key. The moves can leave a group where none does (the stranded group of the arm C crash), and a card whose account text is present but cannot be read as an account number can pick such a group as its only home. No run so far reached it (all completed). *Fix* (2 lines and a docstring sentence): a card whose account number is to be flagged does not join a group that no card reads the account of. The condition holds exactly where the old lookup would have raised, so behaviour changes only there. *Test:* `test_a_stray_card_does_not_join_a_group_no_card_reads_the_account_of` in `tests/test_checks.py` calls `_accounts` directly on a synthetic batch and reproduces the `StopIteration` on the unfixed code; all 383 tests pass. *Evidence that nothing else changed*, from replays out of the cache with no paid call (the spend ledger stayed at 18,595 lines, and both spend caps were set far below it, so a cache miss would have aborted): dev and val for arms A, B and C (six runs) and the test-set runs of arms A and C are byte-identical to the committed verdict files, which includes every field's policy v2 outcome, value and flags. The baseline, arm A and arm C results are unchanged.
- 2026-10-27, run 4 (arm B's extraction, `test-baseline-open`), stopped and resumed. This is not a departure from the plan: the run was stopped by hand at about 12:50Z with SIGINT (its record shows `KeyboardInterrupt`), after 116 of 157 pages, and resumed with the identical command (`--workers 3`). Completed answers replayed from the cache, so none were regenerated: the run's 314 ledger lines (157 pages, two calls each) match the 314 cache entries written, so no call was made twice, and the 6 calls of pages in flight at the stop replayed from the cache. No page failed.

## Reading these numbers

- One run of each configuration on one synthetic test set: 157 pages from 12 accounts, with source errors planted at a fixed rate. Real archives will differ.
- The intervals resample pages as if they were independent, as pre-registered. Pages of one account share names, amounts and balances, so they are not, and the intervals may understate the uncertainty.
- The headline (arm A, policy v2) was chosen on dev and val before the test set was run (D29). The test set decided nothing.
- Error rate among accepted fields counts every accepted value that is not the printed one, including values accepted as blank. A page that failed to extract scores all its fields as omitted: they count as wrong values nobody caught, and are not accepted.
- False alarms are correct values sent to review, not counting the fields of a planted source error, where a flag is a find. A source error counts as found when any of its fields is sent to review; the report does not check the reason given.
- Classification and citation accuracy belong to the extraction run, so the arms that verify the same extraction share them. Citation accuracy is the share of correct values whose box has its centre inside the printed value's box.
- Cost per page is computed from the price lists in the configs, not from invoices. Muse Spark 1.3 runs at Contributor prices (D19). Muse Spark Open's prices are the figures Baseten's marketing page prints, which is not a contract. Cached input is billed as ordinary input, so cost is overstated, never understated.
- Arm B extracts with a different model, so its error rate measures the whole configuration, not the verification alone. The table "What each arm's extraction would have let in without verification" shows what each arm's extraction run would have accepted on its own.
