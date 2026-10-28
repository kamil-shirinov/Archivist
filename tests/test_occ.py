import hashlib
import io
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_fraser import image_pdf, text_pdf

from archivist.ingest import fraser, occ

REAL = Path(__file__).resolve().parents[1] / "data" / "real_occ"
TREASURY = Path(__file__).resolve().parents[1] / "data" / "real"

BASIS = fraser.RecordedBasis(
    fraser_shows="no rights statement",
    basis=occ.BASIS,
    citations=occ.CITATIONS,
    checked=date(2026, 10, 28),
    pages_checked=[occ.TITLE_URL],
)
NOC_US = fraser.Rights(
    statement=fraser.RIGHTS_STATEMENT, uri=fraser.RIGHTS_URI, checked=date(2026, 10, 28)
)


@pytest.fixture(autouse=True)
def _not_stopped():
    fraser._STOP.clear()
    yield
    fraser._STOP.clear()


def title_page(rights: str = "") -> str:
    """What FRASER's title page for title 56 shows: no RIGHTS field. `rights` adds one."""
    return (
        f"<html><head><title>{occ.TITLE_NAME} | Title | FRASER | St. Louis Fed</title></head><body>"
        f"<h1>{occ.TITLE_NAME}</h1><p>DATE: 1863-1980</p>{rights}"
        '<a href="/metadata.php?type=title&id=56&json=1">Metadata (JSON)</a></body></html>'
    )


