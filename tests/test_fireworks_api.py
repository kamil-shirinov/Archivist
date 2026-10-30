"""Muse Spark Open on Fireworks against an injected fake client: no network, no key."""

import json
import os
import tomllib
from pathlib import Path

import httpx2
import openai
import pytest
from test_baseten_api import ANSWER, PRICE, REQUEST, FakeClient, baseten, completion

from archivist import replay
from archivist.models import load_roles
from archivist.models.base import LLMRequest, Usage
from archivist.models.baseten_api import MUSE_SPARK_OPEN as BASETEN_SLUG
from archivist.models.budget import (
    BACKEND_CAPS,
    Budget,
    BudgetExceeded,
    BudgetGuard,
    caps_from_env,
)
from archivist.models.cache import cache_key
from archivist.models.fireworks_api import (
    BASE_URL,
    KEY_ENV,
    MUSE_SPARK_OPEN,
    FireworksLLM,
    MissingAPIKey,
)
from archivist.templates import real_test

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def fireworks(*outcomes, sleeps: list | None = None, **settings) -> tuple[FireworksLLM, FakeClient]:
    client = FakeClient(*outcomes)
    sleep = sleeps.append if sleeps is not None else lambda seconds: None
    return FireworksLLM(MUSE_SPARK_OPEN, PRICE, client=client, sleep=sleep, **settings), client


def refusal(code: int) -> openai.APIStatusError:
    response = httpx2.Response(
        code, request=httpx2.Request("POST", f"{BASE_URL}/chat/completions")
    )
    return openai.APIStatusError(f"status {code}", response=response, body=None)


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """Run in an empty cwd, so no real .env is ever loaded."""
    monkeypatch.chdir(tmp_path)


# --- the model and the request -----------------------------------------------------------------


def test_the_id_is_the_one_fireworks_lists_for_the_key():
    assert MUSE_SPARK_OPEN == "accounts/fireworks/models/muse-spark-open"
    assert BASE_URL == "https://api.fireworks.ai/inference/v1"
    assert KEY_ENV == "FIREWORKS_API_KEY"


def test_the_request_is_baseten_s_apart_from_the_model_so_the_hosts_are_asked_alike():
    llm, client = fireworks(completion())
    other, other_client = baseten(completion())

    llm.complete(REQUEST)
    other.complete(REQUEST)

    (call,), (reference,) = client.calls, other_client.calls
    assert call.pop("model") == MUSE_SPARK_OPEN and reference.pop("model") == BASETEN_SLUG
    assert call == reference  # prompt with the schema in it, image, effort, limits, temperature
    assert "response_format" not in call  # json_schema would switch the reasoning off (Fireworks)
    assert call["reasoning_effort"] == "low" and call["max_tokens"] == 512


@pytest.mark.parametrize("effort", ["none", "minimal", "max", "extreme"])
def test_efforts_baseten_refuses_are_refused_here_too(effort):
    with pytest.raises(ValueError, match="reasoning_effort"):
        fireworks(reasoning_effort=effort)


def test_an_unknown_image_is_refused_before_any_call():
    llm, client = fireworks(completion())
    with pytest.raises(ValueError, match="JPEG, PNG"):
        llm.complete(LLMRequest(role="extractor", prompt="x", images=(b"not an image",)))
    assert client.calls == []


# --- the response ------------------------------------------------------------------------------


def test_the_answer_is_read_apart_from_the_reasoning():
    llm, _ = fireworks(completion())

    response = llm.complete(REQUEST)

    assert response.text == ANSWER  # not the draft in reasoning_content
    assert (response.backend, response.model_id) == ("fireworks", MUSE_SPARK_OPEN)
    assert response.cached is False


def test_reasoning_that_used_all_the_tokens_leaves_an_empty_answer_not_a_wrong_one():
    llm, _ = fireworks(completion(content=None, reasoning="still thinking", finish="length"))

    assert llm.complete(REQUEST).text == ""


def test_the_answer_is_cleaned_as_baseten_s_is():
    cut = '{"lines":{"1":{"b":{"value":"5"}}}'
    llm, _ = fireworks(
        completion('```json\n{"amount": "1.00"}\n```'),
        completion(cut),
        completion(cut, finish="length"),
    )

    assert llm.complete(REQUEST).text == '{"amount": "1.00"}'  # the fence taken off
    assert json.loads(llm.complete(REQUEST).text) == {"lines": {"1": {"b": {"value": "5"}}}}
    assert llm.complete(REQUEST).text == cut  # cut off by max_tokens: left to fail


