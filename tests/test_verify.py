"""Blind re-reads, occlusion and the verification policy, offline with MockLLM and MockSegmenter."""

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from archivist.doctypes import REGISTRY, UNRESOLVABLE
from archivist.doctypes.ledger import (
    COLUMNS,
    LEDGER_REREAD,
    LINES,
    MEMO_REREAD,
    LedgerCard,
    PaymentMemo,
)
from archivist.eval import run_eval
from archivist.models.base import Region
from archivist.models.budget import BudgetGuard
from archivist.models.mock import MockLLM, MockSegmenter
from archivist.pipeline import occlusion, reread, verify
from archivist.pipeline.checks import run_checks
from archivist.pipeline.extract import PageExtraction
from archivist.pipeline.verify import Occluder, ReRead, decide
from archivist.schema import (
    BBox,
    Citation,
    ExtractedValue,
    FieldGT,
    Flag,
    PageGT,
    ledger_header_id,
    ledger_line_id,
    memo_field_id,
)

WIDTH, HEIGHT = 400, 300
MEMO_VALUES = {
    "memo_no": "008348",
    "date": "02/01/86",
    "account_no": "57663909",
    "counterparty": "Eastmoor Electricity Board",
    "amount": "65.48",
    "amount_words": "Sixty-five pounds and forty-eight pence",
    "ledger_ref": "Sheet 32 / Line 02",
}


def _box(k: int) -> BBox:
    return BBox(x0=20, y0=20 + 35 * k, x1=220, y1=45 + 35 * k)


def _value(field_id: str, text: str | None, box: BBox | None = None) -> ExtractedValue:
    box = box or _box(0)
    return ExtractedValue(
        field_id=field_id,
        value=text,
        citation=Citation(page_id="m1", bbox=box),
        abstained=text is None,
    )


def _flag(field_id: str, suggested: str | None = None, detail: str = "line 01 fails") -> Flag:
    return Flag(field_id=field_id, check="arithmetic", detail=detail, suggested=suggested)


def _decide(value, flags=(), occluders=(), reading=None, reread_flags=(), balances=False):
    return decide(
        "m1", "payment_memo", value, list(flags), list(occluders), reading, reread_flags, balances
    )


AMOUNT = memo_field_id("m1", "amount")
PAYEE = memo_field_id("m1", "counterparty")
ACCOUNT = memo_field_id("m1", "account_no")
STAMP = Occluder(label="stamp", bbox=_box(0), cover=0.4)


# --- The re-read prompt ----------------------------------------------------------------------


def test_every_field_has_a_reread_prompt_that_names_its_document_and_field():
    for plugin, table in ((LedgerCard(), LEDGER_REREAD), (PaymentMemo(), MEMO_REREAD)):
        for field_id in plugin.field_ids("p1"):
            prompt = plugin.reread_prompt(field_id)
            assert table[field_id.rsplit(":", 1)[-1]] in prompt
            assert "ledger card" in prompt or "payment memorandum" in prompt
    assert "the Balance column of a ledger card line" in LedgerCard().reread_prompt(
        "L:p1:03:balance"
    )


def test_reread_prompts_hold_no_digits_so_no_value_can_leak():
    for plugin in REGISTRY.values():
        for field_id in plugin.field_ids("p1"):
            assert not any(c.isdigit() for c in plugin.reread_prompt(field_id)), field_id


# --- Crops -----------------------------------------------------------------------------------


def test_the_crop_is_padded_by_half_the_height_and_a_fifth_of_the_width():
    box = BBox(x0=100, y0=100, x1=200, y1=140)
    assert reread.crop_box(box, 1000, 1000) == BBox(x0=80, y0=80, x1=220, y1=160)


def test_the_crop_is_clamped_to_the_page_and_rounded_outwards():
    assert reread.crop_box(BBox(x0=5, y0=3, x1=95, y1=33), 100, 40) == BBox(
        x0=0, y0=0, x1=100, y1=40
    )
    assert reread.crop_box(BBox(x0=11, y0=11, x1=22, y1=14), 100, 100) == BBox(
        x0=8, y0=9, x1=25, y1=16
    )


def test_a_box_snapped_to_one_word_is_widened_to_the_extractors_extent_on_its_own_rows():
    word = BBox(x0=475, y0=250, x1=559, y1=267)
    cell = BBox(x0=306, y0=246, x1=731, y1=270)
    assert reread.widen(word, cell) == BBox(x0=306, y0=250, x1=731, y1=267)
    assert reread.widen(word, None) == word


