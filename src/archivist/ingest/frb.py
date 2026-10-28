"""Federal Reserve Bulletin from FRASER, title 62: download, scan-check, render, record. No model ever reads these pages here.

    data/real_frb/pdf/<YYYY_MM>_frb.pdf          the issue as FRASER serves it    (gitignored)
    data/real_frb/pages/<YYYY-MM>/p<NNN>.jpg     every page at 200 dpi            (gitignored)
    data/real_frb/sources.json     where each PDF came from, when, its size and sha256, what its item's
                                   metadata says about rights, and the rights record
    data/real_frb/scan_check.json  for every issue considered, what each page is made of; which were skipped
    data/real_frb/manifest.json    every rendered page: sha256, size, the PDF's own first lines, OCR counts
    data/real_frb/split.json       development and held-out issues, fixed before any model run

The machinery is archivist.ingest.fraser's, pointed at a third title: resumable at any moment, a PDF
or page written to a .part file and renamed into place only when whole, the record written before
the rename, one ingest at a time, SIGINT and SIGTERM stopping at the next safe point, and every
request sent with the same User-Agent. What differs:

- The issues are the June issue of each year, 1980 to 2000, and June 2001 to 2003 when every page of
  the issue passes the scan check. There is no June 2004 or June 2005: the Bulletin went quarterly in
  2004 (FRASER lists Spring, Summer, Fall and Winter), and those two are recorded as not issued.
- Rights. FRASER's title page shows "No Copyright - United States" and no page of an item does: the
  item page is a bare PDF viewer, and the item's metadata (JSON, MODS, IIIF) says only "for more
  information on rights relating to this item, please see" its page. The title page's statement
  therefore stands for the items, as it did for the Treasury Bulletin. Each item's metadata is read
  before anything is downloaded and recorded as it is; if any item names another statement, or words
  this ingest does not recognise, nothing is downloaded. The Board of Governors being an agency of the
  US Government (17 U.S.C. § 105) is recorded in sources.json as a second basis.
- The scan check (below) is made on every page of every issue. For an issue after 2000 it decides
  whether the issue is ingested; for the 21 fixed issues it is reported and gates nothing.
- The split is by issue: June 1980, 1990 and 2000 are development; every other June issue ingested
  is held out.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, Literal

import pypdfium2 as pdfium
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from archivist.ingest import fraser, occ, survey_modern

TITLE_URL = "https://fraser.stlouisfed.org/title/federal-reserve-bulletin-62"
TITLE_NAME = "Federal Reserve Bulletin"
TITLE_ID = 62
ITEM_URL = TITLE_URL + "/june-{year}-{item}"
METADATA_URL = occ.METADATA_URL
PDF_PREFIX = occ.PDF_PREFIX
DEFAULT_ROOT = Path("data/real_frb")

# issue -> FRASER item id: the June issue of each year. The ids come from the title page's decade
# listings; each is checked against its item's metadata before its PDF is fetched.
ITEMS: dict[str, int] = {
    "1980-06": 20466,
    "1981-06": 20478,
    "1982-06": 20489,
    "1983-06": 20502,
    "1984-06": 20513,
    "1985-06": 20757,
    "1986-06": 20769,
    "1987-06": 20781,
    "1988-06": 20793,
    "1989-06": 20805,
    "1990-06": 20816,
    "1991-06": 20829,
    "1992-06": 20840,
    "1993-06": 20853,
    "1994-06": 20864,
    "1995-06": 20877,
    "1996-06": 20888,
    "1997-06": 20901,
    "1998-06": 20913,
    "1999-06": 20925,
    "2000-06": 20937,
    "2001-06": 20949,
    "2002-06": 20961,
    "2003-06": 20973,
}
GATED = ["2001-06", "2002-06", "2003-06"]  # ingested only if every page passes the scan check
NOT_ISSUED: dict[str, str] = {
    "2004-06": "no such issue: the Bulletin went quarterly in 2004; FRASER lists Spring, Summer, Fall and Winter 2004",
    "2005-06": "no such issue: the Bulletin was quarterly in 2005; FRASER lists Winter, Spring, Summer and Fall 2005",
}
DEVELOPMENT = ["1980-06", "1990-06", "2000-06"]
SPLIT_NOTE = (
    "Development: June 1980, June 1990 and June 2000. Held-out: every other June issue ingested. "
    "Fixed before any model has seen a real page."
)

AGENCY_BASIS = (
    "The Board of Governors of the Federal Reserve System is an independent agency of the US "
    "Government, so the Federal Reserve Bulletin, which it publishes, is a work of the US Government "
    "and is not subject to copyright in the United States (17 U.S.C. § 105). This stands apart from "
    "FRASER's statement. FRASER shows a rights statement for the title only: no page, metadata record "
    "or manifest of an item states one, each says only to see the item's page, so the title's "
    f"{fraser.RIGHTS_STATEMENT!r} stands for its items."
)
AGENCY_CITATIONS = ["17 U.S.C. § 105"]
RIGHTS_POINTER = re.compile(
    r"^For more information on rights relating to this item, please see:\s*\S+$"
)  # what an item's metadata says in place of a statement

# --- the scan check ------------------------------------------------------------------------------
#
# Fixed before any issue after 2000 was downloaded. A page passes if it is a scan, one image covering
# at least survey_modern.SCAN_COVER of it, and has no real text: either its text is an OCR layer (drawn
# invisibly, or under the image) or it has next to no text at all (a cover, a photograph, a blank page:
# at most THIN_MAX_TEXT_OBJECTS text objects). A page whose text is drawn visibly, or that no image
# covers, fails. An issue passes if every one of its pages does. One letter a page is recorded:
OCR, THIN, TEXT, OTHER = "o", "t", "x", "z"
LAYER_NAMES = {
    OCR: "scan with an OCR layer",
    THIN: "scan with next to no text",
    TEXT: "real text",
    OTHER: "other",
}
PASSING = {OCR, THIN}
THIN_MAX_TEXT_OBJECTS = 20
SCAN_RULE = (
    f"A page passes if one image covers at least {survey_modern.SCAN_COVER:.0%} of it and its text is an "
    f"OCR layer (drawn invisibly, or under the image) or it has at most {THIN_MAX_TEXT_OBJECTS} text "
    "objects (a cover, a photograph or a blank page); a page with visible text, or that no image "
    "covers, fails. An issue passes if every page does. The 21 fixed issues (1980 to 2000) are "
    "ingested whatever the check shows; an issue after 2000 only if it passes."
)


def layer_of(layers: survey_modern.PageLayers) -> str:
    """The letter for what a page is made of."""
    kind = layers.kind
    if kind == survey_modern.OCR_LAYER:
        return OCR
    if kind == survey_modern.SCAN_THIN:
        return THIN if layers.text_objects <= THIN_MAX_TEXT_OBJECTS else TEXT
    return TEXT if kind == survey_modern.REAL_TEXT else OTHER


def pdf_layers(path: Path) -> str:
    """One letter for each page of the PDF, in order."""
    pdf = pdfium.PdfDocument(path)
    try:
        out = []
        for index in range(len(pdf)):
            fraser._check_stop()
            page = pdf[index]
            try:
                out.append(layer_of(survey_modern.page_layers(page, index + 1)))
            finally:
                page.close()
        return "".join(out)
    finally:
        pdf.close()


# --- records ---------------------------------------------------------------------------------


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Layers = Annotated[str, StringConstraints(pattern=r"^[otxz]+$")]


class SourceFile(fraser.SourceFile):
    item_id: int  # the FRASER item the PDF was found from
    item_url: str
    metadata_url: str  # where `url` (the item's pdfUrl) and `access_condition` were read
    access_condition: str  # the item's metadata on rights, as it was; "" if it had none


class AgencyBasis(_Record):
    """A second basis, apart from FRASER's statement: who publishes the title and what the law says of it."""

    basis: Annotated[str, StringConstraints(strip_whitespace=True, min_length=40)]
    citations: Annotated[list[Text], Field(min_length=1)]
    checked: date


