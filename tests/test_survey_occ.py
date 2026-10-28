from pathlib import Path

import pytest

from archivist.ingest import occ, survey_occ

REPO = Path(__file__).resolve().parents[1]


def page(volume: str, number: int, *hint: str, figures: int = 40, totals: int = 0, res=False, lib=False):
    return occ.PageEntry(
        issue=volume,
        page=number,
        sha256="0" * 64,
        size_bytes=1,
        width=1,
        height=1,
        title_hint=list(hint),
        lines=figures + 10,
        figure_lines=figures,
        total_lines=totals,
        resources_heading=res,
        liabilities_heading=lib,
    )


HEAD = "REPORT OF THE COMPTROLLER OF THE CURRENCY. 123"


@pytest.mark.parametrize(
    "line",
    [
        HEAD,
        "204 REPORT OF THE COMPTROLLER OF THE CURRENCY.",
        "EEPOKT OF THE COMPTROLLEK OF THE CURRENCY. 8 1",  # OCR misreads
        "BEPOET OP THE COMPTEOLLEK OF THE CUEKENCT. 519",
        "REPORT OF TH E COMPTROLLER OF TH E CURRENCY.",
        "COMPTROISkER OF THE CURRENCY",  # the first words lost
        "REPORT OF THE COMPTROLLER OF THE CURRENCY 5",
    ],
)
def test_the_running_head_is_found_however_the_ocr_read_it(line):
    assert survey_occ.is_running_head(line)


@pytest.mark.parametrize(
    "line",
    [
        "NAMES AND COMPENSATION OF OFFICERS AND CLERKS IN THE OFFICE OF THE COMPTROLLER OF THE CURRENCY",
        "No. 46.—NUMBER OF NATIONAL BANKS IN EACH STATE, RESERVE CITY, AND TERRITORY",
        "Principal items of resources and liabilities of",
        "123",
        "Total",
        "",
    ],
)
def test_a_title_that_mentions_the_comptroller_is_not_the_running_head(line):
    assert not survey_occ.is_running_head(line)


@pytest.mark.parametrize(
    ("hint", "title", "captioned"),
    [
        # 1905: the caption in capitals, wrapped over two lines
        (
            [HEAD, "No. 46.—NUMBER OF NATIONAL BANKS IN EACH STATE, RESERVE CITY, AND TERRI", "TORY, CAPITAL, BONDS ON DEPOSIT", "Reserve city, State, or"],
            "NUMBER OF NATIONAL BANKS IN EACH STATE, RESERVE CITY, AND TERRI TORY, CAPITAL, BONDS ON DEPOSIT",
            True,
        ),
        # 1925: mixed case, TABLE NO., a unit line that is not part of the title
        (
            [HEAD, "TABLE NO. 62.—Principal items of resources and liabilities of", "national banks, Federal reserve districts, April 6, 1925", "[Amounts in thousands of dollars]"],
            "Principal items of resources and liabilities of national banks, Federal reserve districts, April 6, 1925",
            True,
        ),
        ([HEAD, "TABLE NO. 94", "SHOWING INDIVIDUAL STATEMENTS", "[In dollars]"], "SHOWING INDIVIDUAL STATEMENTS", True),
        ([HEAD, "TABLE XXXVIII.", "PER CAPITA, IN THE PRINCIPAL COUNTRIES OF THE WORLD", "397"], "PER CAPITA, IN THE PRINCIPAL COUNTRIES OF THE WORLD", True),
        ([HEAD, "TABLE NO, 15.—National banks chartered during the year ended Oct."], "National banks chartered during the year ended Oct", True),  # OCR: comma for point
        ([HEAD, "ABLE NO. 22.—United States bonds—Monthly range of prices"], "United States bonds—Monthly range of prices", True),  # OCR: lost T
        # the caption is not on the first line, and a bare page number precedes it
        (["65", "65 68 " + HEAD, "No. 2.—NAMES AND COMPENSATION OF OFFICERS"], "NAMES AND COMPENSATION OF OFFICERS", True),
        # no caption: the first heading in capitals with three words or more
        ([HEAD, "PENNSYLVANIA", "INSOLVENT NATIONAL BANKS.", "The banks listed in the following table"], "INSOLVENT NATIONAL BANKS", False),
    ],
)  # fmt: skip
def test_the_title_is_the_caption_or_the_first_capitalised_heading(hint, title, captioned):
    found, _, has_caption = survey_occ.page_title(hint)
    assert (found, has_caption) == (title, captioned)


