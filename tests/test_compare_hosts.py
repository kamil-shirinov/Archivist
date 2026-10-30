"""The two-host comparison (P30): its sampling, logs, speed and agreement figures, no model."""

import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from archivist.eval import compare_hosts
from archivist.eval.compare_hosts import (
    CallLog,
    TimedLLM,
    _percentile,
    _RepairCounter,
    accuracy,
    agreement,
    build_report,
    field_rows,
    sample,
    speed_and_cost,
    table,
)
from archivist.models.base import LLMRequest, LLMResponse, Usage
from archivist.pipeline import extract
from archivist.schema import BBox, ExtractedValue, FieldGT, PageExtraction, PageGT

DEBIT, CREDIT, DATE, WORDS = (f"L:card-01-1:03:{kind}" for kind in ("debit", "credit", "date", "desc"))
PRINTED = {DEBIT: "1,000.00", CREDIT: "25.50", DATE: "03/04/1999", WORDS: "RENT"}
IMAGE = b"\xff\xd8\xff\xe0 page one"


def gt(page_id: str = "card-01-1", severity: int = 1) -> PageGT:
    return PageGT(
        page_id=page_id,
        doc_type="ledger",
        image_path=f"images/{page_id}.jpg",
        width=1000,
        height=1400,
        severity=severity,
        fields=[
            FieldGT(field_id=fid.replace("card-01-1", page_id), printed=text,
                    bbox=BBox(x0=0, y0=10 * i, x1=100, y1=10 * i + 10))
            for i, (fid, text) in enumerate(PRINTED.items())
        ],
        artefacts=[],
        source_errors=[],
    )


def read(page_id: str, values: dict[str, str | None], *, abstain=(), doc_type="ledger_card"):
    return PageExtraction(
        page_id=page_id,
        doc_type=doc_type,
        values=[
            ExtractedValue(
                field_id=fid.replace("card-01-1", page_id),
                value=value,
                citation=None,
                abstained=fid in abstain,
            )
            for fid, value in values.items()
        ],
    )


def response(cached=False, cost=0.01) -> LLMResponse:
    return LLMResponse(
        text="{}", usage=Usage(100, 40, cost), backend="fireworks", model_id="m", cached=cached
    )


# --- the sample ----------------------------------------------------------------------------------


def test_the_sample_is_every_nth_page_of_the_sorted_split_starting_with_the_first():
    pages = [Path(f"p{i}.jpg") for i in (4, 0, 6, 1, 5, 2, 3)]

    assert sample(pages, 3) == [Path("p0.jpg"), Path("p3.jpg"), Path("p6.jpg")]
    assert sample(pages, 1) == sorted(pages)
    with pytest.raises(ValueError, match="at least 1"):
        sample(pages, 0)


def test_the_percentile_is_the_nearest_rank_and_none_without_values():
    values = [5.0, 1.0, 3.0, 2.0, 4.0, 10.0, 9.0, 8.0, 7.0, 6.0]
    assert _percentile(values, 90) == 9.0
    assert _percentile(values, 100) == 10.0
    assert _percentile([2.0], 90) == 2.0
    assert _percentile([], 90) is None


# --- logging the calls ---------------------------------------------------------------------------


