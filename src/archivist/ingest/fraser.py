"""US Treasury Bulletin from FRASER: download, render, record. No model ever reads these pages here.

    data/real/pdf/<YYYY_MM>_treasurybulletin.pdf   the issue as FRASER serves it    (gitignored)
    data/real/pages/<YYYY-MM>/p<NNN>.jpg           every page at 200 dpi            (gitignored)
    data/real/sources.json    where each PDF came from, when, its size and sha256
    data/real/manifest.json   every rendered page: sha256, size, and the PDF's own first lines
    data/real/split.json      development and held-out issues, fixed before any model run

Safe to interrupt, at any moment. A PDF is downloaded to a .part file and renamed into place only
once its size matches, it is a PDF and it opens; a page is rendered to a .part file and renamed the
same way. A rerun skips every PDF and page already complete. sources.json is rewritten atomically
after each PDF, before its rename, so a PDF on disk always has its record. The manifest and the
split are written once, at the end, and only if every issue is complete. SIGINT and SIGTERM stop
the run at the next safe point: the unfinished temp file is removed, where the run got to is
printed, and the exit status is 130.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import html
import http.client
import io
import json
import math
import os
import re
import signal
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import pypdfium2 as pdfium
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

TITLE_URL = "https://fraser.stlouisfed.org/title/treasury-bulletin-407"
PDF_URL = "https://fraser.stlouisfed.org/docs/publications/tbulletin/{name}"
RIGHTS_STATEMENT = "No Copyright - United States"
RIGHTS_URI = "http://rightsstatements.org/vocab/NoC-US/1.0/"
USER_AGENT = "archivist-hackathon/0.1 (+https://github.com/kamil-shirinov/Archivist)"

DPI = 200
SCALE = DPI / 72  # pdfium renders at 72 dpi per unit scale
JPEG_QUALITY = 90
HINT_LINES = 4
HINT_WIDTH = 100
CHUNK = 1 << 20
ATTEMPTS = 3
TIMEOUT = 30  # seconds without a byte from FRASER
POLITE_PAUSE = 1.0  # seconds between requests

DEFAULT_ROOT = Path("data/real")
PERMANENT_HTTP_ERRORS = {403, 404, 410}
FILL_MESSAGE = "run `uv run python -m archivist.ingest.fraser` to fetch and render what is missing"


def issue_ids() -> list[str]:
    """Every monthly issue January 1939 – December 1942, then each June from 1982 to 1994."""
    monthly = [f"{year}-{month:02d}" for year in range(1939, 1943) for month in range(1, 13)]
    return monthly + [f"{year}-06" for year in range(1982, 1995)]


ISSUES = issue_ids()
DEVELOPMENT = [f"1939-{month:02d}" for month in range(1, 13)] + [
    f"{year}-06" for year in range(1982, 1985)
]
HELD_OUT = [i for i in ISSUES if i[:4] in {"1940", "1941", "1942"}] + [
    f"{year}-06" for year in range(1985, 1995)
]
SPLIT_NOTE = (
    "Development: all 1939 issues and June 1982 to June 1984. Held-out: 1940 to 1942 and June 1985 "
    "to June 1994. Fixed before any model has seen a real page."
)


def pdf_name(issue: str) -> str:
    return f"{issue.replace('-', '_')}_treasurybulletin.pdf"


def pdf_url(issue: str) -> str:
    return PDF_URL.format(name=pdf_name(issue))


# --- records ---------------------------------------------------------------------------------

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
IssueId = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rights(_Record):
    """FRASER's own rights statement for the title, as its pages show it."""

    statement: str
    uri: str
    checked: date


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RecordedBasis(_Record):
    """FRASER shows no rights statement for the title; the project records why it may use it anyway."""

    fraser_shows: Literal["no rights statement"]
    basis: Annotated[str, StringConstraints(strip_whitespace=True, min_length=40)]
    citations: Annotated[list[Text], Field(min_length=1)]
    checked: date
    pages_checked: Annotated[list[Text], Field(min_length=1)]  # the FRASER pages that were read


class SourceFile(_Record):
    issue: IssueId
    url: str
    resolved_url: str  # where the redirect from `url` ended up
    retrieved: date
    size_bytes: int = Field(gt=0)
    sha256: Sha256