def test_the_crop_region_is_the_corrected_box_widened_to_the_extractors_own():
    raw = BBox(x0=306, y0=246, x1=731, y1=270)
    citation = Citation(page_id="p1", bbox=BBox(x0=475, y0=250, x1=559, y1=267), raw_bbox=raw)
    assert reread.region(citation) == BBox(x0=306, y0=250, x1=731, y1=267)
    assert reread.region(Citation(page_id="p1", bbox=raw)) == raw


def test_the_crop_is_a_png_of_the_padded_box():
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    picture = Image.open(io.BytesIO(reread.crop(image, BBox(x0=100, y0=100, x1=200, y1=140))))
    assert picture.format == "PNG"
    assert picture.size == (140, 80)


def test_a_reread_asks_the_rereader_role_and_retries_a_bad_answer_once():
    answers = iter(["not json", '{"value": "65.48"}'])
    llm = MockLLM(lambda request: next(answers))
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    text, cached = reread.reread(image, _box(1), "Read the amount.", llm)
    assert (text, cached) == ("65.48", False)
    assert [c.role for c in llm.calls] == ["rereader", "rereader"]
    assert llm.calls[1].prompt.endswith(reread.RETRY_NOTE)
    assert llm.calls[0].json_schema == reread.SCHEMA


def test_a_reread_that_never_parses_raises():
    llm = MockLLM(lambda request: '{"value": 3}')
    with pytest.raises(reread.ReReadFailed):
        reread.reread(Image.new("RGB", (50, 50)), BBox(x0=1, y0=1, x1=9, y1=9), "Read it.", llm)


# --- Occlusion -------------------------------------------------------------------------------


def test_the_segmenter_is_asked_once_for_stamps_and_once_for_stains():
    segmenter = MockSegmenter(
        lambda request: [Region(label=request.prompts[0], bbox=_box(2), score=0.9)]
    )
    regions = occlusion.detect(b"page", segmenter)
    assert [c.prompts for c in segmenter.calls] == [("stamp",), ("stain",)]
    assert [c.role for c in segmenter.calls] == ["segmenter", "segmenter"]
    assert [r.label for r in regions] == ["stamp", "stain"]


def test_a_field_is_occluded_when_one_box_covers_a_tenth_of_it():
    value = _value(AMOUNT, "65.48", BBox(x0=0, y0=0, x1=100, y1=10))
    tenth = Region(label="stamp", bbox=BBox(x0=90, y0=0, x1=300, y1=50), score=0.9)
    less = Region(label="stain", bbox=BBox(x0=91, y0=0, x1=300, y1=50), score=0.9)
    assert occlusion.covered(value.citation.bbox, tenth.bbox) == pytest.approx(0.1)
    assert [r.label for r, _ in occlusion.occluders(value, [tenth, less])] == ["stamp"]
    assert occlusion.occluders(value.model_copy(update={"citation": None}), [tenth]) == []


# --- The policy table ------------------------------------------------------------------------


def test_a_money_field_is_reread_too_and_accepted_only_when_both_reads_agree():
    value = _value(AMOUNT, "65.48")
    assert verify.needs_reread(value)
    agrees = _decide(value, reading=ReRead("65.48"))
    assert (agrees.status, agrees.confidence) == ("accepted", 0.99)
    assert (agrees.evidence.route, agrees.evidence.reread_status) == ("arithmetic", "agrees")
    disagrees = _decide(value, reading=ReRead("65.43"))
    assert (disagrees.status, disagrees.confidence) == ("review", 0.3)
    assert disagrees.evidence.proposed is None  # nothing says which read is right


def test_a_flagged_money_field_is_reread_and_its_matching_suggestion_proposed():
    value = _value(AMOUNT, "65.43")
    flag = _flag(AMOUNT, suggested="65.48")
    verdict = _decide(value, [flag], reading=ReRead("65.48"))
    assert (verdict.status, verdict.confidence) == ("review", 0.5)
    assert verdict.value == "65.43"  # never changed
    assert (verdict.evidence.proposed, verdict.evidence.proposed_by) == ("65.48", "check")
    assert verdict.evidence.reread == "65.48"
    reread_flags = [f for f in verdict.flags if f.check == "reread"]
    assert [f.suggested for f in reread_flags] == ["65.48"]
    assert flag in verdict.flags