class Sources(fraser.Sources):
    rights: fraser.Rights  # FRASER's own statement, never a recorded basis alone
    agency_basis: AgencyBasis
    files: list[SourceFile]


class ScanEntry(_Record):
    issue: fraser.IssueId
    pages: int = Field(gt=0)
    layers: Layers  # one letter a page: o scan with an OCR layer, t scan with next to no text, x real text, z other
    gate: Literal["required", "reported"]  # required: the issue is ingested only if every page passes
    outcome: Literal["ingested", "skipped"]

    @model_validator(mode="after")
    def _one_letter_a_page(self) -> ScanEntry:
        if len(self.layers) != self.pages:
            raise ValueError(f"{self.issue}: {len(self.layers)} letters for {self.pages} pages")
        return self

    @property
    def failing(self) -> list[int]:
        return [n for n, c in enumerate(self.layers, 1) if c not in PASSING]

    def counts(self) -> dict[str, int]:
        return {name: self.layers.count(letter) for letter, name in LAYER_NAMES.items()}


class NotIssued(_Record):
    issue: fraser.IssueId
    reason: Text


class ScanCheck(_Record):
    rule: str
    issues: list[ScanEntry]
    not_issued: list[NotIssued]


class TableMark(_Record):
    """A numbered table's caption on a page, with the lines that begin "Total" after it on that page."""

    number: Annotated[str, StringConstraints(pattern=r"^\d\.\d{2}$")]
    title: str
    total_lines: int = Field(ge=0)


