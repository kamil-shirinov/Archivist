"""What each flag says, in a form the UI and the database can use: a rule id, the other fields in
its equation, and why a field went to review.

Rule ids come from the wording of a flag's detail, the way the checks write it (doctypes/ledger.py,
pipeline/verify.py). The check rules use the same ids and phrases as eval.run_eval.check_rule, so
the two always agree (tests/test_export.py holds them to it on the committed test runs); the notes
the verification adds (re-reads, occlusion) get ids of their own.

A flag's equation is found by reading the batch the way the checks read it, through the ledger's
own readers: the same used lines, the same accounts (strays included) and the same postings. The
batch is read once per chain, the extracted values for a field's flags and the re-read values for
its re-read flags, as each set of flags was raised on its own chain.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from archivist.doctypes import is_unresolvable
from archivist.doctypes import ledger as L
from archivist.pipeline.extract import PageExtraction
from archivist.schema import Flag

CHECKS = frozenset({"arithmetic", "words_figures", "crossdoc"})  # what the checks raise
# Which rule raised a flag, from the wording of its detail: (rule, check, phrases), first match.
# The check rules are eval.run_eval.CHECK_RULES, word for word.
RULES = (
    ("unreadable", "arithmetic", ("can't be read as", "blank, but must hold")),
    ("running_balance", "arithmetic", ("but the balance reads",)),
    ("carried_forward", "arithmetic", ("carried forward",)),
    ("one_side", "arithmetic", ("a line is one or the other",)),
    ("date_order", "arithmetic", ("the date goes backwards",)),
    ("cheque_order", "arithmetic", ("the cheque number goes backwards",)),
    ("words_figures", "words_figures", ("",)),
    ("sheet_order", "crossdoc", ("never goes backwards along an account",)),
    ("carry_across_sheets", "crossdoc", ("brings forward",)),
    ("card_account_by_holder", "crossdoc", ("fills the gap",)),
    ("memo_account_by_posting", "crossdoc", ("the memo's account reads",)),
    ("memo_amount", "crossdoc", ("the memo pays",)),
    ("memo_date", "crossdoc", ("the memo is dated",)),
    ("occluded", "occlusion", ("covered by",)),
    ("reread_mismatch", "reread", ("the blind re-read reads",)),
    ("reread_illegible", "reread", ("the blind re-read found it illegible",)),
    ("reread_failed", "reread", ("the re-read failed",)),
    ("no_citation", "reread", ("no citation box",)),
    ("second_look", "reread", ("second look",)),  # policy v3's evidence; v2 never acts on it
)
REREAD_REASONS = {
    "disagrees": "read_mismatch",
    "illegible": "reread_illegible",
    "failed": "reread_failed",
    "no_citation": "no_citation",
}


def rule_id(flag: Flag) -> str:
    if is_unresolvable(flag):
        return "unresolvable"
    for rule, check, phrases in RULES:
        if flag.check == check and any(p in flag.detail for p in phrases):
            return rule
    return "other"


def is_failure(flag: Flag) -> bool:
    """A check that failed: a reason for review, unlike a note or an unresolvable reference."""
    return flag.check in CHECKS and not is_unresolvable(flag)


def reasons(
    status: str, reread_status: str, flags: Sequence[Flag], occluded: bool
) -> list[tuple[str, str | None]]:
    """Why a field is not accepted, as (code, rule) pairs; empty for an accepted field.

    These are the causes verify.decide acts on: the two reads disagree, the re-read is illegible
    or failed, there is no box to re-read, or a named check failed on the extracted values. A field
    the extractor didn't read is "not_read"; "obscured" is added when something covers the field.
    """
    if status == "accepted":
        return []
    out: list[tuple[str, str | None]] = []
    if status == "abstained":
        out.append(("not_read", None))
    if reread_status in REREAD_REASONS:
        out.append((REREAD_REASONS[reread_status], None))
    for rule in dict.fromkeys(rule_id(f) for f in flags if is_failure(f)):
        out.append(("rule_failed", rule))
    if occluded:
        out.append(("obscured", None))
    return out


@dataclass(frozen=True)
class Posting:
    """Where a memo's ledger reference leads, found as _memo_ledger_check finds it."""

    memo: L._Memo
    account: str | None  # the account group the line was found in
    card: L._Card | None
    line: L._Line | None
    by_amount: bool  # found by the amount the line debits, not by the memo's own account
    unresolved: str | None  # why no line was found