def test_no_correction_is_proposed_when_the_reread_and_the_suggestion_differ():
    value = _value(AMOUNT, "65.43")
    flag = _flag(AMOUNT, suggested="65.48")
    for reading in ("65.45", "65.43"):
        verdict = _decide(value, [flag], reading=ReRead(reading))
        assert (verdict.status, verdict.confidence) == ("review", 0.3)
        assert verdict.evidence.proposed is None
        assert all(f.suggested is None for f in verdict.flags if f.check == "reread")


def test_reread_values_that_pass_the_checks_the_extraction_fails_are_proposed():
    value = _value(AMOUNT, "65.43")
    verdict = _decide(value, [_flag(AMOUNT)], reading=ReRead("65.48"), balances=True)
    assert (verdict.status, verdict.confidence) == ("review", 0.5)
    assert (verdict.evidence.proposed, verdict.evidence.proposed_by) == ("65.48", "reread_chain")
    assert verdict.value == "65.43"
    # Not when a check fails on the re-read values too, nor when no equation holds for them.
    failing = _decide(
        value, [_flag(AMOUNT)], reading=ReRead("65.48"), reread_flags=[_flag(AMOUNT)],
        balances=True,
    )
    unchecked = _decide(value, [_flag(AMOUNT)], reading=ReRead("65.48"))
    for verdict in (failing, unchecked):
        assert (verdict.confidence, verdict.evidence.proposed) == (0.3, None)
    assert failing.evidence.reread_flags == [_flag(AMOUNT)]


def test_a_check_without_a_suggestion_never_yields_a_proposal():
    verdict = _decide(_value(AMOUNT, "65.43"), [_flag(AMOUNT)], reading=ReRead("65.48"))
    assert (verdict.status, verdict.confidence, verdict.evidence.proposed) == ("review", 0.3, None)


def test_a_non_money_field_is_accepted_when_the_blind_reread_agrees():
    value = _value(PAYEE, "Eastmoor Electricity Board")
    verdict = _decide(value, reading=ReRead("EASTMOOR  electricity board"))
    assert (verdict.status, verdict.confidence) == ("accepted", 0.99)
    assert verdict.evidence.route == "reread"
    assert verdict.evidence.reread_status == "agrees"


def test_a_disagreement_goes_to_review():
    value = _value(PAYEE, "Eastmoon Electricity Board")
    verdict = _decide(value, reading=ReRead("Eastmoor Electricity Board"))
    assert (verdict.status, verdict.confidence) == ("review", 0.3)
    assert verdict.value == "Eastmoon Electricity Board"
    assert verdict.evidence.reread_status == "disagrees"
    assert any(f.check == "reread" and "Eastmoor" in f.detail for f in verdict.flags)


def test_an_illegible_reread_or_a_failed_one_goes_to_review():
    value = _value(PAYEE, "Eastmoor Electricity Board")
    illegible = _decide(value, reading=ReRead(None))
    failed = _decide(value, reading=ReRead(None, error="TimeoutError"))
    assert (illegible.status, illegible.evidence.reread_status) == ("review", "illegible")
    assert (failed.status, failed.evidence.reread_status) == ("review", "failed")
    assert illegible.confidence == failed.confidence == 0.3


def test_a_field_that_needs_a_reread_but_has_no_box_goes_to_review():
    value = _value(PAYEE, "Eastmoor Electricity Board").model_copy(update={"citation": None})
    verdict = _decide(value)
    assert (verdict.status, verdict.evidence.reread_status) == ("review", "no_citation")


def test_a_flagged_field_goes_to_review_even_when_the_reread_agrees_with_it():
    value = _value(ACCOUNT, "57663909")
    flag = _flag(ACCOUNT, suggested="57663900", detail="it fills the gap")
    verdict = _decide(value, [flag], reading=ReRead("57663909"))
    assert (verdict.status, verdict.confidence, verdict.evidence.proposed) == ("review", 0.3, None)


def test_a_non_money_suggestion_the_reread_confirms_is_proposed():
    value = _value(ACCOUNT, "57668909")
    flag = _flag(ACCOUNT, suggested="5766 3909", detail="it fills the gap")
    verdict = _decide(value, [flag], reading=ReRead("57663909"))
    assert (verdict.status, verdict.confidence) == ("review", 0.5)
    assert verdict.evidence.proposed == "5766 3909"


