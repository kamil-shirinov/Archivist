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

A verdict run (archivist.pipeline.verify, with verdicts.jsonl) is scored side by side with the
extraction run it verified, which accepts every value it didn't abstain on: errors caught (wrong
and sent to review), errors missed (accepted and not correct), false alarms (correct and sent to
review, not counting a source error's fields), review rate, error rate among accepted fields,
risk–coverage points, how often a proposed correction equals the printed value, and source-error
detection (any of its fields sent to review). For re-read fields it also reports how often the
re-reader agreed with a wrong extraction: the independence number, lower is better. Overall, per
severity, per doc type and per verification route, with page-bootstrap 95% intervals; how many
proposals came from the re-read chain (D26) and how many of those were right; and the wrong
fields it accepted.

    python -m archivist.eval.run_eval --run archivist-dev-v1 --split dev

A verdict run records the outcome of every policy (verify.py); --policy v2 or v3 scores it under
that one (verify.as_policy) into metrics_<policy>.json, and without it the verdicts' own policy is
scored into metrics.json.

--compare-checks DEV_RUN VAL_RUN writes results/checks_val.json: the checks report of two runs
side by side, flags tallied by the rule that raised them, and the wrong fields no flag caught.

--compare-verdicts RUN [RUN ...] writes results/verdicts_compare.json: scored verdict runs (their
metrics.json) side by side with each other and with the extraction runs they verified.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from archivist.doctypes import is_unresolvable
from archivist.eval.metrics import (
    WRONG,
    FieldOutcome,
    bootstrap_ci,
    normalise,
    risk_coverage,
    score_page,
    summarise,
)
from archivist.pipeline.checks import FLAGS_FILE, load_flags
from archivist.pipeline.extract import RUNS_DIR, PageExtraction, load_predictions
from archivist.pipeline.verify import (
    POLICIES,
    VERDICTS_FILE,
    Evidence,
    as_policy,
    load_verdicts,
)
from archivist.schema import Flag, PageGT, SourceError

DATA_ROOT = Path("data")
CHECKS_VAL_PATH = Path("results/checks_val.json")
VERDICTS_COMPARE_PATH = Path("results/verdicts_compare.json")
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


# Which rule raised a flag, from the wording of its detail: (rule, check, phrases), first match.
CHECK_RULES = (
    ("unreadable", "arithmetic", ("can't be read as", "blank, but must hold")),
    ("running_balance", "arithmetic", ("but the balance reads",)),
    ("carried_forward", "arithmetic", ("carried forward",)),
    ("one_side", "arithmetic", ("a line is one or the other",)),
    ("date_order", "arithmetic", ("the date goes backwards",)),
    ("cheque_order", "arithmetic", ("the cheque number goes backwards",)),
    ("words_figures", "words_figures", ("",)),
    ("sheet_order", "crossdoc", ("never goes backwards along an account",)),
    ("carry_across_sheets", "crossdoc", ("brings forward",)),
    ("card_account_by_holder", "crossdoc", ("fills the gap",)),
    ("memo_account_by_posting", "crossdoc", ("the memo's account reads",)),
    ("memo_amount", "crossdoc", ("the memo pays",)),
    ("memo_date", "crossdoc", ("the memo is dated",)),
)


def check_rule(flag: Flag) -> str:
    if is_unresolvable(flag):
        return "unresolvable"
    for rule, check, phrases in CHECK_RULES:
        if flag.check == check and any(p in flag.detail for p in phrases):
            return rule
    return "other"


def _source_errors(pages: Sequence[PageGT]) -> list[SourceError]:
    """A source error shared by a memo and its card is listed on both pages: count it once."""
    unique = {(e.kind, tuple(e.field_ids)): e for page in pages for e in page.source_errors}
    return list(unique.values())


def _rules(
    outcomes: Sequence[FieldOutcome], flags: Sequence[Flag], source_fields: set[str]
) -> dict:
    """Flags per rule: on wrong fields, on a source error's fields, and false alarms."""
    by_id = {o.field_id: o for o in outcomes}
    tally: dict[str, Counter] = defaultdict(Counter)
    for flag in flags:
        rule, o = check_rule(flag), by_id.get(flag.field_id)
        tally[rule]["flags"] += 1
        if o is None:
            continue
        if o.outcome in WRONG:
            tally[rule]["on_wrong"] += 1
        elif o.field_id in source_fields:
            tally[rule]["on_source_error"] += 1
        elif o.outcome == "correct":
            tally[rule]["false_alarms"] += 1
    keys = ("flags", "on_wrong", "on_source_error", "false_alarms")
    return {rule: {k: tally[rule][k] for k in keys} for rule in sorted(tally)}


def checks_generalisation(run_dirs: dict[str, Path]) -> dict:
    """The checks report of each run, by rule, with the wrong fields no flag caught."""
    out = {}
    for name, run_dir in run_dirs.items():
        split = Path(json.loads((run_dir / "run.json").read_text())["images"]).parent.name
        pages = load_gt(DATA_ROOT / split / "gt")
        predictions = load_predictions(run_dir / "predictions.jsonl")
        flags = load_flags(run_dir / FLAGS_FILE)
        report = checks_report(pages, predictions, flags)
        by_page = {p.page_id: p.values for p in predictions}
        outcomes = [o for page in pages for o in score_page(page, by_page.get(page.page_id, []))]
        source_fields = {f for e in _source_errors(pages) for f in e.field_ids}
        flagged = {f.field_id for f in flags if not is_unresolvable(f)}
        out[name] = {
            "run": run_dir.name,
            "split": split,
            "overall": report["overall"],
            "by_doc_type": report["by_doc_type"],
            "by_severity": report["by_severity"],
            "source_errors_by_kind": report["source_errors_by_kind"],
            "by_rule": _rules(outcomes, flags, source_fields),
            "missed": [
                {
                    "field_id": o.field_id,
                    "severity": o.severity,
                    "occluded": o.occluded,
                    "printed": o.printed,
                    "predicted": o.predicted,
                    "outcome": o.outcome,
                }
                for o in outcomes
                if o.outcome in WRONG and o.field_id not in flagged
            ],
        }
    return out


# --- Verdict runs ---------------------------------------------------------------------------

READ_BACK = frozenset({"agrees", "disagrees", "illegible"})  # a re-read that returned an answer
CI_KEYS = ("error_rate_accepted", "catch_rate", "false_alarm_rate", "review_rate")


def _rates(outcomes: Sequence[FieldOutcome], source_fields: set[str]) -> dict:
    """The rates that get intervals, in one pass; see _verdict_stats."""
    n = wrong = caught = correct = alarms = accepted = missed = review = 0
    for o in outcomes:
        n += 1
        if o.status == "accepted":
            accepted += 1
            missed += o.outcome != "correct"
        review += o.status == "review"
        if o.outcome in WRONG:
            wrong += 1
            caught += o.status == "review"
        elif o.outcome == "correct" and o.field_id not in source_fields:
            correct += 1
            alarms += o.status == "review"
    return {
        "error_rate_accepted": _ratio(missed, accepted),
        "catch_rate": _ratio(caught, wrong),
        "false_alarm_rate": _ratio(alarms, correct),
        "review_rate": _ratio(review, n),
    }


def _bootstrap(
    outcomes: Sequence[FieldOutcome], source_fields: set[str], n: int = 2000, seed: int = 0
) -> dict[str, tuple[float, float] | None]:
    """bootstrap_ci for every CI key at once: the same page resamples, one pass each."""
    by_page: dict[str, list[FieldOutcome]] = defaultdict(list)
    for o in outcomes:
        by_page[o.page_id].append(o)
    pages = [by_page[p] for p in sorted(by_page)]
    values: dict[str, list[float]] = {k: [] for k in CI_KEYS}
    if pages:
        rng = np.random.default_rng(seed)
        for _ in range(n):
            picks = rng.integers(0, len(pages), size=len(pages))
            rates = _rates([o for i in picks for o in pages[i]], source_fields)
            for k in CI_KEYS:
                if rates[k] is not None:
                    values[k].append(rates[k])
    return {
        k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) if v else None
        for k, v in values.items()
    }


