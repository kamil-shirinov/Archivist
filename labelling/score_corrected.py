"""The corrected-key score beside the official one (PREREGISTRATION_REAL.md, Deviations,
2026-11-02): prepared before the relabel and the dash check, and run only after both.

The corrected key is the first-pass key with one change: a cell whose standing first-pass answer
is blank, and which the dash check (labelling/serve.py, /dashcheck) marks "dash printed", is
answered "-", the printed value typed as printed. A cell marked "nothing printed" or "can't tell"
keeps its blank, and no other answer changes. labels.jsonl is never edited: the key is built in
memory from it and the dash marks.

The scoring rules are unchanged: the key is scored by labelling/score.py's own score(), on the
code tagged run-real-treasury, exactly as the official score was, with only the first-pass
answers it reads replaced. Before that, the same score() is run on the committed key and must
reproduce the official score/score.json's label results to the last digit, or nothing is
written. The official score/ is read, never written, and is reported first.

    1. after the relabel and the dash check: commit and push relabels.jsonl and
       dashes_checked.jsonl (results/real_test/held_out/labels/), on their own;
    2. git worktree add --detach <wt> run-real-treasury && (cd <wt> && uv sync --frozen)
       cd <wt> && PYTHONPATH=<main> .venv/bin/python -m labelling.score_corrected --data <main>
    3. commit results/real_test/held_out/score_corrected/ alone, and push.

It refuses unless: the code is the tag's (score.provenance); every label file, the dash marks and
the official score are committed and pushed and unchanged; labels.jsonl is the file the official
score recorded; labelling/score.py is the scorer the official score recorded; every relabel cell
has an answer, all given before the first dash mark; and every first-pass blank, and no other
cell, has a dash mark. It writes score_corrected/ once. No model is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from archivist.templates import real_test
from labelling import score
from labelling.draw import DRAW_FILE, STRATA
from labelling.serve import DASH_ANSWERS, DASH_MARKS, FILES, answers

SIDE = score.SIDE
OUT = "score_corrected"
OFFICIAL = Path("score/score.json")
DASH = "-"
SAID = {"dash": "dash printed", "nothing": "nothing printed", "cant_tell": "can't tell"}
MEASURES = ("single_read_error", "archivist_error", "catch_rate")


class NotReady(RuntimeError):
    pass


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _same(a: object, b: object) -> bool:
    """Equal once both are written as JSON, as score.json was."""
    return json.loads(json.dumps(a)) == json.loads(json.dumps(b))


# --- The key ------------------------------------------------------------------------------------


def blanks(draw: Mapping, first: Mapping[str, Mapping]) -> list[str]:
    """The drawn cells whose standing first-pass answer is blank, in the draw's order."""
    return [s["cell"] for s in draw["sample"] if first[s["cell"]]["choice"] == "blank"]


def ready(draw: Mapping, first: Mapping, relabels: list[dict], dashes: list[dict]) -> None:
    """Raises NotReady unless the relabel is complete and wholly given before the dash check began,
    and every first-pass blank, and no other cell, has a dash mark."""
    second = {line["cell"] for line in relabels}
    missing = [c for c in draw["relabel"] if c not in second]
    if missing:
        raise NotReady(f"{len(missing)} of {len(draw['relabel'])} relabel cells have no answer")
    if not dashes:
        raise NotReady("the dash check has no mark")
    began = min(line["checked_at"] for line in dashes)
    late = [line for line in relabels if line["labelled_at"] >= began]
    if late:
        raise NotReady(f"{len(late)} relabel answers were given after the dash check began")
    wanted, marked = set(blanks(draw, first)), {line["cell"] for line in dashes}
    if marked - wanted:
        raise NotReady(f"{len(marked - wanted)} dash marks are for cells that are not first-pass blanks")
    if wanted - marked:
        raise NotReady(f"{len(wanted - marked)} of {len(wanted)} first-pass blanks have no dash mark")
    bad = [line for line in dashes if line["mark"] not in DASH_MARKS]
    if bad:
        raise NotReady(f"{len(bad)} dash marks are not one of {DASH_MARKS}")


def corrected_key(first: Mapping[str, Mapping], marks: Mapping[str, Mapping]) -> dict[str, dict]:
    """The first-pass key with every blank the dash check marks "dash printed" answered "-"."""
    key = {}
    for cell, label in first.items():
        if label["choice"] == "blank" and marks.get(cell, {}).get("mark") == "dash":
            key[cell] = {**label, "choice": "value", "value": DASH, "corrected_by": "dash check"}
        else:
            key[cell] = dict(label)
    return key