class IssueEntry(fraser.IssueEntry):
    pass


class PageEntry(fraser.PageEntry):
    """A page, with counts from the PDF's own OCR text for the survey (all zero when it has none)."""

    lines: int = Field(ge=0)  # non-empty lines of OCR text
    figure_lines: int = Field(ge=0)  # of those, lines that are mostly digits
    total_lines: int = Field(ge=0)  # lines that begin "Total" or "Totals", after a row number if any
    leading_total_lines: int = Field(ge=0)  # of those, before the page's first caption: a table continued
    tables: list[TableMark]  # the numbered captions on the page, in order

    @model_validator(mode="after")
    def _totals_add_up(self) -> PageEntry:
        if self.leading_total_lines + sum(t.total_lines for t in self.tables) != self.total_lines:
            raise ValueError(f"{self.issue} p{self.page}: total lines do not add up")
        return self


class Manifest(fraser.Manifest):
    issues: list[IssueEntry]
    pages: list[PageEntry]


class Split(_Record):
    development: list[fraser.IssueId]
    held_out: list[fraser.IssueId]
    note: str

    @model_validator(mode="after")
    def _disjoint(self) -> Split:
        sides = [*self.development, *self.held_out]
        if len(sides) != len(set(sides)):
            dupes = sorted({i for i in sides if sides.count(i) > 1})
            raise ValueError(f"issues listed more than once: {dupes}")
        return self

    def side(self, issue: str) -> Literal["development", "held_out"]:
        return "development" if issue in self.development else "held_out"


def current_split(ingested: list[str]) -> Split:
    """The split of the issues ingested: June 1980, 1990 and 2000, and every other one held out."""
    return Split(
        development=list(DEVELOPMENT),
        held_out=[i for i in ingested if i not in DEVELOPMENT],
        note=SPLIT_NOTE,
    )


def check_split(split: Split, ingested: list[str]) -> list[str]:
    """Why a split does not cover the ingested issues exactly; empty when it does."""
    sides = [*split.development, *split.held_out]
    problems = []
    if missing := sorted(set(ingested) - set(sides)):
        problems.append(f"split does not cover the issues exactly: missing {missing}")
    if unknown := sorted(set(sides) - set(ingested)):
        problems.append(f"split does not cover the issues exactly: unknown {unknown}")
    if split != current_split(ingested):
        problems.append("split.json differs from the split fixed in archivist.ingest.frb")
    return problems