def _same(field_id: str, a: str, b: str) -> bool:
    return normalise(field_id, a) == normalise(field_id, b)


def _verdict_stats(
    outcomes: Sequence[FieldOutcome],
    evidence: dict[str, Evidence],
    errors: Sequence[SourceError],
    confidence: bool,
) -> dict:
    """See the module docstring. Evidence is empty for the baseline, which proposes nothing."""
    source_fields = {f for e in errors for f in e.field_ids}
    rates = _rates(outcomes, source_fields)
    counts = Counter(o.status for o in outcomes)
    wrong = [o for o in outcomes if o.outcome in WRONG]
    caught = sum(o.status == "review" for o in wrong)
    accepted = [o for o in outcomes if o.status == "accepted"]
    missed = sum(o.outcome != "correct" for o in accepted)
    correct = [o for o in outcomes if o.outcome == "correct" and o.field_id not in source_fields]
    alarms = sum(o.status == "review" for o in correct)

    proposed = [
        (o, evidence[o.field_id].proposed)
        for o in outcomes
        if o.field_id in evidence and evidence[o.field_id].proposed is not None
    ]
    right = sum(_same(o.field_id, p, o.printed) for o, p in proposed)
    on_wrong = [(o, p) for o, p in proposed if o.outcome in WRONG]
    fixes = sum(_same(o.field_id, p, o.printed) for o, p in on_wrong)
    by_chain = [(o, p) for o, p in proposed if evidence[o.field_id].proposed_by == "reread_chain"]

    reread = [
        (o, evidence[o.field_id].reread_status)
        for o in outcomes
        if o.field_id in evidence and evidence[o.field_id].reread_status in READ_BACK
    ]
    reread_wrong = [s for o, s in reread if o.outcome in WRONG]
    reread_right = [s for o, s in reread if o.outcome == "correct"]
    agreed_wrong = reread_wrong.count("agrees")
    agreed_right = reread_right.count("agrees")

    status = {o.field_id: o.status for o in outcomes}
    here = [e for e in errors if any(f in status for f in e.field_ids)]
    found = sum(any(status.get(f) == "review" for f in e.field_ids) for e in here)

    stats = {
        "n_fields": len(outcomes),
        "n_wrong": len(wrong),
        "n_correct": len(correct),
        "n_accepted": len(accepted),
        "n_review": counts["review"],
        "n_abstained": counts["abstained"],
        "coverage": _ratio(len(accepted), len(outcomes)),
        "review_rate": rates["review_rate"],
        "errors_caught": caught,
        "catch_rate": rates["catch_rate"],
        "errors_missed": missed,
        "error_rate_accepted": rates["error_rate_accepted"],
        "false_alarms": alarms,
        "false_alarm_rate": rates["false_alarm_rate"],
        "n_proposed": len(proposed),
        "proposed_equals_printed": right,
        "proposal_accuracy": _ratio(right, len(proposed)),
        "proposed_on_wrong": len(on_wrong),
        "proposal_fixes": fixes,
        "proposed_by_reread_chain": len(by_chain),
        "reread_chain_proposals_right": sum(_same(o.field_id, p, o.printed) for o, p in by_chain),
        "n_source_errors": len(here),
        "source_errors_found": found,
        "source_error_recall": _ratio(found, len(here)),
        "reread_fields": len(reread),
        "reread_on_wrong": len(reread_wrong),
        "reread_agreed_with_wrong": agreed_wrong,
        "independence": _ratio(agreed_wrong, len(reread_wrong)),
        "reread_on_correct": len(reread_right),
        "reread_agreed_with_correct": agreed_right,
        "reread_confirmation_rate": _ratio(agreed_right, len(reread_right)),
    }
    for key, ci in _bootstrap(outcomes, source_fields).items():
        stats[f"{key}_ci95"] = ci
    points = risk_coverage(outcomes) if confidence else []
    if not confidence and stats["coverage"] is not None:  # accepts everything: a single point
        points = [(stats["coverage"], stats["error_rate_accepted"])]
    stats["risk_coverage"] = [[round(c, 4), None if r is None else round(r, 4)] for c, r in points]
    return stats


