"""Dataset builder: one world rendered, degraded and written out as a split.

Images and answers are kept apart, so a pipeline can be pointed at images/ alone:

    data/<split>/images/<page_id>.jpg   the scan, as the scanner would have saved it
    data/<split>/gt/<page_id>.json      PageGT of the degraded page
    data/<split>/gt/world.json       the clean World every page came from
    data/<split>/manifest.json       parameters, provenance, counts and a sha256 per file

Every random choice derives from the seed: the world, each page's render and degradation, and
the shuffled cycle that spreads severities 0–3 evenly over the pages.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import random
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from PIL import Image

from archivist.schema import PageGT
from archivist.synth import degrade, render
from archivist.synth.world import World, generate_world

REPO_ROOT = Path(__file__).resolve().parents[3]
SPLIT_NAME = re.compile(r"[A-Za-z0-9_-]+")
SPLIT_PARTS = ("images", "gt", "manifest.json")  # all a split is made of; nothing else is touched
DOC_TYPES: tuple[Literal["ledger", "memo"], ...] = ("ledger", "memo")


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _severities(seed: int, n_pages: int) -> list[int]:
    """0, 1, 2, 3, 0, 1, … shuffled: each level appears n // 4 or n // 4 + 1 times."""
    cycle = [i % len(degrade.LEVELS) for i in range(n_pages)]
    random.Random(f"{seed}:severity").shuffle(cycle)
    return cycle


def _clean_pages(world: World, seed: int) -> Iterator[tuple[Image.Image, PageGT]]:
    """Every card, then every memo, rendered as render_world would, one page at a time."""
    banks = {card.doc_id: card.bank for card in world.cards}
    renders = [(card.doc_id, functools.partial(render.render_card, card)) for card in world.cards]
    renders += [
        (
            memo.doc_id,
            functools.partial(render.render_memo, memo, bank=banks[memo.ledger_ref.rsplit(":", 1)[0]]),
        )
        for memo in world.memos
    ]
    for doc_id, make in renders:
        image, gt = make(random.Random(f"{seed}:{doc_id}"))
        on_page = {field.field_id for field in gt.fields}
        errors = [e for e in world.source_errors if on_page.intersection(e.field_ids)]
        yield image, gt.model_copy(update={"source_errors": errors})


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def build_split(
    split: str,
    seed: int,
    n_accounts: int,
    cards_per_account: int,
    memo_rate: float,
    source_error_rate: float,
    out_root: Path = Path("data"),
    overwrite: bool = False,
) -> Path:
    """Build out_root/<split> and return its path.

    The split is assembled in a scratch folder beside it and moved into place only once it is
    complete, so a failed build leaves nothing half-written. An existing split is refused unless
    overwrite is set, and then only its images/, gt/ and manifest.json are replaced.
    """
    if not SPLIT_NAME.fullmatch(split):
        raise ValueError(f"split must be letters, digits, '-' or '_', got {split!r}")
    split_dir = out_root / split
    existing = [name for name in SPLIT_PARTS if (split_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"{split_dir} already holds {', '.join(existing)}; pass overwrite=True to replace it"
        )

    # Read before anything is written, so the split's own files never count as changes.
    commit = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))

    world = generate_world(
        seed,
        n_accounts,
        cards_per_account,
        memo_rate=memo_rate,
        source_error_rate=source_error_rate,
    )
    severities = _severities(seed, len(world.cards) + len(world.memos))
    by_doc_type: Counter[str] = Counter()
    by_severity: Counter[int] = Counter()

    out_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_root, prefix=f".{split}-") as scratch:
        stage = Path(scratch)
        images_dir, gt_dir = stage / "images", stage / "gt"
        images_dir.mkdir()
        gt_dir.mkdir()

        for severity, (image, clean) in zip(severities, _clean_pages(world, seed), strict=True):
            rng = random.Random(f"{seed}:{clean.page_id}:sev{severity}")
            scan, degraded = degrade.scan_page(image, clean, severity, rng)
            page = degraded.model_copy(update={"image_path": f"images/{clean.page_id}.jpg"})
            (images_dir / f"{page.page_id}.jpg").write_bytes(scan)
            (gt_dir / f"{page.page_id}.json").write_text(page.model_dump_json(indent=2) + "\n")
            by_doc_type[page.doc_type] += 1
            by_severity[severity] += 1
        (gt_dir / "world.json").write_text(world.model_dump_json(indent=2) + "\n")

        manifest = {
            "split": split,
            "seed": seed,
            "params": {
                "n_accounts": n_accounts,
                "cards_per_account": cards_per_account,
                "memo_rate": memo_rate,
                "source_error_rate": source_error_rate,
            },
            "generator_commit": commit,
            "dirty": dirty,
            "counts": {
                "by_doc_type": {kind: by_doc_type[kind] for kind in DOC_TYPES},
                "by_severity": {str(s): by_severity[s] for s in range(len(degrade.LEVELS))},
            },
            "files": {
                path.relative_to(stage).as_posix(): _sha256(path)
                for path in sorted(stage.rglob("*"))
                if path.is_file()
            },
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

        for name in existing:
            _remove(split_dir / name)
        split_dir.mkdir(exist_ok=True)
        for name in SPLIT_PARTS:
            (stage / name).replace(split_dir / name)
    return split_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.synth.build",
        description="Build a dataset split: degraded pages, ground truth and a hashed manifest.",
    )
    parser.add_argument("--split", required=True, help="folder name under --out-root, e.g. dev")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--accounts", type=int, required=True)
    parser.add_argument("--cards-per-account", type=int, required=True)
    parser.add_argument("--memo-rate", type=float, required=True)
    parser.add_argument("--error-rate", type=float, required=True, help="source error rate")
    parser.add_argument("--out-root", type=Path, default=Path("data"))
    parser.add_argument("--overwrite", action="store_true", help="replace an existing split")
    args = parser.parse_args(argv)
    split_dir = build_split(
        args.split,
        args.seed,
        args.accounts,
        args.cards_per_account,
        args.memo_rate,
        args.error_rate,
        args.out_root,
        args.overwrite,
    )
    n_pages = len(list((split_dir / "images").iterdir()))
    print(f"wrote {n_pages} pages to {split_dir}")


if __name__ == "__main__":
    main()