@pytest.mark.parametrize(
    "hint",
    [
        [],
        [HEAD],
        [HEAD, "123", "45"],
        [HEAD, "PENNSYLVANIA", "Cities"],  # a state is a panel, not a table
        [HEAD, "LITTLE ROCK", "Firs", "t Nationa"],
        [HEAD, "The number of national bank failures during the current year showed", "a considerable decrease"],
        ["Firs", "t Nationa", "l Bank", ", Magdalena"],  # a table body whose OCR runs vertically
    ],
)
def test_pages_without_a_caption_or_a_real_heading_have_no_title(hint):
    assert survey_occ.page_title(hint)[0] is None


def test_a_leading_continued_is_not_part_of_the_title():
    found, continued, _ = survey_occ.page_title([HEAD, "Continued. ABSTRACT OF REPORTS OF CONDITION OF STATE BANKS"])
    assert found == "ABSTRACT OF REPORTS OF CONDITION OF STATE BANKS" and continued


def test_the_contents_lists_page_number_is_not_part_of_the_title():
    found, _, captioned = survey_occ.page_title(["No. 1. Comptrollers and Deputy Comptrollers of the Currency 183"])
    assert found == "Comptrollers and Deputy Comptrollers of the Currency" and captioned


@pytest.mark.parametrize(
    "hint",
    [
        [HEAD, "Abstract of reports since October 10, 1924, arranged by States", "Continued", "KENTUCKY—Continued"],
        [HEAD, "UNITED STATES, ETC., AT THE CLOSE OF BUSINESS JANUARY 11, 1905—Continu"],
        [HEAD, "AMOUNTS COLLECTED FROM ALL SOURCES, ETC.—Continued."],
        [HEAD, "ABSTRACT OF REPORTS OF THE NATIONAL BANKING ASSOCIATIONS OF THE", "LIABILITIES—Continued."],
        [HEAD, "TABLE NO. 63.—Principal items of resources and liabilities of national banks—Contin"],
        [HEAD, "NATIONAL BANKS WHICH HAVE BEEN PLACED IN THE HANDS OF RECEIVERS, ETC.—Con"],
        [HEAD, "RESOURCES—Conlinued."],  # OCR read t as l
    ],
)
def test_continued_is_recognised_even_when_cut_or_misread(hint):
    assert survey_occ.page_title(hint)[1]


@pytest.mark.parametrize(
    "hint",
    [
        [HEAD, "No. 1.—ABSTRACT OF REPORTS OF CONDITION OF NATIONAL BANKS"],
        [HEAD, "No. 1.—Consolidation of banks, a first notice of conditions"],
        [HEAD, "No. 2.—PRICES OF CONSOLS"],
    ],
)
def test_a_title_that_merely_mentions_condition_or_consols_is_not_continued(hint):
    assert not survey_occ.page_title(hint)[1]


@pytest.mark.parametrize("last", ["CONDITION", "CONSOLS", "CONTINENTAL", "CONSTRUCTION", "CONGRESS"])
def test_a_title_keeps_a_last_word_that_starts_like_continued(last):
    found, _, _ = survey_occ.page_title([HEAD, f"No. 1.—SUMMARY OF THE REPORTS OF {last}"])
    assert found == f"SUMMARY OF THE REPORTS OF {last}"
    found, _, _ = survey_occ.page_title([HEAD, f"No. 1.—SUMMARY OF THE REPORTS OF {last}—Continued."])
    assert found == f"SUMMARY OF THE REPORTS OF {last}"


