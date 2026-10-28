"""Document types as plug-ins (D21): each knows its fields, its prompt, its schema and its parser.

The pipeline classifies a page against every registered type's description, then extracts it
with that type alone. A page that matches none is reported as unsupported, never forced into one.
A type's checks run over a whole batch of pages, so cross-document checks see every page; each
picks out the pages it needs by doc_type and reads only their extracted values (D24).

Verification needs nothing more of a type than DocType gives: which fields hold money, how two
readings of a field compare, the type's amounts and dates, and which fields its own equations hold
for. Each type names how its boxes are made (citations): the ledger family keeps S0+ink (D23), a
template takes the strategy measured on the development tables (template.py). A type whose
pages link to others (the ledger family's accounts and postings) also offers the readers its
checks join them with, AccountReader and PostingReader, and the exporter reads the links through
those alone; a type that offers neither is exported page by page. A type whose
checks name their rules in their own wording (a template's identities) offers RuleReader, and the
exporter asks it which rule raised a flag and which cells are in its equation.

Besides the built-in types, every approved template in templates/ is a type (template.py). Drafts
and examples are validated, never registered.

Registered is not enabled (P21b). A run enables the types its config names ([doc_types] enabled),
and only those: the classifier is shown their descriptions alone, and verification takes its money
fields from them alone, so approving a template later can never change what an old run asked or
recorded. A run records the set it enabled, each built-in type as BUILT_IN and each template by its
file's sha256 (recorded()); a run from before P21b recorded none and enabled LEGACY.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol, runtime_checkable

from archivist.doctypes.ledger import (
    UNRESOLVABLE,
    Card,
    LedgerCard,
    Line,
    Memo,
    PaymentMemo,
    Posting,
)
from archivist.doctypes.template import TEMPLATES_DIR, TemplateError, TemplateType, load_templates
from archivist.schema import ExtractedValue, Flag, PageExtraction

UNSUPPORTED = "unsupported"


class DocType(Protocol):
    name: str
    description: str  # one line, shown to the classifier
    money_fields: frozenset[str]  # field names that hold money: checked by sums as well as re-read
    citations: str  # how its boxes are made, one of extract.CITATION_STRATEGIES

    def field_ids(self, page_id: str) -> list[str]: ...

    def extraction_prompt(self, grounding: bool = False) -> str: ...  # grounding: strategy S1

    def extraction_schema(self) -> dict: ...

    def parse(
        self, page_id: str, data: object, width: int, height: int
    ) -> list[ExtractedValue]: ...

    def reread_prompt(self, field_id: str) -> str: ...  # the blind re-read of one field (D4)

    def canonical(self, field_id: str, text: str) -> str: ...  # what two readings compare as

    def money(self, text: str) -> Decimal | None: ...  # an amount as the type writes it

    def calendar_date(self, text: str) -> date | None: ...  # a date as the type writes it

    def checks(self, pages: list[PageExtraction]) -> list[Flag]: ...

    def balanced(self, pages: Sequence[PageExtraction]) -> set[str]: ...  # see LedgerCard.balanced


@runtime_checkable
class AccountReader(Protocol):
    """Pages that are an account's sheets, read as the type's checks read them."""

    def cards(self, pages: Sequence[PageExtraction]) -> dict[str, Card]: ...  # by page id

    def accounts(self, cards: Sequence[Card]) -> dict[str, list[Card]]: ...  # in sheet order


@runtime_checkable
class PostingReader(Protocol):
    """Pages that cite a ledger line, and where each citation leads, as the checks find it."""

    def postings(
        self, pages: Sequence[PageExtraction], accounts: Mapping[str, list[Card]]
    ) -> dict[str, Posting]: ...  # by page id


@runtime_checkable
class RuleReader(Protocol):
    """Flags whose rule the type names itself, and the cells of the equation each was raised on."""

    def rule(self, flag: Flag) -> str | None: ...  # None: not one of this type's

    def equation(self, flag: Flag, pages: Sequence[PageExtraction]) -> list[str]: ...


REGISTRY: dict[str, DocType] = {}


def register(doc_type: DocType) -> None:
    if doc_type.name == UNSUPPORTED or doc_type.name in REGISTRY:
        raise ValueError(f"document type {doc_type.name!r} is reserved or already registered")
    REGISTRY[doc_type.name] = doc_type


register(LedgerCard())
register(PaymentMemo())
for _template in load_templates(TEMPLATES_DIR, reserved=[*REGISTRY, UNSUPPORTED]):
    register(_template)


BUILT_IN = "built-in"  # what a run records for a type defined in code rather than a template
LEGACY = {"ledger_card": BUILT_IN, "payment_memo": BUILT_IN}  # what a run from before P21b enabled


def enabled(names: Sequence[str]) -> dict[str, DocType]:
    """The registered types named, in that order; a name that isn't registered (no such type, or
    a template that isn't approved) is refused."""
    if not names or len(set(names)) != len(names):
        raise ValueError(f"a run enables one or more document types, each once: {list(names)}")
    unknown = [name for name in names if name not in REGISTRY]
    if unknown:
        raise ValueError(
            f"not registered: {unknown}; registered: {list(REGISTRY)} (only approved templates are)"
        )
    return {name: REGISTRY[name] for name in names}


def from_config(config_path: Path) -> dict[str, DocType]:
    """The types a run config enables, from its [doc_types] table."""
    with config_path.open("rb") as config_file:
        names = tomllib.load(config_file).get("doc_types", {}).get("enabled")
    if not isinstance(names, list):
        raise ValueError(f"{config_path} names no document types: add [doc_types] enabled = [...]")
    return enabled(names)


def recorded(doc_types: Mapping[str, DocType]) -> dict[str, str]:
    """What a run records of the types it enabled: BUILT_IN, or the template file's sha256."""
    out = {}
    for name, doc_type in doc_types.items():
        if isinstance(doc_type, TemplateType):
            if doc_type.sha256 is None:
                raise ValueError(f"{name}: a template type not read from its file")
            out[name] = doc_type.sha256
        else:
            out[name] = BUILT_IN
    return out


def recorded_by(record: Mapping[str, object]) -> dict[str, str]:
    """The types a run's run.json says it enabled; LEGACY for a run from before P21b."""
    return dict(record.get("doc_types", LEGACY))


def is_unresolvable(flag: Flag) -> bool:
    """A cross-document check that couldn't find what it needed: a note, not an error."""
    return flag.detail.startswith(UNRESOLVABLE)


def type_of(field_id: str) -> DocType:
    """The registered type whose pages have this field; a field id names its page second."""
    page_id = field_id.split(":")[1]
    for doc_type in REGISTRY.values():
        if field_id in doc_type.field_ids(page_id):
            return doc_type
    raise KeyError(f"no registered document type has the field {field_id!r}")


__all__ = [
    "BUILT_IN",
    "LEGACY",
    "REGISTRY",
    "UNRESOLVABLE",
    "UNSUPPORTED",
    "AccountReader",
    "Card",
    "DocType",
    "LedgerCard",
    "Line",
    "Memo",
    "PaymentMemo",
    "Posting",
    "PostingReader",
    "RuleReader",
    "TemplateError",
    "TemplateType",
    "enabled",
    "from_config",
    "is_unresolvable",
    "recorded",
    "recorded_by",
    "register",
    "type_of",
]
