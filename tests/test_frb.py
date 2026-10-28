import hashlib
import io
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_fraser import image_pdf, text_pdf
from test_survey_modern import IMAGE, pdf_bytes, words

from archivist.ingest import frb, fraser, occ

REAL = Path(__file__).resolve().parents[1] / "data" / "real_frb"
TREASURY = Path(__file__).resolve().parents[1] / "data" / "real"
POINTER = "For more information on rights relating to this item, please see: "
NOC_US = fraser.Rights(
    statement=fraser.RIGHTS_STATEMENT, uri=fraser.RIGHTS_URI, checked=date(2026, 10, 28)
)
AGENCY = frb.AgencyBasis(
    basis=frb.AGENCY_BASIS, citations=frb.AGENCY_CITATIONS, checked=date(2026, 10, 28)
)


@pytest.fixture(autouse=True)
def _not_stopped():
    fraser._STOP.clear()
    yield
    fraser._STOP.clear()


def title_page(rights: str | None = None) -> str:
    """What FRASER's title page for title 62 shows: the NoC-US statement, or `rights` in its place."""
    field = rights or (
        '<span>RIGHTS:</span> <a href="http://rightsstatements.org/vocab/NoC-US/1.0/">'
        "No Copyright - United States (NoC-US)</a>"
    )
    return (
        f"<html><head><title>{frb.TITLE_NAME} | Title | FRASER | St. Louis Fed</title></head><body>"
        f"<h1>{frb.TITLE_NAME}</h1><p>DATE: 1914-2006</p>{field}"
        '<a href="/metadata.php?type=title&id=62&json=1">Metadata (JSON)</a></body></html>'
    )


def pdf_address(issue: str) -> str:
    year, month = issue.split("-")
    return f"https://fraser.stlouisfed.org/docs/publications/FRB/{year[:3]}0s/frb_{month}{year}.pdf"


def item_meta(issue: str, access: str | None = None) -> dict:
    """The parts of an item's metadata record that the ingest reads."""
    return {
        "recordInfo": {"recordIdentifier": [frb.ITEMS[issue]]},
        "relatedItem": [{"@type": "parent", "recordInfo": {"recordIdentifier": ["62"]}}],
        "originInfo": {"sortDate": f"{issue}-01"},
        "titleInfo": [{"title": f"June {issue[:4]}", "subTitle": "", "titlePartNumber": ""}],
        "location": {"pdfUrl": [pdf_address(issue)]},
        "accessCondition": POINTER + frb.item_url(issue) if access is None else access,
    }