# --- OCR counts ----------------------------------------------------------------------------------


def ocr_counts(text: str) -> dict[str, Any]:
    """What the survey counts in a page's OCR text: lines, figure lines, Total lines, numbered captions.

    The Bulletin numbers its statistics tables ("1.26 COMMERCIAL BANKS IN THE UNITED STATES ...") and
    numbers each row ("16 Total assets"); a line "Total ..." belongs to the last caption before it on
    the page, or, with none yet, to the table the page continues. The rules are those of the P24
    survey (survey_modern.CAPTIONS and TOTAL_LINE).
    """
    base = occ.ocr_counts(text)
    caption, is_total = survey_modern.CAPTIONS["frb"], survey_modern.TOTAL_LINE
    leading = 0
    tables: list[dict[str, Any]] = []
    for raw in re.split(r"\r\n|\r|\n", text):
        line = " ".join(raw.split())
        if (match := caption.match(line)) is not None:
            title = survey_modern.clean_title(match["title"])[: fraser.HINT_WIDTH]
            tables.append({"number": match["id"], "title": title, "total_lines": 0})
        elif is_total.match(line):
            if tables:
                tables[-1]["total_lines"] += 1
            else:
                leading += 1
    return {
        "lines": base["lines"],
        "figure_lines": base["figure_lines"],
        "total_lines": leading + sum(t["total_lines"] for t in tables),
        "leading_total_lines": leading,
        "tables": tables,
    }


# --- small helpers ---------------------------------------------------------------------------


def pdf_name(issue: str) -> str:
    return f"{issue.replace('-', '_')}_frb.pdf"


def pdf_path(root: Path, issue: str) -> Path:
    return root / "pdf" / pdf_name(issue)


def item_url(issue: str) -> str:
    return ITEM_URL.format(year=issue[:4], item=ITEMS[issue])


def metadata_url(issue: str) -> str:
    return METADATA_URL.format(item=ITEMS[issue])


def _month_year(issue: str) -> str:
    return f"June {issue[:4]}"


def _gate(issue: str) -> Literal["required", "reported"]:
    return "required" if issue in GATED else "reported"


def ingested_issues(scan: ScanCheck) -> list[str]:
    return [e.issue for e in scan.issues if e.outcome == "ingested"]


def outcome_of(issue: str, layers: str) -> Literal["ingested", "skipped"]:
    """Whether an issue is ingested, given what its pages are made of."""
    return "skipped" if issue in GATED and not set(layers) <= PASSING else "ingested"


# --- checks of the records ---------------------------------------------------------------------


def rights_problem(access: str) -> str | None:
    """Why an item's rights text does not leave the download open; None when it does.

    Open: none, the usual pointer to the item's page, or FRASER's NoC-US statement. Anything else could
    be another statement, and stops everything.
    """
    access = access.strip()
    if not access or RIGHTS_POINTER.match(access):
        return None
    if fraser.RIGHTS_URI in access or fraser.RIGHTS_STATEMENT.lower() in access.lower():
        return None
    return f"its rights text is {access!r}"


def check_sources(sources: Sources) -> list[str]:
    """Problems that make sources.json incomplete or inconsistent; empty when it is sound."""
    found = [f.issue for f in sources.files]
    problems = [
        f"sources.json lists {i} more than once" for i in sorted(set(found)) if found.count(i) > 1
    ]
    problems += [f"sources.json has no record of {i}" for i in ITEMS if i not in found]
    problems += [f"sources.json lists unknown issue {i}" for i in found if i not in ITEMS]
    for f in sources.files:
        if f.issue not in ITEMS:
            continue
        if f.item_id != ITEMS[f.issue]:
            problems.append(f"{f.issue}: item is {f.item_id}, not {ITEMS[f.issue]}")
        if f.item_url != item_url(f.issue) or f.metadata_url != metadata_url(f.issue):
            problems.append(f"{f.issue}: item or metadata address is not the one for its item")
        if not (f.url.startswith(PDF_PREFIX) and f.url.lower().endswith(".pdf")):
            problems.append(f"{f.issue}: url is not a PDF under {PDF_PREFIX}")
        if (why := rights_problem(f.access_condition)) is not None:
            problems.append(f"{f.issue}: {why}")
    if sources.title_url != TITLE_URL:
        problems.append(f"title_url is not {TITLE_URL}")
    problems += fraser.check_rights_record(sources.rights)
    if not any(c.strip() == AGENCY_CITATIONS[0] for c in sources.agency_basis.citations):
        problems.append(f"agency basis does not cite {AGENCY_CITATIONS[0]}")
    return problems


