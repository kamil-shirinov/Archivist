"""The published site (docs/make_site.py) and the workflow that publishes it (.github/workflows/pages.yml).

The site is exactly the files the review app loads, the bundles and scans it shows, and the landing page
at its root (tests/test_landing.py tests the page itself) with its few files, and nothing held-out. The
last test runs the assembled folder in a real browser, from the /Archivist/ path GitHub Pages serves it
under, from the landing page through every view and every run: nothing it asks for may be missing, and
every app file the site ships must have been used.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from browser import Browser, find_browser, serve

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"

spec = importlib.util.spec_from_file_location("make_site", ROOT / "docs" / "make_site.py")
site = importlib.util.module_from_spec(spec)
sys.modules["make_site"] = site
spec.loader.exec_module(site)

ALLOWED = ("ui/", "data/bundles/", "data/pages/", "docs/landing/", "assets/brand/")
NEVER = (
    "ui/js/live/",  # the local live-reading code: the published site has no live mode (D13)
    "ui/css/live.css",
    "ui/mockup/",
    "ui/schema/",
    "ui/screenshots/",
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The site as GitHub Pages serves this repository: a folder called Archivist."""
    top = tmp_path_factory.mktemp("pages")
    files = site.build(top / "Archivist")
    return top, files


def test_the_site_holds_only_the_app_the_bundles_and_the_scans_they_name(built):
    top, files = built
    on_disk = sorted(p.relative_to(top / "Archivist").as_posix() for p in (top / "Archivist").rglob("*") if p.is_file())
    assert on_disk == files, "build() reports what it wrote"
    for path in files:
        assert path == "index.html" or path.startswith(ALLOWED), path
        assert not any(path.startswith(n) for n in NEVER), path
        assert not site.HELD_OUT.search(path), path
    # the scans are the ones the bundles name, no more and no fewer
    named = set()
    for run in json.loads((ROOT / "data/bundles/index.json").read_text())["runs"]:
        bundle = ROOT / "data/bundles" / run["path"]
        for page in json.loads(bundle.read_text())["pages"]:
            named.add((bundle.parent / page["image"]["url"]).resolve().relative_to(ROOT).as_posix())
    assert {p for p in files if p.startswith("data/pages/")} == named
    assert len(named) == 161
    # the licence travels with the fonts it covers
    assert "ui/fonts/GEIST-OFL.txt" in files
    # what the app is told it can load from the same place is all there
    html = (top / "Archivist/ui/index.html").read_text()
    for ref in re.findall(r'(?:href|src)="([^"#:][^":]*)"', html):
        assert (top / "Archivist/ui" / ref).is_file(), ref


def test_the_top_page_is_the_landing_page_and_the_app_stays_at_ui(built):
    top, _ = built
    page = (top / "Archivist/index.html").read_text()
    assert "The archive that shows its work." in page, "the landing page, not a redirect"
    assert "location.replace" not in page
    assert 'href="ui/#replay"' in page, "Watch it work opens the app on the replay"
    assert (top / "Archivist/ui/index.html").is_file()


def test_the_only_dynamic_import_is_the_local_live_code():
    """Static imports are what the site follows; a second dynamic import would escape it."""
    dynamic = []
    for js in (ROOT / "ui" / "js").rglob("*.js"):
        for match in re.finditer(r"\bimport\s*\(\s*[\"']([^\"']+)", js.read_text()):
            dynamic.append((js.relative_to(ROOT).as_posix(), match.group(1)))
    assert dynamic == [("ui/js/main.js", "./live/live.js")], dynamic
    main = (ROOT / "ui/js/main.js").read_text()
    assert "meta[name=\"archivist-live\"]" in main
    assert "archivist-live" not in (ROOT / "ui/index.html").read_text(), "only the local server adds it"


