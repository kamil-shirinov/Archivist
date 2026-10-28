"""Which Comptroller of the Currency table families get a drafted template, by a rule fixed before drafting (P25).

    python -m archivist.templates.families_occ   # -> results/real_occ/family_choice.md

No model is called and no held-out page is opened. Families are the survey's (ingest/survey_occ.py,
results/real_occ/survey.md), grouped from the manifest's title hints, and a family's held-out pages
are counted from those hints alone. Whether two survey families print one table, or one survey
family prints two, was judged by a person from development pages only and is recorded in JUDGED.

The rule, applied in this order:

1. Kind: every member family is flagged by the survey as a statement of condition (C) or as a
   table with printed totals (T); a table is a statement of condition when a member is flagged C.
2. One table in both development years: a table is one survey family, or several printed under
   different titles in different years and judged the same table (JUDGED, same=True); it has
   table pages in 1905 and in 1925 among its members' development pages. A member's development
   pages are only those of the years it is judged for: a survey family whose pages in one
   development year print another table contributes none of them. A table judged two tables
   (same=False) fails this rule.
3. Recurs in held-out: its members have pages in at least MIN_HELD_OUT_YEARS held-out years.
4. Prints totals: in each development year a member table page has a line that begins "Total"
   (the manifest's count). Drafted from the first such page in each development year, and, for a
   statement of condition where neither page carries a Liabilities heading (or neither a Resources
   heading), from the first development table page that does and prints a Total line, so the draft
   sees both halves of a statement printed on facing pages.
5. Ranked by held-out page count (the members' together), then name; the top MIN_CONDITION
   statements of condition, then the best of the rest, up to MAX_FAMILIES in all.

Judging. Candidates are the survey families that pass rule 1 with table pages in both development
years, and pairs of survey families that pass rule 1, each with table pages in one development
year only, whose titles name the same subject and whose held-out pages together could reach the
last choice. They are judged in rank order until the choice is made, by looking at the first table
page of each member in each development year and the page facing it where the table is printed
across two: one table when it has the same stub and the same measures, allowing items added,
dropped or renamed. A family found only in held-out years is never merged in, as that would need
a held-out page; so a table's held-out count is its development members' and may be short.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from archivist.ingest import occ
from archivist.ingest.survey_occ import Family, group

OUT = Path("results/real_occ/family_choice.md")
MIN_HELD_OUT_YEARS = 2
MIN_CONDITION = 2
MAX_FAMILIES = 4
DRAFT_FROM = "1925"  # the year whose printed title names the table to the drafter


@dataclass(frozen=True)
class Judged:
    key: str  # the template's family name, if chosen
    name: str
    members: dict[str, tuple[str, ...]]  # survey family title -> the development years judged for
    same: bool
    looked_at: tuple[str, ...]  # the development pages the judgement was made from
    why: str


JUDGED = (
    Judged(
        "occ_abstract_by_states",
        "Abstract of reports, arranged by States and reserve cities",
        {
            "SUMMARY OF REPORTS OF NATIONAL BANKS SINCE SEPTEMBER 6, 1904": ("1905",),
            "SEPTEMBER 6, 1904, ARRANGED BY STATES AND RESERVE CITIES": ("1905",),
            "ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS": ("1925",),
        },
        True,
        ("1905_p507", "1905_p508", "1925_p341"),
        "the same table retitled: 1905's Summary of reports of national banks since September 6, "
        "1904, arranged by States and reserve cities, and 1925's Abstract of reports since October "
        "10, 1924, arranged by States and reserve cities, each a state's resources and liabilities "
        "at each call of the year, one column per call with its number of banks, and a Total; "
        "1905 prints resources and liabilities on facing pages and up to three states a page, "
        "1925 both on one page, one state a page, and the items changed. The survey's ABSTRACT OF "
        "REPORTS OF CONDITION OF NATIONAL BANKS is taken for 1925 only: its 1905 pages are "
        "Tables I to IV, the abstracts of State, savings and private banks and of loan and trust "
        "companies, another table",
    ),
    Judged(
        "occ_aggregate_resources_liabilities",
        "Aggregate resources and liabilities of national banks",
        {
            "AGGREGATE RESOURCES AND LIABILITIES OF THE NATIONAL": ("1905", "1925"),
            "Aggregate resources and liabilities of national banks from January, 1914, to "
            "September": ("1925",),
        },
        True,
        ("1905_p399", "1925_p326"),
        "one survey family already, in both years: the national banks' aggregate resources (and, "
        "on the facing or the same page, liabilities) at each call, one panel a year, one column "
        "a call with its number of banks, and a Total; 1905 runs from 1863, 1925 from 1914. The "
        "1925 title as the OCR reads it on two pages is the second member",
    ),
    Judged(
        "",
        "Principal items of resources and liabilities of national banks",
        {"PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS": ("1905", "1925")},
        False,
        ("1905_p570", "1925_p466"),
        "two tables under one title: 1905's is each state's history, a row a year from 1863 with "
        "its number of banks, loans, bonds, cash, capital, surplus, profits, circulation, deposits "
        "and total assets; 1925's (Table 62) is each state's counties on one date, with other "
        "items. Neither is in both development years",
    ),
    Judged(
        "",
        "Lawful money reserve / Reserve computation of national banks",
        {
            "LAWFUL MONEY RESERVE OF THE NATIONAL BANKS AT DATE OF": ("1905",),
            "Reserve computation of national banks at date of each report during": ("1925",),
        },
        False,
        ("1905_p160", "1905_p161", "1925_p318"),
        "the same stub (central reserve cities, other reserve cities, states) but different "
        "measures: 1905 prints deposits and the lawful money held, amount and per cent, and on the "
        "facing page the reserve required; 1925 prints net amounts due from banks, the amount on "
        "which reserve is computed, the reserve required and that held with Federal reserve banks",
    ),
    Judged(
        "occ_banks_in_charge_of_receivers",
        "National banks placed in the hands of (in charge of) receivers",
        {
            "NATIONAL BANKS WHICH HAVE BEEN PLACED IN THE HANDS OF": ("1905",),
            "National banks in charge of receivers during year ended October 81,1930, capital at "
            "da causes of failure, dividends paid while solvent, circulation outstanding at date "
            "of failure, lawful": ("1925",),
        },
        True,
        ("1905_p239", "1905_p240", "1925_p238"),
        "the same table retitled: each failed bank by name and location, its charter number, "
        "date and capital at organization, its dividends while solvent, its capital at failure, "
        "the receiver's appointment, the cause of failure, the lawful money deposited and the "
        "circulation; 1905 prints it across facing pages, grouped by year of failure with a Total "
        "line for each, 1925 on one page with total deposits at suspension",
    ),
    Judged(
        "",
        "Specie and circulation / Circulation of national banks",
        {
            "SPECIE AND CIRCULATION OF NATIONAL BANKS AT DATE OF": ("1905",),
            "Circulation of national banks at date of each report during the year ended": (
                "1925",
            ),
        },
        False,
        ("1905_p130", "1905_p131", "1925_p308"),
        "the same stub but different measures: 1905 prints the banks' specie by kind (gold coin, "
        "gold certificates, clearing-house certificates, silver), 1925 the notes received from the "
        "Comptroller, on hand and outstanding at each call",
    ),
    Judged(
        "occ_earnings_and_dividends",
        "Abstract of reports of earnings and dividends of national banks",
        {
            "Abstract of reports of earnings and dividends of national banks, by size of banks, "
            "for by Federal Reserve districts": ("1905",),
            "EARNINGS AND DIVIDENDS OF NATIONAL BANKS": ("1925",),
        },
        True,
        ("1905_p186", "1905_p187", "1925_p061"),
        "the same table, split by the survey's grouping rather than by its title: each state and "
        "reserve city with Total lines for each group of states, and the items of one earnings "
        "statement (capital, surplus, earnings, losses charged off, dividends); 1905 prints them "
        "across facing pages, 1925 across several, in thousands, with ratios",
    ),
)


@dataclass(frozen=True)
class Candidate:
    key: str
    name: str
    condition: bool
    judged: Judged | None  # None: a single survey family, not judged (ranked below the choice)
    dev_years: tuple[str, ...]
    held_out_years: tuple[str, ...]
    held_out_pages: int
    pages: tuple[str, ...]  # the drafting pages
    title: str | None  # the printed title on the DRAFT_FROM drafting page, if any
    excluded: str | None  # the first rule it fails, None if it passes them all


def page_id(page: occ.PageEntry) -> str:
    return f"{page.issue}_p{page.page:03d}"


def flagged(family: Family) -> bool:
    return family.is_condition or family.has_totals


def _member(families: Sequence[Family], title: str) -> Family:
    found = [f for f in families if f.title == title]
    if len(found) != 1:
        raise ValueError(f"the survey has {len(found)} families titled {title!r}")
    return found[0]


def _drafting_pages(table_pages: Sequence[occ.PageEntry], condition: bool) -> list[occ.PageEntry]:
    split = occ.current_split()
    with_total = sorted(
        (p for p in table_pages if p.total_lines >= 1), key=lambda p: (p.issue, p.page)
    )
    chosen = []
    for year in split.development:
        first = next((p for p in with_total if p.issue[:4] == year), None)
        if first is None:
            return []
        chosen.append(first)
    if condition:
        for heading in ("liabilities_heading", "resources_heading"):
            if not any(getattr(p, heading) for p in chosen):
                other = next((p for p in with_total if getattr(p, heading)), None)
                if other is not None and other not in chosen:
                    chosen.append(other)
                break
    return chosen


def candidate(
    families: Sequence[Family],
    members: dict[str, tuple[str, ...]],
    judged: Judged | None,
    titles: dict[str, str],
) -> Candidate:
    """A table made of its member survey families, with the first rule it fails."""
    split = occ.current_split()
    found = [(_member(families, title), years) for title, years in members.items()]
    condition = any(f.is_condition for f, _ in found)
    dev_pages = [p for f, years in found for p in f.table_pages if p.issue[:4] in years]
    held = [p for f, _ in found for p in f.pages if split.side(p.issue) == "held_out"]
    dev_years = tuple(sorted({p.issue[:4] for p in dev_pages}))
    held_years = tuple(sorted({p.issue[:4] for p in held}))
    key = judged.key if judged else ""
    name = judged.name if judged else found[0][0].title

    def out(excluded: str | None, pages=()) -> Candidate:
        ids = tuple(page_id(p) for p in pages)
        title = next((titles[i] for i in ids if i in titles), None)
        return Candidate(
            key, name, condition, judged, dev_years, held_years, len(held), ids, title, excluded
        )

    if not all(flagged(f) for f, _ in found):
        return out("1: a member is neither a statement of condition nor prints totals")
    if judged is not None and not judged.same:
        return out("2: two tables, judged from development pages")
    if set(dev_years) != set(split.development):
        return out(f"2: table pages in development year(s) {', '.join(dev_years) or 'none'}")
    if len(held_years) < MIN_HELD_OUT_YEARS:
        return out(f"3: in {len(held_years)} held-out year(s)")
    pages = _drafting_pages(dev_pages, condition)
    if not pages:
        return out("4: a development year has no table page with a Total line")
    return out(None, pages)


def candidates(manifest: occ.Manifest, titles: dict[str, str]) -> list[Candidate]:
    """Every judged table, and every survey family that passes rule 1 in both development years."""
    families, _ = group(manifest.pages)
    split = occ.current_split()
    judged_titles = {title for j in JUDGED for title in j.members}
    out = [candidate(families, j.members, j, titles) for j in JUDGED]
    for family in sorted(families, key=lambda f: f.title.lower()):
        years = {p.issue[:4] for p in family.table_pages}
        if (
            family.is_table
            and flagged(family)
            and family.title not in judged_titles
            and set(split.development) <= years
        ):
            members = {family.title: tuple(split.development)}
            out.append(candidate(families, members, None, titles))
    return out


def choose(passing: Sequence[Candidate]) -> list[Candidate]:
    """Rule 5: the top MIN_CONDITION statements of condition, then the best of the rest."""
    ranked = sorted(passing, key=lambda c: (-c.held_out_pages, c.name.lower()))
    chosen = [c for c in ranked if c.condition][:MIN_CONDITION]
    for c in ranked:
        if len(chosen) >= MAX_FAMILIES:
            break
        if c not in chosen:
            chosen.append(c)
    chosen = sorted(chosen, key=ranked.index)
    unjudged = [c for c in ranked if c.judged is None and c not in chosen]
    if chosen and unjudged and unjudged[0].held_out_pages >= chosen[-1].held_out_pages:
        raise ValueError(f"{unjudged[0].name!r} could be chosen: judge it before choosing")
    return chosen


# The title printed on each chosen table's 1925 drafting page, copied from the page image (the OCR
# hint misreads some figures of it); passed to the drafter as --title.
PRINTED_TITLES = {
    "1925_p342": "Abstract of reports since October 10, 1924, arranged by States and reserve cities",
    "1925_p326": "Aggregate resources and liabilities of national banks from January, 1914, to "
    "September, 1925",
    "1925_p238": "National banks in charge of receivers, year ended October 31, 1925, capital at "
    "date of organization and at date of failure, causes of failure, dividends paid while "
    "solvent, circulation outstanding at date of failure, lawful money deposited with Treasurer "
    "of the United States to redeem circulation, and total deposits at date of suspension",
    "1925_p061": "Abstract of reports of earnings and dividends of national banks for the year "
    "ended June 30, 1925",
}


def _cell(text: str) -> str:
    return text.replace("|", "/")


def render(all_candidates: Sequence[Candidate], chosen: Sequence[Candidate]) -> str:
    passing = [c for c in all_candidates if c.excluded is None]
    lines = [
        "# Which Comptroller of the Currency tables get a drafted template",
        "",
        "Made by `python -m archivist.templates.families_occ` before any template was drafted. "
        "No model was called and no held-out page was opened: families and their held-out counts "
        "are the survey's (`results/real_occ/survey.md`, from the manifest's title hints and OCR "
        "counts). Which survey families print one table was judged by looking at development "
        "pages only (1905 and 1925), listed below with each judgement.",
        "",
        "## The rule",
        "",
        "1. Kind: every member family is flagged by the survey a statement of condition (C) or a "
        "table with printed totals (T). A table is a statement of condition when a member is C.",
        "2. One table in both development years: one survey family, or several printed under "
        "different titles in different years and judged the same table; with table pages in 1905 "
        "and in 1925 among the development pages it is judged for. A survey family that prints "
        "two different tables fails.",
        f"3. Recurs in held-out: pages in at least {MIN_HELD_OUT_YEARS} held-out years, as the "
        "survey groups them.",
        "4. Prints totals: in each development year a table page with a line that begins "
        "`Total`. Drafted from the first such page in each development year and, for a statement "
        "of condition where neither carries a Liabilities heading (or neither a Resources "
        "heading), from the first development page that does, so the draft sees both halves of "
        "a statement printed on facing pages.",
        f"5. Ranked by held-out page count, then name: the top {MIN_CONDITION} statements of "
        f"condition, then the best of the rest, up to {MAX_FAMILIES} in all.",
        "",
        "The drafter is told only the table's printed title, as printed on its 1925 drafting page "
        "(read off the page image, since the OCR misreads some of its figures).",
        "",
        "## How one table was told from two",
        "",
        "Candidates are the survey families that pass rule 1 with table pages in both development "
        "years, and pairs of survey families that pass rule 1, each found in one development "
        "year only, whose titles name the same subject and whose held-out pages together could "
        "reach the last choice. Each was judged, in rank order until the choice was made, from "
        "the first table page of each member in each development year and the page facing it "
        "where the table is printed across two: one table when the stub and the measures are the "
        "same, allowing items added, dropped or renamed over twenty years. A family found only "
        "in held-out years is never merged in, since judging it would open a held-out page, so a "
        "table's held-out count is that of its development members and may be short (1910's "
        "`ABSTRACT OF REPORTS SINCE SEPTEMBER 1, 1909` reads like the abstract by States, but its "
        "one 1905 page is the District of Columbia's loan and trust companies, another table; "
        "1935's and 1940's receivers' tables carry titles of their own). It may also be long, "
        "where a survey family holds another table too: `ABSTRACT OF REPORTS OF CONDITION OF "
        "NATIONAL BANKS` also holds 1925's abstract by Federal reserve district (Table 60), and "
        "the earnings family is titled after 1935's abstract by size of banks, so their held-out "
        "pages may include such tables. The abstract by States leads either way; but if the "
        "earnings family's 39 pages of 1935 are mostly another table, its count falls to 13, "
        "below National banks chartered (22), which would then be fourth. Telling which needs "
        "the held-out pages, so the survey's count stands.",
        "",
        "| Table | Survey families (development years judged for) | Looked at | One table? | Why |",
        "|---|---|---|---|---|",
        *(
            f"| {j.name} | "
            + "; ".join(f"`{_cell(t)}` ({', '.join(y)})" for t, y in j.members.items())
            + f" | {', '.join(j.looked_at)} | {'yes' if j.same else 'no'} | {_cell(j.why)} |"
            for j in JUDGED
        ),
        "",
        f"## Chosen ({len(chosen)})",
        "",
        "| # | Family | Kind | Held-out pages | Held-out years | Drafted from | Title given |",
        "|--:|---|---|--:|---|---|---|",
        *(
            f"| {n} | `{c.key}`: {c.name} | {'C' if c.condition else 'T'} | {c.held_out_pages} | "
            f"{', '.join(c.held_out_years)} | {', '.join(c.pages)} | {c.title} |"
            for n, c in enumerate(chosen, 1)
        ),
        "",
        f"## Passed every rule but not chosen ({len(passing) - len(chosen)})",
        "",
        "Not judged: each is one survey family in both development years, ranked below the last "
        "choice, so whether its two years print one table was not looked at.",
        "",
        "| Family | Kind | Held-out pages | Held-out years |",
        "|---|---|--:|---|",
        *(
            f"| {_cell(c.name)} | {'C' if c.condition else 'T'} | {c.held_out_pages} | "
            f"{', '.join(c.held_out_years)} |"
            for c in sorted(passing, key=lambda c: (-c.held_out_pages, c.name.lower()))
            if c not in chosen
        ),
        "",
        "## Excluded",
        "",
        "| Table | Held-out pages | First rule failed |",
        "|---|--:|---|",
        *(
            f"| {_cell(c.name)} | {c.held_out_pages} | {c.excluded} |"
            for c in sorted(all_candidates, key=lambda c: (-c.held_out_pages, c.name.lower()))
            if c.excluded is not None
        ),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=occ.DEFAULT_ROOT / "manifest.json")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    manifest = occ.Manifest.model_validate_json(args.manifest.read_text())
    found = candidates(manifest, PRINTED_TITLES)
    chosen = choose([c for c in found if c.excluded is None])
    if untitled := [c.key for c in chosen if c.title is None]:
        raise ValueError(f"no printed title recorded for the drafting pages of {untitled}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(found, chosen), encoding="utf-8")
    for c in chosen:
        print(f"{c.key:<38} {c.held_out_pages:>4} held-out pages  {c.pages}  {c.title!r}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