# --- what FRASER is told about us ---------------------------------------------------------------


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_every_request_is_sent_with_the_one_public_user_agent_and_nothing_else_about_us(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(request)
        url = request.full_url
        body = title_page() if url == frb.TITLE_URL else json.dumps(item_meta("1980-06"))
        return FakeResponse(body.encode())

    monkeypatch.setattr(fraser.urllib.request, "urlopen", fake_urlopen)
    frb.check_rights()
    frb.read_item("1980-06", lambda line: None)
    assert [r.full_url for r in sent] == [frb.TITLE_URL, frb.metadata_url("1980-06")]
    for request in sent:
        assert request.header_items() == [("User-agent", fraser.USER_AGENT)]


def test_frb_makes_no_request_of_its_own():
    source = Path(frb.__file__).read_text()
    assert "urllib" not in source and "http.client" not in source  # only fraser._open sends anything


# --- the rights gate ----------------------------------------------------------------------------


def test_check_rights_takes_the_title_pages_statement_and_records_the_day_it_was_read():
    rights = frb.check_rights(lambda url: title_page())
    assert isinstance(rights, fraser.Rights) and fraser.check_rights_record(rights) == []
    assert abs((rights.checked - datetime.now(UTC).date()).days) <= 1


@pytest.mark.parametrize(
    "page",
    [
        title_page("<p>RIGHTS: In Copyright (InC)</p>"),
        title_page('<a href="http://rightsstatements.org/vocab/InC/1.0/">In Copyright</a>'),
        title_page("<p>RIGHTS: No Copyright - Other Known Legal Restrictions</p>"),
        title_page("<p>no rights field at all</p>"),
        "<html><title>Service unavailable</title><body>try again later</body></html>",  # not the page
        # the right statement on another title's page is not this title's
        title_page().replace(frb.TITLE_NAME, "Treasury Bulletin"),
        "",
    ],
)
def test_any_other_statement_or_a_page_that_is_not_the_title_page_stops_everything(page):
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        frb.check_rights(lambda url: page)


def test_the_gate_takes_frasers_statement_not_a_recorded_basis_in_its_place():
    sources = json.loads(_sources_text())
    sources["rights"] = {
        "fraser_shows": "no rights statement",
        "basis": "x" * 60,
        "citations": ["17 U.S.C. § 105"],
        "checked": "2026-10-28",
        "pages_checked": [frb.TITLE_URL],
    }
    with pytest.raises(ValidationError):
        frb.Sources.model_validate(sources)
    del sources["rights"]
    with pytest.raises(ValidationError):
        frb.Sources.model_validate(sources)


def test_the_second_basis_is_required_and_cites_the_law():
    sources = json.loads(_sources_text())
    del sources["agency_basis"]
    with pytest.raises(ValidationError):
        frb.Sources.model_validate(sources)
    for damage in ({"basis": "too short"}, {"citations": []}, {"citations": [" "]}, {"extra": 1}):
        with pytest.raises(ValidationError):
            frb.AgencyBasis.model_validate({**AGENCY.model_dump(mode="json"), **damage})
    assert "independent agency of the US Government" in AGENCY.basis
    assert "17 U.S.C. § 105" in AGENCY.citations and "no page, metadata record" in AGENCY.basis


def _sources_text() -> str:
    return (REAL / "sources.json").read_text()


@pytest.mark.parametrize(
    "access",
    [
        "",
        POINTER + "https://fraser.stlouisfed.org/title/federal-reserve-bulletin-62/june-1980-20466",
        POINTER + "/title/federal-reserve-bulletin-62/june-1980-20466",
        fraser.RIGHTS_URI,
        "No Copyright - United States",
        "no copyright - united states (NoC-US)",
    ],
)
def test_an_items_rights_text_that_leaves_the_download_open(access):
    assert frb.rights_problem(access) is None


@pytest.mark.parametrize(
    "access",
    [
        "http://rightsstatements.org/vocab/InC/1.0/",
        "In Copyright",
        "No Copyright - Other Known Legal Restrictions",
        "Restricted: licence required",
        POINTER,  # a pointer to nowhere is not the pointer
    ],
)
def test_any_other_rights_text_on_an_item_is_a_reason_to_stop(access):
    assert frb.rights_problem(access)


# --- the issues and the split --------------------------------------------------------------------


def test_the_issues_are_the_june_issues_1980_to_2003_and_june_2004_and_2005_are_not_among_them():
    assert list(frb.ITEMS) == [f"{y}-06" for y in range(1980, 2004)]
    assert len(set(frb.ITEMS.values())) == 24  # no two issues are the same FRASER item
    assert frb.GATED == ["2001-06", "2002-06", "2003-06"]
    core = [i for i in frb.ITEMS if i not in frb.GATED]
    assert len(core) == 21 and core[0] == "1980-06" and core[-1] == "2000-06"
    assert list(frb.NOT_ISSUED) == ["2004-06", "2005-06"]
    assert all("quarterly" in why for why in frb.NOT_ISSUED.values())


def test_the_split_is_the_one_that_was_fixed():
    split = frb.current_split(list(frb.ITEMS))
    assert split.development == ["1980-06", "1990-06", "2000-06"]
    assert split.held_out == [i for i in frb.ITEMS if i not in split.development]
    assert len(split.held_out) == 21
    assert {i: split.side(i) for i in ("1980-06", "1985-06", "1990-06", "2000-06", "2001-06")} == {
        "1980-06": "development",
        "1985-06": "held_out",
        "1990-06": "development",
        "2000-06": "development",
        "2001-06": "held_out",
    }


def test_an_issue_the_scan_check_skipped_is_in_neither_side_of_the_split():
    ingested = [i for i in frb.ITEMS if i != "2002-06"]
    split = frb.current_split(ingested)
    assert "2002-06" not in [*split.development, *split.held_out]
    assert frb.check_split(split, ingested) == []


def test_a_split_that_misses_repeats_or_invents_an_issue_is_refused():
    ingested = list(frb.ITEMS)
    split = frb.current_split(ingested)
    with pytest.raises(ValueError, match="more than once"):
        frb.Split(development=[*split.development, "1985-06"], held_out=split.held_out, note="")
    short = split.model_copy(update={"held_out": split.held_out[1:]})
    assert any("missing ['1981-06']" in p for p in frb.check_split(short, ingested))
    extra = split.model_copy(update={"held_out": [*split.held_out, "2004-06"]})
    assert any("unknown ['2004-06']" in p for p in frb.check_split(extra, ingested))
    swapped = frb.Split(development=["1981-06"], held_out=["1980-06", *split.held_out[1:]], note="")
    assert any("differs from the split fixed" in p for p in frb.check_split(swapped, ingested))


def test_the_addresses_of_an_item_follow_from_its_id():
    assert frb.item_url("1980-06") == f"{frb.TITLE_URL}/june-1980-20466"
    assert frb.metadata_url("1980-06") == "https://fraser.stlouisfed.org/metadata.php?type=item&id=20466&json=1"
    assert frb.pdf_name("1980-06") == "1980_06_frb.pdf"


# --- reading an item's metadata --------------------------------------------------------------


@pytest.mark.parametrize("issue", list(frb.ITEMS))
def test_a_matching_item_gives_its_pdf_address_and_what_it_says_about_rights(issue):
    meta = item_meta(issue)
    assert frb._item_record(issue, meta) == (pdf_address(issue), meta["accessCondition"])


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda m: m["originInfo"].update(sortDate="1980-07-01"), "date"),
        (lambda m: m["originInfo"].update(sortDate="1981-06-01"), "date"),
        (lambda m: m["recordInfo"].update(recordIdentifier=[20467]), "item"),
        (lambda m: m["titleInfo"][0].update(title="July 1980"), "name"),
        (lambda m: m["relatedItem"][0]["recordInfo"].update(recordIdentifier=["407"]), "title"),
        (lambda m: m["location"].update(pdfUrl=["http://elsewhere.example/a.pdf"]), "pdfUrl"),
        (lambda m: m["location"].update(pdfUrl=["https://fraser.stlouisfed.org/docs/a.html"]), "pdfUrl"),
        (lambda m: m["location"].update(pdfUrl=[]), "pdfUrl"),
        (lambda m: m.pop("location"), "unexpected metadata"),
        (lambda m: m.pop("originInfo"), "unexpected metadata"),
    ],
)
def test_an_item_that_is_not_the_issue_we_think_it_is_is_refused(change, match):
    meta = item_meta("1980-06")
    change(meta)
    with pytest.raises(fraser.DownloadError, match=match):
        frb._item_record("1980-06", meta)