@dataclass
class ScoredVerdicts:
    """A verdict run's fields and the run it verified, scored against ground truth."""

    run: dict  # its run.json
    baseline_run: str
    ours: list[FieldOutcome]
    theirs: list[FieldOutcome]  # the extraction run's, which accepts all it didn't abstain on
    evidence: dict[str, Evidence]
    errors: list[SourceError]
    missing_pages: list[str]


def score_verdicts(run_dir: Path, gt_dir: Path, policy: str | None = None) -> ScoredVerdicts:
    """Every ground-truth field's outcome under the run's verdicts, as `policy` decided them
    (verify.as_policy), or as the verdicts say when policy is None.
    """
    pages = load_gt(gt_dir)
    run = json.loads((run_dir / "run.json").read_text())
    baseline_dir = run_dir.parent / run["source_run"]
    verdicts = load_verdicts(run_dir / VERDICTS_FILE)
    if policy is not None:
        verdicts = [as_policy(v, policy) for v in verdicts]
    baseline = {p.page_id: p.values for p in load_predictions(baseline_dir / "predictions.jsonl")}
    by_page: dict[str, list] = defaultdict(list)
    for v in verdicts:
        by_page[v.page_id].append(v)
    unknown = sorted(set(by_page) - {page.page_id for page in pages})
    if unknown:
        raise ValueError(f"verdicts for pages not in {gt_dir}: {unknown[:5]}")
    return ScoredVerdicts(
        run=run,
        baseline_run=baseline_dir.name,
        ours=[o for page in pages for o in score_page(page, by_page.get(page.page_id, []))],
        theirs=[o for page in pages for o in score_page(page, baseline.get(page.page_id, []))],
        evidence={v.field_id: v.evidence for v in verdicts},
        errors=_source_errors(pages),
        missing_pages=sorted(p.page_id for p in pages if p.page_id not in by_page),
    )


