"""The arm comparison, its decision rule, the arm configs and the reproducible P13 comparison."""

import json
import tomllib
from pathlib import Path

import pytest
from test_verify import MEMO_VALUES, _gt_page, _image, _memo_page, _rereader

from archivist.eval import compare_arms, compare_extractors
from archivist.models import smoke
from archivist.models.budget import BudgetGuard
from archivist.models.mock import MockSegmenter
from archivist.pipeline import verify

MISREAD = MEMO_VALUES | {"counterparty": "Eastmoon Electricity Board", "amount": "65.43"}


def _row(error: float, review: float, cost: float) -> dict:
    return {"error_rate_accepted": error, "review_rate": review, "cost_per_page_usd": cost}


# --- The decision rule -----------------------------------------------------------------------


def test_the_lowest_pooled_error_rate_wins_when_nothing_is_within_a_tenth_of_a_point():
    pooled = {("A", "v2"): _row(0.0030, 0.05, 0.01), ("B", "v3"): _row(0.0015, 0.30, 0.10)}
    winner, ranking = compare_arms.choose(pooled)
    assert winner == ("B", "v3")
    assert [(r["arm"], r["within_tie"]) for r in ranking] == [("B", True), ("A", False)]


def test_within_a_tenth_of_a_point_the_lower_review_rate_wins_then_the_lower_cost():
    pooled = {
        ("A", "v2"): _row(0.0020, 0.10, 0.01),
        ("A", "v3"): _row(0.0012, 0.12, 0.01),
        ("C", "v3"): _row(0.0022, 0.08, 0.02),  # 0.1 points above the lowest: still in the tie
    }
    assert compare_arms.choose(pooled)[0] == ("C", "v3")
    pooled[("C", "v3")] = _row(0.0022, 0.10, 0.02)  # the same review rate as A v2, dearer
    assert compare_arms.choose(pooled)[0] == ("A", "v2")


def test_an_arm_with_nothing_accepted_never_wins():
    pooled = {("A", "v2"): _row(None, 1.0, 0.01), ("B", "v2"): _row(0.05, 0.2, 0.1)}
    assert compare_arms.choose(pooled)[0] == ("B", "v2")


# --- The whole comparison, with mocks --------------------------------------------------------


def _source(runs: Path, name: str, values: dict, images: Path, cost: float) -> None:
    run = runs / name
    run.mkdir(parents=True, exist_ok=True)
    (run / "predictions.jsonl").write_text(_memo_page(values).model_dump_json() + "\n")
    run.joinpath("run.json").write_text(
        json.dumps({"images": str(images), "citations": "S0+ink", "cost_usd": cost})
    )


def test_every_arm_is_scored_under_both_policies_per_split_and_pooled(tmp_path):
    runs, data = tmp_path / "runs", tmp_path / "data"
    for split in compare_arms.SPLITS:
        images = _image(data / split / "images").parent
        (data / split / "gt").mkdir(parents=True)
        (data / split / "gt" / "m1.json").write_text(_gt_page().model_dump_json())
        for name, arm in compare_arms.ARMS.items():
            source, out = arm["runs"][split]
            values = MEMO_VALUES if name == "B" else MISREAD  # B's extractor reads it all right
            _source(runs, source, values, images, cost=0.5 if name == "B" else 0.1)
            verify.run(
                runs / source,
                runs / out,
                {"segmenter": MockSegmenter(), "rereader": _rereader(MEMO_VALUES)},
                guard=BudgetGuard(1.0, tmp_path / "ledger.jsonl"),
                config={"rereader": {"backend": "mock"}},
            )

    report = compare_arms.compare(runs, data)

    a = report["results"]["A"]
    assert set(a) == set(verify.POLICIES)
    assert set(a["v2"]) == {"dev", "val", "pooled"}
    # The same page id on both splits is two pages once pooled.
    assert (a["v2"]["dev"]["n_pages"], a["v2"]["pooled"]["n_pages"]) == (1, 2)
    assert a["v2"]["pooled"]["n_fields"] == 2 * a["v2"]["dev"]["n_fields"]
    assert a["v2"]["dev"]["errors_caught"] == 2 and a["v2"]["dev"]["errors_missed"] == 0
    assert a["v2"]["dev"]["baseline_error_rate_accepted"] == pytest.approx(2 / 7)
    assert (a["v2"]["dev"]["n_proposed"], a["v3"]["dev"]["n_proposed"]) == (1, 2)
    assert a["v2"]["dev"]["review_rate_severity_3"] == a["v2"]["dev"]["review_rate"]
    assert a["v2"]["pooled"]["cost_per_page_usd"] == pytest.approx(0.1)
    # B accepts everything and nothing it accepts is wrong: the lowest review rate at no error.
    assert report["winner"]["arm"] == "B"
    assert report["all_open_weights"]["arm"] == "B"
    assert set(report["all_open_weights"]["pooled"]) == set(verify.POLICIES)
    assert report["rule"] == compare_arms.RULE
    assert "headline: arm B" in compare_arms.table(report)