@pytest.mark.parametrize(
    "access",
    [
        "http://rightsstatements.org/vocab/InC/1.0/",
        "In Copyright",
        "http://rightsstatements.org/vocab/NoC-OKLR/1.0/",
    ],
)
def test_an_item_that_shows_another_rights_statement_stops_everything(access):
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        frb._item_record("1980-06", item_meta("1980-06", access))


def test_an_item_that_shows_no_rights_text_or_frasers_own_is_not_a_reason_to_stop():
    meta = item_meta("1980-06", "")
    meta.pop("accessCondition")
    assert frb._item_record("1980-06", meta)[1] == ""
    assert frb._item_record("1980-06", item_meta("1980-06", fraser.RIGHTS_URI))[1] == fraser.RIGHTS_URI


def test_metadata_that_is_not_json_is_a_failed_download_not_a_crash(monkeypatch):
    monkeypatch.setattr(fraser, "_pause", lambda seconds: None)
    with pytest.raises(fraser.DownloadError, match="not JSON"):
        frb.read_item("1980-06", lambda line: None, lambda url: "<html>busy</html>")
    with pytest.raises(fraser.DownloadError, match="not a JSON object"):
        frb.read_item("1980-06", lambda line: None, lambda url: "[1, 2]")


# --- the scan check ---------------------------------------------------------------------------


def layers_of(tmp_path: Path, content: bytes) -> str:
    path = tmp_path / "p.pdf"
    path.write_bytes(pdf_bytes(content))
    return frb.pdf_layers(path)


def test_a_scan_with_an_ocr_layer_passes_whether_the_text_is_invisible_or_under_the_image(tmp_path):
    assert layers_of(tmp_path, IMAGE + words(3)) == frb.OCR
    assert layers_of(tmp_path, words(0) + b" " + IMAGE) == frb.OCR


def test_a_scan_with_next_to_no_text_passes_as_a_cover_a_photograph_or_a_blank_page(tmp_path):
    assert layers_of(tmp_path, IMAGE) == frb.THIN
    assert layers_of(tmp_path, IMAGE + words(0, frb.THIN_MAX_TEXT_OBJECTS)) == frb.THIN


def test_a_scan_with_a_lot_of_visible_text_on_it_does_not_pass(tmp_path):
    assert layers_of(tmp_path, IMAGE + words(0, frb.THIN_MAX_TEXT_OBJECTS + 1)) == frb.TEXT


def test_real_text_and_a_page_no_image_covers_do_not_pass(tmp_path):
    assert layers_of(tmp_path, words(0)) == frb.TEXT
    assert layers_of(tmp_path, b"") == frb.OTHER
    assert {frb.TEXT, frb.OTHER} & frb.PASSING == set()


def test_pdf_layers_gives_one_letter_for_each_page(tmp_path):
    path = image_pdf(tmp_path / "scan.pdf", pages=4)
    assert frb.pdf_layers(path) == frb.THIN * 4


def test_only_an_issue_after_2000_is_skipped_for_a_page_that_fails():
    assert frb.outcome_of("2001-06", "ooootooo") == "ingested"
    assert frb.outcome_of("2001-06", "oooxooo") == "skipped"
    assert frb.outcome_of("2003-06", "ooozooo") == "skipped"
    assert frb.outcome_of("1985-06", "oooxzoo") == "ingested"  # the 21 fixed issues gate nothing


