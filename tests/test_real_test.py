"""The real-pages test's runner (P29, PREREGISTRATION_REAL.md): its gate, caps, sample, sweep and
deep check, offline.

No model is called and no real page is opened: the extractor, the re-reader and the segmenter are
mocks, pages resolve to images drawn in tmp_path, and git is a fake.
"""

import hashlib
import json
import os
import random
import re
import subprocess
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from archivist.doctypes import UNSUPPORTED, recorded
from archivist.models.mock import MockLLM, MockSegmenter
from archivist.templates import pages, real_test
from archivist.templates.pages import Page, PageRefused

ROOT = Path(__file__).resolve().parents[1]
RAILROAD = "receipts_and_expenditures_under_railroad"


def _git(answers: dict[str, tuple[int, str]]):
    def git(*args):
        code, out = answers.get(args[0], (0, ""))
        return subprocess.CompletedProcess(args, code, out, "")

    return git


def test_the_held_out_side_runs_only_on_the_tagged_code():
    real_test.frozen(_git({}))
    for answers, says in (
        ({"rev-parse": (1, "")}, "no tag"),
        ({"diff": (1, "")}, "differs"),
        ({"status": (0, "?? src/archivist/new.py\n")}, "not in"),
    ):
        with pytest.raises(real_test.NotFrozen, match=says):
            real_test.frozen(_git(answers))


