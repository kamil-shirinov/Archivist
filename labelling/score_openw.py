"""The open-weights run's scoring (PREREGISTRATION_OPENW.md, P46), once version 1 is scored.

It runs only on the code tagged run-real-openw, from a checkout of the tag with its own
environment, so `import archivist` and labelling/ (this file and score.py, both frozen by the tag)
are the tag's. Before anything is read it checks that archivist was imported from that checkout,
that its HEAD is the tag's commit, that real_openw.frozen() passes there and that the command is
run from it; otherwise it refuses.

    git worktree add --detach <wt> run-real-openw && (cd <wt> && uv sync --frozen)
    cd <wt> && .venv/bin/python -m labelling.score_openw --data <main>

It reads under <main> version 1's draw, labels, records and score (results/real_test/held_out/)
and this run's records (results/real_openw/held_out/), and writes results/real_openw/held_out/
score/ there, once. No model is called.

- The rules are version 1's, by its own functions (labelling/score.py): a read is right when it
  equals the label under the template's comparison; "row not on the page" and "column not on this
  page" are wrong; can't read, and a cell given no value, are outside every error rate and
  counted. The weights are the draw's (score.cell_weights), the intervals score.estimate's, the
  variants score.LAYOUTS and score.REREADS.
- Open's value for a drawn cell is the field of Open's read the runner found for it (cells.json,
  real_openw.match); a cell for which it found none got no value from Open, as one the read
  abstained on, and is counted by why.
- Re-reads asked again: for Open, the drawn cells whose re-read failed in an earlier verification
  pass (verdicts.pass<n>.jsonl), as run or sent to review as failed re-reads; for version 1, the
  cells score.py names (its 3,322 + 32 keys).
- The measures, on the same drawn cells for both: wrong values among accepted
  (archivist_error), the single read's error, the catch rate, and the share sent to a person
  (sent_to_person: status review, or accepted but sent to review under the variant; over every
  drawn cell). Version 1's are worked out again here from its own records and refused unless its
  error rates and catch rate equal its score.json's in every variant and stratum.
- O1, the one pre-set target: Open's wrong values among accepted below 1%, judged on the rate
  itself in the variant kept/as_run (every drawn cell; re-reads as run), and shown in every other.
- The labels, version 1's score and this run's records must be committed and pushed first; each
  file's sha256 is recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import archivist
from archivist.pipeline import extract, verify
from archivist.schema import VerdictRecord
from archivist.templates import real_openw, real_test
from labelling import score
from labelling.draw import DRAW_FILE, STRATA
from labelling.score import BOTH_WAYS, LAYOUTS, REREADS, Scored
from labelling.serve import FILES, answers

SIDE = "held_out"
OUT = "score"
THRESHOLD = 0.01  # O1: below 1% wrong among accepted, as the synthetic H4
PRIMARY = "kept/as_run"
NO_VALUE = "no_value"  # the runner found no field of Open's read for the cell
RECORDS = ("caps.json", "predictions.jsonl", "boxes.jsonl", "cells.json", "verdicts.jsonl", "run.json")
FIRST_SCORE = Path("score/score.json")
COMPARED = ("single_read_error", "archivist_error", "catch_rate")


class NotFrozen(RuntimeError):
    pass


NotCommitted = score.NotCommitted


# --- Provenance ---------------------------------------------------------------------------------


def provenance(data: Path, git: Callable[..., subprocess.CompletedProcess] | None = None) -> dict:
    """Refuses unless archivist was imported from a checkout of the tag, the tag's own frozen()
    passes there and the command runs from it; returns what the score records of it."""
    code = Path(archivist.__file__).resolve().parents[2]

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(code), *args], capture_output=True, text=True, check=False)

    git = git or run
    tag = git("rev-parse", "-q", "--verify", f"{real_openw.TAG}^{{commit}}").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if not tag or head != tag:
        raise NotFrozen(f"archivist is imported from a checkout at {head or '?'}, not {real_openw.TAG}")
    try:
        real_openw.frozen(git)
    except real_openw.NotFrozen as error:
        raise NotFrozen(str(error)) from error
    if Path.cwd().resolve() != code:
        raise NotFrozen("run it from the tag's checkout, so labelling/, config/ and templates/ are the tag's")
    records = subprocess.run(
        ["git", "-C", str(data), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return {
        "tag": real_openw.TAG,
        "commit": tag,
        "archivist_from_tag_checkout": True,
        "frozen_check": "passed",
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rules_sha256": hashlib.sha256(Path(score.__file__).read_bytes()).hexdigest(),
        "records_commit": records,
    }


def committed(data: Path, paths: Sequence[Path], git: Callable[..., subprocess.CompletedProcess] | None = None) -> dict[str, str]:
    """Each file's sha256; refuses one that is missing, not tracked, differs from its commit, or
    whose commit is not on origin/main."""

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(data), *args], capture_output=True, text=True, check=False)

    git = git or run
    hashes = {}
    for path in paths:
        relative = path.relative_to(data).as_posix()
        if not path.exists():
            raise NotCommitted(f"{relative} is missing")
        if git("ls-files", "--error-unmatch", relative).returncode != 0:
            raise NotCommitted(f"{relative} is not committed")
        if git("diff", "--quiet", "HEAD", "--", relative).returncode != 0:
            raise NotCommitted(f"{relative} differs from its commit")
        last = git("log", "-1", "--format=%H", "--", relative).stdout.strip()
        if git("merge-base", "--is-ancestor", last, "origin/main").returncode != 0:
            raise NotCommitted(f"{relative} is committed but not pushed")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


# --- The measures -------------------------------------------------------------------------------


def parts(rereads: str) -> dict[str, Callable[[Scored], tuple[float, float]]]:
    """score.label_parts' three rates, and the share of the drawn cells sent to a person."""

    def sent(c: Scored) -> tuple[float, float]:
        to_review = c.status == "review" or (c.status == "accepted" and not score.accepted(c.status, c.unanswered, rereads))
        return c.weight * to_review, c.weight

    return {**score.label_parts(rereads), "sent_to_person": sent}


