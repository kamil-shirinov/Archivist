"""Error analysis of a scored run: what went wrong, and how far off the citations are.

    python -m archivist.eval.analyse --run baseline-dev-v1 --split dev

Reads results/runs/<run>/predictions.jsonl and data/<split>/gt/, scores every field with
metrics.py and writes analysis.json and analysis.md next to the predictions. No model calls.

1. Every field that is not correct, with a category by rule (the first that matches):
       blank   omitted or abstained
       format  the values differ only in spacing, punctuation, letter case, currency signs or
               leading zeros
       digit   a money, date or number field with different digits
       text    a text field with different words
   counted by doc type and by severity.
2. Residuals of the citations of correctly read fields: predicted minus true box centre, in
   pixels and as a fraction of the page, and the fit dy = a*y + b per doc type (y the true centre).
   Proportional to position points at a coordinate-frame issue; roughly constant at the model
   boxing something other than the ink, such as the cell.
3. Citation accuracy under three rules: predicted centre inside the true box (the scorer's rule),
   true centre inside the predicted box, and IoU of at least 0.3.
4. The five pages with the most wrong fields.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from archivist.eval.metrics import (
    DATE_FIELDS,
    DIGIT_FIELDS,
    MONEY_FIELDS,
    FieldOutcome,
    _centre_inside,
    field_kind,
    score_page,
)
from archivist.eval.run_eval import DATA_ROOT, load_gt
from archivist.pipeline.extract import RUNS_DIR, load_predictions
from archivist.schema import BBox, Citation, FieldGT, PageGT

CATEGORIES = ("format", "digit", "text", "blank")
NUMBER_FIELDS = MONEY_FIELDS | DATE_FIELDS | DIGIT_FIELDS | {"sheet_no"}
IOU_THRESHOLD = 0.3
WORST_PAGES = 5
# Conventional cut-offs for reading the pooled fit of dy against y, not tuned on this data:
PROPORTIONAL_R2 = 0.5  # position explains at least half of the drift
CONSTANT_R2 = 0.1  # position explains next to nothing
MIN_PAGE_POINTS = 5  # a per-page line is fitted only through at least this many fields
CRITERIA = {
    "pred_centre_in_true_box": "predicted centre inside the true box (the scorer's rule)",
    "true_centre_in_pred_box": "true centre inside the predicted box",
    "iou_at_least_0_3": f"IoU of at least {IOU_THRESHOLD}",
}
VERDICTS = {
    "proportional": "proportional to position: a coordinate-frame (scale) issue",
    "proportional_per_page": (
        "proportional to position within each page, with a slope that differs from page to "
        "page: a coordinate-frame (scale) issue"
    ),
    "constant": "roughly constant: the model is boxing something other than the ink",
    "mixed": "mixed: position explains part of the drift, not most of it",
    "scatter": "neither: no link to position and an offset small next to the scatter",
    "undetermined": "undetermined: too few points to fit",
}


@dataclass(frozen=True)
class Scored:
    page: PageGT
    field: FieldGT
    outcome: FieldOutcome
    citation: Citation | None


def score_run(pages: Sequence[PageGT], predictions: dict) -> list[Scored]:
    """One entry per ground-truth field; a page with no prediction scores as omitted."""
    scored = []
    for page in pages:
        prediction = predictions.get(page.page_id)
        values = prediction.values if prediction else []
        citations = {v.field_id: v.citation for v in values}
        for field, outcome in zip(page.fields, score_page(page, values), strict=True):
            scored.append(Scored(page, field, outcome, citations.get(field.field_id)))
    return scored


# --- 1. wrong fields ---------------------------------------------------------------------------


def _format_key(text: str) -> str:
    """Text with spacing, punctuation, case, currency signs and leading zeros taken out."""
    text = re.sub(r"\d+", lambda m: m.group().lstrip("0") or "0", text)
    return "".join(c for c in text.casefold() if c.isalnum())


def categorise(o: FieldOutcome) -> str | None:
    """The category of a wrong field; None for a correct one."""
    if o.outcome == "correct":
        return None
    if o.outcome in ("omitted", "abstained"):
        return "blank"
    if _format_key(o.printed) == _format_key(o.predicted or ""):
        return "format"
    return "digit" if field_kind(o.field_id) in NUMBER_FIELDS else "text"


def _digits_only(o: FieldOutcome) -> bool:
    """Whether two values differ in their digits alone, as 'CHQ 889341' and 'CHQ 799341' do."""
    printed, predicted = o.printed, o.predicted or ""
    same_rest = _format_key(re.sub(r"\d", "", printed)) == _format_key(re.sub(r"\d", "", predicted))
    return same_rest and re.sub(r"\D", "", printed) != re.sub(r"\D", "", predicted)


def wrong_rows(scored: Sequence[Scored]) -> list[dict]:
    return [
        {
            "page_id": s.outcome.page_id,
            "severity": s.outcome.severity,
            "doc_type": s.outcome.doc_type,
            "field": s.outcome.field_id,
            "outcome": s.outcome.outcome,
            "printed": s.outcome.printed,
            "predicted": s.outcome.predicted,
            "occluded": s.outcome.occluded,
            "category": categorise(s.outcome),
        }
        for s in scored
        if s.outcome.outcome != "correct"
    ]


def _count(rows: Sequence[dict], n_fields: int) -> dict:
    counts = Counter(r["category"] for r in rows)
    return {"n_fields": n_fields, **{c: counts[c] for c in CATEGORIES}, "wrong": len(rows)}


def category_counts(scored: Sequence[Scored], rows: Sequence[dict]) -> dict:
    def group(key: str, of_field) -> dict:
        keys = sorted({of_field(s) for s in scored})
        return {
            k: _count([r for r in rows if r[key] == k], sum(1 for s in scored if of_field(s) == k))
            for k in keys
        }

    text_errors = [s.outcome for s in scored if categorise(s.outcome) == "text"]
    return {
        "overall": _count(rows, len(scored)),
        "by_doc_type": group("doc_type", lambda s: s.page.doc_type),
        "by_severity": group("severity", lambda s: s.page.severity),
        "text_errors_differing_in_digits_only": sum(_digits_only(o) for o in text_errors),
    }


# --- 2. citation residuals ---------------------------------------------------------------------


def _centre(box: BBox) -> tuple[float, float]:
    return (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _describe(values: np.ndarray) -> dict:
    return {
        "mean": _round(values.mean()),
        "median": _round(np.median(values)),
        "std": _round(values.std(ddof=1)) if len(values) > 1 else None,
        "mean_abs": _round(np.abs(values).mean()),
    }


def _fit(x: np.ndarray, y: np.ndarray) -> dict | None:
    """Least-squares y = a*x + b with its R²; None when x has no spread to fit through."""
    if len(x) < 3 or np.ptp(x) == 0:
        return None
    a, b = np.polyfit(x, y, 1)
    total = float(((y - y.mean()) ** 2).sum())
    r2 = None if total == 0 else 1 - float(((y - (a * x + b)) ** 2).sum()) / total
    return {"a": _round(a), "b": _round(b), "r2": _round(r2)}


def _per_page(page_ids: np.ndarray, x: np.ndarray, y: np.ndarray) -> dict | None:
    fits = []
    for page_id in np.unique(page_ids):
        mask = page_ids == page_id
        fit = _fit(x[mask], y[mask]) if mask.sum() >= MIN_PAGE_POINTS else None
        if fit and fit["r2"] is not None:
            fits.append((fit["a"], fit["r2"], int(mask.sum())))
    if not fits:
        return None
    slopes, r2s, points = (np.array(column) for column in zip(*fits, strict=True))
    return {
        "n_pages": len(fits),
        "points_per_page": [int(points.min()), int(points.max())],
        "slope_median": _round(np.median(slopes)),
        "slope_p10_p90": [_round(v) for v in np.percentile(slopes, [10, 90])],
        "r2_median": _round(np.median(r2s)),
        "share_r2_at_least_half": _round((r2s >= PROPORTIONAL_R2).mean()),
    }


def classify(fit: dict | None, per_page: dict | None, mean_dy: float, std_dy: float | None) -> str:
    """Which pattern the pooled fit of dy on y shows; per_page tells a mixed fit apart."""
    if fit is None or fit["r2"] is None or std_dy is None:
        return "undetermined"
    if fit["r2"] >= PROPORTIONAL_R2:
        return "proportional"
    if fit["r2"] >= CONSTANT_R2:
        if per_page and per_page["r2_median"] >= PROPORTIONAL_R2:
            return "proportional_per_page"
        return "mixed"
    return "constant" if abs(mean_dy) >= std_dy else "scatter"


def _residuals(items: Sequence[Scored]) -> dict:
    on_page = [s for s in items if s.citation.page_id == s.page.page_id]
    true = np.array([_centre(s.field.bbox) for s in on_page]).reshape(-1, 2)
    pred = np.array([_centre(s.citation.bbox) for s in on_page]).reshape(-1, 2)
    width = np.array([s.page.width for s in on_page], dtype=float)
    height = np.array([s.page.height for s in on_page], dtype=float)
    page_ids = np.array([s.page.page_id for s in on_page])
    dx, dy = pred[:, 0] - true[:, 0], pred[:, 1] - true[:, 1]
    result = {
        "n": len(items),
        "n_used": len(on_page),
        "n_blank_cells": sum(1 for s in items if s.field.printed == ""),
        "dx_px": _describe(dx) if len(dx) else None,
        "dy_px": _describe(dy) if len(dy) else None,
        "dx_frac_of_width": _describe(dx / width) if len(dx) else None,
        "dy_frac_of_height": _describe(dy / height) if len(dy) else None,
        "fit_dy": _fit(true[:, 1], dy) if len(dy) else None,
        "fit_dx": _fit(true[:, 0], dx) if len(dx) else None,
        "fit_dy_per_page": _per_page(page_ids, true[:, 1], dy) if len(dy) else None,
    }
    mean, std = (result["dy_px"]["mean"], result["dy_px"]["std"]) if len(dy) else (0.0, None)
    result["pattern"] = classify(result["fit_dy"], result["fit_dy_per_page"], mean, std)
    return result


def _cited_correct(scored: Sequence[Scored]) -> list[Scored]:
    """The population citation accuracy is computed on: correct fields that carry a citation."""
    return [s for s in scored if s.outcome.outcome == "correct" and s.citation is not None]


def citation_residuals(scored: Sequence[Scored]) -> dict:
    cited = _cited_correct(scored)
    return {
        doc_type: _residuals([s for s in cited if s.page.doc_type == doc_type])
        for doc_type in sorted({s.page.doc_type for s in cited})
    }


# --- 3. citation accuracy ----------------------------------------------------------------------


def _holds(s: Scored) -> dict[str, bool]:
    box, truth = s.citation.bbox, s.field.bbox
    on_page = s.citation.page_id == s.page.page_id
    return {
        "pred_centre_in_true_box": bool(s.outcome.citation_ok),
        "true_centre_in_pred_box": on_page and _centre_inside(truth, box),
        "iou_at_least_0_3": on_page and box.iou(truth) >= IOU_THRESHOLD,
    }


def citation_criteria(scored: Sequence[Scored]) -> dict:
    cited = _cited_correct(scored)
    groups = {
        d: [s for s in cited if s.page.doc_type == d]
        for d in sorted({s.page.doc_type for s in cited})
    }
    groups["all"] = cited
    result = {}
    for name, items in groups.items():
        held = [_holds(s) for s in items]
        result[name] = {"n": len(items)}
        for criterion in CRITERIA:
            ok = sum(h[criterion] for h in held)
            result[name][criterion] = {"ok": ok, "rate": _round(ok / len(items)) if items else None}
    return result


# --- 4. worst pages ----------------------------------------------------------------------------


def worst_pages(scored: Sequence[Scored], rows: Sequence[dict]) -> list[dict]:
    pages = {s.page.page_id: s.page for s in scored}
    errors = Counter(r["page_id"] for r in rows)
    ranked = sorted(errors, key=lambda p: (-errors[p], -pages[p].severity, p))[:WORST_PAGES]
    result = []
    for page_id in ranked:
        page_rows = [r for r in rows if r["page_id"] == page_id]
        categories = Counter(r["category"] for r in page_rows)
        result.append(
            {
                "page_id": page_id,
                "doc_type": pages[page_id].doc_type,
                "severity": pages[page_id].severity,
                "wrong": errors[page_id],
                "n_fields": len(pages[page_id].fields),
                "categories": {c: categories[c] for c in CATEGORIES},
                "wrong_and_occluded": sum(r["occluded"] for r in page_rows),
                "artefacts": dict(
                    sorted(Counter(a.kind for a in pages[page_id].artefacts).items())
                ),
            }
        )
    return result


# --- assembling and writing --------------------------------------------------------------------


def analyse(run_dir: Path, gt_dir: Path) -> dict:
    pages = load_gt(gt_dir)
    predictions = {p.page_id: p for p in load_predictions(run_dir / "predictions.jsonl")}
    unknown = sorted(set(predictions) - {page.page_id for page in pages})
    if unknown:
        raise ValueError(f"predictions for pages not in {gt_dir}: {unknown[:5]}")

    scored = score_run(pages, predictions)
    rows = wrong_rows(scored)
    run_path = run_dir / "run.json"
    run = json.loads(run_path.read_text()) if run_path.exists() else {}
    return {
        "run_id": run_dir.name,
        "gt": str(gt_dir),
        "config": run.get("config"),
        "missing_pages": sorted(p.page_id for p in pages if p.page_id not in predictions),
        "n_pages": len(pages),
        "thresholds": {
            "iou": IOU_THRESHOLD,
            "pattern_proportional_r2": PROPORTIONAL_R2,
            "pattern_constant_r2": CONSTANT_R2,
            "min_points_per_page_fit": MIN_PAGE_POINTS,
        },
        "categories": category_counts(scored, rows),
        "rows": rows,
        "citation_residuals": citation_residuals(scored),
        "citation_accuracy": citation_criteria(scored),
        "worst_pages": worst_pages(scored, rows),
    }


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{100 * value:.{digits}f}%"


def _mean_sd(stats: dict | None, scale: float = 1.0, digits: int = 1) -> str:
    if stats is None or stats["std"] is None:
        return "—"
    return f"{stats['mean'] * scale:+.{digits}f} ({stats['std'] * scale:.{digits}f})"


def _quote(value: str | None) -> str:
    if value is None:
        return "`null`"
    return "`" + json.dumps(value, ensure_ascii=False).replace("|", "\\|").replace("`", "'") + "`"


def _short_field(field_id: str, page_id: str) -> str:
    parts = field_id.split(":")
    return ":".join(parts[2:]) if len(parts) > 2 and parts[1] == page_id else field_id


def _table(
    headers: Sequence[str], body: Sequence[Sequence[object]], right: Sequence[int] = ()
) -> list[str]:
    rule = ["---:" if i in right else "---" for i in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(rule) + " |"]
    return lines + ["| " + " | ".join(str(cell) for cell in row) + " |" for row in body]


def _counts_row(label: str, c: dict) -> list[object]:
    return [
        label,
        c["n_fields"],
        *(c[k] for k in CATEGORIES),
        c["wrong"],
        _pct(c["wrong"] / c["n_fields"]),
    ]


def _pattern_note(doc_type: str, r: dict) -> str:
    fit, dy = r["fit_dy"], r["dy_px"]
    if fit is None:
        return f"- **{doc_type}**: {VERDICTS['undetermined']}."
    note = (
        f"- **{doc_type}**: {VERDICTS[r['pattern']]}. Pooled R² {fit['r2']:.2f}, slope "
        f"{fit['a']:+.3f}; Δy mean {dy['mean']:+.1f} px, sd {dy['std']:.1f} px."
    )
    page = r["fit_dy_per_page"]
    if page and page["r2_median"] >= PROPORTIONAL_R2:
        low, high = page["slope_p10_p90"]
        fewest, most = page["points_per_page"]
        note += (
            f" Page by page the lines fit better: median R² {page['r2_median']:.2f} over "
            f"{page['n_pages']} pages, slopes {low:+.3f} to {high:+.3f} at the 10th to 90th "
            "percentile"
            + (", so the drift runs both ways on different pages" if low < 0 < high else "")
            + (f"; each line rests on only {fewest}–{most} points" if most < 10 else "")
            + "."
        )
    return note


def markdown(a: dict) -> str:
    cats, overall = a["categories"], a["categories"]["overall"]
    model = ((a["config"] or {}).get("extractor") or {}).get("model_id")
    lines = [
        f"# Baseline error analysis: {a['run_id']}",
        "",
        f"Run `{a['run_id']}`"
        + (f" (extractor `{model}`)" if model else "")
        + f": {a['n_pages']} pages, {overall['n_fields']} fields, {overall['wrong']} wrong "
        f"({_pct(overall['wrong'] / overall['n_fields'])}). Written by "
        f"`python -m archivist.eval.analyse`; no model calls. The same numbers are in "
        "`analysis.json`.",
        "",
        "## 1. Wrong fields",
        "",
        "A wrong field is anything the scorer does not count correct: misread, hallucinated, "
        "omitted or abstained. Each gets one category, by the first rule that matches:",
        "",
        "- **blank**: omitted or abstained.",
        "- **format**: the values differ only in spacing, punctuation, letter case, currency "
        "signs or leading zeros.",
        "- **digit**: a money, date or number field with different digits.",
        "- **text**: a text field with different words.",
        "",
        *_table(
            ["", "fields", *CATEGORIES, "wrong", "wrong %"],
            [
                *(_counts_row(k, v) for k, v in cats["by_doc_type"].items()),
                *(_counts_row(f"severity {k}", v) for k, v in cats["by_severity"].items()),
                _counts_row("**all**", overall),
            ],
            right=range(1, 8),
        ),
        "",
    ]
    digits_only = cats["text_errors_differing_in_digits_only"]
    if overall["text"]:
        lines += [
            f"Of the {overall['text']} text errors, {digits_only} differ in digits only "
            "(a number inside a text field, such as a cheque number or a sheet and line "
            "reference).",
            "",
        ]
    lines += [
        f"### Every wrong field ({len(a['rows'])})",
        "",
        "Occluded is yes when an artefact covers the field in the ground truth.",
        "",
    ]
    lines += _table(
        [
            "page",
            "sev",
            "doc type",
            "field",
            "outcome",
            "printed",
            "predicted",
            "occluded",
            "category",
        ],
        [
            [
                r["page_id"],
                r["severity"],
                r["doc_type"],
                f"`{_short_field(r['field'], r['page_id'])}`",
                r["outcome"],
                _quote(r["printed"]),
                _quote(r["predicted"]),
                "yes" if r["occluded"] else "no",
                r["category"],
            ]
            for r in a["rows"]
        ],
        right=[1],
    )

    res = a["citation_residuals"]
    lines += [
        "",
        "## 2. Citation residuals",
        "",
        "Population: fields read correctly that carry a citation, the same fields citation "
        "accuracy is computed on"
        + (
            f"; {sum(r['n_blank_cells'] for r in res.values())} of them are cells printed blank. "
            if res
            else ". "
        )
        + "Δ is the predicted box centre minus the true one, so a positive Δy is a box below the "
        "ink. Cells show mean (sd).",
        "",
        *_table(
            [
                "doc type",
                "n",
                "Δx px",
                "Δx % of width",
                "Δy px",
                "Δy % of height",
                "mean abs Δy px",
            ],
            [
                [
                    k,
                    r["n"],
                    _mean_sd(r["dx_px"]),
                    _mean_sd(r["dx_frac_of_width"], 100, 2),
                    _mean_sd(r["dy_px"]),
                    _mean_sd(r["dy_frac_of_height"], 100, 2),
                    "—" if r["dy_px"] is None else f"{r['dy_px']['mean_abs']:.1f}",
                ]
                for k, r in res.items()
            ],
            right=range(1, 7),
        ),
        "",
        "Fit of Δy = a·y + b, with y the true centre in pixels (a is a pure ratio; b is in "
        "pixels). The Δx line fits Δx = a·x + b the same way, for comparison: a uniform "
        "coordinate-frame error would show in both axes.",
        "",
    ]
    fit_rows = []
    for k, r in res.items():
        for label, fit in (("Δy on y", r["fit_dy"]), ("Δx on x", r["fit_dx"])):
            fit_rows.append(
                [
                    k,
                    label,
                    "—" if fit is None else f"{fit['a']:+.4f}",
                    "—" if fit is None else f"{fit['b']:+.1f}",
                    "—" if fit is None or fit["r2"] is None else f"{fit['r2']:.3f}",
                ]
            )
        page = r["fit_dy_per_page"]
        if page:
            low, high = page["slope_p10_p90"]
            fit_rows.append(
                [
                    k,
                    f"Δy on y, per page ({page['n_pages']} pages, {page['points_per_page'][0]}–"
                    f"{page['points_per_page'][1]} points each)",
                    f"median {page['slope_median']:+.4f} ({low:+.3f} to {high:+.3f})",
                    "—",
                    f"median {page['r2_median']:.3f}",
                ]
            )
    lines += _table(["doc type", "fit", "a", "b px", "R²"], fit_rows, right=[2, 3, 4])
    lines += [
        "",
        f"Reading Δy: a pooled R² of at least {PROPORTIONAL_R2} counts as proportional to "
        f"position, below {CONSTANT_R2} as no link to position (roughly constant if the mean "
        "offset is at least as large as the spread, otherwise just scatter), in between as mixed.",
        "",
        *(_pattern_note(k, r) for k, r in res.items()),
        "",
        "## 3. Citation accuracy under three rules",
        "",
        "Over the same fields as section 2, each rule judged on its own; a citation on another "
        "page fails all three.",
        "",
    ]
    acc = a["citation_accuracy"]
    lines += _table(
        ["doc type", "n", *CRITERIA.values()],
        [
            [k, v["n"], *(f"{_pct(v[c]['rate'])} ({v[c]['ok']})" for c in CRITERIA)]
            for k, v in acc.items()
        ],
        right=range(1, 5),
    )
    lines += [
        "",
        f"## 4. The {len(a['worst_pages'])} worst pages",
        "",
        "Ranked by wrong fields, then severity, then page id.",
        "",
    ]
    lines += _table(
        [
            "#",
            "page",
            "doc type",
            "severity",
            "wrong / fields",
            *CATEGORIES,
            "wrong and occluded",
            "artefacts",
        ],
        [
            [
                i,
                p["page_id"],
                p["doc_type"],
                p["severity"],
                f"{p['wrong']} / {p['n_fields']}",
                *(p["categories"][c] for c in CATEGORIES),
                p["wrong_and_occluded"],
                ", ".join(f"{n}× {kind}" for kind, n in p["artefacts"].items()) or "none",
            ]
            for i, p in enumerate(a["worst_pages"], 1)
        ],
        right=[0, 3, 5, 6, 7, 8, 9],
    )
    top = sum(p["wrong"] for p in a["worst_pages"])
    lines += ["", f"Together they hold {top} of the {overall['wrong']} wrong fields."]
    return "\n".join(lines) + "\n"


def summary(a: dict) -> str:
    cats, overall = a["categories"], a["categories"]["overall"]
    rule = "-" * 78
    lines = [
        f"{a['run_id']}: {overall['wrong']} wrong fields of {overall['n_fields']} "
        f"({_pct(overall['wrong'] / overall['n_fields'])}) on {a['n_pages']} pages",
        "",
        f"{'wrong fields':<13}{'fields':>7}"
        + "".join(f"{c:>8}" for c in CATEGORIES)
        + f"{'wrong':>8}",
        rule,
    ]
    rows = list(cats["by_doc_type"].items())
    rows += [(f"severity {k}", v) for k, v in cats["by_severity"].items()] + [("all", overall)]
    for label, c in rows:
        lines.append(
            f"{label:<13}{c['n_fields']:>7}"
            + "".join(f"{c[k]:>8}" for k in CATEGORIES)
            + f"{c['wrong']:>8}"
        )
    lines += [
        "",
        f"{'residuals':<9}{'n':>6}  {'dx px mean (sd)':<17}{'dy px mean (sd)':<17}"
        f"{'dy = a*y + b':<24}{'R2':>5}  pattern",
        rule,
    ]
    for k, r in a["citation_residuals"].items():
        fit = r["fit_dy"] or {"a": float("nan"), "b": float("nan"), "r2": float("nan")}
        lines.append(
            f"{k:<9}{r['n']:>6}  {_mean_sd(r['dx_px']):<17}{_mean_sd(r['dy_px']):<17}"
            f"a={fit['a']:+.4f} b={fit['b']:+6.1f}    {fit['r2']:>5.2f}  {r['pattern']}"
        )
    lines += [
        "",
        f"{'citation':<9}{'n':>6}  {'pred centre in true':>20}{'true centre in pred':>21}"
        f"{'IoU>=0.3':>10}",
        rule,
    ]
    for k, v in a["citation_accuracy"].items():
        lines.append(
            f"{k:<9}{v['n']:>6}  "
            + "".join(
                f"{_pct(v[c]['rate']):>{w}}" for c, w in zip(CRITERIA, (20, 21, 10), strict=True)
            )
        )
    worst = ", ".join(
        f"{p['page_id']} {p['wrong']} (sev {p['severity']})" for p in a["worst_pages"]
    )
    lines += ["", f"worst pages: {worst}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--split", required=True)
    args = parser.parse_args(argv)

    run_dir = RUNS_DIR / args.run
    analysis = analyse(run_dir, DATA_ROOT / args.split / "gt")
    (run_dir / "analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (run_dir / "analysis.md").write_text(markdown(analysis), encoding="utf-8")
    print(summary(analysis))
    print(f"wrote {run_dir / 'analysis.md'} and {run_dir / 'analysis.json'}")


if __name__ == "__main__":
    main()
