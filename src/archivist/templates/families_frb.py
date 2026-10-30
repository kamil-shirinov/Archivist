"""Which Federal Reserve Bulletin tables get a drafted template, by a rule fixed beforehand (P28).

    python -m archivist.templates.families_frb   # -> results/real_frb/family_choice.md

No model is called and no page image is opened. Tables are the survey's (ingest/survey_frb.py,
results/real_frb/survey.md), from the manifest's numbered captions and Total lines: a table is a
number together with its title, never a number alone, since numbers are renamed and reused over the
years (survey_frb.group keeps a reused number's tables apart). Held-out pages are counted from the
manifest alone.

The rule, applied in this order:

1. Prints totals: the survey's rule, at least half of the issues it is found in print a Total line
   after its caption, and so does every development issue it is drafted from.
2. Found in development: in at least MIN_DEV_ISSUES of the development issues (June 1980, 1990 and
   2000). Its drafting pages are its first page in each of them (data/real_frb/pages/<issue>/pNNN),
   at most DRAFT_PAGES.
3. Recurs in held-out: in at least MIN_HELD_OUT_ISSUES held-out issues.
4. Ranked first by kind, tables of bank assets and liabilities before the rest, then by held-out
   page count, then by number. A table is one of bank assets and liabilities when its title names
   banks (BANK_WORDS) and what they hold or owe (BALANCE_WORDS). The top MAX_FAMILIES are chosen.

A chosen table's key is "frb_" with its number and the first words of its title, in lower case,
joined by "_", at most 40 characters cut at a word. The drafter is told only the table's printed
title: its number and caption as the OCR reads them on its first development page, a footnote mark
at the end dropped, or, where the OCR's caption is cut short, as read off that page's image
(READ_OFF).
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from archivist.ingest import frb
from archivist.ingest.survey_frb import Table, group, tables_of

OUT = Path("results/real_frb/family_choice.md")
MIN_DEV_ISSUES = 2
MIN_HELD_OUT_ISSUES = 2
DRAFT_PAGES = 3
MAX_FAMILIES = 4
BANK_WORDS = re.compile(r"\b(banks?|banking|depository institutions)\b", re.IGNORECASE)
BALANCE_WORDS = re.compile(
    r"\b(assets|liabilities|condition|balance sheet|claims|loans and securities)\b", re.IGNORECASE
)
FOOTNOTE = re.compile(r"(?<=[A-Za-z])\d+$")
READ_OFF = {  # number -> the caption as printed, where the OCR's is cut short (frb-1990-06_p130)
    "3.19": "BANKS' OWN AND DOMESTIC CUSTOMERS' CLAIMS ON FOREIGNERS Reported by Banks in the "
    "United States",
}


def page_ref(issue: str, page: int) -> str:
    """A Federal Reserve Bulletin page as the template commands name it (templates/pages.py)."""
    return f"frb-{issue}_p{page:03d}"


@dataclass(frozen=True)
class Candidate:
    table: Table
    dev_issues: list[str]
    held_out_issues: list[str]
    held_out_pages: int
    banks: bool  # a table of bank assets and liabilities
    failed: int | None  # the first rule it fails, or None

    @property
    def title(self) -> str:
        return f"{self.table.number} {self.table.title}"


def is_bank_balance(title: str) -> bool:
    """Whether a title names banks and what they hold or owe; a footnote mark at its end, which
    the OCR joins to the last word ("Banks1"), is dropped first."""
    title = FOOTNOTE.sub("", title.strip())
    return bool(BANK_WORDS.search(title) and BALANCE_WORDS.search(title))


def candidates(tables: Sequence[Table], split: frb.Split) -> list[Candidate]:
    out = []
    for table in tables:
        dev = [i for i in table.issues if i in split.development]
        held = [i for i in table.issues if i in split.held_out]
        failed = None
        if not table.has_totals() or not all(table.seen[i].total_lines for i in dev):
            failed = 1
        elif len(dev) < MIN_DEV_ISSUES:
            failed = 2
        elif len(held) < MIN_HELD_OUT_ISSUES:
            failed = 3
        out.append(
            Candidate(
                table=table,
                dev_issues=dev,
                held_out_issues=held,
                held_out_pages=sum(len(table.seen[i].pages) for i in held),
                banks=is_bank_balance(table.title),
                failed=failed,
            )
        )
    return out


def rank(passing: Sequence[Candidate]) -> list[Candidate]:
    def number(c: Candidate) -> tuple[int, ...]:
        return tuple(int(p) for p in c.table.number.split("."))

    return sorted(passing, key=lambda c: (not c.banks, -c.held_out_pages, number(c)))


def drafting_pages(candidate: Candidate) -> list[str]:
    issues = candidate.dev_issues[:DRAFT_PAGES]
    return [page_ref(i, candidate.table.seen[i].pages[0]) for i in issues]


def printed_title(candidate: Candidate) -> str:
    """The number and caption the drafter is told: as the OCR reads them on the first drafting
    issue's caption, without a footnote mark at the end."""
    number = candidate.table.number
    first = candidate.table.seen[candidate.dev_issues[0]]
    return f"{number} {READ_OFF.get(number) or FOOTNOTE.sub('', first.title.strip())}".strip()