def test_a_scan_entry_has_one_letter_for_each_page_and_lists_the_failing_ones():
    entry = frb.ScanEntry(issue="2001-06", pages=5, layers="ootxz", gate="required", outcome="skipped")
    assert entry.failing == [4, 5]
    assert entry.counts() == {
        "scan with an OCR layer": 2,
        "scan with next to no text": 1,
        "real text": 1,
        "other": 1,
    }
    with pytest.raises(ValidationError, match="letters"):
        frb.ScanEntry(issue="2001-06", pages=6, layers="ootxz", gate="required", outcome="skipped")
    with pytest.raises(ValidationError):
        frb.ScanEntry(issue="2001-06", pages=2, layers="ob", gate="required", outcome="ingested")


# --- the counts the survey reads from the OCR text -----------------------------------------------


def test_ocr_counts_find_numbered_captions_and_the_total_lines_after_each():
    text = "\n".join(
        [
            "A12 Domestic Financial Statistics ☐ June 2000",
            "1.26 COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities1",
            "Billions of dollars",
            "15 Cash assets 50.2",
            "16 Total assets6 5,258.7 5,395.2",
            "17 Total liabilities 4,000.1",
            "1.27 LARGE COMMERCIAL BANKS Continued",
            "1 Total 12 13 14",
            "The total of the loans",  # does not begin with Total
            "Subtotal 5",
        ]
    )
    counts = frb.ocr_counts(text)
    assert counts["lines"] == 10
    assert [(t["number"], t["total_lines"]) for t in counts["tables"]] == [("1.26", 2), ("1.27", 1)]
    assert counts["tables"][0]["title"] == "COMMERCIAL BANKS IN THE UNITED STATES Assets and Liabilities1"
    assert counts["tables"][1]["title"] == "LARGE COMMERCIAL BANKS"  # "Continued" is not part of it
    assert (counts["total_lines"], counts["leading_total_lines"]) == (3, 0)


def test_a_total_before_the_pages_first_caption_belongs_to_the_table_it_continues():
    counts = frb.ocr_counts("2 Total vault cash 44,742\n3 Totals 1\n1.12 RESERVES AND BORROWINGS\n1 Total 5")
    assert (counts["total_lines"], counts["leading_total_lines"]) == (3, 2)
    assert [(t["number"], t["total_lines"]) for t in counts["tables"]] == [("1.12", 1)]


def test_a_line_that_only_mentions_a_number_or_is_not_in_capitals_is_not_a_caption():
    text = "See table 1.12 for the figures\n1.5 per cent\n1.26 not in capitals\n12.34 CAPITALS BUT TWO DIGITS"
    assert frb.ocr_counts(text)["tables"] == []


def test_a_page_without_text_counts_as_nothing():
    assert frb.ocr_counts("") == {
        "lines": 0,
        "figure_lines": 0,
        "total_lines": 0,
        "leading_total_lines": 0,
        "tables": [],
    }


def entry(**change):
    base = {
        "issue": "1980-06", "page": 1, "sha256": "0" * 64, "size_bytes": 1, "width": 1, "height": 1,
        "title_hint": [], "lines": 0, "figure_lines": 0, "total_lines": 0, "leading_total_lines": 0,
        "tables": [],
    }  # fmt: skip
    return {**base, **change}


def test_a_page_entry_cannot_leave_out_the_counts_or_make_its_totals_not_add_up():
    frb.PageEntry.model_validate(entry())
    for name in ("lines", "figure_lines", "total_lines", "leading_total_lines", "tables"):
        bare = entry()
        del bare[name]
        with pytest.raises(ValidationError):
            frb.PageEntry.model_validate(bare)
    table = {"number": "1.12", "title": "T", "total_lines": 2}
    frb.PageEntry.model_validate(entry(total_lines=3, leading_total_lines=1, tables=[table]))
    with pytest.raises(ValidationError, match="do not add up"):
        frb.PageEntry.model_validate(entry(total_lines=2, leading_total_lines=1, tables=[table]))
    with pytest.raises(ValidationError):
        frb.PageEntry.model_validate(entry(tables=[{**table, "number": "12.3"}]))


def test_the_manifest_carries_the_hint_and_the_counts_read_from_the_pdfs_own_text(monkeypatch, tmp_path):
    monkeypatch.setattr(frb, "ITEMS", {"1980-06": 20466})
    root = tmp_path / "real_frb"
    (root / "pdf").mkdir(parents=True)
    lines = [
        "A12 Domestic Financial Statistics June 1980",
        "1.26 COMMERCIAL BANKS IN THE UNITED STATES Assets",
        "Billions of dollars",
        "15 Cash assets 1,200",
        "16 Total assets 5,258",
        "98,765",
        "1.27 OTHER",
        "1 Total 7",
    ]
    (root / "pdf" / frb.pdf_name("1980-06")).write_bytes(text_pdf(lines))
    frb.render_issue("1980-06", root, lambda line: None)
    [page] = frb.build_manifest(root, ["1980-06"]).pages
    assert page.title_hint == lines[:4]
    assert (page.lines, page.figure_lines, page.total_lines, page.leading_total_lines) == (8, 1, 2, 0)
    assert [(t.number, t.total_lines) for t in page.tables] == [("1.26", 1), ("1.27", 1)]


