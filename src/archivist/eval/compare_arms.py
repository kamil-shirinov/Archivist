"""Three arms under two policies, on dev and val, and the headline configuration (P14, D29).

    python -m archivist.eval.compare_arms --verify --workers 8

An arm is a config (config/arms/): which model extracts and which re-reads. A runs both on Muse
Spark 1.3 Contributor, B both on Muse Spark Open (Baseten), C extracts on Muse Spark 1.3 and
re-reads on Muse Spark Open; reasoning effort is "low" everywhere. Each arm verifies an existing
extraction run per split (A and C the same Muse Spark 1.3 runs, B the baseline-*-open runs).
--verify runs those verifications first (archivist.pipeline.verify, through the arm's config; the
cache makes a repeated call free); without it the verdict runs on disk are scored as they are.

Every verdict records both policies' outcomes, so each run is scored under v2 and v3 (run_eval.
score_verdicts), for dev and val separately and pooled: error rate among accepted fields with
page-bootstrap 95% intervals, errors caught and missed, false alarms, review rate (overall and on
severity 3), proposals equal to the printed value out of those made, and cost per page. Pooled
pools the pages of both splits (their ids prefixed with the split) and resamples them together.

Cost per page is what the arm costs on pages it has never seen: the extraction run's recorded
spend plus the verification's calls at the price they were first made at, cache hits included
(verify's cost_full_usd), over the pages.

The decision rule, fixed before the comparison ran (RULE): the headline is the arm and policy
with the lowest pooled error rate among accepted fields; of those within 0.1 percentage points of
it, the one with the lower pooled review rate wins; if still tied, the lower pooled cost per page.
Arm B is reported regardless, as the all-open-weights configuration. Writes
results/arms_compare.json with the winner.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from archivist.eval.run_eval import (
    DATA_ROOT,
    ScoredVerdicts,
    _interval,
    _number,
    _verdict_stats,
    score_verdicts,
)
from archivist.doctypes import from_config
from archivist.models import describe_config, load_roles
from archivist.pipeline import reread, verify
from archivist.pipeline.extract import RUNS_DIR

OUT_PATH = Path("results/arms_compare.json")
SPLITS = ("dev", "val")
TIE = 0.001  # 0.1 percentage points of error rate
RULE = (
    "Lowest pooled (dev + val) error rate among accepted fields; among the arm-policy pairs "
    "within 0.1 percentage points of the lowest, the lower pooled review rate; if still tied, the "
    "lower pooled cost per page. Fixed before the comparison ran. Arm B is reported regardless, "
    "as the all-open-weights configuration."
)
ARMS = {
    "A": {
        "config": "config/arms/a.toml",
        "what": "extractor and rereader on Muse Spark 1.3 Contributor",
        "runs": {"dev": ("baseline-dev-v1", "arm-a-dev"), "val": ("baseline-val-s0", "arm-a-val")},
    },
    "B": {
        "config": "config/arms/b.toml",
        "what": "extractor and rereader on Muse Spark Open (Baseten): all open weights",
        "runs": {
            "dev": ("baseline-dev-open", "arm-b-dev"),
            "val": ("baseline-val-open", "arm-b-val"),
        },
    },
    "C": {
        "config": "config/arms/c.toml",
        "what": "extractor on Muse Spark 1.3 Contributor, rereader on Muse Spark Open (Baseten)",
        "runs": {"dev": ("baseline-dev-v1", "arm-c-dev"), "val": ("baseline-val-s0", "arm-c-val")},
    },
}
OPEN_WEIGHTS = "B"
KEPT = (
    "n_fields",
    "n_wrong",
    "n_accepted",
    "n_review",
    "error_rate_accepted",
    "error_rate_accepted_ci95",
    "errors_caught",
    "catch_rate",
    "errors_missed",
    "false_alarms",
    "false_alarm_rate",
    "review_rate",
    "n_proposed",
    "proposed_equals_printed",
    "proposal_accuracy",
    "independence",
)
CAVEATS = [
    "dev and val are both development data (D26). Nothing here was scored on the frozen test set.",
    "Cost per page: the extraction run's recorded spend plus every verification call (occlusion "
    "and re-reads, second looks included) at the price it was first made at, cache hits counted. "
    "Muse Spark 1.3 runs at Contributor prices (D19); Muse Spark Open's are the figures Baseten's "
    "pricing page prints (config/models.toml), not a contract.",
    "Pooled intervals resample the pages of dev and val together. The extractor of B differs "
    "from A and C, so B's fields carry different extraction errors: its error rate measures the "
    "whole configuration, not the verifier alone.",
    "baseline_error_rate_accepted is the error rate of the extraction run alone, which accepts "
    "every value it didn't abstain on.",
    "The P14 run was resumed once. At --workers 8, 538 Baseten re-reads of arms B and C failed "
    "on HTTP 429 after their retries, and a failed re-read sends its field to review; those "
    "scores are kept in arms_compare_first_pass.json. A failed call is not cached, so the "
    "resume (--workers 2) asked only those calls again and replayed every answer already given; "
    "no re-read or second look of B or C failed in the end. The rule chose the same winner on "
    "both passes. Arm A's two failed re-reads on val are empty answers, not errors, and stand.",
]


def verify_arms(workers: int, runs_dir: Path = RUNS_DIR) -> None:
    """Every arm's verification of every split, through the arm's own config."""
    for name, arm in ARMS.items():
        config = Path(arm["config"])
        roles = load_roles(config)
        guard = roles[reread.ROLE].inner.guard
        for split, (source, out) in arm["runs"].items():
            record = verify.run(
                runs_dir / source,
                runs_dir / out,
                roles,
                guard=guard,
                config=describe_config(config),
                doc_types=from_config(config),
                workers=workers,
            )
            calls = record["calls"]
            print(
                f"arm {name} {split}: {record['counts']['fields']} fields, {calls['rereads']} "
                f"re-reads, {calls['second_looks']} second looks; ${record['cost_usd']:.4f} spent"
            )


def _prefixed(scored: ScoredVerdicts, split: str) -> ScoredVerdicts:
    """The same fields with page and field ids prefixed by the split, so splits can be pooled."""

    def outcomes(items: Sequence) -> list:
        return [
            o.model_copy(
                update={"page_id": f"{split}/{o.page_id}", "field_id": f"{split}/{o.field_id}"}
            )
            for o in items
        ]

    return ScoredVerdicts(
        run=scored.run,
        baseline_run=scored.baseline_run,
        ours=outcomes(scored.ours),
        theirs=outcomes(scored.theirs),
        evidence={f"{split}/{k}": v for k, v in scored.evidence.items()},
        errors=[
            e.model_copy(update={"field_ids": [f"{split}/{f}" for f in e.field_ids]})
            for e in scored.errors
        ],
        missing_pages=[f"{split}/{p}" for p in scored.missing_pages],
    )


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def stats(parts: Sequence[ScoredVerdicts], cost_usd: float) -> dict:
    """One row: the verdict statistics of the pooled parts, review on severity 3 and cost."""
    ours = [o for p in parts for o in p.ours]
    theirs = [o for p in parts for o in p.theirs]
    evidence = {k: v for p in parts for k, v in p.evidence.items()}
    errors = [e for p in parts for e in p.errors]
    full = _verdict_stats(ours, evidence, errors, confidence=True)
    baseline = _verdict_stats(theirs, {}, errors, confidence=False)
    severe = [o for o in ours if o.severity == 3]
    pages = len({o.page_id for o in ours})
    return {
        "n_pages": pages,
        **{k: full[k] for k in KEPT},
        "review_rate_severity_3": _ratio(sum(o.status == "review" for o in severe), len(severe)),
        "cost_usd": cost_usd,
        "cost_per_page_usd": _ratio(cost_usd, pages),
        "baseline_error_rate_accepted": baseline["error_rate_accepted"],
        "missing_pages": [p for part in parts for p in part.missing_pages],
    }


def _cost(run: dict, runs_dir: Path) -> float:
    source = json.loads((runs_dir / run["source_run"] / "run.json").read_text())
    return source["cost_usd"] + run["cost_full_usd"]


def score_arms(runs_dir: Path = RUNS_DIR, data_root: Path = DATA_ROOT) -> dict:
    """arm -> policy -> dev, val and pooled rows; and each arm's runs and second-look counts."""
    results: dict = {}
    runs: dict = {}
    for name, arm in ARMS.items():
        runs[name] = {}
        for split, (_, out) in arm["runs"].items():
            run = json.loads((runs_dir / out / "run.json").read_text())
            runs[name][split] = {
                "source_run": run["source_run"],
                "verdict_run": out,
                "config": run["config"],
                "calls": run["calls"],
                "cost_usd_extraction_and_verification": _cost(run, runs_dir),
            }
        results[name] = {}
        for policy in verify.POLICIES:
            parts, costs, rows = [], [], {}
            for split, (_, out) in arm["runs"].items():
                scored = score_verdicts(runs_dir / out, data_root / split / "gt", policy)
                cost = runs[name][split]["cost_usd_extraction_and_verification"]
                rows[split] = stats([scored], cost)
                parts.append(_prefixed(scored, split))
                costs.append(cost)
            rows["pooled"] = stats(parts, sum(costs))
            results[name][policy] = rows
    return {"runs": runs, "results": results}