def family_key(candidate: Candidate) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", candidate.table.title.lower()).split()
    key = "frb_" + candidate.table.number.replace(".", "_")
    for word in words:
        if len(key) + 1 + len(word) > 40:
            break
        key += "_" + word
    return key


def render(all_candidates: Sequence[Candidate], chosen: Sequence[Candidate]) -> str:
    passing = rank([c for c in all_candidates if c.failed is None])
    lines = [
        "# Which Federal Reserve Bulletin tables get a drafted template",
        "",
        "Made by `python -m archivist.templates.families_frb` before any template was drafted. "
        "No model was called and no page image was opened: tables, their issues and their pages "
        "are the survey's (`results/real_frb/survey.md`), from the manifest's numbered captions "
        "and Total lines. A table is a number together with its title, never a number alone, "
        "since numbers are reused for other tables over the years.",
        "",
        "## The rule",
        "",
        "1. Prints totals: at least half of the issues it is found in print a Total line after its "
        "caption (the survey's rule), and so does every development issue it is drafted from.",
        f"2. Found in development: in at least {MIN_DEV_ISSUES} of the development issues (June "
        "1980, 1990 and 2000). Drafted from its first page in each, at most "
        f"{DRAFT_PAGES}.",
        f"3. Recurs in held-out: in at least {MIN_HELD_OUT_ISSUES} held-out issues.",
        "4. Ranked first by kind, tables of bank assets and liabilities first, then by held-out "
        "page count, then by number; the top "
        f"{MAX_FAMILIES} are chosen. A table is one of bank assets and liabilities when its title "
        "names banks (bank, banks, banking, depository institutions) and what they hold or owe "
        "(assets, liabilities, condition, balance sheet, claims, loans and securities).",
        "",
        "The drafter is told only the printed title: the number and caption as the OCR reads them "
        "on the first drafting page, a footnote mark at the end dropped, or, where the OCR cut "
        "the caption short, as read off that page's image (3.19, on frb-1990-06_p130).",
        "",
        f"## Chosen ({len(chosen)})",
        "",
        "| # | Family | Table | Bank assets and liabilities | Held-out pages | Held-out issues "
        "| Development issues | Drafted from | Title given |",
        "|--:|---|---|---|--:|--:|--:|---|---|",
    ]
    for n, c in enumerate(chosen, 1):
        lines.append(
            f"| {n} | `{family_key(c)}` | {c.title} | {'yes' if c.banks else 'no'} | "
            f"{c.held_out_pages} | {len(c.held_out_issues)} | {len(c.dev_issues)} | "
            f"{', '.join(drafting_pages(c))} | {printed_title(c)} |"
        )
    rest = [c for c in passing if c not in chosen]
    lines += [
        "",
        f"## Passed every rule but not chosen ({len(rest)})",
        "",
        "| Table | Bank assets and liabilities | Held-out pages | Held-out issues |",
        "|---|---|--:|--:|",
    ]
    lines += [
        f"| {c.title} | {'yes' if c.banks else 'no'} | {c.held_out_pages} | "
        f"{len(c.held_out_issues)} |"
        for c in rest
    ]
    failed = [c for c in all_candidates if c.failed is not None and c.table.has_totals()]
    lines += [
        "",
        "## Tables with printed totals excluded, by the first rule failed",
        "",
        "| Table | Rule failed | Development issues | Held-out issues |",
        "|---|--:|--:|--:|",
    ]
    lines += [
        f"| {c.title} | {c.failed} | {len(c.dev_issues)} | {len(c.held_out_issues)} |"
        for c in sorted(failed, key=lambda c: (c.failed, c.title))
    ]
    return "\n".join(lines) + "\n"


def choose(manifest: frb.Manifest, split: frb.Split) -> tuple[list[Candidate], list[Candidate]]:
    """Every table as a candidate, and those chosen."""
    found = candidates(group(tables_of(manifest.pages)), split)
    return found, rank([c for c in found if c.failed is None])[:MAX_FAMILIES]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=frb.DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    manifest = frb.Manifest.model_validate_json((args.root / "manifest.json").read_text())
    split = frb.Split.model_validate_json((args.root / "split.json").read_text())
    found, chosen = choose(manifest, split)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(found, chosen), encoding="utf-8")
    for c in chosen:
        print(f"{family_key(c)}: {c.title}; {c.held_out_pages} held-out pages; {drafting_pages(c)}")


if __name__ == "__main__":
    main()