def item_meta(volume: str) -> dict:
    """The parts of an item's metadata record that the ingest reads."""
    year, _, part = volume.partition("-v")
    return {
        "recordInfo": {"recordIdentifier": [occ.VOLUMES[volume]]},
        "relatedItem": [{"@type": "parent", "recordInfo": {"recordIdentifier": ["56"]}}],
        "originInfo": {"dateIssued": [year]},
        "titleInfo": [{"title": year, "titlePartNumber": f"Volume {part}" if part else ""}],
        "location": {"pdfUrl": [f"https://fraser.stlouisfed.org/docs/publications/comp/{volume}.pdf"]},
        "accessCondition": "For more information on rights relating to this item, please see: x",
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
        body = title_page() if url == occ.TITLE_URL else json.dumps(item_meta("1905"))
        return FakeResponse(body.encode())

    monkeypatch.setattr(fraser.urllib.request, "urlopen", fake_urlopen)
    occ.check_rights()
    occ.read_pdf_url("1905", lambda line: None)
    assert [r.full_url for r in sent] == [occ.TITLE_URL, occ.metadata_url("1905")]
    for request in sent:
        assert request.header_items() == [("User-agent", fraser.USER_AGENT)]
    assert "@" not in fraser.USER_AGENT and "/Users/" not in fraser.USER_AGENT


def test_occ_makes_no_request_of_its_own():
    source = Path(occ.__file__).read_text()
    assert "urllib" not in source and "http.client" not in source  # only fraser._open sends anything


# --- the rights gate ----------------------------------------------------------------------------


def test_the_recorded_basis_says_what_it_rests_on():
    assert BASIS.fraser_shows == "no rights statement"
    assert "Comptroller of the Currency is a bureau of the US Department of the Treasury" in BASIS.basis
    assert "works of the US Government" in BASIS.basis and "public domain by age" in BASIS.basis
    assert BASIS.citations == ["17 U.S.C. § 105"] and BASIS.pages_checked == [occ.TITLE_URL]


@pytest.mark.parametrize("rights", [NOC_US, BASIS])
def test_the_gate_accepts_frasers_statement_or_a_recorded_basis(rights):
    assert fraser.check_rights_record(rights) == []
    treasury = fraser.Sources.model_validate_json((TREASURY / "sources.json").read_text())
    assert fraser.check_sources(treasury.model_copy(update={"rights": rights})) == []


@pytest.mark.parametrize(
    "rights",
    [
        fraser.Rights(statement="In Copyright", uri=fraser.RIGHTS_URI, checked=date(2026, 10, 28)),
        fraser.Rights(statement=fraser.RIGHTS_STATEMENT, uri="http://x", checked=date(2026, 10, 28)),
        BASIS.model_copy(update={"basis": "  "}),
        BASIS.model_copy(update={"citations": [""]}),
        BASIS.model_copy(update={"pages_checked": []}),
        BASIS.model_copy(update={"fraser_shows": "a rights statement"}),
    ],
)
def test_the_gate_refuses_a_record_that_is_not_one_of_the_two(rights):
    assert fraser.check_rights_record(rights)
    treasury = fraser.Sources.model_validate_json((TREASURY / "sources.json").read_text())
    assert fraser.check_sources(treasury.model_copy(update={"rights": rights}))


def test_sources_without_a_rights_record_do_not_even_load():
    good = json.loads((TREASURY / "sources.json").read_text())
    del good["rights"]
    with pytest.raises(ValidationError):
        fraser.Sources.model_validate(good)
    good["rights"] = {}
    with pytest.raises(ValidationError):
        fraser.Sources.model_validate(good)


@pytest.mark.parametrize(
    "damage",
    [
        {"basis": ""},
        {"basis": "too short"},
        {"citations": []},
        {"citations": [" "]},
        {"pages_checked": []},
        {"fraser_shows": "No Copyright - United States"},
        {"unexpected": 1},
    ],
)
def test_a_recorded_basis_with_a_missing_part_is_refused_on_load(damage):
    with pytest.raises(ValidationError):
        fraser.RecordedBasis.model_validate({**BASIS.model_dump(mode="json"), **damage})


def test_the_two_kinds_of_record_read_back_as_themselves():
    for rights in (NOC_US, BASIS):
        sources = fraser.Sources(title="t", publisher="p", title_url="u", rights=rights, files=[])
        again = fraser.Sources.model_validate_json(sources.model_dump_json())
        assert again.rights == rights and type(again.rights) is type(rights)


def test_check_rights_records_the_basis_when_the_title_page_shows_no_statement():
    rights = occ.check_rights(lambda url: title_page())
    assert isinstance(rights, fraser.RecordedBasis)
    assert fraser.check_rights_record(rights) == []
    assert rights.pages_checked == [occ.TITLE_URL]
    assert abs((rights.checked - datetime.now(UTC).date()).days) <= 1  # the day it was read
    assert rights.basis == occ.BASIS and rights.citations == occ.CITATIONS


def test_check_rights_prefers_frasers_own_statement_when_the_page_has_it():
    page = title_page(
        '<span>RIGHTS:</span> <a href="http://rightsstatements.org/vocab/NoC-US/1.0/">'
        "No Copyright - United States (NoC-US)</a>"
    )
    rights = occ.check_rights(lambda url: page)
    assert isinstance(rights, fraser.Rights) and rights.statement == fraser.RIGHTS_STATEMENT


@pytest.mark.parametrize(
    "page",
    [
        title_page("<p>RIGHTS: In Copyright (InC)</p>"),
        title_page('<a href="http://rightsstatements.org/vocab/InC/1.0/">In Copyright</a>'),
        title_page("<p>RIGHTS: No Copyright - Other Known Legal Restrictions</p>"),
        "<html><title>Service unavailable</title><body>try again later</body></html>",  # not the page
        "",
    ],
)
def test_any_other_statement_or_a_page_that_is_not_the_title_page_stops_everything(page):
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        occ.check_rights(lambda url: page)


# --- the volumes and the split -------------------------------------------------------------------


def test_the_volumes_are_ten_in_eight_years_with_two_volumes_in_1915_and_1920():
    assert list(occ.VOLUMES) == [
        "1905", "1910", "1915-v1", "1915-v2", "1920-v1", "1920-v2", "1925", "1930", "1935", "1940",
    ]  # fmt: skip
    assert occ.years() == ["1905", "1910", "1915", "1920", "1925", "1930", "1935", "1940"]
    assert len(set(occ.VOLUMES.values())) == 10  # no two volumes are the same FRASER item
    assert occ.VOLUMES["1915-v1"] + 1 == occ.VOLUMES["1915-v2"]


def test_the_split_is_the_one_that_was_fixed():
    split = occ.current_split()
    assert split.development == ["1905", "1925"]
    assert split.held_out == ["1910", "1915", "1920", "1930", "1935", "1940"]
    assert {v: split.side(v) for v in occ.VOLUMES} == {
        "1905": "development",
        "1910": "held_out",
        "1915-v1": "held_out",
        "1915-v2": "held_out",
        "1920-v1": "held_out",
        "1920-v2": "held_out",
        "1925": "development",
        "1930": "held_out",
        "1935": "held_out",
        "1940": "held_out",
    }


def test_a_split_that_misses_repeats_or_invents_a_year_is_refused():
    split = occ.current_split()
    with pytest.raises(ValueError, match="more than once"):
        occ.Split(
            development=[*split.development, "1910"], held_out=split.held_out, note=""
        )
    with pytest.raises(ValueError, match="missing"):
        occ.Split(development=split.development, held_out=split.held_out[1:], note="")
    with pytest.raises(ValueError, match="unknown"):
        occ.Split(development=split.development, held_out=[*split.held_out, "1945"], note="")


def test_the_addresses_of_an_item_follow_from_its_id():
    assert occ.item_url("1915-v2") == f"{occ.TITLE_URL}/1915-19131"
    assert occ.metadata_url("1905") == "https://fraser.stlouisfed.org/metadata.php?type=item&id=19070&json=1"
    assert occ.pdf_name("1915-v1") == "1915-v1_compcurr.pdf"


# --- reading an item's metadata --------------------------------------------------------------


@pytest.mark.parametrize("volume", list(occ.VOLUMES))
def test_a_matching_item_gives_its_pdf_address(volume):
    meta = item_meta(volume)
    assert occ._item_pdf_url(volume, meta) == meta["location"]["pdfUrl"][0]


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda m: m["originInfo"].update(dateIssued=["1906"]), "year"),
        (lambda m: m["recordInfo"].update(recordIdentifier=[19071]), "item"),
        (lambda m: m["titleInfo"][0].update(titlePartNumber="Volume 2"), "part"),
        (lambda m: m["relatedItem"][0]["recordInfo"].update(recordIdentifier=["407"]), "title"),
        (lambda m: m["location"].update(pdfUrl=["http://elsewhere.example/a.pdf"]), "pdfUrl"),
        (lambda m: m["location"].update(pdfUrl=["https://fraser.stlouisfed.org/docs/a.html"]), "pdfUrl"),
        (lambda m: m["location"].update(pdfUrl=[]), "pdfUrl"),
        (lambda m: m.pop("location"), "unexpected metadata"),
        (lambda m: m.pop("originInfo"), "unexpected metadata"),
    ],
)
def test_an_item_that_is_not_the_volume_we_think_it_is_is_refused(change, match):
    meta = item_meta("1905")
    change(meta)
    with pytest.raises(fraser.DownloadError, match=match):
        occ._item_pdf_url("1905", meta)


