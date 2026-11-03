# How every number was measured, and how to reproduce it

One page. Nothing here is a result and nothing was moved: each item links the plan, tag, record, scorer or report where it already lives. The plan for a run was committed before the run, and anything that changed after is recorded under that plan's Deviations heading ([why you can trust the numbers](../README.md#why-you-can-trust-the-numbers)).

## The three pre-registered measurements

| | Synthetic test | Real scans, version 1 (hosted) | Real scans, open weights |
|---|---|---|---|
| **Plan** | [`PREREGISTRATION.md`](../PREREGISTRATION.md) | [`PREREGISTRATION_REAL.md`](../PREREGISTRATION_REAL.md), tag `prereg-real-treasury` | [`PREREGISTRATION_OPENW.md`](../PREREGISTRATION_OPENW.md), tag `prereg-real-openw` |
| **What was measured** | 157 synthetic pages (ledger cards and payment memos), frozen in [`data/test/`](../data/test/) with a hashed manifest, read once by each of four configurations: the read-once baseline and arms A, B and C | Held-out Treasury Bulletin issues: every page sorted among five approved templates, then a deep check of 12 confirmed pages per family | The same pages and the same 400 drawn cells, read by Muse Spark Open |
| **Code that ran** | [`src/archivist/eval/`](../src/archivist/eval/) and [`config/arms/`](../config/arms/) | [`archivist.templates.real_test`](../src/archivist/templates/real_test.py), on the code tagged `run-real-treasury` | [`archivist.templates.real_openw`](../src/archivist/templates/real_openw.py), on the code tagged `run-real-openw` |
| **Records** | [`results/runs/`](../results/runs/) | [`results/real_test/held_out/`](../results/real_test/held_out/): `sweep.json`, `run.json`, `predictions.jsonl`, `verdicts.jsonl`, `boxes.jsonl` | [`results/real_openw/held_out/`](../results/real_openw/held_out/) |
| **Answer key** | The generator's own ground truth, in `data/test/gt/`, which only `archivist.eval` reads | 400 cells drawn in advance ([`draw.json`](../results/real_test/held_out/labels/draw.json)) and labelled by me from the printed page, never shown a model's figure ([`labels.jsonl`](../results/real_test/held_out/labels/labels.jsonl)); 40 labelled again ([`relabels.jsonl`](../results/real_test/held_out/labels/relabels.jsonl)); every first-pass blank checked for a printed dash ([`dashes_checked.jsonl`](../results/real_test/held_out/labels/dashes_checked.jsonl)), which gives the corrected key | The same keys |
| **Scorer** | [`archivist.eval.test_report`](../src/archivist/eval/test_report.py), with [`metrics.py`](../src/archivist/eval/metrics.py) | [`labelling/score.py`](../labelling/score.py), run once on the tag; it refuses anywhere else. The corrected key: [`labelling/score_corrected.py`](../labelling/score_corrected.py), which runs `score.py` again on the same tag | [`labelling/score_openw.py`](../labelling/score_openw.py), run once on its tag; the corrected key through `score_corrected.py`, on that tag |
| **Report** | [`results/test_report.json`](../results/test_report.json), [`results/TEST_RESULTS.md`](../results/TEST_RESULTS.md) | Corrected key: [`score_corrected/score.md`](../results/real_test/held_out/score_corrected/score.md) and `score.json`; as registered: [`score/score.md`](../results/real_test/held_out/score/score.md) and `score.json` | Corrected key: [`score_corrected/score.md`](../results/real_openw/held_out/score_corrected/score.md) and `score.json`; as registered: [`score/score.md`](../results/real_openw/held_out/score/score.md), `score.json` and [`coverage.md`](../results/real_openw/held_out/score/coverage.md) |
| **Tags** | The plan's own commit, in [the dates table](../README.md#why-you-can-trust-the-numbers) | `prereg-real-treasury` (the plan), `run-real-treasury` (the runner), `labels-real-complete` (every label pass, committed before the corrected key was scored) | `prereg-real-openw` (the plan), `run-real-openw` (the runner), and the same `labels-real-complete` |

The tags are lightweight and are records: they are never moved or deleted ([`AGENTS.md`](../AGENTS.md)).

## How the rates and intervals are made