def evaluate_verdicts(run_dir: Path, gt_dir: Path, policy: str | None = None) -> dict:
    scored = score_verdicts(run_dir, gt_dir, policy)
    ours, theirs, evidence, errors = scored.ours, scored.theirs, scored.evidence, scored.errors
    route = {fid: e.route for fid, e in evidence.items()}

    def side_by_side(keep: Callable[[FieldOutcome], bool]) -> dict:
        mine = [o for o in ours if keep(o)]
        ids = {o.field_id for o in mine}
        group_errors = [e for e in errors if any(f in ids for f in e.field_ids)]
        return {
            "archivist": _verdict_stats(mine, evidence, group_errors, confidence=True),
            "baseline": _verdict_stats(
                [o for o in theirs if keep(o)], {}, group_errors, confidence=False
            ),
        }

    groups = {
        "by_severity": lambda o: o.severity,
        "by_doc_type": lambda o: o.doc_type,
        "by_route": lambda o: route.get(o.field_id, "no verdict"),
    }
    result = {
        "run_id": run_dir.name,
        "gt": str(gt_dir),
        "baseline_run": scored.baseline_run,
        "config": scored.run.get("config"),
        "policy": scored.run.get("policy"),
        "policy_scored": policy,
        "missing_pages": scored.missing_pages,
        "overall": side_by_side(lambda o: True),
    }
    for group, key in groups.items():
        values = sorted({key(o) for o in ours}, key=str)
        result[group] = {
            str(v): side_by_side(lambda o, key=key, v=v: key(o) == v) for v in values
        }
    result["missed"] = [
        {
            "field_id": o.field_id,
            "printed": o.printed,
            "predicted": o.predicted,
            "outcome": o.outcome,
            "reread": evidence[o.field_id].reread if o.field_id in evidence else None,
        }
        for o in ours
        if o.status == "accepted" and o.outcome != "correct"
    ]
    return result


COMPARED = (
    "n_fields",
    "n_wrong",
    "error_rate_accepted",
    "error_rate_accepted_ci95",
    "errors_caught",
    "errors_missed",
    "false_alarms",
    "false_alarm_rate",
    "review_rate",
    "n_proposed",
    "proposed_equals_printed",
    "proposal_accuracy",
    "proposed_by_reread_chain",
    "reread_chain_proposals_right",
    "independence",
)


def verdict_comparison(run_dirs: Sequence[Path]) -> dict:
    """Scored verdict runs side by side with the runs they verified, from their metrics.json."""
    rows: dict[str, dict] = {}
    for run_dir in run_dirs:
        metrics = json.loads((run_dir / "metrics.json").read_text())
        overall = metrics["overall"]
        rows.setdefault(
            metrics["baseline_run"],
            {"kind": "baseline", "gt": metrics["gt"]}
            | {k: overall["baseline"].get(k) for k in COMPARED},
        )
        rows[run_dir.name] = (
            {"kind": "archivist", "gt": metrics["gt"], "verifies": metrics["baseline_run"]}
            | {k: overall["archivist"].get(k) for k in COMPARED}
            | {"missed": metrics.get("missed")}
        )
    return rows