def test_a_second_volume_must_say_which_part_it_is():
    meta = item_meta("1915-v2")
    assert meta["titleInfo"][0]["titlePartNumber"] == "Volume 2"
    meta["titleInfo"][0]["titlePartNumber"] = "Volume 1"
    with pytest.raises(fraser.DownloadError, match="part"):
        occ._item_pdf_url("1915-v2", meta)


def test_an_item_that_shows_another_rights_statement_stops_everything():
    meta = item_meta("1905")
    meta["accessCondition"] = "http://rightsstatements.org/vocab/InC/1.0/"
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        occ._item_pdf_url("1905", meta)
    meta["accessCondition"] = fraser.RIGHTS_URI  # FRASER stating NoC-US for the item is fine
    occ._item_pdf_url("1905", meta)


def test_metadata_that_is_not_json_is_a_failed_download_not_a_crash(monkeypatch):
    monkeypatch.setattr(fraser, "_pause", lambda seconds: None)
    with pytest.raises(fraser.DownloadError, match="not JSON"):
        occ.read_pdf_url("1905", lambda line: None, lambda url: "<html>busy</html>")
    with pytest.raises(fraser.DownloadError, match="not a JSON object"):
        occ.read_pdf_url("1905", lambda line: None, lambda url: "[1, 2]")


# --- the committed records ---------------------------------------------------------------------


def test_sources_json_validates_and_names_every_volume_once():
    sources = occ.Sources.model_validate_json((REAL / "sources.json").read_text())
    assert occ.check_sources(sources) == []
    assert sources.title_url == occ.TITLE_URL
    assert [f.issue for f in sources.files] == list(occ.VOLUMES)
    for record in sources.files:
        assert record.resolved_url.startswith("https://fraser.stlouisfed.org/")
        assert record.url.startswith(occ.PDF_PREFIX) and record.item_id == occ.VOLUMES[record.issue]


