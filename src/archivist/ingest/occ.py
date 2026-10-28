"""Annual Report of the Comptroller of the Currency from FRASER, title 56: download, render, record. No model ever reads these pages here.

    data/real_occ/pdf/<volume>_compcurr.pdf         the volume as FRASER serves it    (gitignored)
    data/real_occ/pages/<volume>/p<NNN>.jpg         every page at 200 dpi             (gitignored)
    data/real_occ/sources.json    where each PDF came from, when, its size and sha256, and the rights record
    data/real_occ/manifest.json   every rendered page: sha256, size, the PDF's own first lines, printed-totals counts
    data/real_occ/split.json      development and held-out years, fixed before any model run

The machinery is archivist.ingest.fraser's, pointed at a second title: resumable at any moment, a
PDF or page written to a .part file and renamed into place only when whole, the record written
before the rename, one ingest at a time, SIGINT and SIGTERM stopping at the next safe point, and
every request sent with the same User-Agent. What differs:

- A volume is one FRASER item. Its id is the year, plus -v1, -v2 where a year has several volumes.
  The item ids are fixed below; each PDF's address is read from its item's metadata (pdfUrl) at
  download time, since the addresses of 1915 to 1935 follow no pattern, and recorded in sources.json.
- FRASER shows no rights statement for this title (the Treasury Bulletin's title page does). The
  rights record is then an explicit basis: FRASER shows none, why the title may be used anyway
  (works of the US Government, 17 U.S.C. § 105) and the pages that were read. If FRASER ever shows a
  different statement, nothing is downloaded.
- The split is by year; both volumes of 1915 are held out together.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, Literal

import pypdfium2 as pdfium
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from archivist.ingest import fraser

TITLE_URL = "https://fraser.stlouisfed.org/title/annual-report-comptroller-currency-56"
TITLE_NAME = "Annual Report of the Comptroller of the Currency"
TITLE_ID = 56
ITEM_URL = TITLE_URL + "/{year}-{item}"
METADATA_URL = "https://fraser.stlouisfed.org/metadata.php?type=item&id={item}&json=1"
PDF_PREFIX = "https://fraser.stlouisfed.org/docs/"
DEFAULT_ROOT = Path("data/real_occ")

# volume id -> FRASER item id. One report every five years, 1905 to 1940; where a year has several
# volumes, all of them. The ids come from the title page's decade listings.
VOLUMES: dict[str, int] = {
    "1905": 19070,
    "1910": 19075,
    "1915-v1": 19130,
    "1915-v2": 19131,
    "1920-v1": 19140,
    "1920-v2": 19141,
    "1925": 19146,
    "1930": 19151,
    "1935": 19156,
    "1940": 19161,
}
DEVELOPMENT = ["1905", "1925"]
HELD_OUT = ["1910", "1915", "1920", "1930", "1935", "1940"]
SPLIT_NOTE = (
    "Development: 1905 and 1925. Held-out: 1910, 1915, 1920, 1930, 1935 and 1940; a year's volumes "
    "all go to the same side. Fixed before any model has seen a real page."
)

BASIS = (
    "The Office of the Comptroller of the Currency is a bureau of the US Department of the Treasury, "
    "so its annual reports are works of the US Government and are not subject to copyright in the "
    "United States (17 U.S.C. § 105). The 1905 to 1930 volumes are also in the public domain by "
    "age. FRASER's own pages for this title show no rights statement, so the "
    f"{fraser.RIGHTS_STATEMENT!r} the Treasury Bulletin carries cannot be recorded for it."
)
CITATIONS = ["17 U.S.C. § 105"]

# --- records ---------------------------------------------------------------------------------

Volume = Annotated[str, StringConstraints(pattern=r"^\d{4}(-v[1-9])?$")]
Year = Annotated[str, StringConstraints(pattern=r"^\d{4}$")]


class SourceFile(fraser.SourceFile):
    issue: Volume
    item_id: int  # the FRASER item the PDF was found from
    item_url: str
    metadata_url: str  # where `url` (the item's pdfUrl) was read


class Sources(fraser.Sources):
    files: list[SourceFile]


class IssueEntry(fraser.IssueEntry):
    issue: Volume


class PageEntry(fraser.PageEntry):
    """A page, with counts from the PDF's own OCR text for the survey (all zero when it has none)."""

    issue: Volume
    lines: int = Field(ge=0)  # non-empty lines of OCR text; a table's cells are mostly one per line
    figure_lines: int = Field(ge=0)  # of those, lines that are mostly digits
    total_lines: int = Field(ge=0)  # lines that begin "Total" or "Totals"
    resources_heading: bool  # a line that begins "Resources"
    liabilities_heading: bool  # a line that begins "Liabilities"


