"""Which pages the local app may read, and the list it offers: development pages only (D14).

Only synthetic or public-domain pages are ever sent to a model, and free-credit traffic may be used
by Meta for product improvement, so the app reads a page only if it is one of these:

- a page of the Treasury Bulletin in a development issue of data/real/split.json, its scan matching
  the manifest's sha256 (a held-out issue is refused before its file is opened, and without
  split.json no real page is read at all: nothing is checked against a file that is not there);
- a synthetic development or validation page, data/dev or data/val (never the frozen test set).

That is archivist.templates.pages.resolve, the gate every template command goes through, with the
live app's own limits on top: a page of the Comptroller's reports or the Federal Reserve Bulletin
is refused too, since no approved template reads them. The server calls resolve() on every page it
is asked for, whatever the browser says, and builds its list here from the same split.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from archivist.ingest.fraser import DEFAULT_ROOT, pdf_name
from archivist.templates import pages
from archivist.templates.pages import Page, PageRefused

SYNTHETIC_ROOT = Path("data")
SWEEP_DIR = Path("results/real_test/development")  # the development side of the P29 runner
SYNTHETIC_SPLITS = ("dev", "val")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class LiveRefused(PageRefused):
    """The page is not one the app may read."""


@dataclass(frozen=True)
class LivePage:
    ref: str  # "1939-12_p053" or "dev/card-01-2"
    page_id: str  # as the field ids name it
    path: Path
    kind: str  # "treasury" or "synthetic"
    split: str  # "real", "dev" or "val"

    @property
    def page(self) -> Page:
        return Page(self.ref, self.page_id, self.path)


def resolve(
    ref: str,
    *,
    real_root: Path = DEFAULT_ROOT,
    synthetic_root: Path = SYNTHETIC_ROOT,
) -> LivePage:
    """The page `ref` names, if the app may read it; raises LiveRefused (before any file of a
    refused page is opened) if not."""
    if not isinstance(ref, str):
        raise LiveRefused("a page is named by a string")
    try:
        if pages.REAL.fullmatch(ref) is not None:
            if not (real_root / "split.json").is_file():
                raise LiveRefused(
                    f"{ref}: {real_root / 'split.json'} is missing, so the page cannot be "
                    "checked against the development split and is not read"
                )
            found = pages.resolve(ref, root=real_root, synthetic=synthetic_root)
            return LivePage(ref, found.page_id, found.path, "treasury", "real")
        if (match := pages.SYNTHETIC.fullmatch(ref)) is not None:
            found = pages.resolve(ref, root=real_root, synthetic=synthetic_root)
            return LivePage(ref, found.page_id, found.path, "synthetic", match["split"])
    except LiveRefused:
        raise
    except (PageRefused, OSError, ValueError) as error:  # a missing manifest, a bad split file
        raise LiveRefused(str(error)) from error
    raise LiveRefused(
        f"{ref}: only development pages are read here: a page of a development issue of the "
        "Treasury Bulletin (1939-12_p053) or a synthetic dev or val page (dev/card-01-2)"
    )


def issue_label(ref: str) -> str:
    """"December 1939, page 53" for "1939-12_p053"."""
    found = pages.REAL.fullmatch(ref)
    if found is None:
        return ref
    year, month = found["issue"].split("-")
    return f"{MONTHS[int(month) - 1]} {year}, page {int(found['page'])}"


def _read_before(sweep_dir: Path) -> set[str]:
    """The pages the development runner already read, whose answers are in the cache."""
    path = sweep_dir / "predictions.jsonl"
    if not path.is_file():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r'\s*\{"page_id":\s*"([^"]+)"', line)
        if match:
            out.add(match.group(1))
    return out


def downloaded(real_root: Path, issue: str, number: int) -> bool:
    """Whether the page's scan and its issue's archive PDF (whose OCR layer places the boxes) are on
    this machine: neither is committed, both come from archivist.ingest.fraser."""
    scan = real_root / "pages" / issue / f"p{number:03d}.jpg"
    return scan.is_file() and (real_root / "pdf" / pdf_name(issue)).is_file()


def _treasury(real_root: Path, sweep_dir: Path, limit: int) -> list[dict]:
    """Development pages that look like one of the five approved tables, by their OCR title hints
    in the manifest (plain code; the run itself classifies the page), the pages the development
    runner confirmed first."""
    try:
        split = json.loads((real_root / "split.json").read_text(encoding="utf-8"))
        manifest = json.loads((real_root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    from archivist.templates import real_test  # imported late: it loads the five templates

    doc_types = real_test._types(Path(real_test.CONFIG))
    development = set(split["development"])
    before = _read_before(sweep_dir)
    confirmed = _confirmed(sweep_dir)
    found = []
    for entry in manifest["pages"]:
        if entry["issue"] not in development:
            continue
        ref = f"{entry['issue']}_p{entry['page']:03d}"
        family = confirmed.get(ref)
        if family is None:
            hint = " ".join(entry.get("title_hint") or [])
            family = next(
                (n for n, t in doc_types.items() if real_test.title_match(t, hint) is not None),
                None,
            )
        if family is None:
            continue
        found.append(
            {
                "ref": ref,
                "label": issue_label(ref),
                "family": doc_types[family].template.identity.title,
                "read_before": ref in before,
                "scan": downloaded(real_root, entry["issue"], entry["page"]),
                "confirmed": ref in confirmed,
            }
        )
    found.sort(key=lambda p: (not p["confirmed"], p["ref"]))
    return found[:limit]


def _confirmed(sweep_dir: Path) -> dict[str, str]:
    path = sweep_dir / "titles.jsonl"
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("pattern") is not None:
            out[entry["page"]] = entry["classified_as"]
    return out


def _synthetic(synthetic_root: Path) -> list[dict]:
    images = synthetic_root / "dev" / "images"
    if not images.is_dir():
        return []
    found = []
    for path in sorted(images.glob("*.jpg")):
        kind = "payment memo" if path.stem.startswith("memo") else "ledger card"
        found.append(
            {
                "ref": f"dev/{path.stem}",
                "label": path.stem,
                "family": kind,
                "read_before": False,
                "scan": True,
                "confirmed": False,
            }
        )
    return found


def listing(
    *,
    real_root: Path = DEFAULT_ROOT,
    synthetic_root: Path = SYNTHETIC_ROOT,
    sweep_dir: Path = SWEEP_DIR,
    limit: int = 400,
) -> list[dict]:
    """The groups the picker offers: [{"id", "title", "pages": [...]}]. Every page in it is a
    development page; the list is built from the development split and nothing else."""
    groups = [
        {
            "id": "treasury",
            "title": "US Treasury Bulletin, development issues",
            "note": "Public-domain scans (FRASER) whose printed title matches an approved table.",
            "pages": _treasury(real_root, sweep_dir, limit),
        },
        {
            "id": "synthetic",
            "title": "Synthetic development pages",
            "note": "Ledger cards and payment memos made for the project; no real data.",
            "pages": _synthetic(synthetic_root),
        },
    ]
    return [g for g in groups if g["pages"]]
