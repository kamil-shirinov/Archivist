"""P46's coverage line (openw/coverage.py), on a synthetic score made by the frozen scorer's own
functions: no model, no real page, no held-out record."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # labelling/ and openw/ sit beside src/

from labelling import score_openw  # noqa: E402
from labelling.score import BOTH_WAYS, Scored  # noqa: E402
from openw import coverage  # noqa: E402

CHANGED = sorted(BOTH_WAYS)[0]


def _sample():
    rows = [("1940-01_p051", "1939_1942"), (CHANGED, "1939_1942"), ("1985-06_p058", "total_claims")]
    return [
        {"cell": f"T.f:{page}:0{n}:c", "stratum": stratum, "family": "f", "page": page}
        for n, (page, stratum) in enumerate(rows * 2)
    ]


def _cells(sample):
    found = [{**s, "field": s["cell"], "how": "label", "same_position": True} for s in sample]
    found[1] |= {"field": None, "how": "row_not_found"}  # on a changed-layout page
    found[2] |= {"field": None, "how": "page_not_read"}  # a total-claims page
    return found


def _score(sample, cells):
    cells_by = {c["cell"]: c for c in cells}
    scored = [
        Scored(cell=s["cell"], stratum=s["stratum"], family="f", page=s["page"], weight=1.0, choice="value",
               outcome="abstained" if cells_by[s["cell"]]["field"] is None else "right",
               status=score_openw.NO_VALUE if cells_by[s["cell"]]["field"] is None else "accepted",
               unanswered=False, both_ways=s["page"] in BOTH_WAYS)
        for s in sample
    ]
    found = score_openw.results(scored)
    raw = json.dumps({"cells": cells}).encode()
    return {
        "files_sha256": {"results/real_openw/held_out/cells.json": hashlib.sha256(raw).hexdigest()},
        "o1": score_openw.target(found),
        "open_weights": found,
        "version_1": found,
        "open_weights_with_classified_weights": {n: {m: r["overall"][m] for m in score_openw.COMPARED} for n, r in found.items()},
        "cells_found": {"overall": {"label": 4, "page_not_read": 1, "row_not_found": 1}},
    }, raw


def test_beside_every_rate_the_drawn_cells_not_in_opens_read_are_counted_by_variant_and_stratum():
    sample = _sample()
    cells = _cells(sample)
    scored, raw = _score(sample, cells)
    record = coverage.coverage(scored, sample, cells, hashlib.sha256(raw).hexdigest())
    kept, left = record["by_variant"]["kept/as_run"], record["by_variant"]["left_out/as_run"]
    assert kept["overall"] == {"cells": 2, "of": 6, "by_why": {"page_not_read": 1, "row_not_found": 1}}
    assert left["overall"] == {"cells": 1, "of": 4, "by_why": {"page_not_read": 1}}  # the changed page left out
    assert kept["by_stratum"]["total_claims"] == {"cells": 1, "of": 2, "by_why": {"page_not_read": 1}}
    assert record["o1"]["not_in_read"] == kept["overall"]
    record["score_sha256"] = "s" * 64
    text = coverage.render(scored, record)
    rows = [line for line in text.splitlines() if line.startswith(("| kept/", "| left_out/"))]
    assert len(rows) == 4 * 4 + 4 * 2 * 4  # every measure, overall and by stratum, in every variant
    assert all(" of " in line.rsplit("|", 2)[1] for line in rows)
    assert "drawn cells not in Open's read: 2 of 6 (page_not_read 1, row_not_found 1)" in text
    classified = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(classified) == 4 and all("not in Open's read" in line for line in classified)


def test_it_refuses_a_cells_file_the_score_does_not_record_or_whose_tally_differs():
    sample = _sample()
    cells = _cells(sample)
    scored, raw = _score(sample, cells)
    with pytest.raises(ValueError, match="not the file the score records"):
        coverage.coverage(scored, sample, cells, "0" * 64)
    scored["cells_found"]["overall"] = {"label": 6}
    with pytest.raises(ValueError, match="not the score's"):
        coverage.coverage(scored, sample, cells, hashlib.sha256(raw).hexdigest())


def test_it_writes_beside_the_score_once_and_never_touches_the_score(tmp_path):
    sample = _sample()
    cells = _cells(sample)
    scored, raw = _score(sample, cells)
    out = tmp_path / coverage.RECORDS / "score"
    out.mkdir(parents=True)
    (tmp_path / coverage.RECORDS / "cells.json").write_bytes(raw)
    (tmp_path / coverage.DRAW).parent.mkdir(parents=True)
    (tmp_path / coverage.DRAW).write_text(json.dumps({"sample": sample}))
    with pytest.raises(SystemExit):
        coverage.main(["--data", str(tmp_path)])  # no score yet
    (out / "score.json").write_text(json.dumps(scored))
    before = (out / "score.json").read_bytes()
    coverage.main(["--data", str(tmp_path)])
    assert (out / "score.json").read_bytes() == before and not (out / "score.md").exists()
    assert json.loads((out / "coverage.json").read_text())["score_sha256"] == hashlib.sha256(before).hexdigest()
    with pytest.raises(SystemExit):
        coverage.main(["--data", str(tmp_path)])  # written once