class FakeLLM:
    name, model_id = "fireworks", "m"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)

    def complete(self, request):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_every_call_is_logged_with_its_page_kind_and_whether_it_was_a_second_ask(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    page_of = {hashlib.sha256(IMAGE).hexdigest(): "card-01-1"}
    llm = TimedLLM(FakeLLM(response(), response(cached=True), RuntimeError("boom")), log, page_of)
    classify = LLMRequest("extractor", "which?", (IMAGE,), max_output_tokens=extract.CLASSIFY_TOKENS)
    values = LLMRequest("extractor", "read" + extract.RETRY_NOTE, (IMAGE,), max_output_tokens=16_000)

    llm.complete(classify)
    llm.complete(values)
    with pytest.raises(RuntimeError, match="boom"):
        llm.complete(values)

    first, second, third = log.read()
    assert (first["page_id"], first["kind"], first["second_ask"]) == ("card-01-1", "classify", False)
    assert (second["kind"], second["second_ask"], second["cached"]) == ("read", True, True)
    assert (first["input_tokens"], first["output_tokens"], first["cost_usd"]) == (100, 40, 0.01)
    assert third["error"] == "RuntimeError" and "cost_usd" not in third
    assert all(e["event"] == "call" and e["host"] == "fireworks" and e["elapsed_s"] >= 0
               for e in (first, second, third))
    assert llm.name == "fireworks" and llm.model_id == "m"


def test_a_page_the_split_does_not_know_is_logged_by_its_hash(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    TimedLLM(FakeLLM(response()), log, {}).complete(LLMRequest("extractor", "x", (IMAGE,)))

    (entry,) = log.read()
    assert entry["page_id"] == hashlib.sha256(IMAGE).hexdigest()[:12]


def test_a_retry_and_a_closing_repair_are_events_of_the_host_s_log(tmp_path):
    log = CallLog(tmp_path / "calls.jsonl")
    slept = []
    backend = SimpleNamespace(_sleep=slept.append)

    compare_hosts._count_retries(backend, log, "baseten")
    backend._sleep(1.5)
    handler = _RepairCounter(log, "baseten")
    logger = logging.getLogger("test.repairs")
    logger.addHandler(handler)
    logger.warning("1 bracket(s) left open were closed, after: %s", "x")
    logger.warning("something else")
    logger.removeHandler(handler)

    assert slept == [1.5]  # the real sleep still happens
    assert [(e["event"], e["host"]) for e in log.read()] == [
        ("retry", "baseten"),
        ("repair", "baseten"),
    ]


# --- speed and cost ------------------------------------------------------------------------------


def _call(page, elapsed, kind="read", **kwargs):
    return {
        "event": "call", "host": "h", "page_id": page, "kind": kind, "second_ask": False,
        "elapsed_s": elapsed, "cached": False, "input_tokens": 100, "output_tokens": 40,
        "cost_usd": 0.01, **kwargs,
    }  # fmt: skip


def test_speed_and_cost_leave_cached_calls_out_and_count_failures_retries_and_repairs():
    events = [
        _call("a", 2.0, "classify"),
        _call("a", 10.0),
        _call("b", 4.0, "classify"),
        _call("b", 6.0, second_ask=True),
        _call("b", 1.0, error="APIConnectionError"),
        _call("b", 0.0, cached=True),
        {"event": "retry", "host": "h", "waited_s": 1.0},
        {"event": "repair", "host": "h"},
        {"event": "session", "host": "h", "wall_s": 30.0, "pages_read": 2, "ledger_cost_usd": 0.05},
    ]

    figures = speed_and_cost(events, pages_asked=3, doc_type_of={"a": "ledger", "b": "memo"})

    assert figures["calls"] == 5 and figures["calls_failed"] == {"APIConnectionError": 1}
    assert (figures["second_asks"], figures["retries"], figures["closing_repairs"]) == (1, 1, 1)
    assert figures["call_seconds"] == {"n": 4, "median": 5.0, "p90": 10.0, "max": 10.0, "total": 22.0}
    assert figures["read_call_seconds"]["n"] == 2 and figures["classify_call_seconds"]["n"] == 2
    # a page's time is every call on it, the failed one too
    assert figures["page_seconds"] == {"n": 2, "median": 11.5, "p90": 12.0, "max": 12.0, "total": 23.0}
    assert (figures["input_tokens"], figures["output_tokens"]) == (400, 160)
    assert figures["wall_seconds"] == 30.0 and figures["pages_read_per_minute"] == 4.0
    assert figures["cost_usd"] == 0.05 and figures["cost_usd_per_page"] == 0.025
    assert figures["pages_asked"] == 3
    # reads by the kind of page: the ledger page's one read took 10 s for 40 tokens, the memo's 6 s
    assert figures["by_doc_type"]["ledger"]["read_call_seconds"]["median"] == 10.0
    assert figures["by_doc_type"]["ledger"]["read_tokens_per_second_median"] == 4.0
    assert figures["by_doc_type"]["memo"]["read_output_tokens_median"] == 40
    assert speed_and_cost(events, pages_asked=3)["by_doc_type"] == {}


def test_speed_and_cost_of_a_host_that_read_nothing_have_no_rates():
    figures = speed_and_cost([], pages_asked=16)

    assert figures["pages_read_per_minute"] is None and figures["cost_usd_per_page"] is None
    assert figures["call_seconds"]["median"] is None and figures["calls"] == 0


# --- agreement -----------------------------------------------------------------------------------


def test_fields_are_the_same_when_the_scorers_normalisation_says_so():
    page = gt()
    base = {"card-01-1": read("card-01-1", {DEBIT: "1000.00", CREDIT: "25.50", DATE: "3/4/1999", WORDS: "rent"})}
    other = {"card-01-1": read("card-01-1", {DEBIT: "1,000.00", CREDIT: "25.50", DATE: "03.04.1999", WORDS: "Rent"})}

    rows = field_rows([page], base, other)

    assert [r["same"] for r in rows] == [True, True, True, True]
    assert all(r["first_outcome"] == r["second_outcome"] == "correct" for r in rows)


def test_who_is_right_when_the_hosts_differ_and_what_none_means():
    page = gt()
    base = {"card-01-1": read("card-01-1", {DEBIT: "1,000.00", CREDIT: "99.00", DATE: "03/04/1999"}, abstain=(DATE,))}
    other = {"card-01-1": read("card-01-1", {DEBIT: "1,000.00", CREDIT: "25.50", DATE: "03/04/1999", WORDS: "RENT"})}

    rows = field_rows([page], base, other)
    by_kind = {r["field_id"].rsplit(":", 1)[1]: r for r in rows}

    assert by_kind["debit"]["same"] is True
    assert by_kind["credit"]["same"] is False
    assert (by_kind["credit"]["first_outcome"], by_kind["credit"]["second_outcome"]) == ("misread", "correct")
    assert by_kind["date"]["first"] is None and by_kind["date"]["same"] is False  # abstained vs a value
    assert by_kind["desc"]["first"] is None and by_kind["desc"]["second"] == "RENT"  # absent vs a value

    block = agreement(rows, base, other)
    assert (block["fields"], block["same_value"], block["differ"]) == (4, 1, 3)
    assert block["differ_only_second_right"] == 3 and block["differ_only_first_right"] == 0
    assert block["same_and_right"] == 1 and block["same_and_wrong"] == 0


def test_nothing_from_both_hosts_counts_as_the_same_and_a_page_one_host_failed_is_skipped():
    pages = [gt("card-01-1"), gt("card-02-1")]
    base = {"card-01-1": read("card-01-1", {}), "card-02-1": read("card-02-1", {DEBIT: "1,000.00"})}
    other = {"card-01-1": read("card-01-1", {})}  # card-02-1 failed on this host

    rows = field_rows(pages, base, other)

    assert {r["page_id"] for r in rows} == {"card-01-1"}
    assert all(r["same"] and r["first"] is None and r["second"] is None for r in rows)
    assert agreement(rows, base, other)["pages_in_both"] == 1


def test_the_interval_is_over_pages_repeatable_and_absent_for_one_page():
    pages = [gt(f"card-0{n}-1") for n in range(1, 7)]
    good = {p.page_id: read(p.page_id, {DEBIT: "1,000.00"}) for p in pages}
    bad = {p.page_id: read(p.page_id, {DEBIT: "9.00" if n % 2 else "1,000.00"}) for n, p in enumerate(pages)}
    rows = field_rows(pages, good, bad)

    block = agreement(rows, good, bad)
    again = agreement(rows, good, bad)

    low, high = block["same_value_rate_ci95"]
    assert 0 <= low <= block["same_value_rate"] <= high <= 1
    assert block["same_value_rate_ci95"] == again["same_value_rate_ci95"]
    one = agreement(field_rows(pages[:1], good, good), good, good)
    assert one["same_value_rate"] == 1.0 and one["same_value_rate_ci95"] is None


def test_accuracy_counts_a_page_the_host_did_not_read_as_omitted():
    pages = [gt("card-01-1"), gt("card-02-1")]
    reads = {"card-01-1": read("card-01-1", {DEBIT: "1,000.00", CREDIT: "25.50", DATE: "03/04/1999", WORDS: "RENT"})}

    figures = accuracy(pages, reads)

    assert (figures["pages"], figures["pages_read"], figures["fields"]) == (2, 1, 8)
    assert figures["counts"]["correct"] == 4 and figures["counts"]["omitted"] == 4
    assert figures["field_accuracy"] == 0.5


# --- the report ----------------------------------------------------------------------------------


def _report(noise=None):
    pages = [gt("card-01-1"), gt("card-02-1")]
    reads = {p.page_id: read(p.page_id, {DEBIT: "1,000.00", CREDIT: "25.50"}) for p in pages}
    other = {p.page_id: read(p.page_id, {DEBIT: "1,000.00", CREDIT: "26.50"}) for p in pages}
    session = {"event": "session", "wall_s": 20.0, "pages_read": 2, "ledger_cost_usd": 0.04}
    events = {
        host: [_call("card-01-1", 3.0), _call("card-02-1", 5.0), {**session, "host": host}]
        for host in compare_hosts.HOSTS
    }
    predictions = {"baseten": reads, "fireworks": other}
    return build_report(pages, predictions, events, noise)


def test_the_report_names_both_hosts_the_agreement_and_every_disagreement():
    report = _report()

    assert list(report["hosts"]) == ["baseten", "fireworks"]
    assert report["hosts"]["baseten"]["config"] == "config/models_open.toml"
    assert report["hosts"]["fireworks"]["config"] == "config/models_fireworks.toml"
    # per page: the debit is the same, the credit differs, and the date and words, which neither
    # host gave, count as the same
    assert report["agreement"]["fields"] == 8 and report["agreement"]["same_value"] == 6
    assert [d["field_id"].rsplit(":", 1)[1] for d in report["disagreements"]] == ["credit", "credit"]
    assert report["disagreements"][0]["baseten"] == "25.50"
    assert report["disagreements"][0]["fireworks"] == "26.50"
    assert report["disagreements"][0]["fireworks_outcome"] == "misread"
    assert "noise_floor" not in report and report["caveats"]
    json.dumps(report)  # it is what results/hosts_compare.json holds


def test_the_baseten_noise_floor_is_baseten_against_its_own_earlier_reads():
    own = {p: read(p, {DEBIT: "1,000.00", CREDIT: "25.50"}) for p in ("card-01-1", "card-02-1")}

    report = _report(noise=own)

    assert report["noise_floor"]["same_value"] == 8  # identical reads
    assert "baseline-dev-open" in report["noise_floor"]["what"]


def test_an_undefined_rate_is_a_dash_in_the_markdown_never_a_zero():
    text = table(_report(noise={}))  # no page of Baseten's earlier run to compare with

    assert "0 pages in both, 0 fields, 0 the same value = — (95% — to —)" in text


def test_the_markdown_has_a_column_for_each_host_and_the_agreement_blocks():
    text = table(_report(noise={}))

    assert "| | baseten | fireworks |" in text
    assert "## Host against host" in text and "## Baseten against its own P13 reads" in text
    assert "| pages read / asked | 2 / 2 | 2 / 2 |" in text
    assert "| ledger read call seconds, median / max; tokens a second | 4.0 / 5.0; 10.7 |" in text
    assert "| cost, total / per page | $0.0400 / $0.0200 | $0.0400 / $0.0200 |" in text
    assert text.count("## Caveats") == 1


# --- collecting ----------------------------------------------------------------------------------


def test_collect_reads_through_the_timed_role_and_logs_one_session(tmp_path, monkeypatch):
    spent = iter([1.0, 1.25])  # the guard's spend for the host before and after
    guard = SimpleNamespace(spent=lambda host: next(spent))
    backend = SimpleNamespace(_sleep=lambda seconds: None)
    role = SimpleNamespace(
        name="fireworks", model_id="m", inner=SimpleNamespace(guard=guard, inner=backend)
    )
    seen = {}

    def run(images, run_dir, roles, **kwargs):
        seen.update(images=images, run_dir=run_dir, roles=roles, **kwargs)
        run_dir.mkdir(parents=True)
        page = read("card-01-1", {DEBIT: "1,000.00"})
        (run_dir / "predictions.jsonl").write_text(page.model_dump_json() + "\n")
        backend._sleep(2.0)
        return {"counts": {}}

    monkeypatch.setattr(compare_hosts, "load_roles", lambda config, cache_dir: {"extractor": role})
    monkeypatch.setattr(compare_hosts.extract, "run", run)
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "card-01-1.jpg").write_bytes(IMAGE)
    config = Path(__file__).resolve().parents[1] / "config" / "models_fireworks.toml"

    compare_hosts.collect("fireworks", config, pages, 3, scratch=tmp_path / "scratch")

    assert isinstance(seen["roles"]["extractor"], TimedLLM)
    assert seen["workers"] == 3 and seen["run_dir"] == tmp_path / "scratch" / "runs" / "fireworks"
    events = CallLog(tmp_path / "scratch" / "calls_fireworks.jsonl").read()
    assert [e["event"] for e in events] == ["retry", "session"]
    session = events[1]
    assert (session["pages_read"], session["workers"]) == (1, 3)
    assert session["ledger_cost_usd"] == pytest.approx(0.25)
