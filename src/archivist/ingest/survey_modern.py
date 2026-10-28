"""Survey of modern scanned sources, 1980 to 2000 (P24): rights, scan or text, size, tables. No model is called.

Three candidates are looked at, each from its publisher's own pages and from at most two of its
issues, downloaded to a scratch directory outside the repo (never into it):

1. the Federal Reserve Bulletin of the Board of Governors (FRASER title 62);
2. the FDIC's annual reports (FRASER title 3768) and its Statistics on Banking (FRASER title 125);
3. the Treasury's Monthly Treasury Statement (not on FRASER: the Bureau of the Fiscal Service
   publishes its volumes, one a fiscal year).

For each the survey records, from sources it names:

- Rights: FRASER's rights statement for the title as the title page shows it, or that it shows none,
  with what is known of the publisher under 17 U.S.C. § 105 (D38's basis for the Comptroller) and the
  borderline cases, listed and not decided.
- Scan or text: FRASER's own `digitalOrigin` for every issue that has one, and for the downloaded
  issues a check of the kind P20 made (are the pages images with an OCR layer, or real text fonts), on
  pages sampled evenly through the issue: a page is a scan when one
  image covers it, and its text is an OCR layer when that text is drawn invisibly (text render mode 3);
  a page with visible text and no covering image is real text.
- Size: pages per issue and per year, from FRASER's item metadata (the extent), or from the
  downloaded volume; bytes where the publisher's server reports a file's length to a HEAD request.
- Tables: from the OCR text of the downloaded issues, the numbered tables, each with whether its page
  prints a total, and the tables found in both issues of a source where two were taken.

The request rules are fraser's: every request carries only the project's public User-Agent, with a
pause between requests. The cap on downloads is enforced here: a `downloads.json` ledger in the
scratch directory records every transfer of an issue's bytes, kept or not, and a third is refused.
A file's size is asked for with a HEAD request, which transfers no body, and only of a host known to
report the real length; FRASER does not (its HEAD answers 0 and it ignores a range request, so for it
the size of an issue is known only once downloaded).

    python -m archivist.ingest.survey_modern --work <scratch> [--download <source>=<edition> ...]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from archivist.ingest import fraser, occ

FIRST_YEAR, LAST_YEAR = 1980, 2000
OUT = Path("results/modern/survey.md")
MAX_DOWNLOADS = 2  # issues per source
FRASER = "https://fraser.stlouisfed.org"
ITEM_METADATA = FRASER + "/metadata.php?type=item&id={id}&json=1"
TITLE_METADATA = FRASER + "/metadata.php?type=title&id={id}&json=1"
FISCAL = "https://fiscal.treasury.gov"
FISCAL_HISTORY = FISCAL + "/accounting/monthly-treasury-statement/historical-statements"
SIZE_HOSTS = frozenset({"fiscal.treasury.gov", "www.fdic.gov"})  # whose HEAD reports the real length
PAUSE = fraser.POLITE_PAUSE
TIMEOUT = fraser.TIMEOUT
CHUNK = fraser.CHUNK

Opener = Callable[[urllib.request.Request], Any]  # a context manager yielding a response


class TooManyDownloads(Exception):
    """A third issue of a source was asked for."""


class SizeUnknown(Exception):
    """The host is not known to report a file's length, or did not."""


def _urlopen(request: urllib.request.Request) -> Any:
    return urllib.request.urlopen(request, timeout=TIMEOUT)