def choose(pooled: dict[tuple[str, str], dict]) -> tuple[tuple[str, str], list[dict]]:
    """The winner under RULE, from each (arm, policy)'s pooled row; and the ranking it used."""

    def error(key: tuple[str, str]) -> float:
        rate = pooled[key]["error_rate_accepted"]
        return float("inf") if rate is None else rate

    best = min(error(k) for k in pooled)
    close = [k for k in pooled if error(k) <= best + TIE + 1e-12]
    review = min(pooled[k]["review_rate"] for k in close)
    tied = [k for k in close if abs(pooled[k]["review_rate"] - review) < 1e-12]
    winner = min(tied, key=lambda k: (pooled[k]["cost_per_page_usd"], k))
    ranking = [
        {
            "arm": arm,
            "policy": policy,
            "error_rate_accepted": pooled[(arm, policy)]["error_rate_accepted"],
            "within_tie": (arm, policy) in close,
            "review_rate": pooled[(arm, policy)]["review_rate"],
            "cost_per_page_usd": pooled[(arm, policy)]["cost_per_page_usd"],
        }
        for arm, policy in sorted(pooled, key=lambda k: (error(k), k))
    ]
    return winner, ranking


def compare(runs_dir: Path = RUNS_DIR, data_root: Path = DATA_ROOT) -> dict:
    scored = score_arms(runs_dir, data_root)
    results = scored["results"]
    pooled = {(a, p): rows["pooled"] for a, by in results.items() for p, rows in by.items()}
    (arm, policy), ranking = choose(pooled)
    return {
        "what": "Three arms under policies v2 and v3 on dev and val, and the headline (P14, D29).",
        "rule": RULE,
        "caveats": CAVEATS,
        "arms": {
            name: {"config": a["config"], "what": a["what"], "runs": scored["runs"][name]}
            for name, a in ARMS.items()
        },
        "results": results,
        "ranking": ranking,
        "winner": {
            "arm": arm,
            "policy": policy,
            "config": ARMS[arm]["config"],
            "what": ARMS[arm]["what"],
            "pooled": {k: pooled[(arm, policy)][k] for k in ("error_rate_accepted", "review_rate")},
        },
        "all_open_weights": {
            "arm": OPEN_WEIGHTS,
            "config": ARMS[OPEN_WEIGHTS]["config"],
            "pooled": {p: results[OPEN_WEIGHTS][p]["pooled"] for p in verify.POLICIES},
        },
    }


