"""Survey of the recurring table families in the Comptroller of the Currency's annual reports, from the manifest alone. No model is called.

A page's title is the caption of its table ("No. 46.—NUMBER OF NATIONAL BANKS IN EACH STATE ...",
"TABLE XXXVIII." and the line under it) found among the first lines of the PDF's own OCR text once
the running head ("REPORT OF THE COMPTROLLER OF THE CURRENCY. 123", however badly the OCR read
it) and bare page numbers are set aside. A page marked "Continued" without a caption of its own
belongs to the table of the last titled page before it. Titles are merged into families when their
text, stripped of numbers and months, is nearly the same. A family is a table family if most of
its pages are dense with figures. Two things are highlighted: statements of condition (pages with
a Resources or a Liabilities heading) and tables with printed totals (pages with a line that begins
"Total"), both counted from the OCR text when the manifest was written.

The rules were written while looking only at the development volumes (1905 and 1925) and applied
unchanged to the rest.

    python -m archivist.ingest.survey_occ   # data/real_occ/manifest.json -> results/real_occ/survey.md
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from archivist.ingest import fraser, occ
from archivist.ingest.survey import SIMILAR, _alike, normalise

DEFAULT_OUT = Path("results/real_occ/survey.md")
RUNNING_HEAD = "reportofthecomptrollerofthecurrency"
HEAD_MIN_LETTERS = 14
HEAD_COVERED = 0.7  # a line with this share of its letters inside the running head is the running head
TITLE_SHOWN = 100  # characters of a family's title shown in the tables
MIN_LETTERS = 8
MIN_LETTER_SHARE = 0.6
MIN_UPPER_SHARE = 0.7  # a heading with no caption is in capitals
MIN_HEADING_WORDS = 3  # and is not just a state or a panel ("PENNSYLVANIA", "LITTLE ROCK")
PAGE_AT_END = re.compile(r"\s+\d{1,3}$")  # the contents list ends each entry with its page
UNIT_LINE = re.compile(r"^[\[(]")  # "[Amounts in thousands of dollars]"
TABLE_PAGE_FIGURES = 20  # a table page has at least this many lines that are mostly digits
TABLE_FAMILY_SHARE = 0.5  # a table family: at least this share of its pages are table pages
HIGHLIGHT_SHARE = 0.5  # a family has totals, or is a statement of condition, in this share of table pages
CONDITION_WORDS = re.compile(r"resources|liabilities|condition", re.IGNORECASE)

CAPTION = re.compile(
    r"^(?:t?able\s*(?:no[.,]?\s*)?|no[.,]\s*)(?P<id>\d{1,3}|[ivxlc]{1,7})\b[.,]*\s*[.:\-–—]*\s*(?P<title>.*)$",
    re.IGNORECASE,
)  # "No. 46.—NUMBER OF ...", "TABLE NO. 62.—Principal items ...", "TABLE XXXVIII.", "ABLE NO. 22.—"
BARE_NUMBER = re.compile(r"^[\d\s.,\-–—]+$")
# "Continued" as the OCR garbles it, or cut short by the width of a hint: "Continu", "—Con"
CONT_CUT = r"con[tl]?(?:i(?:n(?:u(?:e(?:d)?)?)?)?)?"
CONTINUED = re.compile(rf"\bcon[tl]i?nue?d?\b|[—–-]\s*{CONT_CUT}\.?\s*$", re.IGNORECASE)
TRAILING = re.compile(
    rf"(?:[\s.:,;\-–—]+{CONT_CUT})?[\s.:,;\-–—]*$", re.IGNORECASE
)  # punctuation, and a trailing "Continued" (only that: "CONDITION" and "CONSOLS" stay)
LEADING_CONTINUED = re.compile(r"^con[tl]i?nue?d?\b[\s.:,;\-–—]*", re.IGNORECASE)  # "Continued. ABSTRACT OF ..."
CONTINUED_WORD = re.compile(r"\bcon[tl]i?nued?\b", re.IGNORECASE)
MONTHS = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", re.IGNORECASE
)


def is_running_head(line: str) -> bool:
    """The running head, however the OCR garbled it, even with its first words lost."""
    letters = re.sub(r"[^a-z]", "", line.lower())
    if len(letters) < HEAD_MIN_LETTERS:
        return False
    blocks = SequenceMatcher(None, letters, RUNNING_HEAD).get_matching_blocks()
    return sum(block.size for block in blocks) >= HEAD_COVERED * len(letters)


def _heading(text: str, capitals: bool) -> str | None:
    """The text, without its trailing 'Continued', if it reads as a heading.

    A heading is mostly letters; with `capitals`, mostly capital letters and at least
    MIN_HEADING_WORDS words (a caption needs neither: the reports print some in mixed case).
    """
    text = LEADING_CONTINUED.sub("", text.strip())
    text = PAGE_AT_END.sub("", TRAILING.sub("", text)).strip()
    letters = [c for c in text if c.isalpha()]
    if len(letters) < MIN_LETTERS or len(letters) / len(text) < MIN_LETTER_SHARE:
        return None
    if capitals and (
        sum(c.isupper() for c in letters) / len(letters) < MIN_UPPER_SHARE
        or len(re.findall(r"[A-Za-z]{3,}", text)) < MIN_HEADING_WORDS
    ):
        return None
    return text


def page_title(hint: list[str]) -> tuple[str | None, bool, bool]:
    """(title, continued, has a caption of its own) for a page's title hint.

    The title is the caption's text, joined with the line under it when that continues it, else
    the first heading in capitals among the lines that are not the running head or a page number;
    None if there is none. `continued` is whether the hint says Continued.
    """
    lines = [
        line.strip()
        for line in hint
        if line.strip() and not is_running_head(line) and not BARE_NUMBER.match(line)
    ]
    continued = any(CONTINUED.search(line) for line in hint)
    for n, line in enumerate(lines):
        caption = CAPTION.match(line)
        if not caption:
            continue
        text, rest = caption["title"], lines[n + 1 :]
        if not text and rest:
            text, rest = rest[0], rest[1:]
        if _heading(text, capitals=False) is None:
            continue
        if rest and not UNIT_LINE.match(rest[0]) and _heading(rest[0], capitals=False) is not None:
            text = f"{text} {rest[0]}"
        return _heading(text, capitals=False), continued, True
    for line in lines:
        if (found := _heading(line, capitals=True)) is not None:
            return found, continued, False
    return None, continued, False


def family_key(title: str) -> str:
    """The title as families compare it: no numbers, months or 'continued', lower case, one space."""
    return normalise(CONTINUED_WORD.sub(" ", MONTHS.sub(" ", re.sub(r"\d+", " ", title))))


@dataclass
class Family:
    title: str  # the commonest spelling
    spellings: Counter[str] = field(default_factory=Counter)
    pages: list[occ.PageEntry] = field(default_factory=list)

    @property
    def volumes(self) -> list[str]:
        return sorted({p.issue for p in self.pages})

    @property
    def years(self) -> list[str]:
        return sorted({p.issue[:4] for p in self.pages})

    @property
    def table_pages(self) -> list[occ.PageEntry]:
        return [p for p in self.pages if p.figure_lines >= TABLE_PAGE_FIGURES]

    @property
    def is_table(self) -> bool:
        return len(self.table_pages) >= TABLE_FAMILY_SHARE * len(self.pages)

    @property
    def with_totals(self) -> list[occ.PageEntry]:
        return [p for p in self.table_pages if p.total_lines >= 1]

    @property
    def with_resources(self) -> list[occ.PageEntry]:
        return [p for p in self.table_pages if p.resources_heading]

    @property
    def with_liabilities(self) -> list[occ.PageEntry]:
        return [p for p in self.table_pages if p.liabilities_heading]

    @property
    def has_totals(self) -> bool:
        return len(self.with_totals) >= HIGHLIGHT_SHARE * max(1, len(self.table_pages))

    @property
    def is_condition(self) -> bool:
        """A statement of condition: titled so, or Resources or Liabilities headings on most pages."""
        headed = {id(p) for p in (*self.with_resources, *self.with_liabilities)}
        return bool(CONDITION_WORDS.search(self.title)) or len(headed) >= HIGHLIGHT_SHARE * max(
            1, len(self.table_pages)
        )


def titled(pages: list[occ.PageEntry]) -> list[tuple[occ.PageEntry, str | None]]:
    """Each page with its title: its own caption, or for a 'Continued' page the last page's title."""
    out: list[tuple[occ.PageEntry, str | None]] = []
    last: dict[str, str] = {}
    for page in pages:
        title, continued, captioned = page_title(page.title_hint)
        if continued and not captioned and page.issue in last:
            title = last[page.issue]
        if title is not None and (captioned or not continued):
            last[page.issue] = title
        out.append((page, title))
    return out


