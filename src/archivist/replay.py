"""Proof that a change to the code changed nothing a committed run produced (P19).

    python -m archivist.replay [--workers 8]

Run from the repository root. In order:

1. The cache must be present, and the dev and val images are rebuilt from their manifests' seeds
   into results/scratch/replay/splits/; every image must match its manifest's sha256, as must the
   images the runs read (data/<split>/images/, put there from the rebuild when missing, and the
   committed test images).
2. Every backend's spend cap is set to zero (budget.BACKEND_CAPS), so any cache miss raises
   BudgetExceeded and aborts the replay, and the spend ledger's line count is recorded.
3. Every current run is replayed into results/scratch/replay/<run>, through its own config and
   the document types it enables: the extraction runs (REPLAYED_EXTRACTIONS) with their recorded
   --citations, the verification runs (REPLAYED_VERIFICATIONS) from their committed source runs
   with their recorded policy. The types registered beyond those (an approved template) play no
   part, so approving one changes nothing here.
4. A replayed verdicts.jsonl must be byte-identical to the committed one, a replayed
   predictions.jsonl identical once its lines are sorted (pages finish in any order), and run.json
   identical apart from the times and the cost (VOLATILE). What those may differ in is checked
   instead: the replay spent nothing, and every call that answered came from the cache. A run
   from before P21b recorded no document types; it is compared as having enabled LEGACY, the
   built-in ledger card and payment memo.
5. The scoring commands (SCORING) are re-run in place, and git must show no change under results/
   apart from the ledger, whose line count must be unchanged; the exporter's checks must pass for
   every committed bundle and database.

Writes results/scratch/replay/replay.json with what was compared; exits non-zero on any problem.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from archivist.doctypes import from_config, recorded_by
from archivist.eval import compare_arms, compare_extractors, test_report
from archivist.export import bundle, database
from archivist.models import describe_config, load_roles
from archivist.models.budget import BACKEND_CAPS, LEDGER_PATH
from archivist.models.cache import CACHE_DIR
from archivist.pipeline import extract, reread, verify
from archivist.pipeline.extract import RUNS_DIR
from archivist.synth.build import build_split

DATA_ROOT = Path("data")
SCRATCH = Path("results/scratch/replay")
REBUILT_SPLITS = ("dev", "val")
CHECKED_SPLITS = ("dev", "val", "test")
CAPS = tuple(variable for variable, _ in BACKEND_CAPS.values())
# Run id -> the config it was run with.
REPLAYED_EXTRACTIONS = {
    "test-baseline": "config/models.toml",
    "test-baseline-open": "config/models_open.toml",
}
REPLAYED_VERIFICATIONS = {
    "arm-a-dev": "config/arms/a.toml",
    "arm-a-val": "config/arms/a.toml",
    "arm-b-dev": "config/arms/b.toml",
    "arm-b-val": "config/arms/b.toml",
    "arm-c-dev": "config/arms/c.toml",
    "arm-c-val": "config/arms/c.toml",
    "test-archivist-A": "config/arms/a.toml",
    "test-archivist-B": "config/arms/b.toml",
    "test-archivist-C": "config/arms/c.toml",
}
# run.json keys a replay may change: the times and the cost, and an extraction's sessions, which
# hold only those and how many pages each session extracted.
VOLATILE = frozenset({"started_at", "finished_at", "cost_usd", "cost_full_usd", "sessions"})
VOLATILE_CALLS = frozenset({"rereads_from_cache", "second_looks_from_cache"})
SCORING: dict[str, Callable[[list[str]], None]] = {
    "archivist.eval.compare_arms": compare_arms.main,
    "archivist.eval.compare_extractors": compare_extractors.main,
    "archivist.eval.test_report": test_report.main,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_cache() -> list[str]:
    if not CACHE_DIR.is_dir() or not any(CACHE_DIR.iterdir()):
        return [f"{CACHE_DIR}/ is missing or empty: nothing can be replayed without paid calls"]
    return []


def check_images(split_dir: Path, manifest: dict) -> list[str]:
    """Problems with split_dir/images against the manifest's hashes: every image, nothing else."""
    expected = {n: h for n, h in manifest["files"].items() if n.startswith("images/")}
    images = split_dir / "images"
    present = {f"images/{p.name}" for p in images.iterdir()} if images.is_dir() else set()
    problems = [f"{split_dir / n} is missing" for n in sorted(set(expected) - present)]
    problems += [f"{split_dir / n} is not in the manifest" for n in sorted(present - set(expected))]
    problems += [
        f"{split_dir / n} does not match its manifest's sha256"
        for n in sorted(set(expected) & present)
        if _sha256(split_dir / n) != expected[n]
    ]
    return problems


