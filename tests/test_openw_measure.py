"""P33's measurement code (openw/): recording, the shim, the decision rule, the gate, the draw.

No network and no model: a fake client stands in for the OpenAI client.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # openw/ sits beside src/

from archivist.models import LLMRequest  # noqa: E402
from archivist.models.baseten_api import BasetenLLM  # noqa: E402
from archivist.models.budget import Budget, BudgetGuard, Price  # noqa: E402
from archivist.models.cache import Cache  # noqa: E402
from openw import analyse, measure, spy  # noqa: E402

PRICE = Price(1.25, 4.25)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def completion(text, *, finish="stop", prompt=100, out=50, reasoning=30, cached=0):
    message = SimpleNamespace(content=text, reasoning_content="thinking " * 5)
    return SimpleNamespace(
        model="vendor/model-rev",
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=out,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        ),
    )


class Fake:
    """A client whose chat.completions.create plays back answers and notes what it was sent."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.sent.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def request(**kw):
    return LLMRequest(
        role="rereader",
        prompt="what is printed?",
        images=(PNG,),
        json_schema={"type": "object"},
        max_output_tokens=kw.pop("max_output_tokens", 2048),
    )


def stack(tmp_path, fake, effort="minimal", timeout_s=60.0):
    backend = spy.OpenwBaseten(
        "meta-models/muse-spark-open-1026", PRICE, reasoning_effort=effort, timeout_s=timeout_s, client=fake
    )
    backend._sleep = lambda seconds: None
    guard = BudgetGuard(1.0, tmp_path / "ledger.jsonl", caps={"baseten": 1.0})
    sink = spy.Sink(tmp_path / "calls.jsonl")
    role = Cache(Budget(backend, guard, PRICE), tmp_path / "cache", backend.settings)
    return spy.Recorder(role, host="baseten", effort=effort, sink=sink, flights=spy.Flights()), sink


def records(sink):
    return [json.loads(line) for line in sink.path.read_text().splitlines()]


def test_the_committed_backend_refuses_minimal_and_the_shim_sends_it(tmp_path):
    with pytest.raises(ValueError):
        BasetenLLM("m", PRICE, reasoning_effort="minimal")
    fake = Fake(completion('{"value": "1"}'))
    role, _ = stack(tmp_path, fake, effort="minimal", timeout_s=1200.0)
    role.complete(request())
    assert fake.sent[0]["reasoning_effort"] == "minimal"
    assert fake.sent[0]["timeout"] == 1200.0  # the committed 60 s is not what the shim sends
    assert role.name == "baseten"  # ledger lines and caps are the committed backend's


def test_a_call_is_recorded_with_what_the_backend_discards(tmp_path):
    role, sink = stack(tmp_path, Fake(completion('{"value": "1"}', cached=40)))
    with spy.tagged(step="probe", cell="c1", validate=measure.parsed):
        role.complete(request())
    [record] = records(sink)
    assert record["host"] == "baseten" and record["effort"] == "minimal"
    assert (record["step"], record["cell"]) == ("probe", "c1")
    assert record["response_model"] == "vendor/model-rev"
    assert record["finish_reason"] == "stop"
    assert (record["input_tokens"], record["cached_input_tokens"]) == (100, 40)
    assert (record["output_tokens"], record["reasoning_tokens"]) == (50, 30)
    assert record["empty"] is False and record["parse_ok"] is True
    assert record["cache_hit"] is False and record["retries"] == 0
    assert record["cost_usd"] == pytest.approx((100 * 1.25 + 50 * 4.25) / 1e6)
    assert record["in_flight_at_start"] == 1
    assert len(record["request_sha256"]) == 64


def test_a_cache_hit_is_recorded_as_one_and_not_as_a_call(tmp_path):
    role, sink = stack(tmp_path, Fake(completion('{"value": "1"}')))
    role.complete(request())
    role.complete(request())
    first, second = records(sink)
    assert first["cache_hit"] is False and second["cache_hit"] is True
    assert "finish_reason" not in second and "http_attempts" not in second


def test_an_empty_answer_that_ran_out_of_allowance_is_told_from_a_bad_one(tmp_path):
    fake = Fake(
        completion("", finish="length", out=2048, reasoning=2048),
        completion('{"value": ', finish="length", out=2048),
    )
    role, sink = stack(tmp_path, fake)
    with spy.tagged(validate=measure.parsed):
        role.complete(request())
        role.complete(request(max_output_tokens=4096))
    empty, cut = records(sink)
    assert empty["empty"] is True and empty["finish_reason"] == "length"
    assert empty["parse_ok"] is False
    assert cut["empty"] is False and cut["parse_ok"] is False and cut["answer_tail"] == '{"value": '


def test_retries_and_errors_are_recorded(tmp_path):
    overloaded = openai.RateLimitError(
        "slow down",
        response=httpx2.Response(429, request=httpx2.Request("POST", "https://x.example")),
        body=None,
    )
    role, sink = stack(tmp_path, Fake(overloaded, completion('{"value": "1"}')))
    role.complete(request())
    [record] = records(sink)
    assert record["http_attempts"] == 2 and record["retries"] == 1
    assert record["failed_attempts"][0]["status"] == 429
    bad = openai.BadRequestError(
        "reasoning_effort must be one of low, medium, high",
        response=httpx2.Response(400, request=httpx2.Request("POST", "https://x.example")),
        body=None,
    )
    role, sink = stack(tmp_path / "b", Fake(bad))
    with pytest.raises(openai.BadRequestError):
        role.complete(request())
    [record] = records(sink)
    assert record["error"]["status"] == 400 and "must be one of" in record["error"]["message"]