def changes(draw: Mapping, first: Mapping, key: Mapping, marks: Mapping) -> dict:
    """How many answers the corrected key changes, overall and by stratum, and the marks given."""
    stratum = {s["cell"]: s["stratum"] for s in draw["sample"]}
    changed = [c for c in key if key[c]["choice"] != first[c]["choice"] or key[c]["value"] != first[c]["value"]]
    checked = blanks(draw, first)
    return {
        "labelled_cells": len(first),
        "cells_checked": len(checked),
        "marks": {m: sum(marks[c]["mark"] == m for c in checked) for m in DASH_MARKS},
        "answers_changed": len(changed),
        "answers_changed_by_stratum": {name: sum(stratum[c] == name for c in changed) for name in STRATA},
        "cells_checked_by_stratum": {name: sum(stratum[c] == name for c in checked) for name in STRATA},
    }


# --- Scoring with score.py's own functions ------------------------------------------------------


@contextmanager
def keyed(first_file: Path, key: Mapping[str, Mapping]) -> Iterator[None]:
    """score.score() reading key for the first-pass answers file, and every other file as it is."""
    real = score.answers
    first_file = first_file.resolve()

    def read(path: Path, name: str) -> dict[str, dict]:
        return dict(key) if Path(path).resolve() == first_file else real(path, name)

    with mock.patch.object(score, "answers", read):
        yield


def remembered(function: Callable) -> Callable:
    """The function's first answer, given again: the re-read keys and SAM's detections do not
    depend on the labels, so the two scorings share one computation of each."""
    kept: list = []

    def again(*args, **kwargs):
        if not kept:
            kept.append(function(*args, **kwargs))
        return kept[0]

    return again


def corrected_score(data: Path) -> dict:
    """The official label results reproduced, then scored again on the corrected key."""
    records = data / real_test.OUT_DIR / SIDE
    labels = records / "labels"
    official = json.loads((records / OFFICIAL).read_text(encoding="utf-8"))
    first_file = labels / FILES["first"]
    if hashlib.sha256(first_file.read_bytes()).hexdigest() != official["label_files_sha256"][FILES["first"]]:
        raise NotReady(f"{FILES['first']} is not the file the official score recorded")
    if hashlib.sha256(Path(score.__file__).read_bytes()).hexdigest() != official["provenance"]["scorer_sha256"]:
        raise NotReady("labelling/score.py is not the scorer the official score recorded")

    draw = json.loads((labels / DRAW_FILE).read_text(encoding="utf-8"))
    first = answers(first_file, "cell")
    relabels, dashes = _lines(labels / FILES["relabel"]), _lines(labels / DASH_ANSWERS)
    ready(draw, first, relabels, dashes)
    marks = answers(labels / DASH_ANSWERS, "cell")
    key = corrected_key(first, marks)

    with (
        mock.patch.object(score, "reread_keys", remembered(score.reread_keys)),
        mock.patch.object(score, "detections", remembered(score.detections)),
    ):
        as_scored = score.score(data)
        for part in ("labels", "headline_with_classified_weights"):
            if not _same(as_scored[part], official[part]):
                raise ValueError(f"score.py on the committed key does not reproduce the official {part}")
        with keyed(first_file, key):
            fixed = score.score(data)

    return {
        "official": {
            "labels": official["labels"],
            "headline_with_classified_weights": official["headline_with_classified_weights"],
        },
        "corrected_key": {
            "labels": fixed["labels"],
            "headline_with_classified_weights": fixed["headline_with_classified_weights"],
        },
        "changes": changes(draw, first, key, marks),
        "relabel_agreement": {"first_pass_key": as_scored["relabel"], "corrected_key": fixed["relabel"]},
    }


# --- Committed and pushed -----------------------------------------------------------------------


def committed(data: Path, paths: list[Path], git: Callable[..., subprocess.CompletedProcess] | None = None) -> dict[str, str]:
    """Each file's sha256; refuses one that is missing, not tracked, differs from its commit, or
    whose commit is not on origin/main."""

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(data), *args], capture_output=True, text=True, check=False)

    git = git or run
    hashes = {}
    for path in paths:
        relative = path.relative_to(data).as_posix()
        if not path.exists():
            raise score.NotCommitted(f"{relative} is missing")
        if git("ls-files", "--error-unmatch", relative).returncode != 0:
            raise score.NotCommitted(f"{relative} is not committed")
        if git("diff", "--quiet", "HEAD", "--", relative).returncode != 0:
            raise score.NotCommitted(f"{relative} differs from its commit")
        last = git("log", "-1", "--format=%H", "--", relative).stdout.strip()
        if git("merge-base", "--is-ancestor", last, "origin/main").returncode != 0:
            raise score.NotCommitted(f"{relative} is committed but not pushed")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


# --- The report ---------------------------------------------------------------------------------


