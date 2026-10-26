"""Ground-truth world: ledger cards, debit memos and the source errors planted in them.

Everything later stages render, degrade and score against starts here. One seed fixes the
whole world: all randomness comes from a single random.Random(seed) plus a Faker instance
seeded with the same value.
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
from collections import Counter
from decimal import Decimal
from typing import NamedTuple, get_args

from faker import Faker
from pydantic import BaseModel, model_validator

from archivist.schema import SourceError, ledger_line_id, memo_field_id

BANKS = (
    "Ashgrove & Penhallow Bank",
    "Thistledown County Bank",
    "Wrenfield Mercantile Bank",
    "Quillon Provident Bank",
    "Marrowby Savings Bank",
)
BRANCHES = (
    "Harrogate", "Kendal", "Ludlow", "Truro", "Hexham", "Stamford", "Ripon", "Whitby",
    "Frome", "Malton", "Oakham", "Ely", "Bideford", "Penrith", "Beverley", "Devizes",
    "Morpeth", "Buxton", "Thirsk", "Wells",
)  # fmt: skip
# A memo backs a payment to someone else: not cash, not the bank's own charges.
THIRD_PARTY_PREFIXES = ("CHQ", "STANDING ORDER", "DIRECT DEBIT")
FIXED_PAYEES = {
    "STANDING ORDER RATES": "District Council Rates Office",
    "STANDING ORDER INSURANCE": "Wrenfield Assurance Society",
    "DIRECT DEBIT ELECTRICITY": "Eastmoor Electricity Board",
}

PENNY = Decimal("0.01")
MAX_WORDS_AMOUNT = Decimal("999999.99")
FIRST_DATE = dt.date(1975, 1, 1)
LAST_DATE = dt.date(1995, 12, 31)
MAX_MEMO_LAG_DAYS = 3
MAX_LINE_STEP_DAYS = 6
CREDIT_SHARE = 0.3
MIN_BALANCE = Decimal("1.00")
LOW_BALANCE = Decimal("25.00")  # below this the clerk only ever sees money coming in


class LedgerLine(BaseModel):
    line_no: int  # 1-based, pre-printed on the card
    date: dt.date
    description: str
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal  # as printed, which may carry a clerk's slip

    @model_validator(mode="after")
    def _one_side(self) -> LedgerLine:
        if (self.debit is None) == (self.credit is None):
            raise ValueError("exactly one of debit or credit must be set")
        return self


class LedgerCard(BaseModel):
    doc_id: str
    bank: str
    branch: str
    account_no: str  # 8 digits
    holder: str
    sheet_no: int
    brought_forward: Decimal
    lines: list[LedgerLine]
    carried_forward: Decimal


class Memo(BaseModel):
    doc_id: str
    memo_no: str
    date: dt.date
    account_no: str
    counterparty: str
    amount: Decimal  # figures as printed
    amount_words: str  # words as printed
    ledger_ref: str  # f"{card_doc_id}:{line_no:02d}", the internal link to the ledger line
    printed_ref: str  # f"Sheet {sheet_no} / Line {line_no:02d}", what the clerk writes


class World(BaseModel):
    seed: int
    cards: list[LedgerCard]
    memos: list[Memo]
    source_errors: list[SourceError]


# --- amounts in words -------------------------------------------------------------------

_ONES = (
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen",
)  # fmt: skip
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _under_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return f"{_TENS[tens]}-{_ONES[ones]}" if ones else _TENS[tens]


def _under_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    if not hundreds:
        return _under_hundred(rest)
    words = f"{_ONES[hundreds]} hundred"
    return f"{words} and {_under_hundred(rest)}" if rest else words


def _integer_words(n: int) -> str:
    thousands, rest = divmod(n, 1000)
    if not thousands:
        return _under_thousand(rest)
    words = f"{_under_thousand(thousands)} thousand"
    if not rest:
        return words
    if rest < 100:
        return f"{words} and {_under_hundred(rest)}"
    return f"{words} {_under_thousand(rest)}"


def amount_to_words_gb(amount: Decimal) -> str:
    """British cheque-style words, e.g. 12.00 -> "Twelve pounds only"."""
    if not PENNY <= amount <= MAX_WORDS_AMOUNT or amount != amount.quantize(PENNY):
        raise ValueError(f"amount must be 0.01–999,999.99 in whole pence, got {amount}")
    pounds, pence = divmod(int(amount * 100), 100)
    parts = []
    if pounds:
        parts.append(f"{_integer_words(pounds)} {'pound' if pounds == 1 else 'pounds'}")
    if pence:
        parts.append(f"{_under_hundred(pence)} {'penny' if pence == 1 else 'pence'}")
    text = " and ".join(parts) if len(parts) == 2 else f"{parts[0]} only"
    return text[0].upper() + text[1:]


# --- clerical slips ---------------------------------------------------------------------


def _digit_slip(rng: random.Random, value: Decimal) -> Decimal:
    """Change exactly one printed digit; the leading digit never becomes a zero."""
    text = f"{value:.2f}"
    pos = rng.choice([i for i, c in enumerate(text) if c.isdigit()])
    options = [d for d in "0123456789" if d != text[pos] and not (pos == 0 and d == "0")]
    return Decimal(text[:pos] + rng.choice(options) + text[pos + 1 :])


def _transpose(rng: random.Random, value: Decimal) -> Decimal | None:
    """Swap two adjacent, different digits (across the point too); None if impossible."""
    text = f"{value:.2f}"
    point = text.index(".")
    digits = text.replace(".", "")
    swaps = [
        j
        for j in range(len(digits) - 1)
        if digits[j] != digits[j + 1] and not (j == 0 and digits[1] == "0" and point > 1)
    ]
    if not swaps:
        return None
    j = rng.choice(swaps)
    d = digits[:j] + digits[j + 1] + digits[j] + digits[j + 2 :]
    return Decimal(f"{d[:point]}.{d[point:]}")


# --- ledger cards -----------------------------------------------------------------------


class _Entry(NamedTuple):
    description: str
    weight: int
    min_pence: int
    max_pence: int
    step_pence: int


_DEBITS = (
    _Entry("CHQ", 6, 500, 45_000, 1),
    _Entry("CASH", 3, 1_000, 20_000, 500),
    _Entry("STANDING ORDER RATES", 1, 1_800, 9_500, 1),
    _Entry("STANDING ORDER INSURANCE", 1, 800, 6_000, 1),
    _Entry("DIRECT DEBIT ELECTRICITY", 1, 1_200, 8_000, 1),
    _Entry("BANK CHARGES", 1, 150, 1_200, 25),
)
_CREDITS = (
    _Entry("SALARY", 4, 25_000, 180_000, 1),
    _Entry("CASH", 2, 1_000, 30_000, 500),
    _Entry("CREDIT TRANSFER", 2, 2_000, 50_000, 1),
    _Entry("DIVIDEND", 1, 500, 15_000, 1),
    _Entry("INTEREST", 1, 50, 4_000, 1),
)


def _pence(n: int) -> Decimal:
    return (Decimal(n) / 100).quantize(PENNY)


def _draw(rng: random.Random, entries: tuple[_Entry, ...]) -> tuple[str, Decimal]:
    entry = rng.choices(entries, weights=[e.weight for e in entries])[0]
    pence = rng.randrange(entry.min_pence, entry.max_pence + 1, entry.step_pence)
    return entry.description, _pence(pence)


def _start_date(rng: random.Random, n_lines: int) -> dt.date:
    earliest = FIRST_DATE + dt.timedelta(days=MAX_MEMO_LAG_DAYS)
    latest = max(earliest, LAST_DATE - dt.timedelta(days=n_lines * MAX_LINE_STEP_DAYS))
    return earliest + dt.timedelta(days=rng.randint(0, (latest - earliest).days))


def _account(
    rng: random.Random,
    fake: Faker,
    index: int,
    account_no: str,
    cards_per_account: int,
    lines_per_card: int,
    source_error_rate: float,
) -> tuple[list[LedgerCard], list[SourceError]]:
    bank = rng.choice(BANKS)
    branch = rng.choice(BRANCHES)
    holder = fake.name()
    first_sheet = rng.randint(1, 60)
    balance = _pence(rng.randint(5_000, 300_000))
    day = _start_date(rng, cards_per_account * lines_per_card)
    cheque_no = rng.randint(1_000, 900_000)
    cards: list[LedgerCard] = []
    errors: list[SourceError] = []

    for k in range(cards_per_account):
        doc_id = f"card-{index + 1:02d}-{k + 1}"
        slip_line = rng.randint(1, lines_per_card) if rng.random() < source_error_rate else None
        brought_forward = balance
        lines: list[LedgerLine] = []
        for line_no in range(1, lines_per_card + 1):
            day = min(day + dt.timedelta(days=rng.randint(0, MAX_LINE_STEP_DAYS)), LAST_DATE)
            debit = credit = None
            if balance > LOW_BALANCE and rng.random() >= CREDIT_SHARE:
                description, amount = _draw(rng, _DEBITS)
                if balance - amount >= MIN_BALANCE:
                    debit = amount
            if debit is None:
                description, amount = _draw(rng, _CREDITS)
                credit = amount
            if description == "CHQ":
                description = f"CHQ {cheque_no:06d}"
                cheque_no += 1

            true_balance = balance - (debit or 0) + (credit or 0)
            balance = true_balance
            if line_no == slip_line:
                # The clerk misprints one digit and carries on from the wrong figure.
                balance = _digit_slip(rng, true_balance)
                errors.append(
                    SourceError(
                        kind="balance_arithmetic",
                        field_ids=[ledger_line_id(doc_id, line_no, "balance")],
                        note=f"printed balance {balance} should be {true_balance}",
                    )
                )
            lines.append(
                LedgerLine(
                    line_no=line_no,
                    date=day,
                    description=description,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                )
            )
        cards.append(
            LedgerCard(
                doc_id=doc_id,
                bank=bank,
                branch=branch,
                account_no=account_no,
                holder=holder,
                sheet_no=first_sheet + k,
                brought_forward=brought_forward,
                lines=lines,
                carried_forward=balance,
            )
        )
    return cards, errors


# --- memos ------------------------------------------------------------------------------


def _counterparty(rng: random.Random, fake: Faker, description: str) -> str:
    if description.startswith("CHQ"):
        return fake.name() if rng.random() < 0.5 else fake.company()
    if description in FIXED_PAYEES:
        return FIXED_PAYEES[description]
    if description.startswith(THIRD_PARTY_PREFIXES):
        return fake.company()
    raise ValueError(f"no third-party payee for {description!r}")


def _memos(
    rng: random.Random,
    fake: Faker,
    cards: list[LedgerCard],
    memo_rate: float,
    source_error_rate: float,
) -> tuple[list[Memo], list[SourceError]]:
    memos: list[Memo] = []
    errors: list[SourceError] = []
    memo_no = rng.randint(1_000, 80_000)
    for card in cards:
        for line in card.lines:
            if (
                line.debit is None
                or not line.description.startswith(THIRD_PARTY_PREFIXES)
                or rng.random() >= memo_rate
            ):
                continue
            doc_id = f"memo-{len(memos) + 1:04d}"
            amount, words = line.debit, amount_to_words_gb(line.debit)
            if rng.random() < source_error_rate:
                kind = rng.choice(("words_figures_mismatch", "memo_ledger_mismatch"))
                transposed = _transpose(rng, amount) if kind == "words_figures_mismatch" else None
                if transposed is not None:
                    amount = transposed
                    field_ids = [memo_field_id(doc_id, "amount"), memo_field_id(doc_id, "amount_words")]
                    note = f"figures {amount} transpose the {line.debit} stated in words"
                else:
                    kind = "memo_ledger_mismatch"
                    amount = _digit_slip(rng, line.debit)
                    words = amount_to_words_gb(amount)
                    field_ids = [
                        memo_field_id(doc_id, "amount"),
                        ledger_line_id(card.doc_id, line.line_no, "debit"),
                    ]
                    note = f"memo states {amount}; ledger line shows {line.debit}"
                errors.append(SourceError(kind=kind, field_ids=field_ids, note=note))
            memos.append(
                Memo(
                    doc_id=doc_id,
                    memo_no=f"{memo_no:06d}",
                    date=line.date - dt.timedelta(days=rng.randint(0, MAX_MEMO_LAG_DAYS)),
                    account_no=card.account_no,
                    counterparty=_counterparty(rng, fake, line.description),
                    amount=amount,
                    amount_words=words,
                    ledger_ref=f"{card.doc_id}:{line.line_no:02d}",
                    printed_ref=f"Sheet {card.sheet_no} / Line {line.line_no:02d}",
                )
            )
            memo_no += 1
    return memos, errors


# --- world ------------------------------------------------------------------------------


def generate_world(
    seed: int,
    n_accounts: int = 10,
    cards_per_account: int = 3,
    lines_per_card: int = 18,
    memo_rate: float = 0.3,
    source_error_rate: float = 0.1,
) -> World:
    rng = random.Random(seed)
    fake = Faker("en_GB")
    fake.seed_instance(seed)

    cards: list[LedgerCard] = []
    errors: list[SourceError] = []
    account_nos: set[str] = set()
    for index in range(n_accounts):
        account_no = f"{rng.randint(10_000_000, 99_999_999)}"
        while account_no in account_nos:
            account_no = f"{rng.randint(10_000_000, 99_999_999)}"
        account_nos.add(account_no)
        account_cards, account_errors = _account(
            rng, fake, index, account_no, cards_per_account, lines_per_card, source_error_rate
        )
        cards += account_cards
        errors += account_errors

    memos, memo_errors = _memos(rng, fake, cards, memo_rate, source_error_rate)
    return World(seed=seed, cards=cards, memos=memos, source_errors=errors + memo_errors)


def summary(world: World) -> str:
    kinds = Counter(e.kind for e in world.source_errors)
    rows = [
        f"seed {world.seed}",
        f"cards: {len(world.cards)}",
        f"lines: {sum(len(c.lines) for c in world.cards)}",
        f"memos: {len(world.memos)}",
        "source errors:",
    ]
    all_kinds = get_args(SourceError.model_fields["kind"].annotation)
    rows += [f"  {kind}: {kinds[kind]}" for kind in all_kinds]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.synth.world", description="Generate a ground-truth world."
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--summary", action="store_true", help="print counts, not the JSON")
    args = parser.parse_args(argv)
    world = generate_world(args.seed)
    print(summary(world) if args.summary else world.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