class Sources(_Record):
    title: str
    publisher: str
    title_url: str
    rights: Rights | RecordedBasis
    files: list[SourceFile]


def check_rights_record(rights: Rights | RecordedBasis) -> list[str]:
    """Why a rights record does not open the gate; empty when it does.

    The gate takes FRASER's own statement, "No Copyright - United States", or an explicit recorded
    basis: FRASER shows none, why the project may use the title anyway, and the law it cites. Never nothing.
    """
    if isinstance(rights, Rights):
        if rights.statement != RIGHTS_STATEMENT or rights.uri != RIGHTS_URI:
            return [f"rights statement is {rights.statement!r}, not {RIGHTS_STATEMENT!r}"]
        return []
    problems = []
    if rights.fraser_shows != "no rights statement":
        problems.append("recorded basis does not say that FRASER shows no rights statement")
    if not rights.basis.strip():
        problems.append("recorded basis states no basis")
    if not any(c.strip() for c in rights.citations):
        problems.append("recorded basis cites no law")
    if not any(p.strip() for p in rights.pages_checked):
        problems.append("recorded basis does not say which FRASER pages were read")
    return problems


class Renderer(_Record):
    pypdfium2: str
    pillow: str
    dpi: int
    jpeg_quality: int


class IssueEntry(_Record):
    issue: IssueId
    pages: int = Field(gt=0)


class PageEntry(_Record):
    issue: IssueId
    page: int = Field(ge=1)
    sha256: Sha256
    size_bytes: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    title_hint: list[str]  # first lines of the PDF's own OCR text; [] when the page has none


class Manifest(_Record):
    renderer: Renderer
    issues: list[IssueEntry]
    pages: list[PageEntry]


class Split(_Record):
    development: list[IssueId]
    held_out: list[IssueId]
    note: str

    @model_validator(mode="after")
    def _disjoint_and_complete(self) -> Split:
        sides = [*self.development, *self.held_out]
        if len(sides) != len(set(sides)):
            dupes = sorted({i for i in sides if sides.count(i) > 1})
            raise ValueError(f"issues listed more than once: {dupes}")
        if set(sides) != set(ISSUES):
            raise ValueError(
                f"split does not cover the issues exactly: missing {sorted(set(ISSUES) - set(sides))}, "
                f"unknown {sorted(set(sides) - set(ISSUES))}"
            )
        return self


def current_split() -> Split:
    return Split(development=DEVELOPMENT, held_out=HELD_OUT, note=SPLIT_NOTE)


def check_sources(sources: Sources) -> list[str]:
    """Problems that make sources.json incomplete or inconsistent; empty when it is sound."""
    found = [f.issue for f in sources.files]
    problems = [
        f"sources.json lists {i} more than once" for i in sorted(set(found)) if found.count(i) > 1
    ]
    problems += [f"sources.json has no record of {i}" for i in ISSUES if i not in found]
    problems += [f"sources.json lists unknown issue {i}" for i in found if i not in ISSUES]
    problems += [
        f"{f.issue}: url is not {pdf_url(f.issue)}"
        for f in sources.files
        if f.url != pdf_url(f.issue)
    ]
    return problems + check_rights_record(sources.rights)


def check_manifest(manifest: Manifest) -> list[str]:
    """Problems that make the manifest incomplete or inconsistent; empty when it is sound."""
    problems: list[str] = []
    if [e.issue for e in manifest.issues] != ISSUES:
        problems.append("manifest issues are not the expected issues, in order")
    counts = {e.issue: e.pages for e in manifest.issues}
    expected = [(i, n) for i in ISSUES for n in range(1, counts.get(i, 0) + 1)]
    if [(p.issue, p.page) for p in manifest.pages] != expected:
        problems.append("manifest pages are not every page 1..n of every issue, in order")
    return problems


# --- small helpers ---------------------------------------------------------------------------


class Stopped(Exception):
    """SIGINT or SIGTERM arrived; the run stops at the next safe point."""


class RightsError(Exception):
    """FRASER no longer shows the rights statement this project relies on."""


class DownloadError(Exception):
    pass


_STOP = threading.Event()


def _request_stop(signum: int, frame: object) -> None:
    if _STOP.is_set():  # a second signal means now
        raise SystemExit(130)
    _STOP.set()


