"""The landing page at the published site's root (docs/landing.py, P51).

Every number on it comes from a committed file, and these tests are what keeps it so: each marked fact
(data-fact) is recomputed here, straight from the files, and must be what the page says; a digit anywhere on
the page that is not inside a fact fails; and the page may call nothing. Then the page is run in a browser:
its replay plays by itself and can be paused, a visitor who asked for reduced motion gets the settled page,
and it fits a phone, light and dark.
"""

import importlib.util
import json
import re
import subprocess
import sys
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest

from browser import Browser, find_browser, serve

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("make_site", ROOT / "docs" / "make_site.py")
site = importlib.util.module_from_spec(spec)
sys.modules["make_site"] = site
spec.loader.exec_module(site)
landing = site.landing

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "title"}


class Page(HTMLParser):
    """The page's marked facts by key, and the digits that stand outside any of them."""

    def __init__(self) -> None:
        super().__init__()
        self.facts: dict[str, list[str]] = {}
        self.refs: list[str] = []
        self.stray: list[str] = []
        self.urls: list[str] = []
        self.stack: list[tuple[str, str | None, str | None]] = []  # tag, fact key, what an ok region is
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in ("href", "src"):
            if attrs.get(name):
                self.urls.append(attrs[name])
        if tag in VOID:
            return
        if tag in SKIP:
            self.skip += 1
        key = attrs.get("data-fact")
        if key is not None:
            self.facts.setdefault(key, []).append("")
        self.stack.append((tag, key, attrs.get("data-ok")))
        if attrs.get("data-ok") == "ref":
            self.refs.append("")

    def handle_startendtag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.urls.append(value)

    def handle_endtag(self, tag):
        if tag in VOID or not self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            if top[0] in SKIP:
                self.skip -= 1
            if top[0] == tag:
                break

    def handle_data(self, data):
        if self.skip:
            return
        keys = [k for _, k, _ in self.stack if k is not None]
        if keys:
            self.facts[keys[-1]][-1] += data
        if any(ok == "ref" for _, _, ok in self.stack):
            self.refs[-1] += data
        if re.search(r"\d", data) and not keys and not any(ok for _, _, ok in self.stack):
            self.stray.append(data.strip())


def parse(text: str) -> Page:
    page = Page()
    page.feed(text)
    return page


@pytest.fixture(scope="module")
def html_text():
    return landing.render(ROOT)


@pytest.fixture(scope="module")
def page(html_text):
    return parse(html_text)


# --- what the files say ----------------------------------------------------------------------------------


