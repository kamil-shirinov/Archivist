import datetime as dt
from collections import defaultdict
from decimal import Decimal

import pytest

from archivist.schema import ledger_line_id, memo_field_id
from archivist.synth.world import BANKS, World, amount_to_words_gb, generate_world

SEED = 7


@pytest.fixture(
    scope="module", params=[{}, {"source_error_rate": 0.5}], ids=["default", "error-heavy"]
)
def world(request) -> World:
    return generate_world(SEED, **request.param)


def _errors(world: World, kind: str) -> list:
    return [e for e in world.source_errors if e.kind == kind]


def test_same_seed_same_json():
    assert generate_world(SEED).model_dump_json() == generate_world(SEED).model_dump_json()
    assert generate_world(SEED).model_dump_json() != generate_world(SEED + 1).model_dump_json()


def test_default_sizes():
    world = generate_world(SEED)
    assert len(world.cards) == 30
    assert all(len(card.lines) == 18 for card in world.cards)
    assert {card.bank for card in world.cards} <= set(BANKS)
    assert all(len(c.account_no) == 8 and c.account_no.isdigit() for c in world.cards)


def test_every_error_kind_planted():
    world = generate_world(SEED, source_error_rate=0.5)
    for kind in ("balance_arithmetic", "words_figures_mismatch", "memo_ledger_mismatch"):
        assert _errors(world, kind), kind


def test_exactly_one_of_debit_or_credit(world):
    for card in world.cards:
        for line in card.lines:
            assert (line.debit is None) != (line.credit is None)
            assert (line.debit or line.credit) > 0


def test_balance_equation_fails_only_on_listed_lines(world):
    errors = _errors(world, "balance_arithmetic")
    assert all(len(e.field_ids) == 1 for e in errors)
    listed = {e.field_ids[0] for e in errors}
    failing = set()
    for card in world.cards:
        previous = card.brought_forward
        for line in card.lines:
            assert line.balance > 0
            if previous - (line.debit or 0) + (line.credit or 0) != line.balance:
                failing.add(ledger_line_id(card.doc_id, line.line_no, "balance"))
            previous = line.balance
        assert card.carried_forward == card.lines[-1].balance
    assert failing == listed


def test_forward_chain_and_dates_across_each_account(world):
    accounts = defaultdict(list)
    for card in world.cards:
        accounts[card.account_no].append(card)
    for cards in accounts.values():
        cards.sort(key=lambda c: c.sheet_no)
        assert [c.sheet_no for c in cards] == list(range(cards[0].sheet_no, cards[0].sheet_no + len(cards)))
        for before, after in zip(cards, cards[1:]):
            assert after.brought_forward == before.carried_forward
        dates = [line.date for card in cards for line in card.lines]
        assert dates == sorted(dates)
        assert dt.date(1975, 1, 1) <= dates[0] and dates[-1] <= dt.date(1995, 12, 31)


def test_memo_figures_match_ledger_except_mismatch_kinds(world):
    lines = {f"{c.doc_id}:{line.line_no:02d}": line for c in world.cards for line in c.lines}
    kind_by_amount_id = {e.field_ids[0]: e.kind for e in world.source_errors if e.kind != "balance_arithmetic"}
    for memo in world.memos:
        line = lines[memo.ledger_ref]
        assert line.debit is not None
        assert 0 <= (line.date - memo.date).days <= 3
        assert memo.date >= dt.date(1975, 1, 1)
        kind = kind_by_amount_id.get(memo_field_id(memo.doc_id, "amount"))
        if kind is None:
            assert memo.amount == line.debit
            assert memo.amount_words == amount_to_words_gb(memo.amount)
        elif kind == "words_figures_mismatch":
            assert memo.amount != line.debit
            assert memo.amount_words == amount_to_words_gb(line.debit)
            assert sorted(f"{memo.amount:.2f}") == sorted(f"{line.debit:.2f}")
        else:
            assert kind == "memo_ledger_mismatch"
            assert memo.amount != line.debit
            assert memo.amount_words == amount_to_words_gb(memo.amount)


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        ("4375.50", "Four thousand three hundred and seventy-five pounds and fifty pence"),
        ("12.00", "Twelve pounds only"),
        ("0.05", "Five pence only"),
        ("1001.01", "One thousand and one pounds and one penny"),
        (
            "999999.99",
            "Nine hundred and ninety-nine thousand nine hundred and ninety-nine pounds"
            " and ninety-nine pence",
        ),
    ],
)
def test_amount_to_words_gb(amount, words):
    assert amount_to_words_gb(Decimal(amount)) == words


@pytest.mark.parametrize("amount", ["0.00", "1000000.00", "1.005"])
def test_amount_to_words_gb_rejects_out_of_range(amount):
    with pytest.raises(ValueError):
        amount_to_words_gb(Decimal(amount))