def test_a_closed_bracket_repair_is_counted(tmp_path):
    role, sink = stack(tmp_path, Fake(completion('{"a": {"b": 1}')))
    role.complete(request())
    [record] = records(sink)
    assert record["brackets_closed"] == 1


def calls(host, effort, tokens, finish="stop"):
    return [
        {
            "step": "probe",
            "host": host,
            "effort": effort,
            "cell": f"probe{i}",
            "reasoning_tokens": t,
            "output_tokens": t + 20,
            "finish_reason": finish,
            "empty": False,
        }
        for i, t in enumerate(tokens)
    ]


def refused(host, effort, status=400):
    return {
        "step": "probe",
        "host": host,
        "effort": effort,
        "cell": "probe0",
        "error": {"status": status, "type": "BadRequestError", "message": "no"},
    }


def test_minimal_is_honoured_only_if_it_spends_clearly_less_than_low():
    low = [700, 800, 750, 900]
    honoured = calls("a", "low", low) + calls("a", "minimal", [10, 20, 0, 30])
    silent = calls("b", "low", low) + calls("b", "minimal", [690, 810, 760, 880])
    summary = analyse.probe_summary(honoured + silent)
    assert summary["a"]["efforts"]["minimal"]["honoured"] is True
    assert summary["a"]["reread_effort"] == "minimal"
    assert summary["b"]["efforts"]["minimal"]["accepted"] is True
    assert summary["b"]["efforts"]["minimal"]["honoured"] is False
    assert summary["b"]["reread_effort"] == "low"


def test_the_reread_setting_falls_back_to_none_then_low():
    low = [700, 800, 750, 900]
    only_none = calls("a", "low", low) + calls("a", "minimal", low) + calls("a", "none", [0, 0, 5, 0])
    refused_minimal = calls("b", "low", low) + [refused("b", "minimal")]
    summary = analyse.probe_summary(only_none + refused_minimal)
    assert summary["a"]["reread_effort"] == "none"
    assert summary["b"]["efforts"]["minimal"]["accepted"] is False
    assert summary["b"]["efforts"]["minimal"]["refused_statuses"] == ["400"]
    assert summary["b"]["reread_effort"] == "low"


def test_without_reasoning_counts_the_output_tokens_decide():
    rows = [{**c, "reasoning_tokens": None} for c in calls("a", "low", [700, 800, 750, 900])]
    rows += [{**c, "reasoning_tokens": None} for c in calls("a", "minimal", [5, 5, 5, 5])]
    summary = analyse.probe_summary(rows)
    assert summary["a"]["efforts"]["minimal"]["honoured"] is True
    assert summary["a"]["efforts"]["minimal"]["reasoning_reported"] is False


def test_a_held_out_page_is_refused_before_anything_is_opened():
    split = json.loads(Path("data/real/split.json").read_text())
    held_out = split["held_out"][0]
    with pytest.raises(SystemExit):
        measure.development(f"{held_out}_p001")
    with pytest.raises(SystemExit):
        measure.development("not-a-page")


def test_the_draw_is_fixed_by_its_seed_and_the_speed_cells_are_new(tmp_path, monkeypatch):
    monkeypatch.setattr(measure, "ROOT", tmp_path)
    cells = {f"T.f:p:r{i}:c": {"region": {"x0": 0, "y0": 0, "x1": 5, "y1": 5}, "source": "grid"} for i in range(120)}
    (tmp_path / "boxes").mkdir()
    (tmp_path / "boxes" / "1939-01_p051.json").write_text(
        json.dumps({"ref": "1939-01_p051", "crop_host": "baseten", "cells": cells})
    )
    (tmp_path / "pick.json").write_text(
        json.dumps({"pages": {"short_term_foreign_liabilities_as": {"ref": "1939-01_p051"}}})
    )
    first = measure.draw_phase()["pages"]["1939-01_p051"]
    (tmp_path / "draw.json").unlink()
    assert measure.draw_phase()["pages"]["1939-01_p051"] == first
    speed = [c for level in first["speed"].values() for c in level]
    assert len(first["cells"]) == 40 and len(speed) == 24 == len(set(speed))
    assert not set(speed) & set(first["cells"])


def test_wilson_interval_and_the_held_out_mix():
    from openw import summarise

    low, high = summarise.wilson(5, 200)
    assert (low, high) == (0.0107, 0.0572)
    assert summarise.wilson(0, 0) is None
    # a family weighs its pages times its cells: railroad's 12 x 102 cells hardly count
    even = {f: [1.0] for f in summarise.HELD_OUT_PAGES}
    assert summarise.weighted(even) == pytest.approx(1.0)
    cheap_railroad = {**even, "receipts_and_expenditures_under_railroad": [0.0]}
    assert 0.96 < summarise.weighted(cheap_railroad) < 0.98
    assert sum(summarise.CELLS[f] * n for f, n in summarise.HELD_OUT_PAGES.items()) == 33_114