def test_completion_tokens_already_hold_the_reasoning_and_are_billed_as_output():
    """Measured on Fireworks: 322 completion tokens = 244 reasoning + 78 answer."""
    llm, _ = fireworks(completion(prompt=2_785, out=322, reasoning_tokens=244))

    response = llm.complete(REQUEST)

    assert response.usage == Usage(
        input_tokens=2_785,
        output_tokens=322,  # the reasoning is not added again
        cost_usd=pytest.approx((2_785 * 1.25 + 322 * 4.25) / 1e6),
    )


def test_a_response_without_usage_fails_loudly():
    done = completion()
    done.usage = None
    llm, _ = fireworks(done)
    with pytest.raises(RuntimeError, match="usage"):
        llm.complete(REQUEST)


# --- errors and retries ------------------------------------------------------------------------


def test_429_is_retried_waiting_as_long_as_retry_after_asks():
    rate_limited = openai.RateLimitError(
        "slow down",
        response=httpx2.Response(
            429,
            headers={"retry-after": "7"},
            request=httpx2.Request("POST", f"{BASE_URL}/chat/completions"),
        ),
        body=None,
    )
    sleeps: list[float] = []
    llm, client = fireworks(rate_limited, completion(), sleeps=sleeps)

    assert llm.complete(REQUEST).text == ANSWER
    assert len(client.calls) == 2 and sleeps == [7.0]


@pytest.mark.parametrize("code", [400, 401, 402, 403, 412])
def test_an_account_that_refuses_the_call_is_raised_at_once_and_never_retried(code):
    """A payment method asked for (402, 412) is for a person to answer, not for a retry."""
    sleeps: list[float] = []
    llm, client = fireworks(refusal(code), completion(), sleeps=sleeps)

    with pytest.raises(openai.APIStatusError) as raised:
        llm.complete(REQUEST)

    assert raised.value.status_code == code
    assert len(client.calls) == 1 and sleeps == []


