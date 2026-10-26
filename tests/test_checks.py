"""The documents' own checksums, on hand-made pages: no model, no ground truth."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from archivist.doctypes import REGISTRY, is_unresolvable
from archivist.doctypes.ledger import (
    LINES,
    LedgerCard,
    PaymentMemo,
    calendar_date,
    money,
)
from archivist.doctypes.words import parse_amount_words
from archivist.eval.run_eval import checks_report, checks_table
from archivist.pipeline import checks
from archivist.pipeline.extract import PageExtraction
from archivist.schema import (
    BBox,
    ExtractedValue,
    FieldGT,
    Flag,
    PageGT,
    SourceError,
    ledger_header_id,
    ledger_line_id,
    memo_field_id,
)

ACCOUNT = "34192727"
HOLDER = "Mr Dennis Atkinson"

# Sheet 31: ten lines from 2,140.00, cheques 889338 to 889340, all in December 1985.
SHEET_31 = [
    ("01/12/85", "CHQ 889338", "375.50", ""),
    ("03/12/85", "SALARY", "", "1,429.73"),
    ("04/12/85", "CASH", "150.00", ""),
    ("09/12/85", "DIRECT DEBIT ELECTRICITY", "24.85", ""),
    ("14/12/85", "CHQ 889339", "387.03", ""),
    ("17/12/85", "BANK CHARGES", "2.50", ""),
    ("19/12/85", "DIVIDEND", "", "95.76"),
    ("21/12/85", "STANDING ORDER RATES", "69.45", ""),
    ("24/12/85", "CHQ 889340", "265.25", ""),
    ("27/12/85", "CASH", "45.00", ""),
]
SHEET_32 = [
    ("02/01/86", "STANDING ORDER RATES", "25.14", ""),
    ("03/01/86", "DIRECT DEBIT ELECTRICITY", "65.48", ""),
    ("09/01/86", "CHQ 889341", "404.56", ""),
    ("14/01/86", "CREDIT TRANSFER", "", "358.01"),
    ("18/01/86", "CHQ 889342", "18.22", ""),
]
SHEET_33 = [
    ("02/02/86", "CHQ 889343", "50.29", ""),
    ("07/02/86", "SALARY", "", "1,561.68"),
    ("13/02/86", "CASH", "80.00", ""),
]


def _fmt(value: Decimal) -> str:
    return f"{value:,.2f}"


def _balances(start: str, entries) -> list[str]:
    balance, out = Decimal(start.replace(",", "")), []
    for _, _, debit, credit in entries:
        balance += Decimal((credit or "0").replace(",", "")) - Decimal(
            (debit or "0").replace(",", "")
        )
        out.append(_fmt(balance))
    return out


def _page(page_id: str, doc_type: str, field_ids: list[str], values: dict) -> PageExtraction:
    return PageExtraction(
        page_id=page_id,
        doc_type=doc_type,
        values=[
            ExtractedValue(
                field_id=f,
                value=values.get(f, ""),
                citation=None,
                abstained=f in values and values[f] is None,
            )
            for f in field_ids
        ],
    )


def _card(
    page_id: str,
    sheet: int,
    brought: str,
    entries,
    *,
    account: str = ACCOUNT,
    holder: str = HOLDER,
    changes: dict[str, str | None] | None = None,
) -> PageExtraction:
    """A card whose balances add up, then `changes` keyed "05:balance" or "hdr:carried_forward"."""
    balances = _balances(brought, entries)
    values = {
        ledger_header_id(page_id, "account_no"): account,
        ledger_header_id(page_id, "holder"): holder,
        ledger_header_id(page_id, "sheet_no"): str(sheet),
        ledger_header_id(page_id, "brought_forward"): brought,
        ledger_header_id(page_id, "carried_forward"): balances[-1] if balances else brought,
    }
    for no, ((day, description, debit, credit), balance) in enumerate(zip(entries, balances), 1):
        row = dict(date=day, description=description, debit=debit, credit=credit, balance=balance)
        for column, text in row.items():
            values[ledger_line_id(page_id, no, column)] = text
    for key, text in (changes or {}).items():
        line, column = key.split(":")
        field_id = (
            ledger_header_id(page_id, column)
            if line == "hdr"
            else ledger_line_id(page_id, int(line), column)
        )
        values[field_id] = text
    return _page(page_id, "ledger_card", LedgerCard().field_ids(page_id), values)


def _memo(page_id: str, **fields: str | None) -> PageExtraction:
    values = {
        "memo_no": "008348",
        "date": "02/01/86",
        "account_no": ACCOUNT,
        "counterparty": "Eastmoor Electricity Board",
        "amount": "65.48",
        "amount_words": "Sixty-five pounds and forty-eight pence",
        "ledger_ref": "Sheet 32 / Line 02",
    } | fields
    ids = PaymentMemo().field_ids(page_id)
    return _page(
        page_id,
        "payment_memo",
        ids,
        {memo_field_id(page_id, name): text for name, text in values.items()},
    )


def _sheets(**changes) -> list[PageExtraction]:
    """Sheets 31 to 33 of one account; changes is {page_id: {key: text}}."""
    b32 = _balances("2,140.00", SHEET_31)[-1]
    b33 = _balances(b32, SHEET_32)[-1]
    return [
        _card("c31", 31, "2,140.00", SHEET_31, changes=changes.get("c31")),
        _card("c32", 32, b32, SHEET_32, changes=changes.get("c32")),
        _card("c33", 33, b33, SHEET_33, changes=changes.get("c33")),
    ]


def _flags(pages: list[PageExtraction]) -> list[Flag]:
    return checks.run_checks(pages)


def _by_field(flags: list[Flag]) -> dict[str, list[Flag]]:
    out: dict[str, list[Flag]] = {}
    for flag in flags:
        out.setdefault(flag.field_id, []).append(flag)
    return out


# --- parsing -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("words", "amount"),
    [
        ("Three hundred and forty-six pounds and thirty pence", "346.30"),
        ("Nineteen pounds and one penny", "19.01"),
        ("Sixty eight pounds and forty six pence", "68.46"),
        ("Three hundred and fortysix pounds and thirty pence", "346.30"),
        ("Seventy four pounds and thirty pence.", "74.30"),
        ("Two thousand, one hundred and five pounds only", "2105.00"),
        ("One pound", "1.00"),
        ("Fifty pence", "0.50"),
        ("A hundred pounds and no pence", "100.00"),
        ("One million two hundred thousand pounds", "1200000.00"),
    ],
)
def test_amounts_in_words_read_back_to_figures(words, amount):
    assert parse_amount_words(words) == Decimal(amount)


@pytest.mark.parametrize(
    "words",
    ["", "pounds", "Sixty-three pounds and a hundred and five pence", "Sixty-three quid",
     "hundred pounds", "Twelve pounds and fifty"],
)
def test_text_that_states_no_amount_raises(words):
    with pytest.raises(ValueError):
        parse_amount_words(words)


def test_the_parsers_never_borrow_from_the_generator():
    for module in ("words.py", "ledger.py"):
        source = (Path("src/archivist/doctypes") / module).read_text()
        assert "archivist.synth" not in source


def test_money_and_dates_are_read_as_a_clerk_writes_them():
    assert money("1,234.56") == Decimal("1234.56")
    assert money("£12.50") == Decimal("12.50")
    assert money("40.00 DR") == Decimal("-40.00")
    for text in ("346,30", "12.5", "1,23.00", "12", "abc"):
        assert money(text) is None
    assert calendar_date("02/01/86").year == 1986
    assert calendar_date("2/1/1986").month == 1
    assert calendar_date("31/02/85") is None


# --- a card on its own -------------------------------------------------------------------------


def test_a_card_that_adds_up_raises_nothing():
    assert _flags(_sheets()) == []


def test_a_misread_balance_breaks_two_equations_and_the_right_value_is_suggested():
    right = _balances("2,140.00", SHEET_31)[4]  # line 05
    flags = _flags([_card("c31", 31, "2,140.00", SHEET_31, changes={"05:balance": "1,746.50"})])
    assert [(f.field_id, f.check, f.suggested) for f in flags] == [
        (ledger_line_id("c31", 5, "balance"), "arithmetic", right)
    ]
    assert "1,746.50" in flags[0].detail and right in flags[0].detail


def test_a_misread_last_balance_is_mended_by_the_carried_forward():
    right = _balances("2,140.00", SHEET_31)[-1]
    flags = _flags([_card("c31", 31, "2,140.00", SHEET_31, changes={"10:balance": "9.99"})])
    assert [(f.field_id, f.suggested) for f in flags] == [
        (ledger_line_id("c31", 10, "balance"), right)
    ]


def test_the_first_example_in_the_brief_reads_as_stated():
    entries = [("01/12/85", "CHQ 889338", "375.50", "")]
    flags = _flags([_card("c", 1, "2,140.00", entries, changes={"01:balance": "1,746.50"})])
    assert flags[0].detail.startswith(
        "line 01: 2,140.00 − 375.50 + 0.00 = 1,764.50, but the balance reads 1,746.50"
    )


def test_a_misread_amount_breaks_one_equation_and_the_implied_amount_is_suggested():
    flags = _by_field(
        _flags([_card("c31", 31, "2,140.00", SHEET_31, changes={"03:debit": "160.00"})])
    )
    assert set(flags) == {ledger_line_id("c31", 3, "debit"), ledger_line_id("c31", 3, "balance")}
    assert flags[ledger_line_id("c31", 3, "debit")][0].suggested == "150.00"
    assert flags[ledger_line_id("c31", 3, "balance")][0].suggested is None


def test_a_clerks_error_looks_like_a_misread_amount_and_is_flagged_the_same_way():
    # The clerk wrote 4,952.50 for 4,952.59 and carried on from what was written.
    entries = [
        ("06/12/80", "INTEREST", "", "27.56"),
        ("09/12/80", "CASH", "130.00", ""),
        ("15/12/80", "CREDIT TRANSFER", "", "182.49"),
    ]
    page = _card(
        "c6",
        6,
        "5,055.03",
        entries,
        changes={
            "02:balance": "4,952.50",
            "03:balance": "5,134.99",
            "hdr:carried_forward": "5,134.99",
        },
    )
    flags = _by_field(_flags([page]))
    assert set(flags) == {ledger_line_id("c6", 2, "debit"), ledger_line_id("c6", 2, "balance")}
    assert flags[ledger_line_id("c6", 2, "debit")][0].suggested == "130.09"


def test_carried_forward_must_equal_the_last_balance():
    last = _balances("2,140.00", SHEET_31)[-1]
    for text in ("1.00", ""):
        flags = _flags(
            [_card("c31", 31, "2,140.00", SHEET_31, changes={"hdr:carried_forward": text})]
        )
        assert [(f.field_id, f.suggested) for f in flags] == [
            (ledger_header_id("c31", "carried_forward"), last)
        ]


def test_a_line_is_a_debit_or_a_credit_never_both_or_neither():
    both = _flags([_card("c31", 31, "2,140.00", SHEET_31, changes={"03:credit": "150.00"})])
    assert {f.field_id for f in both if "one or the other" in f.detail} == {
        ledger_line_id("c31", 3, "debit"),
        ledger_line_id("c31", 3, "credit"),
    }
    neither = _by_field(
        _flags([_card("c31", 31, "2,140.00", SHEET_31, changes={"03:debit": ""})])
    )
    assert any("neither" in f.detail for f in neither[ledger_line_id("c31", 3, "credit")])
    # The balances say the missing amount was a debit of 150.00.
    assert "150.00" in {f.suggested for f in neither[ledger_line_id("c31", 3, "debit")]}


def test_a_date_that_goes_backwards_down_a_card_is_flagged_alone():
    flags = _flags([_card("c31", 31, "2,140.00", SHEET_31, changes={"05:date": "14/02/85"})])
    assert [(f.field_id, f.check) for f in flags] == [
        (ledger_line_id("c31", 5, "date"), "arithmetic")
    ]


def test_unreadable_values_are_flagged_never_a_crash():
    changes = {"04:balance": "1,2O4.00", "06:date": "31/02/85", "hdr:sheet_no": "3l"}
    flags = _by_field(_flags([_card("c31", 31, "2,140.00", SHEET_31, changes=changes)]))
    for key in ("04:balance", "06:date"):
        line, column = key.split(":")
        field_id = ledger_line_id("c31", int(line), column)
        assert any("can't be read" in f.detail for f in flags[field_id])
    assert any("can't be read" in f.detail for f in flags[ledger_header_id("c31", "sheet_no")])


def test_values_that_were_not_read_skip_the_checks_that_need_them():
    changes = {"04:balance": None, "05:debit": None, "hdr:account_no": None}
    assert _flags([_card("c31", 31, "2,140.00", SHEET_31, changes=changes)]) == []


# --- across an account's cards -----------------------------------------------------------------


def test_brought_forward_must_equal_the_previous_carried_forward():
    flags = _flags(_sheets(c32={"hdr:brought_forward": "1.00"}))
    carry = [f for f in flags if f.check == "crossdoc"]
    assert [(f.field_id, f.suggested) for f in carry] == [
        (ledger_header_id("c32", "brought_forward"), _balances("2,140.00", SHEET_31)[-1])
    ]


def test_a_whole_cards_dates_shifted_by_ten_years_are_caught_across_cards():
    shifted = {f"{no:02d}:date": day[:-2] + "76" for no, (day, *_) in enumerate(SHEET_32, 1)}
    flags = _flags(_sheets(c32=shifted))
    assert {f.field_id for f in flags} == {
        ledger_line_id("c32", no, "date") for no in range(1, len(SHEET_32) + 1)
    }
    assert {f.check for f in flags} == {"crossdoc"}


def test_cheque_numbers_never_decrease_along_the_account():
    flags = _flags(_sheets(c32={"03:description": "CHQ 799341", "05:description": "CHQ 799342"}))
    assert {f.field_id for f in flags} == {
        ledger_line_id("c32", 3, "description"),
        ledger_line_id("c32", 5, "description"),
    }


def test_balances_are_not_carried_across_a_missing_sheet():
    pages = _sheets()
    assert _flags([pages[0], pages[2]]) == []


def test_a_card_with_a_misread_account_is_placed_by_holder_and_sheet():
    shifted = {f"{no:02d}:date": day[:-2] + "76" for no, (day, *_) in enumerate(SHEET_32, 1)}
    flags = _by_field(_flags(_sheets(c32={"hdr:account_no": "34142727", **shifted})))
    assert flags[ledger_header_id("c32", "account_no")][0].suggested == ACCOUNT
    assert ledger_line_id("c32", 1, "date") in flags


# --- payment memos -----------------------------------------------------------------------------


def test_a_memo_that_agrees_with_itself_and_its_ledger_line_raises_nothing():
    assert _flags([*_sheets(), _memo("m1")]) == []


def test_words_against_figures_flags_both_and_suggests_the_words():
    flags = _by_field(_flags([*_sheets(), _memo("m1", amount="56.48")]))
    words = [f for f in flags[memo_field_id("m1", "amount")] if f.check == "words_figures"]
    assert words[0].suggested == "65.48"
    assert flags[memo_field_id("m1", "amount_words")][0].check == "words_figures"


def test_figures_that_cant_be_read_are_suggested_from_the_words():
    for text in ("65,48", ""):
        flags = _flags([*_sheets(), _memo("m1", amount=text)])
        assert [(f.field_id, f.suggested) for f in flags] == [
            (memo_field_id("m1", "amount"), "65.48")
        ]


def test_memo_against_ledger_flags_both_when_the_amounts_differ():
    pages = [*_sheets(c32={"02:debit": "66.48", "02:balance": None}), _memo("m1")]
    crossdoc = {f.field_id for f in _flags(pages) if f.check == "crossdoc"}
    assert crossdoc == {memo_field_id("m1", "amount"), ledger_line_id("c32", 2, "debit")}


def test_the_memo_is_dated_on_or_before_the_posting_and_not_long_before():
    for day, flagged in (("03/01/86", False), ("04/12/85", False), ("04/01/86", True),
                         ("02/12/85", True)):
        flags = _flags([*_sheets(), _memo("m1", date=day)])
        assert ({f.field_id for f in flags} == {
            memo_field_id("m1", "date"), ledger_line_id("c32", 2, "date")
        }) is flagged, day


def test_a_memo_citing_a_missing_card_is_unresolvable_not_an_error():
    flags = _flags([*_sheets(), _memo("m1", ledger_ref="Sheet 40 / Line 02")])
    assert [f.field_id for f in flags] == [memo_field_id("m1", "ledger_ref")]
    assert is_unresolvable(flags[0])
    empty = _flags([*_sheets(), _memo("m1", ledger_ref="Sheet 33 / Line 12")])
    assert [is_unresolvable(f) for f in empty] == [True]


def test_a_memo_with_a_misread_account_is_found_by_its_posting():
    flags = _flags([*_sheets(), _memo("m1", account_no="34/92727")])
    suggested = [f.suggested for f in flags if f.field_id == memo_field_id("m1", "account_no")]
    assert ACCOUNT in suggested
    assert not any(is_unresolvable(f) for f in flags)


# --- the runner and the report -----------------------------------------------------------------


def test_every_registered_type_has_checks():
    assert all(callable(getattr(doc_type, "checks", None)) for doc_type in REGISTRY.values())


def test_the_runner_writes_one_flag_per_line(tmp_path):
    pages = [*_sheets(c31={"05:balance": "1,746.50"}), _memo("m1", amount="56.48")]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "predictions.jsonl").write_text("".join(p.model_dump_json() + "\n" for p in pages))
    flags = checks.run(run_dir)
    assert checks.load_flags(run_dir / checks.FLAGS_FILE) == flags
    assert len(flags) == len((run_dir / checks.FLAGS_FILE).read_text().splitlines()) > 0


def _gt(page: PageExtraction, printed: dict[str, str], errors=()) -> PageGT:
    box = BBox(x0=0, y0=0, x1=10, y1=10)
    return PageGT(
        page_id=page.page_id,
        doc_type="ledger" if page.doc_type == "ledger_card" else "memo",
        image_path=f"images/{page.page_id}.jpg",
        width=100,
        height=100,
        severity=2,
        fields=[
            FieldGT(field_id=v.field_id, printed=printed.get(v.field_id, v.value or ""), bbox=box)
            for v in page.values
        ],
        artefacts=[],
        source_errors=list(errors),
    )


def test_the_report_counts_catches_false_alarms_and_suggestions():
    right = _balances("2,140.00", SHEET_31)[4]
    misread = _card("c31", 31, "2,140.00", SHEET_31, changes={"05:balance": "1,746.50"})
    words_error = SourceError(
        kind="words_figures_mismatch",
        field_ids=[memo_field_id("m1", "amount"), memo_field_id("m1", "amount_words")],
        note="transposed",
    )
    memo = _memo("m1", amount="56.48", ledger_ref="Sheet 40 / Line 02")
    pages = [misread, memo]
    gt = [_gt(misread, {ledger_line_id("c31", 5, "balance"): right}), _gt(memo, {}, [words_error])]
    report = checks_report(gt, pages, checks.run_checks(pages))
    o = report["overall"]
    assert (o["n_wrong"], o["wrong_flagged"], o["check_recall"]) == (1, 1, 1.0)
    assert o["false_alarms"] == 0  # the memo's flags sit on its source error
    assert (o["n_suggestions_on_wrong"], o["suggestion_fixes"]) == (1, 1)
    assert (o["n_source_errors"], o["source_errors_found"]) == (1, 1)
    assert o["n_unresolvable"] == 1
    assert set(report["by_doc_type"]) == {"ledger", "memo"}
    assert json.loads(json.dumps(report))["overall"] == o
    assert "source errors found 1/1" in checks_table(report)