def rebuild_images(split: str) -> list[str]:
    """Rebuild the split from its manifest's seed and check it; install its images if missing."""
    manifest = _read_json(DATA_ROOT / split / "manifest.json")
    params = manifest["params"]
    with contextlib.redirect_stdout(io.StringIO()):
        built = build_split(
            split,
            manifest["seed"],
            params["n_accounts"],
            params["cards_per_account"],
            params["memo_rate"],
            params["source_error_rate"],
            out_root=SCRATCH / "splits",
            overwrite=True,
        )
    problems = check_images(built, manifest)
    if problems:
        return problems
    images = DATA_ROOT / split / "images"
    images.mkdir(exist_ok=True)
    for path in sorted((built / "images").iterdir()):
        if not (images / path.name).exists():
            shutil.copy2(path, images / path.name)
    return check_images(DATA_ROOT / split, manifest)


def _stable(record: dict) -> dict:
    out = {k: v for k, v in copy.deepcopy(record).items() if k not in VOLATILE}
    if isinstance(out.get("calls"), dict):
        out["calls"] = {k: v for k, v in out["calls"].items() if k not in VOLATILE_CALLS}
    return out


def compare_records(run_id: str, committed: dict, replayed: dict) -> list[str]:
    """run.json against the committed one, apart from VOLATILE; and the replay spent nothing."""
    a, b = _stable({**committed, "doc_types": recorded_by(committed)}), _stable(replayed)
    problems = [
        f"{run_id}: run.json differs in {key!r}"
        for key in sorted(set(a) | set(b))
        if a.get(key) != b.get(key)
    ]
    if replayed["cost_usd"] != 0:
        problems.append(f"{run_id}: the replay spent ${replayed['cost_usd']:.4f}")
    calls = replayed.get("calls", {})
    for what in ("rereads", "second_looks"):
        if what in calls and calls[f"{what}_from_cache"] != calls[what] - calls[f"{what}_failed"]:
            problems.append(f"{run_id}: not every answered {what} came from the cache")
    sessions = replayed.get("sessions")
    if sessions is not None and [s["aborted"] for s in sessions] != [None]:
        problems.append(f"{run_id}: the replay did not finish in one session")
    return problems


def replay_extraction(run_id: str, config: str, workers: int) -> dict:
    committed_dir, out = RUNS_DIR / run_id, SCRATCH / run_id
    committed = _read_json(committed_dir / "run.json")
    problems = _config_problems(run_id, config, committed)
    shutil.rmtree(out, ignore_errors=True)
    roles = load_roles(Path(config))
    with contextlib.redirect_stdout(io.StringIO()):
        replayed = extract.run(
            Path(committed["images"]),
            out,
            roles,
            guard=roles[extract.ROLE].inner.guard,
            config=describe_config(Path(config)),
            doc_types=from_config(Path(config)),
            workers=workers,
            citation_strategy=committed["citations"],
        )
    name = "predictions.jsonl"
    before, after = _lines(committed_dir / name), _lines(out / name)
    if sorted(before) != sorted(after):
        problems.append(f"{run_id}: {name} differs from the committed one, sorted")
    problems += compare_records(run_id, committed, replayed)
    return {"kind": "extraction", "config": config, "pages": len(after), "problems": problems}


def replay_verification(run_id: str, config: str, workers: int) -> dict:
    committed_dir, out = RUNS_DIR / run_id, SCRATCH / run_id
    committed = _read_json(committed_dir / "run.json")
    problems = _config_problems(run_id, config, committed)
    shutil.rmtree(out, ignore_errors=True)
    roles = load_roles(Path(config))
    replayed = verify.run(
        RUNS_DIR / committed["source_run"],
        out,
        roles,
        guard=roles[reread.ROLE].inner.guard,
        config=describe_config(Path(config)),
        doc_types=from_config(Path(config)),
        workers=workers,
        policy=committed["policy"]["version"],
    )
    name = verify.VERDICTS_FILE
    if (committed_dir / name).read_bytes() != (out / name).read_bytes():
        problems.append(f"{run_id}: {name} is not byte-identical to the committed one")
    problems += compare_records(run_id, committed, replayed)
    return {
        "kind": "verification",
        "config": config,
        "source_run": committed["source_run"],
        "policy": committed["policy"]["version"],
        "verdicts": len(_lines(out / name)),
        "problems": problems,
    }


