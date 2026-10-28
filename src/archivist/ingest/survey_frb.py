"""Survey of the recurring numbered tables in the Federal Reserve Bulletin, from the manifest alone. No model is called.

The Bulletin numbers the tables of its statistics section ("1.26 COMMERCIAL BANKS IN THE UNITED
STATES Assets and Liabilities") and numbers the rows of each ("16 Total assets"). The manifest holds,
for every page, the numbered captions found in the PDF's own OCR text and the lines that begin
"Total" after each (or, before the page's first caption, those of the table it continues). A table
in one issue is a number: a caption repeated on later pages ("Continued") is the same table, and its
total lines are the sum over its pages. Across issues a table is a number together with a title: the
titles of one number are merged into a family when their text, stripped of numbers and months, is
nearly the same (the P20 rule, survey.SIMILAR), so a number reused for another table is kept
apart. A table is *recurring* if it is found in at least half of the issues ingested, and has
*printed totals* if at least half of the issues it is found in print a Total line.

The rules were written before the ingested pages were looked at and are applied unchanged to all of
them.

    python -m archivist.ingest.survey_frb   # data/real_frb/manifest.json -> results/real_frb/survey.md
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from archivist.ingest import frb, fraser
from archivist.ingest.survey import SIMILAR, _alike, issues_label, normalise

DEFAULT_OUT = Path("results/real_frb/survey.md")
RECURRING_SHARE = 0.5  # recurring: found in at least this share of the issues ingested
TOTALS_SHARE = 0.5  # printed totals: at least this share of the issues it is found in print a Total line
TABLE_PAGE_FIGURES = 20  # a table page has at least this many lines that are mostly digits
TITLE_SHOWN = 90  # characters of a title shown in the tables


@dataclass
class Seen:
    """A numbered table in one issue."""

    number: str
    title: str  # the first caption's words
    pages: list[int] = field(default_factory=list)
    total_lines: int = 0


def tables_of(pages: list[frb.PageEntry]) -> dict[str, dict[str, Seen]]:
    """Issue -> number -> the table, from the pages in order. A page's leading total lines go to the
    table that was last captioned, on the page before; a caption repeated is the same table."""
    out: dict[str, dict[str, Seen]] = defaultdict(dict)
    current: Seen | None = None
    last_issue = None
    for page in pages:
        if page.issue != last_issue:
            current, last_issue = None, page.issue
        here = out[page.issue]
        if current is not None:
            current.total_lines += page.leading_total_lines
        for mark in page.tables:
            current = here.setdefault(mark.number, Seen(mark.number, mark.title))
            if page.page not in current.pages:
                current.pages.append(page.page)
            current.total_lines += mark.total_lines
            current.title = current.title or mark.title
    return out


@dataclass
class Table:
    number: str
    spellings: Counter[str] = field(default_factory=Counter)
    seen: dict[str, Seen] = field(default_factory=dict)  # issue -> the table in that issue

    @property
    def title(self) -> str:
        return self.spellings.most_common(1)[0][0] if self.spellings else ""

    @property
    def issues(self) -> list[str]:
        return sorted(self.seen)

    @property
    def with_totals(self) -> list[str]:
        return [i for i in self.issues if self.seen[i].total_lines]

    @property
    def n_pages(self) -> int:
        return sum(len(s.pages) for s in self.seen.values())

    @property
    def n_total_lines(self) -> int:
        return sum(s.total_lines for s in self.seen.values())

    def has_totals(self) -> bool:
        return len(self.with_totals) >= TOTALS_SHARE * max(1, len(self.issues))

    def is_recurring(self, n_issues: int) -> bool:
        return len(self.issues) >= RECURRING_SHARE * n_issues


def group(by_issue: dict[str, dict[str, Seen]]) -> list[Table]:
    """The tables across issues: each number's captions merged into families by their titles."""
    by_number: dict[str, list[tuple[str, Seen]]] = defaultdict(list)
    for issue, tables in by_issue.items():
        for number, seen in tables.items():
            by_number[number].append((issue, seen))

    tables: list[Table] = []
    for number in sorted(by_number, key=lambda n: tuple(int(p) for p in n.split("."))):
        observed = by_number[number]
        keyed: dict[str, list[tuple[str, Seen]]] = defaultdict(list)
        for issue, seen in observed:
            keyed[normalise(seen.title)].append((issue, seen))
        families: list[Table] = []
        reps: list[str] = []
        for key in sorted(keyed, key=lambda k: (-len(keyed[k]), k)):  # commonest become reps
            found = next((n for n, rep in enumerate(reps) if key and _alike(rep, key)), None)
            if found is None:
                if not key and families:  # no title: the number's commonest family
                    found = 0
                else:
                    reps.append(key)
                    families.append(Table(number))
                    found = len(families) - 1
            for issue, seen in keyed[key]:
                families[found].seen[issue] = seen
                if seen.title:
                    families[found].spellings[seen.title] += 1
        tables += families
    return tables