def results(cells: Sequence[Scored]) -> dict:
    """Every variant: the measures overall and by stratum, and what was counted."""
    out = {}
    for layout in LAYOUTS:
        kept = [c for c in cells if layout == "kept" or not c.both_ways]
        for rereads in REREADS:
            out[f"{layout}/{rereads}"] = {
                **score.counted(kept),
                "overall": score.estimate(kept, parts(rereads)),
                "by_stratum": {
                    name: score.estimate(mine, parts(rereads)) | {"counted": score.counted(mine)}
                    for name in STRATA
                    for mine in ([c for c in kept if c.stratum == name],)
                },
            }
    return out


def target(open_results: Mapping[str, Mapping]) -> dict:
    """O1: Open's wrong values among accepted below THRESHOLD, judged on the rate itself."""

    def met(variant: Mapping) -> bool:
        value = variant["overall"]["archivist_error"]["value"]
        return value is not None and value < THRESHOLD

    primary = open_results[PRIMARY]["overall"]["archivist_error"]
    return {
        "claim": "Muse Spark Open's error rate among accepted cells is below 1%.",
        "variant": PRIMARY,
        "threshold": THRESHOLD,
        "value": primary["value"],
        "ci": primary["ci"],
        "met": met(open_results[PRIMARY]),
        "in_every_variant": {name: met(variant) for name, variant in open_results.items()},
    }


def same_as_scored(mine: Mapping, scored: Mapping) -> None:
    """Raises unless version 1's rates worked out here are its score's, in every variant and
    stratum, to the last digit."""
    for name, variant in scored.items():
        for measure in COMPARED:
            pairs = [(mine[name]["overall"][measure], variant["overall"][measure])]
            pairs += [(mine[name]["by_stratum"][s][measure], variant["by_stratum"][s][measure]) for s in STRATA]
            for a, b in pairs:
                if json.loads(json.dumps(a)) != json.loads(json.dumps(b)):
                    raise ValueError(f"version 1's {measure} in {name} is not its score's: {a} against {b}")


# --- The cells ----------------------------------------------------------------------------------


def open_cells(
    draw: Mapping,
    first: Mapping[str, Mapping],
    found: Mapping[str, Mapping],
    reads: Mapping[str, object],
    verdicts: Mapping[str, VerdictRecord],
    asked_again: set[str],
    canonical: Mapping[str, Callable[[str, str], str]],
) -> list[Scored]:
    """Each drawn cell as Open read it and Archivist decided it, judged against its first label."""
    weights = score.cell_weights(draw)
    out = []
    for s in draw["sample"]:
        cell, label = s["cell"], first[s["cell"]]
        field = found[cell]["field"]
        if field is None:
            read, status = None, NO_VALUE
        else:
            value = reads[field]
            read = None if value.abstained else value.value
            verdict = verdicts[field]
            if verdict.value != read:
                raise ValueError(f"{field}: the verdict's value is not Open's read")
            status = verdict.status
        out.append(
            Scored(
                cell=cell,
                stratum=s["stratum"],
                family=s["family"],
                page=s["page"],
                weight=weights[cell],
                choice=label["choice"],
                outcome=score.judged(cell, label["choice"], label["value"], read, canonical[s["family"]]),
                status=status,
                unanswered=field is not None and field in asked_again,
                both_ways=s["page"] in BOTH_WAYS,
            )
        )
    return out


