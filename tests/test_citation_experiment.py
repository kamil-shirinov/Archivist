"""The citation experiment's decision rule and its offline S1+ink step, with no model involved."""

import io
import json

import pytest
from PIL import Image

from archivist.eval import citation_experiment as experiment
from archivist.pipeline.extract import PageExtraction, load_predictions
from archivist.schema import BBox, Citation, ExtractedValue


def _variant(citation: float | None, field: float) -> dict:
    return {
        "run_id": "r",
        "citation_accuracy": {"all": citation},
        "field_accuracy": field,
        "error_rate": 0.0,
    }


def test_the_best_citations_win_within_half_a_point_of_s0s_field_accuracy():
    variants = {
        "S0": _variant(0.45, 0.960),
        "S1": _variant(0.60, 0.956),  # 0.4 points down: allowed
        "S1+ink": _variant(0.90, 0.956),
    }
    assert experiment.choose(variants) == "S1+ink"


def test_more_than_half_a_point_lost_rules_a_variant_out():
    variants = {
        "S0": _variant(0.45, 0.960),
        "S1": _variant(0.60, 0.954),  # 0.6 points down
        "S1+ink": _variant(0.90, 0.954),
    }
    assert experiment.choose(variants) == "S0"


def test_a_tie_goes_to_the_simpler_variant():
    variants = {
        "S0": _variant(0.45, 0.960),
        "S1": _variant(0.80, 0.960),
        "S1+ink": _variant(0.80, 0.970),
    }
    assert experiment.choose(variants) == "S1"


def test_a_variant_with_no_citations_to_judge_cannot_win():
    variants = {
        "S0": _variant(0.45, 0.960),
        "S1": _variant(None, 0.960),
        "S1+ink": _variant(None, 0.960),
    }
    assert experiment.choose(variants) == "S0"


def test_the_variant_summary_reads_a_run_evals_metrics():
    metrics = {
        "overall": {"citation_accuracy": 0.5, "field_accuracy": 0.9, "error_rate_accepted": 0.1},
        "by_doc_type": {"ledger": {"citation_accuracy": 0.4}, "memo": {"citation_accuracy": 0.7}},
    }
    assert experiment.variant("run-1", metrics) == {
        "run_id": "run-1",
        "citation_accuracy": {"all": 0.5, "ledger": 0.4, "memo": 0.7},
        "field_accuracy": 0.9,
        "error_rate": 0.1,
    }


def test_apply_ink_writes_a_derived_run_with_every_page_and_its_fit(tmp_path):
    images, source, target = tmp_path / "images", tmp_path / "s1", tmp_path / "s1-ink"
    images.mkdir()
    source.mkdir()
    buffer = io.BytesIO()
    Image.new("L", (300, 200), 245).save(buffer, format="JPEG")
    (images / "p1.jpg").write_bytes(buffer.getvalue())
    box = Citation(page_id="p1", bbox=BBox(x0=10, y0=10, x1=50, y1=30))
    page = PageExtraction(
        page_id="p1",
        doc_type="payment_memo",
        values=[ExtractedValue(field_id="M:p1:amount", value="1.00", citation=box)],
    )
    (source / "predictions.jsonl").write_text(page.model_dump_json() + "\n")
    (source / "run.json").write_text(json.dumps({"config": {"extractor": "mock"}}))

    record = experiment.apply_ink(source, target, images)

    assert load_predictions(target / "predictions.jsonl") == [page]  # too little ink: unchanged
    assert record == json.loads((target / "run.json").read_text())
    assert record["derived_from"] == "s1" and record["citations"] == "S1+ink"
    assert record["config"] == {"extractor": "mock"} and record["cost_usd"] == 0.0
    assert record["pages"] == {"p1": {"alpha": None, "beta": None, "inked": 1, "matched": 0}}


def test_the_experiment_refuses_the_test_set():
    with pytest.raises(SystemExit, match="D7"):
        experiment.main(["--split", "test"])
