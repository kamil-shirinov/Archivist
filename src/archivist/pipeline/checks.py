"""The documents' own checksums over a run's extracted values; no model calls.

    python -m archivist.pipeline.checks --run baseline-dev-v1

Reads results/runs/<run_id>/predictions.jsonl, runs every registered document type's checks over
the whole batch, so cross-document checks see every page, and writes the flags to
results/runs/<run_id>/flags.jsonl, one Flag per line. Checks see only extracted values (D24).
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from archivist.doctypes import REGISTRY, is_unresolvable
from archivist.pipeline.extract import RUNS_DIR, PageExtraction, load_predictions
from archivist.schema import Flag

FLAGS_FILE = "flags.jsonl"


def run_checks(pages: Sequence[PageExtraction]) -> list[Flag]:
    """Every registered type's checks over the batch, in registry order."""
    batch = sorted(pages, key=lambda p: p.page_id)
    return [flag for doc_type in REGISTRY.values() for flag in doc_type.checks(batch)]


def load_flags(path: Path) -> list[Flag]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Flag.model_validate_json(line) for line in lines if line.strip()]


def run(run_dir: Path) -> list[Flag]:
    predictions = run_dir / "predictions.jsonl"
    if not predictions.exists():
        raise FileNotFoundError(f"{predictions} is missing: run archivist.pipeline.extract first")
    flags = run_checks(load_predictions(predictions))
    text = "".join(flag.model_dump_json() + "\n" for flag in flags)
    (run_dir / FLAGS_FILE).write_text(text, encoding="utf-8")
    return flags


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run", required=True)
    args = parser.parse_args(argv)

    run_dir = RUNS_DIR / args.run
    flags = run(run_dir)
    unresolvable = sum(is_unresolvable(f) for f in flags)
    by_check = Counter(f.check for f in flags)
    print(
        f"{len(flags)} flags on {len({f.field_id for f in flags})} fields "
        f"({unresolvable} unresolvable) -> {run_dir / FLAGS_FILE}"
    )
    for check, n in sorted(by_check.items()):
        print(f"  {check:<14} {n}")


if __name__ == "__main__":
    main()