# --- the committed records ---------------------------------------------------------------------


def committed():
    return (
        frb.Sources.model_validate_json(_sources_text()),
        frb.ScanCheck.model_validate_json((REAL / "scan_check.json").read_text()),
        frb.Manifest.model_validate_json((REAL / "manifest.json").read_text()),
        frb.Split.model_validate_json((REAL / "split.json").read_text()),
    )


def test_sources_json_validates_and_names_every_issue_downloaded_once():
    sources, *_ = committed()
    assert frb.check_sources(sources) == []
    assert sources.title_url == frb.TITLE_URL
    assert [f.issue for f in sources.files] == list(frb.ITEMS)
    for record in sources.files:
        assert record.resolved_url.startswith("https://fraser.stlouisfed.org/")
        assert record.url.startswith(frb.PDF_PREFIX) and record.item_id == frb.ITEMS[record.issue]
        assert record.retrieved <= date.today()


def test_the_committed_rights_record_is_frasers_statement_with_the_agency_basis_beside_it():
    sources, *_ = committed()
    assert isinstance(sources.rights, fraser.Rights) and fraser.check_rights_record(sources.rights) == []
    assert sources.rights.statement == fraser.RIGHTS_STATEMENT and sources.rights.checked <= date.today()
    assert sources.agency_basis.citations == ["17 U.S.C. § 105"]
    assert "independent agency of the US Government" in sources.agency_basis.basis


def test_what_each_items_metadata_says_about_rights_is_recorded_and_none_names_another_statement():
    sources, *_ = committed()
    for record in sources.files:
        assert frb.rights_problem(record.access_condition) is None, record.issue
        assert record.access_condition.startswith(POINTER) or record.access_condition in (
            "",
            fraser.RIGHTS_URI,
        )


def test_the_scan_check_is_sound_and_says_why_june_2004_and_2005_are_missing():
    _, scan, *_ = committed()
    assert frb.check_scan(scan) == []
    assert scan.rule == frb.SCAN_RULE
    assert {n.issue: n.reason for n in scan.not_issued} == frb.NOT_ISSUED
    assert [e.issue for e in scan.issues] == list(frb.ITEMS)
    for e in scan.issues[:21]:  # the fixed issues are ingested, whatever their pages are
        assert e.gate == "reported" and e.outcome == "ingested"
    for e in scan.issues[21:]:
        assert e.gate == "required"
        assert (e.outcome == "ingested") == (e.failing == [])  # skipped exactly when a page failed


def test_the_manifest_validates_and_agrees_with_the_scan_check():
    sources, scan, manifest, _ = committed()
    assert frb.check_manifest(manifest, scan) == []
    assert (manifest.renderer.dpi, manifest.renderer.jpeg_quality) == (fraser.DPI, fraser.JPEG_QUALITY)
    assert [e.issue for e in manifest.issues] == frb.ingested_issues(scan)
    assert frb.ingested_issues(scan)[:21] == list(frb.ITEMS)[:21]
    for page in manifest.pages:
        assert len(page.title_hint) <= fraser.HINT_LINES
        assert all(0 < len(line) <= fraser.HINT_WIDTH for line in page.title_hint)
        assert page.figure_lines <= page.lines and page.total_lines <= page.lines
        assert bool(page.title_hint) == (page.lines > 0)  # the hint and the counts read the same text
        assert all(len(t.title) <= fraser.HINT_WIDTH for t in page.tables)
    assert sum(p.lines > 0 for p in manifest.pages) > 0.9 * len(manifest.pages)  # the OCR layer is there


def test_split_json_is_the_split_fixed_in_code_for_the_issues_ingested():
    _, scan, manifest, split = committed()
    ingested = frb.ingested_issues(scan)
    assert split == frb.current_split(ingested) and frb.check_split(split, ingested) == []
    assert split.development == ["1980-06", "1990-06", "2000-06"]
    assert sorted([*split.development, *split.held_out]) == sorted(e.issue for e in manifest.issues)
    skipped = [e.issue for e in scan.issues if e.outcome == "skipped"]
    assert not set(skipped) & {e.issue for e in manifest.issues}


def test_a_record_with_a_bad_hash_is_refused():
    good = json.loads(_sources_text())
    good["files"][0]["sha256"] = "not-a-hash"
    with pytest.raises(ValueError):
        frb.Sources.model_validate(good)


def test_check_sources_notices_a_wrong_item_a_missing_issue_or_a_rights_text_that_is_another_statement():
    sources, *_ = committed()
    first, *rest = sources.files
    wrong = first.model_copy(
        update={"item_id": 1, "url": "http://elsewhere.example/a.pdf", "access_condition": "In Copyright"}
    )
    problems = frb.check_sources(sources.model_copy(update={"files": [wrong, *rest]}))
    assert any("item is 1" in p for p in problems) and any("not a PDF under" in p for p in problems)
    assert any("In Copyright" in p for p in problems)
    problems = frb.check_sources(sources.model_copy(update={"files": rest}))
    assert problems == [f"sources.json has no record of {first.issue}"]


