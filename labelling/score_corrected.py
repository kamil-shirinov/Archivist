"""The corrected-key score beside the official ones (PREREGISTRATION_REAL.md and
PREREGISTRATION_OPENW.md, Deviations, 2026-11-02): prepared before the relabel and the dash
check, and run only after both, once for each configuration.

The corrected key is the first-pass key with one change: a cell whose standing first-pass answer
is blank, and which the dash check (labelling/serve.py, /dashcheck) marks "dash printed", is
answered "-", the printed value typed as printed. A cell marked "nothing printed" or "can't tell"
keeps its blank, and no other answer changes. labels.jsonl is never edited: the key is built in
memory from it and the dash marks. Both configurations are scored against the same key.

The scoring rules are unchanged. Each configuration is scored by its own official scorer's
functions, on its own tag, exactly as its official score was, with only the first-pass answers
the scorer reads replaced. Before that, the same scorer is run on the committed key and must
reproduce its official score.json to the last digit, or nothing is written. The official score/
folders are read, never written, and are reported first.

- version_1: labelling/score.py's score(), on the code tagged run-real-treasury. That tag has no
  labelling/, so labelling/ (score.py and this file) comes from the main checkout, as for the
  official score.
- open_weights: labelling/score_openw.py's score_openw(), on the code tagged run-real-openw. That
  tag freezes labelling/ and refuses untracked files there, so score_openw.py and score.py are the
  tag's own and this file is run by its path from the main checkout. In the corrected run, version
  1's side-by-side figures are worked out on the corrected key too, so score_openw's check that
  they equal version 1's official score is passed over there; the committed-key run has made it.

The order:

    1. after the relabel and the dash check: commit and push relabels.jsonl and
       dashes_checked.jsonl (results/real_test/held_out/labels/), on their own;
    2. git worktree add --detach <wt1> run-real-treasury && (cd <wt1> && uv sync --frozen)
       cd <wt1> && PYTHONPATH=<main> .venv/bin/python -m labelling.score_corrected version_1 --data <main>
       -> results/real_test/held_out/score_corrected/
    3. git worktree add --detach <wt2> run-real-openw && (cd <wt2> && uv sync --frozen)
       cd <wt2> && PYTHONPATH=. .venv/bin/python <main>/labelling/score_corrected.py open_weights --data <main>
       -> results/real_openw/held_out/score_corrected/
    4. commit the two score_corrected/ folders alone, and push.

Each run refuses unless: the code is its tag's (its scorer's provenance()); the labels, the dash
marks, its official score and its records are committed, pushed and unchanged; labels.jsonl is
the file its official score recorded, and its scorer files are the ones it recorded; every relabel
cell has an answer, all given before the first dash mark; and every first-pass blank, and no other
cell, has a dash mark. Each writes its score_corrected/ once. No model is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest import mock

from archivist.templates import real_test
from labelling import score
from labelling.draw import DRAW_FILE, STRATA
from labelling.serve import FILES, answers

SIDE = score.SIDE
OUT = "score_corrected"
OFFICIAL = Path("score/score.json")
# labelling.serve's names for the marks; the open-weights tag's serve.py predates them
DASH_ANSWERS = "dashes_checked.jsonl"
DASH_MARKS = ("dash", "nothing", "cant_tell")
DASH = "-"
SAID = {"dash": "dash printed", "nothing": "nothing printed", "cant_tell": "can't tell"}
RUNS = ("version_1", "open_weights")
# what the open-weights scorer's committed-key run must give exactly as its score.json has it
OPEN_PARTS = ("o1", "open_weights", "version_1", "open_weights_with_classified_weights", "cells_found")
OPEN_MEASURES = (
    ("archivist_error", "Wrong among accepted"),
    ("single_read_error", "Single read error"),
    ("catch_rate", "Wrong values caught"),
    ("sent_to_person", "Sent to a person"),
)


class NotReady(RuntimeError):
    pass


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _same(a: object, b: object) -> bool:
    """Equal once both are written as JSON, as score.json was."""
    return json.loads(json.dumps(a)) == json.loads(json.dumps(b))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def labels_in(data: Path) -> dict:
    """The draw, the first-pass key, the relabel answers and the dash marks, once ready() passes,
    and the corrected key built from them."""
    labels = data / real_test.OUT_DIR / SIDE / "labels"
    draw = json.loads((labels / DRAW_FILE).read_text(encoding="utf-8"))
    first = answers(labels / FILES["first"], "cell")
    relabels, dashes = _lines(labels / FILES["relabel"]), _lines(labels / DASH_ANSWERS)
    ready(draw, first, relabels, dashes)
    marks = answers(labels / DASH_ANSWERS, "cell")
    key = corrected_key(first, marks)
    return {
        "first_file": labels / FILES["first"],
        "draw": draw,
        "first": first,
        "second": answers(labels / FILES["relabel"], "cell"),
        "key": key,
        "changes": changes(draw, first, key, marks),
    }


# --- Scoring with each scorer's own functions ---------------------------------------------------


@contextmanager
def keyed(module: ModuleType, first_file: Path, key: Mapping[str, Mapping]) -> Iterator[None]:
    """module's own answers() reading key for the first-pass answers file, and every other file
    as it is."""
    real = module.answers
    first_file = first_file.resolve()

    def read(path: Path, name: str) -> dict[str, dict]:
        return dict(key) if Path(path).resolve() == first_file else real(path, name)

    with mock.patch.object(module, "answers", read):
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


def agreement(given: Mapping, canonical_of: Callable[[str, str], str]) -> dict:
    """The relabel's agreement, by score.relabel_agreement, with the first-pass key (the plan's
    figure) and with the corrected key."""
    draw, second = given["draw"], given["second"]
    return {
        "first_pass_key": score.relabel_agreement(draw, given["first"], second, canonical_of),
        "corrected_key": score.relabel_agreement(draw, given["key"], second, canonical_of),
    }


def version_1(data: Path) -> dict:
    """Version 1's official label results reproduced by score.score(), then scored on the
    corrected key."""
    records = data / real_test.OUT_DIR / SIDE
    official = json.loads((records / OFFICIAL).read_text(encoding="utf-8"))
    given = labels_in(data)
    if _sha256(given["first_file"]) != official["label_files_sha256"][FILES["first"]]:
        raise NotReady(f"{FILES['first']} is not the file the official score recorded")
    if _sha256(score.__file__) != official["provenance"]["scorer_sha256"]:
        raise NotReady("labelling/score.py is not the scorer the official score recorded")

    with (
        mock.patch.object(score, "reread_keys", remembered(score.reread_keys)),
        mock.patch.object(score, "detections", remembered(score.detections)),
    ):
        as_scored = score.score(data)
        for part in ("labels", "headline_with_classified_weights"):
            if not _same(as_scored[part], official[part]):
                raise ValueError(f"score.py on the committed key does not reproduce the official {part}")
        with keyed(score, given["first_file"], given["key"]):
            fixed = score.score(data)

    canonical = {f: t.canonical for f, t in real_test._types(real_test.CONFIG).items() if f in real_test.FAMILIES}
    return {
        "official": {part: official[part] for part in ("labels", "headline_with_classified_weights")},
        "corrected_key": {part: fixed[part] for part in ("labels", "headline_with_classified_weights")},
        "changes": given["changes"],
        "relabel_agreement": agreement(given, lambda cell, text: canonical[score.parts(cell)[0]](cell, text)),
    }


def open_weights(data: Path) -> dict:
    """The open-weights official score reproduced by score_openw.score_openw(), then scored on the
    corrected key; on the open-weights tag, with its own labelling/."""
    from archivist.templates import real_openw
    from labelling import score_openw

    records = data / real_openw.OUT_DIR / SIDE
    official = json.loads((records / OFFICIAL).read_text(encoding="utf-8"))
    given = labels_in(data)
    if _sha256(given["first_file"]) != official["files_sha256"][FILES["first"]]:
        raise NotReady(f"{FILES['first']} is not the file the official score recorded")
    if _sha256(score_openw.__file__) != official["provenance"]["scorer_sha256"]:
        raise NotReady("labelling/score_openw.py is not the scorer the official score recorded")
    if _sha256(score.__file__) != official["provenance"]["rules_sha256"]:
        raise NotReady("labelling/score.py is not the rules the official score recorded")

    with mock.patch.object(score, "reread_keys", remembered(score.reread_keys)):
        as_scored = score_openw.score_openw(data)
        for part in OPEN_PARTS:
            if not _same(as_scored[part], official[part]):
                raise ValueError(f"score_openw.py on the committed key does not reproduce the official {part}")
        # version 1's figures here are on the corrected key too, so they no longer equal its
        # official score: the committed-key run above has checked them
        with (
            keyed(score_openw, given["first_file"], given["key"]),
            mock.patch.object(score_openw, "same_as_scored", lambda mine, scored: None),
        ):
            fixed = score_openw.score_openw(data)

    canonical = {f: t.canonical for f, t in real_test._types(real_openw.CONFIG).items() if f in real_test.FAMILIES}
    return {
        "official": {part: official[part] for part in OPEN_PARTS},
        "corrected_key": {part: fixed[part] for part in OPEN_PARTS},
        "changes": given["changes"],
        "relabel_agreement": agreement(given, lambda cell, text: canonical[score.parts(cell)[0]](cell, text)),
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
        hashes[relative] = _sha256(path)
    return hashes


# --- The reports --------------------------------------------------------------------------------


def _key_lines(record: Mapping) -> list[str]:
    """What the key changed and the relabel's agreement, as both reports give them."""
    c = record["changes"]
    agreed = "; ".join(
        f"{name.replace('_', ' ')}: "
        + (
            f"{a['agree']} of {a['of']} ({a['wilson'][0]:.1%}–{a['wilson'][1]:.1%})"
            if a["status"] == "done"
            else json.dumps(a)
        )
        for name, a in record["relabel_agreement"].items()
    )
    return [
        "## The key",
        "",
        f"First-pass blanks checked: {c['cells_checked']} ({c['cells_checked_by_stratum']}). Marks: "
        + ", ".join(f"{SAID[m]} {n}" for m, n in c["marks"].items())
        + f". Answers changed: {c['answers_changed']} of {c['labelled_cells']} "
        f"({c['answers_changed_by_stratum']}), each from blank to \"{DASH}\".",
        "",
        f"Relabel agreement: {agreed}. The plan's figure is the first-pass key's.",
        "",
    ]


