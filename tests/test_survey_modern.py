import io
import json
import urllib.error
from pathlib import Path

import pytest

from archivist.ingest import fraser
from archivist.ingest import survey_modern as sm

REPO = Path(__file__).resolve().parents[1]


# --- fakes -----------------------------------------------------------------------------------


class Response:
    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None, status: int = 200):
        self._body = io.BytesIO(body)
        self.headers = headers or {}
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        pass


class Server:
    """An opener that answers from a table and remembers every request."""

    def __init__(self, answers: dict[str, Response | bytes | Exception] | None = None):
        self.answers = answers or {}
        self.requests: list = []

    def __call__(self, request):
        self.requests.append(request)
        answer = self.answers[request.full_url]
        if isinstance(answer, Exception):
            raise answer
        return Response(answer) if isinstance(answer, bytes) else answer


def web(tmp_path: Path, server: Server) -> sm.Web:
    return sm.Web(tmp_path / "work", opener=server, pause=0)


def pdf_bytes(content: bytes) -> bytes:
    """A one-page PDF with this content stream."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


IMAGE = b"q 612 0 0 792 0 0 cm BI /W 2 /H 2 /CS /G /BPC 8 ID \x80\x80\x80\x80 EI Q "


def words(mode: int, n: int = 3) -> bytes:
    lines = b" ".join(b"(Total %d) Tj T*" % i for i in range(n))
    return b"BT %d Tr /F1 12 Tf 72 720 Td 14 TL " % mode + lines + b" ET"


# --- FRASER's pages --------------------------------------------------------------------------

TITLE_PAGE = (
    '<p><span class="metadata-heading"><!--googleoff: snippet-->RIGHTS:<!--googleon: snippet--></span>\n'
    "\t<a href=http://rightsstatements.org/vocab/NoC-US/1.0/>\n\tNo Copyright - United States (NoC-US)\n"
    "\t</a></p> <p>CLASSIFICATION: sudocs: FR 1.3</p>"
)


def test_rights_field_reads_the_statement_and_stops_at_the_next_label():
    assert sm.rights_field(TITLE_PAGE) == "No Copyright - United States (NoC-US)"


def test_rights_field_is_none_when_the_page_shows_none():
    page = "<p>PUBLISHER: Federal Deposit Insurance Corporation</p><p>IDENTIFIER: oclc: 1296007</p>"
    assert sm.rights_field(page) is None


def test_item_links_give_each_item_once_with_the_year_its_address_names():
    page = (
        '<a href="/title/federal-reserve-bulletin-62/january-1980-20461">a</a>'
        '<a href="https://fraser.stlouisfed.org/title/federal-reserve-bulletin-62/june-1985-20526">b</a>'
        '<a href="/title/federal-reserve-bulletin-62/january-1980-20461">again</a>'
        '<a href="/title/federal-reserve-bulletin-62/articles-compilation-pt-1-20984">c</a>'
        '<a href="/title/other-title-9/june-1985-1">not this title</a>'
    )
    assert sm.item_links(page, "federal-reserve-bulletin-62") == [
        (20461, 1980),
        (20526, 1985),
        (20984, None),
    ]


@pytest.mark.parametrize(
    "extent, pages",
    [("163 pages", 163), ("1,024 pages", 1024), ("1 page", 1), ("83 vol.", None), (None, None)],
)
def test_extent_pages(extent, pages):
    assert sm.extent_pages(extent) == pages


def item(ident=20461, date="1980-01-01", extent="163 pages", frequency="", **physical):
    return {
        "titleInfo": [{"title": "January 1980"}],
        "recordInfo": {"recordIdentifier": [ident]},
        "originInfo": {"sortDate": date, "frequency": frequency},
        "physicalDescription": {
            "extent": extent,
            "digitalOrigin": "reformatted digital",
            **physical,
        },
        "location": {"pdfUrl": ["https://fraser.stlouisfed.org/docs/publications/FRB/1980s/frb_011980.pdf"]},
    }


def test_item_edition_reads_year_month_pages_label_and_pdf():
    e = sm.item_edition("frb", item())
    assert (e.source, e.ident, e.label, e.first_year, e.month, e.pages) == (
        "frb", "20461", "January 1980", 1980, 1, 163,
    )
    assert e.origin == "reformatted digital" and e.pdf_url.endswith("frb_011980.pdf")


def test_an_annual_report_has_no_month():
    assert sm.item_edition("fdic", item(frequency="annual")).month is None


def test_fraser_editions_fetches_only_items_in_the_years(tmp_path):
    listing = (
        '<a href="/title/t-1/june-1979-1">x</a><a href="/title/t-1/june-1985-2">y</a>'
        '<a href="/title/t-1/june-1985-3">z</a><a href="/title/t-1/june-2001-4">w</a>'
    )
    server = Server(
        {
            "https://fraser.stlouisfed.org/title/t-1?browse=1980s": listing.encode(),
            sm.ITEM_METADATA.format(id=2): json.dumps(item(2, "1985-06-01")).encode(),
            sm.ITEM_METADATA.format(id=3): json.dumps(item(3, "1985-07-01")).encode(),
        }
    )
    editions = sm.fraser_editions(web(tmp_path, server), "frb", f"{sm.FRASER}/title/t-1", ("1980s",))
    assert [e.ident for e in editions] == ["2", "3"]
    assert len(server.requests) == 3  # the listing, and the two items in range


def test_one_a_year_takes_the_middle_item_of_each_year(tmp_path):
    listing = "".join(f'<a href="/title/t-1/m-1985-{i}">x</a>' for i in range(1, 6))
    server = Server(
        {
            "https://fraser.stlouisfed.org/title/t-1?browse=1980s": listing.encode(),
            sm.ITEM_METADATA.format(id=3): json.dumps(item(3, "1985-03-01")).encode(),
        }
    )
    editions = sm.fraser_editions(
        web(tmp_path, server), "frb", f"{sm.FRASER}/title/t-1", ("1980s",), range(1980, 1990), True
    )
    assert [e.ident for e in editions] == ["3"]


VOLUMES = (
    '<a href="/system/files/files/reports-statements/mts/vol-18-mts-oct85-sep86.pdf">PDF</a>'
    '<a href="/system/files/files/reports-statements/mts/vol-27-mts-oct97-sep98-hc.pdf">PDF</a>'
    '<a href="/system/files/files/reports-statements/mts/vol-18-mts-oct85-sep86.pdf">again</a>'
    '<a href="/system/files/files/reports-statements/mts/mts0198.pdf">a month</a>'
)


def test_fiscal_volumes_are_the_bound_volumes_oldest_first():
    volumes = sm.fiscal_volumes(VOLUMES)
    assert [(v.ident, v.first_year, v.last_year) for v in volumes] == [
        ("vol-18-mts-oct85-sep86", 1985, 1986),
        ("vol-27-mts-oct97-sep98-hc", 1997, 1998),
    ]
    assert volumes[0].pdf_url == sm.FISCAL + "/system/files/files/reports-statements/mts/vol-18-mts-oct85-sep86.pdf"


# --- the web ---------------------------------------------------------------------------------


def test_every_request_carries_the_project_user_agent_and_nothing_that_identifies_anyone(tmp_path):
    server = Server({"https://a.example/x": b"hello", "https://www.fdic.gov/f.pdf": Response(headers={"Content-Length": "9"})})
    w = web(tmp_path, server)
    w.text("https://a.example/x")
    w.size("https://www.fdic.gov/f.pdf")
    for request in server.requests:
        assert dict(request.header_items()) == {"User-agent": fraser.USER_AGENT}
    assert "@" not in fraser.USER_AGENT and "/Users/" not in fraser.USER_AGENT


def test_a_page_is_asked_for_once(tmp_path):
    server = Server({"https://a.example/x": b"hello"})
    w = web(tmp_path, server)
    assert w.text("https://a.example/x") == w.text("https://a.example/x") == "hello"
    assert len(server.requests) == 1
    assert sm.Web(tmp_path / "work", opener=Server(), pause=0).text("https://a.example/x") == "hello"


def test_size_is_a_head_request_and_never_reads_a_body(tmp_path):
    server = Server({"https://www.fdic.gov/f.pdf": Response(b"x" * 100, {"Content-Length": "12345"})})
    assert web(tmp_path, server).size("https://www.fdic.gov/f.pdf") == 12345
    assert server.requests[0].get_method() == "HEAD"


def test_size_asks_only_hosts_known_to_report_a_length(tmp_path):
    server = Server()
    with pytest.raises(sm.SizeUnknown):
        web(tmp_path, server).size("https://fraser.stlouisfed.org/docs/x.pdf")
    assert server.requests == []  # FRASER's HEAD says 0; it is not asked


@pytest.mark.parametrize("length", ["0", "", "abc"])
def test_a_missing_or_zero_length_is_unknown(tmp_path, length):
    server = Server({"https://www.fdic.gov/f.pdf": Response(headers={"Content-Length": length})})
    with pytest.raises(sm.SizeUnknown):
        web(tmp_path, server).size("https://www.fdic.gov/f.pdf")


def test_a_missing_file_is_an_unknown_size_not_a_crash(tmp_path):
    error = urllib.error.HTTPError("https://www.fdic.gov/f.pdf", 404, "Not Found", {}, None)
    with pytest.raises(sm.SizeUnknown, match="404"):
        web(tmp_path, Server({"https://www.fdic.gov/f.pdf": error})).size("https://www.fdic.gov/f.pdf")


def test_a_missing_file_is_not_asked_for_twice(tmp_path):
    error = urllib.error.HTTPError("https://www.fdic.gov/f.pdf", 404, "Not Found", {}, None)
    server = Server({"https://www.fdic.gov/f.pdf": error})
    w = web(tmp_path, server)
    for _ in range(2):
        with pytest.raises(sm.SizeUnknown):
            w.size("https://www.fdic.gov/f.pdf")
    assert len(server.requests) == 1


GOOD = pdf_bytes(IMAGE + words(3))


def test_download_keeps_a_whole_pdf_and_counts_it(tmp_path):
    server = Server({"https://a.example/1.pdf": Response(GOOD, {"Content-Length": str(len(GOOD))})})
    w = web(tmp_path, server)
    path = w.download("frb", "https://a.example/1.pdf", "1.pdf")
    assert path.read_bytes() == GOOD and path.is_relative_to(tmp_path / "work" / "pdf")
    assert [(e["source"], e["bytes"], e["kept"]) for e in w.ledger()] == [("frb", len(GOOD), True)]
    assert w.download("frb", "https://a.example/1.pdf", "1.pdf") == path  # kept: costs nothing
    assert len(server.requests) == 1 and len(w.ledger()) == 1


def test_a_third_issue_of_a_source_is_refused_before_any_request(tmp_path):
    server = Server({f"https://a.example/{n}.pdf": GOOD for n in (1, 2, 3)})
    w = web(tmp_path, server)
    w.download("fdic", "https://a.example/1.pdf", "1.pdf")
    w.download("fdic", "https://a.example/2.pdf", "2.pdf")
    before = len(server.requests)
    with pytest.raises(sm.TooManyDownloads):
        w.download("fdic", "https://a.example/3.pdf", "3.pdf")
    assert len(server.requests) == before
    w.download("mts", "https://a.example/3.pdf", "3.pdf")  # another source has its own two


def test_a_transfer_that_is_not_kept_still_counts_against_the_cap(tmp_path):
    server = Server(
        {
            "https://a.example/bad.pdf": b"<html>not a pdf</html>",
            "https://a.example/1.pdf": GOOD,
            "https://a.example/2.pdf": GOOD,
        }
    )
    w = web(tmp_path, server)
    with pytest.raises(OSError):
        w.download("frb", "https://a.example/bad.pdf", "bad.pdf")
    assert not (tmp_path / "work" / "pdf" / "frb" / "bad.pdf").exists()
    assert [e["kept"] for e in w.ledger()] == [False]
    w.download("frb", "https://a.example/1.pdf", "1.pdf")
    with pytest.raises(sm.TooManyDownloads):
        w.download("frb", "https://a.example/2.pdf", "2.pdf")


def test_a_short_download_is_not_kept(tmp_path):
    server = Server({"https://a.example/1.pdf": Response(GOOD, {"Content-Length": str(len(GOOD) + 5)})})
    w = web(tmp_path, server)
    with pytest.raises(OSError):
        w.download("frb", "https://a.example/1.pdf", "1.pdf")
    assert not list((tmp_path / "work" / "pdf").rglob("*.pdf*"))


def test_the_command_refuses_a_work_directory_inside_the_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        sm.main(["--work", str(tmp_path / "scratch")])
    assert "outside the repo" in capsys.readouterr().err
    with pytest.raises(SystemExit):  # nor a directory that holds the repo
        sm.main(["--work", str(tmp_path.parent)])


def test_the_command_refuses_a_third_download_of_a_source(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit):
        sm.main(["--work", str(tmp_path / "scratch")] + [f"--download=frb={n}" for n in (1, 2, 3)])
    assert "cap is 2" in capsys.readouterr().err


# --- scan or text ----------------------------------------------------------------------------


def layers(tmp_path: Path, content: bytes) -> sm.PageLayers:
    path = tmp_path / "p.pdf"
    path.write_bytes(pdf_bytes(content))
    count, found = sm.pdf_layers(path)
    assert count == 1
    return found[0]


def test_a_scan_with_invisible_text_is_a_scan_with_an_ocr_layer(tmp_path):
    page = layers(tmp_path, IMAGE + words(3))
    assert (page.cover, page.invisible_text, page.beneath_text) == (1.0, 3, 0)
    assert page.kind == sm.OCR_LAYER


def test_text_drawn_under_the_image_is_an_ocr_layer_too(tmp_path):
    page = layers(tmp_path, words(0) + b" " + IMAGE)
    assert (page.invisible_text, page.beneath_text) == (0, 3)
    assert page.kind == sm.OCR_LAYER


def test_a_scan_with_hardly_any_text_is_a_thin_scan_not_text(tmp_path):
    page = layers(tmp_path, IMAGE + words(0, 1))
    assert page.kind == sm.SCAN_THIN


def test_visible_text_with_no_covering_image_is_real_text(tmp_path):
    page = layers(tmp_path, words(0))
    assert (page.cover, page.images) == (0.0, 0)
    assert page.kind == sm.REAL_TEXT


def test_a_blank_page_is_other(tmp_path):
    assert layers(tmp_path, b"").kind == sm.OTHER


def test_images_that_tile_a_page_cover_it_and_a_repeated_one_counts_once():
    half = [(0, 0, 612, 396), (0, 396, 612, 792)]
    assert sm.covered_share(half, 612, 792) == 1.0
    assert sm.covered_share([(0, 0, 612, 396)] * 2, 612, 792) == pytest.approx(0.5, abs=0.03)
    assert sm.covered_share([], 612, 792) == 0.0


def test_sample_pages_are_spread_from_first_to_last():
    assert sm.sample_pages(5) == [1, 2, 3, 4, 5]
    picked = sm.sample_pages(157)
    assert len(picked) == sm.SAMPLE_PAGES and picked[0] == 1 and picked[-1] == 157
    assert picked == sorted(set(picked))


def test_page_texts_gives_each_pages_own_text(tmp_path):
    path = tmp_path / "p.pdf"
    path.write_bytes(pdf_bytes(words(0, 2)))
    assert "Total 0" in sm.page_texts(path)[0]


# --- tables ----------------------------------------------------------------------------------


def test_bulletin_tables_are_found_by_their_numbered_captions_and_totals_go_to_the_last_one():
    pages = [
        "A4 Domestic Financial Statistics • June 2000\n1.10 RESERVES, MONEY STOCK, AND DEBT MEASURES\n"
        "1 Total -6.6 -15.4\n2 Revolving 1.0\n",
        "1.12 RESERVES AND BORROWINGS Depository Institutions1\n2 Total vault cash3 44,742\n"
        "1.13 Not a caption: lower case after the number\n",
        "1.12 RESERVES AND BORROWINGS—Continued\n9 Total borrowings 12\n10 Totals 4\n",
    ]
    tables = sm.find_tables("frb", pages)
    assert [(t.key, t.pages, t.total_lines) for t in tables] == [
        ("1.10", [1], 1),
        ("1.12", [2, 3], 3),
    ]
    assert tables[0].title == "RESERVES, MONEY STOCK, AND DEBT MEASURES"
    assert tables[1].example.startswith("2 Total vault cash")
    assert [t.key for t in sm.with_totals(tables)] == ["1.10", "1.12"]


def test_treasury_statement_tables_merge_each_months_caption_and_keep_the_first_title():
    pages = [
        "Table 4. Receipts of the U.S. Government, October 1985 and Other Periods (in millions)\n"
        "Total-Individual income taxes 5\n",
        "Table 5.—Outlays of the U.S. Government, October 1985\nTotal—Legislative Branch 1\n",
        "Table 4. Receipts of the U.S. Government, November 1985 and Other Periods\nTotal 3\n",
        "Table 6.\nSchedule C (Memorandum)\n",
    ]
    tables = {t.key: t for t in sm.find_tables("mts", pages)}
    assert sorted(tables) == ["Table 4", "Table 5", "Table 6"]
    assert tables["Table 4"].pages == [1, 3] and tables["Table 4"].total_lines == 2
    assert tables["Table 4"].title == "Receipts of the U.S. Government, (in millions)"
    assert tables["Table 6"].total_lines == 0


def test_fdic_statements_are_found_by_name_through_ocr_letter_spacing():
    pages = [
        "Bank Insurance Fund S tatem ents of Financial Position at Decem ber 31\nTotal Assets $ 5\n",
        "Statements of\nIncome and the\nDeposit Insurance Fund\nTotal Income 7\n",
        "Table 122. NUMBER OF BANKS CLOSED, 1934-1985\nTotal 3\n",
    ]
    tables = {t.key: t for t in sm.find_tables("fdic", pages)}
    assert set(tables) == {"Statements of Financial Position", "Statements of Income", "Table 122"}
    assert tables["Statements of Financial Position"].total_lines == 1


def test_a_total_before_any_caption_belongs_to_no_table():
    assert sm.find_tables("mts", ["Total 5\n", "Table 1. Summary\n"]) == [
        sm.TableFound("Table 1", "Summary", [2], 0, "")
    ]


def test_recurring_tables_are_those_found_in_both_issues():
    a = sm.find_tables("mts", ["Table 1. A\nTotal 1\n", "Table 2. B\nTotal 1\n"])
    b = sm.find_tables("mts", ["Table 2. B\nTotal 2\n", "Table 3. C\nTotal 3\n"])
    assert [(x.key, y.key) for x, y in sm.recurring(a, b)] == [("Table 2", "Table 2")]


# --- the recommendation ----------------------------------------------------------------------


def edition(source="frb", year=1985, month=6, pages=100, origin="reformatted digital"):
    return sm.Edition(source, f"{source}{year}{month}", f"{year}-{month}", year, year, pages, origin, None, None, month)


def checked(source: sm.Source, tables: int, scan=True, year=2000, ocr_pages=3):
    layer = sm.PageLayers(1, 1.0, 1, 10, 10 if scan else 0, 0, 1, 0)
    texts = [f"Table {n}. T\nTotal 1\n" for n in range(1, tables + 1)]
    return sm.Checked(
        edition(source.key, year, None), "x.pdf", 1000, 1, [layer] * ocr_pages, sm.find_tables("mts", texts)
    )


def result(key: str, rights, tables: int, scan: bool, editions=None):
    src = sm.SOURCE[key]
    return sm.Result(src, rights, editions or [edition(key, y, m) for y in (1980, 1981) for m in range(1, 13)], [checked(src, tables, scan)], [], {}, {}, [])


def test_the_most_issues_a_year_that_fit_under_the_earlier_sources_pages():
    short = [edition(year=y, month=m, pages=10) for y in (1980, 1981) for m in range(1, 13)]
    long_ = [edition(year=y, month=m, pages=2000) for y in (1980, 1981) for m in range(1, 13)]
    r = result("frb", sm.NOC_US, 5, True, short)
    assert sm.choose_issues(r, 1981).per_year == 12
    r = result("frb", sm.NOC_US, 5, True, long_)
    choice = sm.choose_issues(r, 1981)
    assert (choice.per_year, choice.months, len(choice.issues), choice.pages) == (1, (6,), 2, 4000)
    assert sm.choose_issues(result("frb", sm.NOC_US, 5, True, [edition(year=1980, month=6, pages=7000)]), 1981) is None


def test_one_edition_a_year_takes_every_year():
    annual = [edition("fdic", y, None, 90) for y in range(1980, 1985)]
    choice = sm.choose_issues(result("fdic", None, 5, True, annual), 1984)
    assert (choice.per_year, len(choice.issues)) == (1, 5)


def test_a_statement_ranks_before_a_basis_and_then_more_totals_win():
    results = [result("mts", None, 8, True), result("frb", sm.NOC_US, 5, True), result("fdic", None, 9, True)]
    rec = sm.recommend(results)
    assert rec.choice.source.key == "frb"
    assert {r.source.key: why for r, why in rec.ranking} == {"mts": "eligible", "frb": "eligible", "fdic": "eligible"}
    without = sm.recommend([result("mts", None, 8, True), result("fdic", None, 9, True)])
    assert without.choice.source.key == "fdic"  # no statement among them: more totals decide


def test_a_source_that_is_not_a_verified_scan_or_has_few_totals_is_not_eligible():
    results = [result("frb", sm.NOC_US, 2, True), result("mts", None, 8, False)]
    assert sm.recommend(results) is None
    reasons = dict.fromkeys(("frb", "mts"))
    rec = sm.recommend(results + [result("fdic", None, 4, True)])
    for r, why in rec.ranking:
        reasons[r.source.key] = why
    assert "only 2 recurring tables" in reasons["frb"]
    assert "no downloaded issue verified as a scan" in reasons["mts"]
    assert reasons["fdic"] == "eligible"


def test_a_page_mostly_without_ocr_text_does_not_verify_a_scan():
    src = sm.SOURCE["frb"]
    thin = sm.PageLayers(1, 1.0, 1, 10, 0, 0, 1, 0)
    ocr = sm.PageLayers(1, 1.0, 1, 10, 10, 0, 1, 0)
    r = result("frb", sm.NOC_US, 5, True)
    r.checked[0].layers = [thin, thin, ocr]
    assert sm.verified_scan_year(r) is None
    r.checked[0].layers = [thin, ocr, ocr]
    assert sm.verified_scan_year(r) == 2000
    assert src.federal_agency


def test_the_label_runs_through_the_last_unbroken_year():
    r = result("frb", sm.NOC_US, 5, True)
    r.labels_after = [edition(year=2001), edition(year=2002), edition(year=2003, origin="born digital")]
    assert sm.label_through(r) == 2002
    r.editions[0] = edition(year=1980, origin=None)
    assert sm.label_through(r) is None


# --- the report ------------------------------------------------------------------------------


def survey(tmp_path: Path) -> sm.Survey:
    frb = result("frb", sm.NOC_US, 5, True)
    fdic = result("fdic", None, 4, True, [edition("fdic", y, None, 90) for y in (1980, 1985)])
    fdic.copy_sizes = {1985: 23_647_371, 1990: None}
    fdic.extra = [("Statistics on Banking, FRASER title 125", None, [edition("fdic", 1997, 8, 410)])]
    mts = result("mts", None, 8, True, [
        sm.Edition("mts", "vol-18-mts-oct85-sep86", "Volume 18", 1985, 1986, 383, None, None, 34_823_029),
        sm.Edition("mts", "vol-27-mts-oct97-sep98-hc", "Volume 27", 1997, 1998, None, None, None, 19_318_337),
    ])
    mts.monthly_sizes = {"10/1998": 900_000, "11/1998": 1_100_000}
    ledger = [{"source": "frb", "url": "https://a.example/frb_061985.pdf", "bytes": None, "kept": False, "note": "a test"}]
    return sm.Survey([frb, fdic, mts], ledger, 12)


def test_the_report_names_every_source_the_rule_the_ledger_and_the_borderline_cases(tmp_path):
    text = sm.render(survey(tmp_path))
    for part in (
        "## Recommendation", "## Summary", "## Method and limits", "Federal Reserve Bulletin",
        "FDIC annual reports", "Monthly Treasury Statement", "Borderline, for you to decide",
        "frb_061985.pdf", "The rule: ", "not on FRASER",
    ):
        assert part in text
    assert text == sm.render(survey(tmp_path))  # the same inputs, the same report


def test_the_report_holds_no_local_path_name_or_address(tmp_path):
    text = sm.render(survey(tmp_path))
    for private in ("/Users/", "/private/", "/tmp/", str(tmp_path), "@"):
        assert private not in text


def test_the_committed_survey_exists_and_holds_nothing_private():
    path = REPO / "results" / "modern" / "survey.md"
    if not path.exists():
        pytest.skip("not made yet")
    text = path.read_text(encoding="utf-8")
    for private in ("/Users/", "/private/", "/tmp/", "@"):
        assert private not in text
    for part in ("Federal Reserve Bulletin", "Monthly Treasury Statement", "## Recommendation"):
        assert part in text