def jload(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def pc(x: float, places: int = 2) -> str:
    return f"{x * 100:.{places}f}%"


def n(x: int) -> str:
    return f"{x:,}"


def ci(interval) -> str:
    return f"{pc(interval[0], 1)}–{pc(interval[1], 1)}"


def when(stamp: str) -> str:
    from datetime import datetime, timezone

    t = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    return f"{t.day} {('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')[t.month - 1]} {t.year}, {t:%H:%M} UTC"


def diagnosis_counts(heading: str) -> dict[str, list[int]]:
    """{layout: [wrong, drift, row, format, misalignment, digit, other]} of a table's All row."""
    text = (ROOT / "results/real_test/held_out/diagnosis.md").read_text(encoding="utf-8")
    block = text[text.index(f"#### {heading}") :].split("\n####", 1)[0].split("\n## ", 1)[0]
    found = {}
    for layout, row in re.findall(r"^\| (kept|left out) \| \*\*All\*\* \|((?: \d+ \|){7})", block, re.M):
        found[layout] = [int(c) for c in row.strip(" |").split("|")]
    return found


def expected() -> dict[str, str]:
    report = jload("results/test_report.json")
    hyp = {k: v["numbers"] for k, v in report["hypotheses"].items()}
    cfg = report["configurations"]
    base, a, b = cfg["baseline"]["stats"], cfg["A"]["stats"], cfg["B"]["stats"]
    alone = cfg["B"]["extraction_alone"]
    h1, h2, h3, h4, h5 = (hyp[k] for k in ("H1", "H2", "H3", "H4", "H5"))
    threshold = lambda x: f"{x * 100:g}%"  # noqa: E731
    e = {
        "stat.a_wrong": pc(h1["headline"]["rate"]),
        "stat.base_wrong": pc(h1["baseline"]["rate"]),
        "stat.a_wrong_n": f"{h1['headline']['wrong']} of {n(h1['headline']['accepted'])}",
        "stat.base_wrong_n": f"{h1['baseline']['wrong']} of {n(h1['baseline']['accepted'])}",
        "stat.caught": pc(h2["rate"]),
        "stat.caught_n": f"{h2['caught']} of {h2['wrong']}",
        "stat.base_caught_n": f"{base['errors_caught']} of {base['n_wrong']}",
        "stat.open_wrong": pc(h4["rate"]),
        "stat.open_wrong_n": f"{h4['wrong']} of {n(h4['accepted'])}",
        "stat.open_base": pc(alone["error_rate_accepted"]),
        "stat.open_base_n": f"{alone['errors_missed']} of {n(alone['n_accepted'])}",
        "test.pages": n(report["n_pages"]),
        "test.fields": n(report["n_fields"]),
        "test.review": pc(h3["rate"]),
        "test.review_n": f"{n(h3['review'])} of {n(h3['fields'])}",
        "test.target": threshold(h3["threshold"]),
        "limit.h3": pc(h3["rate"]),
        "limit.h3_target": threshold(h3["threshold"]),
        "limit.h5": pc(h5["rate"]),
        "limit.h5_n": f"{h5['found']} of {h5['planted']}",
        "limit.h5_target": threshold(h5["threshold"]),
        "hw.wrong.hosted": pc(h1["headline"]["rate"]),
        "hw.wrong.open": pc(h4["rate"]),
        "hw.caught.hosted": pc(h2["rate"]),
        "hw.caught.open": pc(b["catch_rate"]),
        "hw.review.hosted": pc(h3["rate"]),
        "hw.review.open": pc(b["review_rate"]),
    }
    for key, who in (("hosted", "A"), ("open", "B")):
        e[f"hw.cost.{key}"] = f"${cfg[who]['cost']['per_page_usd']:.4f}"
    e["limit.cost_a"], e["limit.cost_b"] = e["hw.cost.hosted"], e["hw.cost.open"]
    assert a["n_review"] == h3["review"]

    runs = [json.loads((ROOT / f"results/runs/{name}/run.json").read_text()) for name in ("test-baseline", "test-archivist-A", "test-baseline-open", "test-archivist-B", "test-archivist-C")]
    first, last = min(r["started_at"] for r in runs), max(r["finished_at"] for r in runs)
    assert first[:10] == last[:10], "the test ran on one day"
    e["test.date"] = when(first).split(",")[0]

    v1, ow = jload("results/real_test/held_out/score/score.json"), jload("results/real_openw/held_out/score/score.json")
    for key, label in (("real.kept", "kept/as_run"), ("real.left", "left_out/as_run")):
        o = v1["labels"][label]["overall"]
        for name, field in (("single", "single_read_error"), ("archivist", "archivist_error"), ("caught", "catch_rate")):
            e[f"{key}.{name}"] = pc(o[field]["value"], 1)
            e[f"{key}.{name}.ci"] = ci(o[field]["ci"])
    o = ow["open_weights"]["kept/as_run"]["overall"]
    for name, field in (("single", "single_read_error"), ("archivist", "archivist_error"), ("caught", "catch_rate")):
        e[f"open.{name}"] = pc(o[field]["value"], 1)
        e[f"open.{name}.ci"] = ci(o[field]["ci"])
    kept = v1["labels"]["kept/as_run"]
    e["real.cells"] = n(kept["cells"])
    e["real.left_cells"] = n(v1["labels"]["left_out/as_run"]["cells"])
    e["real.blank"] = n(kept["by_choice"]["blank"])
    e["open.target"] = e["hw.target"] = e["limit.o1_target"] = threshold(ow["o1"]["threshold"])
    e["hw.o1"] = pc(ow["o1"]["value"], 1)
    e["hw.real.hosted"] = e["real.kept.archivist"]
    e["hw.real.open"] = e["open.archivist"]
    every = v1["every_cell"]["kept/as_run"]["overall"]
    e["limit.model_box"], e["limit.ocr_box"], e["limit.grid_box"] = (pc(every[k]["value"], 1) for k in ("boxed_model", "boxed_ocr", "boxed_grid"))
    e["limit.pages"] = str(v1["sam"]["pages"])
    e["limit.changed"] = f"{len(v1['both_ways_pages'])} of {v1['sam']['pages']}"

    for config, who, heading in (
        ("v1", "single", "Version 1, wrong values in the single read"),
        ("v1", "accepted", "Version 1, wrong values Archivist accepted"),
        ("ow", "single", "Open weights, wrong values in the single read"),
        ("ow", "accepted", "Open weights, wrong values Archivist accepted"),
    ):
        rows = diagnosis_counts(heading)
        wrong, drift, row, fmt, mis, digit, other = rows["kept"]
        e[f"diag.{config}.{who}.wrong"] = str(wrong)
        e[f"diag.{config}.{who}.layout drift"] = str(drift)
        e[f"diag.{config}.{who}.format only"] = str(fmt)
        e[f"diag.{config}.{who}.reading errors"] = str(row + mis + digit + other)
    left, left_acc = diagnosis_counts("Version 1, wrong values in the single read")["left out"], diagnosis_counts("Version 1, wrong values Archivist accepted")["left out"]
    kept_s, kept_a = diagnosis_counts("Version 1, wrong values in the single read")["kept"], diagnosis_counts("Version 1, wrong values Archivist accepted")["kept"]
    e["diag.left.single"] = f"{left[3]} of {left[0]}"
    e["diag.left.accepted"] = f"{left_acc[3]} of {left_acc[0]}"
    e["diag.kept.drift"] = f"{kept_s[1]} of {kept_s[0]}"
    e["diag.kept.drift_acc"] = f"{kept_a[1]} of {kept_a[0]}"
    e["diag.kept.reading"] = f"{sum(kept_s[2:3]) + sum(kept_s[4:])} of {kept_s[0]}"
    e["diag.kept.reading_acc"] = f"{sum(kept_a[2:3]) + sum(kept_a[4:])} of {kept_a[0]}"

    bundle = jload("data/bundles/treasury-development/bundle.json")
    fields = {f["field_id"]: f for f in bundle["fields"]}
    field = fields[landing.REPLAY_FIELD]
    page = next(p for p in bundle["pages"] if p["page_id"] == field["page_id"])
    steps = {s["key"]: s["facts"] for s in page["steps"]}
    others = [fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:{c}"]["value"] for c in ("admin", "to_retirement", "to_unemployment")]
    total = fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:total_exp"]["value"]
    assert sum(Decimal(x) for x in others) == Decimal(total)
    e["replay.value"], e["replay.reread"], e["replay.row"] = field["value"], field["reread"], field["row"]
    e["replay.sum"] = " + ".join(str(Decimal(x)) for x in others) + f" = {Decimal(total)}"
    e["replay.boxes"], e["replay.moved"] = str(steps["snap"]["boxes"]), str(steps["snap"]["moved"])
    e["replay.accepted"], e["replay.review"], e["replay.read"] = (str(steps["decide"]["accepted"]), str(steps["decide"]["review"]), str(steps["read"]["values"]))
    e["replay.year"] = page["issue"][:4]
    e["replay.issue"] = "December 1939"
    assert page["issue"] == "1939-12"
    e["replay.number"] = str(page["number"])
    doc_type = next(t for t in bundle["doc_types"] if t["name"] == page["doc_type"])
    e["replay.type"] = doc_type["title"]
    e["replay.column"] = next(c["printed"] for c in doc_type["columns"] if c["key"] == field["name"])
    e["replay.period"] = fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:period"]["value"].strip(" .")

    return e


def git(*args: str) -> str | None:
    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def full_history() -> bool:
    return git("rev-parse", "--is-shallow-repository") == "false"


def commit_of(*ref: str) -> tuple[str, str]:
    sha, stamp = git("log", "-1", "--format=%H %cI", *ref).split(" ", 1)
    return sha[:7], stamp


# --- the numbers ------------------------------------------------------------------------------------------


def test_every_marked_fact_is_what_its_file_says(page):
    want = expected()
    from_git = ("test.commit", "foot.first")  # checked against git, with the plans' dates, in test_the_dates_are_gits
    unknown = [k for k in page.facts if k not in want and not k.startswith("plan.") and k not in ("model", "docker", *from_git)]
    assert unknown == [], f"facts the test does not recompute: {unknown}"
    for key, texts in page.facts.items():
        if key in want:
            assert set(texts) == {want[key]}, key
    must = [k for k in want if k.startswith(("stat.", "test.", "real.kept", "real.cells", "open.", "replay.", "hw.", "limit."))]
    missing = [k for k in must if k not in page.facts]
    assert missing == [], f"facts the page should state: {missing}"


def test_the_three_numbers_are_the_report_s(html_text):
    assert "0.36%" in html_text and "93.65%" in html_text and "0.30%" in html_text, "the report's headline figures"


def test_no_digit_stands_outside_a_marked_fact(page):
    assert page.stray == [], "a number typed by hand: every digit on the page must be a fact read from a file"


def test_the_references_are_to_things_that_exist(page):
    refs = {r.strip() for r in page.refs}
    assert refs <= {"R1", "D19"}, refs
    assert "- R1:" in (ROOT / "PREREGISTRATION_REAL.md").read_text()
    assert re.search(r"^D19 .*Contributor", (ROOT / "DECISIONS.md").read_text(), re.M)


def test_the_models_are_the_ones_the_configs_name(page):
    ids = " ".join(re.findall(r'model_id\s*=\s*"([^"]+)"', "".join((ROOT / c).read_text() for c in landing.MODEL_CONFIGS))).lower()
    shown = {t.strip() for t in page.facts["model"]}
    assert shown == {"Muse Glimmer", "Muse Spark 1.3", "Muse Spark Open", "SAM 3.1"}
    for mark in ("muse-glimmer", "muse-spark-1.3", "muse-spark-open", "sam-3.1"):
        assert mark in ids


def test_the_docker_commands_are_the_readme_s(page):
    section = (ROOT / "README.md").read_text().split("## Run it yourself", 1)[1]
    block = re.search(r"```bash\n(.*?)```", section, re.S).group(1)
    assert page.facts["docker"] == ["\n".join(ln for ln in block.splitlines() if ln.startswith("docker "))]


@pytest.mark.skipif(not full_history(), reason="no full git history here")
def test_the_dates_are_gits(page):
    added = git("log", "--diff-filter=A", "--format=%H %cI", "--", "PREREGISTRATION.md").splitlines()[-1].split(" ", 1)
    assert page.facts["test.commit"] == [added[0][:7]]
    assert page.facts["plan.synthetic.0.sha"] == [added[0][:7]]
    assert page.facts["plan.synthetic.0.when"] == [when(added[1])]
    for plan, tags in (("real", ("prereg-real-treasury", "run-real-treasury")), ("openw", ("prereg-real-openw", "run-real-openw"))):
        for i, tag in enumerate(tags):
            sha, stamp = commit_of(f"refs/tags/{tag}^{{commit}}")
            assert page.facts[f"plan.{plan}.{i}.sha"] == [sha]
            assert page.facts[f"plan.{plan}.{i}.when"] == [when(stamp)]
    root = git("rev-list", "--max-parents=0", "HEAD").split()
    assert len(root) == 1
    sha, stamp = commit_of(root[0])
    assert page.facts["plan.first.sha"] == [sha] and page.facts["plan.first.when"] == [when(stamp)]
    assert page.facts["foot.first"] == [when(stamp).split(",")[0]]
    started = lambda p: json.loads((ROOT / p).read_text())  # noqa: E731
    assert page.facts["plan.real.2.when"] == [when(started("results/real_test/held_out/sweep.json")["started_at"])]
    assert page.facts["plan.openw.2.when"] == [when(started("results/real_openw/held_out/score/score.json")["run"]["started_at"])]
    assert page.facts["plan.synthetic.1.when"] == [when(started("results/runs/test-baseline/run.json")["started_at"])]


@pytest.mark.skipif(not full_history(), reason="no full git history here")
def test_the_committed_snapshot_is_what_git_says():
    """Where there is no git (the Docker image) the page reads docs/landing_proof.json; it must be git's answer."""
    assert json.loads((ROOT / landing.PROOF_FILE).read_text()) == landing.git_facts(ROOT), "run: python docs/make_site.py --write-proof"


def test_without_git_the_page_is_the_same(html_text, monkeypatch, capsys):
    monkeypatch.setattr(landing, "git_facts", lambda root=ROOT: None)
    assert landing.render(ROOT) == html_text
    assert landing.PROOF_FILE in capsys.readouterr().err


def test_no_git_and_no_snapshot_stops_the_build(tmp_path):
    with pytest.raises(landing.Refused, match="no git history"):
        landing.proof(tmp_path)


# --- the replay -------------------------------------------------------------------------------------------


def test_the_replays_value_is_an_accepted_one_with_a_rule_and_a_clean_loop():
    shown = landing.replay(ROOT)
    assert shown["field"]["field_id"] == landing.REPLAY_FIELD
    assert shown["models"] == ["Muse Spark 1.3", "SAM 3.1"], "only the models the run used"
    index = jload("data/bundles/index.json")
    assert next(r for r in index["runs"] if r["run_id"] == landing.REPLAY_RUN)["stage"] == "development"
    assert not shown["page"]["page_id"].startswith("held")


def test_a_value_that_no_longer_qualifies_is_refused():
    shown = landing.replay(ROOT)
    field, rules, page = dict(shown["field"]), [shown["rule"]], shown["page"]
    assert landing.qualifying(field, rules, page) == []
    assert "not accepted" in " ".join(landing.qualifying({**field, "status": "review"}, rules, page))
    assert "blind read" in " ".join(landing.qualifying({**field, "reread": "1"}, rules, page))
    assert "rule" in " ".join(landing.qualifying(field, [], page))
    assert "rule" in " ".join(landing.qualifying(field, [{**rules[0], "ok": False}], page))
    assert "covers" in " ".join(landing.qualifying({**field, "occluders": [{}]}, rules, page))
    assert "pen loop" in " ".join(landing.qualifying({**field, "loop": {**field["loop"], "kind": "underline"}}, rules, page))
    x0, y0, x1, y1 = field["loop"]["ink"]
    crossing = {**field["loop"], "d": f"M{(x0 + x1) / 2} {(y0 + y1) / 2}L{x1 + 30} {y1 + 30}"}
    assert "own ink" in " ".join(landing.qualifying({**field, "loop": crossing}, rules, page))


def test_the_replay_shows_a_development_page_only(html_text, page):
    assert "data/pages/real/1939-12_p025.jpg" in html_text
    local = [u for u in page.urls if not u.startswith(landing.REPO)]
    assert not re.search(r"held[-_ ]?out", " ".join(local), re.I)


# --- the corrected key ------------------------------------------------------------------------------------


def test_the_corrected_key_is_pending_until_its_file_exists(html_text):
    exists = [p for p in landing.CORRECTED.values() if (ROOT / p).is_file()]
    assert ("Pending, after the dash check" in html_text) == (not exists)


def test_a_corrected_key_is_shown_beside_the_official_result_when_its_file_exists():
    v1, ow = jload(landing.REAL_SCORE), jload(landing.OPEN_SCORE)
    labels = json.loads(json.dumps(v1["labels"]))
    for result in labels.values():
        for name in ("single_read_error", "archivist_error", "catch_rate"):
            result["overall"][name] = {"value": 0.0123, "ci": [0.0, 0.0456]}
    fixed = {"version_1": {"official": {"labels": v1["labels"]}, "corrected_key": {"labels": labels}}}
    card = landing.corrected_card(fixed)
    assert "1.2%" in card and "0.0%–4.6%" in card and "Open weights: pending, after the dash check" in card
    both = {**fixed, "open_weights": {"corrected_key": {"o1": {**ow["o1"], "value": 0.0099, "ci": [0.0, 0.02], "met": True}, "open_weights": {"kept/as_run": {"overall": ow["open_weights"]["kept/as_run"]["overall"]}}}}}
    card = landing.corrected_card(both)
    assert "target met" in card and "pending" not in card


# --- a page that calls nothing ----------------------------------------------------------------------------


def test_the_page_makes_no_request_of_its_own_to_another_site(html_text, page):
    outside = [u for u in page.urls if re.match(r"[a-z][a-z0-9+.-]*:", u, re.I)]
    assert outside, "the links to the repository"
    assert all(u.startswith(landing.REPO) for u in outside), outside
    requests = [u for u in page.urls if not u.startswith(landing.REPO)]
    assert all(not u.startswith(("//", "http")) for u in requests)
    assert "preconnect" not in html_text and "dns-prefetch" not in html_text
    script = (ROOT / "docs/landing/landing.js").read_text()
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "import(", "http:", "https:", "document.cookie"):
        assert forbidden not in script, forbidden
    css = (ROOT / "docs/landing/landing.css").read_text()
    assert not re.search(r"url\(\s*[\"']?(https?:|//)", css)
    assert "@import" not in css


def test_the_site_holds_the_page_its_files_and_no_result(tmp_path):
    out = tmp_path / "site"
    files = site.build(out)
    assert {"index.html", *landing.ASSETS} <= set(files)
    assert not [f for f in files if f.startswith("results/") or site.HELD_OUT.search(f)], "no result file and nothing held out is published"
    text = (out / "index.html").read_text()
    assert "The archive that shows its work." in text
    for ref in re.findall(r'(?:href|src)="([^"#:][^":]*)"', text):
        assert (out / ref.split("#")[0].split("?")[0]).exists(), ref
    assert "Pending, after the dash check" in text or all((ROOT / p).is_file() for p in landing.CORRECTED.values())
    assert 'href="ui/#replay"' in text, "Watch it work opens the app on the replay"
    assert (out / "ui/index.html").is_file(), "the app stays at /ui/"


def test_the_docker_image_is_let_in_everything_the_page_reads():
    """.dockerignore leaves everything out and lets back in what the build reads; the page reads more than the app."""
    allowed = [ln[1:].strip() for ln in (ROOT / ".dockerignore").read_text().splitlines() if ln.startswith("!")]
    reads = [
        landing.TEST_REPORT, landing.REAL_SCORE, landing.OPEN_SCORE, landing.DIAGNOSIS, landing.SWEEP, *landing.CORRECTED.values(),
        *landing.MODEL_CONFIGS, landing.PROOF_FILE, "README.md", *landing.ASSETS,
        "results/runs/test-baseline/run.json", "data/bundles/index.json", "ui/fonts/Geist-Variable.woff2",
    ]
    lost = [p for p in reads if not any(p == a or p.startswith(a.rstrip("/") + "/") for a in allowed)]
    assert lost == [], f"the Docker build cannot see: {lost}"


# --- the page, run ------------------------------------------------------------------------------------------

SCREENSHOTS = ROOT / "ui" / "screenshots"
needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Chromium or Chrome found (set ARCHIVIST_BROWSER)")
ONE_PAGE_WASH = "body::after{position:absolute!important;height:100%!important}"  # the wash is fixed: on a page-long shot it would stop at the window's foot


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    top = tmp_path_factory.mktemp("landing")
    site.build(top / "Archivist")
    with serve(top) as base, Browser() as browser:
        yield base + "/Archivist/", browser


def shown(tab) -> int:
    return tab.eval("document.querySelectorAll('.rp-log li.on').length")


@needs_browser
def test_the_replay_starts_by_itself_pauses_and_plays_again(served):
    base, browser = served
    tab = browser.tab()
    tab.open(base, dark=False)
    tab.wait_for("document.documentElement.classList.contains('play')", 10)
    tab.wait_for("document.querySelectorAll('.rp-log li.on').length >= 2", 20)  # it began without a click
    tab.eval("document.querySelector('[data-act=pause]').click()")
    held = shown(tab)
    tab.pump(2.8)
    assert shown(tab) == held, "paused"
    assert tab.eval("document.querySelector('[data-act=pause]').textContent") == "Resume"
    tab.eval("document.querySelector('[data-act=pause]').click()")
    tab.wait_for("document.querySelectorAll('.rp-log li.on').length === 7", 30)
    assert tab.eval("document.querySelector('.pen').classList.contains('on') && document.querySelector('.tick').classList.contains('on')")
    tab.wait_for("getComputedStyle(document.querySelector('.rp-count')).opacity === '1'", 5)
    tab.eval("document.querySelector('[data-act=replay]').click()")
    tab.pump(0.3)
    assert shown(tab) < 7, "Replay starts again from the beginning"
    tab.wait_for("document.querySelectorAll('.rp-log li.on').length === 7", 30)
    assert tab.errors == []
    assert [u for u in tab.requests if not u.startswith((base, "data:"))] == [], "no request off the site"


@needs_browser
def test_sections_fade_in_once_as_they_scroll_into_view(served):
    base, browser = served
    tab = browser.tab()
    tab.open(base, dark=False)
    tab.pump(0.6)
    assert tab.eval("getComputedStyle(document.querySelector('#limits')).opacity") == "0"
    tab.eval("document.querySelector('#limits').scrollIntoView()")
    tab.wait_for("getComputedStyle(document.querySelector('#limits')).opacity === '1'", 10)
    tab.eval("scrollTo(0, 0)")
    tab.pump(0.8)
    assert tab.eval("getComputedStyle(document.querySelector('#limits')).opacity") == "1", "once"


@needs_browser
def test_with_reduced_motion_the_page_is_its_settled_state(served):
    base, browser = served
    tab = browser.tab()
    tab.open(base, still=True)
    tab.pump(1.0)
    assert tab.eval("document.documentElement.classList.contains('play')") is False
    assert tab.eval("[...document.querySelectorAll('.rp-log li, .rp-count, .reveal, .rise')].every(e => getComputedStyle(e).opacity === '1')")
    assert tab.eval("document.getAnimations().length") == 0, "nothing moves"
    assert tab.eval("getComputedStyle(document.querySelector('.layer.pen')).strokeDashoffset") == "0px"
    tab.eval("document.querySelector('[data-act=replay]').click()")  # the visitor's own choice
    tab.wait_for("document.querySelectorAll('.rp-log li.on').length === 7", 30)
    assert tab.eval("document.getAnimations().length") == 0


@needs_browser
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("phone", [False, True], ids=["desktop", "phone"])
def test_the_page_fits_the_screen_in_light_and_dark(served, dark, phone):
    base, browser = served
    tab = browser.tab()
    width, height = (390, 844) if phone else (1440, 900)
    tab.open(base, width=width, height=height, dark=dark, mobile=phone, still=True)
    tab.pump(0.8)
    assert tab.eval("document.documentElement.scrollWidth") <= width, "no sideways scroll"
    assert tab.eval("[...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1 && !e.closest('svg, pre')).length") == 0
    background = tab.eval("getComputedStyle(document.body).backgroundColor")
    assert background == ("rgb(10, 11, 14)" if dark else "rgb(246, 246, 243)")
    assert tab.eval("getComputedStyle(document.querySelector('h1')).color") == ("rgb(232, 233, 237)" if dark else "rgb(22, 24, 29)")
    assert tab.eval("document.querySelector('h1').getBoundingClientRect().top < innerHeight / 2"), "the headline is in the first screen"
    assert tab.eval("document.querySelector('.hero .btn.primary').getBoundingClientRect().bottom < innerHeight + (500 * " + ("1" if phone else "0") + ")")
    name = f"landing-{'dark' if dark else 'light'}-{'phone' if phone else 'desktop'}"
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)  # gitignored: the screenshots are never committed
    tab.screenshot(SCREENSHOTS / f"{name}-first-screen.png")
    tab.eval(f"document.head.insertAdjacentHTML('beforeend', '<style>{ONE_PAGE_WASH}</style>')")
    tab.pump(0.3)
    tab.screenshot(SCREENSHOTS / f"{name}.png", full_page=True)
    assert tab.errors == []


@needs_browser
def test_watch_it_work_opens_the_app_on_the_replay(served):
    base, browser = served
    tab = browser.tab()
    tab.open(base, still=True)
    tab.eval("document.querySelector('.hero .btn.primary').click()")
    tab.wait_for("location.pathname.endsWith('/ui/') && document.documentElement.dataset.ready === '1'", 60)
    assert tab.eval("location.hash") == "#replay"
    assert tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)") == ["v-replay"]