def first_cells(data: Path, draw: Mapping, first: Mapping[str, Mapping], canonical) -> list[Scored]:
    """Version 1's drawn cells, as labelling/score.py makes them, from its records and the cache."""
    from archivist.models import load_roles

    records = data / real_test.OUT_DIR / SIDE
    doc_types = real_test._types(real_test.CONFIG)
    pages = sorted(extract.load_predictions(records / "predictions.jsonl"), key=lambda p: p.page_id)
    reads = {v.field_id: v for p in pages for v in p.values}
    status = {v.field_id: v.status for v in verify.load_verdicts(records / verify.VERDICTS_FILE)}
    roles = load_roles(real_test.CONFIG, cache_dir=data / "cache")
    keys = score.reread_keys(pages, doc_types, roles["rereader"], data / real_test.DEFAULT_ROOT)
    lists = {name: [line["key"] for line in score._lines(records / name)] for name in score.UNANSWERED}
    strays = [k for found in lists.values() for k in found if k not in keys]
    if strays:
        raise ValueError(f"{len(strays)} unanswered keys match no re-read of version 1's deep check")
    unanswered = {cell for found in lists.values() for k in found for cell in keys[k]}
    weights = score.cell_weights(draw)
    out = []
    for s in draw["sample"]:
        cell, label, read = s["cell"], first[s["cell"]], reads[s["cell"]]
        out.append(
            Scored(
                cell=cell,
                stratum=s["stratum"],
                family=s["family"],
                page=s["page"],
                weight=weights[cell],
                choice=label["choice"],
                outcome=score.judged(
                    cell, label["choice"], label["value"], None if read.abstained else read.value, canonical[s["family"]]
                ),
                status=status[cell],
                unanswered=cell in unanswered,
                both_ways=s["page"] in BOTH_WAYS,
            )
        )
    return out


# --- The score ----------------------------------------------------------------------------------


def score_openw(data: Path) -> dict:
    """Everything the results report, from the records under data, on the tag's code."""
    first_records = data / real_test.OUT_DIR / SIDE
    records = data / real_openw.OUT_DIR / SIDE
    draw = json.loads((first_records / "labels" / DRAW_FILE).read_text(encoding="utf-8"))
    first = answers(first_records / "labels" / FILES["first"], "cell")
    unlabelled = [s["cell"] for s in draw["sample"] if s["cell"] not in first]
    if unlabelled:
        raise ValueError(f"{len(unlabelled)} of {len(draw['sample'])} cells have no first label")
    scored_first = json.loads((first_records / FIRST_SCORE).read_text(encoding="utf-8"))

    doc_types = real_test._types(real_openw.CONFIG)
    canonical = {f: doc_types[f].canonical for f in real_test.FAMILIES}
    found = {c["cell"]: c for c in json.loads((records / "cells.json").read_text(encoding="utf-8"))["cells"]}
    missing = sorted({s["cell"] for s in draw["sample"]} - set(found))
    if missing:
        raise ValueError(f"{len(missing)} drawn cells are not in cells.json")
    reads = {v.field_id: v for p in extract.load_predictions(records / "predictions.jsonl") for v in p.values}
    verdicts = {v.field_id: v for v in verify.load_verdicts(records / verify.VERDICTS_FILE)}
    asked_again = {
        v.field_id
        for path in real_openw.passes_of(records)
        for v in verify.load_verdicts(path)
        if v.evidence.reread_status == "failed"
    }
    opened = open_cells(draw, first, found, reads, verdicts, asked_again, canonical)
    v1 = first_cells(data, draw, first, canonical)
    v1_results = results(v1)
    same_as_scored(v1_results, scored_first["labels"])
    open_results = results(opened)

    classified = score.cell_weights(draw, "classified")
    sources = {f: s for line in score._lines(records / "boxes.jsonl") for f, s in line["box_sources"].items()}
    run = json.loads((records / "run.json").read_text(encoding="utf-8"))
    by_stratum = {name: [c for c in found.values() if c["stratum"] == name] for name in STRATA}
    return {
        "both_ways_pages": sorted(BOTH_WAYS),
        "o1": target(open_results),
        "open_weights": open_results,
        "version_1": v1_results,
        "open_weights_with_classified_weights": {
            name: {m: r["overall"][m] for m in (*COMPARED, "sent_to_person")}
            for name, r in results([replace(c, weight=classified[c.cell]) for c in opened]).items()
        },
        "cells_found": {
            "overall": dict(sorted(Counter(c["how"] for c in found.values()).items())),
            "by_stratum": {n: dict(sorted(Counter(c["how"] for c in cs).items())) for n, cs in by_stratum.items()},
            "at_the_same_position": sum(bool(c.get("same_position")) for c in found.values()),
            "status": dict(sorted(Counter(c.status for c in opened).items())),
        },
        "box_sources_drawn_cells": dict(
            sorted(Counter(sources.get(c["field"], "none") for c in found.values() if c["field"]).items())
        ),
        "asked_again": {"cells": len(asked_again), "drawn": sum(c.unanswered for c in opened)},
        "run": {k: run.get(k) for k in ("pages_read", "failed", "page_tries", "order_guard", "verification_pass", "cost_usd", "cost_full_usd", "started_at", "finished_at")},
        "stalled": (records / "stall.json").exists(),
    }


