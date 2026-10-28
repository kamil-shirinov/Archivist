"""Which citation strategy to keep: three variants on the dev split, one rule fixed in advance.

    python -m archivist.eval.citation_experiment --split dev

S0 is the baseline run baseline-<split>-v1, whose boxes come from the extraction call. S1 runs
the grounding prompt as baseline-<split>-s1, resuming if it is part done. S1+ink corrects S1's
boxes from the page images with pipeline/citations.py, with no model call, and is written as
baseline-<split>-s1-ink. Each is scored by metrics.py into its run's metrics.json.

Decision rule, fixed before running: choose the variant with the highest citation accuracy whose
field accuracy is no more than 0.5 points below S0's; on a tie, prefer the simpler one (S0, then
S1, then S1+ink). Writes results/citation_experiment.json with the winner and every variant's
citation accuracy by doc type, field accuracy and error rate of accepted values.

    python -m archivist.eval.citation_experiment --split val --validate

Validation of S0+ink, the correction built on dev and frozen, on a split it has never seen. S0
runs as baseline-<split>-s0, resuming if it is part done; S0+ink corrects its boxes offline as
baseline-<split>-s0-ink. Both are scored for citation accuracy by doc type and for the wrong-field
rate: the share of citations whose centre lands inside a different field's box. Rule, fixed
before running: adopt S0+ink if it raises citation accuracy by at least 20 points and its
wrong-field rate is no higher than S0's; otherwise keep S0. Writes
results/citation_validation.json with what was adopted, both variants and the hash of the
correction it ran.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from archivist.eval import run_eval
from archivist.eval.metrics import _centre_inside
from archivist.doctypes import from_config
from archivist.models import describe_config, load_roles
from archivist.models.registry import CONFIG_PATH
from archivist.pipeline import citations, extract
from archivist.pipeline.extract import (
    CITATION_STRATEGIES,
    IMAGE_SUFFIXES,
    PageExtraction,
    load_predictions,
)

OUT = Path("results/citation_experiment.json")
MAX_FIELD_ACCURACY_DROP = 0.005  # 0.5 points
RULE = (
    "Choose the variant with the highest citation accuracy whose field accuracy is no more than "
    "0.5 points below S0's; on a tie, prefer the simpler one (S0, then S1, then S1+ink)."
)
VALIDATION_OUT = Path("results/citation_validation.json")
MIN_CITATION_GAIN = 0.20  # 20 points
VALIDATION_RULE = (
    "Adopt S0+ink as the default if it raises citation accuracy by at least 20 points and its "
    "wrong-field rate is no higher than S0's; otherwise keep S0."
)


def run_ids(split: str) -> dict[str, str]:
    return {
        "S0": f"baseline-{split}-v1",
        "S1": f"baseline-{split}-s1",
        "S1+ink": f"baseline-{split}-s1-ink",
    }


def validation_run_ids(split: str) -> dict[str, str]:
    return {"S0": f"baseline-{split}-s0", "S0+ink": f"baseline-{split}-s0-ink"}


def apply_ink(source: Path, target: Path, images: Path, strategy: str = "S1+ink") -> dict:
    """target holds source's predictions with every page's boxes corrected from its image."""
    scans = {p.stem: p for p in images.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES}
    pages: list[PageExtraction] = []
    fits = {}
    for page in load_predictions(source / "predictions.jsonl"):
        fix = citations.correct(scans[page.page_id].read_bytes(), page.values)
        pages.append(page.model_copy(update={"values": fix.values}))
        fits[page.page_id] = {
            "alpha": fix.alpha,
            "beta": fix.beta,
            "gamma": fix.gamma,
            "inked": fix.inked,
            "matched": fix.matched,
        }
    target.mkdir(parents=True, exist_ok=True)
    (target / "predictions.jsonl").write_text(
        "".join(page.model_dump_json() + "\n" for page in pages), encoding="utf-8"
    )
    source_run = json.loads((source / "run.json").read_text())
    record = {
        "run_id": target.name,
        "derived_from": source.name,
        "citations": strategy,
        "config": source_run.get("config"),
        "cost_usd": 0.0,
        "pages": dict(sorted(fits.items())),
    }
    (target / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def variant(run_id: str, metrics: Mapping) -> dict:
    return {
        "run_id": run_id,
        "citation_accuracy": {
            "all": metrics["overall"]["citation_accuracy"],
            **{k: v["citation_accuracy"] for k, v in metrics["by_doc_type"].items()},
        },
        "field_accuracy": metrics["overall"]["field_accuracy"],
        "error_rate": metrics["overall"]["error_rate_accepted"],
    }


def wrong_field_rate(run_dir: Path, gt_dir: Path) -> dict[str, float | None]:
    """Overall and by doc type: of the citations of ground-truth fields, the share whose centre
    lands inside a different field's box on the same page."""
    predictions = {p.page_id: p for p in load_predictions(run_dir / "predictions.jsonl")}
    counts: dict[str, list[int]] = {"all": [0, 0]}  # [wrong, cited]
    for page in run_eval.load_gt(gt_dir):
        boxes = {field.field_id: field.bbox for field in page.fields}
        prediction = predictions.get(page.page_id)
        for value in prediction.values if prediction else []:
            if value.citation is None or value.field_id not in boxes:
                continue
            wrong = value.citation.page_id == page.page_id and any(
                _centre_inside(value.citation.bbox, box)
                for field_id, box in boxes.items()
                if field_id != value.field_id
            )
            for key in ("all", page.doc_type):
                tally = counts.setdefault(key, [0, 0])
                tally[0] += wrong
                tally[1] += 1
    return {key: wrong / cited if cited else None for key, (wrong, cited) in counts.items()}


