# Pre-registration — Archivist on real pages, Treasury Bulletin held-out issues

Committed, and tagged `prereg-real-treasury`, before any held-out page of the Treasury Bulletin has been opened by a person or sent to a model. Nothing below may change after this commit; any departure is recorded in the Deviations section at the end of this file and reported with the results.

## What is being tested
Whether Archivist's verification reduces the wrong values that reach the database when it reads real scanned tables it was not developed on, compared with reading each page once, and what that costs in human review.

## Pages
- Source: the Treasury Bulletin from FRASER, `data/real`. The issues are the `held_out` list of `data/real/split.json` (sha256 812520b7999ddbc3b8ac6add2e5362ffa3256c75cbbe12b6a7f21cf7da6d8de2), fixed before any model saw a real page: the 36 monthly issues of 1940 to 1942 and the June issues of 1985 to 1994, 46 issues and 4,569 pages in `data/real/manifest.json` (sha256 76f14cbd0d271807833113406be999901756d9602e0d91fb1cdb4bc2bc56c83b). No held-out page was used for drafting, testing, approving or tuning anything.
- Families: the five approved templates, and only these:

  | Family | Era | Template sha256 | Evidence sha256 |
  |---|---|---|---|
  | `short_term_foreign_liabilities_as` | 1939–1942 | 156a9632a74690d8c7235a707f3ac5061b769940fc64f93f90b31f020ed97b21 | 41017b7a751417836b5133a23f2fa717d37e6f32e9d62474092a8e8a4458e464 |
  | `security_transactions_as_reported_by` | 1939–1942 | 7659ec40ef400a8c2dfca34ee32c2e3a71a74ef09fc14026fb95d1ed9e0597ee | 501fb1b0088dc0b9b9a4aab3a46e701828f7d0f82ea829acc6ee8e8e4d5e2583 |
  | `outstanding_forward_exchange_contracts` | 1939–1942 | 3bc2e5769f6d9a2973f9147d09a55f01dd48ca50a5f9f5e0b4cc693994e199c4 | afe03066edf93c97e091fb60f6a48c92f1d187f5c26ea66a746c36599bb60494 |
  | `receipts_and_expenditures_under_railroad` | 1939–1942 | 8b6d3cf7ed6f28921fa518017a5fb64be950ef60f3e51c8c3604d596d3193d86 | b4177b0b109b66a843a31820ceaf9c34331739d47c4a9d904ea973adaa56a778 |
  | `total_claims_by_country` | 1982–1994 | aba101beccc5c9e12ae5eb0bcd9429160e94833148773fa446e8b681489e185e | 6f6892fb6161cdf6056c59820195130a67d4501c90f9b8049a623ed01370ca40 |

- Which pages are read is decided by Archivist's own classifier, with these five types enabled and no others. A page it classifies as any other kind (unsupported) is set aside: it yields no values and is counted. The survey's title hints (`results/real/family_choice.md`: 97, 54, 27, 25 and 22 held-out pages) are an estimate only; they choose no page.

