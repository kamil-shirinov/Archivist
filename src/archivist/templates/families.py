"""Which Treasury Bulletin table families get a drafted template, by a rule fixed before drafting.

    python -m archivist.templates.families   # -> results/real/family_choice.md

No model is called and no held-out page is opened. Families are the survey's (ingest/survey.py,
results/real/survey.md), grouped from the manifest's title hints; a family's held-out pages are
counted from those hints alone. Only the development pages a family would be drafted from are
looked at, through the PDF's own OCR text, to see whether they print a total.

The rule, applied in this order:

1. A table, not a running heading: the family's title is not in capitals. The later bulletins print
   a section heading in capitals above each table's caption, and a heading covers several tables.
2. Found in development: pages in at least MIN_DEV_ISSUES development issues of one era (1939-1942,
   or 1982-1994), the era with more of its development pages. Its drafting pages are its first page
   in each of those issues, at most DRAFT_PAGES of them, the issues spread evenly (first, middle,
   last).
3. Recurs in held-out: pages in at least MIN_HELD_OUT_ISSUES held-out issues of that era.
4. Prints totals: the word "total" is in the OCR text of every drafting page.
5. Ranked by held-out page count in its era, then by title. The top PER_ERA of each era are
   chosen, then the best of the rest from either era, up to MAX_FAMILIES in all.

A chosen family's key is its title in lower case, words joined by "_", at most 40 characters cut
at a word; a key that is already the family of a template file drafted from other pages gets
"_drafted".

Amendments. A family set aside after the choice (SET_ASIDE: its title, the date and why) is taken
out before rule 5 ranks, so the next eligible family under the same rule takes its place; the
report lists it with the reason. Set-asides are made only before any held-out page is touched.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from archivist.doctypes.template import TEMPLATES_DIR, read_template
from archivist.ingest.fraser import DEFAULT_ROOT, Manifest, current_split, pdf_name
from archivist.ingest.survey import Family, group, normalise, page_title

OUT = Path("results/real/family_choice.md")
ERAS = {"1939-1942": range(1939, 1943), "1982-1994": range(1982, 1995)}
MIN_DEV_ISSUES = 2
MIN_HELD_OUT_ISSUES = 2
DRAFT_PAGES = 3
PER_ERA = 2
MAX_FAMILIES = 6
TOTAL = re.compile(r"\btotal", re.IGNORECASE)
SET_ASIDE = {  # title -> (date, why), before any held-out page was touched
    "Collections of Internal Revenue": (
        "2026-10-28",
        "the title covers two different tables, collections by source of revenue and "
        "collections by period, and each is printed as two panels on one page (side by side, "
        "or one above the other); a page is classified as one type, so each would be one "
        "template with two panels, which the template language cannot yet describe. Its draft "
        "read the by-period table's columns across all three pages, two of which print the "
        "by-source table (results/templates/citations_dev.md)",
    ),
}


def era_of(issue: str) -> str:
    return next(name for name, years in ERAS.items() if int(issue[:4]) in years)


def page_id(issue: str, page: int) -> str:
    return f"{issue}_p{page:03d}"


@dataclass(frozen=True)
class Candidate:
    title: str
    era: str
    dev_issues: list[str]
    held_out_issues: int
    held_out_pages: int
    pages: list[str]  # the drafting pages
    totals: list[bool]  # whether each drafting page's OCR text has "total"
    excluded: str | None  # the first rule it fails, None if it passes them all


def _spread(issues: Sequence[str], n: int) -> list[str]:
    if len(issues) <= n:
        return list(issues)
    last = len(issues) - 1
    return [issues[round(k * last / (n - 1))] for k in range(n)]


def ocr_text(root: Path, issue: str, page: int) -> str:
    """A development page's own OCR text, from its PDF."""
    if issue not in current_split().development:
        raise ValueError(f"{issue} is not a development issue: its pages are not opened")
    pdf = pdfium.PdfDocument(root / "pdf" / pdf_name(issue))
    try:
        textpage = pdf[page - 1].get_textpage()
        try:
            return textpage.get_text_range()
        finally:
            textpage.close()
    finally:
        pdf.close()