def check_scan(scan: ScanCheck) -> list[str]:
    """Problems that make scan_check.json incomplete or inconsistent; empty when it is sound."""
    problems: list[str] = []
    if [e.issue for e in scan.issues] != list(ITEMS):
        problems.append("scan_check.json does not have every issue considered, in order")
    if scan.rule != SCAN_RULE:
        problems.append("scan_check.json states a rule other than the one fixed in archivist.ingest.frb")
    if {n.issue: n.reason for n in scan.not_issued} != NOT_ISSUED:
        problems.append("scan_check.json does not record June 2004 and June 2005 as not issued")
    for e in scan.issues:
        if e.gate != _gate(e.issue):
            problems.append(f"{e.issue}: gate is {e.gate}, not {_gate(e.issue)}")
        if e.outcome != outcome_of(e.issue, e.layers):
            problems.append(f"{e.issue}: outcome {e.outcome} does not follow from its pages")
    return problems


def check_manifest(manifest: Manifest, scan: ScanCheck) -> list[str]:
    """Problems that make the manifest incomplete or inconsistent; empty when it is sound."""
    problems: list[str] = []
    ingested = ingested_issues(scan)
    if [e.issue for e in manifest.issues] != ingested:
        problems.append("manifest issues are not the issues the scan check ingested, in order")
    counts = {e.issue: e.pages for e in manifest.issues}
    expected = [(i, n) for i in ingested for n in range(1, counts.get(i, 0) + 1)]
    if [(p.issue, p.page) for p in manifest.pages] != expected:
        problems.append("manifest pages are not every page 1..n of every issue, in order")
    for e in scan.issues:
        if e.issue in counts and counts[e.issue] != e.pages:
            problems.append(f"{e.issue}: manifest has {counts[e.issue]} pages, the scan check {e.pages}")
    return problems


# --- rights and item metadata ------------------------------------------------------------------


def check_rights(fetch: Callable[[str], str] | None = None) -> fraser.Rights:
    """Read FRASER's title page; raise RightsError unless it is this title's and still carries the statement."""
    page = (fetch or fraser._fetch_text)(TITLE_URL)
    if TITLE_NAME not in occ._text_of(page):
        raise fraser.RightsError(
            f"{TITLE_URL} is not showing the title page of {TITLE_NAME!r}; nothing was downloaded. "
            "Check the page by hand before going on."
        )
    if not fraser.rights_statement_present(page):
        raise fraser.RightsError(
            f"{TITLE_URL} no longer shows {fraser.RIGHTS_STATEMENT!r} in its RIGHTS field; "
            "nothing was downloaded. Check the title page by hand before going on."
        )
    return fraser.Rights(
        statement=fraser.RIGHTS_STATEMENT, uri=fraser.RIGHTS_URI, checked=datetime.now(UTC).date()
    )


