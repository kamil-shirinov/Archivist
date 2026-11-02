"""The open-weights run's runner (P46, PREREGISTRATION_OPENW.md): its gate, caps, config, how a
drawn cell is found in Open's read, the run on drawn pages, its passes and its stall stop, offline.

No model is called and no real page is opened: the readers and the segmenter are mocks, pages
resolve to images drawn in tmp_path, and git is a fake.
"""

import json
import threading
import time
import tomllib
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from archivist.models.mock import MockLLM, MockSegmenter
from archivist.pipeline import extract
from archivist.templates import real_openw, real_test
from archivist.templates import test as arithmetic
from archivist.templates.pages import Page, PageRefused

ROOT = Path(__file__).resolve().parents[1]
RAILROAD = "receipts_and_expenditures_under_railroad"
FORWARD = "outstanding_forward_exchange_contracts"
COLUMNS = ("period", "taxes", "admin", "to_retirement", "to_unemployment", "total_exp")


def _git(answers):
    import subprocess

    def git(*args):
        code, out = answers.get(args[0], (0, ""))
        return subprocess.CompletedProcess(args, code, out, "")

    return git


def types():
    return real_test._types(ROOT / real_openw.CONFIG)


def ev(field_id, value, abstained=False):
    from archivist.schema import ExtractedValue

    return ExtractedValue(field_id=field_id, value=value, abstained=abstained, citation=None)


# --- The gate, the caps and the config ----------------------------------------------------------


def test_the_held_out_side_runs_only_on_its_own_tag_with_the_scorer_frozen_too():
    assert real_openw.TAG == "run-real-openw" and real_openw.TAG != real_test.TAG
    assert "labelling" in real_openw.FROZEN
    real_openw.frozen(_git({}))
    for answers, says in (
        ({"rev-parse": (1, "")}, "no tag"),
        ({"diff": (1, "")}, "differs"),
        ({"status": (0, "?? labelling/new.py\n")}, "not in"),
    ):
        with pytest.raises(real_openw.NotFrozen, match=says):
            real_openw.frozen(_git(answers))