class Reading:
    """A batch of pages as one chain read them: cards, accounts in sheet order, memos, postings."""

    def __init__(self, pages: Sequence[PageExtraction]) -> None:
        ignored: list[Flag] = []
        batch = sorted(pages, key=lambda p: p.page_id)
        self.cards = {
            p.page_id: L._read_card(p, ignored) for p in batch if p.doc_type == L.LedgerCard.name
        }
        self.accounts = L._accounts(list(self.cards.values()), ignored)
        self.account_of = {c.page_id: key for key, group in self.accounts.items() for c in group}
        memos = {
            p.page_id: L._read_memo(p, ignored) for p in batch if p.doc_type == L.PaymentMemo.name
        }
        self.postings = {page_id: self._posting(memo) for page_id, memo in memos.items()}

    def _posting(self, memo: L._Memo) -> Posting:
        if memo.ref is None:
            return Posting(memo, None, None, None, False, "no ledger reference can be read")
        if memo.account is None and memo.raw["account_no"] is None:
            return Posting(memo, None, None, None, False, "the memo's account was not read")
        sheet, line_no = memo.ref
        account = memo.account
        matches = [c for c in self.accounts.get(account or "", []) if c.sheet == sheet]
        by_amount = False
        if not matches:
            found = L._posting(memo, self.accounts)
            if found and any(c.account == found[0] for c in self.accounts[found[0]]):
                (account, card), by_amount = found, True
                matches = [card]
        if len(matches) != 1:
            found = "no card" if not matches else f"{len(matches)} cards"
            where = f"sheet {sheet} of account {account or memo.raw['account_no']}"
            return Posting(memo, account, None, None, by_amount, f"{found} for {where}")
        card = matches[0]
        line = card.by_no.get(line_no)
        if line is None:
            why = f"line {line_no:02d} of sheet {sheet} is empty or not on the card"
            return Posting(memo, account, card, None, by_amount, why)
        return Posting(memo, account, card, line, by_amount, None)

    def memos_on(self, field_id: str) -> list[Posting]:
        """The postings to the ledger line a field belongs to."""
        return [
            p
            for p in self.postings.values()
            if p.line is not None and field_id in p.line.ids.values()
        ]

    def group_of(self, page_id: str) -> list[L._Card]:
        return self.accounts.get(self.account_of.get(page_id, ""), [])


def page_of(field_id: str) -> str:
    return field_id.split(":")[1]


def line_of(field_id: str) -> int | None:
    part = field_id.split(":")[-2]
    return int(part) if part.isdigit() else None


def _line(reading: Reading, field_id: str) -> tuple[L._Card, int] | None:
    card = reading.cards.get(page_of(field_id))
    no = line_of(field_id)
    if card is None or no is None or no not in card.by_no:
        return None
    return card, [line.no for line in card.lines].index(no)


def _running_balance(flag: Flag, reading: Reading) -> list[str]:
    found = _line(reading, flag.field_id)
    if found is None:
        return []
    card, k = found
    line = card.lines[k]
    prev = card.lines[k - 1].ids["balance"] if k else card.hdr("brought_forward")
    ids = [prev, line.ids["debit"], line.ids["credit"], line.ids["balance"]]
    if "also makes" in flag.detail:  # one balance mends this line and the next
        if k + 1 < len(card.lines):
            ids += [card.lines[k + 1].ids[c] for c in ("debit", "credit", "balance")]
        else:
            ids.append(card.hdr("carried_forward"))
    return ids


def _carried_forward(flag: Flag, reading: Reading) -> list[str]:
    card = reading.cards.get(page_of(flag.field_id))
    if card is None:
        return []
    last = card.lines[-1].ids["balance"] if card.lines else card.hdr("brought_forward")
    return [last, card.hdr("carried_forward")]


def _one_side(flag: Flag, reading: Reading) -> list[str]:
    found = _line(reading, flag.field_id)
    if found is None:
        return []
    card, k = found
    return [card.lines[k].ids["debit"], card.lines[k].ids["credit"]]


_BACKWARDS = re.compile(r"goes backwards: (.*) then (.*)$")


def _descent(items_of: Callable[[L._Card], list]) -> Callable[[Flag, Reading], list[str]]:
    def equation(flag: Flag, reading: Reading) -> list[str]:
        card = reading.cards.get(page_of(flag.field_id))
        match = _BACKWARDS.search(flag.detail)
        if card is None or match is None:
            return []
        items = items_of(card)
        for (a_id, a, a_text), (b_id, b, b_text) in zip(items, items[1:], strict=False):
            if b < a and flag.field_id in (a_id, b_id) and (a_text, b_text) == match.groups():
                return [a_id, b_id]
        return []

    return equation


_ALONG = re.compile(r"^sheet (\S+) starts with .*, before sheet (\S+) ends with ")