def _item_record(issue: str, meta: dict[str, Any]) -> tuple[str, str]:
    """(PDF address, rights text) from an item's metadata, after checking it is the issue we think."""
    item_id = ITEMS[issue]
    try:
        found = {
            "item": [str(i) for i in meta["recordInfo"]["recordIdentifier"]],
            "title": [
                str(i)
                for rel in meta["relatedItem"]
                if rel.get("@type") == "parent"
                for i in rel["recordInfo"]["recordIdentifier"]
            ],
            "date": str(meta["originInfo"]["sortDate"])[:7],
            "name": meta["titleInfo"][0]["title"],
            "pdf": meta["location"]["pdfUrl"],
        }
        access = str(meta.get("accessCondition", ""))
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise fraser.DownloadError(f"item {item_id}: unexpected metadata ({exc!r})") from exc
    wanted = {
        "item": [str(item_id)],
        "title": [str(TITLE_ID)],
        "date": issue,
        "name": _month_year(issue),
    }
    for key, want in wanted.items():
        if found[key] != want:
            raise fraser.DownloadError(
                f"item {item_id} is not the {_month_year(issue)} issue: its {key} is {found[key]!r}, not {want!r}"
            )
    if (why := rights_problem(access)) is not None:
        raise fraser.RightsError(
            f"item {item_id} ({issue}): {why}, not FRASER's {fraser.RIGHTS_STATEMENT!r} or a "
            "pointer to the item's page; nothing was downloaded. Check the item by hand before going on."
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
    return pdf[0], access


def read_item(
    issue: str, log: Callable[[str], None], fetch: Callable[[str], str] | None = None
) -> tuple[str, str]:
    """(PDF address, rights text) for the issue, read from its item's metadata."""
    url = metadata_url(issue)

    def attempt() -> dict[str, Any]:
        try:
            meta = json.loads((fetch or fraser._fetch_text)(url))
        except ValueError as exc:
            raise fraser.DownloadError(f"not JSON: {exc}") from exc
        if not isinstance(meta, dict):
            raise fraser.DownloadError("metadata is not a JSON object")
        return meta

    return _item_record(issue, fraser._retrying(issue, url, log, attempt, lambda: None))


# --- download and render -----------------------------------------------------------------------


def download_issue(
    issue: str,
    root: Path,
    sources: Sources,
    pdf_url: str,
    access: str,
    log: Callable[[str], None],
) -> Sources:
    """Fetch the issue's PDF to a .part file, check it, record it, then rename it."""
    updated = sources

    def record(resolved: str, size: int, sha: str) -> None:
        nonlocal updated
        entry = SourceFile(
            issue=issue,
            url=pdf_url,
            resolved_url=resolved,
            retrieved=datetime.now(UTC).date(),
            size_bytes=size,
            sha256=sha,
            item_id=ITEMS[issue],
            item_url=item_url(issue),
            metadata_url=metadata_url(issue),
            access_condition=access,
        )
        order = list(ITEMS)
        files = sorted(
            [*(f for f in sources.files if f.issue != issue), entry], key=lambda f: order.index(f.issue)
        )
        updated = sources.model_copy(update={"files": files})
        fraser._write_record(root / "sources.json", updated)

    fraser._download(pdf_url, pdf_path(root, issue), issue, log, record)
    return updated


def render_issue(issue: str, root: Path, log: Callable[[str], None]) -> tuple[int, int]:
    """Render every page that is not already on disk; return (rendered now, already there)."""
    return fraser._render_pdf(pdf_path(root, issue), root, issue, log)


def build_manifest(root: Path, issues: list[str]) -> Manifest:
    """Read every rendered page of the issues back from disk. Raises FileNotFoundError if any is missing."""
    entries: list[IssueEntry] = []
    pages: list[PageEntry] = []
    for issue in issues:
        pdf = pdfium.PdfDocument(pdf_path(root, issue))
        try:
            entries.append(IssueEntry(issue=issue, pages=len(pdf)))
            for index in range(len(pdf)):
                fraser._check_stop()
                path = fraser._page_path(root, issue, index + 1)
                page = pdf[index]
                try:
                    if not fraser._page_complete(path, page):
                        raise FileNotFoundError(f"{path} is missing or incomplete")
                    with Image.open(path) as image:
                        width, height = image.size
                    pages.append(
                        PageEntry(
                            issue=issue,
                            page=index + 1,
                            sha256=fraser._sha256(path),
                            size_bytes=path.stat().st_size,
                            width=width,
                            height=height,
                            title_hint=fraser.title_hint(page),
                            **ocr_counts(occ._page_text(page)),
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
    return Manifest(renderer=renderer, issues=entries, pages=pages)


# --- the run -----------------------------------------------------------------------------------


def _load_sources(root: Path) -> Sources | None:
    path = root / "sources.json"
    return Sources.model_validate_json(path.read_text()) if path.is_file() else None


def _load_scan(root: Path) -> ScanCheck:
    path = root / "scan_check.json"
    if path.is_file():
        return ScanCheck.model_validate_json(path.read_text())
    return ScanCheck(
        rule=SCAN_RULE,
        issues=[],
        not_issued=[NotIssued(issue=i, reason=r) for i, r in NOT_ISSUED.items()],
    )


def _with_entry(scan: ScanCheck, entry: ScanEntry) -> ScanCheck:
    order = list(ITEMS)
    issues = sorted([*(e for e in scan.issues if e.issue != entry.issue), entry], key=lambda e: order.index(e.issue))
    return scan.model_copy(update={"issues": issues})


def progress(root: Path) -> str:
    """Where an ingest stands, read from disk."""
    sources = _load_sources(root)
    records = {f.issue: f for f in sources.files} if sources else {}
    done = [i for i in ITEMS if fraser._pdf_complete(pdf_path(root, i), records.get(i))]
    rendered = {
        i: len(list((root / "pages" / i).glob("p*.jpg")))
        for i in ITEMS
        if (root / "pages" / i).is_dir()
    }
    return (
        f"{len(done)} of {len(ITEMS)} PDFs complete; "
        f"{sum(rendered.values())} page images on disk across {len(rendered)} issues"
    )


def ingest(root: Path, log: Callable[[str], None] = print) -> int:
    """Download, scan-check, render and record every issue; 0 when all is complete, 1 if some issue failed."""
    with fraser._lock(root):
        stale = fraser._clear_temp_files(root)
        if stale:
            log(f"removed {stale} unfinished temp file(s) from an earlier run")
        log(f"start: {progress(root)}")
        sources = _load_sources(root)
        scan = _load_scan(root)
        failures: list[str] = []
        current = "starting"
        try:
            decided = {e.issue: e for e in scan.issues}
            wanted = [i for i in ITEMS if i not in decided or decided[i].outcome == "ingested"]
            records = {f.issue: f for f in sources.files} if sources else {}
            needed = [i for i in wanted if not fraser._pdf_complete(pdf_path(root, i), records.get(i))]
            # (PDF address, rights text) of every issue still to fetch, all read before the first fetch
            items: dict[str, tuple[str, str]] = {}
            if needed:
                rights = check_rights()
                log(f"rights: {rights.statement!r} confirmed on {TITLE_URL}")
                sources = (
                    sources
                    or Sources(
                        title=TITLE_NAME,
                        publisher="Board of Governors of the Federal Reserve System",
                        title_url=TITLE_URL,
                        rights=rights,
                        agency_basis=AgencyBasis(
                            basis=AGENCY_BASIS, citations=AGENCY_CITATIONS, checked=rights.checked
                        ),
                        files=[],
                    )
                ).model_copy(update={"rights": rights})
                for issue in needed:
                    current = issue
                    fraser._pause(fraser.POLITE_PAUSE)
                    try:
                        items[issue] = read_item(issue, log)
                    except fraser.DownloadError as exc:
                        failures.append(f"{issue}: {exc}")
                        log(f"  {issue}: FAILED, moving on ({exc})")
                log(f"rights: {len(items)} item(s) read; none names another statement")
            for issue in wanted:
                fraser._check_stop()
                current = issue
                records = {f.issue: f for f in sources.files} if sources else {}
                try:
                    if not fraser._pdf_complete(pdf_path(root, issue), records.get(issue)):
                        if issue not in items:
                            continue  # its metadata failed above
                        assert sources is not None
                        fraser._pause(fraser.POLITE_PAUSE)
                        sources = download_issue(issue, root, sources, *items[issue], log)
                    if issue not in decided:
                        layers = pdf_layers(pdf_path(root, issue))
                        entry = ScanEntry(
                            issue=issue,
                            pages=len(layers),
                            layers=layers,
                            gate=_gate(issue),
                            outcome=outcome_of(issue, layers),
                        )
                        scan = _with_entry(scan, entry)
                        decided[issue] = entry
                        fraser._write_record(root / "scan_check.json", scan)
                        shown = ", ".join(f"{n} {name}" for name, n in entry.counts().items() if n)
                        log(f"  {issue}: scan check, {entry.pages} pages: {shown}")
                        if entry.outcome == "skipped":
                            log(
                                f"  {issue}: SKIPPED, not every page passes the scan check "
                                f"(failing pages: {entry.failing[:12]}{' …' if len(entry.failing) > 12 else ''})"
                            )
                    if decided[issue].outcome == "ingested":
                        render_issue(issue, root, log)
                except (fraser.DownloadError, OSError, pdfium.PdfiumError) as exc:
                    failures.append(f"{issue}: {exc}")
                    log(f"  {issue}: FAILED, moving on ({exc})")
        except fraser.Stopped:
            fraser._clear_temp_files(root)
            log(
                f"stopped while on {current}. {progress(root)}. Nothing is half-written; rerun to resume."
            )
            return 130
        if failures:
            log(f"{len(failures)} issue(s) failed, manifest not written:")
            for line in failures:
                log(f"  {line}")
            return 1
        ingested = ingested_issues(scan)
        try:
            manifest = build_manifest(root, ingested)
        except fraser.Stopped:
            log(f"stopped while building the manifest. {progress(root)}. Rerun to resume.")
            return 130
        fraser._write_record(root / "manifest.json", manifest)
        fraser._write_record(root / "split.json", current_split(ingested))
        skipped = [e.issue for e in scan.issues if e.outcome == "skipped"]
        log(
            f"done: {len(manifest.pages)} pages in {len(ingested)} issues"
            f"{f' (skipped by the scan check: {skipped})' if skipped else ''}; "
            "sources.json, scan_check.json, manifest.json, split.json written"
        )
        return 0


# --- verify ------------------------------------------------------------------------------------


def verify(root: Path, log: Callable[[str], None] = print) -> int:
    """Offline: the committed records are sound and the files on disk match them. 0 if so."""
    problems: list[str] = []
    try:
        sources = Sources.model_validate_json((root / "sources.json").read_text())
        scan = ScanCheck.model_validate_json((root / "scan_check.json").read_text())
        manifest = Manifest.model_validate_json((root / "manifest.json").read_text())
        split = Split.model_validate_json((root / "split.json").read_text())
    except (OSError, ValueError) as exc:
        log(f"FAIL: cannot read the records: {exc}")
        return 1
    problems += check_sources(sources) + check_scan(scan) + check_manifest(manifest, scan)
    problems += check_split(split, ingested_issues(scan))

    records = {f.issue: f for f in sources.files}
    counts = {e.issue: e.pages for e in manifest.issues}
    checked = {e.issue: e.pages for e in scan.issues}
    fill = "run `uv run python -m archivist.ingest.fraser --source frb` to fetch and render what is missing"
    for issue in ITEMS:
        path = pdf_path(root, issue)
        if issue not in records or not path.is_file():
            problems.append(f"{issue}: PDF not on disk; {fill}")
            continue
        if not fraser._pdf_complete(path, records[issue]):
            problems.append(
                f"{issue}: PDF does not match sources.json (size, sha256 or it does not open)"
            )
            continue
        pages = fraser._opens(path)
        if pages != checked.get(issue):
            problems.append(f"{issue}: PDF page count differs from the scan check")
        if issue in counts and pages != counts[issue]:
            problems.append(f"{issue}: PDF page count differs from the manifest")
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
    skipped = [e.issue for e in scan.issues if e.outcome == "skipped"]
    log(
        f"ok: {len(sources.files)} PDFs and {len(manifest.pages)} page images match their records"
        f"{f'; skipped by the scan check: {skipped}' if skipped else ''}"
    )
    return 0