def _shown(title: str) -> str:
    title = title.replace("|", "/")
    return title if len(title) <= TITLE_SHOWN else title[:TITLE_SHOWN].rstrip() + "…"


def render(manifest: frb.Manifest, split: frb.Split | None = None) -> str:
    issues = [e.issue for e in manifest.issues]
    split = split or frb.current_split(issues)
    by_issue = tables_of(manifest.pages)
    tables = group(by_issue)
    n = len(issues)
    dev = [i for i in issues if split.side(i) == "development"]
    held = [i for i in issues if split.side(i) == "held_out"]
    recurring = [t for t in tables if t.is_recurring(n)]
    with_totals = [t for t in recurring if t.has_totals()]
    without = [t for t in recurring if not t.has_totals()]
    rare = [t for t in tables if not t.is_recurring(n)]
    reused = sorted({t.number for t in tables if sum(u.number == t.number for u in tables) > 1})
    n_pages = len(manifest.pages)
    captioned = sum(bool(p.tables) for p in manifest.pages)
    dense_uncaptioned = sum(
        p.figure_lines >= TABLE_PAGE_FIGURES and not p.tables for p in manifest.pages
    )

    def row(k: int, t: Table) -> str:
        return (
            f"| {k} | {t.number} | {_shown(t.title)} | {len(t.issues)} | "
            f"{sum(i in dev for i in t.issues)} | {sum(i in held for i in t.issues)} | "
            f"{len(t.with_totals)} | {t.n_total_lines} | {t.n_pages} | {issues_label(t.issues)} |"
        )

    header = [
        f"| # | Table | Title | Issues (of {n}) | Dev (of {len(dev)}) | Held-out (of {len(held)}) | "
        "Issues with a Total line | Total lines | Pages | Appears in (months: years) |",
        "|--:|---|---|--:|--:|--:|--:|--:|--:|---|",
    ]
    lines = [
        "# Survey of the recurring numbered tables with printed totals: Federal Reserve Bulletin, FRASER title 62",
        "",
        (
            "Made by `python -m archivist.ingest.survey_frb` from the title hints and OCR counts in "
            "`data/real_frb/manifest.json` (the first lines of each PDF's own OCR text, and the numbered "
            f"captions and Total lines found in all of it). No model was called and no page image was "
            f"looked at. {n} June issues, {n_pages:,} pages."
        ),
        "",
        "## How to read it",
        "",
        (
            "- A *table* in one issue is a number from the statistics section (`1.26`, `3.17`): a line "
            "that begins with a number of the form `d.dd` and a caption in capitals "
            "(`1.26 COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities`). A caption repeated "
            "on later pages (`Continued`) is the same table. Its months, years and `Continued` are "
            "dropped from the title, which the hint cuts at "
            f"{fraser.HINT_WIDTH} characters."
        ),
        (
            "- A *Total line* is a line that begins `Total` or `Totals`, after a row number if it has "
            "one (`16 Total assets`), found after the table's caption on its page; those before a "
            "page's first caption belong to the table the page continues. They are lines, not tables: "
            "a table can print several (`Total, all foreigners`, `Total vault cash`)."
        ),
        (
            f"- Across issues a table is its number *and* its title: the titles of one number are "
            f"merged when their text without numbers and months is at least {SIMILAR:.0%} "
            "alike, or one is the start of the other, so a number reused for another table is listed "
            "apart (see the section on numbers with more than one title)."
        ),
        (
            f"- *Recurring*: found in at least {RECURRING_SHARE:.0%} of the {n} issues. *Printed "
            f"totals*: at least {TOTALS_SHARE:.0%} of the issues the table is found in print a Total line. "
            "The rules were written before the pages were looked at and are applied unchanged to all of "
            "them."
        ),
        (
            "- The OCR is imperfect, so counts are approximate: a caption misread (`1.l2`) is a table "
            "missed in that issue, a table printed below another on a page is found only if its caption "
            "is read, and a Total line is counted only if the OCR keeps `Total` at the start of the "
            "line. Whether a table's *figures* add up to its totals is not looked at here."
        ),
        "",
        "## Pages",
        "",
        "| | pages |",
        "|---|---:|",
        f"| all pages | {n_pages:,} |",
        f"| with a numbered caption | {captioned:,} |",
        f"| with {TABLE_PAGE_FIGURES}+ figure lines and no numbered caption (a table continued from an "
        f"earlier page, or one that is not numbered) | {dense_uncaptioned:,} |",
        "",
        "## Issues",
        "",
        "| Issue | Side | Pages | Numbered tables | With a Total line |",
        "|---|---|--:|--:|--:|",
        *(
            f"| {i} | {split.side(i).replace('_', '-')} | "
            f"{next(e.pages for e in manifest.issues if e.issue == i):,} | {len(by_issue[i])} | "
            f"{sum(bool(s.total_lines) for s in by_issue[i].values())} |"
            for i in issues
        ),
        "",
        f"## Recurring numbered tables with printed totals ({len(with_totals):,})",
        "",
        *header,
        *(row(k, t) for k, t in enumerate(with_totals, 1)),
        "",
        f"## Recurring numbered tables without printed totals ({len(without):,})",
        "",
        *header,
        *(row(k, t) for k, t in enumerate(without, 1)),
        "",
        f"## Numbered tables found in fewer than {RECURRING_SHARE:.0%} of the issues ({len(rare):,})",
        "",
        *header,
        *(row(k, t) for k, t in enumerate(rare, 1)),
        "",
        f"## Numbers with more than one title ({len(reused):,})",
        "",
        (
            "A number whose captions fall into two or more families is either a table renamed, a number "
            "reused for another table, or an OCR misreading. Each family is a row above; this lists "
            "the numbers so that they are not taken for one table."
        ),
        "",
        "| Table | Titles |",
        "|---|---|",
        *(
            f"| {number} | "
            + " / ".join(
                f"{_shown(t.title)} ({len(t.issues)})" for t in tables if t.number == number
            )
            + " |"
            for number in reused
        ),
        "",
        "## Issues by side of the split",
        "",
        "| Side | Issues | Pages |",
        "|---|--:|--:|",
        *(
            f"| {side} | {', '.join(ids)} | "
            f"{sum(e.pages for e in manifest.issues if e.issue in ids):,} |"
            for side, ids in (("development", dev), ("held-out", held))
        ),
        "",
        "See `data/real_frb/split.json`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m archivist.ingest.survey_frb",
        description="Survey the recurring numbered tables of the Federal Reserve Bulletin from the manifest.",
    )
    parser.add_argument("--manifest", type=Path, default=frb.DEFAULT_ROOT / "manifest.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    manifest = frb.Manifest.model_validate_json(args.manifest.read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(manifest))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
