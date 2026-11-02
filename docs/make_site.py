"""Assemble the published site: a landing page at its root, the review app at /ui/, the recorded runs it
shows and nothing else.

    python docs/make_site.py --out _site         # copy the site into a new, empty folder
    python docs/make_site.py --list              # print the files it would hold; copy nothing
    python docs/make_site.py --write-proof       # rewrite docs/landing_proof.json from git (see below)

The GitHub Pages workflow (.github/workflows/pages.yml) runs this on every push to main and
publishes the folder. The files are found by following what the app itself loads, so nothing is
listed by hand and nothing the app does not load is shipped:

  * ui/index.html, what it links, the modules those import and what the stylesheets name (the
    fonts). Only static imports are followed: main.js imports the local live-reading code
    (ui/js/live/) only when the page carries <meta name="archivist-live">, which the published
    site never does (D12, D13), so that code and its stylesheet are not part of the site;
  * data/bundles/index.json, each bundle it lists, the truth file next to a bundle that has one,
    and every scan a bundle names;
  * the Geist licence, which the font's licence requires to travel with it;
  * the landing page: an index.html at the top, written by docs/landing.py with every number in it read from
    a committed result file, and its stylesheet, script and logos (docs/landing/, assets/brand/). It reads
    git for the pre-registration dates, so the Pages checkout has full history; where there is no git (the
    Docker image) it reads docs/landing_proof.json, which tests/test_landing.py proves equal to git's answer.
    The app stays at /ui/, unchanged.

Nothing held-out is ever published: a path, a run or a stage that says so is refused, and so is any
run whose stage is not one this script has been told is published (the synthetic test pages and the
development pages). A collection added later has to be allowed here on purpose, by the project owner
(CLAUDE.md, P31 milestone 3). The script reads only the repository's files and makes no request.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import landing  # noqa: E402  (docs/landing.py: the page at the site's root)

ROOT = Path(__file__).resolve().parents[1]

APP = "ui/index.html"
BUNDLES = "data/bundles"
HOME = landing.HOME  # the view Watch it work opens
LICENCES = ("ui/fonts/GEIST-OFL.txt",)  # the OFL: the licence is shipped with the fonts it covers
PUBLISHED_STAGES = frozenset({"test", "development"})
HELD_OUT = re.compile(r"held[-_ ]?out", re.IGNORECASE)

LINK = re.compile(r'\b(?:href|src)="([^"]+)"')
IMPORT = re.compile(r"""\bfrom\s+["'](\.{1,2}/[^"']+)["']""")
CSS_URL = re.compile(r"""url\(\s*["']?([^)"']+?)["']?\s*\)""")
CSS_IMPORT = re.compile(r"""@import\s+["']([^"']+)["']""")

Refused = landing.Refused  # something that must not be published, or a file the site names that is not there


def _local(reference: str) -> bool:
    return not (
        reference.startswith(("#", "data:", "//", "mailto:", "javascript:"))
        or re.match(r"[a-z][a-z0-9+.-]*:", reference, re.IGNORECASE)
    )


def _inside(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise Refused(f"{path} is outside the repository") from None


def _need(root: Path, source: str, reference: str) -> str:
    """The repository path a reference in `source` names, which must exist."""
    target = (root / source).parent / reference.split("#")[0].split("?")[0]
    path = _inside(root, target)
    if not (root / path).is_file():
        raise Refused(f"{source} names {reference}, which is not a file ({path})")
    return path


def app_files(root: Path = ROOT) -> list[str]:
    """Every file the app loads, from ui/index.html: links, static imports and stylesheet urls."""
    seen: dict[str, None] = {}
    queue = [APP]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        if not (root / current).is_file():
            raise Refused(f"{current} is not a file")
        seen[current] = None
        kind = Path(current).suffix  # a font or an image is shipped, not read
        if kind not in (".html", ".js", ".css"):
            continue
        text = (root / current).read_text(encoding="utf-8")
        if kind == ".html":
            found = LINK.findall(text)
        elif kind == ".js":
            found = IMPORT.findall(text)
        else:
            found = CSS_URL.findall(text) + CSS_IMPORT.findall(text)
        queue += [_need(root, current, ref) for ref in found if _local(ref)]
    return sorted(seen)


def _check_not_held_out(*labels: object) -> None:
    for label in labels:
        if HELD_OUT.search(str(label)):
            raise Refused(f"{label!r} names a held-out run or path, which is never published")


def data_files(root: Path = ROOT) -> list[str]:
    """The index, each bundle it lists, the truth file beside one that has it and every scan named."""
    index_path = f"{BUNDLES}/index.json"
    index = json.loads((root / index_path).read_text(encoding="utf-8"))
    seen: dict[str, None] = {index_path: None}
    for run in index["runs"]:
        _check_not_held_out(*(run.get(k) for k in ("run_id", "path", "split", "stage", "collection")))
        if run.get("stage") not in PUBLISHED_STAGES:
            raise Refused(
                f"run {run.get('run_id')!r} has stage {run.get('stage')!r}; only "
                f"{sorted(PUBLISHED_STAGES)} are published (docs/make_site.py, PUBLISHED_STAGES)"
            )
        bundle = _need(root, index_path, run["path"])
        seen[bundle] = None
        if run.get("truth"):
            seen[_need(root, bundle, "truth.json")] = None
        data = json.loads((root / bundle).read_text(encoding="utf-8"))
        _check_not_held_out(*(data["run"].get(k) for k in ("run_id", "stage", "split", "images")))
        for page in data["pages"]:
            image = (page.get("image") or {}).get("url")
            if image:
                seen[_need(root, bundle, image)] = None
    for path in seen:
        _check_not_held_out(path)
    return sorted(seen)


def site_files(root: Path = ROOT, with_landing: bool = True) -> list[str]:
    """Every file the site holds, as repository paths (the top index.html is written, not copied)."""
    files = set(app_files(root)) | set(data_files(root))
    for path in (*LICENCES, *(landing.ASSETS if with_landing else ())):
        if not (root / path).is_file():
            raise Refused(f"{path} is not a file")
        files.add(path)
    return sorted(files)


def build(out: Path, root: Path = ROOT, with_landing: bool = True) -> list[str]:
    """Copy the site into `out` (new or empty), write its landing page, return every path in it.

    The page is written first, so that a number it cannot read stops the build before anything is copied;
    `with_landing=False` builds the app and its data alone, which the tests of what is published use on small
    repositories."""
    page = landing.render(root) if with_landing else None
    files = site_files(root, with_landing)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise Refused(f"{out} exists and is not empty; the site is built into an empty folder")
    for path in files:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / path, target)
    if page is not None:
        (out / "index.html").write_text(page, encoding="utf-8")
    return sorted([*files, "index.html"]) if page is not None else files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--out", type=Path, help="a new or empty folder to build the site in")
    where.add_argument("--list", action="store_true", help="print the files, copy nothing")
    where.add_argument("--write-proof", action="store_true", help=f"rewrite {landing.PROOF_FILE} from git")
    args = parser.parse_args(argv)
    try:
        if args.write_proof:
            facts = landing.git_facts()
            if facts is None:
                raise Refused("git has no full history here (a shallow clone, or no git) or lacks a tag the page cites")
            (ROOT / landing.PROOF_FILE).write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {landing.PROOF_FILE}")
            return 0
        if args.list:
            print("\n".join([*site_files(), "index.html (written)"]))
            return 0
        files = build(args.out)
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    size = sum((args.out / path).stat().st_size for path in files)
    print(f"{len(files)} files, {size / 1e6:.1f} MB, in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