def test_an_unresolvable_note_alone_is_no_reason_for_review():
    value = _value(memo_field_id("m1", "ledger_ref"), "Sheet 32 / Line 02")
    note = Flag(field_id=value.field_id, check="crossdoc", detail=UNRESOLVABLE + "no card")
    verdict = _decide(value, [note], reading=ReRead("Sheet 32 / Line 02"))
    assert (verdict.status, verdict.confidence) == ("accepted", 0.99)
    assert note in verdict.flags


def test_occluded_fields_are_reread_and_accepted_only_on_agreement_with_less_confidence():
    money = _value(AMOUNT, "65.48")
    agrees = _decide(money, occluders=[STAMP], reading=ReRead("65.48"))
    disagrees = _decide(money, occluders=[STAMP], reading=ReRead("66.48"))
    assert (agrees.status, agrees.confidence) == ("accepted", 0.9)
    assert (disagrees.status, disagrees.confidence) == ("review", 0.3)
    payee = _decide(
        _value(PAYEE, "Eastmoor"), occluders=[STAMP], reading=ReRead("Eastmoor")
    )
    assert (payee.status, payee.confidence) == ("accepted", 0.9)
    assert any(f.check == "occlusion" for f in agrees.flags)


def test_an_abstained_field_is_abstained_with_no_confidence_and_no_reread():
    value = _value(PAYEE, None)
    assert not verify.needs_reread(value)
    verdict = _decide(value, occluders=[STAMP])
    assert (verdict.status, verdict.confidence, verdict.value) == ("abstained", 0.0, None)


@pytest.mark.parametrize(
    ("field", "a", "b", "same"),
    [
        ("amount", "1,234.50", "1234.50", True),
        ("amount", "1,234.50", "1,234.56", False),
        ("date", "02/01/86", "2/1/1986", True),
        ("account_no", "5766-3909", "57663909", True),
        ("amount_words", "Sixty-five pounds", "sixty five pounds", True),
        ("amount_words", "Sixty-five pounds", "Sixty-five pounds only", False),
        ("counterparty", "Eastmoor  Board", "EASTMOOR BOARD", True),
        ("counterparty", "", "  ", True),
        ("counterparty", "", "Eastmoor", False),
    ],
)
def test_readings_agree_after_normalisation(field, a, b, same):
    assert verify.same_reading(memo_field_id("m1", field), a, b) is same


# --- The second look (v3) --------------------------------------------------------------------


def _outcomes(verdict) -> dict[str, tuple]:
    return {
        p: (o.status, o.confidence, o.proposed, o.proposed_by) for p, o in verdict.policies.items()
    }


def test_the_second_look_crop_is_padded_by_the_whole_height_and_two_fifths_of_the_width():
    box = BBox(x0=100, y0=100, x1=200, y1=140)
    wider = reread.crop_box(box, 1000, 1000, pad_x=reread.SECOND_PAD_X, pad_y=reread.SECOND_PAD_Y)
    assert wider == BBox(x0=60, y0=60, x1=240, y1=180)
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    assert reread.crop(image, box) != reread.crop(
        image, box, pad_x=reread.SECOND_PAD_X, pad_y=reread.SECOND_PAD_Y
    )


def test_a_second_look_that_agrees_with_the_extractor_accepts_under_v3_only():
    value = _value(PAYEE, "Eastmoor Electricity Board")
    first, second = ReRead("Eastmoon Electricity Board"), ReRead("Eastmoor Electricity Board")
    verdict = decide("m1", "payment_memo", value, [], [], first, second=second)
    assert _outcomes(verdict) == {
        "v2": ("review", 0.3, None, None),
        "v3": ("accepted", 0.99, None, None),
    }
    assert verdict.evidence.second_look_status == "agrees"
    assert verdict.evidence.second_look == "Eastmoor Electricity Board"
    assert any("second look" in f.detail for f in verdict.flags)
    # An illegible first look is given a second one too, and occlusion still lowers confidence.
    second = ReRead("EASTMOOR ELECTRICITY BOARD")
    illegible = decide("m1", "payment_memo", value, [], [STAMP], ReRead(None), second=second)
    assert _outcomes(illegible)["v3"] == ("accepted", 0.9, None, None)


