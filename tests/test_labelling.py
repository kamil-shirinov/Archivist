"""The labels' draw and the labelling pages' server (labelling/): no model, no network, records
written in tmp_path from the approved templates' own cell ids."""

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # labelling/ sits beside src/

from archivist.schema import BBox, Citation, ExtractedValue, PageExtraction  # noqa: E402
from archivist.templates import real_test  # noqa: E402
from labelling import draw, serve  # noqa: E402

TYPES = real_test._types(real_test.CONFIG)
RAILROAD, CLAIMS = "receipts_and_expenditures_under_railroad", "total_claims_by_country"


def _page(family: str, page_id: str, *, abstain_rows: frozenset[str] = frozenset()) -> PageExtraction:
    values = []
    for field in TYPES[family].field_ids(page_id):
        row = draw.parts(field)[2]
        gone = row in abstain_rows
        values.append(
            ExtractedValue(
                field_id=field,
                value=None if gone else "1",
                citation=None if gone else Citation(page_id=page_id, bbox=BBox(x0=1, y0=2, x1=30, y1=12)),
                abstained=gone,
            )
        )
    return PageExtraction(page_id=page_id, doc_type=family, values=values)


def _records(out: Path, pages: list[PageExtraction], *, finished: bool = True) -> None:
    out.mkdir(parents=True)
    (out / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    by_family = {f: {"classified": 3, "confirmed": 2, "type_unconfirmed": 1} for f in real_test.FAMILIES}
    (out / "sweep.json").write_text(json.dumps({"by_family": by_family}))
    titles = [
        {"page": p.page_id, "classified_as": p.doc_type, "pattern": "x"} for p in pages
    ] + [{"page": "1940-01_p099", "classified_as": RAILROAD, "pattern": None}]
    (out / "titles.jsonl").write_text("".join(json.dumps(t) + "\n" for t in titles))
    if finished:
        (out / "verdicts.jsonl").write_text("")
        (out / "run.json").write_text("{}")


@pytest.fixture
def records(tmp_path: Path) -> Path:
    out = tmp_path / "held_out"
    railroad = [_page(RAILROAD, f"1940-{m:02d}_p026") for m in range(1, 7)]  # 510 figure cells
    claims = _page(CLAIMS, "1993-06_p097", abstain_rows=frozenset(TYPES[CLAIMS].layout.row_keys[:45]))
    _records(out, [*railroad, claims])
    return out


def test_the_draw_waits_for_both_runs(tmp_path: Path) -> None:
    out = tmp_path / "held_out"
    _records(out, [_page(RAILROAD, "1940-01_p026")], finished=False)
    with pytest.raises(FileNotFoundError, match="after both runs"):
        draw.draw(out)


def test_cells_are_figure_cells_of_returned_rows_sorted_by_id(records: Path) -> None:
    from archivist.pipeline import extract

    pages = extract.load_predictions(records / "predictions.jsonl")
    cells, dropped = draw.cells_of(pages, TYPES)
    railroad_money = TYPES[RAILROAD].money_fields
    assert cells["1939_1942"] == sorted(cells["1939_1942"])
    assert {draw.parts(c)[3] for c in cells["1939_1942"]} == railroad_money
    assert len(cells["1939_1942"]) == 6 * len(TYPES[RAILROAD].layout.row_keys) * len(railroad_money)
    claims_rows = TYPES[CLAIMS].layout.row_keys
    assert dropped == {CLAIMS: 45}
    assert {draw.parts(c)[2] for c in cells["total_claims"]} == set(claims_rows[45:])


def test_the_draw_is_seeded_as_preregistered(records: Path) -> None:
    record = draw.draw(records)
    from archivist.pipeline import extract

    cells, _ = draw.cells_of(extract.load_predictions(records / "predictions.jsonl"), TYPES)
    first = [s["cell"] for s in record["sample"] if s["stratum"] == "1939_1942"]
    second = [s["cell"] for s in record["sample"] if s["stratum"] == "total_claims"]
    assert first == random.Random(4004).sample(cells["1939_1942"], 300)
    assert second == random.Random(4004).sample(cells["total_claims"], 100)
    assert [s["order"] for s in record["sample"]] == list(range(1, 401))
    assert record["relabel"] == random.Random(4004).sample(sorted(first + second), 40)
    counted = sorted(p.page_id for p in extract.load_predictions(records / "predictions.jsonl"))
    assert [p["page"] for p in record["pages_checked"]] == random.Random(4004).sample(counted, 7)
    assert "1940-01_p099" not in {p["page"] for p in record["pages_checked"]}  # title rejected
    assert record["strata"]["total_claims"] == {"families": [CLAIMS], "cells": len(cells["total_claims"]), "sampled": 100}
    assert record["families"][RAILROAD] == {"classified": 3, "confirmed": 2, "deep_pages": 6}


def test_the_draw_names_no_value_and_names_rows_as_printed(records: Path) -> None:
    record = draw.draw(records)
    text = json.dumps(record)
    assert '"value"' not in text and "verdict" not in text and "ocr" not in text
    claims = next(s for s in record["sample"] if s["stratum"] == "total_claims")
    row = next(r for r in TYPES[CLAIMS].layout.rows if r.key == claims["row"])
    assert claims["row_named"] == row.printed
    assert draw.row_named(TYPES[RAILROAD], "07") == "row 7 from the top of the table"
    forward = TYPES["outstanding_forward_exchange_contracts"]
    assert draw.row_named(forward, "total_sale_03") == 'row 3 under the heading "TOTAL SALES CONTRACTS:"'


def test_the_draw_is_made_once(records: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(real_test, "OUT_DIR", tmp_path)
    draw.main(["--side", "held_out"])
    with pytest.raises(SystemExit):
        draw.main(["--side", "held_out"])


@pytest.fixture
def labels(records: Path, tmp_path: Path, monkeypatch) -> serve.Labels:
    monkeypatch.setattr(real_test, "OUT_DIR", tmp_path)
    draw.main(["--side", "held_out"])
    return serve.Labels("held_out", records / "labels")


def test_the_page_is_never_sent_a_read(labels: serve.Labels) -> None:
    shown = labels.cells("first")
    assert len(shown["cells"]) == 400 and shown["answers"] == {}
    for cell in shown["cells"]:
        assert set(cell) == {"n", "cell", "page", "title", "unit", "row", "column", "box"}
    assert shown["cells"][0]["box"] == {"x0": 1.0, "y0": 2.0, "x1": 30.0, "y1": 12.0}


def test_answers_are_kept_as_given_and_the_last_stands(labels: serve.Labels) -> None:
    cell = labels.draw["sample"][0]["cell"]
    with pytest.raises(ValueError, match="typed as printed"):
        labels.answer({"pass": "first", "cell": cell, "choice": "value", "value": "  "})
    with pytest.raises(ValueError, match="not drawn"):
        labels.answer({"pass": "first", "cell": "T.x:y:01:z", "choice": "blank"})
    with pytest.raises(ValueError, match="choice"):
        labels.answer({"pass": "first", "cell": cell, "choice": "zero"})
    labels.answer({"pass": "first", "cell": cell, "choice": "value", "value": " 1,234 "})
    labels.answer({"pass": "first", "cell": cell, "choice": "blank"})
    lines = (labels.labels / "labels.jsonl").read_text().splitlines()
    assert [json.loads(line)["choice"] for line in lines] == ["value", "blank"]
    assert json.loads(lines[0])["value"] == "1,234"
    assert labels.cells("first")["answers"] == {cell: {"choice": "blank", "value": None}}


def test_the_relabel_pass_opens_24_hours_after_the_last_first_label(
    labels: serve.Labels, monkeypatch
) -> None:
    start = datetime(2026, 11, 1, 9, tzinfo=UTC)
    monkeypatch.setattr(serve, "_now", lambda: start)
    assert "400 cells have no first label" in labels.cells("relabel")["blocked"]
    for sampled in labels.draw["sample"]:
        labels.answer({"pass": "first", "cell": sampled["cell"], "choice": "value", "value": "7"})
    assert "opens at 2026-11-02T09:00" in labels.cells("relabel")["blocked"]
    with pytest.raises(ValueError, match="not a pass open"):
        labels.answer({"pass": "relabel", "cell": labels.draw["relabel"][0], "choice": "blank"})
    monkeypatch.setattr(serve, "_now", lambda: start + timedelta(hours=24))
    shown = labels.cells("relabel")
    assert shown["blocked"] is None and shown["answers"] == {}  # never the first labels
    assert [c["cell"] for c in shown["cells"]] == labels.draw["relabel"]
    labels.answer({"pass": "relabel", "cell": labels.draw["relabel"][0], "choice": "cant_read"})
    assert (labels.labels / "relabels.jsonl").exists()


def test_the_page_check_takes_right_or_wrong_for_drawn_pages(labels: serve.Labels) -> None:
    pages = labels.checks()["pages"]
    assert [p["page"] for p in pages] == [p["page"] for p in labels.draw["pages_checked"]]
    assert pages[0]["title"] == TYPES[pages[0]["family"]].template.identity.title
    with pytest.raises(ValueError, match="verdict"):
        labels.check({"page": pages[0]["page"], "verdict": "maybe"})
    with pytest.raises(ValueError, match="not drawn"):
        labels.check({"page": "1940-01_p099", "verdict": "wrong"})
    labels.check({"page": pages[0]["page"], "verdict": "wrong"})
    assert labels.checks()["answers"] == {pages[0]["page"]: {"verdict": "wrong"}}


def test_only_drawn_pages_are_served(labels: serve.Labels) -> None:
    with pytest.raises(ValueError, match="not drawn"):
        labels.image("1940-01_p099")
