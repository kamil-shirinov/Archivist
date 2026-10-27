import hashlib
import json
import math
import shutil
from datetime import date
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageDraw

from archivist.ingest import fraser

REAL = Path(__file__).resolve().parents[1] / "data" / "real"

# What FRASER's title page really holds around the statement: tags, tabs, newlines, a hyphen.
TITLE_PAGE_SNIPPET = (
    '<p><span class="metadata-heading"><!--googleoff: snippet-->RIGHTS:<!--googleon: snippet--></span>\n'
    "\t\t\t\t\t\t\t<a href=http://rightsstatements.org/vocab/NoC-US/1.0/>\n"
    "\t\t\t\t\tNo Copyright - United States (NoC-US)\n\t\t\t\t</a>\n\t\t\t\t\t</p>"
)


RIGHTS = fraser.Rights(
    statement=fraser.RIGHTS_STATEMENT, uri=fraser.RIGHTS_URI, checked=date(2026, 10, 27)
)


@pytest.fixture(autouse=True)
def _not_stopped():
    fraser._STOP.clear()
    yield
    fraser._STOP.clear()


def image_pdf(path: Path, pages: int = 3) -> Path:
    """A PDF of `pages` scanned-looking pages, with no text layer."""
    images = []
    for n in range(pages):
        image = Image.new("L", (400, 520), 235)
        draw = ImageDraw.Draw(image)
        draw.text((30, 40 + n * 20), f"TABLE {n + 1}.- SUMMARY OF FISCAL OPERATIONS", fill=20)
        draw.rectangle((30, 100, 370, 480), outline=60)
        images.append(image)
    images[0].save(path, "PDF", resolution=72.0, save_all=True, append_images=images[1:])
    return path