def table(report: dict) -> str:
    header = (
        f"{'arm':<3} {'policy':<6} {'split':<6} {'fields':>6} {'wrong':>5}  "
        f"{'error rate accepted [95% CI]':<29} {'caught':>6} {'missed':>6} {'alarms':>6} "
        f"{'review':>6} {'sev 3':>6}  {'proposals':>9}  {'$/page':>7}"
    )
    lines = [header, "-" * len(header)]
    for arm, by_policy in report["results"].items():
        for policy, rows in by_policy.items():
            for split, r in rows.items():
                proposals = f"{r['proposed_equals_printed']}/{r['n_proposed']}"
                lines.append(
                    f"{arm:<3} {policy:<6} {split:<6} {r['n_fields']:>6} {r['n_wrong']:>5}  "
                    f"{_interval(r['error_rate_accepted'], r['error_rate_accepted_ci95']):<29} "
                    f"{r['errors_caught']:>6} {r['errors_missed']:>6} {r['false_alarms']:>6} "
                    f"{_number(r['review_rate']):>6} {_number(r['review_rate_severity_3']):>6}  "
                    f"{proposals:>9}  {r['cost_per_page_usd']:>7.4f}"
                )
        lines.append("")
    w = report["winner"]
    lines.append(f"headline: arm {w['arm']} under {w['policy']} ({w['what']}); {report['rule']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--verify", action="store_true", help="run every arm's verification first")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    if args.verify:
        verify_arms(args.workers)
    report = compare()
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(table(report))
    print(
        "caught = wrong and sent to review; missed = accepted and wrong; alarms = correct and sent "
        "to review;\nsev 3 = review rate on severity 3; proposals = equal to the printed value/made"
        f" -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
