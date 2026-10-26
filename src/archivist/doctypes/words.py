"""British amounts in words, read back to a Decimal: "Three hundred and forty-six pounds and thirty
pence" -> Decimal("346.30").

Written from how cheques and memos are worded, not from any generator: pounds before "pound(s)",
pence before "pence"/"penny", "and" anywhere, hyphens or spaces between tens and units, and a
trailing "only" or full stop. A tens and units run together ("fortysix") still reads, as a clerk
would read it. Anything else raises ValueError.
"""

from __future__ import annotations

import re
from decimal import Decimal

UNITS = {
    "nought": 0,
    "zero": 0,
    "nil": 0,
    "no": 0,
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
SCALES = {"thousand": 1_000, "million": 1_000_000}
POUNDS = frozenset({"pound", "pounds"})
PENCE = frozenset({"pence", "penny", "p"})
FILLER = frozenset({"and", "only", "exactly"})


def _tokens(text: str) -> list[str]:
    words = re.sub(r"[^a-z]+", " ", text.lower().replace("-", " ")).split()
    out = []
    for word in words:
        if word in UNITS or word in TENS or word in SCALES or word == "hundred":
            out.append(word)
            continue
        # A tens and units run together: "fortysix".
        split = next(
            (
                (tens, word[len(tens) :])
                for tens in TENS
                if word.startswith(tens) and word[len(tens) :] in UNITS
            ),
            None,
        )
        out.extend(split if split else (word,))
    return out


def _number(tokens: list[str]) -> int:
    """A cardinal number from its words; raises ValueError if they don't make one."""
    words = [t for t in tokens if t not in FILLER]
    if not words:
        raise ValueError("no number")
    total = current = 0
    for word in words:
        if word in UNITS:
            current += UNITS[word]
        elif word in TENS:
            current += TENS[word]
        elif word == "hundred":
            if current == 0 or current >= 100:
                raise ValueError("'hundred' without a number before it")
            current *= 100
        elif word in SCALES:
            if current == 0:
                raise ValueError(f"{word!r} without a number before it")
            total += current * SCALES[word]
            current = 0
        else:
            raise ValueError(f"not a number word: {word!r}")
    return total + current


def parse_amount_words(text: str) -> Decimal:
    """The amount a sterling amount in words states; raises ValueError if it states none."""
    tokens = [t for t in _tokens(text) if t not in ("only", "exactly")]
    if not tokens:
        raise ValueError(f"no amount in {text!r}")
    pounds = pence = 0
    if any(t in POUNDS for t in tokens):
        cut = next(i for i, t in enumerate(tokens) if t in POUNDS)
        pounds = _number(tokens[:cut])
        rest = tokens[cut + 1 :]
    else:
        rest = tokens
    rest = [t for t in rest if t != "and"]
    if rest:
        if rest[-1] not in PENCE or any(t in PENCE or t in POUNDS for t in rest[:-1]):
            raise ValueError(f"can't read the pence in {text!r}")
        pence = _number(rest[:-1])
        if pence >= 100:
            raise ValueError(f"{pence} pence is not under a pound in {text!r}")
    elif not any(t in POUNDS for t in tokens):
        raise ValueError(f"no pounds or pence in {text!r}")
    return (Decimal(pounds) + Decimal(pence) / 100).quantize(Decimal("0.01"))