def test_check_scan_notices_an_outcome_that_does_not_follow_from_the_pages():
    _, scan, *_ = committed()
    last = scan.issues[-1]
    lie = last.model_copy(
        update={"layers": last.layers[:-1] + "x", "outcome": "ingested"}
    )
    problems = frb.check_scan(scan.model_copy(update={"issues": [*scan.issues[:-1], lie]}))
    assert problems == [f"{last.issue}: outcome ingested does not follow from its pages"]
    assert frb.check_scan(scan.model_copy(update={"issues": scan.issues[:-1]}))


# --- safe to interrupt ------------------------------------------------------------------------


@pytest.fixture
def four_issues(monkeypatch, tmp_path):
    """The ingest shrunk to four issues, FRASER replaced by local pages and PDFs.

    1980-06 and 1990-06 are fixed issues (development), 2001-06 is a scan with an OCR layer and
    2002-06 has real text on its page, so the scan check ingests the one and skips the other.
    """
    issues = {"1980-06": 20466, "1990-06": 20816, "2001-06": 20949, "2002-06": 20961}
    monkeypatch.setattr(frb, "ITEMS", issues)
    monkeypatch.setattr(frb, "GATED", ["2001-06", "2002-06"])
    monkeypatch.setattr(frb, "DEVELOPMENT", ["1980-06", "1990-06"])
    monkeypatch.setattr(fraser, "POLITE_PAUSE", 0)
    scan = image_pdf(tmp_path / "scan.pdf").read_bytes()
    bodies = {
        pdf_address("1980-06"): scan,
        pdf_address("1990-06"): scan,
        pdf_address("2001-06"): pdf_bytes(IMAGE + words(3)),
        pdf_address("2002-06"): text_pdf(["TABLE 1.- REAL TEXT, NOT A SCAN"]),
    }
    calls: list[str] = []

    def fake_fetch(url: str, part: Path):
        calls.append(url)
        data = bodies[url]
        part.write_bytes(data)
        return url.replace("/docs/", "/files/docs/"), len(data), hashlib.sha256(data).hexdigest()

    pages = {frb.TITLE_URL: title_page()}
    pages |= {frb.metadata_url(i): json.dumps(item_meta(i)) for i in issues}
    monkeypatch.setattr(fraser, "_fetch_pdf", fake_fetch)
    monkeypatch.setattr(fraser, "_fetch_text", lambda url: pages[url])
    return tmp_path / "real_frb", calls, pages