def test_the_committed_rights_record_is_frasers_statement_or_the_recorded_basis_never_nothing():
    rights = occ.Sources.model_validate_json((REAL / "sources.json").read_text()).rights
    assert fraser.check_rights_record(rights) == []
    if isinstance(rights, fraser.RecordedBasis):
        assert "17 U.S.C. § 105" in rights.citations
        assert "works of the US Government" in rights.basis
        assert rights.fraser_shows == "no rights statement" and rights.checked <= date.today()
    else:
        assert rights.statement == fraser.RIGHTS_STATEMENT


def test_the_manifest_validates_and_agrees_with_sources():
    manifest = occ.Manifest.model_validate_json((REAL / "manifest.json").read_text())
    assert occ.check_manifest(manifest) == []
    assert (manifest.renderer.dpi, manifest.renderer.jpeg_quality) == (
        fraser.DPI,
        fraser.JPEG_QUALITY,
    )
    sources = occ.Sources.model_validate_json((REAL / "sources.json").read_text())
    assert [e.issue for e in manifest.issues] == [f.issue for f in sources.files]
    for page in manifest.pages:
        assert len(page.title_hint) <= fraser.HINT_LINES
        assert all(0 < len(line) <= fraser.HINT_WIDTH for line in page.title_hint)
        assert page.figure_lines <= page.lines and page.total_lines <= page.lines
        assert bool(page.title_hint) == (page.lines > 0)  # the hint and the counts read the same text
    assert sum(p.lines > 0 for p in manifest.pages) > 0.95 * len(manifest.pages)  # the OCR layer is there
    for entry in manifest.issues:  # FRASER's own page counts for the items: 751 for 1905, and so on
        assert entry.pages == {
            "1905": 751, "1910": 836, "1915-v1": 246, "1915-v2": 999, "1920-v1": 330,
            "1920-v2": 882, "1925": 664, "1930": 787, "1935": 862, "1940": 473,
        }[entry.issue]  # fmt: skip


def test_split_json_is_the_split_fixed_in_code():
    assert (
        occ.Split.model_validate_json((REAL / "split.json").read_text()) == occ.current_split()
    )


def test_a_record_with_a_bad_hash_is_refused():
    good = json.loads((REAL / "sources.json").read_text())
    good["files"][0]["sha256"] = "not-a-hash"
    with pytest.raises(ValueError):
        occ.Sources.model_validate(good)


def test_check_sources_notices_a_wrong_item_address_or_a_missing_volume():
    sources = occ.Sources.model_validate_json((REAL / "sources.json").read_text())
    first, *rest = sources.files
    wrong = first.model_copy(update={"item_id": 1, "url": "http://elsewhere.example/a.pdf"})
    problems = occ.check_sources(sources.model_copy(update={"files": [wrong, *rest]}))
    assert any("item is 1" in p for p in problems) and any("not a PDF under" in p for p in problems)
    problems = occ.check_sources(sources.model_copy(update={"files": rest}))
    assert problems == [f"sources.json has no record of {first.issue}"]


# --- the counts the survey reads from the OCR text -----------------------------------------------


def test_ocr_counts_find_figure_lines_total_lines_and_the_two_headings():
    text = "\n".join(
        [
            "REPORT OF THE COMPTROLLER OF THE CURRENCY. 5",
            "RESOURCES.",
            "Loans and discounts",
            "$194,665",  # a figure line
            "12",  # a figure line
            "7",  # one digit is not enough
            "Total",
            "Total re-",
            "sources.",
            "Totals 1,200",  # begins with Totals; fewer digits than half its characters
            "The total of the loans",  # does not begin with Total
            "Liabilities—Continued",
            "",
            "   ",
        ]
    )
    assert occ.ocr_counts(text) == {
        "lines": 12,
        "figure_lines": 2,
        "total_lines": 3,
        "resources_heading": True,
        "liabilities_heading": True,
    }


def test_a_page_without_text_counts_as_nothing():
    assert occ.ocr_counts("") == {
        "lines": 0,
        "figure_lines": 0,
        "total_lines": 0,
        "resources_heading": False,
        "liabilities_heading": False,
    }
    assert not occ.ocr_counts("Total resources and Liabilities are not headings")["liabilities_heading"]