# --- The report ---------------------------------------------------------------------------------


def _pct(estimate: Mapping) -> str:
    return score._pct(estimate)


MEASURES = (
    ("archivist_error", "Wrong among accepted"),
    ("single_read_error", "Single read error"),
    ("catch_rate", "Wrong values caught"),
    ("sent_to_person", "Sent to a person"),
)


def render(record: Mapping) -> str:
    """score.md: version 1 and open weights side by side in every variant; score.json has all."""
    p, o1 = record["provenance"], record["o1"]
    lines = [
        "# Open weights on the real scans — scoring (PREREGISTRATION_OPENW.md)",
        "",
        f"Code: `{p['tag']}` ({p['commit'][:7]}), checked frozen; scorer sha256 `{p['scorer_sha256'][:12]}`, "
        f"rules (labelling/score.py) sha256 `{p['rules_sha256'][:12]}`. The same 400 drawn cells and labels "
        "for both; intervals 95%, page bootstrap within strata.",
        "",
        "Files (sha256): " + ", ".join(f"`{n}` {h}" for n, h in record.get("files_sha256", {}).items()),
        "",
        f"**O1** (below 1% wrong among accepted, {o1['variant']}): {'met' if o1['met'] else 'not met'}, "
        f"{_pct({'value': o1['value'], 'ci': o1['ci']})}. In every variant: {o1['in_every_variant']}.",
        "",
        "| Variant | Measure | Version 1 (Muse Spark 1.3) | Open weights (Muse Spark Open) |",
        "|---|---|---|---|",
    ]
    for name, mine in record["open_weights"].items():
        for key, title in MEASURES:
            lines.append(
                f"| {name} | {title} | {_pct(record['version_1'][name]['overall'][key])} | {_pct(mine['overall'][key])} |"
            )
    lines += ["", "By stratum:", "", "| Variant | Stratum | Measure | Version 1 | Open weights |", "|---|---|---|---|---|"]
    for name, mine in record["open_weights"].items():
        for stratum, o in mine["by_stratum"].items():
            for key, title in MEASURES:
                lines.append(
                    f"| {name} | {stratum} | {title} | {_pct(record['version_1'][name]['by_stratum'][stratum][key])} | {_pct(o[key])} |"
                )
    lines += ["", "Labels and outcomes (variant: by outcome, version 1; open weights):", ""]
    for name, mine in record["open_weights"].items():
        lines.append(f"- {name}: {record['version_1'][name]['by_outcome']}; {mine['by_outcome']}")
    compared = "; ".join(
        f"{name}: wrong among accepted {_pct(h['archivist_error'])}" for name, h in record["open_weights_with_classified_weights"].items()
    )
    lines += ["", f"Open weights with classified-page weights instead: {compared}."]
    f = record["cells_found"]
    lines += [
        "",
        "## How the drawn cells were found in Open's read",
        "",
        f"{f['overall']}; by stratum {f['by_stratum']}; {f['at_the_same_position']} at the drawn cell's own position; "
        f"statuses {f['status']}. Box sources of the cells found: {record['box_sources_drawn_cells']}. "
        f"Re-reads asked again: {record['asked_again']}.",
        "",
        "## The run",
        "",
        f"`{json.dumps(record['run'])}`; stalled: {record['stalled']}.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--data", type=Path, required=True, help="the main checkout, with the records")
    args = parser.parse_args(argv)
    data = args.data.resolve()
    origin = provenance(data)
    files = score.committed_labels(data)
    records = data / real_openw.OUT_DIR / SIDE
    files |= committed(data, [data / real_test.OUT_DIR / SIDE / FIRST_SCORE, *(records / n for n in RECORDS)])
    out = records / OUT
    if out.exists():
        parser.error(f"{out} exists: the open-weights run is scored once")
    record = {"provenance": origin, "files_sha256": files, **score_openw(data)}
    out.mkdir(parents=True)
    (out / "score.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "score.md").write_text(render(record), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