def candidates(
    manifest: Manifest, text_of: Callable[[str, int], str]
) -> list[Candidate]:
    """Every recurring family, with the first rule it fails (rules 1-4)."""
    split = current_split()
    families, _ = group(manifest.pages)
    first_page: dict[tuple[str, str], int] = {}  # (family title, issue) -> first page number
    by_key = {normalise(s): f for f in families for s in f.spellings}  # as the survey titles them
    for entry in manifest.pages:
        if entry.title_hint and (title := page_title(entry.title_hint)) is not None:
            family = by_key[normalise(title)]
            key = (family.title, entry.issue)
            first_page[key] = min(first_page.get(key, entry.page), entry.page)

    out = []
    for family in sorted(families, key=lambda f: f.title.lower()):
        if len(family.pages) < 2:
            continue
        out.append(_candidate(family, split.development, split.held_out, first_page, text_of))
    return out


def _candidate(
    family: Family,
    development: Sequence[str],
    held_out: Sequence[str],
    first_page: dict[tuple[str, str], int],
    text_of: Callable[[str, int], str],
) -> Candidate:
    dev = sorted(i for i in family.pages if i in development)
    eras = {era: [i for i in dev if era_of(i) == era] for era in ERAS}
    era = max(ERAS, key=lambda e: (sum(family.pages[i] for i in eras[e]), e == "1939-1942"))
    dev_issues = eras[era]
    held = [i for i in family.pages if i in held_out and era_of(i) == era]
    held_pages = sum(family.pages[i] for i in held)

    def candidate(excluded: str | None, pages=(), totals=()) -> Candidate:
        return Candidate(
            family.title, era, dev_issues, len(held), held_pages, list(pages), list(totals),
            excluded,
        )

    letters = [c for c in family.title if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return candidate("1: a heading in capitals")
    if len(dev_issues) < MIN_DEV_ISSUES:
        return candidate(f"2: in {len(dev_issues)} development issue(s) of its era")
    if len(held) < MIN_HELD_OUT_ISSUES:
        return candidate(f"3: in {len(held)} held-out issue(s) of its era")
    issues = _spread(dev_issues, DRAFT_PAGES)
    pages = [(i, first_page[(family.title, i)]) for i in issues]
    totals = [bool(TOTAL.search(text_of(i, p))) for i, p in pages]
    ids = [page_id(i, p) for i, p in pages]
    if not all(totals):
        return candidate("4: a drafting page prints no total", ids, totals)
    return candidate(None, ids, totals)


def choose(passing: Sequence[Candidate]) -> list[Candidate]:
    """Rule 5: the top PER_ERA of each era, then the best of the rest, up to MAX_FAMILIES."""
    ranked = sorted(passing, key=lambda c: (-c.held_out_pages, c.title.lower()))
    chosen = [c for era in ERAS for c in [r for r in ranked if r.era == era][:PER_ERA]]
    for c in ranked:
        if len(chosen) >= MAX_FAMILIES:
            break
        if c not in chosen:
            chosen.append(c)
    return sorted(chosen, key=ranked.index)


def family_key(title: str, taken: Sequence[str]) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    key = ""
    for word in words:
        if len(f"{key}_{word}".strip("_")) > 40:
            break
        key = f"{key}_{word}".strip("_")
    if key[:1].isdigit():
        key = f"t_{key}"[:40]
    return f"{key[:32]}_drafted" if key in taken else key


def render(all_candidates: Sequence[Candidate], chosen: Sequence[Candidate], keys: dict) -> str:
    passing = [c for c in all_candidates if c.excluded is None and c.title not in SET_ASIDE]
    aside = [c for c in all_candidates if c.excluded is None and c.title in SET_ASIDE]
    lines = [
        "# Which Treasury families get a drafted template",
        "",
        "Made by `python -m archivist.templates.families` before any template was drafted. No "
        "model was called and no held-out page was opened: families and their held-out counts are "
        "the survey's (`results/real/survey.md`, from the manifest's title hints), and only the "
        "development pages a family would be drafted from were read, through the PDF's own OCR "
        "text."
        + (
            " Amended after drafting began, before any held-out page was touched: the families "
            "under \"Set aside after the choice\" were taken out and the next eligible family "
            "under the same rule took each one's place."
            if aside
            else ""
        ),
        "",
        "## The rule",
        "",
        "1. A table, not a running heading: the family's title is not in capitals (the later "
        "bulletins print a section heading in capitals above each table's caption, and one heading "
        "covers several tables).",
        f"2. Found in development: pages in at least {MIN_DEV_ISSUES} development issues of one "
        "era (1939-1942 or 1982-1994: the era with more of its development pages). It is drafted "
        f"from its first page in each such issue, at most {DRAFT_PAGES}, the issues spread evenly "
        "(first, middle, last).",
        f"3. Recurs in held-out: pages in at least {MIN_HELD_OUT_ISSUES} held-out issues of that "
        "era.",
        "4. Prints totals: the word \"total\" is in the OCR text of every drafting page.",
        f"5. Ranked by held-out page count in its era, then title; the top {PER_ERA} of each era, "
        f"then the best of the rest from either era, up to {MAX_FAMILIES} in all.",
        "",
        f"## Chosen ({len(chosen)})",
        "",
        "| # | Family | Era | Held-out pages | Held-out issues | Development issues | Drafted "
        "from |",
        "|--:|---|---|--:|--:|--:|---|",
        *(
            f"| {n} | `{keys[c.title]}`: {c.title} | {c.era} | {c.held_out_pages} | "
            f"{c.held_out_issues} | {len(c.dev_issues)} | {', '.join(c.pages)} |"
            for n, c in enumerate(chosen, 1)
        ),
        "",
        *(
            [
                f"## Set aside after the choice ({len(aside)})",
                "",
                "| Family | Era | Held-out pages | Drafted from | Set aside on | Why |",
                "|---|---|--:|---|---|---|",
                *(
                    f"| {c.title} | {c.era} | {c.held_out_pages} | {', '.join(c.pages)} | "
                    f"{SET_ASIDE[c.title][0]} | {SET_ASIDE[c.title][1]} |"
                    for c in aside
                ),
                "",
            ]
            if aside
            else []
        ),
        f"## Passed every rule but not chosen ({len(passing) - len(chosen)})",
        "",
        "| Family | Era | Held-out pages |",
        "|---|---|--:|",
        *(
            f"| {c.title} | {c.era} | {c.held_out_pages} |"
            for c in sorted(passing, key=lambda c: (-c.held_out_pages, c.title.lower()))
            if c not in chosen
        ),
        "",
        "## Excluded, by the first rule failed",
        "",
        "| Rule | Families | Of which with 10+ held-out pages |",
        "|---|--:|---|",
    ]
    excluded: dict[str, list[Candidate]] = {}
    for c in all_candidates:
        if c.excluded is not None:
            excluded.setdefault(c.excluded.split(":")[0], []).append(c)
    for rule, group_ in sorted(excluded.items()):
        big = sorted((c for c in group_ if c.held_out_pages >= 10), key=lambda c: -c.held_out_pages)
        names = "; ".join(f"{c.title} ({c.held_out_pages})" for c in big) or "-"
        lines.append(f"| {rule} | {len(group_)} | {names} |")
    return "\n".join([*lines, ""])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    manifest = Manifest.model_validate_json((args.root / "manifest.json").read_text())
    found = candidates(manifest, lambda issue, page: ocr_text(args.root, issue, page))
    chosen = choose([c for c in found if c.excluded is None and c.title not in SET_ASIDE])
    drafts = {
        p.stem: read_template(p).provenance.drafted_from for p in TEMPLATES_DIR.glob("*.yaml")
    }
    keys = {
        c.title: family_key(c.title, [k for k, pages in drafts.items() if pages != c.pages])
        for c in chosen
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(found, chosen, keys), encoding="utf-8")
    for c in chosen:
        print(f"{keys[c.title]:<42} {c.era}  {c.held_out_pages:>4} held-out pages  {c.pages}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
