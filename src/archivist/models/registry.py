"""Roles to backends. Everything that calls a model gets it from load_roles(), already wrapped.

config/models.toml maps each role to a backend, a model_id and optional settings (such as
reasoning_effort), so swapping a model is a config change. Each role is built as
Cache(Budget(Backend)): a cache hit costs nothing, and a miss cannot reach a backend without
passing the spend cap. One guard covers all roles, with a cap per backend (budget.py). The
backend's settings are part of the cache key, so changing one is a miss, never a stale answer.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from archivist.models.base import Segmenter, VisionLLM
from archivist.models.baseten_api import BasetenLLM
from archivist.models.budget import LEDGER_PATH, Budget, BudgetGuard, Price, caps_from_env
from archivist.models.cache import CACHE_DIR, Cache
from archivist.models.fireworks_api import FireworksLLM
from archivist.models.meta_api import MetaLLM, MetaSAM
from archivist.models.mock import MockLLM, MockSegmenter

CONFIG_PATH = Path("config/models.toml")

Kind = Literal["llm", "segmenter"]
Factory = Callable[..., VisionLLM | Segmenter]
_BACKENDS: dict[tuple[str, Kind], tuple[Factory, bool]] = {}


def register_backend(name: str, kind: Kind, factory: Factory, *, priced: bool = False) -> None:
    """Make `name` available as the `backend` of roles of this kind.

    The factory is called as factory(model_id, **settings), with the role's settings table, plus
    price=Price(...) when `priced`: a backend that reports its own cost needs the config's price.
    """
    if (name, kind) in _BACKENDS:
        raise ValueError(f"{kind} backend {name!r} is already registered")
    _BACKENDS[(name, kind)] = (factory, priced)


register_backend("mock", "llm", lambda model_id: MockLLM(model_id=model_id))
register_backend("mock", "segmenter", lambda model_id: MockSegmenter(model_id=model_id))
register_backend("meta", "llm", MetaLLM, priced=True)
register_backend("meta", "segmenter", MetaSAM, priced=True)
register_backend("baseten", "llm", BasetenLLM, priced=True)
register_backend("fireworks", "llm", FireworksLLM, priced=True)


def _read(config_path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)
    return config["roles"], config["prices"]


def _build(
    role: str, spec: dict, prices: dict[str, dict], guard: BudgetGuard, cache_dir: Path
) -> Cache:
    kind, name, model_id = spec["kind"], spec["backend"], spec["model_id"]
    if (name, kind) not in _BACKENDS:
        known = sorted(f"{n} ({k})" for n, k in _BACKENDS)
        raise ValueError(f"role {role!r}: no {kind} backend {name!r}; registered: {known}")
    if model_id not in prices:
        raise ValueError(f"role {role!r}: no [prices.{model_id}] entry in the config")
    entry = prices[model_id]
    price = Price(
        entry["input_per_mtok"], entry["output_per_mtok"], entry.get("per_image_usd", 0.0)
    )
    factory, priced = _BACKENDS[(name, kind)]
    options = dict(spec.get("settings", {}))
    if priced:
        options["price"] = price
    backend = factory(model_id, **options)
    # The backend's own settings, defaults included, so a changed default is a miss too.
    settings = getattr(backend, "settings", {})
    return Cache(Budget(backend, guard, price), cache_dir, settings)


def load_roles(
    config_path: Path = CONFIG_PATH,
    *,
    cache_dir: Path = CACHE_DIR,
    ledger_path: Path = LEDGER_PATH,
) -> dict[str, VisionLLM | Segmenter]:
    """Every role as Cache(Budget(Backend)). Caps per backend: Meta's is env BUDGET_CAP_USD
    (default 120), Baseten's env BASETEN_CAP_USD (default 80), Fireworks' env FIREWORKS_CAP_USD
    (default 40).
    """
    roles, prices = _read(config_path)
    caps = caps_from_env()
    guard = BudgetGuard(caps["meta"], ledger_path, caps=caps)
    return {role: _build(role, spec, prices, guard, cache_dir) for role, spec in roles.items()}


def describe_config(config_path: Path = CONFIG_PATH) -> dict[str, dict[str, str]]:
    """Which backend and model each role uses; stamped on every results file."""
    roles, _ = _read(config_path)
    return {
        role: {"backend": spec["backend"], "model_id": spec["model_id"]}
        for role, spec in roles.items()
    }