def _check_stop() -> None:
    if _STOP.is_set():
        raise Stopped


def _pause(seconds: float) -> None:
    if _STOP.wait(seconds):
        raise Stopped


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes_atomically(path: Path, data: bytes) -> None:
    part = path.with_name(path.name + ".part")
    with part.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(part, path)


def _dumps(obj: dict[str, Any]) -> str:
    """Top-level keys on their own lines and one list entry per line, so a diff shows what changed."""

    def one(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))

    lines = ["{"]
    keys = list(obj)
    for n, key in enumerate(keys):
        tail = "," if n < len(keys) - 1 else ""
        value = obj[key]
        if isinstance(value, list) and value:
            lines.append(f"  {one(key)}: [")
            lines += [
                f"    {one(item)}{',' if k < len(value) - 1 else ''}"
                for k, item in enumerate(value)
            ]
            lines.append(f"  ]{tail}")
        else:
            lines.append(f"  {one(key)}: {one(value)}{tail}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _write_record(path: Path, model: BaseModel) -> None:
    _write_bytes_atomically(path, _dumps(model.model_dump(mode="json")).encode())


@contextlib.contextmanager
def _lock(root: Path) -> Iterator[None]:
    """One ingest at a time: a second run would delete the first one's temp files."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".ingest.lock").open("w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"another ingest is already running in {root}") from None
        yield


def _clear_temp_files(root: Path) -> int:
    stale = [p for p in root.rglob("*.part") if p.is_file()]
    for path in stale:
        path.unlink()
    return len(stale)


# --- rights ----------------------------------------------------------------------------------


def rights_statement_present(page_html: str) -> bool:
    """True if the page's RIGHTS field reads 'No Copyright - United States', however it is marked up.

    The tags between the label and the text, the whitespace around them and the kind of dash
    (hyphen, en or em dash) vary with FRASER's templates and mean nothing.
    """
    text = re.sub(r"<!--.*?-->", " ", page_html, flags=re.DOTALL)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[‐-―−]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return re.search(r"RIGHTS:\s*No Copyright - United States\b", text, re.IGNORECASE) is not None


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=TIMEOUT)


def _fetch_text(url: str) -> str:
    with _open(url) as response:
        return response.read().decode("utf-8", "replace")


def check_rights(fetch: Callable[[str], str] = _fetch_text) -> Rights:
    """Read FRASER's title page; raise RightsError unless it still carries the statement."""
    if not rights_statement_present(fetch(TITLE_URL)):
        raise RightsError(
            f"{TITLE_URL} no longer shows {RIGHTS_STATEMENT!r} in its RIGHTS field; "
            "nothing was downloaded. Check the title page by hand before going on."
        )
    return Rights(statement=RIGHTS_STATEMENT, uri=RIGHTS_URI, checked=datetime.now(UTC).date())


# --- download --------------------------------------------------------------------------------


def _opens(path: Path) -> int:
    """Page count of a PDF that opens and has pages; raises pdfium.PdfiumError if it does not."""
    with path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise pdfium.PdfiumError("not a PDF (no %PDF- header)")
    pdf = pdfium.PdfDocument(path)
    try:
        if len(pdf) < 1:
            raise pdfium.PdfiumError("PDF has no pages")
        return len(pdf)
    finally:
        pdf.close()


def _pdf_complete(path: Path, record: SourceFile | None) -> bool:
    if record is None or not path.is_file() or path.stat().st_size != record.size_bytes:
        return False
    try:
        _opens(path)
    except pdfium.PdfiumError:
        return False
    return _sha256(path) == record.sha256


def _fetch_pdf(url: str, part: Path) -> tuple[str, int, str]:
    """Stream url to part; return (resolved url, size, sha256). Raises DownloadError if it is short."""
    digest = hashlib.sha256()
    size = 0
    with _open(url) as response, part.open("wb") as out:
        expected = response.headers.get("Content-Length")
        resolved = response.geturl()
        while chunk := response.read(CHUNK):
            _check_stop()
            out.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        out.flush()
        os.fsync(out.fileno())
    if expected is not None and size != int(expected):
        raise DownloadError(f"got {size} bytes, server announced {expected}")
    if size == 0:
        raise DownloadError("empty response")
    return resolved, size, digest.hexdigest()


T = TypeVar("T")


def _retrying(
    label: str,
    url: str,
    log: Callable[[str], None],
    action: Callable[[], T],
    cleanup: Callable[[], None],
) -> T:
    """Run action up to ATTEMPTS times, pausing longer after each failure.

    A permanent HTTP error fails at once; cleanup removes whatever a failed or stopped attempt left.
    """
    last_error = "unknown"
    for attempt in range(1, ATTEMPTS + 1):
        _check_stop()
        try:
            return action()
        except (Stopped, SystemExit):
            cleanup()
            raise
        except urllib.error.HTTPError as exc:
            cleanup()
            if exc.code in PERMANENT_HTTP_ERRORS:
                raise DownloadError(f"{url}: HTTP {exc.code}") from exc
            last_error = f"HTTP {exc.code}"
        except (OSError, http.client.HTTPException, DownloadError, pdfium.PdfiumError) as exc:
            cleanup()
            last_error = f"{type(exc).__name__}: {exc}"
        log(f"  {label}: attempt {attempt}/{ATTEMPTS} failed ({last_error})")
        if attempt < ATTEMPTS:
            _pause(4**attempt)
    raise DownloadError(f"{url}: {last_error}")


def _download(
    url: str,
    final: Path,
    label: str,
    log: Callable[[str], None],
    record: Callable[[str, int, str], None],
) -> None:
    """Fetch url to final's .part file and check it, call record(resolved url, size, sha256), then rename.

    The record is written before the rename, so a PDF on disk always has one.
    """
    final.parent.mkdir(parents=True, exist_ok=True)
    part = final.with_name(final.name + ".part")

    def attempt() -> tuple[str, int, str, int]:
        resolved, size, sha = _fetch_pdf(url, part)
        return resolved, size, sha, _opens(part)

    resolved, size, sha, pages = _retrying(
        label, url, log, attempt, lambda: part.unlink(missing_ok=True)
    )
    record(resolved, size, sha)
    os.replace(part, final)
    log(f"  {label}: downloaded {size:,} bytes, {pages} pages")


def download_issue(issue: str, root: Path, sources: Sources, log: Callable[[str], None]) -> Sources:
    """Fetch one PDF to a .part file, check it, record it, then rename it. Returns updated sources."""
    url = pdf_url(issue)
    updated = sources

    def record(resolved: str, size: int, sha: str) -> None:
        nonlocal updated
        entry = SourceFile(
            issue=issue,
            url=url,
            resolved_url=resolved,
            retrieved=datetime.now(UTC).date(),
            size_bytes=size,
            sha256=sha,
        )
        files = sorted([*(f for f in sources.files if f.issue != issue), entry], key=lambda f: f.issue)
        updated = sources.model_copy(update={"files": files})
        _write_record(root / "sources.json", updated)

    _download(url, root / "pdf" / pdf_name(issue), issue, log, record)
    return updated


# --- render ----------------------------------------------------------------------------------


def render_page(page: pdfium.PdfPage) -> bytes:
    """The page as a JPEG at DPI. The same page always gives the same bytes."""
    image = page.render(scale=SCALE).to_pil().convert("RGB")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=JPEG_QUALITY, dpi=(DPI, DPI))
    return out.getvalue()


