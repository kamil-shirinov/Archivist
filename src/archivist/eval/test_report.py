"""The pre-registered test report (P16): four configurations scored once, five hypotheses judged.

    python -m archivist.eval.test_report

Scores the runs PREREGISTRATION.md lists on data/test with the frozen metrics, the code that
scored dev and val (metrics.py, run_eval.py, verdicts under policy v2), and writes
results/test_report.json and results/TEST_RESULTS.md. Nothing here calls a model: it reads the
runs on disk.

For every configuration: error rate among accepted fields with 95% page-bootstrap intervals
(2,000 resamples, seed 0), errors caught and missed, false alarms, review rate overall and by
severity, proposals right out of proposals made, source-error recall, classification accuracy,
citation accuracy, cost per page and the risk–coverage points. Cost per page is what the
configuration costs on pages it has never seen, as compare_arms counts it: the extraction run's
spend plus every verification call at the price it was first made at, cache hits included.

H1–H5 are then judged against the criteria fixed in PREREGISTRATION.md. H1 asks for non-overlapping
intervals; H2–H5 are thresholds on the rate itself, and the interval is shown beside it.

The report refuses to run if data/test/manifest.json is not the pre-registered file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path

from archivist.eval.metrics import FieldOutcome, score_page, summarise
from archivist.eval.run_eval import (
    DATA_ROOT,
    GT_DOC_TYPE,
    _source_errors,
    _verdict_stats,
    load_gt,
    score_verdicts,
)
from archivist.pipeline.extract import RUNS_DIR, load_predictions
from archivist.schema import PageGT

OUT_JSON = Path("results/test_report.json")
OUT_MD = Path("results/TEST_RESULTS.md")
PREREGISTRATION = Path("PREREGISTRATION.md")
SPLIT = "test"
MANIFEST_SHA256 = "78db32f34cdb7a2aa2fb5ab4f24e5d9540d11729460e9657b604b141c250c1e4"
POLICY = "v2"
BOOTSTRAP = {"unit": "page", "resamples": 2000, "seed": 0}  # run_eval._bootstrap's own settings

BASELINE, HEADLINE, OPEN_WEIGHTS = "baseline", "A", "B"
CONFIGS: dict[str, dict] = {
    BASELINE: {
        "label": "Baseline",
        "what": "Muse Spark 1.3 Contributor reads each page once; every value is accepted",
        "extraction": "test-baseline",
        "verdicts": None,
        "config": "config/models.toml",
    },
    "A": {
        "label": "Archivist, arm A (headline)",
        "what": "Muse Spark 1.3 Contributor reads every value in context and again in isolation, "
        "the documents' own checks, SAM 3.1 occlusion; policy v2",
        "extraction": "test-baseline",
        "verdicts": "test-archivist-A",
        "config": "config/arms/a.toml",
    },
    "B": {
        "label": "Archivist, arm B (all open weights)",
        "what": "Muse Spark Open on Baseten for the extraction and both reads, the documents' own "
        "checks, SAM 3.1 occlusion; policy v2",
        "extraction": "test-baseline-open",
        "verdicts": "test-archivist-B",
        "config": "config/arms/b.toml",
    },
    "C": {
        "label": "Archivist, arm C (two models)",
        "what": "Muse Spark 1.3 Contributor reads in context, Muse Spark Open re-reads in "
        "isolation, the documents' own checks, SAM 3.1 occlusion; policy v2",
        "extraction": "test-baseline",
        "verdicts": "test-archivist-C",
        "config": "config/arms/c.toml",
    },
}

# The criteria of PREREGISTRATION.md, fixed before any run.
H2_CATCH = Fraction(85, 100)  # at least: wrong values sent to review
H3_REVIEW = Fraction(20, 100)  # at most: fields sent to review
H4_ERROR = Fraction(1, 100)  # below: arm B's error rate among accepted fields
H5_SOURCE = Fraction(90, 100)  # at least: planted source errors with a field sent to review

ALONE = ("n_accepted", "errors_missed", "error_rate_accepted", "error_rate_accepted_ci95")
NOTES = [
    "One run of each configuration on one synthetic test set: 157 pages from 12 accounts, with "
    "source errors planted at a fixed rate. Real archives will differ.",
    "The intervals resample pages as if they were independent, as pre-registered. Pages of one "
    "account share names, amounts and balances, so they are not, and the intervals may understate "
    "the uncertainty.",
    "The headline (arm A, policy v2) was chosen on dev and val before the test set was run "
    "(D29). The test set decided nothing.",
    "Error rate among accepted fields counts every accepted value that is not the printed one, "
    "including values accepted as blank. A page that failed to extract scores all its fields as "
    "omitted: they count as wrong values nobody caught, and are not accepted.",
    "False alarms are correct values sent to review, not counting the fields of a planted source "
    "error, where a flag is a find. A source error counts as found when any of its fields is sent "
    "to review; the report does not check the reason given.",
    "Classification and citation accuracy belong to the extraction run, so the arms that verify "
    "the same extraction share them. Citation accuracy is the share of correct values whose box "
    "has its centre inside the printed value's box.",
    "Cost per page is computed from the price lists in the configs, not from invoices. Muse Spark "
    "1.3 runs at Contributor prices (D19). Muse Spark Open's prices are the figures Baseten's "
    "marketing page prints, which is not a contract. Cached input is billed as ordinary input, "
    "so cost is overstated, never understated.",
    "Arm B extracts with a different model, so its error rate measures the whole configuration, "
    "not the verification alone. The row 'extraction alone' shows what each arm's extraction run "
    "would have accepted without verification.",
]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_extraction(extraction_dir: Path, pages: Sequence[PageGT]) -> list[FieldOutcome]:
    """Every ground-truth field's outcome when each value an extraction run read is accepted."""
    predictions = load_predictions(extraction_dir / "predictions.jsonl")
    by_page = {p.page_id: p.values for p in predictions}
    return [o for page in pages for o in score_page(page, by_page.get(page.page_id, []))]