## Frozen system
- Plan: this file, at the commit tagged `prereg-real-treasury`. Templates and their evidence as in the table above; `config/templates.toml` sha256 e6906bd854d8f93f2863e5723be2e11f402198cb07209cb095e4ee723a412041; `config/models.toml` sha256 68fa39edaa87db92e00144d4f1d0120d869455a3051a558ecd5ab25fda1dad0f.
- Code: the commit tagged `run-real-treasury`. At `prereg-real-treasury` no code can run this test: the pipeline refuses the S0+grid boxes by name, it reads only `data/<split>/images/`, and `src/archivist/templates/pages.py` refuses held-out pages. The runner is therefore built after this commit, tried on development pages only, and tagged `run-real-treasury` before any held-out page is opened. Its commit message lists every file it adds or changes. It must do what this file says and no more; it must leave unchanged every file whose sha256 is given here; and it must not change the behaviour of the code the committed runs depend on: `python -m archivist.replay` passes on it, and `python -m archivist.templates.recount` leaves `results/templates/recount.md` unchanged, as both do at `prereg-real-treasury`. Nothing is changed after that tag except under the Deviations section.
- Models: Muse Spark 1.3 as `muse-spark-1.3-contributor` (Meta Model API, Contributor mode, D19; the pages are public domain, D14) classifies each page, reads each table in context at reasoning "low", and re-reads each cell blind at reasoning "minimal" (D33). SAM 3.1 (`sam-3.1`, Meta Model API) runs its stain check on every page of the deep check: prompts "stamp" and "stain", a value occluded when one detected box covers at least 10% of its box. No Baseten model is used.
- Boxes: each template's own strategy, S0+grid with OCR anchors (D35, D37): the box from the archive PDF's OCR layer where the figure is found there, else the cell of the table's grid found in the page by plain code, else the model's; each cell records which.
- Policy v2 (`src/archivist/pipeline/verify.py`), unchanged, with each template's approved identities as its document checks: a value is accepted only when the in-context read and the blind re-read agree under the template's comparison and no identity involving it fails on the in-context values. A disagreement, a failed identity, an illegible or failed re-read, or a cell with no box goes to review. Occluded values are accepted only if everything agrees, at lower confidence. No value is ever changed; a correction is only proposed.

## Two stages
1. Sweep: every held-out page is classified, one call each. It counts the pages of each family and the pages set aside, and it is the frame for the classification check.
2. Deep check: in each family, 12 of the pages the sweep classified into it, drawn with `random.Random(4004).sample` from its page ids sorted, or all of them where it has 12 or fewer, go through the full pipeline: the table read in context, the boxes, SAM's stain check, a blind re-read of every cell, the identities and policy v2. Each page's classification is the sweep's, replayed from the cache. The 400 labels are drawn from these pages.

## Expected calls, cost and time
Estimated from the spend ledger's earlier calls of the same kinds, before any held-out page: a page's classification costs about $0.0005 (about 4,000 input tokens and 250 output); a whole table's read up to about $0.006 (up to 30,000 output tokens, minutes per call); a minimal-reasoning re-read about $0.00011; SAM $0.0025 an image, one per prompt. Times are at the rates the ledger shows for these calls: about 0.6 to 1 classification a second, and 1.0 to 1.6 re-reads a second.

| Stage | Paid calls | Cost | Time |
|---|--:|--:|--:|
| Sweep | 4,569 classifications (plus at most one retry each for an answer that does not parse) | about $2.30 | about 1.5 to 2 hours |
| Deep check | at most 60 table reads, 120 SAM calls and about 32,000 re-reads (at most 12 pages a family; per page at most 650, 780, 390, 85 and 744 figure cells, as on the development pages) | about $4.20 | about 7 to 12 hours, almost all of it re-reads |
| Both | about 36,750 | about $6.50 | about 9 to 14 hours |

Spend cap: the Meta Model API may spend at most $40.00 on this test, both stages together. Before the first run, `BUDGET_CAP_USD` is set to the Meta total in `results/spend_ledger.jsonl` plus $40.00, and `BASETEN_CAP_USD` to the Baseten total, so no Baseten call can be made; both values are recorded in the run records. The standing $120 cap (D8) is not raised. A run that reaches the cap stops; going past it is a deviation.

## Configurations, each run once
1. Single read (the baseline): each deep-check page as classified by the sweep, its table read once, in context, by Muse Spark 1.3; every value it gives is accepted.
2. Archivist: configuration 1's own reads verified under policy v2, as above. Both configurations judge the same first read, so every difference between them is verification's.

## Labels
Drawn after both runs have finished, and blind to them.