def choose(variants: Mapping[str, Mapping]) -> str:
    """The decision rule; variants maps strategies to variant()'s output and must include S0."""
    floor = variants["S0"]["field_accuracy"] - MAX_FIELD_ACCURACY_DROP
    eligible = [
        name
        for name in CITATION_STRATEGIES  # simplest first, so max() keeps the simpler on a tie
        if name in variants
        and variants[name]["field_accuracy"] >= floor
        and variants[name]["citation_accuracy"]["all"] is not None
    ]
    return max(eligible, key=lambda name: variants[name]["citation_accuracy"]["all"])


def adopt(variants: Mapping[str, Mapping]) -> str:
    """The validation rule, over variant()'s output with a wrong_field_rate for S0 and S0+ink."""
    base, ink = variants["S0"], variants["S0+ink"]
    before, after = base["citation_accuracy"]["all"], ink["citation_accuracy"]["all"]
    if before is None or after is None:
        return "S0"
    gain = round(after - before, 9)  # so that exactly 20 points counts despite float error
    no_worse = ink["wrong_field_rate"]["all"] <= base["wrong_field_rate"]["all"]
    return "S0+ink" if gain >= MIN_CITATION_GAIN and no_worse else "S0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(split: str, workers: int) -> dict:
    """S0 and the frozen S0+ink on a split the correction was not built on; see the docstring."""
    ids = validation_run_ids(split)
    images = run_eval.DATA_ROOT / split / "images"
    gt = run_eval.DATA_ROOT / split / "gt"
    runs = run_eval.RUNS_DIR
    roles = load_roles()
    guard = roles[extract.ROLE].inner.guard
    record = extract.run(
        images,
        runs / ids["S0"],
        roles,
        guard=guard,
        config=describe_config(),
        doc_types=from_config(CONFIG_PATH),
        workers=workers,
        citation_strategy="S0",
    )
    if record["counts"]["failed"]:
        print(f"S0: {record['counts']['failed']} pages failed and are scored as omitted")
    apply_ink(runs / ids["S0"], runs / ids["S0+ink"], images, strategy="S0+ink")

    variants = {}
    for name, run_id in ids.items():
        run_dir = runs / run_id
        metrics = run_eval.evaluate(run_dir, gt)
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        variants[name] = {
            **variant(run_id, metrics),
            "wrong_field_rate": wrong_field_rate(run_dir, gt),
        }
    return {
        "split": split,
        "rule": VALIDATION_RULE,
        "correction_sha256": _sha256(Path(citations.__file__)),
        "adopted": adopt(variants),
        "variants": variants,
    }


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def table(result: Mapping) -> str:
    header = (
        f"{'':<8} {'citation all':>12} {'ledger':>8} {'memo':>8} {'field acc':>10} {'error':>8}"
    )
    lines = [header, "-" * len(header)]
    for name, v in result["variants"].items():
        c = v["citation_accuracy"]
        lines.append(
            f"{name:<8} {_percent(c['all']):>12} {_percent(c.get('ledger')):>8} "
            f"{_percent(c.get('memo')):>8} {_percent(v['field_accuracy']):>10} "
            f"{_percent(v['error_rate']):>8}"
        )
    if "winner" in result:
        return "\n".join(lines + [f"winner: {result['winner']}"])
    for name, v in result["variants"].items():
        w = v["wrong_field_rate"]
        lines.append(
            f"{name:<8} wrong-field {_percent(w['all'])} (ledger {_percent(w.get('ledger'))}, "
            f"memo {_percent(w.get('memo'))})"
        )
    return "\n".join(lines + [f"adopted: {result['adopted']}"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--split", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--validate", action="store_true", help="validate S0+ink (see above)")
    args = parser.parse_args(argv)
    if args.split == "test":
        raise SystemExit("the test set is never used to choose anything (D7)")
    if args.validate:
        if args.split == "dev":
            raise SystemExit("S0+ink was built on dev; validate it on a split it has not seen")
        result = validate(args.split, args.workers)
        VALIDATION_OUT.write_text(json.dumps(result, indent=2) + "\n")
        print(table(result))
        return

    ids = run_ids(args.split)
    images = run_eval.DATA_ROOT / args.split / "images"
    gt = run_eval.DATA_ROOT / args.split / "gt"
    runs = run_eval.RUNS_DIR
    if not (runs / ids["S0"] / "predictions.jsonl").exists():
        raise SystemExit(f"S0 is the run {ids['S0']}, which is missing")

    roles = load_roles()
    guard = roles[extract.ROLE].inner.guard
    record = extract.run(
        images,
        runs / ids["S1"],
        roles,
        guard=guard,
        config=describe_config(),
        doc_types=from_config(CONFIG_PATH),
        workers=args.workers,
        citation_strategy="S1",
    )
    if record["counts"]["failed"]:
        print(f"S1: {record['counts']['failed']} pages failed and are scored as omitted")
    apply_ink(runs / ids["S1"], runs / ids["S1+ink"], images)

    variants = {}
    for name, run_id in ids.items():
        run_dir = runs / run_id
        metrics = run_eval.evaluate(run_dir, gt)
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        variants[name] = variant(run_id, metrics)
    result = {"split": args.split, "rule": RULE, "winner": choose(variants), "variants": variants}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(table(result))


if __name__ == "__main__":
    main()
