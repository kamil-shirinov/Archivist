"""How many dates each section of a forward-exchange page prints, from the PDF's OCR layer alone.

Plain code: the archive PDF's text layer via archivist.templates.real_test.words (pdfium); no
model. For each of the six sections it counts the printed lines three ways: lines in the label
column that carry a day number, and figure lines in the United Kingdom and Grand total columns.
Run from archivist/: uv run python <this> <page> [<page> ...]
"""

import json
import re
import sys

from archivist.templates import real_test

SECTIONS = ("total_purchase", "purchase_foreign", "purchase_domestic", "total_sale", "sale_foreign", "sale_domestic")


def centre(w):
    return (w.box.y0 + w.box.y1) / 2


def lines(words, gap=9):
    out = []
    for w in sorted(words, key=centre):
        if out and centre(w) - out[-1][-1][0] <= gap:
            out[-1].append((centre(w), w))
        else:
            out.append([(centre(w), w)])
    return [(sum(c for c, _ in line) / len(line), [w for _, w in sorted(line, key=lambda p: p[1].box.x0)]) for line in out]


def text(line):
    return " ".join(w.text for w in line[1])


def count(page_id):
    words = real_test.words(real_test.resolve(page_id, "held_out"))
    kingdom = min((w for w in words if w.text.lower().startswith("kingdom")), key=lambda w: w.box.y0)
    grand = min((w for w in words if w.text.lower() == "grand"), key=lambda w: w.box.y0)
    labels = lines([w for w in words if w.box.x1 < kingdom.box.x0 - 5 and centre(w) > kingdom.box.y1])
    low = [text(line).lower() for line in labels]

    def after(start, test):
        return next(i for i in range(start + 1, len(labels)) if test(low[i]))

    h1 = next(i for i, t in enumerate(low) if "total" in t and "purchase" in t)
    h2 = after(h1, lambda t: "foreign" in t)
    h3 = after(h2, lambda t: "domestic" in t)
    h4 = after(h3, lambda t: "total" in t and "sale" in t)
    h5 = after(h4, lambda t: "foreign" in t)
    h6 = after(h5, lambda t: "domestic" in t)
    heads = [h1, h2, h3, h4, h5, h6]
    tops = [h1] + [h - 1 if "contracts" in low[h - 1] else h for h in heads[1:]]
    end = next((i for i in range(h6 + 1, len(labels)) if re.search(r"\bnet\b|position", low[i])), len(labels))
    bounds = [(labels[heads[k]][0] + 5, labels[tops[k + 1]][0] - 5 if k < 5 else labels[end][0] - 5 if end < len(labels) else 1e9) for k in range(6)]

    def figures(x0, x1, y0, y1):
        column = [w for w in words if x0 <= w.box.x0 and w.box.x1 <= x1 and y0 < centre(w) < y1]
        return len(lines(column))

    heading = re.compile(r"contract|purchas|sale|customer|total|foreign|domestic")
    result = {}
    for key, (y0, y1) in zip(SECTIONS, bounds, strict=True):
        dated = [text(line) for line in labels if y0 < line[0] < y1 and not heading.search(text(line).lower())]
        if key == SECTIONS[-1] and dated:  # the table ends with the last date line
            last = max(line[0] for line in labels if text(line) == dated[-1])
            y1 = min(y1, last + 12)
        result[key] = {
            "date_lines": len(dated),
            "dates": dated,
            "uk_lines": figures(kingdom.box.x0 - 45, kingdom.box.x1 + 45, y0, y1),
            "grand_total_lines": figures(grand.box.x0 - 30, grand.box.x1 + 60, y0, y1),
        }
    return result


def dump(page_id):
    words = real_test.words(real_test.resolve(page_id, "held_out"))
    kingdom = [w for w in words if w.text.lower().startswith("kingdom")]
    x = min(w.box.x0 for w in kingdom) if kingdom else 360
    return [f"{round(line[0])} {text(line)}" for line in lines([w for w in words if w.box.x1 < x - 5])]


for page_id in sys.argv[1:]:
    try:
        print(json.dumps({"page": page_id, "sections": count(page_id)}))
    except (StopIteration, ValueError) as error:
        print(json.dumps({"page": page_id, "error": repr(error), "label_lines": dump(page_id)}))