class Manifest(fraser.Manifest):
    issues: list[IssueEntry]
    pages: list[PageEntry]


class Split(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    development: list[Year]
    held_out: list[Year]
    note: str

    @model_validator(mode="after")
    def _disjoint_and_complete(self) -> Split:
        sides = [*self.development, *self.held_out]
        if len(sides) != len(set(sides)):
            dupes = sorted({y for y in sides if sides.count(y) > 1})
            raise ValueError(f"years listed more than once: {dupes}")
        if set(sides) != set(years()):
            raise ValueError(
                f"split does not cover the years exactly: missing {sorted(set(years()) - set(sides))}, "
                f"unknown {sorted(set(sides) - set(years()))}"
            )
        return self

    def side(self, volume: str) -> Literal["development", "held_out"]:
        return "development" if volume[:4] in self.development else "held_out"


FIGURE_SHARE = 0.5  # a line is a figure line if at least this share of its characters are digits
TOTAL = re.compile(r"totals?\b", re.IGNORECASE)
RESOURCES = re.compile(r"resources\b", re.IGNORECASE)
LIABILITIES = re.compile(r"liabilities\b", re.IGNORECASE)


def ocr_counts(text: str) -> dict[str, int | bool]:
    """What the survey counts in a page's OCR text: lines, figure lines, Total lines, two headings."""
    lines = [" ".join(raw.split()) for raw in re.split(r"\r\n|\r|\n", text)]
    lines = [line for line in lines if line]
    figures = 0
    for line in lines:
        compact = line.replace(" ", "")
        digits = sum(c.isdigit() for c in compact)
        figures += digits >= 2 and digits / len(compact) >= FIGURE_SHARE
    return {
        "lines": len(lines),
        "figure_lines": figures,
        "total_lines": sum(TOTAL.match(line) is not None for line in lines),
        "resources_heading": any(RESOURCES.match(line) for line in lines),
        "liabilities_heading": any(LIABILITIES.match(line) for line in lines),
    }


def _page_text(page: pdfium.PdfPage) -> str:
    textpage = page.get_textpage()
    try:
        return textpage.get_text_range()
    finally:
        textpage.close()


def years() -> list[str]:
    return sorted({volume[:4] for volume in VOLUMES})


def current_split() -> Split:
    return Split(development=DEVELOPMENT, held_out=HELD_OUT, note=SPLIT_NOTE)


def pdf_name(volume: str) -> str:
    return f"{volume}_compcurr.pdf"


def pdf_path(root: Path, volume: str) -> Path:
    return root / "pdf" / pdf_name(volume)


def item_url(volume: str) -> str:
    return ITEM_URL.format(year=volume[:4], item=VOLUMES[volume])


def metadata_url(volume: str) -> str:
    return METADATA_URL.format(item=VOLUMES[volume])


def check_sources(sources: Sources) -> list[str]:
    """Problems that make sources.json incomplete or inconsistent; empty when it is sound."""
    found = [f.issue for f in sources.files]
    problems = [
        f"sources.json lists {v} more than once" for v in sorted(set(found)) if found.count(v) > 1
    ]
    problems += [f"sources.json has no record of {v}" for v in VOLUMES if v not in found]
    problems += [f"sources.json lists unknown volume {v}" for v in found if v not in VOLUMES]
    for f in sources.files:
        if f.issue not in VOLUMES:
            continue
        if f.item_id != VOLUMES[f.issue]:
            problems.append(f"{f.issue}: item is {f.item_id}, not {VOLUMES[f.issue]}")
        if f.item_url != item_url(f.issue) or f.metadata_url != metadata_url(f.issue):
            problems.append(f"{f.issue}: item or metadata address is not the one for its item")
        if not (f.url.startswith(PDF_PREFIX) and f.url.lower().endswith(".pdf")):
            problems.append(f"{f.issue}: url is not a PDF under {PDF_PREFIX}")
    if sources.title_url != TITLE_URL:
        problems.append(f"title_url is not {TITLE_URL}")
    return problems + fraser.check_rights_record(sources.rights)


def check_manifest(manifest: Manifest) -> list[str]:
    """Problems that make the manifest incomplete or inconsistent; empty when it is sound."""
    problems: list[str] = []
    if [e.issue for e in manifest.issues] != list(VOLUMES):
        problems.append("manifest volumes are not the expected volumes, in order")
    counts = {e.issue: e.pages for e in manifest.issues}
    expected = [(v, n) for v in VOLUMES for n in range(1, counts.get(v, 0) + 1)]
    if [(p.issue, p.page) for p in manifest.pages] != expected:
        problems.append("manifest pages are not every page 1..n of every volume, in order")
    return problems


# --- rights and item metadata ------------------------------------------------------------------


def _text_of(page_html: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", page_html, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))


def check_rights(
    fetch: Callable[[str], str] | None = None,
) -> fraser.Rights | fraser.RecordedBasis:
    """Read the title page; return the rights record that lets the download go ahead.

    FRASER's own statement if the page now shows it; the recorded basis if it shows none; and
    RightsError, with nothing downloaded, if it shows any other statement or is not the title page.
    """
    page = (fetch or fraser._fetch_text)(TITLE_URL)
    today = datetime.now(UTC).date()
    if fraser.rights_statement_present(page):
        return fraser.Rights(
            statement=fraser.RIGHTS_STATEMENT, uri=fraser.RIGHTS_URI, checked=today
        )
    text = _text_of(page)
    if TITLE_NAME not in text:
        raise fraser.RightsError(
            f"{TITLE_URL} is not showing the title page of {TITLE_NAME!r}; nothing was downloaded. "
            "Check the page by hand before going on."
        )
    if re.search(r"\bRIGHTS\s*:", text) or "rightsstatements.org" in page:
        raise fraser.RightsError(
            f"{TITLE_URL} shows a rights statement other than {fraser.RIGHTS_STATEMENT!r}; "
            "nothing was downloaded. Check the title page by hand before going on."
        )
    return fraser.RecordedBasis(
        fraser_shows="no rights statement",
        basis=BASIS,
        citations=CITATIONS,
        checked=today,
        pages_checked=[TITLE_URL],
    )


def _item_pdf_url(volume: str, meta: dict[str, Any]) -> str:
    """The PDF address in an item's metadata, after checking that this is the item we think it is."""
    item_id = VOLUMES[volume]
    year, _, part = volume.partition("-v")
    try:
        found = {
            "item": [str(i) for i in meta["recordInfo"]["recordIdentifier"]],
            "title": [
                str(i)
                for rel in meta["relatedItem"]
                if rel.get("@type") == "parent"
                for i in rel["recordInfo"]["recordIdentifier"]
            ],
            "year": [str(y) for y in meta["originInfo"]["dateIssued"]],
            "part": meta["titleInfo"][0]["titlePartNumber"],
            "pdf": meta["location"]["pdfUrl"],
        }
        access = str(meta.get("accessCondition", ""))
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise fraser.DownloadError(f"item {item_id}: unexpected metadata ({exc!r})") from exc
    wanted = {
        "item": [str(item_id)],
        "title": [str(TITLE_ID)],
        "year": [year],
        "part": f"Volume {part}" if part else "",
    }
    for key, want in wanted.items():
        if found[key] != want:
            raise fraser.DownloadError(
                f"item {item_id} is not volume {volume}: its {key} is {found[key]!r}, not {want!r}"
            )
    if "rightsstatements.org" in access and fraser.RIGHTS_URI not in access:
        raise fraser.RightsError(
            f"item {item_id} shows a rights statement other than {fraser.RIGHTS_STATEMENT!r} "
            f"({access!r}); nothing was downloaded."
        )
    pdf = found["pdf"]
    if not (
        isinstance(pdf, list)
        and len(pdf) == 1
        and isinstance(pdf[0], str)
        and pdf[0].startswith(PDF_PREFIX)
        and pdf[0].lower().endswith(".pdf")
    ):
        raise fraser.DownloadError(f"item {item_id}: pdfUrl is not one PDF under {PDF_PREFIX}: {pdf!r}")
    return pdf[0]


def read_pdf_url(
    volume: str, log: Callable[[str], None], fetch: Callable[[str], str] | None = None
) -> str:
    """The volume's PDF address, read from its item's metadata."""
    url = metadata_url(volume)

    def attempt() -> dict[str, Any]:
        try:
            meta = json.loads((fetch or fraser._fetch_text)(url))
        except ValueError as exc:
            raise fraser.DownloadError(f"not JSON: {exc}") from exc
        if not isinstance(meta, dict):
            raise fraser.DownloadError("metadata is not a JSON object")
        return meta

    meta = fraser._retrying(volume, url, log, attempt, lambda: None)
    return _item_pdf_url(volume, meta)


# --- download and render -----------------------------------------------------------------------


def download_volume(
    volume: str,
    root: Path,
    sources: Sources,
    log: Callable[[str], None],
    fetch: Callable[[str], str] | None = None,
) -> Sources:
    """Read the item's metadata, fetch its PDF to a .part file, check it, record it, then rename it."""
    url = read_pdf_url(volume, log, fetch)
    fraser._pause(fraser.POLITE_PAUSE)
    updated = sources

    def record(resolved: str, size: int, sha: str) -> None:
        nonlocal updated
        entry = SourceFile(
            issue=volume,
            url=url,
            resolved_url=resolved,
            retrieved=datetime.now(UTC).date(),
            size_bytes=size,
            sha256=sha,
            item_id=VOLUMES[volume],
            item_url=item_url(volume),
            metadata_url=metadata_url(volume),
        )
        order = list(VOLUMES)
        files = sorted(
            [*(f for f in sources.files if f.issue != volume), entry],
            key=lambda f: order.index(f.issue),
        )
        updated = sources.model_copy(update={"files": files})
        fraser._write_record(root / "sources.json", updated)

    fraser._download(url, pdf_path(root, volume), volume, log, record)
    return updated


def render_volume(volume: str, root: Path, log: Callable[[str], None]) -> tuple[int, int]:
    """Render every page that is not already on disk; return (rendered now, already there)."""
    return fraser._render_pdf(pdf_path(root, volume), root, volume, log)


def build_manifest(root: Path) -> Manifest:
    """Read every rendered page back from disk. Raises FileNotFoundError if any is missing."""
    issues: list[IssueEntry] = []
    pages: list[PageEntry] = []
    for volume in VOLUMES:
        pdf = pdfium.PdfDocument(pdf_path(root, volume))
        try:
            issues.append(IssueEntry(issue=volume, pages=len(pdf)))
            for index in range(len(pdf)):
                path = fraser._page_path(root, volume, index + 1)
                page = pdf[index]
                try:
                    if not fraser._page_complete(path, page):
                        raise FileNotFoundError(f"{path} is missing or incomplete")
                    with Image.open(path) as image:
                        width, height = image.size
                    pages.append(
                        PageEntry(
                            issue=volume,
                            page=index + 1,
                            sha256=fraser._sha256(path),
                            size_bytes=path.stat().st_size,
                            width=width,
                            height=height,
                            title_hint=fraser.title_hint(page),
                            **ocr_counts(_page_text(page)),
                        )
                    )
                finally:
                    page.close()
        finally:
            pdf.close()
    renderer = fraser.Renderer(
        pypdfium2=version("pypdfium2"),
        pillow=version("pillow"),
        dpi=fraser.DPI,
        jpeg_quality=fraser.JPEG_QUALITY,
    )
    return Manifest(renderer=renderer, issues=issues, pages=pages)


# --- the run -----------------------------------------------------------------------------------


def _load_sources(root: Path) -> Sources | None:
    path = root / "sources.json"
    return Sources.model_validate_json(path.read_text()) if path.is_file() else None


def progress(root: Path) -> str:
    """Where an ingest stands, read from disk."""
    sources = _load_sources(root)
    records = {f.issue: f for f in sources.files} if sources else {}
    done = [v for v in VOLUMES if fraser._pdf_complete(pdf_path(root, v), records.get(v))]
    rendered = {
        v: len(list((root / "pages" / v).glob("p*.jpg")))
        for v in VOLUMES
        if (root / "pages" / v).is_dir()
    }
    return (
        f"{len(done)} of {len(VOLUMES)} PDFs complete; "
        f"{sum(rendered.values())} page images on disk across {len(rendered)} volumes"
    )


def ingest(root: Path, log: Callable[[str], None] = print) -> int:
    """Download, render and record every volume; 0 when all is complete, 1 if some volume failed."""
    with fraser._lock(root):
        stale = fraser._clear_temp_files(root)
        if stale:
            log(f"removed {stale} unfinished temp file(s) from an earlier run")
        log(f"start: {progress(root)}")
        sources = _load_sources(root)
        failures: list[str] = []
        checked = False
        current = "starting"
        try:
            for volume in VOLUMES:
                fraser._check_stop()
                current = volume
                records = {f.issue: f for f in sources.files} if sources else {}
                try:
                    if not fraser._pdf_complete(pdf_path(root, volume), records.get(volume)):
                        if not checked:
                            rights = check_rights()
                            checked = True
                            shown = (
                                f"FRASER's {rights.statement!r}"
                                if isinstance(rights, fraser.Rights)
                                else f"no rights statement on FRASER; recorded basis {CITATIONS[0]}"
                            )
                            log(f"rights: {shown} (title page {TITLE_URL})")
                            sources = (
                                sources
                                or Sources(
                                    title=TITLE_NAME,
                                    publisher="US Office of the Comptroller of the Currency",
                                    title_url=TITLE_URL,
                                    rights=rights,
                                    files=[],
                                )
                            ).model_copy(update={"rights": rights})
                        fraser._pause(fraser.POLITE_PAUSE)
                        sources = download_volume(volume, root, sources, log)
                    render_volume(volume, root, log)
                except (fraser.DownloadError, OSError, pdfium.PdfiumError) as exc:
                    failures.append(f"{volume}: {exc}")
                    log(f"  {volume}: FAILED, moving on ({exc})")
        except fraser.Stopped:
            fraser._clear_temp_files(root)
            log(
                f"stopped while on {current}. {progress(root)}. Nothing is half-written; rerun to resume."
            )
            return 130
        if failures:
            log(f"{len(failures)} volume(s) failed, manifest not written:")
            for line in failures:
                log(f"  {line}")
            return 1
        try:
            manifest = build_manifest(root)
        except fraser.Stopped:
            log(f"stopped while building the manifest. {progress(root)}. Rerun to resume.")
            return 130
        fraser._write_record(root / "manifest.json", manifest)
        fraser._write_record(root / "split.json", current_split())
        log(
            f"done: {len(manifest.pages)} pages in {len(VOLUMES)} volumes; "
            "sources.json, manifest.json, split.json written"
        )
        return 0


# --- verify ------------------------------------------------------------------------------------


def verify(root: Path, log: Callable[[str], None] = print) -> int:
    """Offline: the committed records are sound and the files on disk match them. 0 if so."""
    problems: list[str] = []
    try:
        sources = Sources.model_validate_json((root / "sources.json").read_text())
        manifest = Manifest.model_validate_json((root / "manifest.json").read_text())
        split = Split.model_validate_json((root / "split.json").read_text())
    except (OSError, ValueError) as exc:
        log(f"FAIL: cannot read the records: {exc}")
        return 1
    problems += check_sources(sources) + check_manifest(manifest)
    if split != current_split():
        problems.append("split.json differs from the split fixed in archivist.ingest.occ")

    records = {f.issue: f for f in sources.files}
    counts = {e.issue: e.pages for e in manifest.issues}
    fill = "run `uv run python -m archivist.ingest.fraser --source occ` to fetch and render what is missing"
    for volume in VOLUMES:
        path = pdf_path(root, volume)
        if volume not in records or not path.is_file():
            problems.append(f"{volume}: PDF not on disk; {fill}")
            continue
        if not fraser._pdf_complete(path, records[volume]):
            problems.append(
                f"{volume}: PDF does not match sources.json (size, sha256 or it does not open)"
            )
            continue
        if fraser._opens(path) != counts.get(volume):
            problems.append(f"{volume}: PDF page count differs from the manifest")
    for entry in manifest.pages:
        path = fraser._page_path(root, entry.issue, entry.page)
        if not path.is_file():
            problems.append(f"{entry.issue} p{entry.page:03d}: image not on disk; {fill}")
        elif path.stat().st_size != entry.size_bytes or fraser._sha256(path) != entry.sha256:
            problems.append(f"{entry.issue} p{entry.page:03d}: image differs from the manifest")

    if problems:
        shown = problems[:20]
        log(f"FAIL: {len(problems)} problem(s)")
        for line in shown:
            log(f"  {line}")
        if len(problems) > len(shown):
            log(f"  … and {len(problems) - len(shown)} more")
        return 1
    log(f"ok: {len(sources.files)} PDFs and {len(manifest.pages)} page images match their records")
    return 0
