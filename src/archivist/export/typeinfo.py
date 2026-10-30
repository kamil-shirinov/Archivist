"""Every registered document type as the UI shows it: what it reads, the rules that must hold on it,
the evidence each rule held on, and who approved it.

A template's layout, identities and approval are read from its file through the type itself
(doctypes.template), its evidence from the file the approval recorded the sha256 of
(templates/<family>.evidence.json): how many times each rule applied on the pages it was tested on,
on how many of those every cell was read twice and agreed, and how often it held. The built-in types
(ledger card, payment memo) have no template and no evidence file; their rules are the checks in
doctypes/ledger.py and they are measured in the test report. Only registered types are listed:
approved templates, never drafts.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence

from archivist.doctypes import REGISTRY, LedgerCard, PaymentMemo, TemplateType
from archivist.doctypes.ledger import LINES
from archivist.doctypes.template import (
    TEMPLATES_DIR,
    Layout,
    ReadRows,
    Sections,
    evidence_path,
    written,
)
from archivist.export.rule_results import label as rule_label
from archivist.export.schema import Approval, DocColumn, DocRule, DocTypeInfo, RuleEvidence
from archivist.schema import PageExtraction

LEDGER_RULES = (
    "running_balance",
    "carried_forward",
    "one_side",
    "date_order",
    "cheque_order",
    "sheet_order",
    "carry_across_sheets",
    "card_account_by_holder",
)
MEMO_RULES = ("words_figures", "memo_amount", "memo_date", "memo_account_by_posting")
LEDGER_COLUMNS = (
    ("date", "Date", "date"),
    ("description", "Particulars", "text"),
    ("debit", "Debit", "money"),
    ("credit", "Credit", "money"),
    ("balance", "Balance", "money"),
)
MEMO_FIELDS = (
    ("memo_no", "Memo No.", "text"),
    ("date", "Date", "date"),
    ("account_no", "Account No.", "text"),
    ("counterparty", "Pay to", "text"),
    ("amount", "Amount in figures", "money"),
    ("amount_words", "Amount in words", "text"),
    ("ledger_ref", "Ledger ref.", "text"),
)


def rows_in_words(layout: Layout) -> str:
    rows = layout.rows
    if isinstance(rows, ReadRows):
        return f"{rows.read} rows, read from the top"
    if isinstance(rows, Sections):
        return "; ".join(f"{s.printed} ({s.read} rows)" for s in rows.sections)
    return f"{len(rows)} fixed rows: " + ", ".join(r.printed for r in rows)


def _evidence_of(family: str) -> dict | None:
    path = evidence_path(TEMPLATES_DIR / f"{family}.yaml")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _template(doc_type: TemplateType, enabled: bool, pages: int) -> DocTypeInfo:
    template = doc_type.template
    family = template.family
    record = _evidence_of(family)
    found = {i["id"]: i for i in (record or {}).get("identities", [])}
    rules = []
    for identity in template.identities:
        e = found.get(identity.id)
        rules.append(
            DocRule(
                id=f"{family}.{identity.id}",
                label=identity.description,
                equation=written(identity),
                for_each=identity.for_each,
                evidence=None
                if e is None
                else RuleEvidence(
                    applies=e["applies"],
                    evaluated=e["evaluated"],
                    held=e["held"],
                    failed=e["failed"],
                    hold_rate=e["hold_rate"],
                    outcome=e["outcome"],
                    not_evaluated=e["not_evaluated"],
                ),
            )
        )
    p = template.provenance
    approval = None
    if p.approved:
        approval = Approval(
            approved_by=str(p.approved_by),
            approved_on=p.approved_on.isoformat(),
            drafted_by=p.drafted_by.id,
            drafted_on=p.drafted_on.isoformat(),
            drafted_from=list(p.drafted_from),
            tested_on=record["tested_on"] if record else None,
            tested_pages=[page["page_id"] for page in record["pages"]] if record else [],
            evidence_file=f"templates/{family}.evidence.json" if record else None,
            evidence_sha256=p.evidence_sha256,
            dropped=[f"{d.id}: {d.why} ({d.by})" for d in p.dropped],
        )
    layout = doc_type.layout
    return DocTypeInfo(
        name=family,
        title=template.identity.title,
        description=template.identity.description,
        kind="template",
        unit=layout.unit,
        precision=layout.precision,
        columns=[DocColumn(key=c.key, printed=c.printed, kind=c.kind) for c in layout.columns],
        rows=rows_in_words(layout),
        rules=rules,
        approval=approval,
        enabled=enabled,
        pages=pages,
    )


def _built_in(name: str, title: str, enabled: bool, pages: int) -> DocTypeInfo:
    ledger = name == "ledger_card"
    doc_type = REGISTRY[name]
    return DocTypeInfo(
        name=name,
        title=title,
        description=doc_type.description,
        kind="built-in",
        unit=None,
        precision=None,
        columns=[
            DocColumn(key=k, printed=printed, kind=kind)
            for k, printed, kind in (LEDGER_COLUMNS if ledger else MEMO_FIELDS)
        ],
        rows=f"{len(LINES)} numbered lines, each read in full" if ledger else "one record",
        rules=[
            DocRule(id=r, label=rule_label(r), equation=None, for_each=None, evidence=None)
            for r in (LEDGER_RULES if ledger else MEMO_RULES)
        ],
        approval=None,
        enabled=enabled,
        pages=pages,
    )


def doc_types(pages: Sequence[PageExtraction], enabled: Mapping[str, object]) -> list[DocTypeInfo]:
    """Every registered type, in registry order, with what this run did with it."""
    count = Counter(p.doc_type for p in pages)
    out = []
    for name, doc_type in REGISTRY.items():
        on, n = name in enabled, count.get(name, 0)
        if isinstance(doc_type, TemplateType):
            out.append(_template(doc_type, on, n))
        elif isinstance(doc_type, LedgerCard):
            out.append(_built_in(name, "Ledger card", on, n))
        elif isinstance(doc_type, PaymentMemo):
            out.append(_built_in(name, "Payment memorandum", on, n))
    return out