def _expected_size(page: pdfium.PdfPage) -> tuple[int, int]:
    width, height = page.get_size()
    return math.ceil(width * SCALE), math.ceil(height * SCALE)


def _page_complete(path: Path, page: pdfium.PdfPage) -> bool:
    """A JPEG of the right pixel size that ends with its end-of-image marker."""
    try:
        with path.open("rb") as f:
            f.seek(-2, os.SEEK_END)
            if f.read(2) != b"\xff\xd9":
                return False
        with Image.open(path) as image:
            return image.format == "JPEG" and image.size == _expected_size(page)
    except (OSError, ValueError):
        return False


def _page_path(root: Path, issue: str, number: int) -> Path:
    return root / "pages" / issue / f"p{number:03d}.jpg"


def render_issue(issue: str, root: Path, log: Callable[[str], None]) -> tuple[int, int]:
    """Render every page that is not already on disk; return (rendered now, already there)."""
    return _render_pdf(root / "pdf" / pdf_name(issue), root, issue, log)


def _render_pdf(
    pdf_path: Path, root: Path, issue: str, log: Callable[[str], None]
) -> tuple[int, int]:
    """Render pdf_path's pages to root/pages/<issue>/; return (rendered now, already there)."""
    (root / "pages" / issue).mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(pdf_path)
    rendered = skipped = 0
    try:
        for index in range(len(pdf)):
            _check_stop()
            target = _page_path(root, issue, index + 1)
            page = pdf[index]
            try:
                if _page_complete(target, page):
                    skipped += 1
                    continue
                _write_bytes_atomically(target, render_page(page))
                rendered += 1
            finally:
                page.close()
    finally:
        pdf.close()
    log(f"  {issue}: {rendered} pages rendered, {skipped} already there")
    return rendered, skipped