def text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with a real text layer, one line of text per entry."""
    stream = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({t}) Tj T*" for t in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


# --- what FRASER is told about us ---------------------------------------------------------------


def test_the_user_agent_carries_only_the_public_repo_url():
    assert (
        fraser.USER_AGENT
        == "archivist-hackathon/0.1 (+https://github.com/kamil-shirinov/Archivist)"
    )
    assert "@" not in fraser.USER_AGENT and "/Users/" not in fraser.USER_AGENT


def test_every_request_is_sent_with_that_user_agent_and_nothing_else_about_us(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(request)
        raise OSError("stop here")

    monkeypatch.setattr(fraser.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OSError):
        fraser._open(fraser.TITLE_URL)
    assert [r.full_url for r in sent] == [fraser.TITLE_URL]
    assert sent[0].header_items() == [("User-agent", fraser.USER_AGENT)]


# --- the rights check ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "page",
    [
        TITLE_PAGE_SNIPPET,
        "RIGHTS: No Copyright – United States",  # en dash, as the task writes it
        "RIGHTS: <a>No Copyright — United States</a>",
        "<b>RIGHTS:</b>\n  No&nbsp;Copyright &ndash; United States",
    ],
)
def test_the_rights_statement_is_found_however_it_is_marked_up(page):
    assert fraser.rights_statement_present(page)


@pytest.mark.parametrize(
    "page",
    [
        "RIGHTS: In Copyright (InC)",
        "RIGHTS: Copyright Not Evaluated",
        "RIGHTS: No Copyright - Other Known Legal Restrictions",
        "<p>Published as No Copyright - United States elsewhere on the page</p>",  # not the field
        "",
    ],
)
def test_any_other_rights_statement_is_refused(page):
    assert not fraser.rights_statement_present(page)


def test_check_rights_returns_the_statement_or_stops():
    rights = fraser.check_rights(lambda url: TITLE_PAGE_SNIPPET)
    assert rights.statement == fraser.RIGHTS_STATEMENT and rights.uri == fraser.RIGHTS_URI
    with pytest.raises(fraser.RightsError, match="nothing was downloaded"):
        fraser.check_rights(lambda url: "RIGHTS: In Copyright (InC)")


# --- the issues and the split ----------------------------------------------------------------


def test_the_issues_are_48_monthly_and_13_june_issues():
    issues = fraser.ISSUES
    assert len(issues) == len(set(issues)) == 61
    assert [i for i in issues if i < "1943"] == [
        f"{y}-{m:02d}" for y in range(1939, 1943) for m in range(1, 13)
    ]
    assert [i for i in issues if i > "1943"] == [f"{y}-06" for y in range(1982, 1995)]


def test_the_split_covers_every_issue_exactly_once_and_the_sides_do_not_overlap():
    split = fraser.current_split()
    everything = [*split.development, *split.held_out]
    assert sorted(everything) == sorted(fraser.ISSUES)  # each issue once, none missing
    assert not set(split.development) & set(split.held_out)


def test_the_split_is_the_one_that_was_fixed():
    split = fraser.current_split()
    assert split.development == [f"1939-{m:02d}" for m in range(1, 13)] + [
        f"{y}-06" for y in (1982, 1983, 1984)
    ]
    assert split.held_out == (
        [f"{y}-{m:02d}" for y in (1940, 1941, 1942) for m in range(1, 13)]
        + [f"{y}-06" for y in range(1985, 1995)]
    )
    assert (len(split.development), len(split.held_out)) == (15, 46)


def test_a_split_that_misses_or_repeats_an_issue_is_refused():
    split = fraser.current_split()
    with pytest.raises(ValueError, match="more than once"):
        fraser.Split(
            development=[*split.development, split.held_out[0]], held_out=split.held_out, note=""
        )
    with pytest.raises(ValueError, match="missing"):
        fraser.Split(development=split.development, held_out=split.held_out[1:], note="")


# --- the committed records --------------------------------------------------------------------


def test_sources_json_validates_and_names_every_issue_once():
    sources = fraser.Sources.model_validate_json((REAL / "sources.json").read_text())
    assert fraser.check_sources(sources) == []
    assert sources.title_url == fraser.TITLE_URL
    assert sources.rights.statement == "No Copyright - United States"
    for record in sources.files:
        assert record.resolved_url.startswith("https://fraser.stlouisfed.org/")


def test_the_manifest_validates_and_agrees_with_sources():
    manifest = fraser.Manifest.model_validate_json((REAL / "manifest.json").read_text())
    assert fraser.check_manifest(manifest) == []
    assert (manifest.renderer.dpi, manifest.renderer.jpeg_quality) == (
        fraser.DPI,
        fraser.JPEG_QUALITY,
    )
    sources = fraser.Sources.model_validate_json((REAL / "sources.json").read_text())
    assert [e.issue for e in manifest.issues] == [f.issue for f in sources.files]
    for page in manifest.pages:
        assert len(page.title_hint) <= fraser.HINT_LINES
        assert all(0 < len(line) <= fraser.HINT_WIDTH for line in page.title_hint)


def test_split_json_is_the_split_fixed_in_code():
    assert (
        fraser.Split.model_validate_json((REAL / "split.json").read_text())
        == fraser.current_split()
    )


def test_a_record_with_a_bad_hash_is_refused():
    good = json.loads((REAL / "sources.json").read_text())
    good["files"][0]["sha256"] = "not-a-hash"
    with pytest.raises(ValueError):
        fraser.Sources.model_validate(good)


def test_records_are_written_one_entry_per_line_and_read_back_whole():
    obj = {"a": {"x": 1}, "rows": [{"n": 1, "t": ["é", "b"]}, {"n": 2, "t": []}], "empty": []}
    text = fraser._dumps(obj)
    assert json.loads(text) == obj
    assert text.endswith("}\n") and all(line == line.rstrip() for line in text.splitlines())
    assert len(text.splitlines()) == 8


# --- rendering ---------------------------------------------------------------------------------


def test_rendering_one_page_twice_gives_the_same_sha256(tmp_path):
    pdf = image_pdf(tmp_path / "a.pdf")
    digests = set()
    for _ in range(2):  # a fresh document each time, as two separate runs would have
        doc = pdfium.PdfDocument(pdf)
        page = doc[1]
        digests.add(hashlib.sha256(fraser.render_page(page)).hexdigest())
        page.close()
        doc.close()
    assert len(digests) == 1


def test_a_page_is_rendered_at_200_dpi(tmp_path):
    doc = pdfium.PdfDocument(image_pdf(tmp_path / "a.pdf", pages=1))
    jpeg = fraser.render_page(doc[0])
    (tmp_path / "p.jpg").write_bytes(jpeg)
    with Image.open(tmp_path / "p.jpg") as image:
        assert image.format == "JPEG"
        assert image.size == (
            math.ceil(400 * 200 / 72),
            math.ceil(520 * 200 / 72),
        )  # pdfium rounds up
        assert round(image.info["dpi"][0]) == 200


def test_the_title_hint_is_the_first_lines_of_the_pdfs_own_text(tmp_path):
    lines = ["TABLE 3.- Public debt", "  by   issues ", "", "(In millions)", "fourth", "fifth"]
    (tmp_path / "t.pdf").write_bytes(text_pdf([ln for ln in lines if ln]))
    doc = pdfium.PdfDocument(tmp_path / "t.pdf")
    assert fraser.title_hint(doc[0]) == [
        "TABLE 3.- Public debt",
        "by issues",
        "(In millions)",
        "fourth",
    ]
    assert fraser.title_hint(pdfium.PdfDocument(image_pdf(tmp_path / "s.pdf", 1))[0]) == []


# --- safe to interrupt ------------------------------------------------------------------------


@pytest.fixture
def two_issues(monkeypatch, tmp_path):
    """The ingest shrunk to two issues, with the network replaced by a local PDF."""
    monkeypatch.setattr(fraser, "ISSUES", ["1939-01", "1940-01"])
    monkeypatch.setattr(fraser, "DEVELOPMENT", ["1939-01"])
    monkeypatch.setattr(fraser, "HELD_OUT", ["1940-01"])
    monkeypatch.setattr(fraser, "POLITE_PAUSE", 0)
    source = image_pdf(tmp_path / "source.pdf")
    calls: list[str] = []

    def fake_fetch(url: str, part: Path):
        calls.append(url)
        data = source.read_bytes()
        part.write_bytes(data)
        return url.replace("/docs/", "/files/docs/"), len(data), hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(fraser, "_fetch_pdf", fake_fetch)
    monkeypatch.setattr(fraser, "check_rights", lambda: RIGHTS)
    return tmp_path / "real", calls


def leftovers(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.part")]


def test_stopping_mid_run_leaves_whole_issues_and_no_manifest_and_a_rerun_finishes(two_issues):
    root, calls = two_issues

    def stop_after_the_first_issue(line: str) -> None:
        if "1939-01: 3 pages rendered" in line:
            fraser._STOP.set()

    assert fraser.ingest(root, log=stop_after_the_first_issue) == 130
    assert not (root / "manifest.json").exists() and not (root / "split.json").exists()
    assert (root / "pdf" / "1939_01_treasurybulletin.pdf").is_file()
    assert not (root / "pdf" / "1940_01_treasurybulletin.pdf").exists()
    assert len(list((root / "pages" / "1939-01").glob("p*.jpg"))) == 3
    assert [
        f.issue
        for f in fraser.Sources.model_validate_json((root / "sources.json").read_text()).files
    ] == ["1939-01"]
    assert leftovers(root) == []
    assert len(calls) == 1

    fraser._STOP.clear()
    assert fraser.ingest(root, log=lambda line: None) == 0
    assert len(calls) == 2  # the first issue was not fetched again
    assert fraser.verify(root, log=lambda line: None) == 0
    assert (
        fraser.Manifest.model_validate_json((root / "manifest.json").read_text()).pages[0].page == 1
    )


def test_a_stop_during_a_download_removes_the_temp_file_and_records_nothing(
    two_issues, monkeypatch
):
    root, _ = two_issues

    def interrupted(url: str, part: Path):
        part.write_bytes(b"%PDF-1.4 only the first few bytes")
        fraser._STOP.set()
        fraser._check_stop()

    monkeypatch.setattr(fraser, "_fetch_pdf", interrupted)
    assert fraser.ingest(root, log=lambda line: None) == 130
    assert leftovers(root) == []
    assert not list((root / "pdf").glob("*.pdf"))
    assert not (root / "sources.json").exists()


@pytest.mark.parametrize("damage", ["short", "not a pdf", "empty"])
def test_a_download_that_is_short_or_not_a_pdf_never_reaches_its_final_name(
    two_issues, monkeypatch, damage
):
    root, _ = two_issues
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
    sources = fraser.Sources(
        title="t", publisher="p", title_url=fraser.TITLE_URL,
        rights=RIGHTS, files=[],
    )  # fmt: skip
    with pytest.raises(fraser.DownloadError):
        fraser.download_issue("1939-01", root, sources, lambda line: None)
    assert leftovers(root) == [] and not list((root / "pdf").glob("*.pdf"))
    assert not (root / "sources.json").exists()


def test_a_missing_or_truncated_page_is_rendered_again_and_complete_ones_are_left_alone(tmp_path):
    root = tmp_path / "real"
    (root / "pdf").mkdir(parents=True)
    image_pdf(root / "pdf" / fraser.pdf_name("1939-01"))
    assert fraser.render_issue("1939-01", root, lambda line: None) == (3, 0)
    pages = root / "pages" / "1939-01"
    untouched = (pages / "p001.jpg").stat().st_mtime_ns
    (pages / "p002.jpg").unlink()
    cut = (pages / "p003.jpg").read_bytes()
    (pages / "p003.jpg").write_bytes(cut[: len(cut) // 2])
    (pages / "p004.jpg.part").write_bytes(b"half a page")

    assert fraser._clear_temp_files(root) == 1
    assert fraser.render_issue("1939-01", root, lambda line: None) == (2, 1)
    assert (pages / "p001.jpg").stat().st_mtime_ns == untouched


def test_verify_notices_a_page_that_no_longer_matches_the_manifest(two_issues):
    root, _ = two_issues
    assert fraser.ingest(root, log=lambda line: None) == 0
    assert fraser.verify(root, log=lambda line: None) == 0
    shutil.copy(root / "pages" / "1939-01" / "p001.jpg", root / "pages" / "1939-01" / "p002.jpg")
    lines: list[str] = []
    assert fraser.verify(root, log=lines.append) == 1
    assert any("1939-01 p002" in line for line in lines)


def test_a_second_ingest_cannot_start_while_one_is_running(tmp_path):
    with fraser._lock(tmp_path), pytest.raises(SystemExit, match="already running"):
        fraser._lock(tmp_path).__enter__()