def test_a_second_look_that_agrees_is_not_enough_when_a_check_fails():
    value = _value(AMOUNT, "65.43")
    flag = _flag(AMOUNT, suggested="65.48")
    verdict = decide(
        "m1", "payment_memo", value, [flag], [], ReRead("65.48"), second=ReRead("65.43")
    )
    assert _outcomes(verdict) == {
        "v2": ("review", 0.5, "65.48", "check"),
        "v3": ("review", 0.3, None, None),  # the looks split, so nothing is proposed
    }


def test_two_looks_that_agree_with_each_other_and_not_the_extractor_are_proposed():
    value = _value(PAYEE, "Eastmoon Electricity Board")
    first, second = ReRead("Eastmoor Electricity Board"), ReRead("EASTMOOR electricity board")
    verdict = decide("m1", "payment_memo", value, [], [], first, second=second)
    assert _outcomes(verdict) == {
        "v2": ("review", 0.3, None, None),
        "v3": ("review", 0.5, "Eastmoor Electricity Board", "second_look"),
    }
    assert verdict.value == "Eastmoon Electricity Board"  # never changed


def test_looks_that_differ_from_each_other_go_to_review_with_nothing_proposed():
    value = _value(AMOUNT, "65.43")
    for second in (ReRead("65.45"), ReRead(None)):
        verdict = decide(
            "m1", "payment_memo", value, [_flag(AMOUNT)], [], ReRead("65.48"), [], True, second
        )
        assert _outcomes(verdict)["v2"] == ("review", 0.5, "65.48", "reread_chain")
        assert _outcomes(verdict)["v3"] == ("review", 0.3, None, None)
    both_illegible = decide("m1", "payment_memo", value, [], [], ReRead(None), second=ReRead(None))
    assert _outcomes(both_illegible)["v3"] == ("review", 0.3, None, None)
    assert both_illegible.evidence.second_look_status == "illegible"


def test_a_failed_second_look_is_no_look_and_an_agreeing_first_look_needs_none():
    value = _value(AMOUNT, "65.43")
    flags, timeout = [_flag(AMOUNT, suggested="65.48")], ReRead(None, error="TimeoutError: slow")
    failed = decide("m1", "payment_memo", value, flags, [], ReRead("65.48"), second=timeout)
    assert _outcomes(failed)["v3"] == _outcomes(failed)["v2"] == ("review", 0.5, "65.48", "check")
    assert failed.evidence.second_look_status == "failed"
    agrees = decide("m1", "payment_memo", value, [], [], ReRead("65.43"), second=ReRead("1.00"))
    assert _outcomes(agrees)["v3"] == ("accepted", 0.99, None, None)
    assert agrees.evidence.second_look_status == "not_reread"


def test_a_verdict_carries_its_policys_outcome_and_can_be_read_as_the_other():
    value = _value(PAYEE, "Eastmoor Electricity Board")
    args = ("m1", "payment_memo", value, [], [], ReRead("Eastmoon Electricity Board"))
    second = ReRead("Eastmoor Electricity Board")
    as_v2 = decide(*args, second=second, policy="v2")
    as_v3 = decide(*args, second=second, policy="v3")
    assert (as_v2.policy, as_v2.status, as_v3.policy, as_v3.status) == (
        "v2", "review", "v3", "accepted"
    )
    assert verify.as_policy(as_v2, "v3") == as_v3
    assert verify.as_policy(as_v3, "v2") == as_v2
    old = as_v2.model_copy(update={"policies": {}})  # a verdict written before v3 existed
    assert verify.as_policy(old, "v2") is old
    with pytest.raises(ValueError):
        verify.as_policy(old, "v3")
    abstained = decide("m1", "payment_memo", _value(PAYEE, None), [], [], None)
    assert {o.status for o in abstained.policies.values()} == {"abstained"}


# --- The whole run, with mocks ---------------------------------------------------------------


def _memo_page(values: dict[str, str | None]) -> PageExtraction:
    fields = list(MEMO_VALUES)
    return PageExtraction(
        page_id="m1",
        doc_type="payment_memo",
        values=[
            _value(memo_field_id("m1", name), values[name], _box(k))
            for k, name in enumerate(fields)
        ],
    )