def _printable(text: str) -> str:
    return "".join(c for c in text if c.isprintable() or c.isspace())


def title_hint(page: pdfium.PdfPage) -> list[str]:
    """The first lines of the PDF's own OCR text, whitespace collapsed and cut to HINT_WIDTH."""
    textpage = page.get_textpage()
    try:
        text = textpage.get_text_range()
    finally:
        textpage.close()
    lines = [" ".join(_printable(raw).split()) for raw in re.split(r"\r\n|\r|\n", text)]
    return [line[:HINT_WIDTH] for line in lines if line][:HINT_LINES]


def build_manifest(root: Path) -> Manifest:
    """Read every rendered page back from disk. Raises FileNotFoundError if any is missing."""
    issues: list[IssueEntry] = []
    pages: list[PageEntry] = []
    for issue in ISSUES:
        pdf = pdfium.PdfDocument(root / "pdf" / pdf_name(issue))
        try:
            issues.append(IssueEntry(issue=issue, pages=len(pdf)))
            for index in range(len(pdf)):
                path = _page_path(root, issue, index + 1)
                page = pdf[index]
                try:
                    if not _page_complete(path, page):
                        raise FileNotFoundError(f"{path} is missing or incomplete")
                    with Image.open(path) as image:
                        width, height = image.size
                    pages.append(
                        PageEntry(
                            issue=issue,
                            page=index + 1,
                            sha256=_sha256(path),
                            size_bytes=path.stat().st_size,
                            width=width,
                            height=height,
                            title_hint=title_hint(page),
                        )
                    )
                finally:
                    page.close()
        finally:
            pdf.close()
    renderer = Renderer(
        pypdfium2=version("pypdfium2"), pillow=version("pillow"), dpi=DPI, jpeg_quality=JPEG_QUALITY
    )
    return Manifest(renderer=renderer, issues=issues, pages=pages)


# --- the run ---------------------------------------------------------------------------------


def _load_sources(root: Path) -> Sources | None:
    path = root / "sources.json"
    return Sources.model_validate_json(path.read_text()) if path.is_file() else None


def progress(root: Path) -> str:
    """Where an ingest stands, read from disk."""
    sources = _load_sources(root)
    records = {f.issue: f for f in sources.files} if sources else {}
    done = [i for i in ISSUES if _pdf_complete(root / "pdf" / pdf_name(i), records.get(i))]
    rendered = {
        i: len(list((root / "pages" / i).glob("p*.jpg")))
        for i in ISSUES
        if (root / "pages" / i).is_dir()
    }
    return (
        f"{len(done)} of {len(ISSUES)} PDFs complete; "
        f"{sum(rendered.values())} page images on disk across {len(rendered)} issues"
    )


