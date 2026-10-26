"""Document types as plug-ins (D21): each knows its fields, its prompt, its schema and its parser.

The pipeline classifies a page against every registered type's description, then extracts it
with that type alone. A page that matches none is reported as unsupported, never forced into one.
Checks will be the next part of a type.
"""

from __future__ import annotations

from typing import Protocol

from archivist.doctypes.ledger import LedgerCard, PaymentMemo
from archivist.schema import ExtractedValue

UNSUPPORTED = "unsupported"


class DocType(Protocol):
    name: str
    description: str  # one line, shown to the classifier

    def field_ids(self, page_id: str) -> list[str]: ...

    def extraction_prompt(self) -> str: ...

    def extraction_schema(self) -> dict: ...

    def parse(
        self, page_id: str, data: object, width: int, height: int
    ) -> list[ExtractedValue]: ...


REGISTRY: dict[str, DocType] = {}


def register(doc_type: DocType) -> None:
    if doc_type.name == UNSUPPORTED or doc_type.name in REGISTRY:
        raise ValueError(f"document type {doc_type.name!r} is reserved or already registered")
    REGISTRY[doc_type.name] = doc_type


register(LedgerCard())
register(PaymentMemo())

__all__ = ["REGISTRY", "UNSUPPORTED", "DocType", "LedgerCard", "PaymentMemo", "register"]