def _repo(tmp_path, runs, bundle_run=None, images=("../../pages/x/p.jpg",)):
    """A small repository: the app's index page and an index of `runs`, each with one bundle."""
    tmp_path.mkdir()
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui/index.html").write_text("<!doctype html><title>x</title>")
    (tmp_path / "ui/fonts").mkdir()
    (tmp_path / "ui/fonts/GEIST-OFL.txt").write_text("licence")
    (tmp_path / "data/bundles").mkdir(parents=True)
    (tmp_path / "data/pages/x").mkdir(parents=True)
    (tmp_path / "data/pages/x/p.jpg").write_bytes(b"jpg")
    (tmp_path / "data/bundles/index.json").write_text(json.dumps({"runs": runs}))
    for run in runs:
        folder = tmp_path / "data/bundles" / run["run_id"]
        folder.mkdir(exist_ok=True)
        body = {"run": bundle_run or {"run_id": run["run_id"], "stage": run["stage"]}, "pages": [{"image": {"url": u}} for u in images]}
        (folder / "bundle.json").write_text(json.dumps(body))
    return tmp_path


def _run(run_id="r1", stage="development", **more):
    return {"run_id": run_id, "path": f"{run_id}/bundle.json", "split": "real", "stage": stage, "collection": "C", **more}


def test_a_small_repository_builds(tmp_path):
    root = _repo(tmp_path / "repo", [_run()])
    files = site.build(tmp_path / "out", root, with_landing=False)
    assert files == [
        "data/bundles/index.json",
        "data/bundles/r1/bundle.json",
        "data/pages/x/p.jpg",
        "ui/fonts/GEIST-OFL.txt",
        "ui/index.html",
    ]


@pytest.mark.parametrize(
    "run",
    [
        _run("heldout-run", "development"),
        _run("held_out", "development"),
        _run("r1", "held_out"),
        _run("r1", "held-out"),
        _run("r1", "Held Out"),
        _run("r1", "measured"),  # a stage nobody has allowed
        _run("r1", "development", collection="the pre-registered test: held-out pages"),
    ],
)
def test_nothing_held_out_and_no_stage_nobody_allowed_is_published(tmp_path, run):
    root = _repo(tmp_path / "repo", [run])
    with pytest.raises(site.Refused):
        site.build(tmp_path / "out", root, with_landing=False)
    assert not (tmp_path / "out").exists(), "a refusal leaves nothing behind"


def test_a_held_out_path_or_a_held_out_bundle_is_refused(tmp_path):
    root = _repo(tmp_path / "a", [_run()], images=("../../pages/x/held_out/p.jpg",))
    (root / "data/pages/x/held_out").mkdir()
    (root / "data/pages/x/held_out/p.jpg").write_bytes(b"jpg")
    with pytest.raises(site.Refused, match="held-out"):
        site.build(tmp_path / "out", root, with_landing=False)
    root = _repo(tmp_path / "b", [_run()], bundle_run={"run_id": "r1", "stage": "development", "images": "data/real_held_out"})
    with pytest.raises(site.Refused, match="held-out"):
        site.build(tmp_path / "out2", root, with_landing=False)


def test_a_file_the_app_names_that_is_missing_stops_the_build(tmp_path):
    root = _repo(tmp_path / "a", [_run()], images=("../../pages/x/missing.jpg",))
    with pytest.raises(site.Refused, match="not a file"):
        site.build(tmp_path / "out", root, with_landing=False)


def test_the_site_is_built_only_into_an_empty_folder(tmp_path):
    root = _repo(tmp_path / "a", [_run()])
    (tmp_path / "out").mkdir()
    (tmp_path / "out/keep.txt").write_text("mine")
    with pytest.raises(site.Refused, match="not empty"):
        site.build(tmp_path / "out", root, with_landing=False)
    assert (tmp_path / "out/keep.txt").read_text() == "mine"


# --- the workflow ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def test_the_workflow_publishes_on_every_push_to_main_and_nothing_else_triggers_it(workflow):
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as true
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"branches": ["main"]}


