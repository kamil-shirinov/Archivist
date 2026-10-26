"""Two extractors on the same pages, side by side (P13): results/extractor_compare.json.

    python -m archivist.eval.compare_extractors

Scores each extraction run of RUNS afresh against its split's ground truth (run_eval.evaluate)
and writes, per split and per arm, the run's extractor, citation strategy, failed pages, cost and
overall and per-severity statistics with page-bootstrap 95% intervals; then Muse Spark Open minus
Muse Spark 1.3, overall and per severity, with whether the two intervals overlap. Nothing is
called: the runs' predictions are already on disk, so the file is regenerated from the repo.

closing_repairs counts the answers whose missing closing brackets baseten_api.close_brackets
supplied (D28). The repair is logged as a warning when the call is made, and the cache keeps only
the repaired answer, so the counts are those the P13 runs logged, recorded here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from archivist.eval.run_eval import DATA_ROOT, evaluate
from archivist.pipeline.extract import RUNS_DIR

OUT_PATH = Path("results/extractor_compare.json")
SPLITS = ("dev", "val")
# arm -> split -> extraction run
RUNS = {
    "muse-spark-1.3-contributor": {"dev": "baseline-dev-v1", "val": "baseline-val-s0"},
    "muse-spark-open": {"dev": "baseline-dev-open", "val": "baseline-val-open"},
    "muse-spark-open-unrepaired": {
        "dev": "baseline-dev-open-unrepaired",
        "val": "baseline-val-open-unrepaired",
    },
}
CLOSING_REPAIRS = {"baseline-dev-open": 8, "baseline-val-open": 6}  # logged by the P13 runs
BASE, OTHER = "muse-spark-1.3-contributor", "muse-spark-open"
WHAT = (
    "Single-pass extraction (classify, then read every field) by two models, same prompts, same "
    "pages, scored by archivist.eval.run_eval. 95% intervals are page-bootstrap."
)
CAVEATS = [
    "muse-spark-open is the run with the closing-bracket repair (baseten_api.close_brackets). "
    "Muse Spark Open, asked for JSON through the prompt, ended 75% of its ledger-card answers "
    "one } short (finish_reason stop); muse-spark-open-unrepaired is the first run, without the "
    "repair, where those pages failed to parse and are scored as omitted. The repair touches the "
    "form of an answer, never a value; 'closing_repairs' counts the answers it was applied to.",
    "reasoning_effort is low for both. Muse Spark Open always reasons and has no structured "
    "outputs: its schema is given in the prompt, Muse Spark 1.3's through response_format.",
    "The runs differ in the citation step (run.json 'citations'); field accuracy and error rate "
    "do not depend on the boxes.",
    "dev is development data (D26); val is development data too. Nothing here was scored on the "
    "frozen test set.",
]


def _stats(s: dict) -> dict:
    return {
        "pages": s["n_pages"],
        "fields": s["n_fields"],
        "accepted": s["n_accepted"],
        "counts": s["counts"],
        "field_accuracy": s["field_accuracy"],
        "field_accuracy_ci95": s["field_accuracy_ci95"],
        "error_rate_accepted": s["error_rate_accepted"],
        "error_rate_ci95": s["error_rate_ci95"],
        "classification_accuracy": s["classification_accuracy"],
    }


def arm(run_dir: Path) -> dict:
    """One extraction run, scored against its split's ground truth."""
    run = json.loads((run_dir / "run.json").read_text())
    split = Path(run["images"]).parent.name
    metrics = evaluate(run_dir, DATA_ROOT / split / "gt")
    out = {
        "run_id": run_dir.name,
        "extractor": run["config"]["extractor"],
        "citations": run.get("citations", "S0"),  # runs before --citations existed were S0
        "pages_failed": len(run["failed_pages"]),
        "failed_pages": sorted(run["failed_pages"]),
        "cost_usd": run["cost_usd"],
        "overall": _stats(metrics["overall"]),
        "by_severity": {k: _stats(v) for k, v in metrics["by_severity"].items()},
    }
    if run_dir.name in CLOSING_REPAIRS:
        out["closing_repairs"] = CLOSING_REPAIRS[run_dir.name]
    return out


def _overlap(a: list[float] | None, b: list[float] | None) -> bool | None:
    if a is None or b is None:
        return None
    return a[0] <= b[1] and b[0] <= a[1]


def difference(other: dict, base: dict) -> dict:
    """other minus base, on field accuracy and the error rate among accepted fields."""
    return {
        "field_accuracy": other["field_accuracy"] - base["field_accuracy"],
        "field_accuracy_intervals_overlap": _overlap(
            other["field_accuracy_ci95"], base["field_accuracy_ci95"]
        ),
        "error_rate_accepted": other["error_rate_accepted"] - base["error_rate_accepted"],
        "error_rate_intervals_overlap": _overlap(other["error_rate_ci95"], base["error_rate_ci95"]),
    }


def compare(runs_dir: Path = RUNS_DIR) -> dict:
    report: dict = {"what": WHAT, "caveats": CAVEATS}
    for split in SPLITS:
        arms = {name: arm(runs_dir / splits[split]) for name, splits in RUNS.items()}
        base, other = arms[BASE], arms[OTHER]
        report[split] = {
            "arms": arms,
            "open_minus_1_3": {
                "overall": difference(other["overall"], base["overall"]),
                "by_severity": {
                    k: difference(other["by_severity"][k], base["by_severity"][k])
                    for k in base["by_severity"]
                },
            },
        }
    return report


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.parse_args(argv)
    report = compare()
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for split in SPLITS:
        print(split)
        for name, a in report[split]["arms"].items():
            o = a["overall"]
            print(
                f"  {name:<28} accuracy {_number(o['field_accuracy'])}  error rate "
                f"{_number(o['error_rate_accepted'])}  failed pages {a['pages_failed']:>2}  "
                f"${a['cost_usd']:.4f}"
            )
    print(f"-> {OUT_PATH}")


if __name__ == "__main__":
    main()
