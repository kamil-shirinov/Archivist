"""The existing approved-template title check, shared by new archive classification paths."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from archivist.doctypes.template import TemplateType

_FOLD = str.maketrans(
    {"l": "i", "1": "i", "|": "i", "!": "i", "0": "o", "—": "-", "–": "-", "‐": "-"}
)


def fold(text: str) -> str:
    """Text as the title check compares it: lower case, each confusion folded, a dash as a space
    (the layer prints "Short-Term-Foreign" for "Short-Term Foreign"), and any run of whitespace one
    space."""
    return " ".join(text.lower().translate(_FOLD).replace("-", " ").split())


def fold_pattern(pattern: str) -> str:
    """A title pattern folded as fold() folds text, leaving each escape (\\s, \\.) as it is; a
    literal space or dash matches any run of spacing."""
    out, escaped = [], False
    for char in pattern:
        out.append(char if escaped else char.lower().translate(_FOLD))
        escaped = char == "\\" and not escaped
    return re.sub(r"(?<!\\)[ -]+", r"\\s+", "".join(out))


def title_match(doc_type: TemplateType, text: str) -> str | None:
    """The first of the family's approved title patterns that the page's text matches, or None."""
    folded = fold(text)
    for pattern in doc_type.template.identity.title_patterns:
        if re.search(fold_pattern(pattern), folded, re.IGNORECASE) is not None:
            return pattern
    return None