def test_a_continued_page_takes_the_title_of_the_last_titled_page_in_its_volume():
    pages = [
        page("1905", 1, HEAD, "No. 74.—INSOLVENT NATIONAL BANKS, DATES OF ORGANIZATION"),
        page("1905", 2, HEAD, "AMOUNTS COLLECTED FROM ALL SOURCES, ETC.—Continued."),  # tail of the title
        page("1905", 3, HEAD, "No. 75.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS"),
        page("1905", 4, HEAD, "No. 75.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS—Continued."),  # its own caption
        page("1910", 1, HEAD, "AMOUNTS COLLECTED FROM ALL SOURCES, ETC.—Continued."),  # nothing before it here
    ]
    assert [t for _, t in survey_occ.titled(pages)] == [
        "INSOLVENT NATIONAL BANKS, DATES OF ORGANIZATION",
        "INSOLVENT NATIONAL BANKS, DATES OF ORGANIZATION",
        "LAWFUL MONEY RESERVE OF THE NATIONAL BANKS",
        "LAWFUL MONEY RESERVE OF THE NATIONAL BANKS",
        "AMOUNTS COLLECTED FROM ALL SOURCES, ETC",
    ]


def test_a_title_with_a_different_date_a_misreading_or_a_wrap_is_one_family():
    pages = [
        page("1905", 1, HEAD, "No. 12.—NATIONAL BANKS CHARTERED DURING THE YEAR ENDED OCTOBER 31, 1905"),
        page("1910", 1, HEAD, "TABLE NO. 15.—National banks chartered during the year ended October 31, 1910"),
        page("1915", 1, HEAD, "No. 12.—NATIONAL BANKS CHARTERED DURING THE YEAR ENDED OCTOBEB 31, 1915"),
        page("1905", 2, HEAD, "No. 13.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS"),
        page("1910", 2, HEAD, "TABLE NO. 16.—Lawful money reserve of the national banks at date of each report"),
        page("1905", 3, HEAD, "No. 14.—INSOLVENT NATIONAL BANKS"),
    ]
    families, skipped = survey_occ.group(pages)
    assert not skipped
    by_years = sorted((tuple(f.years), len(f.pages)) for f in families)
    assert by_years == [(("1905",), 1), (("1905", "1910"), 2), (("1905", "1910", "1915"), 3)]


def test_pages_without_a_title_are_counted_by_reason_not_dropped():
    pages = [
        page("1905", 1),
        page("1905", 2, HEAD, "123"),
        page("1905", 3, HEAD, "No. 14.—INSOLVENT NATIONAL BANKS"),
    ]
    families, skipped = survey_occ.group(pages)
    assert dict(skipped) == {"no OCR text": 1, "no heading in the first lines": 1}
    assert [f.title for f in families] == ["INSOLVENT NATIONAL BANKS"]


def test_a_family_of_prose_pages_is_not_a_table_family():
    prose = [page("1905", n, HEAD, "INSOLVENT NATIONAL BANKS", figures=3) for n in (1, 2, 3)]
    table = [page("1905", 4, HEAD, "No. 5.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS", figures=60)]
    families, _ = survey_occ.group([*prose, *table])
    assert {f.title: f.is_table for f in families} == {
        "INSOLVENT NATIONAL BANKS": False,
        "LAWFUL MONEY RESERVE OF THE NATIONAL BANKS": True,
    }


def test_statements_of_condition_and_tables_with_totals_are_flagged_from_the_ocr_counts():
    pages = [
        # titled so, with a total on every page
        *(page("1905", n, HEAD, "No. 1.—PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES", totals=1) for n in (1, 2)),
        # not titled so, but half the pages carry a Resources or Liabilities heading and none a total
        page("1905", 3, HEAD, "No. 2.—SUMMARY OF REPORTS OF NATIONAL BANKS", res=True),
        page("1905", 4, HEAD, "No. 2.—SUMMARY OF REPORTS OF NATIONAL BANKS", lib=True),
        page("1905", 5, HEAD, "No. 2.—SUMMARY OF REPORTS OF NATIONAL BANKS"),
        # a totals table that is no statement of condition
        page("1905", 6, HEAD, "No. 3.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS", totals=2),
        page("1905", 7, HEAD, "No. 4.—CAPITAL OF NATIONAL BANKS BY STATES"),
    ]
    flags = {f.title: (f.is_condition, f.has_totals) for f in survey_occ.group(pages)[0]}
    assert flags == {
        "PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES": (True, True),
        "SUMMARY OF REPORTS OF NATIONAL BANKS": (True, False),
        "LAWFUL MONEY RESERVE OF THE NATIONAL BANKS": (False, True),
        "CAPITAL OF NATIONAL BANKS BY STATES": (False, False),
    }


