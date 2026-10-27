from pathlib import Path

import pytest

from archivist.ingest import fraser, survey

REPO = Path(__file__).resolve().parents[1]


def page(issue: str, number: int, *hint: str) -> fraser.PageEntry:
    return fraser.PageEntry(
        issue=issue,
        page=number,
        sha256="0" * 64,
        size_bytes=1,
        width=1,
        height=1,
        title_hint=list(hint),
    )


@pytest.mark.parametrize(
    ("hint", "title"),
    [
        # the table number sits on its own line, then the title, then the unit line
        (["11", "Collections of Internal Revenue", "(In thousands of dollars)"], "Collections of Internal Revenue"),
        (["Table FFO-1.—Summary of Fiscal Operations"], "Summary of Fiscal Operations"),
        (["TABLE 3.- Public Debt Outstanding", "by issues"], "Public Debt Outstanding"),
        (["GENERAL FUND AND PUBLIC DEBT", "-17-"], "GENERAL FUND AND PUBLIC DEBT"),
        (["Holdings of Direct and Guaranteed Obligations of the United States i/"], "Holdings of Direct and Guaranteed Obligations of the United States"),
    ],
)  # fmt: skip
def test_the_title_is_the_first_line_that_reads_as_a_heading(hint, title):
    assert survey.page_title(hint) == title


@pytest.mark.parametrize(
    ("hint", "title"),
    [
        # a running section heading sits above the caption; the caption is the table's title
        (["FEDERAL DEBT", "Table FD— 1. - Summary of Federal Debt"], "Summary of Federal Debt"),
        # OCR read Table as Tabie, and the caption shares a line with a section label
        (["Section I.—Government Corporations Tabie GA-l-2.—Statements of Income"], "Statements of Income"),
        # the caption's words are on the next line
        (["76", "CAPITAL MOVEMENTS", "Table CM-l-2.", "Total Liabilities by Type"], "Total Liabilities by Type"),
        # a page number glued to the heading is not part of it
        (["24 PUBLIC DEBT OPERATIONS"], "PUBLIC DEBT OPERATIONS"),
        # a sentence that mentions a table is not a caption
        (["See Table 4 for details of the sources", "Federal Debt"], "Federal Debt"),
    ],
)  # fmt: skip
def test_a_table_caption_beats_the_section_heading_above_it(hint, title):
    assert survey.page_title(hint) == title


@pytest.mark.parametrize(
    "hint",
    [
        [],
        ["(In millions of dollars)"],
        ["^^", "COo", "^6", "o o"],
        ["16", "S4"],
        ["The statistics are classified by countries and geographical areas as follows:"],
    ],
)
def test_figures_unit_lines_noise_and_running_text_have_no_title(hint):
    assert survey.page_title(hint) is None


def test_ocr_misspellings_and_a_different_line_wrap_join_one_family():
    pages = [
        page("1939-01", 1, "Collections of Internal Revenue"),
        page("1939-02", 1, "Collections of Internal Revenue"),
        page("1939-03", 1, "Collections of lnternal Revenue"),  # OCR l for I
        page("1939-01", 2, "Holdings of Direct and Guaranteed Interest-Bearing Obligations"),
        page("1939-02", 2, "Holdings of Direct and Guaranteed Interest-Bearing Obligations of the"),
        page("1939-01", 3, "Components of Silver Monetary Stock"),
    ]
    families, skipped = survey.group(pages)
    by_title = {f.title: f for f in families}
    assert len(families) == 3 and not skipped
    assert by_title["Collections of Internal Revenue"].pages == {
        "1939-01": 1,
        "1939-02": 1,
        "1939-03": 1,
    }
    assert sum(f.n_pages for f in families) == 6
    assert sorted(len(f.pages) for f in families) == [1, 2, 3]


def test_pages_without_a_title_are_counted_by_reason_not_dropped():
    pages = [page("1939-01", 1), page("1939-01", 2, "16"), page("1939-01", 3, "Public Debt")]
    families, skipped = survey.group(pages)
    assert dict(skipped) == {"no OCR text": 1, "no heading in the first lines": 1}
    assert [f.title for f in families] == ["Public Debt"]


def test_issues_are_labelled_by_months_and_the_years_that_have_them():
    monthly = [f"{y}-{m:02d}" for y in range(1939, 1943) for m in range(1, 13)]
    assert survey.issues_label(monthly) == "01–12: 1939–1942"
    junes = ["1982-06", *(f"{y}-06" for y in range(1985, 1995))]
    assert survey.issues_label(junes) == "06: 1982, 1985–1994"
    assert survey.issues_label(["1939-01", "1939-02", "1939-04", "1940-01"]) == (
        "01–02, 04: 1939; 01: 1940"
    )


def test_the_committed_survey_is_what_the_committed_manifest_gives():
    manifest = fraser.Manifest.model_validate_json((REPO / "data/real/manifest.json").read_text())
    committed = (REPO / "results/real/survey.md").read_text()
    assert committed == survey.render(manifest)
    assert all(line == line.rstrip() for line in committed.splitlines())
