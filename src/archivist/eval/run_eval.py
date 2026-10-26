"""Score a run against ground truth.

    python -m archivist.eval.run_eval --run baseline-dev-v1 --split dev

Reads results/runs/<run>/predictions.jsonl and data/<split>/gt/, scores every ground-truth field
with metrics.py, and writes results/runs/<run>/metrics.json: summarise()'s overall, by_severity
and by_doc_type statistics, each with classification accuracy and page-bootstrap 95% intervals
for field accuracy and the error rate of accepted values. A page with no prediction (failed or
never run) scores every field as omitted and its classification as wrong.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from archivist.eval.metrics import FieldOutcome, bootstrap_ci, score_page, summarise
from archivist.pipeline.extract import RUNS_DIR, load_predictions
from archivist.schema import PageGT

DATA_ROOT = Path("data")
# Document-type plug-in name -> the doc_type ground truth gives the same page.
GT_DOC_TYPE = {"ledger_card": "ledger", "payment_memo": "memo"}
INTERVALS = {"field_accuracy": "field_accuracy_ci95", "error_rate_accepted": "error_rate_ci95"}


def load_gt(gt_dir: Path) -> list[PageGT]:
    paths = sorted(p for p in gt_dir.glob("*.json") if p.name != "world.json")
    if not paths:
        raise FileNotFoundError(f"no ground truth in {gt_dir}")
    return [PageGT.model_validate_json(p.read_text()) for p in paths]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _annotate(
    stats: dict, outcomes: Sequence[FieldOutcome], pages: Sequence[PageGT], classified: dict
) -> None:
    stats["n_pages"] = len(pages)
    stats["classification_accuracy"] = _ratio(
        sum(classified[p.page_id] for p in pages), len(pages)
    )
    for metric, key in INTERVALS.items():
        stats[key] = bootstrap_ci(outcomes, metric)


def evaluate(run_dir: Path, gt_dir: Path) -> dict:
    pages = load_gt(gt_dir)
    predictions = {p.page_id: p for p in load_predictions(run_dir / "predictions.jsonl")}
    unknown = sorted(set(predictions) - {page.page_id for page in pages})
    if unknown:
        raise ValueError(f"predictions for pages not in {gt_dir}: {unknown[:5]}")

    outcomes: list[FieldOutcome] = []
    classified: dict[str, bool] = {}
    for page in pages:
        prediction = predictions.get(page.page_id)
        outcomes += score_page(page, prediction.values if prediction else [])
        classified[page.page_id] = (
            prediction is not None and GT_DOC_TYPE.get(prediction.doc_type) == page.doc_type
        )

    summary = summarise(outcomes)
    _annotate(summary["overall"], outcomes, pages, classified)
    for group, attribute in (("by_severity", "severity"), ("by_doc_type", "doc_type")):
        for key, stats in summary[group].items():
            _annotate(
                stats,
                [o for o in outcomes if getattr(o, attribute) == key],
                [p for p in pages if getattr(p, attribute) == key],
                classified,
            )

    run_path = run_dir / "run.json"
    run = json.loads(run_path.read_text()) if run_path.exists() else {}
    return {
        "run_id": run_dir.name,
        "gt": str(gt_dir),
        "config": run.get("config"),
        "missing_pages": sorted(p.page_id for p in pages if p.page_id not in predictions),
        **summary,
    }


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _interval(value: float | None, ci: list[float] | tuple[float, float] | None) -> str:
    bounds = "" if ci is None else f" [{ci[0]:.3f}, {ci[1]:.3f}]"
    return _number(value) + bounds


def table(metrics: dict) -> str:
    rows = [("overall", metrics["overall"])]
    rows += [(f"severity {k}", v) for k, v in metrics["by_severity"].items()]
    rows += [(str(k), v) for k, v in metrics["by_doc_type"].items()]
    header = (
        f"{'':<12} {'pages':>5} {'fields':>6} {'class acc':>9}  "
        f"{'field accuracy [95% CI]':<26} {'error rate [95% CI]':<26} {'citation':>8}"
    )
    lines = [header, "-" * len(header)]
    for name, s in rows:
        lines.append(
            f"{name:<12} {s['n_pages']:>5} {s['n_fields']:>6} "
            f"{_number(s['classification_accuracy']):>9}  "
            f"{_interval(s['field_accuracy'], s['field_accuracy_ci95']):<26} "
            f"{_interval(s['error_rate_accepted'], s['error_rate_ci95']):<26} "
            f"{_number(s['citation_accuracy']):>8}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--split", required=True)
    args = parser.parse_args(argv)

    run_dir = RUNS_DIR / args.run
    metrics = evaluate(run_dir, DATA_ROOT / args.split / "gt")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(table(metrics))
    if metrics["missing_pages"]:
        print(f"no prediction for {len(metrics['missing_pages'])} pages, scored as omitted")
    print("error rate = share of accepted values that are wrong; citation = boxes on target")


if __name__ == "__main__":
    main()
