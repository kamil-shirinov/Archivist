"""The citation experiment's and the validation's decision rules, the offline +ink step and the
wrong-field rate, with no model involved."""

import io
import json

import pytest
from PIL import Image

from archivist.eval import citation_experiment as experiment
from archivist.pipeline.extract import PageExtraction, load_predictions
from archivist.schema import BBox, Citation, ExtractedValue, FieldGT, PageGT


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


def test_the_rule_judges_only_the_variants_it_is_given():
    variants = {"S0": _variant(0.45, 0.960), "S1": _variant(0.60, 0.960)}
    assert experiment.choose(variants) == "S1"


def _validated(s0: float, ink: float, wrong_s0: float, wrong_ink: float) -> dict:
    return {
        "S0": {**_variant(s0, 0.96), "wrong_field_rate": {"all": wrong_s0}},
        "S0+ink": {**_variant(ink, 0.96), "wrong_field_rate": {"all": wrong_ink}},
    }


@pytest.mark.parametrize(
    "s0, ink, wrong_s0, wrong_ink, adopted",
    [
        (0.45, 0.95, 0.19, 0.00, "S0+ink"),
        (0.45, 0.65, 0.19, 0.19, "S0+ink"),  # exactly 20 points and no more wrong fields
        (0.45, 0.64, 0.19, 0.00, "S0"),  # 19 points
        (0.45, 0.95, 0.10, 0.11, "S0"),  # more citations inside another field's box
        (None, 0.95, 0.10, 0.00, "S0"),  # nothing to compare against
    ],
)
def test_s0_ink_is_adopted_only_for_20_points_and_no_more_wrong_fields(
    s0, ink, wrong_s0, wrong_ink, adopted
):
    assert experiment.adopt(_validated(s0, ink, wrong_s0, wrong_ink)) == adopted


def _gt_page(page_id: str, doc_type: str) -> PageGT:
    fields = [
        FieldGT(field_id=f"{page_id}:a", printed="1", bbox=BBox(x0=0, y0=0, x1=100, y1=20)),
        FieldGT(field_id=f"{page_id}:b", printed="2", bbox=BBox(x0=0, y0=40, x1=100, y1=60)),
    ]
    return PageGT(
        page_id=page_id,
        doc_type=doc_type,
        image_path=f"images/{page_id}.jpg",
        width=200,
        height=100,
        severity=0,
        fields=fields,
        artefacts=[],
        source_errors=[],
    )


def _cited(page_id: str, field: str, y: int, on: str | None = None) -> ExtractedValue:
    box = BBox(x0=10, y0=y, x1=90, y1=y + 10)
    citation = Citation(page_id=on or page_id, bbox=box)
    return ExtractedValue(field_id=f"{page_id}:{field}", value="1", citation=citation)


def test_the_wrong_field_rate_counts_citations_centred_in_another_fields_box(tmp_path):
    gt, run = tmp_path / "gt", tmp_path / "run"
    gt.mkdir()
    run.mkdir()
    for page in (_gt_page("c1", "ledger"), _gt_page("m1", "memo")):
        (gt / f"{page.page_id}.json").write_text(page.model_dump_json())
    pages = [
        PageExtraction(
            page_id="c1",
            doc_type="ledger_card",
            values=[
                _cited("c1", "a", 45),  # inside b's box
                _cited("c1", "b", 45),  # its own
                _cited("c1", "x", 5),  # not a field: ignored
            ],
        ),
        PageExtraction(
            page_id="m1",
            doc_type="payment_memo",
            values=[
                _cited("m1", "a", 25),  # between the boxes: wrong place, but no other field
                _cited("m1", "b", 5, on="c1"),  # another page: not another field of this one
            ],
        ),
    ]
    (run / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))

    assert experiment.wrong_field_rate(run, gt) == {"all": 1 / 4, "ledger": 1 / 2, "memo": 0.0}


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

    record = experiment.apply_ink(source, target, images, strategy="S0+ink")

    assert load_predictions(target / "predictions.jsonl") == [page]  # too little ink: unchanged
    assert record == json.loads((target / "run.json").read_text())
    assert record["derived_from"] == "s1" and record["citations"] == "S0+ink"
    assert record["config"] == {"extractor": "mock"} and record["cost_usd"] == 0.0
    assert record["pages"] == {
        "p1": {"alpha": None, "beta": None, "gamma": None, "inked": 1, "matched": 0}
    }


@pytest.mark.parametrize("validate", [[], ["--validate"]])
def test_the_experiment_refuses_the_test_set(validate):
    with pytest.raises(SystemExit, match="D7"):
        experiment.main(["--split", "test", *validate])


def test_validation_refuses_the_split_the_correction_was_built_on():
    with pytest.raises(SystemExit, match="has not seen"):
        experiment.main(["--split", "dev", "--validate"])
