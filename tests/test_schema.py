import pytest
from pydantic import ValidationError

from archivist.schema import (
    Artefact,
    BBox,
    FieldGT,
    FieldVerdict,
    PageGT,
    SourceError,
    ledger_header_id,
    ledger_line_id,
    memo_field_id,
)


def test_bbox_rejects_non_positive_extent():
    with pytest.raises(ValidationError):
        BBox(x0=10, y0=0, x1=10, y1=5)
    with pytest.raises(ValidationError):
        BBox(x0=10, y0=0, x1=4, y1=5)
    with pytest.raises(ValidationError):
        BBox(x0=0, y0=5, x1=10, y1=5)


def test_bbox_area():
    assert BBox(x0=2, y0=3, x1=7, y1=5).area() == 10


def test_iou_identical_and_disjoint():
    a = BBox(x0=0, y0=0, x1=10, y1=10)
    assert a.iou(a) == 1.0
    assert a.iou(BBox(x0=20, y0=20, x1=30, y1=30)) == 0.0
    assert a.iou(BBox(x0=10, y0=0, x1=20, y1=10)) == 0.0  # touching edge only


def test_iou_partial_overlap():
    a = BBox(x0=0, y0=0, x1=10, y1=10)
    b = BBox(x0=5, y0=0, x1=15, y1=10)
    assert a.iou(b) == pytest.approx(50 / 150)


def _page() -> PageGT:
    box = BBox(x0=10, y0=20, x1=110, y1=50)
    return PageGT(
        page_id="p1",
        doc_type="ledger",
        image_path="data/dev/p1.png",
        width=800,
        height=1000,
        severity=2,
        fields=[
            FieldGT(
                field_id=ledger_line_id("d1", 1, "balance"),
                printed="4,375.50",
                bbox=box,
                occluded_by=["a1"],
            ),
            FieldGT(field_id=ledger_line_id("d1", 2, "credit"), printed="", bbox=box),
        ],
        artefacts=[Artefact(artefact_id="a1", kind="stamp", bbox=box)],
        source_errors=[
            SourceError(
                kind="balance_arithmetic",
                field_ids=[ledger_line_id("d1", 1, "balance")],
                note="running balance off by 10.00",
            )
        ],
    )


def test_pagegt_json_round_trip():
    page = _page()
    assert PageGT.model_validate_json(page.model_dump_json()) == page


def test_ledger_line_id():
    assert ledger_line_id("d1", 3, "debit") == "L:d1:03:debit"
    assert ledger_line_id("d1", 12, "balance") == "L:d1:12:balance"
    with pytest.raises(ValueError):
        ledger_line_id("d1", 1, "memo")


def test_ledger_header_id():
    assert ledger_header_id("d1", "carried_forward") == "L:d1:hdr:carried_forward"
    with pytest.raises(ValueError):
        ledger_header_id("d1", "amount")


def test_memo_field_id():
    assert memo_field_id("m7", "amount_words") == "M:m7:amount_words"
    with pytest.raises(ValueError):
        memo_field_id("m7", "balance")


def test_severity_out_of_range_rejected():
    data = _page().model_dump()
    for bad in (4, -1):
        with pytest.raises(ValidationError):
            PageGT.model_validate({**data, "severity": bad})


def test_confidence_out_of_range_rejected():
    ok = FieldVerdict(field_id="f", value="1", confidence=1.0, status="accepted")
    assert ok.flags == []
    for bad in (1.5, -0.1):
        with pytest.raises(ValidationError):
            FieldVerdict(field_id="f", value="1", confidence=bad, status="accepted")
