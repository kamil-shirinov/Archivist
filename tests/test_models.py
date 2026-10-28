"""Model layer: cache, spend cap and registry, on mock backends only."""

import dataclasses
import itertools
import json
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from archivist.models import describe_config, load_roles, registry
from archivist.models.base import LLMRequest, Region, SegmentRequest, Usage
from archivist.models.budget import (
    SEGMENT_OUTPUT_TOKENS,
    Budget,
    BudgetExceeded,
    BudgetGuard,
    Price,
    project_cost,
)
from archivist.models.cache import Cache, cache_key
from archivist.models.mock import MockLLM, MockSegmenter
from archivist.schema import BBox

CONFIG = Path(__file__).resolve().parents[1] / "config" / "models.toml"
REQUEST = LLMRequest(role="extractor", prompt="read the amount", images=(b"page-1",))
SEGMENT = SegmentRequest(role="segmenter", image=b"page-1", prompts=("cell", "stamp"))

CAP = 1.00
# 4000 output tokens at $100 per million: every call is projected at $0.40, like the mock's cost
PRICE = Price(input_per_mtok=0.0, output_per_mtok=100.0)
CALL = LLMRequest(role="extractor", prompt="read", max_output_tokens=4000)


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    """Default relative paths (cache/, results/) land in a scratch cwd that must stay empty."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    yield
    assert not any(cwd.iterdir()), "a test wrote through a default path instead of tmp_path"


def ledger_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- cache -------------------------------------------------------------------------------------


def test_repeated_request_hits_the_cache_without_calling_the_backend(tmp_path):
    backend = MockLLM(lambda request: "4,375.50", cost_usd=0.01)
    cache = Cache(backend, tmp_path / "cache")

    first = cache.complete(REQUEST)
    second = cache.complete(REQUEST)

    assert len(backend.calls) == 1
    assert (first.cached, second.cached) == (False, True)
    assert dataclasses.replace(second, cached=False) == first
    key = cache_key(backend.name, backend.model_id, REQUEST)
    assert (tmp_path / "cache" / key[:2] / f"{key}.json").is_file()


def test_identical_requests_made_at_once_share_one_call_and_one_answer(tmp_path):
    asked, release = threading.Event(), threading.Event()
    answers = (f"answer {n}" for n in itertools.count())  # a model that never answers alike twice

    def respond(request):
        asked.set()
        assert release.wait(5)
        return next(answers)

    backend = MockLLM(respond)
    caches = [Cache(backend, tmp_path / "cache") for _ in range(2)]  # two roles, one directory
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(caches[n % 2].complete, REQUEST) for n in range(8)]
        assert asked.wait(5)
        time.sleep(0.1)  # the other seven are waiting on the first call by now
        release.set()
        responses = [future.result() for future in futures]

    assert len(backend.calls) == 1
    assert {r.text for r in responses} == {"answer 0"}
    assert sorted(r.cached for r in responses) == [False] + [True] * 7
    replayed = Cache(MockLLM(lambda request: "never asked"), tmp_path / "cache").complete(REQUEST)
    assert replayed.text == "answer 0"


def test_when_the_one_call_fails_the_next_caller_asks_in_its_place(tmp_path):
    outcomes = iter([TimeoutError("the backend timed out"), "4,375.50"])

    def respond(request):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    cache = Cache(MockLLM(respond), tmp_path / "cache")
    with pytest.raises(TimeoutError):
        cache.complete(REQUEST)
    assert cache.complete(REQUEST).text == "4,375.50"  # the failed call left no lock held


def test_an_entry_is_written_whole_or_not_at_all(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache = Cache(MockLLM(lambda request: "4,375.50"), cache_dir)
    cache.complete(REQUEST)
    files = [p.name for p in cache_dir.rglob("*") if p.is_file()]
    assert len(files) == 1 and files[0].endswith(".json")  # no temporary file left behind

    def failing_fsync(fd):
        raise OSError("disk full")

    monkeypatch.setattr("archivist.models.cache.os.fsync", failing_fsync)
    other = dataclasses.replace(REQUEST, prompt="read the date")
    with pytest.raises(OSError, match="disk full"):
        cache.complete(other)
    assert sorted(p.name for p in cache_dir.rglob("*") if p.is_file()) == files  # nothing new


def test_different_image_bytes_miss(tmp_path):
    backend = MockLLM()
    cache = Cache(backend, tmp_path / "cache")

    cache.complete(REQUEST)
    other = cache.complete(dataclasses.replace(REQUEST, images=(b"page-2",)))

    assert other.cached is False
    assert len(backend.calls) == 2


def test_cache_is_a_replay_log_across_instances(tmp_path):
    cache_dir = tmp_path / "cache"
    recorded = Cache(MockLLM(lambda request: "recorded"), cache_dir).complete(REQUEST)

    offline = MockLLM()
    replayed = Cache(offline, cache_dir).complete(REQUEST)

    assert offline.calls == []
    assert (replayed.text, replayed.cached) == (recorded.text, True)


@pytest.mark.parametrize(
    "change",
    [
        {"role": "rereader"},
        {"prompt": "read the date"},
        {"images": ()},
        {"system": "be brief"},
        {"json_schema": {"type": "object"}},
        {"max_output_tokens": 128},
        {"temperature": 0.7},
    ],
    ids=lambda change: next(iter(change)),
)
def test_every_request_field_is_part_of_the_key(change):
    changed = dataclasses.replace(REQUEST, **change)
    assert cache_key("mock", "mock-llm", changed) != cache_key("mock", "mock-llm", REQUEST)


def test_backend_and_model_are_part_of_the_key():
    key = cache_key("mock", "mock-llm", REQUEST)
    assert cache_key("other", "mock-llm", REQUEST) != key
    assert cache_key("mock", "mock-llm-2", REQUEST) != key


def test_key_does_not_depend_on_dict_order():
    a = dataclasses.replace(REQUEST, json_schema={"a": 1, "b": 2})
    b = dataclasses.replace(REQUEST, json_schema={"b": 2, "a": 1})
    assert cache_key("mock", "m", a) == cache_key("mock", "m", b)


def test_segmenter_responses_survive_the_cache(tmp_path):
    regions = (Region(label="cell", bbox=BBox(x0=1, y0=2, x1=30, y1=40), score=0.9),)
    cache_dir = tmp_path / "cache"
    first = Cache(MockSegmenter(lambda request: regions, cost_usd=0.02), cache_dir).segment(SEGMENT)

    offline = MockSegmenter()
    second = Cache(offline, cache_dir).segment(SEGMENT)

    assert offline.calls == []
    assert second.cached is True
    assert second.regions == first.regions == regions
    assert second.usage == first.usage
    assert first.usage.cost_usd == 0.02


def test_wrapper_refuses_the_other_protocol(tmp_path):
    with pytest.raises(AttributeError):
        Cache(MockSegmenter(), tmp_path / "cache").complete(REQUEST)


# --- budget ------------------------------------------------------------------------------------


def test_third_call_is_refused_before_reaching_the_backend(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    backend = MockLLM(cost_usd=0.40)
    budget = Budget(backend, BudgetGuard(CAP, ledger), PRICE)

    budget.complete(CALL)
    budget.complete(CALL)
    with pytest.raises(BudgetExceeded):
        budget.complete(CALL)

    assert len(backend.calls) == 2
    assert len(ledger.read_text().splitlines()) == 2


def test_ledger_line_holds_the_actual_usage(tmp_path):
    ledger = tmp_path / "results" / "ledger.jsonl"  # created on first write
    backend = MockLLM(lambda request: "x" * 40, cost_usd=0.40)

    Budget(backend, BudgetGuard(CAP, ledger), PRICE).complete(CALL)

    (line,) = ledger_lines(ledger)
    stamp = datetime.fromisoformat(line.pop("timestamp"))
    assert stamp.utcoffset().total_seconds() == 0
    assert abs((datetime.now(UTC) - stamp).total_seconds()) < 60
    assert line == {
        "role": "extractor",
        "backend": "mock",
        "model_id": "mock-llm",
        "input_tokens": 1,  # "read": 4 characters
        "output_tokens": 10,  # 40 characters
        "cost_usd": 0.40,
    }


def test_segmenter_calls_are_guarded_and_recorded(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    budget = Budget(MockSegmenter(cost_usd=0.25), BudgetGuard(CAP, ledger), Price(0.0, 0.0))

    budget.segment(SEGMENT)

    (line,) = ledger_lines(ledger)
    assert (line["role"], line["cost_usd"]) == ("segmenter", 0.25)


def test_cache_hits_add_nothing_to_the_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    backend = MockLLM(cost_usd=0.40)
    guard = BudgetGuard(CAP, ledger)
    cache = Cache(Budget(backend, guard, PRICE), tmp_path / "cache")

    cache.complete(CALL)
    hit = cache.complete(CALL)

    assert hit.cached is True
    assert len(backend.calls) == 1
    assert len(ledger.read_text().splitlines()) == 1
    assert guard.spent() == pytest.approx(0.40)


def test_ledger_survives_restarts(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    Budget(MockLLM(cost_usd=0.40), BudgetGuard(CAP, ledger), PRICE).complete(CALL)

    fresh = BudgetGuard(CAP, ledger)
    assert fresh.spent() == pytest.approx(0.40)

    backend = MockLLM(cost_usd=0.40)
    big = dataclasses.replace(CALL, max_output_tokens=7000)  # projected at 0.70
    with pytest.raises(BudgetExceeded):  # fits an empty ledger, not one with 0.40 already spent
        Budget(backend, fresh, PRICE).complete(big)
    assert backend.calls == []


def test_a_call_landing_exactly_on_the_cap_is_allowed(tmp_path):
    guard = BudgetGuard(1.0, tmp_path / "ledger.jsonl")
    guard.record("extractor", "mock", "mock-llm", Usage(1, 1, 0.25))

    guard.check(0.75)
    with pytest.raises(BudgetExceeded):
        guard.check(0.76)


def test_missing_ledger_is_zero_spend_and_is_not_created(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    assert BudgetGuard(CAP, ledger).spent() == 0.0
    assert not ledger.exists()


def test_unreadable_ledger_line_fails_loudly(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"cost_usd": 0.1}\nnot json\n')
    with pytest.raises(json.JSONDecodeError):
        BudgetGuard(CAP, ledger).spent()


def test_default_ledger_path():
    assert BudgetGuard(CAP).ledger_path == Path("results/spend_ledger.jsonl")


def test_projection_counts_everything_sent_and_the_full_output_limit():
    price = Price(input_per_mtok=1e6, output_per_mtok=2e6)  # $1 per input token, $2 per output
    request = LLMRequest(
        role="extractor",
        prompt="p" * 400,  # 100 tokens
        images=(b"a", b"b"),  # 4 000 tokens
        system="s" * 40,  # 10 tokens
        json_schema={"type": "object"},  # 18 characters, 4.5 tokens
        max_output_tokens=10,
    )
    assert project_cost(request, price) == pytest.approx(100 + 4000 + 10 + 4.5 + 2 * 10)


def test_segment_projection_uses_one_image_and_the_default_output_limit():
    price = Price(input_per_mtok=1e6, output_per_mtok=2e6)
    request = SegmentRequest(role="segmenter", image=b"a", prompts=("p" * 20, "q" * 20))
    assert project_cost(request, price) == pytest.approx(10 + 2000 + 2 * SEGMENT_OUTPUT_TOKENS)


# --- mocks -------------------------------------------------------------------------------------


def test_mocks_are_deterministic_and_use_the_given_function_and_cost():
    llm = MockLLM(lambda request: request.prompt.upper(), cost_usd=0.5)
    first, second = llm.complete(REQUEST), llm.complete(REQUEST)
    assert first == second
    assert first.text == "READ THE AMOUNT"
    assert first.usage.cost_usd == 0.5
    assert (first.backend, first.model_id) == ("mock", "mock-llm")

    box = BBox(x0=0, y0=0, x1=5, y1=5)
    segmenter = MockSegmenter(lambda request: [Region(label=request.prompts[0], bbox=box, score=1)])
    assert segmenter.segment(SEGMENT).regions == (Region(label="cell", bbox=box, score=1),)
    assert MockSegmenter().segment(SEGMENT).regions == ()
    assert MockLLM().complete(REQUEST).usage.cost_usd == 0.0


# --- registry ----------------------------------------------------------------------------------


def load(tmp_path, config_path=CONFIG):
    return load_roles(config_path, cache_dir=tmp_path / "cache", ledger_path=tmp_path / "l.jsonl")


def write_config(tmp_path, *, backend="mock", kind="llm", prices=True):
    path = tmp_path / "models.toml"
    path.write_text(
        f'[roles.extractor]\nkind = "{kind}"\nbackend = "{backend}"\nmodel_id = "m"\n'
        + ("[prices.m]\ninput_per_mtok = 1.0\noutput_per_mtok = 2.0\n" if prices else "[prices]\n")
    )
    return path


def test_load_roles_builds_cache_budget_backend_for_every_role(tmp_path):
    roles = load(tmp_path)

    assert roles.keys() == {"extractor", "rereader", "segmenter"}
    for role, client in roles.items():
        assert isinstance(client, Cache)
        assert isinstance(client.inner, Budget)
        assert client.inner.inner.name == describe_config(CONFIG)[role]["backend"]
    assert len({id(client.inner.guard) for client in roles.values()}) == 1  # one cap for all


def test_cap_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("BUDGET_CAP_USD", raising=False)
    assert load(tmp_path)["extractor"].inner.guard.cap_usd == 120.0

    monkeypatch.setenv("BUDGET_CAP_USD", "7.5")
    assert load(tmp_path)["extractor"].inner.guard.cap_usd == 7.5


def test_describe_config_matches_models_toml(tmp_path):
    expected = {
        role: {"backend": spec["backend"], "model_id": spec["model_id"]}
        for role, spec in tomllib.loads(CONFIG.read_text())["roles"].items()
    }
    assert describe_config(CONFIG) == expected
    assert expected.keys() == {"extractor", "rereader", "segmenter"}
    for role, client in load(tmp_path).items():
        assert (client.name, client.model_id) == tuple(expected[role].values())


def test_roles_work_end_to_end_and_write_only_where_told(tmp_path):
    config = tmp_path / "models.toml"  # all mock: the shipped config reaches a paid API
    config.write_text(
        '[roles.extractor]\nkind = "llm"\nbackend = "mock"\nmodel_id = "mock-llm"\n'
        '[roles.segmenter]\nkind = "segmenter"\nbackend = "mock"\nmodel_id = "mock-segmenter"\n'
        "[prices.mock-llm]\ninput_per_mtok = 0.0\noutput_per_mtok = 0.0\n"
        "[prices.mock-segmenter]\ninput_per_mtok = 0.0\noutput_per_mtok = 0.0\n"
    )
    roles = load(tmp_path, config)
    request = LLMRequest(role="extractor", prompt="hello")

    assert roles["extractor"].complete(request).cached is False
    assert roles["extractor"].complete(request).cached is True
    assert roles["segmenter"].segment(SEGMENT).regions == ()

    assert [line["role"] for line in ledger_lines(tmp_path / "l.jsonl")] == [
        "extractor",
        "segmenter",
    ]
    assert len(list((tmp_path / "cache").glob("*/*.json"))) == 2


def test_backends_register_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_BACKENDS", dict(registry._BACKENDS))
    registry.register_backend("fake", "llm", lambda model_id: MockLLM(model_id=model_id))

    roles = load(tmp_path, write_config(tmp_path, backend="fake"))

    assert roles["extractor"].inner.inner.model_id == "m"
    with pytest.raises(ValueError, match="already registered"):
        registry.register_backend("fake", "llm", lambda model_id: MockLLM())


def test_unknown_backend_fails_loudly(tmp_path):
    with pytest.raises(ValueError, match="no llm backend 'nope'"):
        load(tmp_path, write_config(tmp_path, backend="nope"))


def test_backend_of_the_wrong_kind_fails_loudly(tmp_path):
    with pytest.raises(ValueError, match="no segmenter backend 'nope'"):
        load(tmp_path, write_config(tmp_path, backend="nope", kind="segmenter"))


def test_model_without_a_price_fails_loudly(tmp_path):
    with pytest.raises(ValueError, match=r"\[prices\.m\]"):
        load(tmp_path, write_config(tmp_path, prices=False))
