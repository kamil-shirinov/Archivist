"""P46: beside every rate of the open-weights score, how many drawn cells Open's read did not contain.

    uv run python -m openw.coverage  # after labelling.score_openw has written the score, once

Added after the open-weights run had started on run-real-openw and before any result was seen
(PREREGISTRATION_OPENW.md, Deviations). It only adds reporting: it reads the frozen scorer's
results/real_openw/held_out/score/score.json as written, this run's cells.json and version 1's
draw, and writes score/coverage.json and score/coverage.md beside them. No rate is recomputed or
changed, score.json and score.md are never written, and no model is called.

A drawn cell Open's read did not contain is one for which the runner found no field of Open's
read (cells.json: field null, because the row was not found or the page was not read). It gave
no value, so the scorer leaves it outside the error rates; it is counted here, for each variant
and stratum, beside every rate, so that rows the read left out cannot make the rates look better.
It refuses unless cells.json is the file the score records (its sha256 in files_sha256) and its
counts agree with the score's own tally of how the cells were found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # labelling/ sits beside src/

from labelling.draw import STRATA  # noqa: E402
from labelling.score import BOTH_WAYS, _pct  # noqa: E402

RECORDS = Path("results/real_openw/held_out")
DRAW = Path("results/real_test/held_out/labels/draw.json")
NOT_FOUND = ("page_not_read", "row_not_found")
MEASURES = (
    ("archivist_error", "Wrong among accepted"),
    ("single_read_error", "Single read error"),
    ("catch_rate", "Wrong values caught"),
    ("sent_to_person", "Sent to a person"),
)


def missing(sample: list[dict], found: Mapping[str, Mapping], layout: str, stratum: str | None = None) -> dict:
    """The drawn cells of a variant's layout (and stratum) Open's read did not contain, of how
    many, and why."""
    cells = [
        s for s in sample
        if (layout == "kept" or s["page"] not in BOTH_WAYS) and (stratum is None or s["stratum"] == stratum)
    ]
    gone = [s for s in cells if found[s["cell"]]["field"] is None]
    return {
        "cells": len(gone),
        "of": len(cells),
        "by_why": dict(sorted(Counter(found[s["cell"]]["how"] for s in gone).items())),
    }


def shown(counts: Mapping) -> str:
    """"12 of 400 (row_not_found 11, page_not_read 1)"."""
    why = ", ".join(f"{k} {n}" for k, n in counts["by_why"].items())
    return f"{counts['cells']} of {counts['of']}" + (f" ({why})" if why else "")


def coverage(scored: Mapping, sample: list[dict], cells: list[dict], cells_sha256: str) -> dict:
    """The counts beside every rate of the score, checked against the score's own records."""
    recorded = scored["files_sha256"].get(str(RECORDS / "cells.json"))
    if recorded != cells_sha256:
        raise ValueError("cells.json is not the file the score records")
    found = {c["cell"]: c for c in cells}
    if sorted(found) != sorted(s["cell"] for s in sample):
        raise ValueError("cells.json and the draw name different cells")
    tally = dict(sorted(Counter(c["how"] for c in cells).items()))
    if tally != scored["cells_found"]["overall"]:
        raise ValueError(f"cells.json's tally {tally} is not the score's {scored['cells_found']['overall']}")
    out = {}
    for name in scored["open_weights"]:
        layout = name.split("/")[0]
        out[name] = {
            "overall": missing(sample, found, layout),
            "by_stratum": {s: missing(sample, found, layout, s) for s in STRATA},
        }
    return {
        "note": "Drawn cells Open's read did not contain, beside every rate; reporting only, no rate changed.",
        "score_sha256": None,  # set by main from the file read
        "by_variant": out,
        "o1": {"variant": scored["o1"]["variant"], "not_in_read": out[scored["o1"]["variant"]]["overall"]},
    }


def render(scored: Mapping, record: Mapping) -> str:
    """coverage.md: every rate of the score as it wrote it, with the count beside it."""
    o1, by = scored["o1"], record["by_variant"]
    lines = [
        "# Open weights on the real scans — drawn cells not in Open's read, beside every rate",
        "",
        "Reporting only (PREREGISTRATION_OPENW.md, Deviations): every rate below is copied from `score.json` "
        f"(sha256 `{record['score_sha256']}`) as the frozen scorer wrote it. Beside each: how many of the drawn "
        "cells Open's read did not contain, of how many, and why. Such a cell gave no value, so it is outside "
        "the error rates; it is shown so that missing rows cannot make the rates look better.",
        "",
        f"**O1** ({o1['variant']}): {'met' if o1['met'] else 'not met'}, {_pct({'value': o1['value'], 'ci': o1['ci']})}; "
        f"drawn cells not in Open's read: {shown(record['o1']['not_in_read'])}.",
        "",
        "| Variant | Measure | Version 1 | Open weights | Drawn cells not in Open's read |",
        "|---|---|---|---|---|",
    ]
    for name, mine in scored["open_weights"].items():
        for key, title in MEASURES:
            lines.append(
                f"| {name} | {title} | {_pct(scored['version_1'][name]['overall'][key])} | "
                f"{_pct(mine['overall'][key])} | {shown(by[name]['overall'])} |"
            )
    lines += ["", "By stratum:", "", "| Variant | Stratum | Measure | Version 1 | Open weights | Drawn cells not in Open's read |",
              "|---|---|---|---|---|---|"]
    for name, mine in scored["open_weights"].items():
        for stratum, o in mine["by_stratum"].items():
            for key, title in MEASURES:
                lines.append(
                    f"| {name} | {stratum} | {title} | {_pct(scored['version_1'][name]['by_stratum'][stratum][key])} | "
                    f"{_pct(o[key])} | {shown(by[name]['by_stratum'][stratum])} |"
                )
    lines += ["", "With classified-page weights instead:", ""]
    for name, h in scored["open_weights_with_classified_weights"].items():
        lines.append(f"- {name}: wrong among accepted {_pct(h['archivist_error'])}; "
                     f"drawn cells not in Open's read: {shown(by[name]['overall'])}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--data", type=Path, default=Path("."), help="the checkout with the records")
    args = parser.parse_args(argv)
    data = args.data.resolve()
    out = data / RECORDS / "score"
    if not (out / "score.json").exists():
        parser.error(f"no {out / 'score.json'}: run labelling.score_openw first")
    if (out / "coverage.json").exists():
        parser.error(f"{out / 'coverage.json'} exists: written once")
    raw = (out / "score.json").read_bytes()
    scored = json.loads(raw)
    sample = json.loads((data / DRAW).read_text(encoding="utf-8"))["sample"]
    cells_bytes = (data / RECORDS / "cells.json").read_bytes()
    record = coverage(scored, sample, json.loads(cells_bytes)["cells"], hashlib.sha256(cells_bytes).hexdigest())
    record["score_sha256"] = hashlib.sha256(raw).hexdigest()
    (out / "coverage.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "coverage.md").write_text(render(scored, record), encoding="utf-8")
    print(f"-> {out / 'coverage.md'}")


if __name__ == "__main__":
    main()