def test_a_total_or_a_heading_must_begin_the_line():
    counts = occ.ocr_counts("Subtotal\nGrand total\nResourcesX\nTotality\nLiabilitiesx")
    assert counts["total_lines"] == 0  # not at the start, or not the word Total
    assert not counts["resources_heading"] and not counts["liabilities_heading"]
    assert occ.ocr_counts("Total\nTotal.\nTotals\nTotal, Western States")["total_lines"] == 4


def test_the_manifest_carries_the_hint_and_the_counts_read_from_the_pdfs_own_text(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(occ, "VOLUMES", {"1905": 19070})
    root = tmp_path / "real_occ"
    (root / "pdf").mkdir(parents=True)
    lines = [
        "REPORT OF THE COMPTROLLER OF THE CURRENCY. 5",
        "No. 3.- PRINCIPAL ITEMS OF RESOURCES AND LIABILITIES",
        "Resources.",
        "Loans",
        "1,200,000",
        "Total",
        "Liabilities.",
        "98,765",
    ]
    (root / "pdf" / occ.pdf_name("1905")).write_bytes(text_pdf(lines))
    occ.render_volume("1905", root, lambda line: None)
    [page] = occ.build_manifest(root).pages
    assert page.title_hint == lines[:4]
    assert (page.lines, page.figure_lines, page.total_lines) == (8, 2, 1)
    assert page.resources_heading and page.liabilities_heading


def test_a_page_entry_cannot_leave_out_the_counts():
    entry = {"issue": "1905", "page": 1, "sha256": "0" * 64, "size_bytes": 1, "width": 1, "height": 1}
    with pytest.raises(ValidationError):
        occ.PageEntry.model_validate({**entry, "title_hint": []})


# --- safe to interrupt ------------------------------------------------------------------------


@pytest.fixture
def two_volumes(monkeypatch, tmp_path):
    """The ingest shrunk to two volumes, with FRASER replaced by local pages and a local PDF."""
    monkeypatch.setattr(occ, "VOLUMES", {"1905": 19070, "1910": 19075})
    monkeypatch.setattr(occ, "DEVELOPMENT", ["1905"])
    monkeypatch.setattr(occ, "HELD_OUT", ["1910"])
    monkeypatch.setattr(fraser, "POLITE_PAUSE", 0)
    source = image_pdf(tmp_path / "source.pdf")
    calls: list[str] = []

    def fake_fetch(url: str, part: Path):
        calls.append(url)
        data = source.read_bytes()
        part.write_bytes(data)
        return url.replace("/docs/", "/files/docs/"), len(data), hashlib.sha256(data).hexdigest()

    pages = {occ.TITLE_URL: title_page()}
    pages |= {occ.metadata_url(v): json.dumps(item_meta(v)) for v in occ.VOLUMES}
    monkeypatch.setattr(fraser, "_fetch_pdf", fake_fetch)
    monkeypatch.setattr(fraser, "_fetch_text", lambda url: pages[url])
    return tmp_path / "real_occ", calls, pages


def leftovers(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.part")]


def test_stopping_mid_run_leaves_whole_volumes_and_no_manifest_and_a_rerun_finishes(two_volumes):
    root, calls, _ = two_volumes

    def stop_after_the_first_volume(line: str) -> None:
        if "1905: 3 pages rendered" in line:
            fraser._STOP.set()

    assert occ.ingest(root, log=stop_after_the_first_volume) == 130
    assert not (root / "manifest.json").exists() and not (root / "split.json").exists()
    assert (root / "pdf" / "1905_compcurr.pdf").is_file()
    assert not (root / "pdf" / "1910_compcurr.pdf").exists()
    assert len(list((root / "pages" / "1905").glob("p*.jpg"))) == 3
    recorded = occ.Sources.model_validate_json((root / "sources.json").read_text())
    assert [f.issue for f in recorded.files] == ["1905"]
    assert leftovers(root) == []
    assert len(calls) == 1

    fraser._STOP.clear()
    assert occ.ingest(root, log=lambda line: None) == 0
    assert len(calls) == 2  # the first volume was not fetched again
    assert occ.verify(root, log=lambda line: None) == 0
    manifest = occ.Manifest.model_validate_json((root / "manifest.json").read_text())
    assert manifest.pages[0].page == 1 and [e.issue for e in manifest.issues] == ["1905", "1910"]
    assert occ.Split.model_validate_json((root / "split.json").read_text()) == occ.current_split()


def test_the_rights_record_is_written_with_the_first_pdf_and_names_the_basis(two_volumes):
    root, _, _ = two_volumes
    assert occ.ingest(root, log=lambda line: None) == 0
    sources = occ.Sources.model_validate_json((root / "sources.json").read_text())
    assert isinstance(sources.rights, fraser.RecordedBasis) and sources.rights.citations == occ.CITATIONS
    assert occ.check_sources(sources) == []
    for record in sources.files:  # the address came from the item's metadata
        assert record.url == item_meta(record.issue)["location"]["pdfUrl"][0]
        assert record.metadata_url == occ.metadata_url(record.issue)


def test_a_complete_tree_needs_no_network_on_rerun(two_volumes, monkeypatch):
    root, calls, _ = two_volumes
    assert occ.ingest(root, log=lambda line: None) == 0
    monkeypatch.setattr(fraser, "_fetch_text", lambda url: pytest.fail("network used"))
    monkeypatch.setattr(fraser, "_fetch_pdf", lambda url, part: pytest.fail("network used"))
    assert occ.ingest(root, log=lambda line: None) == 0
    assert len(calls) == 2


def test_another_rights_statement_stops_before_anything_is_downloaded(two_volumes):
    root, calls, pages = two_volumes
    pages[occ.TITLE_URL] = title_page("<p>RIGHTS: In Copyright (InC)</p>")
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        occ.ingest(root, log=lambda line: None)
    assert calls == [] and not list(root.rglob("*.pdf")) and not (root / "sources.json").exists()


def test_an_item_with_another_rights_statement_stops_the_run_at_that_item(two_volumes):
    root, calls, pages = two_volumes
    meta = item_meta("1910")
    meta["accessCondition"] = "http://rightsstatements.org/vocab/InC/1.0/"
    pages[occ.metadata_url("1910")] = json.dumps(meta)
    with pytest.raises(fraser.RightsError):
        occ.ingest(root, log=lambda line: None)
    assert [f.issue for f in occ.Sources.model_validate_json((root / "sources.json").read_text()).files] == ["1905"]
    assert len(calls) == 1 and leftovers(root) == []


def test_a_wrong_item_is_a_failed_volume_and_the_others_still_finish(two_volumes):
    root, _, pages = two_volumes
    meta = item_meta("1905")
    meta["originInfo"]["dateIssued"] = ["1906"]
    pages[occ.metadata_url("1905")] = json.dumps(meta)
    lines: list[str] = []
    assert occ.ingest(root, log=lines.append) == 1
    assert any("1905: FAILED" in line and "not volume 1905" in line for line in lines)
    assert (root / "pdf" / "1910_compcurr.pdf").is_file() and not (root / "pdf" / "1905_compcurr.pdf").exists()
    assert not (root / "manifest.json").exists()


def test_a_stop_during_a_download_removes_the_temp_file_and_records_nothing(two_volumes, monkeypatch):
    root, _, _ = two_volumes

    def interrupted(url: str, part: Path):
        part.write_bytes(b"%PDF-1.4 only the first few bytes")
        fraser._STOP.set()
        fraser._check_stop()

    monkeypatch.setattr(fraser, "_fetch_pdf", interrupted)
    assert occ.ingest(root, log=lambda line: None) == 130
    assert leftovers(root) == []
    assert not list((root / "pdf").glob("*.pdf"))
    assert not (root / "sources.json").exists()


@pytest.mark.parametrize("damage", ["short", "not a pdf", "empty"])
def test_a_download_that_is_short_or_not_a_pdf_never_reaches_its_final_name(
    two_volumes, monkeypatch, damage
):
    root, _, _ = two_volumes
    good = (root.parent / "source.pdf").read_bytes()
    body = {"short": good[: len(good) // 2], "not a pdf": b"<html>busy</html>" * 20, "empty": b""}[
        damage
    ]

    def damaged(url: str, part: Path):
        part.write_bytes(body)
        if damage == "short":  # the server announced the whole file
            raise fraser.DownloadError(f"got {len(body)} bytes, server announced {len(good)}")
        return url, len(body), hashlib.sha256(body).hexdigest()

    monkeypatch.setattr(fraser, "_fetch_pdf", damaged)
    monkeypatch.setattr(fraser, "_pause", lambda seconds: None)
    sources = occ.Sources(
        title="t", publisher="p", title_url=occ.TITLE_URL,
        rights=BASIS, files=[],
    )  # fmt: skip
    with pytest.raises(fraser.DownloadError):
        occ.download_volume("1905", root, sources, lambda line: None)
    assert leftovers(root) == [] and not list((root / "pdf").glob("*.pdf"))
    assert not (root / "sources.json").exists()


def test_a_pdf_never_exists_without_its_record(two_volumes, monkeypatch):
    root, _, _ = two_volumes
    real_replace = fraser.os.replace

    def replace(src, dst):
        if str(dst).endswith(".pdf"):
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(fraser.os, "replace", replace)
    assert occ.ingest(root, log=lambda line: None) == 1  # both volumes failed at the rename
    assert not list((root / "pdf").glob("*.pdf"))
    assert [f.issue for f in occ.Sources.model_validate_json((root / "sources.json").read_text()).files]


def test_verify_notices_a_page_that_no_longer_matches_the_manifest(two_volumes):
    root, _, _ = two_volumes
    assert occ.ingest(root, log=lambda line: None) == 0
    assert occ.verify(root, log=lambda line: None) == 0
    shutil.copy(root / "pages" / "1905" / "p001.jpg", root / "pages" / "1905" / "p002.jpg")
    lines: list[str] = []
    assert occ.verify(root, log=lines.append) == 1
    assert any("1905 p002" in line for line in lines)


def test_verify_notices_a_split_that_is_valid_but_not_the_one_fixed(two_volumes):
    root, _, _ = two_volumes
    assert occ.ingest(root, log=lambda line: None) == 0
    swapped = occ.Split(development=["1910"], held_out=["1905"], note="edited")
    fraser._write_record(root / "split.json", swapped)
    lines: list[str] = []
    assert occ.verify(root, log=lines.append) == 1
    assert any("split.json differs" in line for line in lines)


def test_verify_notices_a_pdf_that_no_longer_matches_its_record(two_volumes):
    root, _, _ = two_volumes
    assert occ.ingest(root, log=lambda line: None) == 0
    pdf = root / "pdf" / "1910_compcurr.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"\n%tampered")
    lines: list[str] = []
    assert occ.verify(root, log=lines.append) == 1
    assert any("1910: PDF does not match sources.json" in line for line in lines)


def test_a_second_ingest_cannot_start_while_one_is_running(tmp_path):
    with fraser._lock(tmp_path), pytest.raises(SystemExit, match="already running"):
        fraser._lock(tmp_path).__enter__()


# --- the command line ----------------------------------------------------------------------------


def test_root_needs_a_source():
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify", "--root", "somewhere"])
    assert stop.value.code == 2


def test_verify_checks_every_source_and_reports_the_worst(monkeypatch):
    seen = []
    monkeypatch.setattr(fraser, "verify", lambda root: seen.append(("treasury", root)) or 0)
    monkeypatch.setattr(occ, "verify", lambda root: seen.append(("occ", root)) or 1)
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify"])
    assert stop.value.code == 1
    assert seen == [("treasury", fraser.DEFAULT_ROOT), ("occ", occ.DEFAULT_ROOT)]  # one failing does not hide the other

    seen.clear()
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify", "--source", "treasury"])
    assert stop.value.code == 0 and seen == [("treasury", fraser.DEFAULT_ROOT)]


def test_a_source_and_root_can_be_named(two_volumes, monkeypatch):
    root, _, _ = two_volumes
    monkeypatch.setattr(fraser.signal, "signal", lambda signum, handler: None)  # keep pytest's own
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--source", "occ", "--root", str(root)])
    assert stop.value.code == 0
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--verify", "--source", "occ", "--root", str(root)])
    assert stop.value.code == 0


def test_a_rights_stop_exits_2_and_a_stop_signal_exits_130(two_volumes, monkeypatch):
    root, _, pages = two_volumes
    monkeypatch.setattr(fraser.signal, "signal", lambda signum, handler: None)
    pages[occ.TITLE_URL] = title_page("<p>RIGHTS: In Copyright (InC)</p>")
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--source", "occ", "--root", str(root)])
    assert stop.value.code == 2
    monkeypatch.setattr(occ, "ingest", lambda root, log: 130)
    with pytest.raises(SystemExit) as stop:
        fraser.main(["--source", "occ", "--root", str(root)])
    assert stop.value.code == 130
