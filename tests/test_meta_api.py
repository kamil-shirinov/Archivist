"""Muse Spark backend against an injected fake client: no network, no key."""

import base64
import os
from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai.types.chat import ChatCompletion

from archivist.models import load_roles
from archivist.models.base import LLMRequest, Usage
from archivist.models.budget import Price
from archivist.models.cache import cache_key
from archivist.models.meta_api import (
    BASE_URL,
    FIRST_BACKOFF_S,
    KEY_ENV,
    MAX_RETRIES,
    MetaLLM,
    MissingAPIKey,
    api_key,
)

CONFIG = Path(__file__).resolve().parents[1] / "config" / "models.toml"
JPEG = b"\xff\xd8\xff\xe0" + b"scan bytes"
PRICE = Price(input_per_mtok=0.10, output_per_mtok=0.20)
SCHEMA = {"type": "object", "properties": {"amount": {"type": "string"}}, "required": ["amount"]}
REQUEST = LLMRequest(
    role="extractor",
    prompt="Read the amount.",
    images=(JPEG,),
    system="You read ledger cards.",
    json_schema=SCHEMA,
    max_output_tokens=512,
)


def completion(text: str = '{"amount": "4,375.50"}', prompt: int = 1_800, out: int = 250):
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "muse-spark-1.3-contributor",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": out,
                "total_tokens": prompt + out,
                "completion_tokens_details": {"reasoning_tokens": 200},
            },
        }
    )


def status_error(code: int, headers: dict | None = None) -> openai.APIStatusError:
    response = httpx2.Response(
        code, headers=headers, request=httpx2.Request("POST", f"{BASE_URL}/chat/completions")
    )
    classes = {400: openai.BadRequestError, 429: openai.RateLimitError}
    error_class = classes.get(code, openai.InternalServerError)
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


def meta(*outcomes, sleeps: list | None = None, **settings) -> tuple[MetaLLM, FakeClient]:
    client = FakeClient(*outcomes)
    sleep = sleeps.append if sleeps is not None else lambda seconds: None
    llm = MetaLLM("muse-spark-1.3-contributor", PRICE, client=client, sleep=sleep, **settings)
    return llm, client


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """Run in an empty cwd, so no real .env is ever loaded."""
    monkeypatch.chdir(tmp_path)


# --- request -----------------------------------------------------------------------------------