def test_the_held_out_side_takes_no_choice_and_checks_the_code_before_anything(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("nothing is built or opened before the gate")

    monkeypatch.setattr(real_openw, "load_roles", never)
    monkeypatch.setattr(real_openw, "caps", never)
    for extra in (["--pages", "1940-01_p001"], ["--per-page", "3"], ["--allowance", "1"]):
        with pytest.raises(SystemExit):
            real_openw.main(["deep", "--side", "held_out", *extra])
    monkeypatch.setattr(real_openw, "frozen", lambda: (_ for _ in ()).throw(real_openw.NotFrozen("x")))
    with pytest.raises(real_openw.NotFrozen):
        real_openw.main(["deep", "--side", "held_out"])


def test_the_development_side_may_not_spend_more_than_three_dollars(monkeypatch):
    monkeypatch.setattr(real_openw, "caps", lambda *a: (_ for _ in ()).throw(AssertionError("no")))
    with pytest.raises(SystemExit):
        real_openw.main(["deep", "--side", "development", "--pages", "x", "--allowance", "3.01"])


def test_caps_let_baseten_spend_the_allowance_and_nothing_else_spend_at_all(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    lines = [{"backend": "meta", "cost_usd": 2.5}, {"backend": "baseten", "cost_usd": 4.0}]
    ledger.write_text("".join(json.dumps(line) + "\n" for line in lines))
    record = real_openw.caps(tmp_path / "out", 20.0, ledger)
    assert record["meta"] == 2.5 and record["baseten"] == 24.0 and "fireworks" not in record
    ledger.write_text(ledger.read_text() + json.dumps({"backend": "baseten", "cost_usd": 9}) + "\n")
    assert real_openw.caps(tmp_path / "out", 20.0, ledger) == record  # read back, not redone
    for variable in ("BUDGET_CAP_USD", "BASETEN_CAP_USD", "FIREWORKS_CAP_USD", "GLIMMER_CAP_USD"):
        monkeypatch.delenv(variable, raising=False)
    real_openw.set_caps(record)
    import os

    assert os.environ["FIREWORKS_CAP_USD"] == "0.0" and os.environ["GLIMMER_CAP_USD"] == "0.0"


def test_the_config_reads_with_open_at_p33s_settings_and_keeps_version_1s_segmenter():
    config = tomllib.loads((ROOT / real_openw.CONFIG).read_text())
    first = tomllib.loads((ROOT / real_test.CONFIG).read_text())
    assert tuple(config["doc_types"]["enabled"]) == real_test.FAMILIES
    for role in ("extractor", "rereader"):
        spec = config["roles"][role]
        assert (spec["backend"], spec["model_id"]) == ("baseten", "meta-models/muse-spark-open-1026")
        assert spec["settings"]["reasoning_effort"] == "low"
    assert config["roles"]["extractor"]["settings"]["timeout_s"] == 1200.0
    assert config["roles"]["segmenter"] == first["roles"]["segmenter"]  # so SAM replays its cache
    assert config["prices"]["sam-3.1"] == first["prices"]["sam-3.1"]
    assert set(config["roles"]) == {"extractor", "rereader", "segmenter"}  # no classifier is asked


# --- Finding a drawn cell in Open's read --------------------------------------------------------


def _railroad(labels, family=RAILROAD, page="1939-12_p025"):
    """A read railroad table whose rows carry these period labels, and a figure in every cell."""
    values = []
    for n, label in enumerate(labels, 1):
        for column in COLUMNS:
            text = label if column == "period" else "1.0"
            values.append(ev(f"T.{family}:{page}:{n:02d}:{column}", text))
    for n in range(len(labels) + 1, 18):  # rows not returned
        for column in COLUMNS:
            values.append(ev(f"T.{family}:{page}:{n:02d}:{column}", None, abstained=True))
    from archivist.schema import PageExtraction

    return PageExtraction(page_id=page, doc_type=family, values=values)


def test_a_drawn_cell_is_the_row_with_its_label_and_occurrence_not_its_position():
    doc_type = types()[RAILROAD]
    first = _railroad(["1938 .....", "Nov.", "Dec.", "Nov.", "", "1939"])
    read = _railroad(["1937", "1938", "Nov", "Dec.", "N o v .", "", "1939"])  # one row more at the top
    cell = lambda row: f"T.{RAILROAD}:1939-12_p025:{row}:taxes"  # noqa: E731

    assert real_openw.match(doc_type, first, read, cell("01")) == {
        "field": cell("02"), "how": "label", "same_position": False,
    }
    assert real_openw.match(doc_type, first, read, cell("04"))["field"] == cell("05")  # the 2nd Nov.
    assert real_openw.match(doc_type, first, read, cell("05")) == {  # no label: by position
        "field": cell("05"), "how": "position_no_label", "same_position": True,
    }
    assert real_openw.match(doc_type, first, read, cell("06"))["field"] == cell("07")
    other = _railroad(["1936", "Jan.", "Feb."])
    assert real_openw.match(doc_type, first, other, cell("02")) == {"field": None, "how": "row_not_found"}
    assert real_openw.match(doc_type, first, None, cell("02")) == {"field": None, "how": "page_not_read"}


def test_in_a_table_read_in_sections_the_occurrence_is_counted_within_the_section():
    from archivist.schema import PageExtraction

    doc_type = types()[FORWARD]
    label = next(c.key for c in doc_type.layout.columns if c.kind == "text")
    figure = sorted(doc_type.money_fields)[0]
    keys = doc_type.layout.row_keys
    sections = sorted({k.rsplit("_", 1)[0] for k in keys})
    a, b = sections[:2]

    def page(labels):
        values = []
        for key in keys:
            text = labels.get(key)
            values.append(ev(f"T.{FORWARD}:p:{key}:{label}", text))
            values.append(ev(f"T.{FORWARD}:p:{key}:{figure}", "5"))
        return PageExtraction(page_id="p", doc_type=FORWARD, values=values)

    first = page({f"{a}_01": "Sept. 6", f"{b}_01": "Sept. 13", f"{b}_02": "Sept. 6"})
    read = page({f"{a}_01": "Sept. 6", f"{a}_02": "Sept. 13", f"{b}_01": "Sept. 6"})
    cell = f"T.{FORWARD}:p:{b}_02:{figure}"
    assert real_openw.match(doc_type, first, read, cell) == {
        "field": f"T.{FORWARD}:p:{b}_01:{figure}", "how": "label", "same_position": False,
    }
    lost = f"T.{FORWARD}:p:{b}_01:{figure}"  # Sept. 13 is in the other section of Open's read
    assert real_openw.match(doc_type, first, read, lost)["how"] == "row_not_found"


def test_a_fixed_row_is_the_templates_row():
    from archivist.schema import PageExtraction

    doc_type = types()["total_claims_by_country"]
    key, column = doc_type.layout.row_keys[3], sorted(doc_type.money_fields)[0]
    field = f"T.total_claims_by_country:p:{key}:{column}"
    page = PageExtraction(
        page_id="p", doc_type="total_claims_by_country", values=[ev(field, "1")]
    )
    assert real_openw.match(doc_type, page, page, field) == {
        "field": field, "how": "fixed_row", "same_position": True,
    }


# --- The run, on drawn pages --------------------------------------------------------------------


@pytest.fixture
def drawn(tmp_path, monkeypatch) -> dict[str, Page]:
    """Three pages drawn in tmp_path; any other reference, or another side, is refused."""
    found = {}
    for n in range(3):
        ref = f"1939-0{n + 1}_p010"
        path = tmp_path / "pages" / f"{ref}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1000, 1000), "white")
        canvas = ImageDraw.Draw(image)
        for r in range(1, 18):
            for i in range(6):
                x0, y0 = 120 + 140 * i, 50 + 50 * r
                canvas.rectangle([x0, y0, x0 + 60 + n, y0 + 20], fill=(10 * n, 10 * n, 10 * n))
        image.save(path)
        found[ref] = Page(ref, ref, path)

    def resolve(ref, side, root=None):
        if ref not in found or side != "development":
            raise PageRefused(f"{ref}: refused")
        return found[ref]

    monkeypatch.setattr(real_test, "resolve", resolve)
    return found


def _answer(labels):
    def respond(request) -> str:
        texts = ("2.0", "1.0", "1.0", "1.0", "3.0")
        rows = {
            f"{r:02d}": {
                c: {"value": label if c == "period" else t, "box": [100 + 140 * i, 40 + 50 * r, 220 + 140 * i, 80 + 50 * r]}
                for i, (c, t) in enumerate(zip(COLUMNS, ("",) + texts, strict=True))
            }
            for r, label in enumerate(labels, 1)
        }
        return json.dumps({"rows": rows})

    return respond


LABELS = [f"19{n:02d}" for n in range(23, 40)]  # 17 distinct periods


@pytest.fixture
def source(tmp_path, drawn) -> Path:
    """Version 1's development records: its first read of every page and its title check."""
    doc_type = types()[RAILROAD]
    out = tmp_path / "v1"
    out.mkdir()
    first = MockLLM(_answer(LABELS))
    lines, titles = [], []
    for ref, page in sorted(drawn.items()):
        values = extract.read_page(
            page.path.read_bytes(), ref, first, doc_type, "S0", arithmetic.output_tokens(doc_type)
        )
        lines.append(extract.PageExtraction(page_id=ref, doc_type=RAILROAD, values=values).model_dump_json())
        titles.append({"page": ref, "classified_as": RAILROAD, "pattern": None if ref.startswith("1939-03") else "x"})
    (out / "predictions.jsonl").write_text("\n".join(lines) + "\n")
    (out / "titles.jsonl").write_text("".join(json.dumps(t) + "\n" for t in titles))
    return out


def _roles(rereader):
    # Open's read has one row more at the top, so every drawn cell is found one row down.
    return {
        "extractor": MockLLM(_answer(["1922", *LABELS[:16]])),
        "rereader": rereader,
        "segmenter": MockSegmenter(),
    }


def test_the_run_reads_each_page_once_finds_the_drawn_cells_and_re_reads_only_them(tmp_path, drawn, source):
    doc_types, out = types(), tmp_path / "out"
    wanted = ["1939-01_p010", "1939-02_p010"]
    with pytest.raises(ValueError, match="title check confirmed"):
        real_openw.run(out, "development", _roles(MockLLM()), doc_types, source=source, wanted=["1939-03_p010"])
    rereader = MockLLM(lambda request: json.dumps({"value": "1.0"}))
    roles = _roles(rereader)

    verdicts, record = real_openw.run(
        out, "development", roles, doc_types, source=source, wanted=wanted, per_page=6, workers=2,
        layer_of=lambda page: (),
    )
    draw = json.loads((out / "draw.json").read_text())
    assert draw["seed"] == 4004 and len(draw["sample"]) == 12
    cells = json.loads((out / "cells.json").read_text())["cells"]
    in_range = [c for c in cells if int(c["cell"].split(":")[2]) <= 16]  # 1939 is not in Open's read
    assert all(c["how"] == "label" and c["same_position"] is False for c in in_range)
    assert all(c["how"] == "row_not_found" for c in cells if c not in in_range)
    assert len(roles["extractor"].calls) == 2 and len(roles["segmenter"].calls) == 2 * 2
    assert len(verdicts) == len(in_range) == record["calls"]["rereads"]
    # With no OCR layer each page takes S0+grid's order fallback, whose guard re-reads 20 cells.
    assert record["order_guard"] == {"pages": 2, "cells_reread": 40, "used": 0}  # it refused
    assert len(rereader.calls) == len(in_range) + 40
    assert {v.field_id for v in verdicts} == {c["field"] for c in in_range}
    by_column = {}
    for v in verdicts:
        by_column.setdefault(v.field_id.rsplit(":", 1)[-1], set()).add(v.status)
    assert by_column.get("total_exp", {"review"}) == {"review"}  # the re-read disagrees
    assert by_column.get("admin", {"accepted"}) == {"accepted"}  # both 1.0 and the identity holds

    with pytest.raises(real_openw.Finished, match="no re-read failed"):
        real_openw.run(out, "development", roles, doc_types, source=source, wanted=wanted,
                       layer_of=lambda page: ())
    assert len(roles["extractor"].calls) == 2


def test_failed_re_reads_are_asked_again_on_a_later_pass_and_every_pass_is_kept(tmp_path, drawn, source):
    doc_types, out = types(), tmp_path / "out"
    failing = [True]

    def respond(request):
        if failing[0]:
            raise TimeoutError("slow")
        return json.dumps({"value": "1.0"})

    rereader = MockLLM(respond)
    roles = _roles(rereader)
    common = dict(source=source, wanted=["1939-01_p010"], per_page=4, workers=1, layer_of=lambda page: ())
    first, record = real_openw.run(out, "development", roles, doc_types, **common)
    assert record["rereads_failed"] and all(v.status == "review" for v in first)
    asked = len(rereader.calls)
    failing[0] = False
    second, record = real_openw.run(out, "development", roles, doc_types, **common)
    assert record["verification_pass"] == 2 and not record["rereads_failed"]
    assert len(rereader.calls) - asked == len(first)  # only the failed ones, once each
    assert (out / "verdicts.pass1.jsonl").exists()
    with pytest.raises(real_openw.Finished):
        real_openw.run(out, "development", roles, doc_types, **common)


def test_a_page_that_fails_is_tried_on_later_starts_up_to_its_tries(tmp_path, drawn, source):
    doc_types, out = types(), tmp_path / "out"
    roles = _roles(MockLLM(lambda request: json.dumps({"value": "1.0"})))
    roles["extractor"] = MockLLM(lambda request: (_ for _ in ()).throw(TimeoutError("slow")))
    common = dict(source=source, wanted=["1939-01_p010"], per_page=4, workers=1, layer_of=lambda page: ())
    for _ in range(real_openw.PAGE_TRIES):
        verdicts, record = real_openw.run(out, "development", roles, doc_types, **common)
        assert verdicts == [] and record["failed"] == ["1939-01_p010"]
    assert record["cells_found"] == {"page_not_read": 4}
    with pytest.raises(real_openw.Finished):
        real_openw.run(out, "development", roles, doc_types, **common)


# --- A stall stops the run ----------------------------------------------------------------------


def test_a_call_in_flight_with_no_answer_for_the_stall_time_stops_the_run(tmp_path):
    lock = threading.Lock()
    watch = real_openw.Watch(tmp_path, lock, stall_s=0.05, poll_s=0.01)
    stopped = []
    watch.stop = stopped.append
    assert not watch.stalled()
    watch.enter()
    time.sleep(0.1)
    assert watch.stalled()
    watch.leave()
    assert not watch.stalled()  # nothing in flight is no stall
    watch.enter()
    watch.start()
    for _ in range(100):
        if stopped:
            break
        time.sleep(0.01)
    assert stopped == [3] and json.loads((tmp_path / "stall.json").read_text())["in_flight"] == 1


def test_a_watched_role_passes_everything_through():
    inner = MockLLM(lambda request: '{"value": "1"}')
    watch = real_openw.Watch(Path("."), threading.Lock())
    role = real_openw.Watched(inner, watch)
    from archivist.models import LLMRequest

    assert role.complete(LLMRequest(role="rereader", prompt="x")).text == '{"value": "1"}'
    assert role.name == inner.name and watch.in_flight == 0


# --- The draw's own rules, copied, must stay the draw's -----------------------------------------


def test_the_label_and_cell_rules_are_labelling_draws_on_version_1s_development_reads():
    import sys

    sys.path.insert(0, str(ROOT))  # labelling/ sits beside src/
    from labelling import draw

    doc_types = types()
    pages = extract.load_predictions(ROOT / "results/real_test/development/predictions.jsonl")
    for page in pages:
        doc_type = doc_types[page.doc_type]
        stratum = real_openw.STRATA[page.doc_type]
        assert real_openw.figure_cells(page, doc_type) == draw.cells_of([page], doc_types)[0][stratum]
        for value in page.values:
            assert real_openw.printed(value.value) == draw.printed(value.value)
            assert real_openw._parts(value.field_id) == draw.parts(value.field_id)
    assert real_openw.STRATA == {f: n for n, fs in draw.STRATA.items() for f in fs}


def test_the_runs_own_cache_is_seeded_from_the_shared_one_which_is_never_written(tmp_path):
    from archivist.models import LLMRequest
    from archivist.models.cache import Cache, cache_key

    shared, own = tmp_path / "shared", tmp_path / "own"
    asked = LLMRequest(role="rereader", prompt="seen before")
    answered = Cache(MockLLM(lambda request: '{"value": "7"}'), shared)
    answered.complete(asked)  # an answer the shared cache already holds
    before = sorted(p.relative_to(shared) for p in shared.rglob("*.json"))
    inner = MockLLM(lambda request: '{"value": "8"}')
    role = real_openw.ReadThrough(Cache(inner, own), shared)

    assert role.complete(asked).text == '{"value": "7"}' and inner.calls == []  # from the shared one
    assert role.complete(LLMRequest(role="rereader", prompt="new")).text == '{"value": "8"}'
    assert sorted(p.relative_to(shared) for p in shared.rglob("*.json")) == before
    key = cache_key(inner.name, inner.model_id, asked, {})
    assert (own / key[:2] / f"{key}.json").exists() and len(list(own.rglob("*.json"))) == 2