def _image(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "m1.jpg"
    Image.new("RGB", (WIDTH, HEIGHT), "white").save(path, format="JPEG")
    return path


def _rereader(answers: dict[str, str | None]) -> MockLLM:
    """Answers by the field its prompt names, so it never sees what was extracted."""

    def respond(request) -> str:
        name = next(n for n, what in MEMO_REREAD.items() if what in request.prompt)
        return json.dumps({"value": answers[name]})

    return MockLLM(respond)


def _stamp_on(k: int) -> MockSegmenter:
    def respond(request):
        stamp = Region(label="stamp", bbox=_box(k), score=0.9)
        return [stamp] if request.prompts == ("stamp",) else []

    return MockSegmenter(respond)


def test_verify_rereads_what_the_policy_asks_and_never_shows_the_extracted_values(tmp_path):
    extracted = MEMO_VALUES | {"counterparty": "Eastmoon Electricity Board", "amount": "65.43"}
    answers = MEMO_VALUES | {"amount": "65.48"}
    llm = _rereader(answers)
    segmenter = _stamp_on(1)  # covers the date
    page = _memo_page(extracted)
    verdicts, calls = verify.verify(
        [page],
        {"m1": _image(tmp_path)},
        {"segmenter": segmenter, "rereader": llm},
        correct_citations=False,
    )
    by_name = {v.field_id.rsplit(":", 1)[-1]: verify.as_policy(v, "v2") for v in verdicts}
    # The words say 65.48, so the figures are flagged with that suggestion; the re-read agrees.
    assert by_name["amount"].evidence.proposed == "65.48"
    assert (by_name["amount"].status, by_name["amount"].confidence) == ("review", 0.5)
    assert (by_name["counterparty"].status, by_name["counterparty"].confidence) == ("review", 0.3)
    # The words are flagged with the figures; the re-read agrees with them, but a check failed.
    assert (by_name["amount_words"].status, by_name["amount_words"].confidence) == ("review", 0.3)
    assert (by_name["date"].status, by_name["date"].confidence) == ("accepted", 0.9)
    assert by_name["memo_no"].status == "accepted"
    # v3 took a second look at the two disagreements; both looks read the payee the same way.
    v3 = {v.field_id.rsplit(":", 1)[-1]: verify.as_policy(v, "v3") for v in verdicts}
    assert (v3["counterparty"].status, v3["counterparty"].confidence) == ("review", 0.5)
    assert v3["counterparty"].evidence.proposed == "Eastmoor Electricity Board"
    assert v3["counterparty"].evidence.proposed_by == "second_look"
    # The amount's looks agree too; v2 had proposed the same reading, so its provenance stays.
    assert v3["amount"].evidence.proposed == "65.48"
    assert v3["amount"].evidence.proposed_by == by_name["amount"].evidence.proposed_by
    assert [v.value for v in verdicts] == [extracted[n] for n in MEMO_VALUES]
    assert calls["rereads"] == len(MEMO_VALUES)  # 6 others + flagged amount
    assert calls["second_looks"] == 2
    assert len(llm.calls) == calls["rereads"] + calls["second_looks"]
    for request in llm.calls:
        for text in extracted.values():
            assert text not in request.prompt
    assert len(segmenter.calls) == 2


def test_a_reread_that_fails_sends_its_field_to_review_without_stopping_the_run(tmp_path):
    def respond(request) -> str:
        if MEMO_REREAD["counterparty"] in request.prompt:
            raise TimeoutError("slow")
        return json.dumps({"value": "x"})

    verdicts, calls = verify.verify(
        [_memo_page(MEMO_VALUES)],
        {"m1": _image(tmp_path)},
        {"segmenter": MockSegmenter(), "rereader": MockLLM(respond)},
        correct_citations=False,
    )
    payee = next(v for v in verdicts if v.field_id == PAYEE)
    assert (payee.status, payee.evidence.reread_status) == ("review", "failed")
    assert calls["rereads_failed"] == 1


# --- Reading twice: a misreading that adds up ------------------------------------------------

CARD = "c1"
CARD_IDS = LedgerCard().field_ids(CARD)
CARD_LINES = [  # date, particulars, debit, credit, balance, as printed, from 1,000.00
    ("02/01/86", "CASH", "50.00", "", "950.00"),
    ("05/01/86", "CHQ 889341", "39.06", "", "910.94"),
    ("09/01/86", "SALARY", "", "500.00", "1,410.94"),
    ("12/01/86", "CASH", "20.00", "", "1,390.94"),
]


def _card_printed() -> dict[str, str]:
    printed = {
        ledger_header_id(CARD, "account_no"): "34192727",
        ledger_header_id(CARD, "holder"): "Mr Dennis Atkinson",
        ledger_header_id(CARD, "sheet_no"): "32",
        ledger_header_id(CARD, "brought_forward"): "1,000.00",
        ledger_header_id(CARD, "carried_forward"): "1,390.94",
    }
    for no in LINES:
        cells = CARD_LINES[no - 1] if no <= len(CARD_LINES) else ("",) * len(COLUMNS)
        printed |= {ledger_line_id(CARD, no, c): t for c, t in zip(COLUMNS, cells, strict=True)}
    return printed


def _card_box(i: int) -> BBox:
    x0, y0 = 20 + 200 * (i % 5), 20 + 40 * (i // 5)
    return BBox(x0=x0, y0=y0, x1=x0 + 180, y1=y0 + 30)


def _card_image(folder: Path) -> Path:
    """Each field's box filled with its own shade of red, so a crop shows whose cell it is."""
    image = Image.new("RGB", (1020, 800), "white")
    draw = ImageDraw.Draw(image)
    for i in range(len(CARD_IDS)):
        box = _card_box(i)
        draw.rectangle([box.x0, box.y0, box.x1 - 1, box.y1 - 1], fill=(i + 1, 0, 0))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{CARD}.png"
    image.save(path)
    return path


def _card_page(values: dict[str, str]) -> PageExtraction:
    return PageExtraction(
        page_id=CARD,
        doc_type="ledger_card",
        values=[
            ExtractedValue(
                field_id=f, value=values[f], citation=Citation(page_id=CARD, bbox=_card_box(i))
            )
            for i, f in enumerate(CARD_IDS)
        ],
    )


def _cell_rereader(answers: dict[str, str]) -> MockLLM:
    """Reads the one cell in the crop, told apart by the shade at its centre; sees nothing else."""

    def respond(request) -> str:
        crop = Image.open(io.BytesIO(request.images[0])).convert("RGB")
        shade = crop.getpixel((crop.width // 2, crop.height // 2))[0]
        return json.dumps({"value": answers[CARD_IDS[shade - 1]]})

    return MockLLM(respond)


def _verify_card(extracted: dict, answers: dict, folder: Path) -> dict[str, verify.VerdictRecord]:
    verdicts, _ = verify.verify(
        [_card_page(extracted)],
        {CARD: _card_image(folder)},
        {"segmenter": MockSegmenter(), "rereader": _cell_rereader(answers)},
        correct_citations=False,
    )
    return {v.field_id: v for v in verdicts}


def test_a_misread_debit_carried_through_every_later_balance_goes_to_review_with_the_rereads(
    tmp_path,
):
    printed = _card_printed()
    misread = {
        ledger_line_id(CARD, 2, "debit"): "34.06",
        ledger_line_id(CARD, 2, "balance"): "915.94",
        ledger_line_id(CARD, 3, "balance"): "1,415.94",
        ledger_line_id(CARD, 4, "balance"): "1,395.94",
        ledger_header_id(CARD, "carried_forward"): "1,395.94",
    }
    extracted = printed | misread
    # The extracted chain adds up: the arithmetic alone passes every one of these.
    assert run_checks([_card_page(extracted)]) == []

    verdicts = _verify_card(extracted, printed, tmp_path)

    for field_id, wrong in misread.items():
        verdict = verdicts[field_id]
        assert (verdict.status, verdict.confidence, verdict.value) == ("review", 0.5, wrong)
        evidence = verdict.evidence
        assert (evidence.proposed, evidence.proposed_by) == (printed[field_id], "reread_chain")
        assert evidence.reread_balances and evidence.reread_flags == []
        assert not [f for f in verdict.flags if f.check == "arithmetic"]
    rest = [v for field_id, v in verdicts.items() if field_id not in misread]
    assert {(v.status, v.evidence.reread_status) for v in rest} == {("accepted", "agrees")}


def test_a_lone_misread_by_the_rereader_breaks_its_own_chain_and_proposes_nothing(tmp_path):
    printed = _card_printed()
    balance = ledger_line_id(CARD, 3, "balance")

    verdicts = _verify_card(printed, printed | {balance: "1,470.94"}, tmp_path)

    verdict = verify.as_policy(verdicts[balance], "v2")
    assert (verdict.status, verdict.confidence, verdict.evidence.proposed) == ("review", 0.3, None)
    assert verdict.evidence.reread_flags and not verdict.evidence.reread_balances
    for policy in verify.POLICIES:
        statuses = {f: verify.as_policy(v, policy).status for f, v in verdicts.items()}
        assert [f for f, status in statuses.items() if status != "accepted"] == [balance]
    # This re-reader misreads the cell the same way from any crop, so under v3 its two looks agree
    # and their reading is proposed: still only a proposal, for a field that goes to review.
    assert _outcomes(verdicts[balance])["v3"] == ("review", 0.5, "1,470.94", "second_look")


def _gt_page() -> PageGT:
    return PageGT(
        page_id="m1",
        doc_type="memo",
        image_path="images/m1.jpg",
        width=WIDTH,
        height=HEIGHT,
        severity=3,
        fields=[
            FieldGT(field_id=memo_field_id("m1", name), printed=text, bbox=_box(k))
            for k, (name, text) in enumerate(MEMO_VALUES.items())
        ],
        artefacts=[],
        source_errors=[],
    )


def test_a_verdict_run_is_written_and_scored_against_the_baseline(tmp_path):
    runs, gt = tmp_path / "runs", tmp_path / "gt"
    source = runs / "base"
    source.mkdir(parents=True)
    extracted = MEMO_VALUES | {"counterparty": "Eastmoon Electricity Board", "amount": "65.43"}
    (source / "predictions.jsonl").write_text(_memo_page(extracted).model_dump_json() + "\n")
    images = _image(tmp_path / "images").parent
    (source / "run.json").write_text(json.dumps({"images": str(images), "citations": "S0+ink"}))
    gt.mkdir()
    (gt / "m1.json").write_text(_gt_page().model_dump_json())

    record = verify.run(
        source,
        runs / "checked",
        {"segmenter": MockSegmenter(), "rereader": _rereader(MEMO_VALUES | {"amount": "65.48"})},
        guard=BudgetGuard(1.0, tmp_path / "ledger.jsonl"),
        config={"rereader": {"backend": "mock"}},
    )
    assert record["counts"]["by_status"] == {"accepted": 4, "review": 3}
    assert record["citations"] == "S0+ink"
    assert record["cost_usd"] == 0.0

    assert record["policy"]["version"] == verify.POLICY
    assert record["counts"]["by_policy"]["v2"]["proposed_corrections"] == 1
    assert record["counts"]["by_policy"]["v3"]["proposed_corrections"] == 2
    assert record["calls"]["second_looks"] == 2 and record["cost_full_usd"] == 0.0

    v3 = run_eval.evaluate_verdicts(runs / "checked", gt, "v3")["overall"]["archivist"]
    assert (v3["n_proposed"], v3["proposal_fixes"]) == (2, 2)  # the payee too, from two looks
    metrics = run_eval.evaluate_verdicts(runs / "checked", gt, "v2")
    assert metrics["policy_scored"] == "v2"
    ours, base = metrics["overall"]["archivist"], metrics["overall"]["baseline"]
    assert (ours["n_wrong"], ours["errors_caught"], ours["errors_missed"]) == (2, 2, 0)
    assert (ours["false_alarms"], ours["error_rate_accepted"]) == (1, 0.0)  # the words
    assert (ours["n_proposed"], ours["proposal_fixes"]) == (1, 1)
    # The payee and the flagged amount were re-read; neither re-read agreed with the misread.
    assert (ours["reread_on_wrong"], ours["independence"]) == (2, 0.0)
    assert ours["risk_coverage"][0] == [round(4 / 7, 4), 0.0]
    assert (base["errors_caught"], base["errors_missed"]) == (0, 2)
    assert base["error_rate_accepted"] == pytest.approx(2 / 7)
    assert set(metrics["by_route"]) == {"arithmetic", "reread"}
    assert metrics["baseline_run"] == "base"
    assert metrics["missed"] == []

    (runs / "checked" / "metrics.json").write_text(json.dumps(metrics))
    rows = run_eval.verdict_comparison([runs / "checked"])
    assert [(name, r["kind"]) for name, r in rows.items()] == [
        ("base", "baseline"),
        ("checked", "archivist"),
    ]
    assert (rows["base"]["errors_missed"], rows["checked"]["errors_caught"]) == (2, 2)
    assert "checked" in run_eval.comparison_table(rows)
