"""Document types as plug-ins (D21): each knows its fields, its prompt, its schema and its parser.

The pipeline classifies a page against every registered type's description, then extracts it
with that type alone. A page that matches none is reported as unsupported, never forced into one.
A type's checks run over a whole batch of pages, so cross-document checks see every page; each
picks out the pages it needs by doc_type and reads only their extracted values (D24).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from archivist.doctypes.ledger import UNRESOLVABLE, LedgerCard, PaymentMemo
from archivist.schema import ExtractedValue, Flag

if TYPE_CHECKING:
    from archivist.pipeline.extract import PageExtraction

UNSUPPORTED = "unsupported"


class DocType(Protocol):
    name: str
    description: str  # one line, shown to the classifier

    def field_ids(self, page_id: str) -> list[str]: ...

    def extraction_prompt(self, grounding: bool = False) -> str: ...  # grounding: strategy S1

    def extraction_schema(self) -> dict: ...

    def parse(
        self, page_id: str, data: object, width: int, height: int
    ) -> list[ExtractedValue]: ...

    def checks(self, pages: list[PageExtraction]) -> list[Flag]: ...


REGISTRY: dict[str, DocType] = {}


def register(doc_type: DocType) -> None:
    if doc_type.name == UNSUPPORTED or doc_type.name in REGISTRY:
        raise ValueError(f"document type {doc_type.name!r} is reserved or already registered")
    REGISTRY[doc_type.name] = doc_type


register(LedgerCard())
register(PaymentMemo())

def is_unresolvable(flag: Flag) -> bool:
    """A cross-document check that couldn't find what it needed: a note, not an error."""
    return flag.detail.startswith(UNRESOLVABLE)


__all__ = [
    "REGISTRY",
    "UNRESOLVABLE",
    "UNSUPPORTED",
    "DocType",
    "LedgerCard",
    "PaymentMemo",
    "is_unresolvable",
    "register",
]