def _header(title: str, record: Mapping, official: str, rules: str) -> list[str]:
    p = record["provenance"]
    return [
        f"# {title}",
        "",
        "PREREGISTRATION_REAL.md and PREREGISTRATION_OPENW.md, Deviations, 2026-11-02. **The official "
        f"score stands as scored** (`{official}`); it is shown first. The corrected key differs from the "
        "first-pass key only where the dash check found a dash printed in a cell first labelled blank; "
        f"it is scored by {rules}'s own functions under unchanged rules.",
        "",
        f"Code: `{p['tag']}` ({p['commit'][:7]}), checked frozen; scorer files (sha256): "
        + ", ".join(f"{n} `{h[:12]}`" for n, h in p["scorers_sha256"].items())
        + ". Intervals: 95%, page bootstrap within strata; Wilson for the relabel.",
        "",
        "Files (sha256): " + ", ".join(f"`{n}` {h}" for n, h in record["files_sha256"].items()),
        "",
    ]


def render(record: Mapping) -> str:
    """Version 1's score.md: the official results first, then the corrected key's, variant by
    variant."""
    lines = _header(
        "Held-out scoring with the dash-corrected key, beside the official score (version 1)",
        record,
        "results/real_test/held_out/score/",
        "`labelling/score.py`",
    )
    lines += _key_lines(record)
    lines += [
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


def render_open(record: Mapping) -> str:
    """Open weights' score.md: O1 and the measures, official first, then on the corrected key,
    with version 1's on the same cells beside them, and the coverage line."""
    lines = _header(
        "Open weights on the real scans with the dash-corrected key, beside the official score",
        record,
        "results/real_openw/held_out/score/",
        "`labelling/score_openw.py` and `labelling/score.py`",
    )
    lines += _key_lines(record)
    for title, part in (("official", record["official"]), ("corrected key", record["corrected_key"])):
        o1 = part["o1"]
        lines.append(
            f"**O1** ({title}; below 1% wrong among accepted, {o1['variant']}): {'met' if o1['met'] else 'not met'}, "
            f"{score._pct({'value': o1['value'], 'ci': o1['ci']})}. In every variant: {o1['in_every_variant']}."
        )
        lines.append("")
    lines += [
        "O1 stands as scored; the corrected key's O1 is reported beside it and replaces nothing.",
        "",
        "| Variant | Measure | Key | Version 1 (Muse Spark 1.3) | Open weights (Muse Spark Open) |",
        "|---|---|---|---|---|",
    ]
    for name in record["official"]["open_weights"]:
        for key, measure in OPEN_MEASURES:
            for title, part in (("**official**", record["official"]), ("corrected", record["corrected_key"])):
                lines.append(
                    f"| {name} | {measure} | {title} | {score._pct(part['version_1'][name]['overall'][key])} | "
                    f"{score._pct(part['open_weights'][name]['overall'][key])} |"
                )
    lines += ["", "By stratum:", "", "| Variant | Stratum | Measure | Key | Version 1 | Open weights |"]
    lines.append("|---|---|---|---|---|---|")
    for name, variant in record["official"]["open_weights"].items():
        for stratum in variant["by_stratum"]:
            for key, measure in OPEN_MEASURES:
                for title, part in (("**official**", record["official"]), ("corrected", record["corrected_key"])):
                    lines.append(
                        f"| {name} | {stratum} | {measure} | {title} | "
                        f"{score._pct(part['version_1'][name]['by_stratum'][stratum][key])} | "
                        f"{score._pct(part['open_weights'][name]['by_stratum'][stratum][key])} |"
                    )
    lines += ["", "Labels and outcomes (variant: open weights official; corrected):", ""]
    for name, official in record["official"]["open_weights"].items():
        lines.append(f"- {name}: {official['by_outcome']}; {record['corrected_key']['open_weights'][name]['by_outcome']}")
    compared = "; ".join(
        f"{name}: wrong among accepted {score._pct(h['archivist_error'])}"
        for name, h in record["corrected_key"]["open_weights_with_classified_weights"].items()
    )
    found = record["corrected_key"]["cells_found"]
    lines += [
        "",
        f"Corrected key, open weights with classified-page weights instead: {compared}.",
        "",
        f"Coverage (the same under both keys): how the 400 drawn cells were found in Open's read "
        f"{found['overall']}; by stratum {found['by_stratum']}. A cell Open's read did not contain gives "
        "no value and is outside the error rates.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("run", choices=RUNS)
    parser.add_argument("--data", type=Path, required=True, help="the main checkout, with the records")
    args = parser.parse_args(argv)
    data = args.data.resolve()
    labels = data / real_test.OUT_DIR / SIDE / "labels"
    label_files = [labels / DRAW_FILE, labels / FILES["first"], labels / FILES["relabel"], labels / DASH_ANSWERS]
    if args.run == "version_1":
        origin = score.provenance(data)
        scorers = {"labelling/score.py": origin.pop("scorer_sha256")}
        records = data / real_test.OUT_DIR / SIDE
        files = committed(data, [*label_files, records / OFFICIAL])
        build, write = version_1, render
    else:
        from archivist.templates import real_openw
        from labelling import score_openw

        if Path(score_openw.__file__).resolve().parents[1] != Path.cwd().resolve():
            parser.error("labelling/ must be the open-weights tag's: run from its checkout with PYTHONPATH=.")
        origin = score_openw.provenance(data)
        scorers = {
            "labelling/score_openw.py": origin.pop("scorer_sha256"),
            "labelling/score.py": origin.pop("rules_sha256"),
        }
        records = data / real_openw.OUT_DIR / SIDE
        files = committed(
            data,
            [
                *label_files,
                data / real_test.OUT_DIR / SIDE / OFFICIAL,
                records / OFFICIAL,
                *(records / name for name in score_openw.RECORDS),
            ],
        )
        build, write = open_weights, render_open
    origin["scorers_sha256"] = {**scorers, "labelling/score_corrected.py": _sha256(__file__)}
    out = records / OUT
    if out.exists():
        parser.error(f"{out} exists: the corrected key is scored once")
    record = {"provenance": origin, "files_sha256": files, **build(data)}
    out.mkdir(parents=True)
    (out / "score.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "score.md").write_text(write(record), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
