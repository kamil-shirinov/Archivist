from pathlib import Path

from archivist.ingest import frb, survey_frb

REPO = Path(__file__).resolve().parents[1]


def page(issue: str, number: int, *tables: tuple[str, str, int], leading: int = 0, figures: int = 0):
    marks = [{"number": n, "title": t, "total_lines": c} for n, t, c in tables]
    return frb.PageEntry(
        issue=issue,
        page=number,
        sha256="0" * 64,
        size_bytes=1,
        width=1,
        height=1,
        title_hint=["x"],
        lines=60,
        figure_lines=figures,
        total_lines=leading + sum(c for _, _, c in tables),
        leading_total_lines=leading,
        tables=marks,
    )


def manifest(pages: list[frb.PageEntry]) -> frb.Manifest:
    counts: dict[str, int] = {}
    for p in pages:
        counts[p.issue] = max(counts.get(p.issue, 0), p.page)
    return frb.Manifest(
        renderer={"pypdfium2": "x", "pillow": "x", "dpi": 200, "jpeg_quality": 90},
        issues=[{"issue": i, "pages": n} for i, n in counts.items()],
        pages=pages,
    )


RESERVES = "RESERVES, MONEY STOCK, AND DEBT MEASURES"


def test_a_caption_repeated_on_later_pages_is_one_table_and_its_totals_add_up():
    pages = [
        page("1980-06", 1, ("1.26", "COMMERCIAL BANKS IN THE UNITED STATES", 1)),
        page("1980-06", 2, leading=2),  # the same table, continued, with two more Total lines
        page("1980-06", 3, ("1.26", "COMMERCIAL BANKS IN THE UNITED STATES", 3), ("1.27", "OTHER", 0)),
        page("1990-06", 1, leading=5),  # a new issue: nothing to continue
    ]
    tables = survey_frb.tables_of(pages)
    seen = tables["1980-06"]["1.26"]
    assert (seen.pages, seen.total_lines) == ([1, 3], 1 + 2 + 3)
    assert tables["1980-06"]["1.27"].total_lines == 0
    assert tables["1990-06"] == {}


def test_a_total_line_before_the_first_caption_of_a_page_goes_to_the_table_of_the_page_before():
    pages = [
        page("1980-06", 1, ("1.10", RESERVES, 0)),
        page("1980-06", 2, ("1.12", "RESERVES AND BORROWINGS", 1), leading=0),
        page("1980-06", 3, leading=4),
    ]
    tables = survey_frb.tables_of(pages)["1980-06"]
    assert (tables["1.10"].total_lines, tables["1.12"].total_lines) == (0, 5)


def test_titles_of_one_number_that_read_alike_are_one_table_and_a_reused_number_is_another():
    by_issue = {
        "1980-06": {"1.26": survey_frb.Seen("1.26", "COMMERCIAL BANKS IN THE UNITED STATES", [1], 2)},
        "1981-06": {"1.26": survey_frb.Seen("1.26", "COMMERCIAL BANKS IN THE UNITED STATES.", [1], 2)},
        "1982-06": {"1.26": survey_frb.Seen("1.26", "CONSUMER CREDIT OUTSTANDING AND ITS TERMS", [1], 0)},
        "1983-06": {"1.26": survey_frb.Seen("1.26", "", [1], 1)},  # no title: joins the commonest
    }
    tables = survey_frb.group(by_issue)
    assert [(t.number, t.issues) for t in tables] == [
        ("1.26", ["1980-06", "1981-06", "1983-06"]),
        ("1.26", ["1982-06"]),
    ]
    assert tables[0].title == "COMMERCIAL BANKS IN THE UNITED STATES"


def test_tables_are_ordered_by_their_numbers():
    numbers = ("2.12", "1.26", "1.09", "1.10")
    by_issue = {"1980-06": {n: survey_frb.Seen(n, f"TABLE {n} TITLE", [1], 0) for n in numbers}}
    assert [t.number for t in survey_frb.group(by_issue)] == ["1.09", "1.10", "1.26", "2.12"]


def issues_with(tables_by_issue: dict[str, list[tuple[str, str, int]]]):
    pages = []
    for issue, tables in tables_by_issue.items():
        for number, (n, title, totals) in enumerate(tables, 1):
            pages.append(page(issue, number, (n, title, totals), figures=30))
    return pages


def test_recurring_means_half_the_issues_and_printed_totals_means_half_of_those_it_is_in():
    heads = {
        "1.10": "RESERVES, MONEY STOCK, AND DEBT MEASURES",
        "1.12": "RESERVES AND BORROWINGS Depository Institutions",
        "1.43": "U.S. GOVERNMENT SECURITIES DEALERS Positions",
    }
    pages = issues_with(
        {
            "1980-06": [("1.10", heads["1.10"], 1), ("1.12", heads["1.12"], 0), ("1.43", heads["1.43"], 1)],
            "1981-06": [("1.10", heads["1.10"], 1), ("1.12", heads["1.12"], 0)],
            "1982-06": [("1.10", heads["1.10"], 0), ("1.12", heads["1.12"], 0)],
            "1983-06": [("1.10", heads["1.10"], 1)],
        }
    )
    m = manifest(pages)
    tables = {t.number: t for t in survey_frb.group(survey_frb.tables_of(m.pages))}
    n = len(m.issues)
    assert tables["1.10"].is_recurring(n) and tables["1.10"].has_totals()  # 4 of 4 issues, 3 print totals
    assert tables["1.12"].is_recurring(n) and not tables["1.12"].has_totals()  # 3 of 4, none print one
    assert not tables["1.43"].is_recurring(n)  # 1 of 4


def test_the_survey_lists_tables_in_the_section_their_rules_put_them():
    pages = issues_with(
        {
            "1980-06": [("1.10", RESERVES, 1), ("1.12", "RESERVES AND BORROWINGS", 0), ("3.25", "MARKETABLE BONDS AND NOTES", 1)],
            "1990-06": [("1.10", RESERVES, 2), ("1.12", "RESERVES AND BORROWINGS", 0)],
            "2001-06": [("1.10", RESERVES, 1), ("1.12", "RESERVES AND BORROWINGS", 0)],
        }
    )
    text = survey_frb.render(manifest(pages))
    sections = {s.split("\n", 1)[0]: s for s in text.split("\n## ")}
    with_totals = next(s for h, s in sections.items() if h.startswith("Recurring numbered tables with printed totals (1)"))
    without = next(s for h, s in sections.items() if h.startswith("Recurring numbered tables without printed totals (1)"))
    rare = next(s for h, s in sections.items() if h.startswith("Numbered tables found in fewer than 50% of the issues (1)"))
    assert "| 1.10 | " + RESERVES in with_totals and "1.12" not in with_totals
    assert "| 1.12 | RESERVES AND BORROWINGS" in without
    assert "| 3.25 | MARKETABLE BONDS AND NOTES" in rare
    assert "| 1980-06 | development |" in text and "| 2001-06 | held-out |" in text
    assert "No model was called" in text and "3 June issues" in text
    assert all(line == line.rstrip() for line in text.splitlines())


def test_the_committed_survey_is_what_the_committed_manifest_gives():
    manifest_ = frb.Manifest.model_validate_json((REPO / "data/real_frb/manifest.json").read_text())
    committed = (REPO / "results/real_frb/survey.md").read_text()
    assert committed == survey_frb.render(manifest_)
    assert all(line == line.rstrip() for line in committed.splitlines())
    assert committed.endswith("\n") and not committed.endswith("\n\n")