def _sheet_order(flag: Flag, reading: Reading) -> list[str]:
    match = _ALONG.search(flag.detail)
    if match is None:
        return []
    items_of = L._cheque_items if "cheque number" in flag.detail else L._date_items
    seq = [(c, items) for c in reading.group_of(page_of(flag.field_id)) if (items := items_of(c))]
    b_sheet, a_sheet = match.groups()
    for (a, a_items), (b, b_items) in zip(seq, seq[1:], strict=False):
        if (str(a.sheet), str(b.sheet)) != (a_sheet, b_sheet):
            continue
        if flag.field_id in {f for f, _, _ in b_items}:
            return [a_items[-1][0]]
        if flag.field_id in {f for f, _, _ in a_items}:
            return [b_items[0][0]]
    return []


_CARRY = re.compile(r"^sheet (\S+) carries forward .*, but sheet (\S+) brings forward ")


def _carry_across_sheets(flag: Flag, reading: Reading) -> list[str]:
    match = _CARRY.search(flag.detail)
    if match is None:
        return []
    group = reading.group_of(page_of(flag.field_id))
    for a, b in zip(group, group[1:], strict=False):
        if (str(a.sheet), str(b.sheet)) == match.groups():
            return [a.hdr("carried_forward"), b.hdr("brought_forward")]
    return []


_GAP = re.compile(r"fills the gap in account (\d+)'s sheets")


def _card_account_by_holder(flag: Flag, reading: Reading) -> list[str]:
    match = _GAP.search(flag.detail)
    if match is None:
        return []
    # The cards that read the account, wherever they ended up: later moves can leave its group
    # with none that does (the stranded group in PREREGISTRATION.md's Deviations).
    key = match.group(1)
    return [c.hdr("account_no") for c in reading.cards.values() if c.account == key]


def _memo_account_by_posting(flag: Flag, reading: Reading) -> list[str]:
    posting = reading.postings.get(page_of(flag.field_id))
    if posting is None or posting.line is None:
        return []
    memo = posting.memo
    return [
        memo.ids["account_no"],
        memo.ids["ledger_ref"],
        memo.ids["amount"],
        posting.line.ids["debit"],
        posting.card.hdr("account_no"),
    ]


def _memo_amount(flag: Flag, reading: Reading) -> list[str]:
    not_a_debit = "is not a debit" in flag.detail
    posting = reading.postings.get(page_of(flag.field_id))
    if posting is not None:  # the flag is on the memo
        if posting.line is None:
            return []
        ids = [posting.memo.ids["amount"], posting.line.ids["debit"]]
        if not_a_debit:
            ids.append(posting.line.ids["credit"])
        if "as its words do" in flag.detail:
            ids.append(posting.memo.ids["amount_words"])
        return ids
    ids = []  # the flag is on the ledger line: the memos posted to it that pay what it says
    for p in reading.memos_on(flag.field_id):
        if p.memo.amount is not None and f"the memo pays {L._fmt(p.memo.amount)}," in flag.detail:
            ids += [p.memo.ids["amount"], p.line.ids["debit"]]
            if not_a_debit:
                ids.append(p.line.ids["credit"])
    return ids


def _memo_date(flag: Flag, reading: Reading) -> list[str]:
    posting = reading.postings.get(page_of(flag.field_id))
    if posting is not None:
        return [] if posting.line is None else [posting.memo.ids["date"], posting.line.ids["date"]]
    return [
        id_
        for p in reading.memos_on(flag.field_id)
        if f"the memo is dated {p.memo.raw['date']}," in flag.detail
        for id_ in (p.memo.ids["date"], p.line.ids["date"])
    ]


def _words_figures(flag: Flag, reading: Reading) -> list[str]:
    posting = reading.postings.get(page_of(flag.field_id))
    return [] if posting is None else [posting.memo.ids["amount"], posting.memo.ids["amount_words"]]


EQUATIONS: dict[str, Callable[[Flag, Reading], list[str]]] = {
    "running_balance": _running_balance,
    "carried_forward": _carried_forward,
    "one_side": _one_side,
    "date_order": _descent(L._date_items),
    "cheque_order": _descent(L._cheque_items),
    "words_figures": _words_figures,
    "sheet_order": _sheet_order,
    "carry_across_sheets": _carry_across_sheets,
    "card_account_by_holder": _card_account_by_holder,
    "memo_account_by_posting": _memo_account_by_posting,
    "memo_amount": _memo_amount,
    "memo_date": _memo_date,
}


def related(flag: Flag, reading: Reading) -> list[str]:
    """The other fields in the flag's equation, in the equation's order; none for a rule without
    one (an unreadable value, an unresolvable reference, a note).
    """
    equation = EQUATIONS.get(rule_id(flag))
    ids = equation(flag, reading) if equation else []
    return [f for f in dict.fromkeys(ids) if f != flag.field_id]
