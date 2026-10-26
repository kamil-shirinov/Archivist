"""The single-pass extractor, the thread-safe spend cap and the evaluation of a run, all offline."""

import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from archivist.doctypes.ledger import COLUMNS, HEADER_BOTTOM, HEADER_TOP, LINES, MEMO_FIELDS
from archivist.eval import run_eval
from archivist.models.base import LLMRequest
from archivist.models.budget import Budget, BudgetExceeded, BudgetGuard, Price
from archivist.models.cache import Cache
from archivist.models.mock import MockLLM
from archivist.pipeline.extract import (
    EXTRACT_TOKENS,
    RETRY_NOTE,
    ExtractionFailed,
    PageExtraction,
    classify,
    extract_page,
    load_predictions,
    run,
)
from archivist.schema import BBox, Citation, ExtractedValue, FieldGT, PageGT

FREE = Price(input_per_mtok=0.0, output_per_mtok=0.0)
CELL = {"value": "1.00", "box": [100, 100, 200, 200]}
LEDGER = {
    "header": {name: CELL for name in HEADER_TOP + HEADER_BOTTOM},
    "lines": {f"{line:02d}": {column: CELL for column in COLUMNS} for line in LINES},
}
MEMO = {"fields": {name: CELL for name in MEMO_FIELDS}}
CONFIG = {"extractor": {"backend": "mock", "model_id": "mock-llm"}}


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    """Default relative paths (cache/, results/) land in a scratch cwd that must stay empty."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    yield
    assert not any(cwd.iterdir()), "a test wrote through a default path instead of tmp_path"


def _jpeg(shade: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 100), (shade, shade, shade)).save(buffer, format="JPEG")
    return buffer.getvalue()


class Pages:
    """A folder of tiny scans, each with the type a mock classifier will call it."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.kinds: dict[bytes, str] = {}

    def add(self, page_id: str, kind: str) -> Path:
        image = _jpeg(len(self.kinds) * 20 + 10)
        self.kinds[image] = kind
        path = self.folder / f"{page_id}.jpg"
        path.write_bytes(image)
        return path


def responder(pages: Pages, extraction: dict | None = None):
    """A canned model: the page's type when classifying, a full answer when extracting."""

    def respond(request: LLMRequest) -> str:
        properties = request.json_schema["properties"]
        if "doc_type" in properties:
            return json.dumps({"doc_type": pages.kinds[request.images[0]]})
        if extraction is not None:
            return json.dumps(extraction)
        return json.dumps(LEDGER if "lines" in properties else MEMO)

    return respond


def roles_for(llm: MockLLM, tmp_path: Path, cap: float = 10.0) -> tuple[dict, BudgetGuard]:
    guard = BudgetGuard(cap, tmp_path / "ledger.jsonl")
    return {"extractor": Cache(Budget(llm, guard, FREE), tmp_path / "cache")}, guard


# --- extract_page ------------------------------------------------------------------------------


def test_a_ledger_card_is_classified_then_extracted_in_full(tmp_path):
    pages = Pages(tmp_path / "images")
    path = pages.add("scan_7", "ledger_card")
    llm = MockLLM(responder(pages))
    roles, _ = roles_for(llm, tmp_path)

    page = extract_page(path, roles)

    assert (page.page_id, page.doc_type) == ("scan_7", "ledger_card")
    assert len(page.values) == 95
    assert page.values[0].field_id == "L:scan_7:hdr:account_no"
    assert page.values[0].citation == Citation(
        page_id="scan_7", bbox=BBox(x0=20, y0=10, x1=40, y1=20)
    )
    classify_call, extract_call = llm.calls
    assert "doc_type" in classify_call.json_schema["properties"]
    assert extract_call.max_output_tokens == EXTRACT_TOKENS == 16_000
    assert extract_call.images == (path.read_bytes(),)


def test_the_classifier_is_offered_every_type_and_unsupported(tmp_path):
    pages = Pages(tmp_path / "images")
    pages.add("p", "payment_memo")
    llm = MockLLM(responder(pages))

    assert classify(next(iter(pages.kinds)), llm) == "payment_memo"
    request = llm.calls[0]
    assert request.json_schema["properties"]["doc_type"]["enum"] == [
        "ledger_card",
        "payment_memo",
        "unsupported",
    ]
    assert "ledger_card:" in request.prompt and "payment_memo:" in request.prompt


