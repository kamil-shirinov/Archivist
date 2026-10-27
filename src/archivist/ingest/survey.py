"""Survey of the recurring table families, from the manifest's title hints alone. No model is called.

Each page's title is its table caption ("Table FD-1. - Summary of Federal Debt") if the hint has
one, else the first line that looks like a heading: mostly letters, in title or upper case, not a
unit line like "(In millions of dollars)". Titles are normalised and merged
when their text is nearly the same, which absorbs the OCR noise; each family is then listed with
the issues it appears in and its page count. The grouping rules were written while looking only at
development issues, and applied unchanged to the rest.

    python -m archivist.ingest.survey   # data/real/manifest.json -> results/real/survey.md
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from archivist.ingest.fraser import DEFAULT_ROOT, Manifest, PageEntry, current_split

DEFAULT_OUT = Path("results/real/survey.md")
SIMILAR = 0.85  # two normalised titles at least this alike are one family
WRAPPED_MIN = 25  # characters a title must share to be called the start of a longer one
MIN_LETTERS = 6
MIN_LETTER_SHARE = 0.6
TITLE_CASE_SHARE = 0.6

PREFIX = re.compile(r"^(table|chart)\s+[a-z0-9-]{1,8}\s*[.:\-–—]*\s*", re.IGNORECASE)
CAPTION = re.compile(
    r"(?:^|[.\s])Tab[li1]e\s+(?P<id>[A-Za-z0-9]{1,5}(?:\s?[-–—]\s?[A-Za-z0-9]{1,5}){0,3})"
    r"\s*[.:\-–—]*\s*(?P<title>.*)$",
    re.IGNORECASE,
)  # "Table FD-1. - Summary of Federal Debt"; OCR often reads Table as Tabie
PAGE_NUMBER = re.compile(r"^\d{1,3}\s+(?=[A-Za-z])")  # "24 PUBLIC DEBT OPERATIONS"
FOOTNOTE = re.compile(r"\s*\(?\b[1-9a-z]/\)?\s*$|\s*[*†‡]+\s*$")


@dataclass
class Family:
    title: str  # the commonest spelling
    spellings: Counter[str] = field(default_factory=Counter)
    pages: dict[str, int] = field(default_factory=lambda: defaultdict(int))  # issue -> pages

    @property
    def n_pages(self) -> int:
        return sum(self.pages.values())


def _heading(text: str) -> str | None:
    """The text if it reads as a heading (mostly letters, title or upper case), else None."""
    text = PAGE_NUMBER.sub("", text.strip())
    letters = sum(c.isalpha() for c in text)
    if letters < MIN_LETTERS or letters / len(text) < MIN_LETTER_SHARE or text.startswith("("):
        return None
    words = [w for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 4]
    if not words or sum(w[0].isupper() for w in words) / len(words) < TITLE_CASE_SHARE:
        return None
    return FOOTNOTE.sub("", text).strip(" .:-")


def page_title(hint: list[str]) -> str | None:
    """A table's own caption if the hint has one, else its first heading, else None.

    Later bulletins put a running section heading ("FEDERAL DEBT") above the caption ("Table FD-1.
    - Summary of Federal Debt"); the caption is the table's title. When the caption's words are on
    the next line, that line is used. Earlier bulletins have no such caption, only a heading.
    """
    for n, line in enumerate(hint):
        caption = CAPTION.search(line)
        if caption and re.search(r"[\d\-–—]", caption["id"]):
            title = caption["title"] or (hint[n + 1] if n + 1 < len(hint) else "")
            if (found := _heading(title)) is not None:
                return found
    for line in hint:
        if (found := _heading(PREFIX.sub("", line.strip()))) is not None:
            return found
    return None


def normalise(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower().replace("&", " and ")).split())


def _alike(a: str, b: str) -> bool:
    """Same heading: one is the start of the other (a different line wrap), or nearly the same text."""
    short, long = sorted((a, b), key=len)
    if len(short) >= WRAPPED_MIN and long.startswith(short):
        return True
    if len(long) * SIMILAR > len(short) * (2 - SIMILAR):  # too different in length to reach SIMILAR
        return False
    matcher = SequenceMatcher(None, a, b)
    return matcher.quick_ratio() >= SIMILAR and matcher.ratio() >= SIMILAR


def group(pages: list[PageEntry]) -> tuple[list[Family], Counter[str]]:
    """Families of pages sharing a title, and how many pages had none (by reason)."""
    keyed: dict[str, Counter[str]] = defaultdict(Counter)  # normalised -> issue -> pages
    spelled: dict[str, Counter[str]] = defaultdict(Counter)  # normalised -> raw spelling
    skipped: Counter[str] = Counter()
    for page in pages:
        if not page.title_hint:
            skipped["no OCR text"] += 1
        elif (title := page_title(page.title_hint)) is None:
            skipped["no heading in the first lines"] += 1
        else:
            key = normalise(title)
            keyed[key][page.issue] += 1
            spelled[key][title] += 1

    families: list[Family] = []
    reps: list[str] = []
    for key in sorted(keyed, key=lambda k: (-sum(keyed[k].values()), k)):  # commonest become reps
        found = next((n for n, rep in enumerate(reps) if _alike(rep, key)), None)
        if found is None:
            reps.append(key)
            families.append(Family(title=""))
            found = len(families) - 1
        families[found].spellings.update(spelled[key])
        for issue, n in keyed[key].items():
            families[found].pages[issue] += n
    for family in families:
        family.title = family.spellings.most_common(1)[0][0]
    return families, skipped


def _ranges(numbers: list[int], width: int = 0) -> str:
    out: list[str] = []
    start = prev = numbers[0]
    for n in [*numbers[1:], None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        label = lambda v: f"{v:0{width}d}"
        out.append(label(start) if start == prev else f"{label(start)}–{label(prev)}")
        if n is not None:
            start = prev = n
    return ", ".join(out)


def issues_label(issues: list[str]) -> str:
    """'01–12: 1939–1942; 06: 1982, 1985–1994' — the months, then the years that have exactly them."""
    months_by_year: dict[int, list[int]] = defaultdict(list)
    for issue in sorted(issues):
        year, month = issue.split("-")
        months_by_year[int(year)].append(int(month))
    years_by_months: dict[tuple[int, ...], list[int]] = defaultdict(list)
    for year, months in sorted(months_by_year.items()):
        years_by_months[tuple(months)].append(year)
    return "; ".join(
        f"{_ranges(list(months), 2)}: {_ranges(years)}" for months, years in years_by_months.items()
    )


def render(manifest: Manifest) -> str:
    families, skipped = group(manifest.pages)
    recurring = sorted(
        (f for f in families if len(f.pages) >= 2),
        key=lambda f: (-len(f.pages), -f.n_pages, f.title.lower()),
    )
    once = [f for f in families if len(f.pages) == 1]
    split = current_split()
    n_pages = len(manifest.pages)
    in_recurring = sum(f.n_pages for f in recurring)

    lines = [
        "# Survey of the recurring table families: Treasury Bulletin, FRASER title 407",
        "",
        (
            f"Made by `python -m archivist.ingest.survey` from the title hints in `data/real/manifest.json` "
            f"(the first lines of each PDF's own OCR text). No model was called and no page image was "
            f"looked at. {len(manifest.issues)} issues, {n_pages:,} pages."
        ),
        "",
        "## How to read it",
        "",
        (
            "- A page's *title* is its table caption if the hint has one (`Table FD-1. - Summary of "
            "Federal Debt` gives `Summary of Federal Debt`), else the first hint line that reads as "
            "a heading: mostly letters, in title or upper case, not a unit line such as "
            "`(In millions of dollars)`. Table numbers and page numbers are dropped."
        ),
        (
            f"- Titles are merged into one family when their normalised text is at least {SIMILAR:.0%} "
            f"alike, or when one is the first {WRAPPED_MIN}+ characters of the other (the same heading "
            "wrapped at a different word), so OCR misspellings of a heading usually join. A family is "
            "shown under its commonest spelling."
        ),
        (
            "- The OCR is poor on the 1939–1942 scans, so counts are approximate: a family can be split "
            "in two by a bad misreading, and two real tables with near-identical headings can be merged."
        ),
        (
            "- A hint keeps only the first 100 characters of a line, so a caption that shares its line "
            "with a section heading can be cut short (`Statements of In`); such stubs form their own "
            "small families."
        ),
        "- Only families found in two or more issues are listed. Page counts are over all issues.",
        "",
        "## Totals",
        "",
        "| | pages |",
        "|---|---:|",
        f"| all pages | {n_pages:,} |",
        f"| in a family found in 2+ issues | {in_recurring:,} |",
        f"| in a title found in one issue only ({len(once):,} titles) | {sum(f.n_pages for f in once):,} |",
        *(f"| skipped: {reason} | {count:,} |" for reason, count in sorted(skipped.items())),
        "",
        f"## Recurring families ({len(recurring):,})",
        "",
        "| # | Title | Issues | Pages | Appears in (months: years) |",
        "|--:|---|--:|--:|---|",
        *(
            f"| {n} | {f.title.replace('|', '/')} | {len(f.pages)} | {f.n_pages} | "
            f"{issues_label(list(f.pages))} |"
            for n, f in enumerate(recurring, 1)
        ),
        "",
        "## Issues by side of the split",
        "",
        (
            f"Development: {len(split.development)} issues. Held-out: {len(split.held_out)}. "
            "See `data/real/split.json`."
        ),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.ingest.survey",
        description="Survey the recurring table families from the manifest's title hints.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ROOT / "manifest.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    manifest = Manifest.model_validate_json(args.manifest.read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(manifest))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