def classification(extraction_dir: Path, pages: Sequence[PageGT]) -> dict:
    """Pages whose document type the run got right; a page it never extracted is wrong."""
    kinds = {p.page_id: p.doc_type for p in load_predictions(extraction_dir / "predictions.jsonl")}
    right = sum(GT_DOC_TYPE.get(kinds.get(page.page_id, "")) == page.doc_type for page in pages)
    return {"right": right, "pages": len(pages), "accuracy": _ratio(right, len(pages))}


def by_severity(outcomes: Sequence[FieldOutcome]) -> dict:
    """Review rate, and what was caught and missed, for the pages of each severity."""
    rows = {}
    for severity in sorted({o.severity for o in outcomes}):
        group = [o for o in outcomes if o.severity == severity]
        review = sum(o.status == "review" for o in group)
        wrong = [o for o in group if o.outcome in ("misread", "hallucinated", "omitted")]
        accepted = [o for o in group if o.status == "accepted"]
        rows[str(severity)] = {
            "n_pages": len({o.page_id for o in group}),
            "n_fields": len(group),
            "n_review": review,
            "review_rate": _ratio(review, len(group)),
            "n_wrong": len(wrong),
            "errors_caught": sum(o.status == "review" for o in wrong),
            "n_accepted": len(accepted),
            "errors_missed": sum(o.outcome != "correct" for o in accepted),
        }
    return rows


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def run_facts(runs_dir: Path, spec: Mapping) -> dict:
    """What the runs behind a configuration did: pages, failures, resumes, calls and spend."""
    extraction = _read(runs_dir / spec["extraction"] / "run.json")
    facts: dict = {
        "extraction": {
            "run": spec["extraction"],
            "config": extraction["config"],
            "citations": extraction.get("citations"),
            "counts": extraction["counts"],
            "failed_pages": extraction["failed_pages"],
            "sessions": len(extraction["sessions"]),
            "aborted": [s["aborted"] for s in extraction["sessions"] if s["aborted"]],
            "cost_usd": extraction["cost_usd"],
        }
    }
    if spec["verdicts"] is not None:
        verdicts = _read(runs_dir / spec["verdicts"] / "run.json")
        facts["verification"] = {
            "run": spec["verdicts"],
            "config": verdicts["config"],
            "policy": verdicts["policy"]["version"],
            "counts": verdicts["counts"],
            "calls": verdicts["calls"],
            "spent_usd": verdicts["cost_usd"],
            "cost_full_usd": verdicts["cost_full_usd"],
        }
    return facts