- The cells: every cell of a figure column (kind money) in every row the first read returned, on every deep-check page read without failure. Text columns (row labels and periods) are not sampled. A cell is named by its template id: family, page, row (a fixed row's key, or a read row's position from the top of the table or of its section) and column.
- The sample: 400 cells drawn with `random.Random(4004).sample` from each stratum's cells sorted by cell id: 300 from the four 1939–1942 families together, then, with a fresh `random.Random(4004)`, 100 from `total_claims_by_country`. A page counts in the stratum of the family it was classified as.
- Weights: the population is every figure cell on every page the sweep classified into the five families. Each labelled cell is weighted by its family's classified pages divided by its family's deep-check pages, times its stratum's deep-check cells divided by its stratum's sampled cells, which is the inverse of its chance of being labelled. Overall rates are ratios of weighted sums; each stratum's own rates are reported too.
- How I label: one cell at a time, in the sample's order, on a page that shows the printed table around the cell, with its row label and its column heading as printed, and the cell's box marked as a locator. The page never shows any model's read, any verdict or the box's source. The cell is the one at the named row and column; where the box disagrees, the row and column win. My choices are: the printed value (typed as printed), blank, or can't read.
- My consistency: 40 of the 400 cells, drawn with `random.Random(4004).sample` from the 400 sorted by cell id, are labelled again at least 24 hours after the first pass, in a shuffled order, without seeing the first labels. Agreement between the two is reported with a Wilson 95% interval. The first label is the one scored.
- Scoring: a read is right when it equals the label under the template's own comparison (`TemplateType.canonical`: a figure as its value, a blank as blank). A cell labelled can't read is left out of every error rate and counted. A cell the first read abstained on gave no value: it is outside both error rates and counted.

## Hypothesis (criterion fixed now)
- R1: Archivist's error rate among accepted cells (wrong values accepted ÷ values accepted) is lower than the single read's error rate (wrong values ÷ values given), with non-overlapping 95% intervals. Intervals are 95% percentile intervals from 2,000 bootstrap resamples by page, seed 0 (`numpy.random.default_rng(0)`), as `bootstrap_ci` in `src/archivist/eval/metrics.py` makes them, except that pages are resampled with replacement within each stratum, each page keeping its sampled cells and their weights. R1 is reported as met or not met, with its numbers, whatever the outcome.

## Reported whatever they show, with intervals and no thresholds
- Archivist's error rate among accepted cells (the R1 figure), overall and by stratum.
- The catch rate: the share of the single read's wrong values that Archivist did not accept.
- The review rate: the share of all deep-check cells, not just the sample, sent to review, overall (weighted by family as above) and by family.
- How cells were boxed: the share of deep-check cells boxed from the OCR layer, from the grid and from the model, overall (weighted by family) and by family.
- Pages set aside: how many held-out pages the sweep classified as none of the five, by era, and how many it classified into each family.
- SAM's detections on the deep-check pages: pages with at least one, cells it marked occluded, and by prompt.
- Classification precision: 50 pages drawn with `random.Random(4004).sample` from all the pages the sweep classified into one of the five families, sorted by page id, which I check by eye after labelling the cells; a page is right when it prints the table of the family it was given. Reported with a Wilson 95% interval. Recall (a family's pages classified as something else) is not measured.

Rates over deep-check cells or pages use the same page bootstrap; rates over the 50 checked pages and the 40 relabelled cells use Wilson intervals.

## Limits, stated before the results
- One labeller, me, who is also the project's author and the templates' approver. The relabelled 40 measure my consistency, not my accuracy.
- The development and held-out pages come from the same publication, the templates were drafted from its development pages, and the box strategy was chosen on them. This test says how Archivist does on later issues of tables it was built from, not on archives it has never seen.
- A table printed as two or more panels on one page cannot yet be described by a template (P21d, D34). Such pages are set aside, or read as one panel, and the results say nothing about them.
- The deep check reads at most 12 pages of each family, so a family's rates rest on few pages, and their intervals say so.

## Rules for the runs
- One run per configuration; no change to code, prompts, templates, thresholds or configuration between or during runs.
- A failure of any kind (an HTTP 429 or 5xx, a timeout, a crash, a stop by hand) is resumed from the cache with the identical command, with fewer workers if needed; it is never re-run fresh, and an answer is never re-requested because of its content. Each departure, however small, is recorded below.
- A failed re-read sends its cell to review. A page that fails to classify or to read is counted and reported, and its cells are not in the sample; it is not replaced.
- All run records are committed, including any failed first passes.

## Deviations