def ingest(root: Path, log: Callable[[str], None] = print) -> int:
    """Download, render and record every issue; 0 when all is complete, 1 if some issue failed."""
    with _lock(root):
        stale = _clear_temp_files(root)
        if stale:
            log(f"removed {stale} unfinished temp file(s) from an earlier run")
        log(f"start: {progress(root)}")
        sources = _load_sources(root)
        failures: list[str] = []
        checked = False
        current = "starting"
        try:
            for issue in ISSUES:
                _check_stop()
                current = issue
                records = {f.issue: f for f in sources.files} if sources else {}
                try:
                    if not _pdf_complete(root / "pdf" / pdf_name(issue), records.get(issue)):
                        if not checked:
                            rights = check_rights()
                            checked = True
                            log(f"rights: {rights.statement!r} confirmed on {TITLE_URL}")
                            sources = (
                                sources
                                or Sources(
                                    title="Treasury Bulletin",
                                    publisher="US Department of the Treasury",
                                    title_url=TITLE_URL,
                                    rights=rights,
                                    files=[],
                                )
                            ).model_copy(update={"rights": rights})
                        else:
                            _pause(POLITE_PAUSE)
                        sources = download_issue(issue, root, sources, log)
                    render_issue(issue, root, log)
                except (DownloadError, OSError, pdfium.PdfiumError) as exc:
                    failures.append(f"{issue}: {exc}")
                    log(f"  {issue}: FAILED, moving on ({exc})")
        except Stopped:
            _clear_temp_files(root)
            log(
                f"stopped while on {current}. {progress(root)}. Nothing is half-written; rerun to resume."
            )
            return 130
        if failures:
            log(f"{len(failures)} issue(s) failed, manifest not written:")
            for line in failures:
                log(f"  {line}")
            return 1
        try:
            manifest = build_manifest(root)
        except Stopped:
            log(f"stopped while building the manifest. {progress(root)}. Rerun to resume.")
            return 130
        _write_record(root / "manifest.json", manifest)
        _write_record(root / "split.json", current_split())
        log(
            f"done: {len(manifest.pages)} pages in {len(ISSUES)} issues; sources.json, manifest.json, split.json written"
        )
        return 0


# --- verify ----------------------------------------------------------------------------------


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
        problems.append("split.json differs from the split fixed in archivist.ingest.fraser")

    records = {f.issue: f for f in sources.files}
    counts = {e.issue: e.pages for e in manifest.issues}
    for issue in ISSUES:
        path = root / "pdf" / pdf_name(issue)
        if issue not in records or not path.is_file():
            problems.append(f"{issue}: PDF not on disk; {FILL_MESSAGE}")
            continue
        if not _pdf_complete(path, records[issue]):
            problems.append(
                f"{issue}: PDF does not match sources.json (size, sha256 or it does not open)"
            )
            continue
        if _opens(path) != counts.get(issue):
            problems.append(f"{issue}: PDF page count differs from the manifest")
    for entry in manifest.pages:
        path = _page_path(root, entry.issue, entry.page)
        if not path.is_file():
            problems.append(f"{entry.issue} p{entry.page:03d}: image not on disk; {FILL_MESSAGE}")
        elif path.stat().st_size != entry.size_bytes or _sha256(path) != entry.sha256:
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


def main(argv: list[str] | None = None) -> None:
    from archivist.ingest import frb, occ  # here, not at the top: both build on this module

    # source -> (default root, ingest, verify)
    sources = {
        "treasury": (DEFAULT_ROOT, ingest, verify),
        "occ": (occ.DEFAULT_ROOT, occ.ingest, occ.verify),
        "frb": (frb.DEFAULT_ROOT, frb.ingest, frb.verify),
    }
    parser = argparse.ArgumentParser(
        prog="python -m archivist.ingest.fraser",
        description="Download the real FRASER sources (the Treasury Bulletin, the Comptroller of "
        "the Currency's annual reports and the Federal Reserve Bulletin), render their pages and "
        "record them.",
    )
    parser.add_argument(
        "--source", choices=list(sources), help="only this source (default: every source)"
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="where --source's pages live (default: data/real, data/real_occ or data/real_frb)",
    )
    parser.add_argument(
        "--verify", action="store_true", help="offline: check the files against the records"
    )
    args = parser.parse_args(argv)
    if args.root is not None and args.source is None:
        parser.error("--root needs --source")
    chosen = [args.source] if args.source else list(sources)
    roots = {name: args.root or sources[name][0] for name in chosen}

    if args.verify:
        results = []
        for name in chosen:  # every source is checked, so one failure does not hide another
            print(f"{name}:")
            results.append(sources[name][2](roots[name]))
        sys.exit(max(results))

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    worst = 0
    try:
        for name in chosen:
            print(f"{name}:", flush=True)
            code = sources[name][1](roots[name], log=lambda line: print(line, flush=True))
            if code == 130:
                sys.exit(130)
            worst = max(worst, code)
    except RightsError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(worst)


if __name__ == "__main__":
    main()