def score_configuration(key: str, spec: Mapping, runs_dir: Path, gt_dir: Path) -> dict:
    pages = load_gt(gt_dir)
    extraction_dir = runs_dir / spec["extraction"]
    facts = run_facts(runs_dir, spec)
    if spec["verdicts"] is None:
        ours = theirs = score_extraction(extraction_dir, pages)
        evidence, errors = {}, _source_errors(pages)
    else:
        scored = score_verdicts(runs_dir / spec["verdicts"], gt_dir, POLICY)
        ours, theirs, evidence, errors = scored.ours, scored.theirs, scored.evidence, scored.errors
    verified = spec["verdicts"] is not None
    stats = _verdict_stats(ours, evidence, errors, confidence=verified)
    alone = _verdict_stats(theirs, {}, errors, confidence=False) if verified else stats

    cost_extraction = facts["extraction"]["cost_usd"]
    cost_verification = facts["verification"]["cost_full_usd"] if verified else 0.0
    cost = cost_extraction + cost_verification
    stats["wrong_unanswered"] = stats["n_wrong"] - stats["errors_caught"] - stats["errors_missed"]
    return {
        "label": spec["label"],
        "what": spec["what"],
        "config": spec["config"],
        "runs": facts,
        "stats": stats,
        "extraction_alone": {k: alone[k] for k in ALONE},
        "by_severity": by_severity(ours),
        "classification": classification(extraction_dir, pages),
        "citation_accuracy": summarise(theirs)["overall"]["citation_accuracy"],
        "cost": {
            "pages": len(pages),
            "extraction_usd": cost_extraction,
            "verification_usd": cost_verification,
            "total_usd": cost,
            "per_page_usd": cost / len(pages),
        },
    }


def _pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{100 * value:.{digits}f}%"


def _span(interval: Sequence[float] | None) -> str:
    if interval is None:
        return ""
    return f" (95% interval {_pct(interval[0])} to {_pct(interval[1])})"


def _count(part: int, whole: int, rate: float | None) -> str:
    return f"{part} of {whole} ({_pct(rate)})"


