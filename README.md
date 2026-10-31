# Archivist

<!-- Logo goes here: assets/brand/ (added later). -->

Archivist turns scanned financial archives into a verified database. Every value is cited to its spot on the page, cross-checked by arithmetic and a blind second read, and flagged for a person when unsure.

## For judges

**The problem.** *(Draft: for the author to rewrite from their bank internship.)* Banks hold decades of records as scans. Typing them in is slow, and a model reading them alone gets some values wrong without saying which.

**Headline results.** On a pre-registered test (targets fixed in git before it ran) of 157 synthetic pages, reading once let in 189 wrong values out of 4,251 accepted (4.4%). Archivist let in 12 of 3,330 (0.4%) but sent 21.6% of values to a person. Three of five targets were met. Real scans: [results pending].

**Meta models.** Muse Spark 1.3 and SAM 3.1 (Meta's API), Muse Spark Open (open weights, on Baseten), Muse Glimmer (Modal GPUs, being measured).

**Live demo:** [link pending] · **Video:** [link pending]

> No model grades its own work. Every value gets a blind second read and plain-code arithmetic, and a person decides anything in doubt.

## How it works

Archivist reads each page in seven steps, and a value is accepted only when independent checks agree.

<img src="docs/img/architecture.svg" alt="Flow chart of the seven steps: sort the page, read and cite, snap to the ink, find covered ink, read again blind, check the arithmetic, decide. Models are purple, plain code is grey, results and people are teal." width="100%">

1. **Sort the page.** A model says which kind of page it is. A table from a real archive is described by a template, a description of its layout, drafted by Muse Spark and approved by a person.
2. **Read and cite.** A model reads every value and draws a box where it saw it.
3. **Snap to the ink.** Plain code moves each box onto the printed figure, using the page image, the archive's own text layer, or the table's ruled grid.
4. **Find covered ink.** SAM 3.1, a Meta model that outlines objects in an image, looks for stamps and stains over a value.
5. **Read again, blind.** A model re-reads each value from a small crop, never seeing the first answer.
6. **Check the arithmetic.** Plain code tests rules a person approved, such as totals that must add up.
7. **Decide.** A value is accepted only if both reads agree and every rule holds. Anything else goes to a person.

Principles:

- No model grades its own work.
- The model proposes and a person decides. Archivist never changes a value; it proposes a correction with evidence (D25).
- Source errors are flagged, never corrected. Archivist reports what the document says (D10).
- Every decision is recorded and replays exactly (`archivist.replay`).
- Only synthetic or public-domain pages reach a model (D14).

## Two ways to run it

One method, two places for the models to run. **Hosted** uses Meta's API and is the default and the measured headline. **Open weights** uses Muse Spark Open, a model whose trained weights are published, so it can run on your own hardware.

<img src="docs/img/two-modes.svg" alt="The same seven steps in both modes. Three steps change model: sort the page, read and cite, and read again blind. Hosted uses Muse Spark 1.3; open weights uses Muse Spark Open. SAM 3.1 and the plain-code steps are the same in both." width="100%">

Why both:

- **Banks that cannot send documents out** can keep pages on their own machines. No measured run has yet: the open-weights arm used Baseten, and SAM 3.1 still ran on Meta's API.
- **The method, not one model, gives the accuracy.** On the same pre-registered test the open-weights arm let in 3.0 wrong values per 1,000 accepted against 3.6 hosted, meeting its target of under 1%. It also extracted with Muse Spark Open, so this compares whole set-ups.
- **Cost per page** was $0.0564 open weights against $0.0089 hosted on that test. Hosted calls ran at the hackathon's Contributor discount: $0.10 in and $0.20 out per million tokens against $1.25 and $4.25 at the standard price (`config/models.toml`, D19). The gap is partly price.

Measured so far:

- **Hosted:** the synthetic test; the real Treasury pages (run on 2026-10-29, scores [pending]).
- **Open weights:** the synthetic test; development pages of the Treasury Bulletin, for cost, speed and empty answers only, with no accuracy; real held-out pages [pending]; your own hardware, not measured.

<details>
<summary>The four Meta models: exact ids, hosts, jobs, and what the open-weights report found</summary>

The report is [`results/openw_measure/REPORT.md`](https://github.com/kamil-shirinov/Archivist/blob/openw-measure/results/openw_measure/REPORT.md) on branch `openw-measure` (commit `633cdff`, not merged). It used development pages only and made no call to Meta's API.

| Model | Exact id (file) | Host | Job | What the report found |
|---|---|---|---|---|
| Muse Spark 1.3 | `muse-spark-1.3-contributor` (`config/models.toml`) | Meta Model API | Sorts, reads and cites, re-reads blind, drafts templates | A one-value re-read costs $0.00011; the open model's costs about 25 times as much. |
| Muse Spark Open | `meta-models/muse-spark-open-1026` (`config/models_open.toml`) | Baseten | The same jobs, in open-weights mode | Takes "low" reasoning but does not honour "minimal". 5 of 200 re-reads came back empty (2.5%). $0.0028 a re-read, 2.1 a second at 8 at once. The report's pick for both jobs. |
| Muse Spark Open | `accounts/fireworks/models/muse-spark-open` (`config/models_fireworks.toml`) | Fireworks | A second host, measured only | 3 of 200 re-reads empty. Answered "can't read" for 103 of 200 crops (51.5%) against 8 of 200 on Baseten. 0.39 re-reads a second. One page read did not return in 30 minutes. |
| SAM 3.1 | `sam-3.1` (every config) | Meta Model API | Finds covered ink | Not measured there. It stayed on Meta's API in the open-weights arm. |
| Muse Glimmer | `meta-models/Muse-Glimmer-30B@a4e59da52a7bc87ae7251dd5545c0dd437c44b68` (branch `glimmer`, `results/glimmer/baseline_roles.toml`; not in `config/`) | Modal GPUs | A second opinion for sorting pages, from the page's text | Not in that report. Its own phase-1 report ([`results/glimmer/REPORT.md`](https://github.com/kamil-shirinov/Archivist/blob/glimmer/results/glimmer/REPORT.md)): on 40 development pages, scored against Muse Spark's own confirmed answers, untrained 39 of 40; trained 0 of 40 under the frozen parser and 40 of 40 under a diagnostic added afterwards, which is not a pre-registered claim. Phase 2: [pending]. |

On development pages of real scans the report also found Muse Spark Open's own boxes sit away from the printed figures, so the box step anchors fewer cells and most re-read crops come from the wrong place (report section 4.5).

</details>

## Results

On the pre-registered synthetic test Archivist met three of five targets. The numbers are in [`results/test_report.json`](results/test_report.json) and [`results/TEST_RESULTS.md`](results/TEST_RESULTS.md). A 95% interval is the middle 95% of a rate recomputed on 2,000 resamples of the test pages.

| | Target | Result | Verdict |
|---|---|---|---|
| H1 | Wrong values among those accepted: lower than reading once, intervals not overlapping | 0.36% (0.14% to 0.67%) against 4.45% (2.28% to 7.14%) | Met |
| H2 | Catches at least 85% of wrong values | 93.65% (88.31% to 97.28%): 177 of 189 | Met |
| H3 | Sends at most 20% of values to a person | 21.58% (15.44% to 27.87%): 921 of 4,267 | **Missed** |
| H4 | All-open-weights arm: under 1% wrong among accepted | 0.30% (0.12% to 0.54%): 10 of 3,296 | Met |
| H5 | Flags at least 90% of the planted source errors | 88.46%: 23 of 26 (the report gives no interval) | **Missed** |

<img src="docs/img/chart-mistakes.svg" alt="Bar chart: wrong values per 1,000 accepted. Read once, 44.5 with interval 22.8 to 71.4. Archivist, 3.6 with interval 1.4 to 6.7." width="100%">

<img src="docs/img/chart-hosted-vs-open.svg" alt="Three bar charts comparing hosted and open weights on the same test: wrong values per 1,000 accepted, share of wrong values caught, and share of values sent to a person." width="100%">

<img src="docs/img/chart-review-by-condition.svg" alt="Grouped bar chart: share of values sent to a person for each scan condition from 0 (mildest) to 3 (worst), hosted and open weights." width="100%">

The charts are drawn from the report by [`docs/make_charts.py`](docs/make_charts.py).

**Real-scan test** (plan: [`PREREGISTRATION_REAL.md`](PREREGISTRATION_REAL.md); records: `results/real_test/held_out/`). Held-out pages are ones the system never saw while it was built. The sweep sorted all 4,569 held-out Treasury Bulletin pages (46 issues: 1940 to 1942 and each June of 1985 to 1994) among five approved table types. The model assigned 291 and a plain-code title check confirmed 136. The deep check ran the full pipeline on 58: 33,114 table cells and 29,018 blind re-reads. The answer key is 400 cells drawn in advance and labelled by the author from the printed page, never shown a model's figure; 40 are labelled again a day or more later. The scorer runs once the labels are committed, on the code tagged `run-real-treasury`.

- [real-scan results, version 1, hosted: pending]
- [real-scan results, open weights: pending]
- [version 2: pending]

## Why it's built this way

- **Every value is read twice, once without seeing the first answer,** because a model reading in context can make a mistake add up: in development a misread debit was carried through every later balance, so arithmetic alone passed it (D26).
- **The arithmetic is plain code,** so it cannot share a model's blind spots and anyone can read the rules (D4, D24).
- **Tests use held-out pages the system never saw while it was built,** so a score cannot be tuned: the synthetic test set was generated once and the real pages were split before any model saw one (D7, D30).
- **The answer key is hand-labelled,** because on real scans only a person reading the printed page can say what is true.
- **Only synthetic or public-domain pages reach a model,** because free-credit API traffic may be used by Meta for product improvement (D14).
- **Two modes,** so the accuracy belongs to the method and a bank can choose where its pages go ([Two ways to run it](#two-ways-to-run-it)).

## Proof and dates

Each plan was committed before the runs it governs. Dates are from `git log`, set by the committer's clock, not a third-party timestamp.

<details>
<summary>Pre-registrations beside the commits they govern</summary>

| Registered | Commit or tag | Date (UTC) | Governs | Commits that follow |
|---|---|---|---|---|
| Synthetic test set and plan (`PREREGISTRATION.md`; manifest sha256 `78db32f3…`) | `fc85fce` | 2026-10-27 07:45 | 157 pages, four configurations | Baseline `a5375ae` 07:58; arm A `6240efd` 09:34; arm C `e7b728f` 12:15; arm B `b330c12` 14:47; report `5297b60` 15:03. The code it froze: `63d7d5e`, 00:37 the same day. |
| Real-pages plan (`PREREGISTRATION_REAL.md`), tag `prereg-real-treasury` | `c69d24a` | 2026-10-29 08:02 | Held-out Treasury issues | Title check and runner `462828d`, `b8ff15d` |
| Runner code, tag `run-real-treasury` | `b8ff15d` | 2026-10-29 08:41 | The held-out run | Sweep began 08:49:35 and the deep check finished 23:55:06 (`results/real_test/held_out/`); records `00da8e1`, 23:59 |
| Draw of the 400 values to label | `6d35bae` | 2026-10-30 00:00 | The answer key | `labels/draw.json` |
| Scorer, tested on synthetic records only | `b934786` | 2026-10-30 07:26 | The scoring | Weights decision recorded `f1d3091`, 07:38, before any scoring |
| Real-scan score | [pending] | [pending] | | |

The tags are lightweight, so git stores the tagged commit's date, not when the tag was made; the run's own timestamps (`sweep.json`) show it began after the tagged commit. Both plans have changed only below their Deviations heading (checked 2026-10-31).

</details>

The first commit is `dd55660`, 2026-10-26 16:06 UTC, and there is none before it. Everything in the repository was built from 26 Oct 2026, except the third-party components in Credits.

## Honest limits

- **Two targets were missed:** 21.58% of values went to a person against a 20% limit (H3), and 23 of 26 planted source errors were flagged, 88.46% against 90% (H5).
- **The synthetic test is one run** on 157 pages from 12 accounts, which share names and amounts, so the intervals may understate the uncertainty.
- **Boxes can sit away from the printed value on pages where section headings repeat.** [box-offset measurement: not yet in a committed file]
- **The templates drifted on the wartime layout.** They were drafted from 1939 pages. Of the 58 deep-check pages, 39 print different columns from their template (all from April 1940 on), 18 match (one only as far as its text layer reaches) and one is a different table (`PREREGISTRATION_REAL.md`, Deviations). The results will score cells both ways.
- **One page passed the title check wrongly.** A table of revisions to security transactions was confirmed because its title contains the approved one. The results will name this as a weakness of the check.
- **Hosted costs use the Contributor discount.** Real deployments would pay the standard price or use open weights (D19).
- **Open weights are untested on real scans** and have not run on-site. The real-scan test has one labeller, the author, and covers later issues of tables the system was built from, not unseen archives.

## Run it yourself

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
```

```bash
uv run pytest -q && uv run python -m archivist.replay
```

That second command is the Check. `cache/`, the saved model answers, is not committed, so `replay` stops at the missing cache. Without the Treasury scans and rebuilt development images, three tests in `tests/test_export.py` also fail (3 failed, 1,379 passed, 1 skipped, 2026-10-31).

From the repository alone, with no key and no model call, you can:

- Re-score the pre-registered test: `uv run python -m archivist.eval.test_report` rewrote `results/test_report.json` and `results/TEST_RESULTS.md` unchanged in a clean checkout (24 seconds, 2026-10-31).
- Check a committed export against its run: `uv run python -m archivist.export.bundle --run test-archivist-A --check`.
- Check the charts against the data: `uv run python docs/make_charts.py --check`.

Not reproducible here: the model calls, which need a key and spend, and the held-out real-page run, which ran once on the tagged code. Its scans come from FRASER (`uv run python -m archivist.ingest.fraser`) and are not committed.

### Reading a page live

For the demo, a local app reads a page with real model calls, each visible as it happens. It runs only on your machine.

```bash
uv run python -m archivist.live
```

Open the address it prints and choose **Read a page**. **Live calls** needs `META_API_KEY` (and `BASETEN_API_KEY` for open-weight choices) in your environment or an uncommitted `.env`; every call still passes the cache, spend caps and ledger. **Replay** plays a recorded read from `cache/` and spends nothing. Only development pages are offered. See [`docs/live-reading.md`](docs/live-reading.md).

## What's next

A learning loop, not built yet. People correct values in the review queue and the corrections are kept. A new version is trained on them, measured on held-back pages, and approved by a person before it replaces the current one. Today a reviewer's answers stay in their own browser.

<details>
<summary>Credits</summary>

**Fonts.** Rendering synthetic documents: Libre Baskerville, Courier Prime and Nanum Pen Script (SIL Open Font License 1.1); Special Elite and Homemade Apple (Apache License 2.0). Licence files are in `assets/fonts/`. The review app uses Geist (SIL Open Font License 1.1, `ui/fonts/GEIST-OFL.txt`). Sources and dates: [`DATA_SOURCES.md`](DATA_SOURCES.md).

**Libraries** (`pyproject.toml`): faker, meta-sam-parser, numpy, openai (the SDK that calls the APIs), pillow, pydantic, pypdfium2, python-dotenv, pyyaml; for development jsonschema, pre-commit and pytest. Python 3.12, locked with uv.

**Data.** All from FRASER, the St. Louis Fed's archive; PDFs are not committed, and per-file records are in each source's `sources.json`.

| Source | Rights statement |
|---|---|
| Treasury Bulletin, 1939 to 1942 and June 1982 to 1994 | FRASER's statement for the title: "No Copyright - United States" |
| Annual Report of the Comptroller of the Currency, 1905 to 1940 | FRASER shows none. Recorded basis: works of the US Government (17 U.S.C. § 105), and public domain by age for 1905 to 1930 |
| Federal Reserve Bulletin, June issues 1980 to 2003 | FRASER's title-page statement "No Copyright - United States", plus the Board's standing as a federal agency (17 U.S.C. § 105). Not checked: material credited to someone outside the Board |

No real bank or customer data is used.

**Models.** No model licence text is stored in this repository, so none is stated here. The Fireworks listing quoted in `src/archivist/models/fireworks_api.py` describes Muse Spark Open as an open-weights reasoning model with 816B total and 42B active parameters. [model licences: to be confirmed from Meta's pages]

</details>
