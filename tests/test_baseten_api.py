"""Muse Spark Open on Baseten against an injected fake client: no network, no key."""

import base64
import json
import os
import tomllib
from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai.types.chat import ChatCompletion

from archivist.models import load_roles
from archivist.models.base import LLMRequest, Usage
from archivist.models.baseten_api import (
    BASE_URL,
    KEY_ENV,
    MUSE_SPARK_OPEN,
    BasetenLLM,
    MissingAPIKey,
    close_brackets,
    json_answer,
)
from archivist.models.budget import Budget, BudgetExceeded, BudgetGuard, Price, caps_from_env
from archivist.models.cache import cache_key
from archivist.pipeline.citations import correct
from archivist.schema import BBox, Citation, ExtractedValue

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
JPEG = b"\xff\xd8\xff\xe0" + b"scan bytes"
PRICE = Price(input_per_mtok=1.25, output_per_mtok=4.25)
SCHEMA = {"type": "object", "properties": {"amount": {"type": "string"}}, "required": ["amount"]}
REQUEST = LLMRequest(
    role="extractor",
    prompt="Read the amount.",
    images=(JPEG,),
    system="You read ledger cards.",
    json_schema=SCHEMA,
    max_output_tokens=512,
)
ANSWER = '{"amount": "4,375.50"}'


def completion(
    content: str | None = ANSWER,
    reasoning: str | None = 'The total looks like {"amount": "4,375.00"}... no, 4,375.50.',
    prompt: int = 1_800,
    out: int = 1_250,
    reasoning_tokens: int = 1_000,
    finish: str = "stop",
):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": MUSE_SPARK_OPEN,
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": out,
                "total_tokens": prompt + out,
                "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
            },
        }
    )


def status_error(code: int, headers: dict | None = None) -> openai.APIStatusError:
    response = httpx2.Response(
        code, headers=headers, request=httpx2.Request("POST", f"{BASE_URL}/chat/completions")
    )
    error_class = openai.RateLimitError if code == 429 else openai.InternalServerError
    return error_class(f"status {code}", response=response, body=None)


