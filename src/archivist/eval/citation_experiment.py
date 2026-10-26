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
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from archivist.eval import run_eval
from archivist.models import describe_config, load_roles
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


def run_ids(split: str) -> dict[str, str]:
    return {
        "S0": f"baseline-{split}-v1",
        "S1": f"baseline-{split}-s1",
        "S1+ink": f"baseline-{split}-s1-ink",
    }


def apply_ink(source: Path, target: Path, images: Path) -> dict:
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
        "citations": "S1+ink",
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


def choose(variants: Mapping[str, Mapping]) -> str:
    """The decision rule; variants maps each of CITATION_STRATEGIES to variant()'s output."""
    floor = variants["S0"]["field_accuracy"] - MAX_FIELD_ACCURACY_DROP
    eligible = [
        name
        for name in CITATION_STRATEGIES  # simplest first, so max() keeps the simpler on a tie
        if variants[name]["field_accuracy"] >= floor
        and variants[name]["citation_accuracy"]["all"] is not None
    ]
    return max(eligible, key=lambda name: variants[name]["citation_accuracy"]["all"])


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
    return "\n".join(lines + [f"winner: {result['winner']}"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--split", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.split == "test":
        raise SystemExit("the test set is never used to choose anything (D7)")

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
        workers=args.workers,
        citation_strategy="S1",
    )
    if record["counts"]["failed"]:
        print(f"S1: {record['counts']['failed']} pages failed and are scored as omitted")
    apply_ink(runs / ids["S1"], runs / ids["S1+ink"], images)

    variants = {}
    for name in CITATION_STRATEGIES:
        run_dir = runs / ids[name]
        metrics = run_eval.evaluate(run_dir, gt)
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        variants[name] = variant(ids[name], metrics)
    result = {"split": args.split, "rule": RULE, "winner": choose(variants), "variants": variants}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(table(result))


if __name__ == "__main__":
    main()
