"""What the landing page says, as a list of text runs with every fact masked, for tests/test_landing.py.

A run is a stretch of text that belongs together: the text of a block (a paragraph, a list item, a table cell,
a heading, a caption, a label) with its inline parts (bold, links, code, spans) joined in. A number that comes
from a result file stands in a run as {its data-fact key}, so a run does not change when a result does.

P51's page is kept as tests/landing_p51.json (its fact keys and its runs); P52 redesigned the page and must
lose none of it: every fact key still on the page, and every run that holds a sentence or a number still in
one run of the new page, wherever it moved to and however it is styled (inside an expandable panel counts,
since the text is on the page; text that is not on the page does not).

    python tests/landing_content.py          # print the runs of the page as it is built now (a look)
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("landing_p51.json")

# A run ends at one of these; everything else (span, b, strong, a, code, em, i, button, label) is part of its run.
BLOCK = {
    "address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt", "figcaption", "figure",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "small", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
# Spans the old page styled as blocks: a label and its figure are two runs, whatever the markup between them.
FLUSH_CLASSES = {"ev", "when", "gap", "who", "lab", "chip", "tag", "big", "t", "d", "n", "s-drift", "s-format", "s-read"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "title"}


class Runs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[str] = []
        self.keys: list[str] = []
        self.current: list[str] = []
        self.stack: list[tuple[str, str | None, bool]] = []  # tag, data-fact key, whether it is chrome
        self.skip = 0

    def flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.current)).strip()
        if text:
            self.runs.append(text)
        self.current = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        chrome = tag == "nav" or "skip" in (attrs.get("class") or "").split()  # the nav's links and the skip link are not content
        classes = set((attrs.get("class") or "").split())
        if tag in BLOCK or tag == "button" or classes & ({"btn"} | FLUSH_CLASSES):
            self.flush()
        if tag in VOID:
            return
        if tag in SKIP or chrome:
            self.skip += 1
        key = attrs.get("data-fact")
        if key is not None:
            self.keys.append(key)
            if not self.skip:
                self.current.append("{" + key + "}")
        self.stack.append((tag, key, chrome))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        while self.stack:
            top = self.stack.pop()
            if top[0] in SKIP or top[2]:
                self.skip -= 1
            if top[0] == tag:
                break
        if tag in BLOCK or tag == "button" or tag == "a":
            self.flush()

    def handle_data(self, data):
        if self.skip or any(key is not None for _, key, _ in self.stack):
            return  # inside a fact: its key stands for it
        self.current.append(data)


def parse_runs(html: str) -> tuple[list[str], list[str]]:
    """(the fact keys, the text runs) of a page, in document order, repeats removed from the runs."""
    parser = Runs()
    parser.feed(html)
    parser.flush()
    return parser.keys, list(dict.fromkeys(parser.runs))


MODELS = re.compile(r"Muse Glimmer|Muse Spark Open")  # a model's name without a digit; one with a digit is always a fact


def same(run: str) -> str:
    return MODELS.sub("{model}", run)


def worth_keeping(run: str) -> bool:
    """A sentence, or anything with a number in it; not a bare label or a step's number."""
    return "{" in run or len(run.split()) >= 3


def p51() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def lost(html: str) -> dict[str, list[str]]:
    """What P51's page had that this page does not: its fact keys, and its runs."""
    keys, runs = parse_runs(html)
    old = p51()
    have = set(keys)
    return {
        "facts": [k for k in old["facts"] if k not in have],
        "runs": [r for r in old["runs"] if worth_keeping(r) and not any(same(r) in same(new) for new in runs)],
    }


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docs"))
    import landing

    page_keys, page_runs = parse_runs(landing.render())
    if "--snapshot" in sys.argv:
        SNAPSHOT.write_text(json.dumps({"facts": sorted(set(page_keys)), "runs": page_runs}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {SNAPSHOT.name}: {len(set(page_keys))} fact keys, {len(page_runs)} runs")
    else:
        print("\n".join(page_runs))
