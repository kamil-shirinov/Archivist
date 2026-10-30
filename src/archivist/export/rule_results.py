"""Every rule applied to the values as the extractor read them, passed or failed.

A flag says a rule failed; the UI also shows the rules that held ("Running balance: 2,434.75 −
41.58 = 2,393.17"), so each equation the checks apply is worked out here from the same readers
(rules.Reading), in Decimal, the way doctypes/ledger.py applies it: a line's running balance, the
carried forward, dates and cheque numbers in order, the carry from one sheet to the next, and a
memo's words against its figures and its figures and date against the ledger line it cites. An
equation with a value that was not read, or a memo whose line was not found, is left out: it was
not applied. A failed equation takes its wording from the check's flag; a failing flag with no
equation here (a rule this module does not work out) is listed on its own, failed, with its
equation's cells.

Only the extracted chain is applied: the re-read chain's flags stay on the fields.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from archivist.doctypes import REGISTRY, Card, Posting, is_unresolvable
from archivist.doctypes.ledger import MEMO_LEAD, cheque_items, date_items, fmt
from archivist.export import rules
from archivist.export.schema import RuleResult
from archivist.schema import Flag

LABELS = {
    "running_balance": "Running balance",
    "carried_forward": "Carried forward",
    "one_side": "One side of a line",
    "date_order": "Dates in order",
    "cheque_order": "Cheque numbers in order",
    "words_figures": "Words and figures",
    "sheet_order": "Sheet order",
    "carry_across_sheets": "Sheet to sheet",
    "card_account_by_holder": "Card to account",
    "memo_account_by_posting": "Memo against ledger",
    "memo_amount": "Memo against ledger",
    "memo_date": "Memo against ledger",
    "unreadable": "Unreadable value",
    "unresolvable": "Reference not found",
    "other": "Other check",
}


def label(rule: str) -> str:
    """A rule in plain words: a built-in rule's name, a template identity's own description."""
    if rule in LABELS:
        return LABELS[rule]
    family, _, identity = rule.partition(".")
    doc_type = REGISTRY.get(family)
    for candidate in getattr(getattr(doc_type, "template", None), "identities", []):
        if candidate.id == identity:
            return candidate.description
    return rule.replace("_", " ").capitalize()


def _failures(flags: Sequence[Flag]) -> dict[tuple[str, str], Flag]:
    """The failing flags by (rule, field), the first of each."""
    out: dict[tuple[str, str], Flag] = {}
    for flag in flags:
        if rules.is_failure(flag) and not is_unresolvable(flag):
            out.setdefault((rules.rule_id(flag), flag.field_id), flag)
    return out


Add = Callable[[str, str, list[str], bool, str | None], None]


class _Collector:
    def __init__(self, flags: Sequence[Flag]) -> None:
        self.failing = _failures(flags)
        self.used: set[tuple[str, str]] = set()
        self.results: list[RuleResult] = []

    def add(
        self, rule: str, page_id: str, fields: list[str], ok: bool, equation: str | None
    ) -> None:
        flag = None
        if not ok:
            for field_id in fields:
                if (rule, field_id) in self.failing:
                    self.used.add((rule, field_id))
                    flag = flag or self.failing[(rule, field_id)]
        self.results.append(
            RuleResult(
                rule_id=f"{rule}:{page_id}:{fields[-1]}",
                rule=rule,
                label=label(rule),
                page_id=page_id,
                fields=fields,
                ok=ok,
                equation=equation,
                detail=flag.detail if flag else None,
                suggested=flag.suggested if flag else None,
            )
        )

    def unmatched(self, reading: rules.Reading) -> None:
        """Failing flags no equation above took: listed on their own, failed."""
        for (rule, field_id), flag in self.failing.items():
            if (rule, field_id) in self.used:
                continue
            fields = [*rules.related(flag, reading), field_id]
            self.results.append(
                RuleResult(
                    rule_id=f"{rule}:{rules.page_of(field_id)}:{field_id}",
                    rule=rule,
                    label=label(rule),
                    page_id=rules.page_of(field_id),
                    fields=fields,
                    ok=False,
                    equation=None,
                    detail=flag.detail,
                    suggested=flag.suggested,
                )
            )


def _balance(card: Card, k: int, add: Add) -> None:
    line = card.lines[k]
    prev_id = card.lines[k - 1].ids["balance"] if k else card.hdr("brought_forward")
    prev = card.lines[k - 1].balance if k else card.brought
    values = (prev, line.debit, line.credit, line.balance)
    if any(v is None for v in values):
        return
    moved = prev - line.debit + line.credit
    if line.credit:
        sum_ = f"{fmt(prev)} + {fmt(line.credit)} = {fmt(moved)}"
    else:
        sum_ = f"{fmt(prev)} − {fmt(line.debit)} = {fmt(moved)}"
    ok = moved == line.balance
    fields = [prev_id, line.ids["debit"], line.ids["credit"], line.ids["balance"]]
    shown = sum_ if ok else f"{sum_} ≠ {fmt(line.balance)}"
    add("running_balance", card.page_id, fields, ok, shown)


def _card_rules(card: Card, add: Add) -> None:
    for k in range(len(card.lines)):
        _balance(card, k, add)
    last = card.lines[-1] if card.lines else None
    last_id = last.ids["balance"] if last else card.hdr("brought_forward")
    last_value = last.balance if last else card.brought
    if last_value is not None and card.carried is not None:
        ok = last_value == card.carried
        sum_ = f"{fmt(last_value)} = {fmt(card.carried)}"
        add("carried_forward", card.page_id, [last_id, card.hdr("carried_forward")], ok, sum_)
    for rule, items in (("date_order", date_items(card)), ("cheque_order", cheque_items(card))):
        for (a_id, a, a_text), (b_id, b, b_text) in zip(items, items[1:], strict=False):
            add(rule, card.page_id, [a_id, b_id], b >= a, f"{a_text} ≤ {b_text}")


def _sheet_rules(reading: rules.Reading, add: Add) -> None:
    for group in reading.accounts.values():
        for a, b in zip(group, group[1:], strict=False):
            if b.sheet != (a.sheet or 0) + 1 or a.carried is None or b.brought is None:
                continue
            ok = a.carried == b.brought
            sum_ = f"{fmt(a.carried)} = {fmt(b.brought)}"
            fields = [a.hdr("carried_forward"), b.hdr("brought_forward")]
            add("carry_across_sheets", b.page_id, fields, ok, sum_)


def _memo_rules(page_id: str, posting: Posting, add: Add) -> None:
    memo = posting.memo
    if memo.amount is not None and memo.words is not None:
        fields = [memo.ids["amount"], memo.ids["amount_words"]]
        sum_ = f"{fmt(memo.amount)} = {fmt(memo.words)}"
        add("words_figures", page_id, fields, memo.amount == memo.words, sum_)
    line = posting.line
    if line is None:
        return
    if memo.amount is not None and line.debit is not None and line.credit is not None:
        ok = line.debit != 0 and line.debit == memo.amount
        sum_ = f"{fmt(memo.amount)} = {fmt(line.debit)}"
        add("memo_amount", page_id, [memo.ids["amount"], line.ids["debit"]], ok, sum_)
    if memo.date is not None and line.date is not None:
        ok = memo.date <= line.date and line.date - memo.date <= MEMO_LEAD
        sum_ = f"{memo.raw['date']} ≤ {line.date_text}"
        add("memo_date", page_id, [memo.ids["date"], line.ids["date"]], ok, sum_)


def _template_rules(batch: Sequence, add: Add) -> None:
    """Every identity of every template type, wherever it applies on the pages and every cell is a
    figure that was read, the way the type's own checks apply it."""
    texts = {v.field_id: None if v.abstained else v.value for page in batch for v in page.values}
    for doc_type in REGISTRY.values():
        if not hasattr(doc_type, "instances"):
            continue
        for instance in doc_type.instances(batch):
            result = None if instance.unresolved is not None else doc_type.evaluate(instance, texts)
            if result is None:
                continue
            left, right, tolerance = result
            places = max(0, -instance.fields[0][2].as_tuple().exponent)
            ok = abs(left - right) <= tolerance
            fields = list(dict.fromkeys(f for f, *_ in instance.fields))
            sign = "=" if ok else "≠"
            equation = f"{instance.where}: {left:,.{places}f} {sign} {right:,.{places}f}"
            add(instance.rule, rules.page_of(fields[0]), fields, ok, equation)


def rule_results(reading: rules.Reading, flags: Sequence[Flag]) -> list[RuleResult]:
    """Every rule applied to the batch, in page order, then the failures no equation here took."""
    collected = _Collector(flags)
    add = collected.add
    for card in reading.cards.values():
        _card_rules(card, add)
    _sheet_rules(reading, add)
    for page_id, posting in sorted(reading.postings.items()):
        _memo_rules(page_id, posting, add)
    _template_rules(reading.pages, add)
    collected.unmatched(reading)
    return collected.results


def labels(results: Sequence[RuleResult], flags: Sequence[Flag]) -> dict[str, str]:
    """The plain words of every rule id the results and the flags carry, sorted by id."""
    ids = {r.rule for r in results} | {rules.rule_id(f) for f in flags}
    return {rule: label(rule) for rule in sorted(ids)}
