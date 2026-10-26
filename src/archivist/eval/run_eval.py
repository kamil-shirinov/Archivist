"""Score a run against ground truth.

    python -m archivist.eval.run_eval --run baseline-dev-v1 --split dev

Reads results/runs/<run>/predictions.jsonl and data/<split>/gt/, scores every ground-truth field
with metrics.py, and writes results/runs/<run>/metrics.json: summarise()'s overall, by_severity
and by_doc_type statistics, each with classification accuracy and page-bootstrap 95% intervals
for field accuracy and the error rate of accepted values. A page with no prediction (failed or
never run) scores every field as omitted and its classification as wrong.

If the run has flags.jsonl (archivist.pipeline.checks), it also writes checks_report.json: of the
wrong fields (misread, hallucinated or omitted, as the scorer defines them), how many at least one
flag implicates (check recall); how many correct fields are flagged (false alarms, not counting
the fields of a source error, where a flag is a find); source-error detection; and how often a
suggested value equals the printed one. Unresolvable flags are notes, not error claims, so they
are counted on their own and never as a catch or a false alarm.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

from archivist.doctypes import is_unresolvable
from archivist.eval.metrics import (
    WRONG,
    FieldOutcome,
    bootstrap_ci,
    normalise,
    score_page,
    summarise,
)
from archivist.pipeline.checks import FLAGS_FILE, load_flags
from archivist.pipeline.extract import RUNS_DIR, PageExtraction, load_predictions
from archivist.schema import Flag, PageGT

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


def _check_stats(
    outcomes: Sequence[FieldOutcome], flags: dict[str, list[Flag]], source_fields: set[str]
) -> dict:
    wrong = caught = noted = correct = false_alarms = suggested = suggested_ok = 0
    fixes = suggested_wrong = 0
    for o in outcomes:
        errors = [f for f in flags.get(o.field_id, []) if not is_unresolvable(f)]
        notes = len(flags.get(o.field_id, [])) - len(errors)
        if o.outcome in WRONG:
            wrong += 1
            caught += bool(errors)
            noted += bool(notes) and not errors
        elif o.outcome == "correct":
            correct += 1
            false_alarms += bool(errors) and o.field_id not in source_fields
        for flag in errors:
            if flag.suggested is None:
                continue
            same = normalise(o.field_id, flag.suggested) == normalise(o.field_id, o.printed)
            suggested += 1
            suggested_ok += same
            if o.outcome in WRONG:
                suggested_wrong += 1
                fixes += same
    return {
        "n_fields": len(outcomes),
        "n_wrong": wrong,
        "wrong_flagged": caught,
        "check_recall": _ratio(caught, wrong),
        "wrong_only_unresolvable": noted,
        "n_correct": correct,
        "false_alarms": false_alarms,
        "false_alarm_rate": _ratio(false_alarms, correct),
        "n_suggestions": suggested,
        "suggestion_equals_printed": suggested_ok,
        "suggestion_accuracy": _ratio(suggested_ok, suggested),
        "n_suggestions_on_wrong": suggested_wrong,
        "suggestion_fixes": fixes,
    }


def _grouped_checks(
    outcomes: Sequence[FieldOutcome],
    key: Callable[[FieldOutcome], object],
    flags: dict[str, list[Flag]],
    source_fields: set[str],
) -> dict:
    groups: dict = defaultdict(list)
    for o in outcomes:
        groups[key(o)].append(o)
    return {k: _check_stats(groups[k], flags, source_fields) for k in sorted(groups)}


def checks_report(
    pages: Sequence[PageGT], predictions: Sequence[PageExtraction], flags: Sequence[Flag]
) -> dict:
    """How the run's flags line up with ground truth; see the module docstring."""
    by_page = {p.page_id: p for p in predictions}
    outcomes = [
        o
        for page in pages
        for o in score_page(page, by_page[page.page_id].values if page.page_id in by_page else [])
    ]
    by_field: dict[str, list[Flag]] = defaultdict(list)
    for flag in flags:
        by_field[flag.field_id].append(flag)
    # A source error shared by a memo and its card is listed on both pages: count it once.
    errors = {(e.kind, tuple(e.field_ids)): e for page in pages for e in page.source_errors}
    source_fields = {f for e in errors.values() for f in e.field_ids}
    flagged = {f.field_id for f in flags if not is_unresolvable(f)}
    found = {key: any(f in flagged for f in e.field_ids) for key, e in errors.items()}
    by_kind: dict[str, dict] = {}
    for kind in sorted({kind for kind, _ in errors}):
        hits = [hit for (k, _), hit in found.items() if k == kind]
        by_kind[kind] = {"n": len(hits), "found": sum(hits), "recall": _ratio(sum(hits), len(hits))}

    overall = _check_stats(outcomes, by_field, source_fields)
    overall |= {
        "n_flags": len(flags),
        "n_flagged_fields": len({f.field_id for f in flags}),
        "n_unresolvable": sum(is_unresolvable(f) for f in flags),
        "n_source_errors": len(errors),
        "source_errors_found": sum(found.values()),
        "source_error_recall": _ratio(sum(found.values()), len(errors)),
    }
    return {
        "overall": overall,
        "by_doc_type": _grouped_checks(outcomes, lambda o: o.doc_type, by_field, source_fields),
        "by_severity": _grouped_checks(outcomes, lambda o: o.severity, by_field, source_fields),
        "by_check": dict(sorted(Counter(f.check for f in flags).items())),
        "source_errors_by_kind": by_kind,
    }


def checks_table(report: dict) -> str:
    rows = [("overall", report["overall"])]
    rows += [(f"severity {k}", v) for k, v in report["by_severity"].items()]
    rows += [(str(k), v) for k, v in report["by_doc_type"].items()]
    header = (
        f"{'':<12} {'fields':>6} {'wrong':>5} {'flagged':>7} {'recall':>6}  "
        f"{'correct':>7} {'false alarms':>12}  {'suggested':>9} {'= printed':>9} {'fixes':>5}"
    )
    lines = [header, "-" * len(header)]
    for name, s in rows:
        lines.append(
            f"{name:<12} {s['n_fields']:>6} {s['n_wrong']:>5} {s['wrong_flagged']:>7} "
            f"{_number(s['check_recall']):>6}  {s['n_correct']:>7} {s['false_alarms']:>12}  "
            f"{s['n_suggestions']:>9} {s['suggestion_equals_printed']:>9} "
            f"{s['suggestion_fixes']:>5}"
        )
    o = report["overall"]
    lines.append(
        f"source errors found {o['source_errors_found']}/{o['n_source_errors']} "
        f"(recall {_number(o['source_error_recall'])}); {o['n_flags']} flags, "
        f"{o['n_unresolvable']} unresolvable"
    )
    return "\n".join(lines)


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
    gt_dir = DATA_ROOT / args.split / "gt"
    metrics = evaluate(run_dir, gt_dir)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(table(metrics))
    if metrics["missing_pages"]:
        print(f"no prediction for {len(metrics['missing_pages'])} pages, scored as omitted")
    print("error rate = share of accepted values that are wrong; citation = boxes on target")

    flags_path = run_dir / FLAGS_FILE
    if not flags_path.exists():
        print(f"no {FLAGS_FILE}: run archivist.pipeline.checks for the checks report")
        return
    predictions = load_predictions(run_dir / "predictions.jsonl")
    report = checks_report(load_gt(gt_dir), predictions, load_flags(flags_path))
    (run_dir / "checks_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print()
    print(checks_table(report))
    print("recall = wrong fields at least one flag implicates; fixes = suggestions equal to print")


if __name__ == "__main__":
    main()