def group(pages: list[occ.PageEntry]) -> tuple[list[Family], Counter[str]]:
    """Families of pages sharing a title, and how many pages had none (by reason)."""
    keyed: dict[str, list[occ.PageEntry]] = defaultdict(list)
    spelled: dict[str, Counter[str]] = defaultdict(Counter)
    skipped: Counter[str] = Counter()
    for page, title in titled(pages):
        if not page.title_hint:
            skipped["no OCR text"] += 1
        elif title is None or not family_key(title):
            skipped["no heading in the first lines"] += 1
        else:
            key = family_key(title)
            keyed[key].append(page)
            spelled[key][title] += 1

    families: list[Family] = []
    reps: list[str] = []
    for key in sorted(keyed, key=lambda k: (-len(keyed[k]), k)):  # commonest become reps
        found = next((n for n, rep in enumerate(reps) if _alike(rep, key)), None)
        if found is None:
            reps.append(key)
            families.append(Family(title=""))
            found = len(families) - 1
        families[found].spellings.update(spelled[key])
        families[found].pages += keyed[key]
    for family in families:
        family.title = family.spellings.most_common(1)[0][0]
    return families, skipped


def _pages(n: int) -> str:
    return f"{n:,}"


def render(manifest: occ.Manifest) -> str:
    families, skipped = group(manifest.pages)
    split = occ.current_split()
    tables = [f for f in families if f.is_table]
    recurring = sorted(
        (f for f in tables if len(f.years) >= 2),
        key=lambda f: (-len(f.years), -len(f.pages), f.title.lower()),
    )
    once = [f for f in tables if len(f.years) == 1]
    conditions = [f for f in recurring if f.is_condition]
    totals = [f for f in recurring if f.has_totals]
    n_pages = len(manifest.pages)
    n_table_pages = sum(len(f.table_pages) for f in tables)
    n_recurring = sum(len(f.pages) for f in recurring)

    def shown(title: str) -> str:
        title = title.replace("|", "/")
        return title if len(title) <= TITLE_SHOWN else title[:TITLE_SHOWN].rstrip() + "…"

    def row(n: int, f: Family) -> str:
        dev = [y for y in f.years if y in split.development]
        held = [y for y in f.years if y in split.held_out]
        marks = ("C" if f.is_condition else "") + ("T" if f.has_totals else "")
        return (
            f"| {n} | {shown(f.title)} | {marks} | {len(dev)} | {len(held)} | "
            f"{len(f.pages)} | {len(f.with_totals)} | {len(f.with_resources)} | "
            f"{len(f.with_liabilities)} | {', '.join(f.years)} |"
        )

    header = [
        "| # | Title | Flags | Dev years | Held-out years | Pages | With totals | With Resources | With Liabilities | Appears in |",
        "|--:|---|---|--:|--:|--:|--:|--:|--:|---|",
    ]
    lines = [
        "# Survey of the recurring table families: Comptroller of the Currency annual reports, FRASER title 56",
        "",
        (
            "Made by `python -m archivist.ingest.survey_occ` from the title hints and OCR counts in "
            "`data/real_occ/manifest.json` (the first lines of each PDF's own OCR text, and counts over "
            f"all of it). No model was called and no page image was looked at. {len(manifest.issues)} "
            f"volumes in {len(occ.years())} years, {n_pages:,} pages."
        ),
        "",
        "## How to read it",
        "",
        (
            "- A page's *title* is its table caption (`No. 46.—NUMBER OF NATIONAL BANKS IN EACH STATE ...`, "
            "or `TABLE XXXVIII.` and the line under it), found among the first lines of the hint once the "
            "running head (`REPORT OF THE COMPTROLLER OF THE CURRENCY. 123`, matched even when the OCR "
            "misreads it) and bare page numbers are set aside; else the first heading in capitals. "
            "Table numbers are dropped, as they restart every year."
        ),
        (
            "- A page marked `Continued` with no caption of its own takes the title of the last titled "
            "page before it in the same volume; a table continued over many pages is one family."
        ),
        (
            f"- Titles are merged into one family when their text without numbers and months is at "
            f"least {SIMILAR:.0%} alike, or one is the start of the other. Numbers and months are "
            "dropped so that a title carrying a date still matches across years."
        ),
        (
            f"- A *table page* has at least {TABLE_PAGE_FIGURES} OCR lines that are mostly digits; a "
            f"*table family* has at least {TABLE_FAMILY_SHARE:.0%} table pages. Prose sections with a "
            "capitalised heading are therefore left out. Only table families found in two or more "
            "years are listed (a year's two volumes count once); page counts are over all volumes."
        ),
        (
            f"- **C**, a statement of condition: the title names resources, liabilities or condition, or "
            f"at least {HIGHLIGHT_SHARE:.0%} of the family's table pages have a line that begins "
            "`Resources` or `Liabilities`. The abstracts print resources and liabilities on facing pages, "
            "so most pages carry one heading, not both."
        ),
        (
            f"- **T**, printed totals: at least {HIGHLIGHT_SHARE:.0%} of the family's table pages have a "
            "line that begins `Total`. *With totals*, *With Resources* and *With Liabilities* count "
            "table pages."
        ),
        (
            "- The OCR is imperfect, so counts are approximate: a family can be split in two by a bad "
            "misreading, and two real tables with near-identical titles can be merged. A hint keeps the "
            f"first {fraser.HINT_LINES} lines of {fraser.HINT_WIDTH} characters, so a long title is cut."
        ),
        (
            "- Families are made from the words of a title, so a table printed under a different title in "
            "different years is two families: the 1905 `ABSTRACT OF REPORTS OF THE NATIONAL BANKING "
            "ASSOCIATIONS` and the 1925 `ABSTRACT OF CONDITION OF NATIONAL BANKS` are two families, each found in "
            "one year only, so neither is listed."
        ),
        (
            "- FRASER notes that for 1923 to 1941 the *Individual Statements of Condition of National "
            "Banks* were published as a separate supplement; the volumes of 1925, 1930, 1935 and 1940 "
            "therefore hold no individual statements, only aggregates."
        ),
        "",
        "## Totals",
        "",
        "| | pages |",
        "|---|---:|",
        f"| all pages | {_pages(n_pages)} |",
        f"| table pages in any table family | {_pages(n_table_pages)} |",
        f"| in a table family found in 2+ years | {_pages(n_recurring)} |",
        f"| in a table family found in one year only ({len(once):,} families) | {_pages(sum(len(f.pages) for f in once))} |",
        *(f"| skipped: {reason} | {_pages(count)} |" for reason, count in sorted(skipped.items())),
        "",
        f"## Statements of condition (resources and liabilities), found in 2+ years ({len(conditions):,})",
        "",
        *header,
        *(row(n, f) for n, f in enumerate(conditions, 1)),
        "",
        f"## Tables with printed totals, found in 2+ years ({len(totals):,})",
        "",
        *header,
        *(row(n, f) for n, f in enumerate(totals, 1)),
        "",
        f"## All recurring table families ({len(recurring):,})",
        "",
        *header,
        *(row(n, f) for n, f in enumerate(recurring, 1)),
        "",
        "## Volumes by side of the split",
        "",
        "| Side | Years | Volumes | Pages |",
        "|---|---|--:|--:|",
        *(
            f"| {side} | {', '.join(years_)} | "
            f"{sum(1 for e in manifest.issues if e.issue[:4] in years_)} | "
            f"{_pages(sum(e.pages for e in manifest.issues if e.issue[:4] in years_))} |"
            for side, years_ in (
                ("development", split.development),
                ("held-out", split.held_out),
            )
        ),
        "",
        "See `data/real_occ/split.json`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.ingest.survey_occ",
        description="Survey the recurring table families of the annual reports from the manifest.",
    )
    parser.add_argument("--manifest", type=Path, default=occ.DEFAULT_ROOT / "manifest.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    manifest = occ.Manifest.model_validate_json(args.manifest.read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(manifest))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
