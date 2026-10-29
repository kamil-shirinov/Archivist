"""Which column headings a page prints, against its template's, from the PDF's OCR layer alone.

Plain code: the archive PDF's text layer via archivist.templates.real_test.words (pdfium); no
model. It finds the table's heading band (between the "(In ... dollars)" line, or the label
column's heading, and the first line of figures), sets aside a heading that spans several columns,
groups the other heading words into printed columns by horizontal overlap, and aligns them in
order with the template's figure columns, tolerant of OCR errors. It reports the template columns
not printed, the printed columns no template column matches, and those printed out of order.
A page whose OCR layer has no column headings cannot be checked this way.
Run from archivist/: uv run python <this> <side> <page>=<family> [...]
"""

import json
import re
import sys
from difflib import SequenceMatcher

from archivist.templates import real_test

SMALL = {"of", "and", "or", "the", "in", "as", "by", "to", "for", "on", "a", "an"}
TYPES = real_test._types(real_test.CONFIG)


def fold(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def tokens(text: str) -> list[str]:
    return [fold(t) for t in re.split(r"[\s,\-/]+", text) if len(fold(t)) >= 3 and fold(t) not in SMALL]


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def similar(printed: str, heading: str) -> float:
    """The share of the heading's words found, each by its best OCR match, in the printed text."""
    want, have = tokens(heading), tokens(printed)
    if not want or not have:
        return 0.0
    if ratio(fold(printed), fold(heading)) >= 0.7:  # a word split by the OCR: "Swltier- land"
        return 1.0
    return sum(max(ratio(w, h) for h in have) >= 0.6 for w in want) / len(want)


def cy(w):
    return (w.box.y0 + w.box.y1) / 2


def band(words, doc_type):
    label = next(c for c in doc_type.layout.columns if c.kind == "text")
    keys = sorted(tokens(label.printed), key=len, reverse=True)
    width = max(w.box.x1 for w in words)
    top_half = [w for w in words if cy(w) < 0.45 * max(cy(v) for v in words) and w.box.x0 < 0.25 * width]
    scored = [(max(ratio(fold(w.text), k) for k in keys), w) for w in top_half if fold(w.text)]
    good = [w for s, w in scored if s >= 0.6]
    if not good:
        return None, None, f"no heading like {label.printed!r}"
    anchor = min(good, key=lambda w: w.box.y0)  # the table's first: the topmost
    unit = [w for w in words if "dollar" in fold(w.text) and anchor.box.y0 - 160 < cy(w) < anchor.box.y0]
    top = max(cy(w) for w in unit) + 8 if unit else anchor.box.y0 - 45
    figures = sorted(
        (w for w in words if cy(w) > anchor.box.y1 + 15 and len(re.sub(r"\D", "", w.text)) >= 2), key=cy
    )
    rules = [w for w in words if cy(w) > anchor.box.y1 + 15 and w.text.rstrip().endswith(":") and w.text[:1].isupper()]
    bottom = min([cy(figures[0]) - 8] if figures else [anchor.box.y1 + 160], default=anchor.box.y1 + 160)
    if rules:
        bottom = min(bottom, min(cy(w) for w in rules) - 8)
    label_words = [
        w for w in words
        if top <= cy(w) <= bottom and w.box.x0 < 0.25 * width and max(ratio(fold(w.text), k) for k in keys) >= 0.6
    ]
    right = max([w.box.x1 for w in label_words] + [anchor.box.x1]) + 8
    inside = [w for w in words if top <= cy(w) <= bottom and w.box.x0 >= right and fold(w.text)]
    return inside, (right, bottom), None


def figure_columns(words, right, bottom):
    """How many columns of figures the table's body prints: figures (two digits or more) below the
    heading band and right of the label column, down to the first gap of 150 px, grouped by their
    right edges."""
    figures = sorted((w for w in words if cy(w) > bottom and w.box.x0 >= right and len(re.sub(r"\D", "", w.text)) >= 2), key=cy)
    body, last = [], None
    for w in figures:
        if last is not None and cy(w) - last > 150:
            break
        body.append(w)
        last = cy(w)
    groups: list[list[float]] = []
    for edge in sorted(w.box.x1 for w in body):
        if groups and edge - groups[-1][-1] <= 18:
            groups[-1].append(edge)
        else:
            groups.append([edge])
    return [round(sum(g) / len(g)) for g in groups if len(g) >= 3]


def columns(inside):
    """Printed columns: heading words grouped by horizontal overlap, after setting aside a word
    that spans two or more columns of words printed below it."""
    def overlap(a, b, pad=4):
        return a.box.x0 - pad < b.box.x1 and b.box.x0 - pad < a.box.x1

    spanning = []
    for w in inside:
        under = sorted((v for v in inside if v is not w and v.box.y0 > w.box.y1 - 2 and overlap(w, v, 0)), key=lambda v: v.box.x0)
        groups = 0
        edge = -1e9
        for v in under:
            if v.box.x0 > edge + 2:
                groups += 1
            edge = max(edge, v.box.x1)
        if groups >= 2:
            spanning.append(w)
    rest = [w for w in inside if w not in spanning]
    groups: list[list] = []
    for w in sorted(rest, key=lambda w: w.box.x0):
        hit = [g for g in groups if any(overlap(w, v) for v in g)]
        merged = [w] + [v for g in hit for v in g]
        groups = [g for g in groups if g not in hit] + [merged]
    printed = []
    for g in sorted(groups, key=lambda g: min(v.box.x0 for v in g)):
        text = " ".join(v.text for v in sorted(g, key=lambda v: (round(cy(v) / 6), v.box.x0)))
        printed.append({"text": text, "x": round(min(v.box.x0 for v in g))})
    return printed, [w.text for w in spanning]


def align(printed, template):
    """Order-keeping alignment of printed columns to template headings (keys, printed)."""
    n, m = len(printed), len(template)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = similar(printed[i - 1]["text"], template[j - 1][1])
            score[i][j] = max(score[i - 1][j], score[i][j - 1], score[i - 1][j - 1] + (s if s >= 0.5 else -1))
    pairs, i, j = [], n, m
    while i and j:
        s = similar(printed[i - 1]["text"], template[j - 1][1])
        if s >= 0.5 and score[i][j] == score[i - 1][j - 1] + s:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif score[i][j] == score[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def check(side, page_id, family):
    doc_type = TYPES[family]
    words = real_test.words(real_test.resolve(page_id, side))
    base = {"page": page_id, "family": family}
    if len(words) < 40:
        return base | {"checkable": False, "why": f"{len(words)} words in the OCR layer"}
    inside, edges, why = band(words, doc_type)
    if inside is None:
        return base | {"checkable": False, "why": why}
    printed, spanning = columns(inside)
    base = base | {"figure_columns": figure_columns(words, *edges)}
    template = [(c.key, c.printed) for c in doc_type.layout.columns if c.kind != "text"]
    if len(printed) < max(3, len(template) // 3):
        return base | {"checkable": False, "why": f"{len(printed)} heading groups in the OCR layer", "printed": [p["text"] for p in printed]}
    pairs = align(printed, template)
    matched_p, matched_t = {i for i, _ in pairs}, {j for _, j in pairs}
    missing = [template[j] for j in range(len(template)) if j not in matched_t]
    extra = [printed[i] for i in range(len(printed)) if i not in matched_p]
    moved = []
    for p in extra:
        for key, heading in missing:
            if similar(p["text"], heading) >= 0.5:
                moved.append(key)
    return base | {
        "checkable": True,
        "printed": [p["text"] for p in printed],
        "spanning": spanning,
        "missing": [k for k, _ in missing if k not in moved],
        "moved": moved,
        "not_in_template": [p["text"] for p in extra if not any(similar(p["text"], h) >= 0.5 for k, h in missing)],
    }


side = sys.argv[1]
for item in sys.argv[2:]:
    page_id, family = item.split("=")
    print(json.dumps(check(side, page_id, family)))