def test_payload_carries_system_message_image_data_url_and_structured_output():
    llm, client = meta(completion())

    llm.complete(REQUEST)

    (call,) = client.calls
    system, user = call["messages"]
    assert system == {"role": "system", "content": "You read ledger cards."}
    assert user["role"] == "user"
    text, image = user["content"]
    assert text == {"type": "text", "text": "Read the amount."}
    assert image["type"] == "image_url"
    url = image["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == JPEG
    assert call["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "answer", "schema": SCHEMA},
    }
    assert call["model"] == "muse-spark-1.3-contributor"
    assert call["reasoning_effort"] == "low"
    assert call["max_tokens"] == 512
    assert call["timeout"] == 60.0


def test_plain_request_sends_no_system_message_and_no_response_format():
    llm, client = meta(completion("hello"), reasoning_effort="high")

    llm.complete(LLMRequest(role="rereader", prompt="hi"))

    (call,) = client.calls
    assert [message["role"] for message in call["messages"]] == ["user"]
    assert "response_format" not in call
    assert call["reasoning_effort"] == "high"


def test_unknown_image_format_and_effort_are_refused():
    llm, client = meta(completion())
    with pytest.raises(ValueError, match="JPEG, PNG"):
        llm.complete(LLMRequest(role="extractor", prompt="x", images=(b"not an image",)))
    assert client.calls == []
    with pytest.raises(ValueError, match="reasoning_effort"):
        meta(reasoning_effort="none")


# --- response ----------------------------------------------------------------------------------


def test_canned_response_maps_to_text_usage_and_cost():
    llm, _ = meta(completion(prompt=1_800, out=250))

    response = llm.complete(REQUEST)

    assert response.text == '{"amount": "4,375.50"}'
    assert (response.backend, response.model_id) == ("meta", "muse-spark-1.3-contributor")
    assert response.cached is False
    # completion_tokens already includes the 200 reasoning tokens: they are not added again
    assert response.usage == Usage(
        input_tokens=1_800,
        output_tokens=250,
        cost_usd=pytest.approx((1_800 * 0.10 + 250 * 0.20) / 1e6),
    )


# --- retries -----------------------------------------------------------------------------------


def test_429_then_success_retries_once_after_a_jittered_backoff():
    sleeps: list[float] = []
    llm, client = meta(status_error(429), completion(), sleeps=sleeps)

    response = llm.complete(REQUEST)

    assert response.text == '{"amount": "4,375.50"}'
    assert len(client.calls) == 2
    (slept,) = sleeps
    assert FIRST_BACKOFF_S <= slept <= 2 * FIRST_BACKOFF_S


def test_retry_after_header_sets_the_minimum_wait():
    sleeps: list[float] = []
    llm, _ = meta(status_error(503, {"retry-after": "7"}), completion(), sleeps=sleeps)

    llm.complete(REQUEST)

    assert sleeps == [7.0]


def test_gives_up_after_three_retries_with_doubling_backoff():
    sleeps: list[float] = []
    llm, client = meta(*[status_error(500)] * (MAX_RETRIES + 1), sleeps=sleeps)

    with pytest.raises(openai.InternalServerError):
        llm.complete(REQUEST)

    assert len(client.calls) == MAX_RETRIES + 1
    assert len(sleeps) == MAX_RETRIES
    for attempt, slept in enumerate(sleeps):
        assert FIRST_BACKOFF_S * 2**attempt <= slept <= FIRST_BACKOFF_S * 2 ** (attempt + 1)


def test_client_errors_are_not_retried():
    sleeps: list[float] = []
    llm, client = meta(status_error(400), completion(), sleeps=sleeps)

    with pytest.raises(openai.BadRequestError):
        llm.complete(REQUEST)

    assert (len(client.calls), sleeps) == (1, [])


# --- key ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "], ids=["unset", "empty", "blank"])
def test_missing_key_raises_naming_the_variable_only(monkeypatch, tmp_path, value):
    (tmp_path / ".env").write_text("OTHER_SETTING=do-not-print-me\n")
    monkeypatch.setenv("OTHER_SETTING", "do-not-print-me")  # restored after the test
    if value is None:
        monkeypatch.delenv(KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(KEY_ENV, value)

    with pytest.raises(MissingAPIKey) as raised:
        MetaLLM("muse-spark-1.3-contributor", PRICE).complete(REQUEST)

    message = str(raised.value)
    assert KEY_ENV in message
    assert "do-not-print-me" not in message
    assert os.environ.get(KEY_ENV, "").strip() == ""


def test_key_is_read_from_dotenv_and_not_needed_to_load_roles(monkeypatch, tmp_path):
    monkeypatch.delenv(KEY_ENV, raising=False)
    roles = load_roles(CONFIG, cache_dir=tmp_path / "cache", ledger_path=tmp_path / "l.jsonl")
    assert roles["extractor"].name == "meta"  # built without a key; asked for on the first call

    (tmp_path / ".env").write_text(f"{KEY_ENV}=test-value\n")
    monkeypatch.setenv(KEY_ENV, "")  # registers it with monkeypatch, so it is undone afterwards
    monkeypatch.delenv(KEY_ENV)
    assert api_key() == "test-value"


# --- cache key ---------------------------------------------------------------------------------


def test_changing_reasoning_effort_changes_the_cache_key():
    low, _ = meta()
    high, _ = meta(reasoning_effort="high")
    default = MetaLLM("muse-spark-1.3-contributor", PRICE)

    def key(llm):
        return cache_key(llm.name, llm.model_id, REQUEST, llm.settings)

    assert key(low) != key(high)
    assert key(default) == key(low)  # the default is "low", and it is keyed as such


def test_registry_keys_the_cache_on_the_role_settings(tmp_path):
    config = tmp_path / "models.toml"

    def roles_with(effort: str):
        config.write_text(
            '[roles.extractor]\nkind = "llm"\nbackend = "meta"\nmodel_id = "m"\n'
            f'settings = {{ reasoning_effort = "{effort}" }}\n'
            "[prices.m]\ninput_per_mtok = 0.1\noutput_per_mtok = 0.2\n"
        )
        return load_roles(config, cache_dir=tmp_path / "cache", ledger_path=tmp_path / "l.jsonl")

    low, high = roles_with("low")["extractor"], roles_with("high")["extractor"]

    assert low.settings == {"reasoning_effort": "low"}
    assert high.settings == {"reasoning_effort": "high"}
    assert high.inner.inner.price == Price(0.1, 0.2)
    assert cache_key(low.name, low.model_id, REQUEST, low.settings) != cache_key(
        high.name, high.model_id, REQUEST, high.settings
    )