def test_an_unsupported_page_yields_no_values_and_no_extraction_call(tmp_path):
    pages = Pages(tmp_path / "images")
    path = pages.add("photo", "unsupported")
    llm = MockLLM(responder(pages))
    roles, _ = roles_for(llm, tmp_path)

    page = extract_page(path, roles)

    assert (page.doc_type, page.values) == ("unsupported", [])
    assert len(llm.calls) == 1


def test_a_truncated_answer_is_asked_again_once_with_a_note(tmp_path):
    pages = Pages(tmp_path / "images")
    path = pages.add("m1", "payment_memo")
    full = responder(pages)

    def respond(request: LLMRequest) -> str:
        text = full(request)
        if "fields" in request.json_schema["properties"] and RETRY_NOTE not in request.prompt:
            return text[: len(text) // 2]  # cut off mid-answer
        return text

    llm = MockLLM(respond)
    roles, _ = roles_for(llm, tmp_path)

    page = extract_page(path, roles)

    assert len(page.values) == 7
    assert len(llm.calls) == 3
    assert llm.calls[2].prompt == llm.calls[1].prompt + RETRY_NOTE


@pytest.mark.parametrize(
    "answer", ["{\"fields\": {", json.dumps({"fields": {"memo_no": CELL}}), "[]"]
)
def test_a_page_that_fails_twice_raises_instead_of_returning_part(tmp_path, answer):
    pages = Pages(tmp_path / "images")
    path = pages.add("m1", "payment_memo")
    base = responder(pages)

    def respond(request: LLMRequest) -> str:
        return base(request) if "doc_type" in request.json_schema["properties"] else answer

    llm = MockLLM(respond)
    roles, _ = roles_for(llm, tmp_path)

    with pytest.raises(ExtractionFailed, match="payment_memo extraction"):
        extract_page(path, roles)
    assert len(llm.calls) == 3


def test_a_classification_outside_the_registry_fails(tmp_path):
    pages = Pages(tmp_path / "images")
    path = pages.add("x", "bank_statement")
    llm = MockLLM(responder(pages))
    roles, _ = roles_for(llm, tmp_path)

    with pytest.raises(ExtractionFailed, match="classification"):
        extract_page(path, roles)


# --- run ---------------------------------------------------------------------------------------


def test_run_writes_predictions_and_a_run_record(tmp_path):
    pages = Pages(tmp_path / "images")
    pages.add("card-1", "ledger_card")
    pages.add("memo-1", "payment_memo")
    pages.add("other", "unsupported")
    (tmp_path / "images" / "notes.txt").write_text("not a page")
    llm = MockLLM(responder(pages), cost_usd=0.01)
    roles, guard = roles_for(llm, tmp_path)

    record = run(
        tmp_path / "images", tmp_path / "runs" / "r1", roles, guard=guard, config=CONFIG, workers=4
    )

    predictions = load_predictions(tmp_path / "runs" / "r1" / "predictions.jsonl")
    counts = {p.page_id: len(p.values) for p in predictions}
    assert counts == {"card-1": 95, "memo-1": 7, "other": 0}
    assert record == json.loads((tmp_path / "runs" / "r1" / "run.json").read_text())
    assert record["config"] == CONFIG
    assert record["counts"] == {
        "pages": 3,
        "extracted": 3,
        "failed": 0,
        "by_doc_type": {"ledger_card": 1, "payment_memo": 1, "unsupported": 1},
    }
    assert record["cost_usd"] == pytest.approx(0.05)  # 3 classifications + 2 extractions
    assert record["started_at"] <= record["finished_at"]


def test_run_resumes_skipping_written_pages_and_retrying_failed_ones(tmp_path):
    pages = Pages(tmp_path / "images")
    pages.add("a", "payment_memo")
    pages.add("b", "payment_memo")
    broken = {"on": True}
    base = responder(pages)

    def respond(request: LLMRequest) -> str:
        if broken["on"] and request.images[0] == (tmp_path / "images" / "b.jpg").read_bytes():
            if "fields" in request.json_schema["properties"]:
                raise ConnectionError("network down")  # transient: nothing is cached
        return base(request)

    llm = MockLLM(respond, cost_usd=0.01)
    roles, guard = roles_for(llm, tmp_path)
    run_dir = tmp_path / "runs" / "r1"

    first = run(tmp_path / "images", run_dir, roles, guard=guard, config=CONFIG)
    assert first["counts"]["extracted"] == 1
    assert first["failed_pages"] == {"b": "ConnectionError: network down"}
    assert [p.page_id for p in load_predictions(run_dir / "predictions.jsonl")] == ["a"]

    broken["on"] = False
    pages.add("c", "payment_memo")
    calls_before = len(llm.calls)
    second = run(tmp_path / "images", run_dir, roles, guard=guard, config=CONFIG, workers=2)

    asked = {request.images[0] for request in llm.calls[calls_before:]}
    assert (tmp_path / "images" / "a.jpg").read_bytes() not in asked
    assert sorted(p.page_id for p in load_predictions(run_dir / "predictions.jsonl")) == [
        "a",
        "b",
        "c",
    ]
    assert (second["counts"]["extracted"], second["failed_pages"]) == (3, {})
    assert len(second["sessions"]) == 2
    assert second["started_at"] == first["started_at"]
    # first: a classified and extracted, b classified; then b's classification replays from the
    # cache for free, b is extracted and c is classified and extracted.
    assert [s["cost_usd"] for s in second["sessions"]] == pytest.approx([0.03, 0.03])
    assert second["cost_usd"] == pytest.approx(0.06)


def test_run_stops_when_the_budget_is_exhausted(tmp_path):
    pages = Pages(tmp_path / "images")
    for i in range(3):
        pages.add(f"m{i}", "payment_memo")
    llm = MockLLM(responder(pages), cost_usd=0.01)
    guard = BudgetGuard(0.0, tmp_path / "ledger.jsonl")
    roles = {"extractor": Cache(Budget(llm, guard, Price(0.0, 1.0)), tmp_path / "cache")}

    with pytest.raises(BudgetExceeded):
        run(tmp_path / "images", tmp_path / "runs" / "r1", roles, guard=guard, config=CONFIG)
    record = json.loads((tmp_path / "runs" / "r1" / "run.json").read_text())
    assert record["sessions"][-1]["aborted"].startswith("BudgetExceeded")
    assert llm.calls == []


def test_the_pipeline_never_imports_the_generator():
    code = (
        "import sys, archivist.pipeline.extract, archivist.doctypes; "
        "print([m for m in sys.modules if m.startswith('archivist.synth')])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


# --- spend cap under parallel workers ----------------------------------------------------------


def test_the_cap_holds_under_four_parallel_workers(tmp_path):
    # Each call is projected at $0.40 (4000 output tokens at $100/M) and costs $0.40; cap $1.00.
    guard = BudgetGuard(1.00, tmp_path / "ledger.jsonl")
    backend = MockLLM(lambda request: time.sleep(0.2) or "ok", cost_usd=0.40)
    budget = Budget(backend, guard, Price(input_per_mtok=0.0, output_per_mtok=100.0))
    start = threading.Barrier(4)
    outcomes: list[str] = []

    def call(i: int) -> None:
        start.wait()
        try:
            request = LLMRequest(role="extractor", prompt=f"read {i}", max_output_tokens=4000)
            budget.complete(request)
            outcomes.append("ok")
        except BudgetExceeded:
            outcomes.append("refused")

    threads = [threading.Thread(target=call, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["ok", "ok", "refused", "refused"]
    assert guard.spent() == pytest.approx(0.80)
    assert guard.spent() <= guard.cap_usd


def test_a_failed_call_releases_its_reservation(tmp_path):
    guard = BudgetGuard(1.00, tmp_path / "ledger.jsonl")

    def fail(request: LLMRequest) -> str:
        raise ConnectionError("network down")

    price = Price(input_per_mtok=0.0, output_per_mtok=100.0)
    request = LLMRequest(role="extractor", prompt="read", max_output_tokens=4000)
    for _ in range(3):  # three reservations of $0.40 would exceed $1.00 if never released
        with pytest.raises(ConnectionError):
            Budget(MockLLM(fail), guard, price).complete(request)
    Budget(MockLLM(lambda r: "ok"), guard, price).complete(request)
    assert guard.spent() == 0.0


# --- evaluation of a canned run ----------------------------------------------------------------


def _gt(page_id: str, doc_type: str, severity: int, fields: list[tuple[str, str]]) -> PageGT:
    return PageGT(
        page_id=page_id,
        doc_type=doc_type,
        image_path=f"images/{page_id}.jpg",
        width=1000,
        height=1000,
        severity=severity,
        fields=[
            FieldGT(field_id=f, printed=p, bbox=BBox(x0=100, y0=100, x1=200, y1=150))
            for f, p in fields
        ],
        artefacts=[],
        source_errors=[],
    )


def _value(field_id: str, value: str | None, page_id: str, box: tuple[int, ...]) -> ExtractedValue:
    citation = Citation(page_id=page_id, bbox=BBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3]))
    return ExtractedValue(field_id=field_id, value=value, citation=citation)


@pytest.fixture
def canned_run(tmp_path):
    gt_dir = tmp_path / "data" / "dev" / "gt"
    gt_dir.mkdir(parents=True)
    pages = [
        _gt("p1", "memo", 0, [("M:p1:amount", "10.00"), ("M:p1:date", "01/02/85")]),
        _gt("p2", "ledger", 1, [("L:p2:01:debit", "5.00"), ("L:p2:01:credit", "")]),
        _gt("p3", "memo", 1, [("M:p3:amount", "1.00")]),  # failed: no prediction
    ]
    for page in pages:
        (gt_dir / f"{page.page_id}.json").write_text(page.model_dump_json())
    (gt_dir / "world.json").write_text("{}")  # the world file is not a page

    inside, outside = (120, 110, 180, 140), (500, 500, 600, 600)
    predictions = [
        PageExtraction(
            page_id="p1",
            doc_type="payment_memo",
            values=[
                _value("M:p1:amount", "£10.00", "p1", inside),  # correct, cited on target
                _value("M:p1:date", "01/03/85", "p1", inside),  # misread
            ],
        ),
        PageExtraction(
            page_id="p2",
            doc_type="ledger_card",
            values=[
                _value("L:p2:01:debit", "5.00", "p2", outside),  # correct, cited off target
                _value("L:p2:01:credit", None, "p2", inside),  # abstained
            ],
        ),
    ]
    run_dir = tmp_path / "results" / "runs" / "canned"
    run_dir.mkdir(parents=True)
    (run_dir / "predictions.jsonl").write_text(
        "".join(p.model_dump_json() + "\n" for p in predictions)
    )
    (run_dir / "run.json").write_text(json.dumps({"config": CONFIG}))
    return run_dir, gt_dir


def test_run_eval_scores_a_canned_run(canned_run):
    run_dir, gt_dir = canned_run
    metrics = run_eval.evaluate(run_dir, gt_dir)

    overall = metrics["overall"]
    assert overall["counts"] == {
        "correct": 2,
        "misread": 1,
        "hallucinated": 0,
        "omitted": 1,
        "abstained": 1,
    }
    assert overall["n_pages"] == 3
    assert overall["field_accuracy"] == pytest.approx(2 / 5)
    assert overall["error_rate_accepted"] == pytest.approx(1 / 3)
    assert overall["classification_accuracy"] == pytest.approx(2 / 3)
    assert overall["citation_accuracy"] == pytest.approx(1 / 2)
    low, high = overall["field_accuracy_ci95"]
    assert 0.0 <= low <= 2 / 5 <= high <= 1.0
    low, high = overall["error_rate_ci95"]
    assert 0.0 <= low <= 1 / 3 <= high <= 1.0

    by_severity = metrics["by_severity"]
    assert by_severity[0]["field_accuracy"] == pytest.approx(1 / 2)
    assert by_severity[0]["classification_accuracy"] == 1.0
    assert by_severity[1]["field_accuracy"] == pytest.approx(1 / 3)
    assert by_severity[1]["classification_accuracy"] == pytest.approx(1 / 2)
    assert by_severity[1]["error_rate_accepted"] == 0.0
    by_doc_type = metrics["by_doc_type"]
    assert (by_doc_type["memo"]["n_pages"], by_doc_type["memo"]["n_fields"]) == (2, 3)
    assert by_doc_type["ledger"]["field_accuracy"] == pytest.approx(1 / 2)
    assert metrics["missing_pages"] == ["p3"]
    assert metrics["config"] == CONFIG


def test_run_eval_cli_writes_metrics_and_prints_the_table(canned_run, monkeypatch, capsys):
    run_dir, gt_dir = canned_run
    monkeypatch.setattr(run_eval, "RUNS_DIR", run_dir.parent)
    monkeypatch.setattr(run_eval, "DATA_ROOT", gt_dir.parents[1])

    run_eval.main(["--run", "canned", "--split", "dev"])

    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert {"overall", "by_severity", "by_doc_type"} <= set(metrics)
    assert set(metrics["by_severity"]) == {"0", "1"}
    out = capsys.readouterr().out
    assert "field accuracy [95% CI]" in out and "error rate [95% CI]" in out
    for row in ("overall", "severity 0", "severity 1", "ledger", "memo"):
        assert row in out


def test_run_eval_refuses_predictions_for_pages_it_has_no_truth_for(canned_run):
    run_dir, gt_dir = canned_run
    (gt_dir / "p2.json").unlink()
    with pytest.raises(ValueError, match="p2"):
        run_eval.evaluate(run_dir, gt_dir)