- **Wrong values among those accepted** is wrong values accepted divided by values accepted; the headline compares Archivist's with the single read's. **Caught** is wrong values flagged divided by all wrong values. **Sent to a person** is values not accepted divided by all values.
- **Intervals** are 95% percentile intervals from 2,000 bootstrap resamples by page, seed 0 (`bootstrap_ci` in [`metrics.py`](../src/archivist/eval/metrics.py)). On the real scans, pages are resampled within each stratum and each cell keeps its weight (the inverse of its chance of being labelled, from each family's confirmed pages: [`PREREGISTRATION_REAL.md`](../PREREGISTRATION_REAL.md), Deviations, 2026-10-30). Counts use Wilson intervals.
- **A cell is right or wrong** by the template's own comparison (`TemplateType.canonical` in [`src/archivist/doctypes/template.py`](../src/archivist/doctypes/template.py)). Which conventions that comparison leaves open, and what each is worth, is counted in [the diagnosis](../results/real_test/held_out/diagnosis.md) (aggregates only: it names no cell, page, value or label and changes no score).
- **Variants.** The real-scan scores come in four: all 400 cells kept or the changed-layout pages left out, each with re-reads as run or the unanswered ones counted as failed. The figures quoted in the README and on the landing page are `kept/as_run`, with `left_out/as_run` beside them where the layout matters; the other two are in the score files.
- **Two keys.** The real-scan figures lead with the corrected key, which answers "-" where a check of every first-pass blank on its printed page found a dash, by a rule written down before anyone looked ([`PREREGISTRATION_REAL.md`](../PREREGISTRATION_REAL.md), Deviations, 2 Nov 2026). The official figure, as registered, is always beside it, and R1 and O1 stand as scored.

## Development measurements

These used development pages only, are not pre-registered claims, and held-out pages were never opened for them:

- Page sorting with Muse Glimmer: [`results/glimmer/PLAN.md`](../results/glimmer/PLAN.md), [`results/glimmer/phase2/REPORT.md`](../results/glimmer/phase2/REPORT.md) (aggregate comparison on 791 frozen pages, whose declaration is in [`PREREGISTRATION_REAL.md`](../PREREGISTRATION_REAL.md), Deviations).
- Muse Spark Open's cost, speed and empty answers: [`openw/`](../openw/), [`results/openw_measure/REPORT.md`](../results/openw_measure/REPORT.md); the two hosts: [`results/hosts_compare.md`](../results/hosts_compare.md).
- The fine-tune that stopped at its compute gate: [`results/sparkft/REPORT.md`](../results/sparkft/REPORT.md).
- Boxes anchored to the table's structure (version 2): [`results/v2/PLAN.md`](../results/v2/PLAN.md) (the rule, written first) and [`REPORT.md`](../results/v2/REPORT.md).
- Why a decision went the way it did: [`DECISIONS.md`](../DECISIONS.md). A new table type is a template a person approves: the flow is in [`CLAUDE.md`](../CLAUDE.md) (Document types) and [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Reproduce it

Everything below needs Python 3.12 and [uv](https://docs.astral.sh/uv/), or Docker, and no key, model call or scan.

```bash
uv sync --frozen
uv run python -m archivist.verify
```

`archivist.verify` rebuilds from the committed runs, in a scratch folder, the test report (byte for byte against `results/test_report.json` and `results/TEST_RESULTS.md`), the charts (`docs/make_charts.py --check`), every committed review bundle and database export, and compares the README's headline, results and real-scan figures with the files they come from. It writes nothing to the repository, and exits non-zero on any failure. CI runs it, and runs it again inside the Docker image: `docker run --rm archivist python -m archivist.verify`.

To see one piece alone:

```bash
uv run python -m archivist.eval.test_report                        # rewrites the report; unchanged in a clean checkout
uv run python docs/make_charts.py --check                         # the charts against the report
uv run python -m archivist.export.bundle --run test-archivist-A --check
```

**Needs files that are not committed.** `uv run python -m archivist.replay` replays every committed run from the response cache (`cache/`) and proves nothing it produced changed; it spends nothing and stops on a cache miss. The Treasury scans that some tests read come from `uv run python -m archivist.ingest.fraser`.

**The real-scan scores** are recomputed from the committed records and labels, with no model call, by the scorer on its own tag, in a worktree of that tag: `cd <worktree of run-real-treasury, after uv sync --frozen> && PYTHONPATH=<this checkout> .venv/bin/python -m labelling.score --data <this checkout>`. The open-weights scorer works the same way on `run-real-openw` ([`PREREGISTRATION_OPENW.md`](../PREREGISTRATION_OPENW.md) gives the order). Each score file records the sha256 of every label and record file it used. The dash-corrected key ([`labelling/score_corrected.py`](../labelling/score_corrected.py)) was run once for each configuration, after the relabel and the dash check were committed and tagged `labels-real-complete`: `cd <worktree of run-real-treasury> && PYTHONPATH=<this checkout> .venv/bin/python -m labelling.score_corrected version_1 --data <this checkout>`, then `cd <worktree of run-real-openw> && PYTHONPATH=. .venv/bin/python <this checkout>/labelling/score_corrected.py open_weights --data <this checkout>`. Each first reproduces its official `score.json` from the committed key, and refuses to write anything if it does not.

**Not reproducible here:** the model calls (they need a key and spend) and the held-out runs, each of which ran once, on its tagged code.

## The rules that keep it honest

- Nothing runs on `data/test` except the pre-registered runs, and nothing on the held-out real issues except a pre-registered run by its own runner on its own tag; held-out pages are never used for tuning.
- Scoring rules are written and tested on synthetic records before any model output is scored (D20, D30).
- A plan changes only under its Deviations heading, and a deviation is recorded before the result it concerns.
- Only synthetic or public-domain pages are sent to a model (D14).
