"""What a read leaves behind: a run record the exporter understands, and the bundle built from it.

A finished read is written as the pair of folders the pipeline writes (an extraction run, a
verification run on it) under results/scratch/live/, which git ignores, and exported by the very
exporter the committed runs go through (export.bundle.build). The page is then opened in the normal
document view and review queue like any other run's. Nothing is written under results/runs/ or
data/bundles/, so no committed run or bundle can change, and the ledger is the only committed file
a live read touches (D18).

A bundle is named for how it was made: live-<time>-<page> for a read that asked the models, and
replay-<time>-<page> for one played from the cache, so a page opened later says which it was.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from archivist.doctypes import DocType, recorded
from archivist.export import bundle as export
from archivist.live.events import Recorder
from archivist.live.pages import issue_label
from archivist.live.reader import Outcome
from archivist.pipeline import occlusion, reread, verify

LIVE_ROOT = Path("results/scratch/live")


def stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")


def run_id_for(mode: str, page_id: str, when: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", page_id).strip("-").lower()
    return f"{mode}-{when}-{slug}"


def _iso(now: datetime) -> str:
    return now.isoformat(timespec="seconds")


def write_run(
    root: Path,
    run_id: str,
    outcome: Outcome,
    *,
    config: Mapping[str, object],
    doc_types: Mapping[str, DocType],
    rec: Recorder,
    started: datetime,
    finished: datetime,
) -> Path:
    """The extraction run and the verification run of one read, as run.json, predictions.jsonl and
    verdicts.jsonl; returns the verification run's folder. Costs are what this read spent."""
    page, extraction = outcome.page, outcome.extraction
    if page.kind == "treasury":
        images = page.path.parent.parent  # data/real/pages: the exporter takes its split, "real"
    else:
        images = root / "scans" / run_id / page.split / "images"
        images.mkdir(parents=True, exist_ok=True)
        shutil.copy2(page.path, images / page.path.name)
    read_cost = sum(rec.cost_by_step.get(s, 0.0) for s in ("recognise", "read", "snap"))
    check_cost = rec.totals["cost_usd"] - read_cost
    enabled = recorded(doc_types)

    read_dir, verify_dir = root / "runs" / f"{run_id}-read", root / "runs" / run_id
    read_dir.mkdir(parents=True, exist_ok=True)
    verify_dir.mkdir(parents=True, exist_ok=True)
    (read_dir / "predictions.jsonl").write_text(extraction.model_dump_json() + "\n", "utf-8")
    (read_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": read_dir.name,
                "images": images.as_posix(),
                "config": dict(config),
                "doc_types": enabled,
                "citations": outcome.citations,
                "counts": {
                    "pages": 1,
                    "extracted": 1,
                    "failed": 0,
                    "by_doc_type": {extraction.doc_type: 1},
                },
                "failed_pages": {},
                "cost_usd": round(read_cost, 6),
                "started_at": _iso(started),
                "finished_at": _iso(finished),
            },
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    (verify_dir / verify.VERDICTS_FILE).write_text(
        "".join(v.model_dump_json() + "\n" for v in outcome.verdicts), "utf-8"
    )
    calls = dict(outcome.calls)
    cost_full = calls.pop("cost_full_usd", 0.0)
    (verify_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source_run": read_dir.name,
                "images": images.as_posix(),
                "config": dict(config),
                "doc_types": enabled,
                "citations": outcome.citations,
                "policy": {
                    "version": "v2",
                    "recorded": list(verify.POLICIES),
                    "v2": "D26: every field read twice, checks on both chains",
                    "v3": "D29: v2, with a second look before an alarm (not taken here)",
                    "money_fields": sorted(verify.money_fields(doc_types)),
                    "confidence": verify.CONFIDENCE,
                    "occlusion_prompts": list(occlusion.PROMPTS),
                    "occlusion_cover": occlusion.COVER,
                    "reread_padding": {"vertical": reread.PAD_Y, "horizontal": reread.PAD_X},
                    "second_look_padding": {
                        "vertical": reread.SECOND_PAD_Y,
                        "horizontal": reread.SECOND_PAD_X,
                    },
                },
                "counts": {"pages": 1, **verify._counts(outcome.verdicts)},
                "calls": calls,
                "cost_usd": round(check_cost, 6),
                "cost_full_usd": cost_full,
                "started_at": _iso(started),
                "finished_at": _iso(finished),
            },
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    return verify_dir


def export_run(root: Path, run_dir: Path, *, mode: str, outcome: Outcome, cost: float) -> str:
    """The bundle of a written read, in root/bundles/<run>/ with its page image beside it, and its
    entry in root/bundles/index.json; returns the run id."""
    pages_dir, bundles_dir = root / "pages", root / "bundles"
    built = export.build(run_dir, pages_dir, bundles_dir)
    page = outcome.page
    label = issue_label(page.ref) if page.kind == "treasury" else page.page_id
    how = (
        "Read live: the models were asked and the spend ledger records the calls."
        if mode == "live"
        else "Played from the cache: nothing was asked and nothing was spent."
    )
    built.run = built.run.model_copy(
        update={
            "collection": f"{'Live read' if mode == 'live' else 'Replay'}: {label}",
            "description": f"{how} Cost of this read ${cost:.4f}. A development page, kept "
            "outside the committed runs.",
        }
    )
    out_dir = bundles_dir / built.run.run_id
    export.write(built, out_dir)
    export.update_index(built, bundles_dir)
    return built.run.run_id


def has_values(outcome: Outcome) -> bool:
    """Whether the read recorded a value at all: the exporter leaves a page with none out."""
    return outcome.extraction is not None and any(
        v.value is not None for v in outcome.extraction.values
    )