def render(record: Mapping) -> str:
    """score.md: the official results first, then the corrected key's, variant by variant."""
    p, c = record["provenance"], record["changes"]
    lines = [
        "# Held-out scoring with the dash-corrected key, beside the official score",
        "",
        "PREREGISTRATION_REAL.md, Deviations, 2026-11-02. **The official score stands as scored** "
        "(`results/real_test/held_out/score/`); it is shown first. The corrected key differs from the "
        "first-pass key only where the dash check found a dash printed in a cell first labelled blank; "
        "it is scored by `labelling/score.py`'s own functions under unchanged rules.",
        "",
        f"Code: `{p['tag']}` ({p['commit'][:7]}), checked frozen; rules (labelling/score.py) sha256 "
        f"`{p['rules_sha256'][:12]}`, this scorer `{p['scorer_sha256'][:12]}`. Intervals: 95%, page "
        "bootstrap within strata; Wilson for the relabel.",
        "",
        "Files (sha256): " + ", ".join(f"`{n}` {h}" for n, h in record["files_sha256"].items()),
        "",
        "## The key",
        "",
        f"First-pass blanks checked: {c['cells_checked']} ({c['cells_checked_by_stratum']}). Marks: "
        + ", ".join(f"{SAID[m]} {n}" for m, n in c["marks"].items())
        + f". Answers changed: {c['answers_changed']} of {c['labelled_cells']} "
        f"({c['answers_changed_by_stratum']}), each from blank to \"{DASH}\".",
        "",
        "Relabel agreement: " + "; ".join(
            f"{name.replace('_', ' ')}: " + (
                f"{a['agree']} of {a['of']} ({a['wilson'][0]:.1%}–{a['wilson'][1]:.1%})"
                if a["status"] == "done" else json.dumps(a)
            )
            for name, a in record["relabel_agreement"].items()
        ) + ". The plan's figure is the first-pass key's.",
        "",
        "## Labelled cells",
        "",
        "| Variant | Key | Single read error | Archivist error (accepted) | Catch rate | R1 |",
        "|---|---|---|---|---|---|",
    ]
    for name, official in record["official"]["labels"].items():
        for title, result in (("**official**", official), ("corrected", record["corrected_key"]["labels"][name])):
            o = result["overall"]
            lines.append(
                f"| {name} | {title} | {score._pct(o['single_read_error'])} | {score._pct(o['archivist_error'])} | "
                f"{score._pct(o['catch_rate'])} | {'met' if result['r1']['met'] else 'not met'} |"
            )
    lines += ["", "By stratum:", "", "| Variant | Stratum | Key | Single read error | Archivist error | Catch rate |"]
    lines.append("|---|---|---|---|---|---|")
    for name, official in record["official"]["labels"].items():
        for stratum in official["by_stratum"]:
            for title, result in (("**official**", official), ("corrected", record["corrected_key"]["labels"][name])):
                o = result["by_stratum"][stratum]
                lines.append(
                    f"| {name} | {stratum} | {title} | {score._pct(o['single_read_error'])} | "
                    f"{score._pct(o['archivist_error'])} | {score._pct(o['catch_rate'])} |"
                )
    lines += ["", "Labels and outcomes (variant: official; corrected):", ""]
    for name, official in record["official"]["labels"].items():
        corrected = record["corrected_key"]["labels"][name]
        lines.append(f"- {name}: {official['by_outcome']}; {corrected['by_outcome']}")
    compared = "; ".join(
        f"{name}: single read {score._pct(h['single_read_error'])}, Archivist {score._pct(h['archivist_error'])}, "
        f"R1 {'met' if h['r1_met'] else 'not met'}"
        for name, h in record["corrected_key"]["headline_with_classified_weights"].items()
    )
    lines += ["", f"Corrected key with classified-page weights instead: {compared}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--data", type=Path, required=True, help="the main checkout, with the records")
    args = parser.parse_args(argv)
    data = args.data.resolve()
    origin = score.provenance(data)
    origin = {
        **{k: v for k, v in origin.items() if k != "scorer_sha256"},
        "rules_sha256": origin["scorer_sha256"],
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    records = data / real_test.OUT_DIR / SIDE
    labels = records / "labels"
    files = committed(
        data,
        [labels / DRAW_FILE, labels / FILES["first"], labels / FILES["relabel"], labels / DASH_ANSWERS, records / OFFICIAL],
    )
    out = records / OUT
    if out.exists():
        parser.error(f"{out} exists: the corrected key is scored once")
    record = {"provenance": origin, "files_sha256": files, **corrected_score(data)}
    out.mkdir(parents=True)
    (out / "score.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "score.md").write_text(render(record), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