class FakeClient:
    """Plays back outcomes in order: a completion is returned, an exception raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def baseten(*outcomes, sleeps: list | None = None, **settings) -> tuple[BasetenLLM, FakeClient]:
    client = FakeClient(*outcomes)
    sleep = sleeps.append if sleeps is not None else lambda seconds: None
    llm = BasetenLLM(MUSE_SPARK_OPEN, PRICE, client=client, sleep=sleep, **settings)
    return llm, client


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """Run in an empty cwd, so no real .env is ever loaded."""
    monkeypatch.chdir(tmp_path)


# --- request -----------------------------------------------------------------------------------


def test_payload_is_the_slug_the_image_as_a_data_url_and_the_schema_in_the_prompt():
    llm, client = baseten(completion())

    llm.complete(REQUEST)

    (call,) = client.calls
    assert call["model"] == "meta-models/muse-spark-open-1026"
    system, user = call["messages"]
    assert system == {"role": "system", "content": "You read ledger cards."}
    assert user["role"] == "user"
    text, image = user["content"]
    assert text["type"] == "text" and text["text"].startswith("Read the amount.")
    assert json.dumps(SCHEMA, separators=(",", ":")) in text["text"]  # nothing else carries it
    assert image["type"] == "image_url"
    url = image["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == JPEG
    assert "response_format" not in call  # the model has no structured outputs or JSON mode
    assert call["reasoning_effort"] == "low"
    assert call["max_tokens"] == 512
    assert call["temperature"] == 0.0
    assert call["timeout"] == 60.0


def test_plain_request_sends_only_the_prompt():
    llm, client = baseten(completion("hello"), reasoning_effort="xhigh")

    llm.complete(LLMRequest(role="rereader", prompt="hi"))

    (call,) = client.calls
    assert call["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    assert call["reasoning_effort"] == "xhigh"


def test_efforts_the_model_would_remap_and_unknown_images_are_refused():
    llm, client = baseten(completion())
    for effort in ("none", "minimal", "max", "extreme"):
        with pytest.raises(ValueError, match="reasoning_effort"):
            baseten(reasoning_effort=effort)
    with pytest.raises(ValueError, match="JPEG, PNG"):
        llm.complete(LLMRequest(role="extractor", prompt="x", images=(b"not an image",)))
    assert client.calls == []


# --- response ----------------------------------------------------------------------------------


def test_the_answer_is_read_apart_from_the_reasoning():
    llm, _ = baseten(completion())

    response = llm.complete(REQUEST)

    assert response.text == ANSWER  # not the draft in reasoning_content, which also looks like JSON
    assert (response.backend, response.model_id) == ("baseten", MUSE_SPARK_OPEN)
    assert response.cached is False


def test_reasoning_that_used_all_the_tokens_leaves_an_empty_answer_not_a_wrong_one():
    llm, _ = baseten(completion(content=None, reasoning="still thinking", finish="length"))

    assert llm.complete(REQUEST).text == ""


def test_a_fence_around_the_whole_json_answer_is_taken_off_and_nothing_else_is():
    assert json_answer('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert json_answer('  ```\n{"a": 1}\n```  ') == '{"a": 1}'
    assert json_answer('Sure: ```json\n{"a": 1}\n``` done') == 'Sure: ```json\n{"a": 1}\n``` done'
    assert json_answer('{"a": 1}') == '{"a": 1}'
    llm, _ = baseten(completion('```json\n{"amount": "1.00"}\n```'), completion("```x```"))
    assert llm.complete(REQUEST).text == '{"amount": "1.00"}'
    assert llm.complete(LLMRequest(role="rereader", prompt="hi")).text == "```x```"  # no schema


def test_brackets_the_model_left_open_are_closed_when_that_is_all_it_lacked(caplog):
    cut = '{"header":{"a":{"value":"x [y]","box":[1,2]}},"lines":{"1":{"b":{"value":"5"}}}'
    assert close_brackets(cut) == cut + "}"
    assert close_brackets('{"a":[{"b":"q\\"}"}') == '{"a":[{"b":"q\\"}"}]}'  # an escaped quote
    assert "1 bracket(s)" in caplog.text
    for unchanged in (
        '{"a":1}',  # already JSON
        '{"a":"cut off in a str',  # ends inside a string
        '{"a":[1,',  # still not JSON once closed
        '{"a":}',  # not a matter of brackets
        "not json",
    ):
        assert close_brackets(unchanged) == unchanged


def test_an_answer_that_stopped_short_of_its_last_brace_is_completed_but_one_cut_off_is_not():
    cut = '{"lines":{"1":{"b":{"value":"5"}}}'
    llm, _ = baseten(completion(cut), completion(cut, finish="length"), completion(cut))

    assert json.loads(llm.complete(REQUEST).text) == {"lines": {"1": {"b": {"value": "5"}}}}
    assert llm.complete(REQUEST).text == cut  # max_tokens ran out: left to fail
    assert llm.complete(LLMRequest(role="rereader", prompt="hi")).text == cut  # no schema asked


def test_usage_counts_reasoning_once_and_costs_it_as_output():
    llm, _ = baseten(completion(prompt=1_800, out=1_250, reasoning_tokens=1_000))

    response = llm.complete(REQUEST)

    # completion_tokens already includes the 1,000 reasoning tokens: they are not added again
    assert response.usage == Usage(
        input_tokens=1_800,
        output_tokens=1_250,
        cost_usd=pytest.approx((1_800 * 1.25 + 1_250 * 4.25) / 1e6),
    )


def test_a_response_without_usage_fails_loudly():
    done = completion()
    done.usage = None
    llm, _ = baseten(done)
    with pytest.raises(RuntimeError, match="usage"):
        llm.complete(REQUEST)


# --- retries -----------------------------------------------------------------------------------


def test_429_then_success_retries_once():
    sleeps: list[float] = []
    llm, client = baseten(status_error(429), completion(), sleeps=sleeps)

    response = llm.complete(REQUEST)

    assert response.text == ANSWER
    assert len(client.calls) == 2
    assert len(sleeps) == 1


def test_retry_after_sets_the_minimum_wait():
    sleeps: list[float] = []
    llm, _ = baseten(status_error(529, {"retry-after": "9"}), completion(), sleeps=sleeps)

    llm.complete(REQUEST)

    assert sleeps == [9.0]


# --- key ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_missing_key_raises_naming_the_variable_only(monkeypatch, tmp_path, value):
    (tmp_path / ".env").write_text("OTHER_SETTING=do-not-print-me\n")
    monkeypatch.setenv("OTHER_SETTING", "do-not-print-me")  # restored after the test
    monkeypatch.setenv("META_API_KEY", "meta-key-must-not-be-used")
    if value is None:
        monkeypatch.delenv(KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(KEY_ENV, value)

    with pytest.raises(MissingAPIKey) as raised:
        BasetenLLM(MUSE_SPARK_OPEN, PRICE).complete(REQUEST)

    message = str(raised.value)
    assert KEY_ENV in message
    assert "do-not-print-me" not in message and "meta-key-must-not-be-used" not in message
    assert os.environ.get(KEY_ENV, "").strip() == ""


def test_roles_load_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv(KEY_ENV, raising=False)
    roles = load_roles(
        CONFIG_DIR / "models_open.toml", cache_dir=tmp_path / "c", ledger_path=tmp_path / "l.jsonl"
    )
    assert roles["extractor"].name == "baseten"  # built without a key; asked for on the first call


# --- cache key ---------------------------------------------------------------------------------


def test_effort_and_backend_are_part_of_the_cache_key():
    low, _ = baseten()
    high, _ = baseten(reasoning_effort="high")

    def key(llm):
        return cache_key(llm.name, llm.model_id, REQUEST, llm.settings)

    assert key(low) != key(high)
    assert key(low) != cache_key("meta", MUSE_SPARK_OPEN, REQUEST, low.settings)


# --- spend caps, per backend -------------------------------------------------------------------


def test_caps_come_from_the_environment_with_defaults(monkeypatch):
    monkeypatch.delenv("BUDGET_CAP_USD", raising=False)
    monkeypatch.delenv("BASETEN_CAP_USD", raising=False)
    assert caps_from_env() == {"meta": 120.0, "baseten": 80.0}

    monkeypatch.setenv("BUDGET_CAP_USD", "7.5")
    monkeypatch.setenv("BASETEN_CAP_USD", "3")
    assert caps_from_env() == {"meta": 7.5, "baseten": 3.0}


def test_each_backends_cap_is_summed_from_its_own_ledger_lines(tmp_path):
    guard = BudgetGuard(10.0, tmp_path / "ledger.jsonl", caps={"meta": 10.0, "baseten": 4.0})
    guard.record("extractor", "meta", "muse-spark-1.3-contributor", Usage(1, 1, 9.5))
    guard.record("extractor", "baseten", MUSE_SPARK_OPEN, Usage(1, 1, 3.5))

    assert (guard.spent(), guard.spent("meta"), guard.spent("baseten")) == (13.0, 9.5, 3.5)
    guard.check(0.5, "meta")  # 9.5 + 0.5: on the cap is allowed
    guard.check(0.5, "baseten")  # Meta's spend does not count against Baseten
    with pytest.raises(BudgetExceeded, match="baseten cap \\$4.00"):
        guard.check(0.51, "baseten")
    with pytest.raises(BudgetExceeded, match="meta cap \\$10.00"):
        guard.check(0.51, "meta")  # and Baseten's headroom is not Meta's


def test_calls_in_flight_count_against_their_own_backend_only(tmp_path):
    guard = BudgetGuard(10.0, tmp_path / "ledger.jsonl", caps={"meta": 10.0, "baseten": 1.0})

    guard.reserve(0.75, "baseten")
    guard.reserve(9.0, "meta")
    with pytest.raises(BudgetExceeded):
        guard.reserve(0.5, "baseten")
    guard.release(0.75, "baseten")
    guard.reserve(0.5, "baseten")


def test_a_baseten_call_past_its_cap_is_refused_before_reaching_the_client(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    guard = BudgetGuard(120.0, ledger, caps={"meta": 120.0, "baseten": 0.01})
    llm, client = baseten(completion(), completion())
    budget = Budget(llm, guard, PRICE)
    cheap = LLMRequest(role="extractor", prompt="hi", max_output_tokens=1)

    budget.complete(cheap)  # projected at about $0.00001
    guard.record("extractor", "baseten", MUSE_SPARK_OPEN, Usage(1, 1, 0.01))  # now at the cap
    with pytest.raises(BudgetExceeded):
        budget.complete(cheap)

    assert len(client.calls) == 1
    lines = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [line["backend"] for line in lines] == ["baseten", "baseten"]


def test_load_roles_gives_baseten_and_meta_a_cap_each(tmp_path, monkeypatch):
    monkeypatch.setenv("BUDGET_CAP_USD", "120")
    monkeypatch.setenv("BASETEN_CAP_USD", "80")
    roles = load_roles(
        CONFIG_DIR / "models_open.toml", cache_dir=tmp_path / "c", ledger_path=tmp_path / "l.jsonl"
    )
    guard = roles["extractor"].inner.guard

    assert guard is roles["segmenter"].inner.guard
    assert (guard.cap_for("meta"), guard.cap_for("baseten")) == (120.0, 80.0)
    assert guard.cap_usd == 120.0


# --- config ------------------------------------------------------------------------------------


def _config(name: str) -> dict:
    return tomllib.loads((CONFIG_DIR / name).read_text())


def test_models_toml_prices_the_model_and_keeps_its_roles_on_meta():
    config = _config("models.toml")
    assert {role: spec["backend"] for role, spec in config["roles"].items()} == {
        "extractor": "meta",
        "rereader": "meta",
        "segmenter": "meta",
    }
    price = config["prices"][MUSE_SPARK_OPEN]
    assert price["input_per_mtok"] > 0 and price["output_per_mtok"] > 0


def test_models_open_toml_moves_the_extractor_and_rereader_to_baseten_and_changes_nothing_else():
    base, open_ = _config("models.toml"), _config("models_open.toml")

    assert open_["prices"] == base["prices"]
    for role in ("extractor", "rereader"):
        assert open_["roles"][role] == {
            **base["roles"][role],
            "backend": "baseten",
            "model_id": MUSE_SPARK_OPEN,
        }
    assert open_["roles"]["segmenter"] == base["roles"]["segmenter"]


# --- the citations safeguard (P13) -------------------------------------------------------------


def test_a_corrected_box_that_would_leave_the_page_keeps_the_extractors_box():
    from test_citations import COLUMNS, TEXT, _page, _values  # the drifting page of that module

    image, truth = _page()
    # y = 1.25 * y - 60 puts a box predicted at y = 700 at 815: below the 800 px page.
    low = BBox(x0=COLUMNS["a"][0], y0=700, x1=COLUMNS["a"][1], y1=700 + TEXT)
    stray = ExtractedValue(
        field_id="a-low", value="", citation=Citation(page_id="page-1", bbox=low)
    )
    values = [*_values(truth), stray]

    fix = correct(image, values)

    kept = fix.values[-1].citation
    assert (kept.bbox, kept.raw_bbox) == (low, low)  # not the 1 px sliver along the bottom edge
    assert fix.values[0].citation.bbox != fix.values[0].citation.raw_bbox  # the rest still move
    assert fix.matched == fix.inked == len(truth) - 3