def _hypotheses(rows: Mapping[str, dict]) -> dict:
    """H1–H5 against the criteria of PREREGISTRATION.md, each with the numbers it rests on."""
    base, head, open_ = (rows[k]["stats"] for k in (BASELINE, HEADLINE, OPEN_WEIGHTS))
    out = {}

    def errors(s: Mapping) -> dict:
        return {
            "accepted": s["n_accepted"],
            "wrong": s["errors_missed"],
            "rate": s["error_rate_accepted"],
            "ci95": s["error_rate_accepted_ci95"],
        }

    b, h = errors(base), errors(head)
    comparable = None not in (b["rate"], h["rate"], b["ci95"], h["ci95"])
    lower = comparable and h["rate"] < b["rate"]
    apart = comparable and (h["ci95"][1] < b["ci95"][0] or b["ci95"][1] < h["ci95"][0])
    out["H1"] = {
        "claim": "The headline's error rate among accepted fields is lower than the baseline's, "
        "with non-overlapping 95% intervals.",
        "met": bool(lower and apart),
        "numbers": {
            "headline": h,
            "baseline": b,
            "lower": bool(lower),
            "intervals_apart": bool(apart),
        },
        "summary": f"Archivist (arm A) accepted {h['accepted']} values and {h['wrong']} were "
        f"wrong: {_pct(h['rate'])}{_span(h['ci95'])}. The baseline accepted {b['accepted']} "
        f"values and {b['wrong']} were wrong: {_pct(b['rate'])}{_span(b['ci95'])}. "
        f"Archivist's rate is {'lower' if lower else 'not lower'} and the intervals "
        f"{'do not overlap' if apart else 'overlap'}.",
    }

    caught, wrong = head["errors_caught"], head["n_wrong"]
    out["H2"] = {
        "claim": "The headline catches at least 85% of wrong values.",
        "met": bool(wrong and Fraction(caught, wrong) >= H2_CATCH),
        "numbers": {
            "caught": caught,
            "wrong": wrong,
            "rate": head["catch_rate"],
            "ci95": head["catch_rate_ci95"],
            "threshold": float(H2_CATCH),
        },
        "summary": f"Of {wrong} wrong values, Archivist (arm A) sent {caught} to review: "
        f"{_pct(head['catch_rate'])}{_span(head['catch_rate_ci95'])}. The threshold is "
        f"{_pct(float(H2_CATCH), 0)} or more.",
    }

    review, fields = head["n_review"], head["n_fields"]
    out["H3"] = {
        "claim": "The headline sends at most 20% of fields to review.",
        "met": bool(fields and Fraction(review, fields) <= H3_REVIEW),
        "numbers": {
            "review": review,
            "fields": fields,
            "rate": head["review_rate"],
            "ci95": head["review_rate_ci95"],
            "threshold": float(H3_REVIEW),
        },
        "summary": f"Archivist (arm A) sent {review} of {fields} fields to review: "
        f"{_pct(head['review_rate'])}{_span(head['review_rate_ci95'])}. The threshold is "
        f"{_pct(float(H3_REVIEW), 0)} or less.",
    }

    o = errors(open_)
    out["H4"] = {
        "claim": "The all-open-weights arm's error rate among accepted fields is below 1%.",
        "met": bool(o["accepted"] and Fraction(o["wrong"], o["accepted"]) < H4_ERROR),
        "numbers": {**o, "threshold": float(H4_ERROR)},
        "summary": f"Arm B accepted {o['accepted']} values and {o['wrong']} were wrong: "
        f"{_pct(o['rate'])}{_span(o['ci95'])}. The threshold is below "
        f"{_pct(float(H4_ERROR), 0)}, judged on the rate itself.",
    }

    found, planted = head["source_errors_found"], head["n_source_errors"]
    out["H5"] = {
        "claim": "The headline flags at least 90% of the planted source errors.",
        "met": bool(planted and Fraction(found, planted) >= H5_SOURCE),
        "numbers": {
            "found": found,
            "planted": planted,
            "rate": head["source_error_recall"],
            "threshold": float(H5_SOURCE),
        },
        "summary": f"Archivist (arm A) sent a field of {found} of {planted} planted source "
        f"errors to review: {_pct(head['source_error_recall'])}. The threshold is "
        f"{_pct(float(H5_SOURCE), 0)} or more.",
    }
    return out


def build_report(
    configs: Mapping[str, Mapping] = CONFIGS,
    runs_dir: Path = RUNS_DIR,
    data_root: Path = DATA_ROOT,
    split: str = SPLIT,
    manifest_sha256: str | None = MANIFEST_SHA256,
) -> dict:
    """Score every configuration and judge the hypotheses; stops if the manifest has changed."""
    manifest = hashlib.sha256((data_root / split / "manifest.json").read_bytes()).hexdigest()
    if manifest_sha256 is not None and manifest != manifest_sha256:
        raise SystemExit(
            f"data/{split}/manifest.json is {manifest}, not the pre-registered {manifest_sha256}"
        )
    gt_dir = data_root / split / "gt"
    rows = {k: score_configuration(k, spec, runs_dir, gt_dir) for k, spec in configs.items()}
    return {
        "what": "Pre-registered test-set evaluation (P16): four configurations, each run once.",
        "preregistration": str(PREREGISTRATION),
        "split": split,
        "manifest_sha256": manifest,
        "n_pages": rows[BASELINE]["cost"]["pages"],
        "n_fields": rows[BASELINE]["stats"]["n_fields"],
        "policy": POLICY,
        "bootstrap": BOOTSTRAP,
        "configurations": rows,
        "hypotheses": _hypotheses(rows),
        "notes": NOTES,
    }