def test_totals_are_only_counted_on_table_pages():
    pages = [
        page("1905", 1, HEAD, "No. 1.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS", figures=50, totals=1),
        page("1905", 2, HEAD, "No. 1.—LAWFUL MONEY RESERVE OF THE NATIONAL BANKS", figures=2, totals=1),
    ]
    [family] = survey_occ.group(pages)[0]
    assert (len(family.table_pages), len(family.with_totals)) == (1, 1)


def manifest_of(pages: list[occ.PageEntry]) -> occ.Manifest:
    from archivist.ingest import fraser

    volumes = sorted({p.issue for p in pages})
    return occ.Manifest(
        renderer=fraser.Renderer(pypdfium2="x", pillow="x", dpi=200, jpeg_quality=90),
        issues=[occ.IssueEntry(issue=v, pages=sum(p.issue == v for p in pages)) for v in volumes],
        pages=pages,
    )


def test_only_table_families_found_in_two_years_are_listed_and_a_years_two_volumes_count_once(monkeypatch):
    monkeypatch.setattr(occ, "VOLUMES", {"1905": 1, "1910": 2, "1915-v1": 3, "1915-v2": 4})
    monkeypatch.setattr(occ, "DEVELOPMENT", ["1905"])
    monkeypatch.setattr(occ, "HELD_OUT", ["1910", "1915"])
    same = "No. 1.—PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS"
    pages = [
        page("1905", 1, HEAD, same, totals=1),
        page("1910", 1, HEAD, same, totals=1),
        page("1915-v1", 1, HEAD, same, totals=1),
        page("1915-v2", 1, HEAD, same, totals=1),
        page("1915-v1", 2, HEAD, "No. 2.—ONLY IN THE ONE YEAR TWO VOLUMES"),
        page("1915-v2", 2, HEAD, "No. 2.—ONLY IN THE ONE YEAR TWO VOLUMES"),  # two volumes, one year
        page("1905", 2, HEAD, "No. 3.—PROSE ONLY IN ONE VOLUME", figures=1),
    ]
    text = survey_occ.render(manifest_of(pages))
    assert "## Statements of condition (resources and liabilities), found in 2+ years (1)" in text
    assert "| 1 | PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS | CT | 1 | 2 | 4 | 4 | 0 | 0 | 1905, 1910, 1915 |" in text
    assert "## Tables with printed totals, found in 2+ years (1)" in text
    assert "## All recurring table families (1)" in text
    assert "ONLY IN THE ONE YEAR" not in text.split("## All recurring")[1].split("## Volumes")[0]
    assert "| development | 1905 | 1 |" in text and "| held-out | 1910, 1915 | 3 |" in text


def test_a_long_title_is_cut_in_the_tables_only():
    long = "No. 1.—" + "PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES OF NATIONAL BANKS " * 4
    pages = [page(v, 1, HEAD, long.strip()) for v in ("1905", "1910")]
    text = survey_occ.render(manifest_of(pages))
    row = next(line for line in text.splitlines() if line.startswith("| 1 |"))
    assert row.split(" | ")[1].endswith("…") and len(row.split(" | ")[1]) <= survey_occ.TITLE_SHOWN + 1


def test_the_committed_survey_is_what_the_committed_manifest_gives():
    manifest = occ.Manifest.model_validate_json((REPO / "data/real_occ/manifest.json").read_text())
    committed = (REPO / "results/real_occ/survey.md").read_text()
    assert committed == survey_occ.render(manifest)
    assert all(line == line.rstrip() for line in committed.splitlines())
    assert "## Statements of condition (resources and liabilities)" in committed
    assert "## Tables with printed totals" in committed
