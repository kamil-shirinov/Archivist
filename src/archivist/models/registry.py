"""Roles to backends. Everything that calls a model gets it from load_roles(), already wrapped.

config/models.toml maps each role to a backend and a model_id, so swapping a model is a config
change. Each role is built as Cache(Budget(Backend)): a cache hit costs nothing, and a miss
cannot reach a backend without passing the spend cap. One guard, hence one cap, covers all roles.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from archivist.models.base import Segmenter, VisionLLM
from archivist.models.budget import LEDGER_PATH, Budget, BudgetGuard, Price
from archivist.models.cache import CACHE_DIR, Cache
from archivist.models.mock import MockLLM, MockSegmenter

CONFIG_PATH = Path("config/models.toml")
DEFAULT_CAP_USD = 120.0

Kind = Literal["llm", "segmenter"]
_BACKENDS: dict[tuple[str, Kind], Callable[[str], VisionLLM | Segmenter]] = {}


def register_backend(
    name: str, kind: Kind, factory: Callable[[str], VisionLLM | Segmenter]
) -> None:
    """Make `name` available as the `backend` of roles of this kind; factory takes a model_id."""
    if (name, kind) in _BACKENDS:
        raise ValueError(f"{kind} backend {name!r} is already registered")
    _BACKENDS[(name, kind)] = factory


register_backend("mock", "llm", lambda model_id: MockLLM(model_id=model_id))
register_backend("mock", "segmenter", lambda model_id: MockSegmenter(model_id=model_id))


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
    price = Price(prices[model_id]["input_per_mtok"], prices[model_id]["output_per_mtok"])
    return Cache(Budget(_BACKENDS[(name, kind)](model_id), guard, price), cache_dir)


def load_roles(
    config_path: Path = CONFIG_PATH,
    *,
    cache_dir: Path = CACHE_DIR,
    ledger_path: Path = LEDGER_PATH,
) -> dict[str, VisionLLM | Segmenter]:
    """Every role as Cache(Budget(Backend)). The cap is env BUDGET_CAP_USD, default 120."""
    roles, prices = _read(config_path)
    guard = BudgetGuard(float(os.environ.get("BUDGET_CAP_USD", DEFAULT_CAP_USD)), ledger_path)
    return {role: _build(role, spec, prices, guard, cache_dir) for role, spec in roles.items()}


def describe_config(config_path: Path = CONFIG_PATH) -> dict[str, dict[str, str]]:
    """Which backend and model each role uses; stamped on every results file."""
    roles, _ = _read(config_path)
    return {
        role: {"backend": spec["backend"], "model_id": spec["model_id"]}
        for role, spec in roles.items()
    }