# --- Configs ---------------------------------------------------------------------------------


def _roles(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)["roles"]


@pytest.mark.parametrize(
    ("arm", "extractor", "rereader"),
    [("A", "meta", "meta"), ("B", "baseten", "baseten"), ("C", "meta", "baseten")],
)
def test_each_arm_config_puts_its_roles_on_its_backends_at_low_effort(arm, extractor, rereader):
    roles = _roles(compare_arms.ARMS[arm]["config"])
    assert (roles["extractor"]["backend"], roles["rereader"]["backend"]) == (extractor, rereader)
    assert roles["segmenter"]["model_id"] == "sam-3.1"
    for role in ("extractor", "rereader"):
        assert roles[role]["settings"] == {"reasoning_effort": "low"}


def test_arm_b_is_the_open_config_the_baseline_open_runs_were_made_with():
    assert _roles("config/arms/b.toml") == _roles("config/models_open.toml")


# --- Reproducibility -------------------------------------------------------------------------


def test_the_difference_between_extractors_says_whether_their_intervals_overlap():
    base = {
        "field_accuracy": 0.9,
        "field_accuracy_ci95": [0.85, 0.95],
        "error_rate_accepted": 0.05,
        "error_rate_ci95": [0.02, 0.04],
    }
    other = {
        "field_accuracy": 0.97,
        "field_accuracy_ci95": [0.94, 0.99],
        "error_rate_accepted": 0.01,
        "error_rate_ci95": [0.0, 0.019],
    }
    diff = compare_extractors.difference(other, base)
    assert diff["field_accuracy"] == pytest.approx(0.07)
    assert diff["field_accuracy_intervals_overlap"] is True
    assert diff["error_rate_accepted"] == pytest.approx(-0.04)
    assert diff["error_rate_intervals_overlap"] is False


def test_the_smoke_call_picks_its_config_by_backend(monkeypatch, tmp_path):
    page = tmp_path / "card.jpg"
    page.write_bytes(b"")
    monkeypatch.setattr(smoke, "first_clean_ledger", lambda: page)
    monkeypatch.setattr(smoke.Image, "open", lambda _: type("I", (), {"size": (10, 10)})())
    seen = []

    def load_roles(config):
        seen.append(config)
        raise LookupError("stop before any call")

    monkeypatch.setattr(smoke, "load_roles", load_roles)
    for argv in (["--backend", "baseten"], ["--backend", "meta"], []):
        with pytest.raises(LookupError):
            smoke.main(argv)
    assert seen == [
        Path("config/arms/b.toml"),
        Path("config/arms/a.toml"),
        Path("config/models.toml"),
    ]


def test_the_default_config_and_policy_are_the_headline_the_comparison_chose():
    winner = json.loads(Path("results/arms_compare.json").read_text())["winner"]
    assert _roles("config/models.toml") == _roles(compare_arms.ARMS[winner["arm"]]["config"])
    assert verify.POLICY == winner["policy"]