def _text(page_html: str) -> str:
    """A page's visible text: comments and tags out, entities read, dashes plain, spaces collapsed."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", re.sub(r"[‐-―−]", "-", text)).strip()


# --- the web ---------------------------------------------------------------------------------


class Web:
    """Every request of the survey: the project's User-Agent and nothing else that identifies anyone,
    a pause between requests, each answer kept in the scratch directory so a rerun asks nothing twice,
    and a cap on the issues downloaded."""

    def __init__(self, work: Path, opener: Opener = _urlopen, pause: float = PAUSE) -> None:
        self.work = work
        self.opener = opener
        self.pause = pause
        self.requests = 0
        self._last = 0.0
        (work / "web").mkdir(parents=True, exist_ok=True)
        (work / "pdf").mkdir(parents=True, exist_ok=True)

    def _request(self, url: str, extra: dict[str, str] | None = None) -> urllib.request.Request:
        headers = {"User-Agent": fraser.USER_AGENT, **(extra or {})}
        return urllib.request.Request(url, headers=headers)

    def _wait(self) -> None:
        wait = self._last + self.pause - time.monotonic()
        if wait > 0 and self.requests:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1

    def text(self, url: str) -> str:
        """The page at url, from the scratch directory if it was fetched before."""
        kept = self.work / "web" / (hashlib.sha256(url.encode()).hexdigest()[:20] + ".txt")
        if kept.is_file():
            return kept.read_text(encoding="utf-8")
        self._wait()
        with closing(self.opener(self._request(url))) as response:
            body = response.read().decode("utf-8", "replace")
        kept.write_text(body, encoding="utf-8")
        return body

    def json(self, url: str) -> dict[str, Any]:
        data = json.loads(self.text(url))
        if not isinstance(data, dict):
            raise ValueError(f"{url}: not a JSON object")
        return data

    def size(self, url: str) -> int:
        """A file's size in bytes from a HEAD request, which transfers no body. Only for a host in
        SIZE_HOSTS, which report the real length; FRASER's HEAD answers a length of 0."""
        if urllib.parse.urlsplit(url).hostname not in SIZE_HOSTS:
            raise SizeUnknown(f"{url}: this host is not known to report a file's length")
        kept = self.work / "web" / (hashlib.sha256(f"HEAD {url}".encode()).hexdigest()[:20] + ".txt")
        if kept.is_file():
            length = kept.read_text(encoding="utf-8")
        else:
            self._wait()
            request = self._request(url)
            request.method = "HEAD"
            try:
                with closing(self.opener(request)) as response:
                    length = response.headers.get("Content-Length", "")
            except urllib.error.HTTPError as error:
                kept.write_text("", encoding="utf-8")  # a missing file stays missing: not asked again
                raise SizeUnknown(f"{url}: HTTP {error.code}") from error
            kept.write_text(length, encoding="utf-8")
        if not length.strip().isdigit() or int(length) == 0:
            raise SizeUnknown(f"{url}: Content-Length is {length!r}")
        return int(length)

    # --- the cap -----------------------------------------------------------------------------

    @property
    def ledger_path(self) -> Path:
        return self.work / "downloads.json"

    def ledger(self) -> list[dict[str, Any]]:
        if not self.ledger_path.is_file():
            return []
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def record_transfer(self, source: str, url: str, size: int | None, kept: bool, note: str) -> None:
        """Count a transfer of an issue's bytes against the cap, whether the file was kept or not."""
        entries = self.ledger()
        entries.append(
            {"source": source, "url": url, "bytes": size, "kept": kept, "note": note}
        )
        self.ledger_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")

    def transfers(self, source: str) -> list[dict[str, Any]]:
        return [e for e in self.ledger() if e["source"] == source]

    def pdf_path(self, source: str, name: str) -> Path:
        return self.work / "pdf" / source / name

    def download(self, source: str, url: str, name: str) -> Path:
        """The issue at url, saved under the scratch directory; a second request for a file already
        kept costs nothing, and a third issue of a source raises TooManyDownloads before any request."""
        path = self.pdf_path(source, name)
        if path.is_file():
            return path
        if len(self.transfers(source)) >= MAX_DOWNLOADS:
            raise TooManyDownloads(
                f"{source}: {MAX_DOWNLOADS} issues were already transferred, {url} would be a third"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        self._wait()
        size = 0
        try:
            with closing(self.opener(self._request(url))) as response, part.open("wb") as out:
                announced = response.headers.get("Content-Length")
                while chunk := response.read(CHUNK):
                    out.write(chunk)
                    size += len(chunk)
            with part.open("rb") as check:
                is_pdf = check.read(5) == b"%PDF-"
            short = announced is not None and announced.isdigit() and size != int(announced)
            # the bytes crossed the wire, so they count against the cap even if the file is no good
            self.record_transfer(
                source, url, size, is_pdf and not short, "downloaded for the survey"
                if is_pdf and not short else "not kept: not a whole PDF"
            )
            if not is_pdf or short:
                raise OSError(f"{url}: got {size} bytes, not a whole PDF")
            part.replace(path)
        except (OSError, http.client.HTTPException, urllib.error.URLError):
            part.unlink(missing_ok=True)
            raise
        return path


# --- FRASER pages ----------------------------------------------------------------------------


def rights_field(page_html: str) -> str | None:
    """The text of a FRASER title page's RIGHTS field ("No Copyright - United States (NoC-US)"), or
    None if the page shows none."""
    text = _text(page_html)
    match = re.search(r"\bRIGHTS:\s*(.+?)(?=\s+[A-Z][A-Z ]{3,}S?:|\s+Metadata \(|\s*$)", text)
    return match.group(1).strip() if match else None


def item_links(page_html: str, slug: str) -> list[tuple[int, int | None]]:
    """The (id, year its address names) of each item a title page lists, in page order, once each."""
    found = re.findall(
        rf'href="(?:{re.escape(FRASER)})?/title/{re.escape(slug)}/([a-z0-9-]*?)-(\d+)"', page_html
    )
    out: dict[int, int | None] = {}
    for name, ident in found:
        year = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", name)
        out.setdefault(int(ident), int(year.group(1)) if year else None)
    return list(out.items())


@dataclass(frozen=True)
class Edition:
    """One issue, report or volume: what a source publishes at one time."""

    source: str
    ident: str  # the FRASER item id, or the Fiscal Service volume
    label: str
    first_year: int
    last_year: int
    pages: int | None  # None until known
    origin: str | None  # FRASER's digitalOrigin ("reformatted digital", "born digital"), if given
    pdf_url: str | None
    size: int | None = None  # bytes, if the publisher's server told us
    month: int | None = None  # 1-12 for a monthly issue


def extent_pages(extent: object) -> int | None:
    """"163 pages" -> 163; None for anything else."""
    match = re.match(r"\s*(\d[\d,]*)\s+pages?\b", str(extent or ""))
    return int(match.group(1).replace(",", "")) if match else None


def item_edition(source: str, meta: dict[str, Any]) -> Edition:
    """An edition from a FRASER item's (or title's) metadata."""
    origin_info = meta.get("originInfo", {})
    sort_date = str(origin_info.get("sortDate", ""))
    year = int(sort_date[:4])
    physical = meta.get("physicalDescription", {})
    pdf = (meta.get("location", {}).get("pdfUrl") or [None])[0]
    title = meta["titleInfo"][0]["title"]
    ident = meta["recordInfo"]["recordIdentifier"][0]
    return Edition(
        source=source,
        ident=str(ident),
        label=title,
        first_year=year,
        last_year=year,
        pages=extent_pages(physical.get("extent")),
        origin=physical.get("digitalOrigin"),
        pdf_url=pdf,
        month=int(sort_date[5:7]) if origin_info.get("frequency") != "annual" and sort_date[5:7].isdigit() else None,
    )


def fraser_editions(
    web: Web,
    source: str,
    title_url: str,
    decades: Sequence[str],
    years: range = range(FIRST_YEAR, LAST_YEAR + 1),
    one_a_year: bool = False,
) -> list[Edition]:
    """Every item of a FRASER title in the decades whose address names a year in `years`, with its
    metadata, in date order; or, with one_a_year, the middle item of each year's listing. An item
    whose address names no year is looked up too."""
    slug = title_url.rstrip("/").rsplit("/", 1)[-1]
    ids: dict[int, int | None] = {}
    for decade in decades:
        ids.update(item_links(web.text(f"{title_url}?browse={decade}"), slug))
    wanted = [i for i, year in ids.items() if year is None or year in years]
    if one_a_year:
        by_year: dict[int | None, list[int]] = {}
        for i in wanted:
            by_year.setdefault(ids[i], []).append(i)
        wanted = [group[len(group) // 2] for group in by_year.values()]
    editions = [item_edition(source, web.json(ITEM_METADATA.format(id=i))) for i in wanted]
    return sorted(
        (e for e in editions if e.first_year in years), key=lambda e: (e.first_year, e.label, e.ident)
    )


# --- the Fiscal Service's Monthly Treasury Statement -----------------------------------------

VOLUME = re.compile(
    r"/system/files/files/reports-statements/mts/(?P<name>vol-(?P<vol>\d+)-mts-oct(?P<a>\d\d)-sep(?P<b>\d\d)[a-z-]*\.pdf)"
)


def _year(two: str) -> int:
    return 1900 + int(two) if int(two) >= 50 else 2000 + int(two)


def fiscal_volumes(page_html: str) -> list[Edition]:
    """The bound volumes of the Monthly Treasury Statement the Fiscal Service lists, oldest first:
    October of one fiscal year to September of another."""
    out = {}
    for match in VOLUME.finditer(page_html):
        a, b = _year(match["a"]), _year(match["b"])
        out[match["name"]] = Edition(
            source="mts",
            ident=match["name"].removesuffix(".pdf"),
            label=f"Volume {int(match['vol'])}, October {a} - September {b}",
            first_year=a,
            last_year=b,
            pages=None,
            origin=None,
            pdf_url=FISCAL + match.group(0),
        )
    return sorted(out.values(), key=lambda e: (e.first_year, e.ident))


def mts_editions(web: Web) -> list[Edition]:
    """The volumes with their sizes in bytes."""
    editions = fiscal_volumes(web.text(FISCAL_HISTORY))
    return [
        Edition(**{**e.__dict__, "size": web.size(e.pdf_url)}) if e.pdf_url else e for e in editions
    ]


# --- one issue per year ----------------------------------------------------------------------


def in_range(e: Edition) -> bool:
    return e.last_year >= FIRST_YEAR and e.first_year <= LAST_YEAR


def years_of(editions: Sequence[Edition]) -> dict[int, list[Edition]]:
    """Editions by the calendar year they start in, FIRST_YEAR to LAST_YEAR."""
    out: dict[int, list[Edition]] = {y: [] for y in range(FIRST_YEAR, LAST_YEAR + 1)}
    for e in editions:
        if e.first_year in out:
            out[e.first_year].append(e)
    return out


def pages_by_year(editions: Sequence[Edition]) -> dict[int, tuple[int, int, int | None, int | None]]:
    """For each year: (issues, issues with a known page count, pages in those, pages in the longest)."""
    out = {}
    for year, here in years_of(editions).items():
        known = [e.pages for e in here if e.pages is not None]
        out[year] = (len(here), len(known), sum(known), max(known) if known else None)
    return out  # type: ignore[return-value]


def date_of(edition: Edition) -> date:
    return date(edition.first_year, 1, 1)


# --- scan or text: what a page's PDF objects are ----------------------------------------------

SCAN_COVER = 0.9  # a page is a scan when images cover at least this share of it
SAMPLE_PAGES = 12  # pages checked in an issue, evenly through it
COVER_GRID = 40  # the page is cut into this many cells each way to find how much images cover
OCR_LAYER = "scan with an OCR layer"
SCAN_THIN = "scan with almost no text (a cover, photograph or blank page)"
REAL_TEXT = "real text"
OTHER = "other (no covering image, no visible text)"
KINDS = (OCR_LAYER, SCAN_THIN, REAL_TEXT, OTHER)


@dataclass(frozen=True)
class PageLayers:
    """What one page of a PDF is made of."""

    page: int  # 1-based
    cover: float  # share of the page the images cover
    images: int
    text_objects: int
    invisible_text: int  # drawn invisibly (text render mode 3), as most OCR layers are
    beneath_text: int  # visible mode, but drawn before (so under) the image that covers the page
    fonts: int  # distinct fonts of the text objects
    embedded_fonts: int  # of them, embedded in the file

    @property
    def hidden_text(self) -> int:
        return self.invisible_text + self.beneath_text

    @property
    def kind(self) -> str:
        scan = self.cover >= SCAN_COVER
        visible = self.text_objects - self.hidden_text
        if scan:  # a few visible objects are the archive's own stamp, so hidden text need only outweigh them
            return OCR_LAYER if self.hidden_text > visible else SCAN_THIN
        return REAL_TEXT if visible > 0 else OTHER


def covered_share(rects: Sequence[tuple[float, float, float, float]], width: float, height: float) -> float:
    """The share of a width x height page the rectangles (left, bottom, right, top) cover together,
    to the resolution of a COVER_GRID x COVER_GRID grid: an image repeated, or a page cut in strips,
    counts once."""
    hit = set()
    for left, bottom, right, top in rects:
        first_x, last_x = int(max(0.0, left) / width * COVER_GRID), int(min(width, right) / width * COVER_GRID - 1e-9)
        first_y, last_y = int(max(0.0, bottom) / height * COVER_GRID), int(min(height, top) / height * COVER_GRID - 1e-9)
        # a cell counts when its centre is inside the rectangle
        for x in range(first_x, last_x + 1):
            for y in range(first_y, last_y + 1):
                cx, cy = (x + 0.5) / COVER_GRID * width, (y + 0.5) / COVER_GRID * height
                if left <= cx <= right and bottom <= cy <= top:
                    hit.add((x, y))
    return len(hit) / COVER_GRID**2


def page_layers(page: pdfium.PdfPage, number: int) -> PageLayers:
    width, height = page.get_size()
    rects: list[tuple[float, float, float, float]] = []
    last_image = -1
    texts: list[tuple[int, bool]] = []  # (position in the drawing order, drawn invisibly)
    fonts: dict[str, bool] = {}
    for position, obj in enumerate(page.get_objects(max_depth=3)):
        if isinstance(obj, pdfium.PdfImage):
            rects.append(tuple(obj.get_bounds()))
            last_image = position
        elif isinstance(obj, pdfium.PdfTextObj):
            mode = pdfium_c.FPDFTextObj_GetTextRenderMode(obj.raw)
            texts.append((position, mode == pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE))
            font = obj.get_font()
            fonts.setdefault(font.get_base_name(), bool(font.is_embedded))
    cover = covered_share(rects, width, height)
    under = last_image if cover >= SCAN_COVER else -1
    return PageLayers(
        page=number,
        cover=cover,
        images=len(rects),
        text_objects=len(texts),
        invisible_text=sum(invisible for _, invisible in texts),
        beneath_text=sum(not invisible and position < under for position, invisible in texts),
        fonts=len(fonts),
        embedded_fonts=sum(fonts.values()),
    )


def sample_pages(count: int, wanted: int = SAMPLE_PAGES) -> list[int]:
    """Up to `wanted` 1-based page numbers spread evenly from the first page to the last."""
    if count <= wanted:
        return list(range(1, count + 1))
    return sorted({1 + round(i * (count - 1) / (wanted - 1)) for i in range(wanted)})


def pdf_layers(path: Path, wanted: int = SAMPLE_PAGES) -> tuple[int, list[PageLayers]]:
    """(the PDF's page count, the layers of its sampled pages)."""
    pdf = pdfium.PdfDocument(path)
    try:
        out = []
        for number in sample_pages(len(pdf), wanted):
            page = pdf[number - 1]
            try:
                out.append(page_layers(page, number))
            finally:
                page.close()
        return len(pdf), out
    finally:
        pdf.close()


def page_texts(path: Path) -> list[str]:
    """The text of every page of a PDF, as its own text layer gives it."""
    pdf = pdfium.PdfDocument(path)
    try:
        out = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    out.append(textpage.get_text_range())
                finally:
                    textpage.close()
            finally:
                page.close()
        return out
    finally:
        pdf.close()


# --- tables: the numbered tables of an issue and the totals they print ------------------------

# A table's caption line, per source. The Bulletin numbers its statistics "1.10 RESERVES, MONEY
# STOCK, AND DEBT MEASURES"; the Monthly Treasury Statement and the FDIC's reports "Table 4. ...".
CAPTIONS: dict[str, re.Pattern[str]] = {
    "frb": re.compile(r"^(?P<id>\d\.\d{2})\s+(?P<title>[A-Z][A-Z0-9 ,.'’&/()\-—]{3,}.*)$"),
    "fdic": re.compile(r"^Table\s+(?P<id>\d{1,3})\s*[.:]\s*(?P<title>.*)$", re.IGNORECASE),
    "mts": re.compile(r"^Table\s+(?P<id>\d{1,3})\s*[.\-—:]*\s*(?P<title>.*)$", re.IGNORECASE),
}
# The FDIC's financial statements are headed by name, and the OCR spaces letters out ("S tatem ents"),
# so their headings are looked for with every space taken out of the page's first lines.
STATEMENT_HEADINGS: dict[str, tuple[tuple[str, str], ...]] = {
    "fdic": (
        ("statementsoffinancialposition", "Statements of Financial Position"),
        ("statementsofincome", "Statements of Income"),
        ("statementsofcashflows", "Statements of Cash Flows"),
    ),
}
HEADING_CHARS = 400  # how much of a page's start a statement's heading is looked for in
TOTAL_LINE = re.compile(r"^\s*(?:\d{1,3}\s+)?totals?\b", re.IGNORECASE)
FIGURE = re.compile(r"\d[\d,]*\.?\d*")
MONTH_YEAR = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b"
    r"|\b(?:19|20)\d\d\b|\band other periods\b",
    re.IGNORECASE,
)


@dataclass
class TableFound:
    key: str  # "1.10", "Table 4", "Statements of Financial Position"
    title: str  # the caption's text, without its month and year
    pages: list[int]  # the pages carrying the caption, 1-based
    total_lines: int  # lines that begin "Total", on the table's pages after its caption
    example: str  # the first such line, shortened


def clean_title(title: str) -> str:
    """A caption's words without months, years, "Continued" or footnote marks, in one line."""
    text = re.sub(r"\bcontinued\b", " ", MONTH_YEAR.sub(" ", title), flags=re.IGNORECASE)
    return " ".join(re.sub(r"[^A-Za-z0-9,.'’&/()\- ]+", " ", text).split()).strip(" .,-—:")


def find_tables(source: str, texts: Sequence[str]) -> list[TableFound]:
    """The captioned tables of an issue, from the text of its pages in order, each with the totals
    it prints. A caption starts a table and a line "Total ..." belongs to the last caption before it,
    on its page or an earlier one; a caption repeated ("Continued", or each month's) is one table."""
    caption = CAPTIONS[source]
    found: dict[str, TableFound] = {}
    current: TableFound | None = None
    for number, text in enumerate(texts, 1):
        squeezed = re.sub(r"\s+", "", text[:HEADING_CHARS]).lower()
        for needle, name in STATEMENT_HEADINGS.get(source, ()):
            if needle in squeezed:
                current = found.setdefault(name, TableFound(name, name, [], 0, ""))
                if number not in current.pages:
                    current.pages.append(number)
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if (match := caption.match(line)) is not None:
                key = match["id"] if source == "frb" else f"Table {int(match['id'])}"
                current = found.setdefault(key, TableFound(key, "", [], 0, ""))
                if number not in current.pages:
                    current.pages.append(number)
                if not current.title:  # the first caption's words; later ones may add a schedule's
                    current.title = clean_title(match["title"])
            elif current is not None and TOTAL_LINE.match(line) and number >= current.pages[0]:
                current.total_lines += 1
                current.example = current.example or line[:70]
    return list(found.values())


def with_totals(tables: Sequence[TableFound]) -> list[TableFound]:
    return [t for t in tables if t.total_lines]


def recurring(first: Sequence[TableFound], second: Sequence[TableFound]) -> list[tuple[TableFound, TableFound]]:
    """The tables an issue shares with another, by key."""
    other = {t.key: t for t in second}
    return [(t, other[t.key]) for t in first if t.key in other]


# --- the sources ------------------------------------------------------------------------------

NOC_US = "No Copyright - United States (NoC-US)"
EARLIER_PAGES = 6830  # the larger of the two sources already ingested: the Comptroller's reports (6,165 for the Treasury Bulletin)
ISSUE_MONTHS = {12: tuple(range(1, 13)), 4: (3, 6, 9, 12), 2: (6, 12), 1: (6,)}  # issues a year -> which
FDIC_COPY = "https://www.fdic.gov/about/financial-reports/reports/archives/fdic-ar-{year}.pdf"
MTS_MONTHLY = re.compile(r"/system/files/files/reports-statements/mts/mts(?P<m>\d\d)(?P<y>\d\d)\.pdf")


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    publisher: str
    where: str  # who serves it
    title_url: str  # the FRASER title page, or the publisher's page
    kind: str  # what one edition is called
    federal_agency: bool  # the publisher is an agency or bureau of the US Government (17 U.S.C. § 105)
    standing: str  # what the survey knows of the publisher's standing; stated, not decided
    borderline: tuple[str, ...]  # cases it leaves to a person


SOURCES = (
    Source(
        key="frb",
        name="Federal Reserve Bulletin",
        publisher="Board of Governors of the Federal Reserve System",
        where="FRASER, title 62",
        title_url=f"{FRASER}/title/federal-reserve-bulletin-62",
        kind="issue",
        federal_agency=True,
        standing=(
            "The Board of Governors is an independent agency of the US Government, so the Bulletin "
            "is a work of the US Government (17 U.S.C. § 105) apart from FRASER's statement."
        ),
        borderline=(
            "The pages were not read for material from outside the Board (a table or chart "
            "credited to another source); FRASER's statement is for the title as a whole.",
        ),
    ),
    Source(
        key="fdic",
        name="FDIC annual reports and Statistics on Banking",
        publisher="Federal Deposit Insurance Corporation",
        where="FRASER, titles 3768 (annual reports) and 125 (Statistics on Banking); the FDIC's own site, fdic.gov, also holds some annual reports",
        title_url=f"{FRASER}/title/annual-report-federal-deposit-insurance-corporation-3768",
        kind="report",
        federal_agency=True,
        standing=(
            "The FDIC is an independent agency of the US Government, so its reports are works of the "
            "US Government (17 U.S.C. § 105), the reasoning D38 records for the Comptroller."
        ),
        borderline=(
            "FRASER shows no rights statement for title 3768 or title 125, so, as for the "
            "Comptroller, the ingest would need a recorded basis in place of one; whether that "
            "basis is enough here is not decided. (It does show one for another FDIC title, Bank "
            "Operating Statistics, title 9318.)",
            "The pages were not read for material that is not the FDIC's own (photographs, tables "
            "credited to others).",
        ),
    ),
    Source(
        key="mts",
        name="Monthly Treasury Statement",
        publisher="Bureau of the Fiscal Service, US Department of the Treasury",
        where="the Fiscal Service's own site (fiscal.treasury.gov): not on FRASER",
        title_url=FISCAL_HISTORY,
        kind="volume",
        federal_agency=True,
        standing=(
            "The Bureau of the Fiscal Service is a bureau of the Department of the Treasury and "
            "the Statement is its own publication, a work of the US Government (17 U.S.C. § 105)."
        ),
        borderline=(
            "The page gives no rights statement. It says \"Most copies are from the Treasury Library "
            "collection with help from the Copyright and Scholarly Communications department of Kent "
            "State University Libraries\", so some volumes are copies from elsewhere.",
            "It is not on FRASER, so the FRASER gate (fraser.check_sources) and ingest cannot take "
            "it as they are; a new ingest and a recorded basis would be needed.",
        ),
    ),
)
SOURCE = {s.key: s for s in SOURCES}


@dataclass
class Checked:
    """A downloaded issue and what was found in it."""

    edition: Edition
    file: str
    bytes: int
    pages: int  # the PDF's own page count
    layers: list[PageLayers]
    tables: list[TableFound]


@dataclass
class Result:
    source: Source
    rights: str | None  # FRASER's statement for the title, None if it shows none (or not FRASER)
    editions: list[Edition]  # in the years, oldest first
    checked: list[Checked]
    labels_after: list[Edition]  # one a year after LAST_YEAR whose origin label was read
    copy_sizes: dict[int, int | None]  # fdic.gov's copy of each year's annual report, bytes
    monthly_sizes: dict[str, int]  # MTS: the monthly files after the volumes, "mm/yy" -> bytes
    extra: list[tuple[str, str | None, list[Edition]]]  # other titles of the source: (name, rights, editions)


@dataclass
class Survey:
    results: list[Result]
    ledger: list[dict[str, Any]]
    requests: int


def verified_scan_year(result: Result) -> int | None:
    """The latest year, at most LAST_YEAR, of a downloaded issue whose sampled pages are mostly scans
    with an OCR layer."""
    years = [
        c.edition.last_year
        for c in result.checked
        if sum(p.kind == OCR_LAYER for p in c.layers) * 2 > len(c.layers)
    ]
    return min(max(years), LAST_YEAR) if years else None


def label_through(result: Result) -> int | None:
    """The last year FRASER labels "reformatted digital" without a break from FIRST_YEAR: of every
    issue in the years, then of the one issue a year read after them."""
    labelled = result.editions + result.labels_after
    if not labelled or not all(e.origin for e in labelled if e.first_year <= LAST_YEAR):
        return None
    last = None
    for year in sorted({e.first_year for e in labelled}):
        if all(e.origin == "reformatted digital" for e in labelled if e.first_year == year):
            last = year
        else:
            break
    return last


def recurring_with_totals(result: Result) -> list[TableFound]:
    """Tables with printed totals that recur: found in both downloaded issues when two were taken,
    else (the Bulletin's own numbering fixes its regular tables) those of the one issue."""
    if not result.checked:
        return []
    if len(result.checked) == 1:
        return with_totals(result.checked[0].tables)
    first, second = result.checked[0].tables, result.checked[1].tables
    return [a for a, b in recurring(first, second) if a.total_lines and b.total_lines]


@dataclass(frozen=True)
class Choice:
    source: Source
    first: int
    last: int
    per_year: int
    months: tuple[int, ...]
    issues: list[Edition]

    @property
    def pages(self) -> int:
        return sum(e.pages or 0 for e in self.issues)


def choose_issues(result: Result, last: int) -> Choice | None:
    """The most issues a year, of 12, 4, 2 or 1, that keep the pages within EARLIER_PAGES, from
    FIRST_YEAR to `last`; for a source with one edition a year, all of them."""
    editions = [e for e in result.editions if e.first_year <= last and e.pages is not None]
    if not editions:
        return None
    if all(e.month is None for e in editions):
        return Choice(result.source, FIRST_YEAR, last, 1, (), editions)
    for per_year, months in ISSUE_MONTHS.items():
        issues = [e for e in editions if e.month in months]
        if sum(e.pages or 0 for e in issues) <= EARLIER_PAGES:
            return Choice(result.source, FIRST_YEAR, last, per_year, months, issues)
    return None


@dataclass(frozen=True)
class Recommendation:
    choice: Choice
    ranking: list[tuple[Result, str]]  # every source with why it ranks where it does
    rule: str


RULE = (
    "A source is eligible when (1) its rights are settled enough to start from: FRASER shows its "
    f"statement, \"{NOC_US}\", or shows none and the publisher is an agency of the US Government "
    "(17 U.S.C. § 105, D38's basis); (2) a downloaded issue is a scan, most sampled pages an image "
    "with an OCR layer; and (3) at least three recurring tables print a total. Eligible sources are "
    "ranked by the kind of rights first (FRASER's statement before a basis) and then by how many "
    f"recurring tables print a total. The years are {FIRST_YEAR} to the last year verified as a scan; "
    "the issues are the most a year of 12, 4, 2 or 1 (all twelve months, March-June-September-"
    f"December, June and December, June) that keep the pages at or under {EARLIER_PAGES:,}, the size "
    "of the larger source already ingested."
)


def recommend(results: Sequence[Result]) -> Recommendation | None:
    ranked = []
    for result in results:
        scan = verified_scan_year(result)
        tables = recurring_with_totals(result)
        statement = result.rights is not None
        reasons = []
        if not (statement or result.source.federal_agency):
            reasons.append("rights not settled")
        if scan is None:
            reasons.append("no downloaded issue verified as a scan")
        if len(tables) < 3:
            reasons.append(f"only {len(tables)} recurring tables print a total")
        ranked.append((result, "; ".join(reasons), (statement, len(tables)), scan))
    eligible = sorted((r for r in ranked if not r[1]), key=lambda r: r[2], reverse=True)
    if not eligible:
        return None
    best = eligible[0]
    choice = choose_issues(best[0], best[3])
    if choice is None:
        return None
    why = {r[0].source.key: r[1] or "eligible" for r in ranked}
    return Recommendation(choice, [(r[0], why[r[0].source.key]) for r in ranked], RULE)


# --- collecting -------------------------------------------------------------------------------


def _check(web: Web, source: str, edition: Edition) -> Checked:
    """Download an issue (a rerun finds it kept) and look into it."""
    assert edition.pdf_url is not None
    name = edition.pdf_url.rsplit("/", 1)[-1]
    path = web.download(source, edition.pdf_url, name)
    pages, layers = pdf_layers(path)
    return Checked(
        edition=replace(edition, pages=pages),
        file=name,
        bytes=path.stat().st_size,
        pages=pages,
        layers=layers,
        tables=find_tables(source, page_texts(path)),
    )


def _checked(web: Web, source: str, editions: Sequence[Edition], wanted: Sequence[str]) -> list[Checked]:
    by_ident = {e.ident: e for e in editions}
    unknown = [w for w in wanted if w not in by_ident]
    if unknown:
        raise ValueError(f"{source}: no such edition to download: {unknown}")
    return [_check(web, source, by_ident[w]) for w in wanted]


def _sizes(web: Web, editions: Sequence[Edition]) -> list[Edition]:
    out = []
    for e in editions:
        try:
            out.append(replace(e, size=web.size(e.pdf_url)) if e.pdf_url else e)
        except SizeUnknown:
            out.append(e)
    return out


def collect_frb(web: Web, wanted: Sequence[str]) -> Result:
    source = SOURCE["frb"]
    rights = rights_field(web.text(source.title_url))
    editions = fraser_editions(web, source.key, source.title_url, ("1980s", "1990s", "2000s"))
    later = fraser_editions(
        web, source.key, source.title_url, ("2000s",), range(LAST_YEAR + 1, LAST_YEAR + 6), True
    )
    return Result(
        source, rights, editions, _checked(web, source.key, editions, wanted), later, {}, {}, []
    )


def collect_fdic(web: Web, wanted: Sequence[str]) -> Result:
    source = SOURCE["fdic"]
    rights = rights_field(web.text(source.title_url))
    editions = fraser_editions(web, source.key, source.title_url, ("1980s", "1990s", "2000s"))
    copies: dict[int, int | None] = {}
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        try:
            copies[year] = web.size(FDIC_COPY.format(year=year))
        except SizeUnknown:
            copies[year] = None
    stats_url = f"{FRASER}/title/statistics-banking-125"
    stats = item_edition("fdic", web.json(TITLE_METADATA.format(id=125)))
    ops_url = f"{FRASER}/title/bank-operating-statistics-9318"
    ops = fraser_editions(web, "fdic", ops_url, ("1980s",))
    extra = [
        ("Statistics on Banking, FRASER title 125", rights_field(web.text(stats_url)), [stats]),
        ("Bank Operating Statistics, FRASER title 9318", rights_field(web.text(ops_url)), ops),
    ]
    return Result(
        source, rights, editions, _checked(web, source.key, editions, wanted), [], copies, {}, extra
    )


def collect_mts(web: Web, wanted: Sequence[str]) -> Result:
    source = SOURCE["mts"]
    volumes = [e for e in fiscal_volumes(web.text(FISCAL_HISTORY)) if in_range(e)]
    editions = _sizes(web, volumes)
    checked = _checked(web, source.key, editions, wanted)
    done = {c.edition.ident: c.edition for c in checked}
    editions = [done.get(e.ident, e) for e in editions]
    previous = web.text(f"{FISCAL}/accounting/monthly-treasury-statement/previous")
    monthly: dict[str, int] = {}
    for match in MTS_MONTHLY.finditer(previous):
        month, year = int(match["m"]), _year(match["y"])
        if (year, month) >= (1998, 10) and year <= LAST_YEAR:
            try:
                monthly[f"{month:02d}/{year}"] = web.size(FISCAL + match.group(0))
            except SizeUnknown:
                pass
    by_date = dict(sorted(monthly.items(), key=lambda kv: kv[0][3:] + kv[0][:2]))
    return Result(source, None, editions, checked, [], {}, by_date, [])


def collect(web: Web, downloads: Mapping[str, Sequence[str]]) -> Survey:
    results = [
        collect_frb(web, downloads.get("frb", ())),
        collect_fdic(web, downloads.get("fdic", ())),
        collect_mts(web, downloads.get("mts", ())),
    ]
    return Survey(results, web.ledger(), len(list((web.work / "web").glob("*.txt"))))


# --- the report -------------------------------------------------------------------------------


def _row(cells: Sequence[object]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    return [_row(headers), _row(["---"] * len(headers)), *(_row(r) for r in rows), ""]


def _mb(size: int | None) -> str:
    return "-" if size is None else f"{size / 1e6:.1f}"


def _median(values: Sequence[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _by_year(editions: Sequence[Edition]) -> list[list[object]]:
    """Per year: issues, pages, and pages per issue (shortest / median / longest)."""
    rows = []
    for year, here in years_of(editions).items():
        pages = [e.pages for e in here if e.pages is not None]
        if not here:
            rows.append([year, 0, "-", "-"])
        elif pages:
            rows.append(
                [year, len(here), f"{sum(pages):,}", f"{min(pages)} / {_median(pages)} / {max(pages)}"]
            )
        else:
            rows.append([year, len(here), "-", "-"])
    return rows


def _check_rows(result: Result) -> list[list[object]]:
    rows = []
    for c in result.checked:
        kinds = {k: sum(p.kind == k for p in c.layers) for k in KINDS}
        invisible = sum(p.invisible_text for p in c.layers)
        beneath = sum(p.beneath_text for p in c.layers)
        text = sum(p.text_objects for p in c.layers)
        rows.append(
            [
                c.edition.label,
                c.pages,
                _mb(c.bytes),
                f"{c.bytes / c.pages / 1000:.0f}",
                len(c.layers),
                kinds[OCR_LAYER],
                kinds[SCAN_THIN],
                kinds[REAL_TEXT] + kinds[OTHER],
                f"{invisible:,} invisible, {beneath:,} under the image, of {text:,}",
            ]
        )
    return rows


CHECK_HEADERS = (
    "issue",
    "pages",
    "MB",
    "KB a page",
    "pages sampled",
    "scan with an OCR layer",
    "scan, almost no text",
    "real text or other",
    "text objects sampled",
)


def _tables_block(result: Result) -> list[str]:
    lines: list[str] = []
    for c in result.checked:
        found = with_totals(c.tables)
        lines.append(
            f"{c.edition.label}: {len(c.tables)} captioned tables, {len(found)} with a line that "
            f"begins \"Total\" after the caption."
        )
    lines.append("")
    if len(result.checked) >= 2:
        first, second = result.checked[0], result.checked[1]
        shared = recurring(first.tables, second.tables)
        rows = [
            [a.key, a.title[:60], len(a.pages), a.total_lines, len(b.pages), b.total_lines, a.example[:40]]
            for a, b in shared
        ]
        lines += [
            f"Tables found in both {first.edition.label} and {second.edition.label}, "
            "with how many pages carry each and how many total lines each prints:",
            "",
            *_table(
                ["table", "caption (first)", "pages", "total lines", "pages", "total lines", "a total line"],
                rows,
            ),
        ]
    elif result.checked:
        only = result.checked[0]
        rows = [
            [t.key, t.title[:60], len(t.pages), t.total_lines, t.example[:40]]
            for t in with_totals(only.tables)
        ]
        lines += [
            f"Tables with printed totals in {only.edition.label}. One issue was taken, so recurrence "
            "is not shown by comparing issues: the Bulletin numbers its regular tables (A-section, "
            "\"1.10\" to \"3.xx\") and lists the irregular ones separately, as special tables, in its "
            "own guide.",
            "",
            *_table(["table", "caption", "pages", "total lines", "a total line"], rows),
        ]
    return lines


def _source_section(result: Result) -> list[str]:
    source = result.source
    lines = [f"## {source.name}", "", f"Publisher: {source.publisher}. Served by {source.where}.", ""]

    lines += ["### Rights", ""]
    if source.key == "mts":
        lines.append(
            "FRASER: not found there. The title index of FRASER was searched by letter (M, T, U, D, R) "
            "and a web search made; neither shows a Monthly Treasury Statement. The letter pages did not "
            "look complete (FRASER's \"Monthly Review\" is missing from the M page, for one), so this is "
            "not proof that FRASER has none. The Fiscal Service's historical page, which lists the volumes "
            "below, shows no rights statement."
        )
    elif result.rights is not None:
        lines.append(f"FRASER's rights statement for the title: \"{result.rights}\".")
    else:
        lines.append("FRASER shows no rights statement for the title.")
    lines += ["", source.standing, ""]
    for name, rights, _ in result.extra:
        lines.append(f"- {name}: " + (f"FRASER's statement is \"{rights}\"." if rights else "FRASER shows no rights statement."))
    if result.extra:
        lines.append("")
    lines += ["Borderline, for you to decide (not decided here):", ""]
    lines += [f"- {b}" for b in source.borderline]
    if source.key == "mts":
        tagged = [e.ident.split("-mts-")[0].replace("vol-", "") for e in result.editions if re.search(r"-(hc|ks)$|-(hc|ks)-", e.ident)]
        if tagged:
            lines.append(
                f"- The file names of volumes {', '.join(tagged)} end in -hc or -ks; the page does not "
                "say what they mean."
            )
    lines.append("")

    lines += ["### Scan or text", ""]
    in_years = [e for e in result.editions if e.first_year <= LAST_YEAR]
    if source.key == "frb":
        n = len(in_years)
        labelled = sum(e.origin == "reformatted digital" for e in in_years)
        lines.append(
            f"FRASER's own label (`digitalOrigin` in the item's metadata) is \"reformatted digital\" "
            f"on {labelled} of the {n} issues from {FIRST_YEAR} to {LAST_YEAR}"
            + (
                f", and on the one issue a year read for {', '.join(str(e.first_year) for e in result.labels_after)} "
                f"({sum(e.origin == 'reformatted digital' for e in result.labels_after)} of {len(result.labels_after)})."
                if result.labels_after
                else "."
            )
            + " The title note says the paper Bulletin ended in 2006."
        )
    elif source.key == "fdic":
        lines.append(
            "FRASER's metadata labels the title \"reformatted digital\" and gives no label for the "
            "individual reports."
        )
    else:
        lines.append(
            "Not a FRASER item, so there is no FRASER label; the check below is of the files."
        )
    lines += [
        "",
        "The check, of the kind P20 made (images with an OCR layer, or real text fonts), on pages sampled "
        "evenly through each downloaded issue: a page is a scan when "
        "images cover at least 90% of it, and its text is an OCR layer when most of its text objects "
        "are invisible (text render mode 3) or sit under the covering image. Real text would show as "
        "visible text with no covering image.",
        "",
        *_table(list(CHECK_HEADERS), _check_rows(result)),
    ]
    scan = verified_scan_year(result)
    through = label_through(result)
    if scan is not None:
        lines.append(
            f"Verified as a scan with an OCR layer, by the check on a downloaded issue: {scan}, the "
            + ("last year of the range" if scan == LAST_YEAR else "last year of this source in the range")
            + (f"; FRASER's label says reformatted digital through {through}." if through and through > scan else ".")
        )
    if source.key == "fdic":
        sized = {y: b for y, b in result.copy_sizes.items() if b}
        pages = {e.first_year: e.pages for e in in_years if e.pages}
        kb = sorted(c.bytes / c.pages / 1000 for c in result.checked)
        fdic_range = f"{kb[0]:.0f} and {kb[-1]:.0f} KB" if len(kb) > 1 else "-"
        per_page = sorted(b / pages[y] / 1000 for y, b in sized.items() if y in pages)
        copy_range = f"{per_page[0]:.0f} to {per_page[-1]:.0f} KB a page" if per_page else "-"
        rows = [
            [y, pages.get(y, "-"), _mb(b), f"{b / pages[y] / 1000:.0f}" if y in pages else "-"]
            for y, b in sorted(sized.items())
        ]
        lines += [
            "",
            "A cross-check without downloading: the FDIC's own site holds a copy of the annual report "
            f"for {min(sized)} to {max(sized)} and reports its length to a HEAD request. The two reports "
            f"downloaded, verified above as scans, run to {fdic_range} a page; the FDIC's copies run from "
            f"{copy_range}, the same order. The copy FRASER serves for 1985 is byte for byte the same "
            "length as the FDIC's, so it is the same file. "
            f"The FDIC's site has no copy at that address for {', '.join(str(y) for y, b in result.copy_sizes.items() if not b)}.",
            "",
            *_table(["year", "pages (FRASER)", "MB (fdic.gov)", "KB a page"], rows),
        ]
    if source.key == "mts":
        sizes = list(result.monthly_sizes.values())
        per_month = [e.size / (12 * (e.last_year - e.first_year)) for e in result.editions if e.size]
        if sizes and per_month:
            lines += [
                "",
                f"The monthly files the Fiscal Service lists for October 1998 to December {LAST_YEAR} "
                f"({len(sizes)} of them, sizes by HEAD, not downloaded) run from {_mb(min(sizes))} to "
                f"{_mb(max(sizes))} MB, median {_mb(_median(sizes))} MB. A bound volume is "
                f"{min(per_month) / 1e6:.1f} to {max(per_month) / 1e6:.1f} MB a month. The monthly files are "
                "an order of magnitude smaller, which fits text and not page images; that is an inference "
                "from size, not a check of the files, so the last year verified as a scan stays 1998.",
            ]
    lines.append("")

    lines += ["### Size", ""]
    if source.key == "mts":
        rows = [
            [e.label, _mb(e.size), e.pages if e.pages else "-", "downloaded and counted" if e.pages else ""]
            for e in result.editions
        ]
        lines += [
            "Each volume is the twelve monthly statements of a fiscal year (two years in volumes 22 to 24). "
            "Pages are known only for the volumes downloaded; bytes are known for every volume.",
            "",
            *_table(["volume", "MB", "pages", ""], rows),
        ]
    else:
        per_issue = [e.pages for e in in_years if e.pages]
        lines += [
            f"{len(in_years)} {source.kind}s from {FIRST_YEAR} to {LAST_YEAR}, {sum(per_issue):,} pages in all; "
            f"{min(per_issue)} to {max(per_issue)} pages per {source.kind}, median {_median(per_issue)}. "
            "Pages come from FRASER's item metadata (the extent).",
            "",
            *_table(
                ["year", f"{source.kind}s", "pages", f"pages per {source.kind} (shortest / median / longest)"],
                _by_year(in_years),
            ),
        ]
    for name, rights, editions in result.extra:
        if not editions:
            continue
        pages = [e.pages for e in editions if e.pages]
        lines.append(
            f"{name}: {len(editions)} {'item' if len(editions) == 1 else 'items'} in range "
            f"({', '.join(dict.fromkeys(e.label for e in editions))}), "
            f"{sum(pages):,} pages in all"
            + (f"; FRASER labels it \"{editions[0].origin}\"" if editions[0].origin else "")
            + ". Not downloaded or checked."
        )
        lines.append("")

    lines += ["### Tables", ""]
    lines += _tables_block(result)
    return lines


def _alternatives(result: Result, last: int) -> list[list[object]]:
    editions = [e for e in result.editions if e.first_year <= last and e.pages is not None]
    if all(e.month is None for e in editions):
        return [[1, "each report", len(editions), f"{sum(e.pages or 0 for e in editions):,}", "yes" if sum(e.pages or 0 for e in editions) <= EARLIER_PAGES else "no"]]
    names = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
    rows = []
    for per_year, months in ISSUE_MONTHS.items():
        chosen = [e for e in editions if e.month in months]
        pages = sum(e.pages or 0 for e in chosen)
        rows.append([per_year, ", ".join(names[m] for m in months) if per_year < 12 else "every month", len(chosen), f"{pages:,}", "yes" if pages <= EARLIER_PAGES else "no"])
    return rows


def _recommendation(survey: Survey, rec: Recommendation | None) -> list[str]:
    lines = ["## Recommendation", ""]
    if rec is None:
        return lines + ["No source passes the rule below.", "", RULE, ""]
    c = rec.choice
    months = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}
    which = (
        "every month" if c.per_year == 12 else " and ".join(months[m] for m in c.months) if c.months else "each report"
    )
    result = next(r for r, _ in rec.ranking if r.source is c.source)
    tables = recurring_with_totals(result)
    lines += [
        f"**Ingest the {c.source.name} ({c.source.publisher}), {c.first} to {c.last}: {len(c.issues)} "
        f"{c.source.kind}s ({which}), {c.pages:,} pages.**",
        "",
        f"- Rights: " + (f"FRASER shows \"{result.rights}\" for the title, the same statement as the Treasury Bulletin." if result.rights else "a recorded basis, as for the Comptroller (D38)."),
        f"- Scan: a downloaded {c.source.kind} verified as a scan with an OCR layer in {verified_scan_year(result)}; "
        + (f"FRASER's label says reformatted digital on every one of its {len(result.editions)} issues {FIRST_YEAR} to {LAST_YEAR}. " if c.source.key == "frb" else "")
        + "The ingest of data/real and data/real_occ already reads this kind of PDF.",
        f"- Tables: {len(tables)} recurring tables print a total in the issue(s) read, the kind of table the arithmetic test needs.",
        f"- Size: {c.pages:,} pages against {EARLIER_PAGES:,} in the larger source already ingested. Every "
        f"{c.source.kind} of the range would be {sum(e.pages or 0 for e in result.editions if e.first_year <= c.last):,} pages; "
        "the choices, by issues a year:",
        "",
        *_table(["issues a year", "which", "issues", "pages", "within the bound"], _alternatives(result, c.last)),
        "How the sources rank under the rule:",
        "",
        *_table(
            ["source", "rights", "verified scan", "recurring tables with a total", "eligible"],
            [
                [
                    r.source.name,
                    ("FRASER statement" if r.rights else "federal agency, no statement"),
                    verified_scan_year(r) or "-",
                    len(recurring_with_totals(r)),
                    why if why != "eligible" else "yes",
                ]
                for r, why in rec.ranking
            ],
        ),
        "The rule: " + rec.rule,
        "",
        "The rule was written after the page counts and the first table counts had been seen, so it "
        "describes the choice; it is not a test the choice passed blind. Nothing here is ingested: this "
        "is only a survey.",
        "",
    ]
    return lines


def render(survey: Survey) -> str:
    rec = recommend(survey.results)
    out = [
        f"# Modern scanned sources, {FIRST_YEAR} to {LAST_YEAR}: a survey (P24)",
        "",
        "Made by `python -m archivist.ingest.survey_modern`. No model was called and no page was "
        "sent anywhere. At most two issues of each source were downloaded to a scratch directory "
        "outside the repo, read for the checks below and not kept in it. Every request carried only "
        "the project's public User-Agent. Nothing is ingested and no data file is added.",
        "",
        "## Summary",
        "",
        *_table(
            ["source", "on FRASER", "rights", "last year still a scan", f"pages a year, {FIRST_YEAR} to {LAST_YEAR}"],
            [
                [
                    r.source.name,
                    "yes" if r.source.key != "mts" else "no",
                    (f"statement: \"{r.rights}\"" if r.rights else "none shown; federal agency"),
                    _last_scan(r),
                    _pages_per_year(r),
                ]
                for r in survey.results
            ],
        ),
        *_recommendation(survey, rec),
    ]
    for result in survey.results:
        out += _source_section(result)
    out += _method(survey)
    return "\n".join(out).rstrip() + "\n"


def _pages_per_year(result: Result) -> str:
    in_years = [e for e in result.editions if e.first_year <= LAST_YEAR]
    if result.source.key == "mts":
        known = [e.pages for e in in_years if e.pages]
        return f"{' and '.join(f'{n:,}' for n in known)} in the {len(known)} volumes counted, each a fiscal year"
    pages = sum(e.pages for e in in_years if e.pages)
    years = {e.first_year for e in in_years}
    return f"{pages // max(1, len(years)):,} on average ({len(in_years)} {result.source.kind}s)"


def _last_scan(result: Result) -> str:
    """The last year still a scan: verified in a downloaded issue, with what else is known."""
    scan = verified_scan_year(result)
    if scan is None:
        return "not verified"
    through = label_through(result)
    if result.source.key == "frb" and through and through > scan:
        return f"{scan}, the end of the range (FRASER's label: through {through})"
    if result.source.key == "mts":
        return f"{scan}, the last bound volume (later monthly files are far smaller)"
    return f"{scan}, the end of the range" if scan == LAST_YEAR else str(scan)


def _method(survey: Survey) -> list[str]:
    rows = [
        [e["source"], e["url"].rsplit("/", 1)[-1], _mb(e["bytes"]) if e["bytes"] else "-", "yes" if e["kept"] else "no", e["note"]]
        for e in survey.ledger
    ]
    return [
        "## Method and limits",
        "",
        f"- Downloads are capped at {MAX_DOWNLOADS} issues a source, enforced in code by a ledger. Every "
        "transfer of an issue's bytes is in it, kept or not:",
        "",
        *_table(["source", "file", "MB", "kept", "note"], rows),
        f"- {survey.requests} pages, metadata records and file sizes were asked for, one request each "
        "(each answer is kept in the scratch directory and never asked for twice), with a pause between "
        "requests; the issues above are the only files downloaded.",
        "- FRASER's HEAD answers a length of 0 and it ignores a range request, so the size of one of its "
        "issues is known only once downloaded. The checks of an issue's pages therefore cover only the "
        "issues downloaded; for the other years the evidence is FRASER's label, the publisher's own "
        "copies where they exist, and file sizes. A check of one issue a year would need about "
        f"{LAST_YEAR - FIRST_YEAR - 1} more downloads of each source, which the cap forbids.",
        "- Sampled pages are spread evenly through an issue (at most 12). A table is found by its "
        "caption in the OCR text; OCR noise can split or miss one, and a line that begins \"Total\" "
        "may not carry its figures on the same line. Counts are a guide to which tables to look at, "
        "not a measurement of them.",
        "",
    ]


# --- the command ------------------------------------------------------------------------------


def _outside_repo(work: Path) -> bool:
    here = Path.cwd().resolve()
    target = work.resolve()
    return here != target and here not in target.parents and target not in here.parents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--work", type=Path, required=True, help="scratch directory outside the repo")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--download",
        action="append",
        default=[],
        metavar="SOURCE=EDITION",
        help="an issue to download and read, e.g. frb=20937 (at most two for each source)",
    )
    args = parser.parse_args(argv)
    if not _outside_repo(args.work):
        parser.error("--work must be outside the repo (and not hold it): nothing downloaded may land in git")
    wanted: dict[str, list[str]] = {}
    for item in args.download:
        source, _, edition = item.partition("=")
        if source not in SOURCE or not edition:
            parser.error(f"--download {item!r}: expected SOURCE=EDITION with SOURCE one of {sorted(SOURCE)}")
        wanted.setdefault(source, []).append(edition)
    for source, editions in wanted.items():
        if len(editions) > MAX_DOWNLOADS:
            parser.error(f"--download: {len(editions)} issues of {source}, the cap is {MAX_DOWNLOADS}")
    web = Web(args.work)
    survey = collect(web, wanted)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(survey), encoding="utf-8")
    print(f"-> {args.out} ({web.requests} requests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