# --- the key -----------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_missing_key_raises_naming_the_variable_only(monkeypatch, tmp_path, value):
    (tmp_path / ".env").write_text("OTHER_SETTING=do-not-print-me\n")
    monkeypatch.setenv("OTHER_SETTING", "do-not-print-me")
    monkeypatch.setenv("BASETEN_API_KEY", "baseten-key-must-not-be-used")
    if value is None:
        monkeypatch.delenv(KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(KEY_ENV, value)

    with pytest.raises(MissingAPIKey) as raised:
        FireworksLLM(MUSE_SPARK_OPEN, PRICE).complete(REQUEST)

    message = str(raised.value)
    assert KEY_ENV in message
    assert "do-not-print-me" not in message and "baseten-key-must-not-be-used" not in message
    assert os.environ.get(KEY_ENV, "").strip() == ""


def test_the_key_comes_from_the_environment_and_is_given_to_the_client_only(monkeypatch):
    monkeypatch.setenv(KEY_ENV, "fw-test-key")
    client = FireworksLLM(MUSE_SPARK_OPEN, PRICE).client

    assert client.api_key == "fw-test-key"
    assert str(client.base_url).rstrip("/") == BASE_URL


# --- the cache key -----------------------------------------------------------------------------


def test_host_and_effort_are_part_of_the_cache_key():
    low, _ = fireworks()
    high, _ = fireworks(reasoning_effort="high")
    baseten_low, _ = baseten()

    def key(llm):
        return cache_key(llm.name, llm.model_id, REQUEST, llm.settings)

    assert low.settings == baseten_low.settings  # asked for alike
    assert len({key(low), key(high), key(baseten_low)}) == 3


# --- spend caps, per backend -------------------------------------------------------------------


def test_fireworks_has_its_own_cap_of_40_dollars_from_its_own_variable(monkeypatch):
    for variable, _ in BACKEND_CAPS.values():
        monkeypatch.delenv(variable, raising=False)
    assert caps_from_env() == {"meta": 120.0, "baseten": 80.0, "fireworks": 40.0}

    monkeypatch.setenv("FIREWORKS_CAP_USD", "2.5")
    assert caps_from_env() == {"meta": 120.0, "baseten": 80.0, "fireworks": 2.5}


def test_spending_on_the_other_backends_does_not_use_up_fireworks_cap(tmp_path):
    caps = {"meta": 120.0, "baseten": 80.0, "fireworks": 40.0}
    guard = BudgetGuard(120.0, tmp_path / "ledger.jsonl", caps=caps)
    guard.record("extractor", "baseten", BASETEN_SLUG, Usage(1, 1, 79.0))
    guard.record("extractor", "fireworks", MUSE_SPARK_OPEN, Usage(1, 1, 39.5))

    guard.check(0.5, "fireworks")
    with pytest.raises(BudgetExceeded, match="fireworks cap \\$40.00"):
        guard.check(0.51, "fireworks")
    guard.check(1.0, "baseten")  # still room: 79 of 80, whatever Fireworks has spent
    assert (guard.spent("baseten"), guard.spent("fireworks")) == (79.0, 39.5)


def test_a_call_made_is_a_ledger_line_and_one_past_the_cap_never_reaches_the_client(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    llm, client = fireworks(completion(), completion())
    cheap = Budget(llm, BudgetGuard(120.0, ledger, caps={"fireworks": 1.0}), PRICE)

    response = cheap.complete(REQUEST)

    (line,) = [json.loads(row) for row in ledger.read_text().splitlines()]
    assert (line["role"], line["backend"], line["model_id"]) == (
        "extractor",
        "fireworks",
        MUSE_SPARK_OPEN,
    )
    assert line["cost_usd"] == pytest.approx(response.usage.cost_usd)

    spent_out = Budget(llm, BudgetGuard(120.0, ledger, caps={"fireworks": 0.0}), PRICE)
    with pytest.raises(BudgetExceeded, match="fireworks cap"):
        spent_out.complete(REQUEST)
    assert len(client.calls) == 1  # the refused call never reached the client
    assert len(ledger.read_text().splitlines()) == 1


def test_replay_zeroes_every_backends_cap_and_a_pre_registered_record_gives_fireworks_nothing(
    monkeypatch,
):
    assert set(replay.CAPS) == {variable for variable, _ in BACKEND_CAPS.values()}
    assert "FIREWORKS_CAP_USD" in replay.CAPS

    for variable, _ in BACKEND_CAPS.values():
        monkeypatch.setenv(variable, "50")
    record = {"meta": 44.5, "baseten": 21.0, "allowance": 40.0}  # as recorded before P30
    real_test.set_caps(record)
    assert os.environ["BUDGET_CAP_USD"] == "44.5" and os.environ["BASETEN_CAP_USD"] == "21.0"
    assert os.environ["FIREWORKS_CAP_USD"] == "0.0"


# --- config ------------------------------------------------------------------------------------


def _config(name: str) -> dict:
    return tomllib.loads((CONFIG_DIR / name).read_text())


def test_roles_load_without_a_key_on_the_fireworks_backend_with_its_own_cap(monkeypatch, tmp_path):
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv("FIREWORKS_CAP_USD", raising=False)
    roles = load_roles(
        CONFIG_DIR / "models_fireworks.toml",
        cache_dir=tmp_path / "c",
        ledger_path=tmp_path / "l.jsonl",
    )
    guard = roles["extractor"].inner.guard

    assert roles["extractor"].name == "fireworks" and roles["rereader"].name == "fireworks"
    assert roles["segmenter"].name == "meta"
    assert guard.cap_for("fireworks") == 40.0 and guard.cap_for("baseten") == 80.0


def test_models_fireworks_toml_is_models_open_toml_with_the_host_changed_and_a_price_added():
    base, open_, fw = _config("models.toml"), _config("models_open.toml"), _config(
        "models_fireworks.toml"
    )

    for role in ("extractor", "rereader"):
        assert fw["roles"][role] == {
            **open_["roles"][role],
            "backend": "fireworks",
            "model_id": MUSE_SPARK_OPEN,
        }
    assert fw["roles"]["segmenter"] == open_["roles"]["segmenter"]
    assert fw["doc_types"] == open_["doc_types"]
    assert fw["prices"] == {**base["prices"], MUSE_SPARK_OPEN: fw["prices"][MUSE_SPARK_OPEN]}
    # the same rates as Baseten's for the same model, per Fireworks' pricing page (2026-10-30)
    assert fw["prices"][MUSE_SPARK_OPEN] == open_["prices"][BASETEN_SLUG]


def test_the_smoke_command_can_pick_fireworks():
    from archivist.models import smoke

    assert smoke.BACKEND_CONFIGS["fireworks"] == Path("config/models_fireworks.toml")