def test_the_held_out_side_takes_no_choice_and_checks_the_code_before_anything(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("nothing is built or opened before the gate")

    monkeypatch.setattr(real_test, "load_roles", never)
    monkeypatch.setattr(real_test, "caps", never)
    for extra in (["--per-family", "3"], ["--issues", "1940-01"], ["--allowance", "1"]):
        with pytest.raises(SystemExit):
            real_test.main(["sweep", "--side", "held_out", *extra])

    def not_frozen():
        raise real_test.NotFrozen("no tag")

    monkeypatch.setattr(real_test, "frozen", not_frozen)
    with pytest.raises(real_test.NotFrozen):
        real_test.main(["deep", "--side", "held_out"])


def test_a_page_is_resolved_only_on_its_side_and_only_if_it_matches_the_manifest(
    tmp_path, monkeypatch
):
    image = tmp_path / "pages" / "1940-01" / "p007.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"page")
    digest = "6c3f0d8b0d7c5b8e0b4b1c79a1f1c2a7b4b9f5c6e0b0b3c2c4a9d1e3f5a7b9c1"  # not its hash
    split = {"development": ["1939-01"], "held_out": ["1940-01"]}
    monkeypatch.setattr(real_test, "issues_of", lambda side, root: split[side])
    monkeypatch.setattr(real_test, "_hashes", lambda root: {("1940-01", 7): digest})
    with pytest.raises(PageRefused, match="not on the development side"):
        real_test.resolve("1940-01_p007", "development", tmp_path)
    with pytest.raises(PageRefused, match="does not match"):
        real_test.resolve("1940-01_p007", "held_out", tmp_path)
    digest = hashlib.sha256(b"page").hexdigest()
    monkeypatch.setattr(real_test, "_hashes", lambda root: {("1940-01", 7): digest})
    assert real_test.resolve("1940-01_p007", "held_out", tmp_path) == Page(
        "1940-01_p007", "1940-01_p007", image
    )
    with pytest.raises(PageRefused, match="not a Treasury"):
        real_test.resolve("dev/card-01-1", "held_out", tmp_path)


def test_the_template_commands_still_refuse_every_held_out_page():
    with pytest.raises(PageRefused, match="not a development issue"):
        pages.resolve("1940-01_p007")


def test_each_family_draws_its_pages_with_a_fresh_seeded_generator():
    classes = {f"1940-{m:02d}_p{p:03d}": RAILROAD for m in range(1, 13) for p in (5, 9)}
    classes |= {"1985-06_p090": "total_claims_by_country", "1940-01_p001": UNSUPPORTED}
    chosen = real_test.sample(classes, 12)
    railroad = sorted(r for r, f in classes.items() if f == RAILROAD)
    assert chosen[RAILROAD] == sorted(random.Random(4004).sample(railroad, 12))
    assert chosen["total_claims_by_country"] == ["1985-06_p090"]  # all, where 12 or fewer
    assert chosen["short_term_foreign_liabilities_as"] == []
    assert real_test.sample(classes, 12) == chosen
    assert UNSUPPORTED not in chosen


def test_the_caps_are_recorded_once_and_read_back_on_every_start(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    lines = [{"backend": "meta", "cost_usd": 4.5}, {"backend": "baseten", "cost_usd": 21.0}]
    ledger.write_text("".join(json.dumps(line) + "\n" for line in lines))
    record = real_test.caps(tmp_path / "out", 40.0, ledger)
    assert (record["meta"], record["baseten"], record["allowance"]) == (44.5, 21.0, 40.0)
    ledger.write_text(ledger.read_text() + json.dumps({"backend": "meta", "cost_usd": 9}) + "\n")
    assert real_test.caps(tmp_path / "out", 1.0, ledger) == record
    monkeypatch.setenv("BUDGET_CAP_USD", "120")
    monkeypatch.setenv("BASETEN_CAP_USD", "80")
    real_test.set_caps(record)
    assert (os.environ["BUDGET_CAP_USD"], os.environ["BASETEN_CAP_USD"]) == ("44.5", "21.0")


def test_ocr_layers_are_read_one_at_a_time_across_workers(monkeypatch):
    inside, most = [0], [0]

    def layer(path, number, image):
        inside[0] += 1
        most[0] = max(most[0], inside[0])
        time.sleep(0.01)
        inside[0] -= 1
        return ()

    monkeypatch.setattr(real_test.ocr, "layer", layer)
    refs = [f"1940-01_p{n:03d}" for n in range(1, 9)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda ref: real_test.words(Page(ref, ref, Path("x.jpg"))), refs))
    assert most[0] == 1


def test_the_config_enables_the_five_frozen_templates_with_the_frozen_roles():
    doc_types = real_test._types(ROOT / real_test.CONFIG)
    prereg = (ROOT / "PREREGISTRATION_REAL.md").read_text(encoding="utf-8")
    table = dict(re.findall(r"\| `(\w+)` \| [^|]+ \| ([0-9a-f]{64}) \|", prereg))
    assert recorded(doc_types) == table
    with (ROOT / real_test.CONFIG).open("rb") as f:
        ours = tomllib.load(f)
    with (ROOT / "config" / "templates.toml").open("rb") as f:
        frozen = tomllib.load(f)
    for role in ("extractor", "rereader"):
        assert ours["roles"][role] == frozen["roles"][role]
    assert ours["roles"]["segmenter"]["model_id"] == "sam-3.1"
    assert {spec["backend"] for spec in ours["roles"].values()} == {"meta"}


# --- The stages, on drawn pages -------------------------------------------------------------------


@pytest.fixture
def drawn(tmp_path, monkeypatch) -> dict[str, Page]:
    """Six pages drawn in tmp_path; any other reference is refused."""
    found = {}
    for n in range(6):
        ref = f"1939-0{n + 1}_p010"
        path = tmp_path / "pages" / f"{ref}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1000, 1000), "white")
        canvas = ImageDraw.Draw(image)
        for r in range(1, 18):  # each page its own ink: a dark mark in every cell's box
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


def test_the_sweep_asks_each_page_once_and_a_failed_page_again(tmp_path, drawn):
    doc_types = real_test._types(ROOT / real_test.CONFIG)
    refs = sorted(drawn)
    failing = {refs[1]}
    image_of = {page.path.read_bytes(): ref for ref, page in drawn.items()}

    def respond(request) -> str:
        assert request.prompt.startswith("Which kind of document")
        ref = image_of[request.images[0]]
        if ref in failing:
            raise TimeoutError("slow")
        return json.dumps({"doc_type": RAILROAD if ref < refs[3] else UNSUPPORTED})

    llm = MockLLM(respond)
    out = tmp_path / "out"
    first = real_test.sweep(refs, "development", out, llm, doc_types, workers=3)
    assert first["failed"] == [refs[1]] and len(llm.calls) == 6
    failing.clear()
    second = real_test.sweep(refs, "development", out, llm, doc_types, workers=3)
    assert len(llm.calls) == 7  # only the failed page was asked again
    assert second["failed"] == [] and second["by_family"][RAILROAD] == 3
    assert second["set_aside"] == 3
    assert second["by_era"] == {"1939-1942": {RAILROAD: 3, UNSUPPORTED: 3}}
    with pytest.raises(PageRefused):
        real_test.sweep(["1940-01_p001"], "development", out, llm, doc_types)


def _railroad_answer(request) -> str:
    """Every row: a period, three ones and their total of three, each in its own box."""
    columns = ("period", "taxes", "admin", "to_retirement", "to_unemployment", "total_exp")
    texts = ("1940", "2.0", "1.0", "1.0", "1.0", "3.0")
    rows = {
        f"{r:02d}": {
            c: {"value": t, "box": [100 + 140 * i, 40 + 50 * r, 220 + 140 * i, 80 + 50 * r]}
            for i, (c, t) in enumerate(zip(columns, texts, strict=True))
        }
        for r in range(1, 18)
    }
    return json.dumps({"rows": rows})


def test_the_deep_check_reads_boxes_and_verifies_its_sample_and_resumes_without_rereading(
    tmp_path, drawn
):
    doc_types = real_test._types(ROOT / real_test.CONFIG)
    out = tmp_path / "out"
    out.mkdir()
    sweep = [{"page": ref, "classified_as": RAILROAD} for ref in sorted(drawn)[:3]]
    (out / "sweep.jsonl").write_text("".join(json.dumps(line) + "\n" for line in sweep))
    extractor = MockLLM(_railroad_answer)
    rereader = MockLLM(lambda request: json.dumps({"value": "1.0"}))
    segmenter = MockSegmenter()
    roles = {"extractor": extractor, "rereader": rereader, "segmenter": segmenter}

    verdicts, record = real_test.deep(
        out, "development", roles, doc_types, per_family=2, workers=2, layer_of=lambda page: ()
    )
    chosen = record["sample"][RAILROAD]
    assert len(chosen) == 2 and json.loads((out / "sample.json").read_text())["seed"] == 4004
    assert len(extractor.calls) == 2 and len(segmenter.calls) == 2 * 2  # stamp and stain
    assert record["calls"]["second_looks"] == 0
    assert len(verdicts) == 2 * 17 * 6 == sum(record["box_sources"].values())
    by_column = {}
    for v in verdicts:
        by_column.setdefault(v.field_id.rsplit(":", 1)[-1], set()).add(v.status)
    assert by_column["admin"] == {"accepted"}  # both reads 1.0, and the identity holds
    assert by_column["total_exp"] == {"review"}  # the re-read disagrees
    predictions = (out / "predictions.jsonl").read_text().splitlines()
    assert sorted(json.loads(line)["page_id"] for line in predictions) == chosen

    again, _ = real_test.deep(
        out, "development", roles, doc_types, per_family=1, workers=2, layer_of=lambda page: ()
    )
    assert len(extractor.calls) == 2  # every page read already: nothing read twice
    assert [v.model_dump() for v in again] == [v.model_dump() for v in verdicts]