# --- Markdown -------------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _with_ci(value: float | None, interval: Sequence[float] | None) -> str:
    if interval is None:
        return _pct(value)
    return f"{_pct(value)} [{_pct(interval[0])}, {_pct(interval[1])}]"


def _deviations(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("## Deviations", 1)[1].strip() if "## Deviations" in text else "—"


def _errors_table(rows: Mapping[str, dict]) -> str:
    header = [
        "Configuration",
        "Values accepted",
        "Wrong among accepted",
        "Error rate among accepted [95% interval]",
        "Wrong values in all",
        "Caught (sent to review)",
        "Catch rate [95% interval]",
        "False alarms (correct values sent to review)",
    ]
    body = []
    for r in rows.values():
        s = r["stats"]
        body.append(
            [
                r["label"],
                str(s["n_accepted"]),
                str(s["errors_missed"]),
                _with_ci(s["error_rate_accepted"], s["error_rate_accepted_ci95"]),
                str(s["n_wrong"]),
                str(s["errors_caught"]),
                _with_ci(s["catch_rate"], s["catch_rate_ci95"]),
                f"{s['false_alarms']} of {s['n_correct']}",
            ]
        )
    return _table(header, body)


def _alone_table(rows: Mapping[str, dict]) -> str:
    header = [
        "Configuration",
        "Values accepted",
        "Wrong among accepted",
        "Error rate among accepted [95% interval]",
    ]
    body = []
    for key, r in rows.items():
        if key == BASELINE:
            continue
        a = r["extraction_alone"]
        rate = _with_ci(a["error_rate_accepted"], a["error_rate_accepted_ci95"])
        body.append([r["label"], str(a["n_accepted"]), str(a["errors_missed"]), rate])
    return _table(header, body)


def _review_table(rows: Mapping[str, dict]) -> str:
    severities = sorted({sev for r in rows.values() for sev in r["by_severity"]})
    header = ["Configuration", "All fields [95% interval]", *[f"Severity {v}" for v in severities]]
    body = []
    for r in rows.values():
        s = r["stats"]
        cells = []
        for sev in severities:
            g = r["by_severity"][sev]
            cells.append(f"{_pct(g['review_rate'])} ({g['n_review']} of {g['n_fields']})")
        body.append([r["label"], _with_ci(s["review_rate"], s["review_rate_ci95"]), *cells])
    return _table(header, body)


def _other_table(rows: Mapping[str, dict]) -> str:
    header = [
        "Configuration",
        "Proposals right",
        "Source errors found",
        "Classification accuracy",
        "Citation accuracy",
        "Cost per page",
    ]
    body = []
    for r in rows.values():
        s, c = r["stats"], r["classification"]
        proposals = "—"
        if s["n_proposed"]:
            right, made = s["proposed_equals_printed"], s["n_proposed"]
            proposals = _count(right, made, s["proposal_accuracy"])
        body.append(
            [
                r["label"],
                proposals,
                _count(s["source_errors_found"], s["n_source_errors"], s["source_error_recall"]),
                _count(c["right"], c["pages"], c["accuracy"]),
                _pct(r["citation_accuracy"]),
                f"${r['cost']['per_page_usd']:.4f}",
            ]
        )
    return _table(header, body)


def _runs_table(rows: Mapping[str, dict]) -> str:
    header = [
        "Configuration",
        "Extraction run",
        "Pages extracted",
        "Pages failed",
        "Sessions",
        "Verification run",
        "Re-reads failed",
        "Second looks failed",
        "Cost of all calls",
    ]
    body = []
    for r in rows.values():
        e, v = r["runs"]["extraction"], r["runs"].get("verification")
        calls = v["calls"] if v else None
        body.append(
            [
                r["label"],
                e["run"],
                f"{e['counts']['extracted']} of {e['counts']['pages']}",
                str(len(e["failed_pages"])),
                str(e["sessions"]),
                v["run"] if v else "—",
                f"{calls['rereads_failed']} of {calls['rereads']}" if calls else "—",
                f"{calls['second_looks_failed']} of {calls['second_looks']}" if calls else "—",
                f"${r['cost']['total_usd']:.2f}",
            ]
        )
    return _table(header, body)


def render(report: Mapping, deviations: str) -> str:
    rows, hypotheses = report["configurations"], report["hypotheses"]
    coverage = [
        [r["label"], ", ".join(f"({_pct(c)}, {_pct(k)})" for c, k in r["stats"]["risk_coverage"])]
        for r in rows.values()
    ]
    parts = [
        "# Test results — Archivist",
        f"The pre-registered test run, scored once. The test set is {report['n_pages']} synthetic "
        f"pages with {report['n_fields']} fields. Every configuration ran on it once, with the "
        "code and settings frozen in PREREGISTRATION.md, and nothing below was used to change "
        "the system.",
        "Each value is *accepted* (the system lets it into the database without a person "
        "looking), *sent to review* (a person checks it first) or *abstained* (the extractor "
        "returned no value). Only values sent to review count toward the review rate and H3; "
        "abstained values are counted separately (n_abstained in results/test_report.json). "
        "The fields of a page that failed to extract are none of these. A *wrong value* is a "
        "value that is not the "
        "printed one, or a blank where something is printed. An *error among accepted fields* is "
        "a wrong value that got in. Intervals are 95% intervals from 2,000 resamples of whole "
        "pages.",
        "## The five hypotheses",
        _table(
            ["", "Claim", "Result"],
            [
                [h, d["claim"], "**MET**" if d["met"] else "**NOT MET**"]
                for h, d in hypotheses.items()
            ],
        ),
        *[
            f"**{h}: {'met' if d['met'] else 'not met'}.** {d['summary']}"
            for h, d in hypotheses.items()
        ],
        "## Errors that reach the database",
        _errors_table(rows),
    ]
    unanswered = {r["label"]: r["stats"]["wrong_unanswered"] for r in rows.values()}
    unanswered = {label: n for label, n in unanswered.items() if n}
    if unanswered:
        parts.append(
            "Wrong values that were neither accepted nor sent to review (the fields of a page "
            "that failed to extract): " + ", ".join(f"{k} {n}" for k, n in unanswered.items()) + "."
        )
    parts += [
        "What each arm's extraction would have let in without verification:",
        _alone_table(rows),
        "## How much goes to review",
        _review_table(rows),
        "Severity is how badly the scan is degraded, from 0 (mildest) to 3 (worst).",
        "## Proposals, source errors, classification, citations and cost",
        _other_table(rows),
        "## Risk and coverage",
        "Coverage is the share of fields accepted at a confidence threshold, and risk is the "
        "error rate among them. Each point is one threshold, strictest first.",
        _table(["Configuration", "Points (coverage, error rate)"], coverage),
        "## What happened in the runs",
        _runs_table(rows),
        "A failed re-read sends its field to review, so failures there raise the review rate. A "
        "run with more than one session was resumed. Second looks belong to policy v3, which was "
        "not adopted: they are recorded and paid for but do not change a v2 verdict, and their "
        "cost is in the cost above.",
        "Deviations recorded in PREREGISTRATION.md:\n\n" + deviations,
        "## Reading these numbers",
        "\n".join(f"- {note}" for note in report["notes"]),
    ]
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.parse_args(argv)  # no options: the configurations are pre-registered
    report = build_report()
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    OUT_MD.write_text(render(report, _deviations(PREREGISTRATION)), encoding="utf-8")
    for h, d in report["hypotheses"].items():
        print(f"{h}: {'met' if d['met'] else 'not met'} — {d['summary']}")
    print(f"-> {OUT_JSON}, {OUT_MD}")


if __name__ == "__main__":
    main()