def leftovers(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.part")]


def quiet(line: str) -> None:
    pass


def test_every_issue_is_checked_and_one_with_a_page_of_real_text_is_skipped_and_said_so(four_issues):
    root, calls, _ = four_issues
    lines: list[str] = []
    assert frb.ingest(root, log=lines.append) == 0
    assert any("2002-06: SKIPPED" in line and "failing pages: [1]" in line for line in lines)
    scan = frb.ScanCheck.model_validate_json((root / "scan_check.json").read_text())
    assert {e.issue: (e.layers, e.outcome) for e in scan.issues} == {
        "1980-06": ("ttt", "ingested"),
        "1990-06": ("ttt", "ingested"),
        "2001-06": ("o", "ingested"),
        "2002-06": ("x", "skipped"),
    }
    assert [e.issue for e in scan.not_issued] == ["2004-06", "2005-06"]
    assert not (root / "pages" / "2002-06").exists()  # skipped: never rendered
    manifest = frb.Manifest.model_validate_json((root / "manifest.json").read_text())
    assert [e.issue for e in manifest.issues] == ["1980-06", "1990-06", "2001-06"]
    split = frb.Split.model_validate_json((root / "split.json").read_text())
    assert (split.development, split.held_out) == (["1980-06", "1990-06"], ["2001-06"])
    sources = frb.Sources.model_validate_json((root / "sources.json").read_text())
    assert [f.issue for f in sources.files] == list(frb.ITEMS)  # the skipped PDF was downloaded: recorded
    assert (root / "pdf" / "2002_06_frb.pdf").is_file()
    assert len(calls) == 4 and leftovers(root) == []
    assert frb.verify(root, log=quiet) == 0


def test_a_rerun_of_a_finished_tree_needs_no_network_and_does_not_fetch_a_skipped_issue_again(
    four_issues, monkeypatch
):
    root, calls, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    before = (root / "scan_check.json").read_bytes(), (root / "manifest.json").read_bytes()
    monkeypatch.setattr(fraser, "_fetch_text", lambda url: pytest.fail("network used"))
    monkeypatch.setattr(fraser, "_fetch_pdf", lambda url, part: pytest.fail("network used"))
    assert frb.ingest(root, log=quiet) == 0
    assert len(calls) == 4
    assert (root / "scan_check.json").read_bytes() == before[0]
    assert (root / "manifest.json").read_bytes() == before[1]


def test_stopping_mid_run_leaves_whole_issues_and_no_manifest_and_a_rerun_finishes(four_issues):
    root, calls, _ = four_issues

    def stop_after_the_first_issue(line: str) -> None:
        if "1980-06: 3 pages rendered" in line:
            fraser._STOP.set()

    assert frb.ingest(root, log=stop_after_the_first_issue) == 130
    assert not (root / "manifest.json").exists() and not (root / "split.json").exists()
    assert (root / "pdf" / "1980_06_frb.pdf").is_file()
    assert not (root / "pdf" / "1990_06_frb.pdf").exists()
    assert len(list((root / "pages" / "1980-06").glob("p*.jpg"))) == 3
    assert [f.issue for f in frb.Sources.model_validate_json((root / "sources.json").read_text()).files] == [
        "1980-06"
    ]
    assert [e.issue for e in frb.ScanCheck.model_validate_json((root / "scan_check.json").read_text()).issues] == [
        "1980-06"
    ]
    assert leftovers(root) == [] and len(calls) == 1

    fraser._STOP.clear()
    assert frb.ingest(root, log=quiet) == 0
    assert len(calls) == 4  # the first issue was not fetched again
    assert frb.verify(root, log=quiet) == 0


def test_the_rights_record_is_written_with_the_first_pdf_and_each_items_text_is_kept(four_issues):
    root, _, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    sources = frb.Sources.model_validate_json((root / "sources.json").read_text())
    assert isinstance(sources.rights, fraser.Rights) and sources.agency_basis.citations == frb.AGENCY_CITATIONS
    assert frb.check_sources(sources) == []
    for record in sources.files:  # the address and the rights text came from the item's metadata
        meta = item_meta(record.issue)
        assert record.url == meta["location"]["pdfUrl"][0]
        assert record.access_condition == meta["accessCondition"]
        assert record.metadata_url == frb.metadata_url(record.issue)


def test_another_statement_on_the_title_page_stops_before_anything_is_downloaded(four_issues):
    root, calls, pages = four_issues
    pages[frb.TITLE_URL] = title_page("<p>RIGHTS: In Copyright (InC)</p>")
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        frb.ingest(root, log=quiet)
    assert calls == [] and not list(root.rglob("*.pdf")) and not (root / "sources.json").exists()


@pytest.mark.parametrize("which", ["1980-06", "2002-06"])
def test_an_item_with_another_statement_stops_the_run_before_any_download_wherever_it_is(four_issues, which):
    root, calls, pages = four_issues
    pages[frb.metadata_url(which)] = json.dumps(item_meta(which, "http://rightsstatements.org/vocab/InC/1.0/"))
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        frb.ingest(root, log=quiet)
    assert calls == [] and not list(root.rglob("*.pdf")) and not (root / "sources.json").exists()


def test_a_wrong_item_is_a_failed_issue_and_the_others_still_finish(four_issues):
    root, _, pages = four_issues
    meta = item_meta("1980-06")
    meta["titleInfo"][0]["title"] = "July 1980"
    pages[frb.metadata_url("1980-06")] = json.dumps(meta)
    lines: list[str] = []
    assert frb.ingest(root, log=lines.append) == 1
    assert any("1980-06: FAILED" in line and "not the June 1980 issue" in line for line in lines)
    assert (root / "pdf" / "1990_06_frb.pdf").is_file() and not (root / "pdf" / "1980_06_frb.pdf").exists()
    assert not (root / "manifest.json").exists()


def test_a_stop_during_a_download_removes_the_temp_file_and_records_nothing(four_issues, monkeypatch):
    root, _, _ = four_issues

    def interrupted(url: str, part: Path):
        part.write_bytes(b"%PDF-1.4 only the first few bytes")
        fraser._STOP.set()
        fraser._check_stop()

    monkeypatch.setattr(fraser, "_fetch_pdf", interrupted)
    assert frb.ingest(root, log=quiet) == 130
    assert leftovers(root) == [] and not list((root / "pdf").glob("*.pdf"))
    assert not (root / "sources.json").exists() and not (root / "scan_check.json").exists()


@pytest.mark.parametrize("damage", ["short", "not a pdf", "empty"])
def test_a_download_that_is_short_or_not_a_pdf_never_reaches_its_final_name(four_issues, monkeypatch, damage):
    root, _, _ = four_issues
    good = (root.parent / "scan.pdf").read_bytes()
    body = {"short": good[: len(good) // 2], "not a pdf": b"<html>busy</html>" * 20, "empty": b""}[damage]

    def damaged(url: str, part: Path):
        part.write_bytes(body)
        if damage == "short":  # the server announced the whole file
            raise fraser.DownloadError(f"got {len(body)} bytes, server announced {len(good)}")
        return url, len(body), hashlib.sha256(body).hexdigest()

    monkeypatch.setattr(fraser, "_fetch_pdf", damaged)
    monkeypatch.setattr(fraser, "_pause", lambda seconds: None)
    sources = frb.Sources(
        title="t", publisher="p", title_url=frb.TITLE_URL, rights=NOC_US, agency_basis=AGENCY, files=[]
    )
    with pytest.raises(fraser.DownloadError):
        frb.download_issue("1980-06", root, sources, pdf_address("1980-06"), "", quiet)
    assert leftovers(root) == [] and not list((root / "pdf").glob("*.pdf"))
    assert not (root / "sources.json").exists()


def test_a_pdf_never_exists_without_its_record(four_issues, monkeypatch):
    root, _, _ = four_issues
    real_replace = fraser.os.replace

    def replace(src, dst):
        if str(dst).endswith(".pdf"):
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(fraser.os, "replace", replace)
    assert frb.ingest(root, log=quiet) == 1  # every issue failed at the rename
    assert not list((root / "pdf").glob("*.pdf"))
    assert [f.issue for f in frb.Sources.model_validate_json((root / "sources.json").read_text()).files]


def test_verify_notices_a_page_that_no_longer_matches_the_manifest(four_issues):
    root, _, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    shutil.copy(root / "pages" / "1980-06" / "p001.jpg", root / "pages" / "1980-06" / "p002.jpg")
    lines: list[str] = []
    assert frb.verify(root, log=lines.append) == 1
    assert any("1980-06 p002" in line for line in lines)


def test_verify_notices_a_split_that_is_valid_but_not_the_one_fixed(four_issues):
    root, _, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    swapped = frb.Split(development=["1990-06"], held_out=["1980-06", "2001-06"], note="edited")
    fraser._write_record(root / "split.json", swapped)
    lines: list[str] = []
    assert frb.verify(root, log=lines.append) == 1
    assert any("split.json differs" in line for line in lines)


def test_verify_notices_a_pdf_that_no_longer_matches_its_record(four_issues):
    root, _, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    pdf = root / "pdf" / "1990_06_frb.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"\n%tampered")
    lines: list[str] = []
    assert frb.verify(root, log=lines.append) == 1
    assert any("1990-06: PDF does not match sources.json" in line for line in lines)


def test_verify_notices_an_issue_ingested_although_its_pages_failed_the_scan_check(four_issues):
    root, _, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    scan = frb.ScanCheck.model_validate_json((root / "scan_check.json").read_text())
    [skipped] = [e for e in scan.issues if e.outcome == "skipped"]
    lie = skipped.model_copy(update={"outcome": "ingested"})
    fraser._write_record(root / "scan_check.json", frb._with_entry(scan, lie))
    lines: list[str] = []
    assert frb.verify(root, log=lines.append) == 1
    assert any("2002-06: outcome ingested does not follow" in line for line in lines)


def test_verify_notices_an_unreadable_or_missing_record(four_issues):
    root, _, _ = four_issues
    assert frb.ingest(root, log=quiet) == 0
    (root / "scan_check.json").unlink()
    lines: list[str] = []
    assert frb.verify(root, log=lines.append) == 1 and "cannot read the records" in lines[0]


def test_a_second_ingest_cannot_start_while_one_is_running(tmp_path):
    with fraser._lock(tmp_path), pytest.raises(SystemExit, match="already running"):
        fraser._lock(tmp_path).__enter__()


# --- the command line ----------------------------------------------------------------------------


def test_verify_checks_every_source_including_this_one_and_reports_the_worst(monkeypatch):
    seen = []
    monkeypatch.setattr(fraser, "verify", lambda root: seen.append(("treasury", root)) or 0)
    monkeypatch.setattr(occ, "verify", lambda root: seen.append(("occ", root)) or 0)
    monkeypatch.setattr(frb, "verify", lambda root: seen.append(("frb", root)) or 1)
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify"])
    assert stop.value.code == 1
    assert seen == [("treasury", fraser.DEFAULT_ROOT), ("occ", occ.DEFAULT_ROOT), ("frb", frb.DEFAULT_ROOT)]

    seen.clear()
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify", "--source", "frb"])
    assert stop.value.code == 1 and seen == [("frb", frb.DEFAULT_ROOT)]


def test_a_source_and_root_can_be_named(four_issues, monkeypatch):
    root, _, _ = four_issues
    monkeypatch.setattr(fraser.signal, "signal", lambda signum, handler: None)  # keep pytest's own
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--source", "frb", "--root", str(root)])
    assert stop.value.code == 0
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify", "--source", "frb", "--root", str(root)])
    assert stop.value.code == 0


def test_a_rights_stop_exits_2_and_a_stop_signal_exits_130(four_issues, monkeypatch):
    root, _, pages = four_issues
    monkeypatch.setattr(fraser.signal, "signal", lambda signum, handler: None)
    pages[frb.TITLE_URL] = title_page("<p>RIGHTS: In Copyright (InC)</p>")
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--source", "frb", "--root", str(root)])
    assert stop.value.code == 2
    monkeypatch.setattr(frb, "ingest", lambda root, log: 130)
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--source", "frb", "--root", str(root)])
    assert stop.value.code == 130