def test_the_workflow_checks_out_the_whole_history_so_the_tag_dates_can_be_read(workflow):
    checkout = next(s for s in workflow["jobs"]["build"]["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"] == {"fetch-depth": 0}, "the landing page's pre-registration dates come from git (tags included)"


def test_the_workflow_builds_with_the_script_and_uploads_what_it_wrote(workflow):
    build = workflow["jobs"]["build"]["steps"]
    runs = [s["run"] for s in build if "run" in s]
    assert runs == ["python3 docs/make_site.py --out _site"]
    upload = next(s for s in build if s.get("uses", "").startswith("actions/upload-pages-artifact@"))
    assert upload["with"] == {"path": "_site"}
    assert workflow["jobs"]["deploy"]["needs"] == "build"
    assert any(s.get("uses", "").startswith("actions/deploy-pages@") for s in workflow["jobs"]["deploy"]["steps"])


def test_the_workflow_holds_no_secret_and_asks_for_the_least(workflow):
    text = WORKFLOW.read_text()
    assert "secrets." not in text and "${{ env." not in text
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}
    assert "permissions" not in workflow["jobs"]["build"], "the build job keeps the read-only default"
    assert workflow["concurrency"]["cancel-in-progress"] is False


# --- the site, run -----------------------------------------------------------------------------------

TOUR = [
    "#overview",
    "#review",
    "#accounts",
    "#acct-84608901",
    "#transactions",
    "#documents",
    "#doc-card-01-2",
    "#replay-card-01-2",
    "#accuracy",
    "#types",
    "?run=test-archivist-B#overview",
    "?run=treasury-development#documents",
    "?run=treasury-development#doc-1939-12_p053",
    "?run=treasury-development#types",
]


@pytest.mark.skipif(find_browser() is None, reason="no Chromium or Chrome found (set ARCHIVIST_BROWSER)")
def test_the_published_site_runs_from_its_own_files_alone(built):
    top, files = built
    with serve(top) as base, Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/Archivist/", dark=False)
        # the top page is the landing page; Watch it work takes the visitor to the app, on the replay
        tab.wait_for("!!document.querySelector('h1') && document.querySelectorAll('.rp-log li').length === 7", 30)
        assert tab.eval("location.pathname") == "/Archivist/"
        assert tab.eval("document.querySelector('h1').textContent") == "The archive that shows its work."
        tab.eval("document.querySelector('.hero .btn.primary').click()")
        tab.wait_for("location.pathname === '/Archivist/ui/' && document.documentElement.dataset.ready === '1'", 60)
        assert tab.eval("location.hash") == "#replay"
        tab.wait_for("!!document.querySelector('#wstage img')?.complete && document.querySelectorAll('#w-steps li').length === 7", 30)
        assert tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)") == ["v-replay"]
        assert tab.eval("document.querySelector('meta[name=\"archivist-live\"]')") is None
        for stop in TOUR:
            tab.open(f"{base}/Archivist/ui/{stop}", dark=True)
            tab.wait_for("document.documentElement.dataset.ready === '1'", 60)
            tab.pump(0.4)
            assert tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).length") == 1, stop
        assert tab.errors == [], "no console error and no request the site could not answer"
        # every request went to the site, and every app file the site ships was one of them
        requested = set()
        for url in tab.requests:
            if url.startswith(base):
                path = url.removeprefix(f"{base}/Archivist/").split("?")[0].split("#")[0]
                requested.add(path + "index.html" if path == "" or path.endswith("/") else path)
        assert [u for u in tab.requests if not u.startswith((base, "data:"))] == []
        shipped_app = {f for f in files if f.startswith("ui/") and f != "ui/fonts/GEIST-OFL.txt"}
        assert shipped_app <= requested, f"shipped and never loaded: {sorted(shipped_app - requested)}"
        assert requested <= set(files), f"loaded and not shipped: {sorted(requested - set(files))}"