def _config_problems(run_id: str, config: str, committed: dict) -> list[str]:
    if describe_config(Path(config)) != committed["config"]:
        return [f"{run_id}: {config} is not the config the run recorded"]
    return []


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=False, capture_output=True, text=True)


def check_results() -> list[str]:
    """Anything git sees changed or added under results/, apart from the ledger."""
    paths = ["--", "results/", f":(exclude){LEDGER_PATH.as_posix()}"]
    diff = _git("diff", "--exit-code", "--stat", *paths)
    problems = [] if diff.returncode == 0 else [f"git diff results/:\n{diff.stdout.rstrip()}"]
    status = _git("status", "--porcelain", "--untracked-files=all", *paths).stdout.splitlines()
    problems += [f"untracked under results/: {line[3:]}" for line in status if line[:2] == "??"]
    return problems


def check_exports() -> tuple[list[str], list[str]]:
    """Every committed bundle and database against a fresh export of its run."""
    runs = sorted(p.name for p in bundle.BUNDLES_DIR.iterdir() if p.is_dir())
    problems = []
    for run_id in runs:
        built = bundle.build(bundle.run_dir(run_id))
        problems += bundle.check(built, bundle.BUNDLES_DIR / run_id)
        if (database.EXPORTS_DIR / run_id).exists():  # a development run on real pages has none
            with tempfile.TemporaryDirectory() as fresh:
                problems += database.check(built, database.EXPORTS_DIR / run_id, Path(fresh))
    return runs, problems


def ledger_lines() -> int:
    return len(_lines(LEDGER_PATH))


def replay(workers: int) -> dict:
    report: dict = {"problems": check_cache()}
    if report["problems"]:
        return report
    for split in REBUILT_SPLITS:
        print(f"rebuilding {split} from its seed", flush=True)
        report["problems"] += rebuild_images(split)
    for split in CHECKED_SPLITS:
        manifest = _read_json(DATA_ROOT / split / "manifest.json")
        report["problems"] += check_images(DATA_ROOT / split, manifest)
    if report["problems"]:
        return report

    for variable in CAPS:
        os.environ[variable] = "0"
    report["ledger_lines_before"] = ledger_lines()
    report["runs"] = {}
    jobs = [(r, c, replay_extraction) for r, c in REPLAYED_EXTRACTIONS.items()]
    jobs += [(r, c, replay_verification) for r, c in REPLAYED_VERIFICATIONS.items()]
    for run_id, config, replay_one in jobs:
        print(f"replaying {run_id}", flush=True)
        result = replay_one(run_id, config, workers)
        report["runs"][run_id] = result
        report["problems"] += result["problems"]

    for name, main in SCORING.items():
        print(f"scoring: {name}", flush=True)
        with contextlib.redirect_stdout(io.StringIO()):
            main([])
    report["scoring"] = list(SCORING)
    report["problems"] += check_results()
    report["ledger_lines_after"] = ledger_lines()
    if report["ledger_lines_after"] != report["ledger_lines_before"]:
        report["problems"].append(
            f"the spend ledger grew from {report['ledger_lines_before']} to "
            f"{report['ledger_lines_after']} lines"
        )
    print("checking the exports", flush=True)
    report["exports"], problems = check_exports()
    report["problems"] += problems
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    report = replay(args.workers)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "replay.json").write_text(json.dumps(report, indent=2) + "\n")
    for run_id, result in report.get("runs", {}).items():
        size = result.get("verdicts", result.get("pages"))
        unit = "verdicts" if "verdicts" in result else "pages"
        mark = "differs" if result["problems"] else "identical"
        print(f"  {run_id:<20} {result['kind']:<12} {size:>5} {unit:<8} {mark}")
    if "ledger_lines_before" in report:
        print(
            f"spend ledger: {report['ledger_lines_before']} lines before, "
            f"{report.get('ledger_lines_after')} after; exports checked: {report.get('exports')}"
        )
    if report["problems"]:
        raise SystemExit("replay FAILED:\n" + "\n".join(f"- {p}" for p in report["problems"]))
    print(f"replay passed: nothing a committed run produced has changed -> {SCRATCH}/replay.json")


if __name__ == "__main__":
    main()