def comparison_table(rows: dict) -> str:
    header = (
        f"{'':<18} {'split':<5} {'fields':>6} {'wrong':>5}  {'error rate accepted [95% CI]':<29} "
        f"{'caught':>6} {'missed':>6} {'alarms':>6} {'review':>6}  {'proposals right':>15}"
    )
    lines = [header, "-" * len(header)]
    for name, r in rows.items():
        proposals = f"{r['proposed_equals_printed']}/{r['n_proposed']}"
        if r["kind"] == "baseline":
            proposals = ""
        lines.append(
            f"{name:<18} {Path(r['gt']).parent.name:<5} {r['n_fields']:>6} {r['n_wrong']:>5}  "
            f"{_interval(r['error_rate_accepted'], r['error_rate_accepted_ci95']):<29} "
            f"{r['errors_caught']:>6} {r['errors_missed']:>6} {r['false_alarms']:>6} "
            f"{_number(r['review_rate']):>6}  {proposals:>15}"
        )
    return "\n".join(lines)


def verdicts_table(metrics: dict) -> str:
    rows = [("overall", metrics["overall"])]
    rows += [(f"severity {k}", v) for k, v in metrics["by_severity"].items()]
    rows += [(k, v) for k, v in metrics["by_doc_type"].items()]
    rows += [(f"route {k}", v) for k, v in metrics["by_route"].items()]
    header = (
        f"{'':<17} {'fields':>6} {'wrong':>5} {'caught':>6} {'missed':>6} {'alarms':>6} "
        f"{'review':>6}  {'error rate accepted [95% CI]':<29} {'baseline':>8}  "
        f"{'proposals':>9} {'indep':>5}"
    )
    lines = [header, "-" * len(header)]
    for name, both in rows:
        a, b = both["archivist"], both["baseline"]
        lines.append(
            f"{name:<17} {a['n_fields']:>6} {a['n_wrong']:>5} {a['errors_caught']:>6} "
            f"{a['errors_missed']:>6} {a['false_alarms']:>6} {_number(a['review_rate']):>6}  "
            f"{_interval(a['error_rate_accepted'], a['error_rate_accepted_ci95']):<29} "
            f"{_number(b['error_rate_accepted']):>8}  "
            f"{a['proposed_equals_printed']:>4}/{a['n_proposed']:<4} "
            f"{_number(a['independence']):>5}"
        )
    o = metrics["overall"]["archivist"]
    lines.append(
        f"source errors found {o['source_errors_found']}/{o['n_source_errors']}; risk–coverage "
        + ", ".join(f"({c:.3f}, {r:.4f})" for c, r in o["risk_coverage"])
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
    parser.add_argument("--run")
    parser.add_argument("--split")
    parser.add_argument("--compare-checks", nargs=2, metavar=("DEV_RUN", "VAL_RUN"))
    parser.add_argument("--compare-verdicts", nargs="+", metavar="VERDICT_RUN")
    parser.add_argument("--policy", choices=POLICIES, help="score a verdict run under this policy")
    args = parser.parse_args(argv)

    if args.compare_verdicts:
        rows = verdict_comparison([RUNS_DIR / r for r in args.compare_verdicts])
        VERDICTS_COMPARE_PATH.write_text(json.dumps(rows, indent=2) + "\n")
        print(comparison_table(rows))
        print(
            "error rate among accepted fields; caught/missed = wrong fields sent to review/"
            "accepted;\nalarms = correct fields sent to review; proposals = equal to the "
            f"printed value/made -> {VERDICTS_COMPARE_PATH}"
        )
        return
    if args.compare_checks:
        dev, val = args.compare_checks
        report = checks_generalisation({"dev": RUNS_DIR / dev, "val": RUNS_DIR / val})
        CHECKS_VAL_PATH.write_text(json.dumps(report, indent=2) + "\n")
        for name, r in report.items():
            print(f"{name} ({r['run']})")
            print(checks_table(r))
            print()
        return
    if not (args.run and args.split):
        parser.error("--run and --split are required unless --compare-checks is given")

    run_dir = RUNS_DIR / args.run
    gt_dir = DATA_ROOT / args.split / "gt"
    if (run_dir / VERDICTS_FILE).exists():
        metrics = evaluate_verdicts(run_dir, gt_dir, args.policy)
        name = "metrics.json" if args.policy is None else f"metrics_{args.policy}.json"
        (run_dir / name).write_text(json.dumps(metrics, indent=2) + "\n")
        print(verdicts_table(metrics))
        print(
            "caught = wrong and sent to review; missed = accepted and wrong; alarms = correct "
            "and sent to review;\nbaseline = the error rate of the run it verified; proposals = "
            "right/proposed; indep = re-read agreed with a wrong extraction"
        )
        return
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
