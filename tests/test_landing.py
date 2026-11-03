"""The landing page at the published site's root (docs/landing.py, P51; redesigned in P52).

Every number on it comes from a committed file, and these tests are what keeps it so: each marked fact
(data-fact) is recomputed here, straight from the files, and must be what the page says; a digit anywhere on
the page that is not inside a fact fails; and the page may call nothing. The redesign lost nothing: every fact
key and every sentence of P51's page is still on the page (tests/landing_content.py, tests/landing_p51.json), and
what a fair reader needs, the missed targets above all, is in the page's text and not behind a click or in a hidden
panel. Held-out results appear as aggregates only. The stylesheet may animate nothing but opacity and transform.
Then the page is run in a browser: its replay plays by itself and can be paused, the ledger's switch re-counts
every figure, a row, a step and a chart each do what they say, a theme change is revealed in a circle (or, where
the browser has no View Transitions, a cross-fade, and instantly with reduced motion), a visitor who asked for
reduced motion gets the settled page, and it fits a phone, light and dark.
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

import landing_content
from browser import Browser, find_browser, serve

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("make_site", ROOT / "docs" / "make_site.py")
site = importlib.util.module_from_spec(spec)
sys.modules["make_site"] = site
spec.loader.exec_module(site)
landing = site.landing

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "noscript", "title"}
OK_KINDS = {"ref", "step", "axis", "grid"}  # what a data-ok region may be: a name, a step's number, an axis label, the grid's size


class Page(HTMLParser):
    """The page's marked facts by key, the digits that stand outside any of them, and what is on it that is hidden."""

    def __init__(self) -> None:
        super().__init__()
        self.facts: dict[str, list[str]] = {}
        self.refs: list[str] = []
        self.oks: list[tuple[str, str]] = []
        self.stray: list[str] = []
        self.urls: list[str] = []
        self.stack: list[tuple[str, str | None, str | None, bool]] = []  # tag, fact key, what an ok region is, hidden
        self.skip = 0
        self.visible_facts: set[str] = set()  # facts not inside an element that has the hidden attribute
        self.visible_text: list[str] = []

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
        hidden = "hidden" in attrs
        if key is not None:
            self.facts.setdefault(key, []).append("")
            if not any(h for *_, h in self.stack) and not hidden:
                self.visible_facts.add(key)
        self.stack.append((tag, key, attrs.get("data-ok"), hidden))
        if attrs.get("data-ok"):
            self.oks.append((attrs["data-ok"], ""))
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
        keys = [k for _, k, _, _ in self.stack if k is not None]
        if keys:
            self.facts[keys[-1]][-1] += data
        if any(ok == "ref" for _, _, ok, _ in self.stack):
            self.refs[-1] += data
        if any(ok for _, _, ok, _ in self.stack):
            kind = [ok for _, _, ok, _ in self.stack if ok][-1]
            self.oks[-1] = (kind, self.oks[-1][1] + data)
        if not any(h for *_, h in self.stack):
            self.visible_text.append(data)
        if re.search(r"\d", data) and not keys and not any(ok for _, _, ok, _ in self.stack):
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


def ci(interval, places: int = 1) -> str:
    return f"{pc(interval[0], places)}–{pc(interval[1], places)}"


def thr(x: float) -> str:
    return f"{x * 100:g}%"


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


VARIANTS = ("kept/as_run", "left_out/as_run", "kept/failed_to_review", "left_out/failed_to_review")


def ledger_expected(report: dict, v1: dict, ow: dict) -> dict[str, str]:
    """Every fact the ledger can state, a superset: each row's two sides, with the interval, the counts and the dots.
    (value, interval, found, of) for the Archivist and the single read of each row, on each side."""
    cfg = report["configurations"]
    base, b, alone = cfg["baseline"]["stats"], cfg["B"]["stats"], cfg["B"]["extraction_alone"]
    h = {k: v["numbers"] for k, v in report["hypotheses"].items()}
    vk, ok = v1["labels"]["kept/as_run"]["overall"], ow["open_weights"]["kept/as_run"]["overall"]
    rows = {
        "h1": (2, "wrong", {
            "hosted": {"arch": (h["H1"]["headline"]["rate"], h["H1"]["headline"]["ci95"], h["H1"]["headline"]["wrong"], h["H1"]["headline"]["accepted"]),
                       "single": (h["H1"]["baseline"]["rate"], h["H1"]["baseline"]["ci95"], h["H1"]["baseline"]["wrong"], h["H1"]["baseline"]["accepted"])},
            "open": {"arch": (h["H4"]["rate"], h["H4"]["ci95"], h["H4"]["wrong"], h["H4"]["accepted"]),
                     "single": (alone["error_rate_accepted"], alone["error_rate_accepted_ci95"], alone["errors_missed"], alone["n_accepted"])}}),
        "h2": (2, "caught", {
            "hosted": {"arch": (h["H2"]["rate"], h["H2"]["ci95"], h["H2"]["caught"], h["H2"]["wrong"]),
                       "single": (base["catch_rate"], base["catch_rate_ci95"], base["errors_caught"], base["n_wrong"])},
            "open": {"arch": (b["catch_rate"], b["catch_rate_ci95"], b["errors_caught"], b["n_wrong"])}}),
        "h3": (2, "review", {
            "hosted": {"arch": (h["H3"]["rate"], h["H3"]["ci95"], h["H3"]["review"], h["H3"]["fields"]),
                       "single": (base["review_rate"], base["review_rate_ci95"], base["n_review"], base["n_fields"])},
            "open": {"arch": (b["review_rate"], b["review_rate_ci95"], b["n_review"], b["n_fields"])}}),
        "h5": (2, "flagged", {
            "hosted": {"arch": (h["H5"]["rate"], None, h["H5"]["found"], h["H5"]["planted"]),
                       "single": (base["source_error_recall"], None, base["source_errors_found"], base["n_source_errors"])},
            "open": {"arch": (b["source_error_recall"], None, b["source_errors_found"], b["n_source_errors"])}}),
        "r1": (1, "real", {
            "hosted": {"arch": (vk["archivist_error"]["value"], vk["archivist_error"]["ci"], None, None),
                       "single": (vk["single_read_error"]["value"], vk["single_read_error"]["ci"], None, None)},
            "open": {"arch": (ok["archivist_error"]["value"], ok["archivist_error"]["ci"], None, None),
                     "single": (ok["single_read_error"]["value"], ok["single_read_error"]["ci"], None, None)}}),
    }
    e: dict[str, str] = {}
    for row, (places, name, modes) in rows.items():
        for mode, whos in modes.items():
            for who, (value, interval, found, of) in whos.items():
                key = f"hw.{name}.{mode}" if who == "arch" else f"ledger.{row}.{mode}.single"
                e[key] = pc(value, places)
                if interval is not None:
                    e[key + ".ci"] = ci(interval, places)
                if found is not None:
                    e[f"ledger.{row}.{mode}.{who}.n"] = f"{n(found)} of {n(of)}"
                if round(value * 1000):
                    e[f"ledger.{row}.{mode}.{who}.dots"] = str(round(value * 1000))
    for row, mode, target in (("h1", "open", h["H4"]["threshold"]), ("h2", "hosted", h["H2"]["threshold"]), ("h3", "hosted", h["H3"]["threshold"]), ("h5", "hosted", h["H5"]["threshold"])):
        e[f"ledger.{row}.{mode}.target"] = thr(target)
    for mode, cells in (("hosted", v1["labels"]["kept/as_run"]), ("open", ow["open_weights"]["kept/as_run"])):
        out = cells["by_outcome"]
        e[f"ledger.r1.{mode}.cells"], e[f"ledger.r1.{mode}.pages"] = n(cells["cells"]), str(cells["pages"])
        for field, key in (("right", "right"), ("wrong", "wrong"), ("cant_read", "cant"), ("abstained", "abstained")):
            e[f"ledger.r1.{mode}.{key}"] = str(out[field])
    e["open.target.synthetic"] = thr(h["H4"]["threshold"])
    return e


def expected() -> dict[str, str]:
    report = jload("results/test_report.json")
    hyp = {k: v["numbers"] for k, v in report["hypotheses"].items()}
    cfg = report["configurations"]
    base, a = cfg["baseline"]["stats"], cfg["A"]["stats"]
    alone = cfg["B"]["extraction_alone"]
    h1, h2, h3, h4, h5 = (hyp[k] for k in ("H1", "H2", "H3", "H4", "H5"))
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
        "test.target": thr(h3["threshold"]),
        "limit.h3": pc(h3["rate"]),
        "limit.h3_target": thr(h3["threshold"]),
        "limit.h5": pc(h5["rate"]),
        "limit.h5_n": f"{h5['found']} of {h5['planted']}",
        "limit.h5_target": thr(h5["threshold"]),
        "hw.review.hosted": pc(h3["rate"]),
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
    e["open.target"] = e["hw.target"] = e["limit.o1_target"] = thr(ow["o1"]["threshold"])
    e["hw.o1"] = pc(ow["o1"]["value"], 1)
    every = v1["every_cell"]["kept/as_run"]["overall"]
    e["limit.model_box"], e["limit.ocr_box"], e["limit.grid_box"] = (pc(every[k]["value"], 1) for k in ("boxed_model", "boxed_ocr", "boxed_grid"))
    e["limit.pages"] = str(v1["sam"]["pages"])
    e["limit.changed"] = f"{len(v1['both_ways_pages'])} of {v1['sam']['pages']}"

    # the ledger: both sides of every row
    e.update(ledger_expected(report, v1, ow))

    # the interval's level and method, from the key's own name and from the real-scan plan
    level = [re.search(r"_ci(\d+)$", k).group(1) for k in a if re.search(r"_ci(\d+)$", k)][0]
    plan = (ROOT / "PREREGISTRATION_REAL.md").read_text()
    stated = re.search(r"(\d+)% percentile intervals from ([\d,]+) bootstrap resamples", plan)
    assert stated.group(1) == level and stated.group(2) == n(report["bootstrap"]["resamples"]), "both plans state the same intervals"
    e["ci.level"], e["ci.resamples"] = f"{level}%", stated.group(2)

    # review rate by condition of the page
    for arm in "ABC":
        for i, c in cfg[arm]["by_severity"].items():
            e[f"cond.{arm}.{i}.rate"] = pc(c["review_rate"], 1)
            e[f"cond.{arm}.{i}.n"] = f"{n(c['n_review'])} of {n(c['n_fields'])}"

    # the steps' panels
    sweep = v1["sweep"]
    e["step.1.pages"] = n(sweep["pages"])
    e["step.1.named"] = n(sum(v["classified"] for v in sweep["by_family"].values()))
    e["step.1.confirmed"] = n(sum(v["confirmed"] for v in sweep["by_family"].values()))
    e["step.1.set_aside"] = n(sweep["set_aside_by_title_check"])
    e["step.4.pages"], e["step.4.with"] = str(v1["sam"]["pages"]), str(v1["sam"]["pages_with_a_detection"])
    e["step.5.wrong"], e["step.5.agreed"] = str(a["reread_on_wrong"]), str(a["reread_agreed_with_wrong"])
    e["step.7.accepted"], e["step.7.fields"], e["step.7.review"], e["step.7.abstained"] = n(a["n_accepted"]), n(a["n_fields"]), n(a["n_review"]), n(a["n_abstained"])

    # the real scans' range chart: every variant, single read against Archivist
    for variant in VARIANTS:
        key = {"kept/as_run": "real.kept", "left_out/as_run": "real.left"}.get(variant) or f"range.v1.{variant.replace('/', '.')}"
        for who, field in (("single", "single_read_error"), ("archivist", "archivist_error")):
            r = v1["labels"][variant]["overall"][field]
            e[f"{key}.{who}"], e[f"{key}.{who}.ci"] = pc(r["value"], 1), ci(r["ci"])
    for variant in ("kept/as_run", "left_out/as_run"):
        key = "open" if variant == "kept/as_run" else f"range.ow.{variant.replace('/', '.')}"
        for who, field in (("single", "single_read_error"), ("archivist", "archivist_error")):
            r = ow["open_weights"][variant]["overall"][field]
            e[f"{key}.{who}"], e[f"{key}.{who}.ci"] = pc(r["value"], 1), ci(r["ci"])

    # by stratum and by family (aggregates)
    for cfg_name, labels in (("v1", v1["labels"]), ("ow", ow["open_weights"])):
        for variant in ("kept/as_run", "left_out/as_run"):
            for stratum, d in labels[variant]["by_stratum"].items():
                key = f"strat.{cfg_name}.{variant.replace('/', '.')}.{stratum}"
                for who, field in (("single", "single_read_error"), ("archivist", "archivist_error")):
                    e[f"{key}.{who}"], e[f"{key}.{who}.ci"] = pc(d[field]["value"], 1), ci(d[field]["ci"])
                e[f"{key}.cells"], e[f"{key}.pages"] = n(d["counted"]["cells"]), str(d["counted"]["pages"])
    for stratum in v1["labels"]["kept/as_run"]["by_stratum"]:
        if stratum[0].isdigit():
            e[f"strat.{stratum}.name"] = stratum.replace("_", "–")
    bundle = jload("data/bundles/treasury-development/bundle.json")
    titles = {t["name"]: t["title"] for t in bundle["doc_types"]}
    for fam, w in v1["weights"]["families"].items():
        d = v1["every_cell"]["kept/as_run"]["by_family"][fam]
        k = f"fam.{fam}"
        e[f"{k}.title"], e[f"{k}.named"], e[f"{k}.confirmed"], e[f"{k}.read"] = titles[fam], str(w["classified"]), str(w["confirmed"]), str(w["deep_pages"])
        e[f"{k}.cells"], e[f"{k}.review"] = n(d["cells"]), pc(d["review_rate"]["value"], 1)
        e[f"{k}.model"], e[f"{k}.ocr"], e[f"{k}.grid"] = (pc(d[f"boxed_{s}"]["value"], 1) for s in ("model", "ocr", "grid"))

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
        for field, count in (("drift", drift), ("format", fmt), ("reading", row + mis + digit + other)):
            e[f"diag.tip.{config}.{who}.{field}.n"] = f"{count} of {wrong}"
            e[f"diag.tip.{config}.{who}.{field}.share"] = f"{count / wrong * 100:.0f}%"
        for field, count in (("missing", row), ("misaligned", mis), ("digit", digit), ("other", other)):
            e[f"diag.tip.{config}.{who}.read.{field}"] = str(count)
    left, left_acc = diagnosis_counts("Version 1, wrong values in the single read")["left out"], diagnosis_counts("Version 1, wrong values Archivist accepted")["left out"]
    kept_s, kept_a = diagnosis_counts("Version 1, wrong values in the single read")["kept"], diagnosis_counts("Version 1, wrong values Archivist accepted")["kept"]
    e["diag.left.single"] = f"{left[3]} of {left[0]}"
    e["diag.left.accepted"] = f"{left_acc[3]} of {left_acc[0]}"
    e["diag.kept.drift"] = f"{kept_s[1]} of {kept_s[0]}"
    e["diag.kept.drift_acc"] = f"{kept_a[1]} of {kept_a[0]}"
    e["diag.kept.reading"] = f"{sum(kept_s[2:3]) + sum(kept_s[4:])} of {kept_s[0]}"
    e["diag.kept.reading_acc"] = f"{sum(kept_a[2:3]) + sum(kept_a[4:])} of {kept_a[0]}"

    field = {f["field_id"]: f for f in bundle["fields"]}[landing.REPLAY_FIELD]
    fields = {f["field_id"]: f for f in bundle["fields"]}
    pg = next(p for p in bundle["pages"] if p["page_id"] == field["page_id"])
    steps = {s["key"]: s["facts"] for s in pg["steps"]}
    others = [fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:{c}"]["value"] for c in ("admin", "to_retirement", "to_unemployment")]
    total = fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:total_exp"]["value"]
    assert sum(Decimal(x) for x in others) == Decimal(total)
    e["replay.value"], e["replay.reread"], e["replay.row"] = field["value"], field["reread"], field["row"]
    e["replay.sum"] = " + ".join(str(Decimal(x)) for x in others) + f" = {Decimal(total)}"
    e["replay.boxes"], e["replay.moved"] = str(steps["snap"]["boxes"]), str(steps["snap"]["moved"])
    e["replay.accepted"], e["replay.review"], e["replay.read"] = (str(steps["decide"]["accepted"]), str(steps["decide"]["review"]), str(steps["read"]["values"]))
    e["replay.year"] = pg["issue"][:4]
    e["replay.issue"] = "December 1939"
    assert pg["issue"] == "1939-12"
    e["replay.number"] = str(pg["number"])
    doc_type = next(t for t in bundle["doc_types"] if t["name"] == pg["doc_type"])
    e["replay.type"] = doc_type["title"]
    e["replay.column"] = next(c["printed"] for c in doc_type["columns"] if c["key"] == field["name"])
    e["replay.period"] = fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:period"]["value"].strip(" .")

    return e


def git(*args: str) -> str | None:
    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def full_history() -> bool:
    return git("rev-parse", "--is-shallow-repository") == "false"


def commit_of(*ref: str) -> tuple[str, str, str]:
    sha, stamp, message = git("log", "-1", "--format=%H%x1f%cI%x1f%s", *ref).split("\x1f", 2)
    return sha[:7], stamp, message


# --- the numbers ------------------------------------------------------------------------------------------


def test_every_marked_fact_is_what_its_file_says(page):
    want = expected()
    from_git = ("test.commit", "foot.first")  # checked against git, with the plans' dates, in test_the_dates_are_gits
    unknown = [k for k in page.facts if k not in want and not k.startswith("plan.") and k not in ("model", "docker", *from_git)]
    assert unknown == [], f"facts the test does not recompute: {unknown}"
    for key, texts in page.facts.items():
        if key in want:
            assert set(texts) == {want[key]}, key
    # the facts every page of this kind states (the ledger's own are checked, row by row, in the next test)
    must = [k for k in want if k.startswith(("stat.", "test.", "real.kept", "real.cells", "open.", "replay.", "limit.", "ci.", "fam.", "strat.", "step.", "diag.tip.", "cond.", "hw.cost", "hw.target", "hw.o1"))]
    missing = [k for k in must if k not in page.facts]
    assert missing == [], f"facts the page should state: {missing}"


def test_the_ledger_states_every_row_on_both_sides(page):
    """Each row's Archivist figure, on Meta's API and on your own hardware, is on the page as its file's number; so is
    the single read's wherever the file has one, and the interval wherever it has one."""
    want = ledger_expected(jload("results/test_report.json"), jload("results/real_test/held_out/score/score.json"), jload("results/real_openw/held_out/score/score.json"))
    for row, name in (("h1", "wrong"), ("h2", "caught"), ("h3", "review"), ("h5", "flagged"), ("r1", "real")):
        for mode in ("hosted", "open"):
            assert f"hw.{name}.{mode}" in page.facts, (row, mode)
            assert f"hw.{name}.{mode}.ci" in page.facts or row == "h5", (row, mode, "its interval")
    for row in ("h1", "h2", "h3", "h5", "r1"):
        assert f"ledger.{row}.hosted.single" in page.facts, row
    assert "ledger.h1.open.single" in page.facts and "ledger.r1.open.single" in page.facts
    for key in ("ledger.h1.hosted.arch.dots", "ledger.h2.hosted.arch.dots", "ledger.h3.hosted.arch.dots", "ledger.r1.hosted.arch.dots"):
        assert key in page.facts and key in want
    assert "ledger.h2.hosted.single.dots" not in page.facts, "nothing is marked on a grid of zero"


def test_a_ledger_row_has_a_row_of_the_table_for_every_target(html_text):
    rows = re.findall(r'<tbody class="lrow" data-row="(\w+)"', html_text)
    assert rows == ["h1", "h2", "h3", "h5", "r1"]
    for row in rows:
        assert f'aria-controls="ev-{row}"' in html_text and f'id="ev-{row}" hidden' in html_text
    assert html_text.count('class="pane"') + html_text.count('class="pane" hidden') == 2 * len(rows)


def test_the_three_numbers_are_the_report_s(html_text):
    assert "0.36%" in html_text and "93.65%" in html_text and "0.30%" in html_text, "the report's headline figures"


def test_no_digit_stands_outside_a_marked_fact(page):
    assert page.stray == [], "a number typed by hand: every digit on the page must be a fact read from a file"


def test_what_is_exempt_from_the_digit_rule_is_only_what_it_says(page):
    """A data-ok region is a name, a step's number, a label on a scale, or the size of a dot grid; nothing else."""
    assert {kind for kind, _ in page.oks} <= OK_KINDS
    for kind, text in page.oks:
        text = text.strip()
        if kind == "step":
            assert text in {"1", "2", "3", "4", "5", "6", "7"}, text
        elif kind == "axis":
            assert re.fullmatch(r"\d+(\.\d+)?%", text), text
        elif kind == "grid":
            assert text == f"{landing.DOTS:,}", text
        else:
            assert text in {"R1", "O1", "D19", "H1", "H2", "H3", "H4", "H5"}, text


def test_the_references_are_to_things_that_exist(page):
    refs = {r.strip() for r in page.refs}
    assert refs <= {"R1", "O1", "D19", "H1", "H2", "H3", "H4", "H5"}, refs
    synthetic = (ROOT / "PREREGISTRATION.md").read_text()
    for h in ("H1", "H2", "H3", "H4", "H5"):
        assert f"- {h}:" in synthetic
    assert "- R1:" in (ROOT / "PREREGISTRATION_REAL.md").read_text()
    assert "**O1:**" in (ROOT / "PREREGISTRATION_OPENW.md").read_text()
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
    added = git("log", "--diff-filter=A", "--format=%H", "--", "PREREGISTRATION.md").splitlines()[-1]
    sha, stamp, message = commit_of(added)
    assert page.facts["test.commit"] == [sha]
    assert page.facts["plan.synthetic.0.sha"] == [sha]
    assert page.facts["plan.synthetic.0.when"] == [when(stamp)]
    assert page.facts["plan.synthetic.0.msg"] == [message]
    for plan, tags in (("real", ("prereg-real-treasury", "run-real-treasury")), ("openw", ("prereg-real-openw", "run-real-openw"))):
        for i, tag in enumerate(tags):
            sha, stamp, message = commit_of(f"refs/tags/{tag}^{{commit}}")
            assert page.facts[f"plan.{plan}.{i}.sha"] == [sha]
            assert page.facts[f"plan.{plan}.{i}.when"] == [when(stamp)]
            assert page.facts[f"plan.{plan}.{i}.msg"] == [message]
    root = git("rev-list", "--max-parents=0", "HEAD").split()
    assert len(root) == 1
    sha, stamp, message = commit_of(root[0])
    assert set(page.facts["plan.first.sha"]) == {sha} and set(page.facts["plan.first.when"]) == {when(stamp)}
    assert page.facts["plan.first.msg"] == [message]
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


def test_the_timeline_links_each_commit_and_says_its_message(html_text, page):
    proof = json.loads((ROOT / landing.PROOF_FILE).read_text())
    commits = [proof["first_commit"], proof["registration"], *proof["tags"].values()]
    linked = {u for u in page.urls if u.startswith(f"{landing.REPO}/commit/")}
    assert linked == {f"{landing.REPO}/commit/{c['sha']}" for c in commits}
    for c in commits:
        assert re.search(rf'<a href="{re.escape(landing.REPO)}/commit/{c["sha"]}" rel="noopener"><code>.*?</code></a><span class="tip" role="tooltip">.*?{re.escape(c["message"].split(":")[0])}', html_text, re.S), c


# --- nothing is lost, nothing a reader needs is hidden ---------------------------------------------------------


def test_nothing_of_p51_s_page_is_lost(html_text):
    """Every fact key and every sentence or number of the page P51 shipped is still on this page."""
    assert landing_content.lost(html_text) == {"facts": [], "runs": []}


def test_the_guard_fails_when_a_sentence_or_a_number_goes(html_text):
    sentence = "A value is accepted only when independent checks agree."
    assert sentence in html_text
    gone = html_text.replace(sentence, "")
    assert landing_content.lost(gone)["runs"], "a sentence removed is noticed"
    key = 'data-fact="hw.o1"'
    assert key in html_text
    assert "hw.o1" in landing_content.lost(html_text.replace(key, 'data-x="hw.o1"'))["facts"], "a number removed is noticed"
    assert landing_content.p51()["facts"] and len(landing_content.p51()["runs"]) > 150


def test_the_missed_targets_and_the_unproven_claim_are_in_the_text_not_behind_a_click(page):
    """Not inside anything hidden or collapsed: the missed targets, 'not met' on the real scans, and 'not yet proven
    on-site'. Expandable panels add depth; they hold none of these."""
    text = " ".join(page.visible_text)
    text = re.sub(r"\s+", " ", text)
    for needle in (
        "missed", "was missed", "Targets missed", "not met", "It was not met, in any variant", "target not met",
        "Not yet proven on-site.", "On the real scans it missed its own target", "open weights missed its target",
    ):
        assert needle in text, needle
    for key in ("hw.review.hosted", "hw.flagged.hosted", "hw.real.hosted", "hw.real.open", "hw.o1", "hw.target", "test.review", "test.target", "limit.h3", "limit.h3_target", "limit.h5", "limit.h5_target", "real.kept.single", "real.kept.archivist"):
        assert key in page.visible_facts, f"{key} is only inside a hidden panel"


def test_held_out_results_are_aggregates_only(html_text):
    """Overall, by stratum, by family: no page, no cell, no value of a held-out page, not even its name."""
    score = jload("results/real_test/held_out/score/score.json")
    ids = set(score["both_ways_pages"]) | set(score["coverage_by_page"]) | set(score["template_drift"])
    assert len(ids) >= 50
    assert not [i for i in ids if i in html_text], "a held-out page is named"
    named = set(re.findall(r"\b\d{4}-\d{2}_p\d{3}\b", html_text))
    assert named <= {"1939-12_p025"}, f"only the development page of the replay: {named}"
    for word in ("cells_by", "labels.jsonl", "predictions.jsonl", "verdicts.jsonl", "boxes.jsonl", "unanswered_rereads"):
        assert word not in html_text, word
    assert "data/real/pages" not in html_text


def test_every_link_to_the_repository_goes_to_a_file_that_exists(html_text):
    for path in set(re.findall(re.escape(landing.REPO) + r"/blob/main/([^\"#]+)", html_text)):
        assert (ROOT / path).exists(), f"the page links to {path}, which is not in the repository"


# --- the dot grids, the intervals and the charts' text -----------------------------------------------------------


def test_each_dot_grid_is_a_thousand_dots_with_its_marked_ones_counted(html_text):
    grids = re.findall(r'<svg class="dots"[^>]*data-dots="(\d+)" data-marked="(\d+)"[^>]*>(.*?)</svg>', html_text, re.S)
    assert len(grids) >= 15
    for total, marked, inner in grids:
        assert total == "1000"
        # the drawn set is whichever is smaller: the marked dots, or the plain ones over a marked base
        path = re.search(r'<path class="(\w+)" d="([^"]*)"', inner)
        drawn = path.group(2).count("M")
        assert drawn == (int(marked) if path.group(1) != "plain" else 1000 - int(marked)), (marked, drawn)


def test_the_dots_come_out_the_same_every_build():
    assert landing.dot_grid("x", 0.25, "wrong", "l") == landing.dot_grid("x", 0.25, "wrong", "l")
    assert landing.dot_grid("x", 0.25, "wrong", "l")[1] == 250
    assert landing.dot_grid("x", 0.0004, "wrong", "l")[1] == 0


class Marks(HTMLParser):
    """Each chart mark (an interval, a bar, a part of a cause bar), and whether text sits in a tip inside it."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[bool] = []
        self.stack: list[tuple[str, int | None, bool]] = []  # tag, which mark it is (an index into found), whether it is a tip

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        classes = set((dict(attrs).get("class") or "").split())
        mark = None
        if {"mk", "cb"} & classes or (tag == "b" and any(c.startswith("s-") for c in classes)):
            self.found.append(False)
            mark = len(self.found) - 1
        self.stack.append((tag, mark, "tip" in classes))

    def handle_endtag(self, tag):
        while self.stack and tag not in VOID:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data):
        if data.strip() and any(tip for _, _, tip in self.stack):
            marks = [m for _, m, _ in self.stack if m is not None]
            if marks:
                self.found[marks[-1]] = True  # the innermost mark that holds this tip


def test_every_chart_has_a_text_equivalent(html_text):
    """A tip on every mark; a data table for the condition chart; a label on every dot grid and every bar of causes."""
    parser = Marks()
    parser.feed(html_text)
    assert len(parser.found) >= 50
    assert all(parser.found), f"{parser.found.count(False)} marks have no tip"
    bare = Marks()
    bare.feed(html_text.replace('<span class="tip">', '<span class="gone">', 1))
    assert not all(bare.found), "a mark without its tip is noticed"
    assert 'class="sr"><caption>Share of values sent to a person, by condition of the page' in html_text
    assert len(re.findall(r'<svg class="dots" viewBox="[^"]*" role="img" aria-label="[^"]+"', html_text)) == len(re.findall(r'<svg class="dots"', html_text))
    assert len(re.findall(r'<div class="seg" role="group" aria-label="[^"]+"', html_text)) == 4
    for tip in re.findall(r'<span class="tip"(?: role="tooltip")?>(.*?)</span></span>', html_text, re.S)[:5]:
        assert tip.strip()


def test_the_pipeline_has_a_panel_for_each_step_with_what_it_checks_and_when_it_fails(html_text):
    assert len(re.findall(r'class="pstep" aria-expanded="false" aria-controls="step-\d"', html_text)) == 7
    panels = re.findall(r'<div class="spanel" id="step-(\d)" role="region"[^>]*hidden>(.*?)</div>', html_text, re.S)
    assert [p for p, _ in panels] == [str(i) for i in range(1, 8)]
    for _, body in panels:
        assert "What it checks." in body and "When it fails." in body
        assert "Code" in body


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


def test_the_crop_is_centred_on_the_value_and_inside_the_page():
    shown = landing.replay(ROOT)
    html = landing.specimen(shown)
    x, y, w, h = (float(v) for v in re.search(r'<svg viewBox="([\d.]+) ([\d.]+) (\d+) (\d+)"', html).groups())
    page, loop = shown["page"], shown["field"]["loop"]["ink"]
    assert 0 <= x and x + w <= page["width"] and 0 <= y and y + h <= page["height"]
    assert abs(x + w / 2 - (loop[0] + loop[2]) / 2) < 1 and abs(y + h / 2 - (loop[1] + loop[3]) / 2) < 1


# --- the corrected key ------------------------------------------------------------------------------------


def test_the_corrected_key_is_pending_until_its_file_exists(html_text):
    exists = [p for p in landing.CORRECTED.values() if (ROOT / p).is_file()]
    assert ("Pending, after the dash check" in html_text) == (not exists)
    disabled = 'data-key="corrected" aria-pressed="false" disabled aria-disabled="true">Corrected key <span class="pend">pending</span>'
    assert (disabled in html_text) == (not exists), "the toggle is disabled and says pending until the file exists"


def _fixed():
    v1, ow = jload(landing.REAL_SCORE), jload(landing.OPEN_SCORE)
    labels = json.loads(json.dumps(v1["labels"]))
    for result in labels.values():
        for name in ("single_read_error", "archivist_error", "catch_rate"):
            result["overall"][name] = {"value": 0.0123, "ci": [0.0, 0.0456]}
    fixed = {"version_1": {"official": {"labels": v1["labels"]}, "corrected_key": {"labels": labels}}}
    both = {**fixed, "open_weights": {"corrected_key": {"o1": {**ow["o1"], "value": 0.0099, "ci": [0.0, 0.02], "met": True}, "open_weights": {"kept/as_run": {"overall": ow["open_weights"]["kept/as_run"]["overall"]}}}}}
    return fixed, both


def test_a_corrected_key_is_shown_beside_the_official_result_when_its_file_exists():
    fixed, both = _fixed()
    card = landing.corrected_card(fixed)
    assert "1.2%" in card and "0.0%–4.6%" in card and "Open weights: pending, after the dash check" in card
    card = landing.corrected_card(both)
    assert "target met" in card and "pending" not in card


def test_the_range_chart_offers_the_corrected_key_once_its_file_exists():
    fixed, both = _fixed()
    r, names = landing.real_scores(ROOT), landing.models(ROOT)
    chart = landing.range_chart(r, both, names)
    assert 'data-key="corrected" aria-pressed="false">Corrected key</button>' in chart and "disabled" not in chart.split('data-key="corrected"')[1].split("</button>")[0]
    assert chart.count('class="rg-set"') + chart.count('class="rg-set" hidden') == 2, "the official set and the corrected one"
    assert "1.2%" in chart
    part = landing.range_chart(r, fixed, names)
    assert "Open weights: pending, after the dash check" in part, "a configuration without its file says so"


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
    assert not [f for f in files if f.endswith(".md")], "the fonts' notes are not shipped; their licences are"
    text = (out / "index.html").read_text()
    assert "The archive that" in text and "shows its work." in text
    for reference in re.findall(r'(?:href|src)="([^"#:][^":]*)"', text):
        assert (out / reference.split("#")[0].split("?")[0]).exists(), reference
    assert "Pending, after the dash check" in text or all((ROOT / p).is_file() for p in landing.CORRECTED.values())
    assert 'href="ui/#replay"' in text, "Watch it work opens the app on the replay"
    assert (out / "ui/index.html").is_file(), "the app stays at /ui/"


def test_the_docker_image_is_let_in_everything_the_page_reads():
    """.dockerignore leaves everything out and lets back in what the build reads; the page reads more than the app."""
    allowed = [ln[1:].strip() for ln in (ROOT / ".dockerignore").read_text().splitlines() if ln.startswith("!")]
    reads = [
        landing.TEST_REPORT, landing.REAL_SCORE, landing.OPEN_SCORE, landing.DIAGNOSIS, landing.SWEEP, *landing.CORRECTED.values(),
        *landing.MODEL_CONFIGS, landing.PROOF_FILE, "README.md", *landing.ASSETS, landing.PLAN_REAL, landing.STORE,
        "results/runs/test-baseline/run.json", "data/bundles/index.json", "data/bundles/treasury-development/bundle.json", "ui/fonts/GEIST-OFL.txt",
    ]
    lost = [p for p in reads if not any(p == a or p.startswith(a.rstrip("/") + "/") for a in allowed)]
    assert lost == [], f"the Docker build cannot see: {lost}"


# --- the brand mark, the type and the motion ------------------------------------------------------------------------


def test_the_logo_is_the_brand_mark_in_both_themes_and_only_the_wordmark_follows_the_theme(html_text):
    imgs = re.findall(r'<img[^>]*src="([^"]*)"', html_text)
    assert imgs == ["assets/brand/logo-light.svg"], "one mark, the same in light and in dark"
    assert "logo-dark" not in html_text and "assets/brand/logo-dark.svg" not in landing.ASSETS
    mark = (ROOT / "assets/brand/logo-light.svg").read_text()
    assert {c.upper() for c in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', mark)} == {"#4A55D4", "#FFFFFF", "#F4B23A"}, "indigo square, white lines, gold tick"
    css = (ROOT / "docs/landing/landing.css").read_text()
    assert not re.search(r"\.brand img[^{]*\{[^}]*(filter|fill)", css), "the mark is never recoloured"
    app = (ROOT / "ui/index.html").read_text()
    inline = re.search(r'<a class="logo"[^>]*>(<svg.*?</svg>)', app, re.S).group(1)
    assert {c.upper() for c in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{3,6})"', inline)} == {"#4A55D4", "#FFF", "#F4B23A"}, "the app's mark is the same three colours"
    for sheet in (ROOT / "ui/css").glob("*.css"):
        assert not re.search(r"\.logo\s+(svg|rect|path)[^{]*\{[^}]*(fill|stroke)\s*:", sheet.read_text()), f"{sheet.name} recolours the app's mark"


def _css_blocks(css: str):
    """(selector, declarations, inside a no-preference block) of every rule, and {keyframes name: its declarations}."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    keyframes = {}
    for name, body in re.findall(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", css):
        keyframes[name] = " ".join(re.findall(r"\{([^{}]*)\}", body))
    ranges = []
    for found in re.finditer(r"@media \(prefers-reduced-motion:\s*no-preference\)\s*\{", css):
        depth, i = 1, found.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        ranges.append((found.end(), i))
    rules = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = m.group(1).strip()
        if selector.startswith(("@keyframes", "from", "to", "0%", "100%")):
            continue
        rules.append((selector, m.group(2).replace("!important", ""), any(a <= m.start(2) < b for a, b in ranges)))
    return rules, keyframes


def test_the_stylesheet_animates_nothing_but_opacity_and_transform():
    """The two exceptions are the ones the brief names: the circular reveal (the browser's View Transition, whose clip
    is set in the script) and, where that does not exist, the cross-fade of colours (.theme-fade)."""
    rules, keyframes = _css_blocks((ROOT / "docs/landing/landing.css").read_text())
    allowed = {"opacity", "transform"}
    transitions = 0
    for selector, body, calm in rules:
        if "theme-fade" in selector or "view-transition" in selector:
            continue
        for value in re.findall(r"(?<![\w-])transition\s*:\s*([^;]+)", body):
            transitions += 1
            props = {item.strip().split()[0] for item in re.split(r",(?![^()]*\))", value)}
            assert props <= allowed, f"{selector}: transitions {props - allowed}"
            assert calm, f"{selector}: a transition that a visitor who asked for reduced motion would still see"
        for value in re.findall(r"(?<![\w-])animation\s*:\s*([^;]+)", body):
            if value.strip() == "none":
                continue
            assert [t for t in re.findall(r"[A-Za-z][\w-]*", value) if t in keyframes], f"{selector}: an animation with no keyframes of ours: {value}"
            assert calm, f"{selector}: an animation that a visitor who asked for reduced motion would still see"
        assert not re.search(r"transition-property\s*:", body)
    assert transitions >= 10
    for name, declarations in keyframes.items():
        props = {d.split(":")[0].strip() for d in declarations.split(";") if ":" in d}
        assert props <= allowed, f"@keyframes {name} animates {props - allowed}"
    assert {"rise", "fade", "show", "drift-a", "drift-b", "drift-c"} <= set(keyframes)


def test_the_script_moves_only_one_thing_by_the_browsers_own_animation_the_theme_reveal():
    script = (ROOT / "docs/landing/landing.js").read_text()
    assert script.count(".animate(") == 1 and 'pseudoElement: "::view-transition-new(root)"' in script and "duration: 600" in script
    assert "startViewTransition" in script and "theme-fade" in script and "still.matches) return apply(next)" in script


def test_the_fonts_are_self_hosted_open_licensed_and_subset_to_latin():
    css = (ROOT / "docs/landing/landing.css").read_text()
    faces = re.findall(r"@font-face\{([^}]*)\}", css)
    assert {re.search(r'font-family:"([^"]+)"', f).group(1) for f in faces} == {"Newsreader", "Geist", "Geist Mono"}
    ranges = {re.search(r"unicode-range:([^;}]+)", f).group(1) for f in faces}
    assert len(ranges) == 1, "one Latin range for all three"
    allowed: set[int] = set()
    for part in ranges.pop().split(","):
        lo, _, hi = part.strip()[2:].partition("-")
        allowed |= set(range(int(lo, 16), int(hi or lo, 16) + 1))
    assert max(c for c in allowed if c < 0xFE00) < 0x2300 and not allowed & set(range(0x370, 0x530)), "no Greek, no Cyrillic"
    total = 0
    for f in faces:
        src = re.search(r'url\("([^"]+)"\)', f).group(1)
        assert not src.startswith(("http", "//", "data:")), "self-hosted"
        data = (ROOT / "docs/landing" / src).read_bytes()
        assert data[:4] == b"wOF2" and len(data) < 60_000, f"{src}: a subset, not the whole font"
        total += len(data)
    assert total < 100_000
    for licence in ("docs/landing/fonts/NEWSREADER-OFL.txt", "ui/fonts/GEIST-OFL.txt"):
        assert "SIL OPEN FONT LICENSE Version 1.1" in (ROOT / licence).read_text()
    assert "Newsreader" in (ROOT / "docs/landing/fonts/README.md").read_text() and "Latin" in (ROOT / "docs/landing/fonts/README.md").read_text()
    assert "font-variant-numeric:tabular-nums" in css.replace(" ", "")


def test_every_character_on_the_page_is_in_the_latin_subset(html_text):
    css = (ROOT / "docs/landing/landing.css").read_text()
    allowed: set[int] = set()
    for part in re.search(r"unicode-range:([^;}]+)", css).group(1).split(","):
        lo, _, hi = part.strip()[2:].partition("-")
        allowed |= set(range(int(lo, 16), int(hi or lo, 16) + 1))
    text = "".join(parse(html_text).visible_text)
    outside = sorted({c for c in text if ord(c) not in allowed and not c.isspace()})
    assert outside == [], f"characters the fonts do not carry: {outside}"


# --- the page, run ------------------------------------------------------------------------------------------

SCREENSHOTS = ROOT / "ui" / "screenshots"
needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Chromium or Chrome found (set ARCHIVIST_BROWSER)")
ONE_PAGE_WASH = ".bg{position:absolute!important;height:100%!important}"  # the glow is fixed: on a page-long shot it would stop at the window's foot


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    top = tmp_path_factory.mktemp("landing")
    site.build(top / "Archivist")
    with serve(top) as base, Browser() as browser:
        yield base + "/Archivist/", browser


def new_tab(browser: Browser):
    """A tab that is the one in front and has the focus, whatever tabs earlier tests left open: hover, focus and CSS
    transitions only advance in a tab that is."""
    tab = browser.tab()
    tab.call("Page.bringToFront")
    tab.call("Emulation.setFocusEmulationEnabled", enabled=True)
    return tab


def shown(tab) -> int:
    return tab.eval("document.querySelectorAll('.notes li.on').length")


def press(tab, key: str, vk: int, text: str | None = None) -> None:
    for kind in ("keyDown", "keyUp"):
        params = {"type": kind, "key": key, "code": key, "windowsVirtualKeyCode": vk}
        if kind == "keyDown" and text is not None:
            params["text"] = text
        tab.call("Input.dispatchKeyEvent", **params)


def hover(tab, selector: str) -> None:
    x, y = tab.eval(f"(()=>{{const r=document.querySelector({selector!r}).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}})()")
    tab.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)


def jump(tab, selector: str, offset: int = 100) -> None:
    tab.eval(f"(()=>{{const e=document.querySelector({selector!r});scrollTo({{top:e.getBoundingClientRect().top+scrollY-{offset},behavior:'instant'}})}})()")
    tab.pump(0.4)


@needs_browser
def test_the_replay_starts_by_itself_pauses_and_plays_again(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    tab.wait_for("document.documentElement.classList.contains('play')", 10)
    tab.wait_for("document.querySelectorAll('.notes li.on').length >= 2", 20)  # it began without a click
    tab.eval("document.querySelector('[data-act=pause]').click()")
    held = shown(tab)
    tab.pump(2.8)
    assert shown(tab) == held, "paused"
    assert tab.eval("document.querySelector('[data-act=pause]').textContent") == "Resume"
    tab.eval("document.querySelector('[data-act=pause]').click()")
    tab.wait_for("document.querySelectorAll('.notes li.on').length === 7", 30)
    assert tab.eval("document.querySelector('.pen').classList.contains('on') && document.querySelector('.tick').classList.contains('on')")
    tab.wait_for("getComputedStyle(document.querySelector('.rp-count')).opacity === '1'", 5)
    assert tab.eval("document.querySelectorAll('.leader.on').length") == 7, "a leader from each note to the value"
    assert tab.eval("document.querySelectorAll('.rail li.on').length") == 7
    tab.eval("document.querySelector('[data-act=replay]').click()")
    tab.pump(0.3)
    assert shown(tab) < 7, "Replay starts again from the beginning"
    tab.wait_for("document.querySelectorAll('.notes li.on').length === 7", 30)
    assert tab.errors == []
    assert [u for u in tab.requests if not u.startswith((base, "data:"))] == [], "no request off the site"


@needs_browser
def test_the_rail_shows_a_step_and_holds_the_replay_there(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, still=True)
    tab.eval("document.querySelector('[data-goto=\"3\"]').click()")
    assert shown(tab) == 3 and tab.eval("document.querySelector('[data-act=pause]').textContent") == "Resume"
    on = lambda sel: tab.eval(f"document.querySelector('{sel}').classList.contains('on')")  # noqa: E731
    assert on(".layer.snapbox") and on(".layer.pen") and not on(".layer.tick") and not on(".layer.cropbox"), "the marks of step three, and no later one"
    assert tab.eval("document.querySelector('.rail li.now button').dataset.goto") == "3"
    tab.pump(2.4)
    assert shown(tab) == 3, "held until resumed"
    tab.eval("document.querySelector('[data-act=pause]').click()")
    tab.wait_for("document.querySelectorAll('.notes li.on').length === 7", 20)


@needs_browser
def test_the_circled_value_is_in_the_first_screen_at_1440_by_900(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, width=1440, height=900, dark=False)
    tab.wait_for("document.querySelector('.layer.pen').classList.contains('on')", 20)
    tab.pump(0.9)
    top, bottom = tab.eval("(()=>{const r=document.querySelector('.layer.pen').getBoundingClientRect();return [r.top,r.bottom]})()")
    assert 60 < top and bottom < 900 - 120, f"the loop is at {top}..{bottom} of 900"
    assert tab.eval("document.querySelector('h1').getBoundingClientRect().top") < 200


@needs_browser
def test_sections_fade_in_once_as_they_scroll_into_view(served):
    base, browser = served
    tab = new_tab(browser)
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
    tab = new_tab(browser)
    tab.open(base, still=True)
    tab.pump(1.0)
    assert tab.eval("document.documentElement.classList.contains('play')") is False
    assert tab.eval("[...document.querySelectorAll('.notes li, .rp-count, .reveal, .rise, .leader')].every(e => getComputedStyle(e).opacity === '1')")
    assert tab.eval("document.getAnimations().length") == 0, "nothing moves: not the glow, not a fade"
    assert tab.eval("getComputedStyle(document.querySelector('.layer.pen')).transform") == "none"
    assert tab.eval("document.querySelectorAll('.leader').length") == 7
    hover(tab, ".frame")
    tab.pump(0.3)
    assert tab.eval("document.querySelector('.frame').style.getPropertyValue('--mx')") == "", "the highlight does not follow the pointer"
    tab.eval("document.querySelector('[data-act=replay]').click()")  # the visitor's own choice
    tab.wait_for("document.querySelectorAll('.notes li.on').length === 7", 30)
    assert tab.eval("document.getAnimations().length") == 0


@needs_browser
def test_the_ledger_switch_recounts_every_figure_and_each_one_ends_as_its_file_says(served):
    base, browser = served
    want = expected()
    tab = new_tab(browser)
    tab.open(base, dark=False)
    jump(tab, "#ledger")
    assert tab.eval("document.querySelector('.ro[aria-pressed=true]').dataset.mode") == "hosted"
    tab.eval("document.querySelector('.ro[data-mode=open]').click()")
    tab.pump(1.3)
    assert tab.eval("document.querySelector('#ledger').dataset.mode") == "open"
    assert tab.eval("document.querySelector('.ro[data-mode=open]').getAttribute('aria-pressed')") == "true"
    for side, hidden in (("o", None), ("h", "true")):
        pairs = tab.eval(f"[...document.querySelectorAll('#ledger .swap .v.{side} [data-fact]')].map(e => [e.dataset.fact, e.textContent])")
        assert len(pairs) >= 12
        for key, text in pairs:
            assert text == want[key], f"{key}: {text!r} is not {want[key]!r} after the count"
        assert tab.eval(f"document.querySelector('#ledger .swap .v.{side}').getAttribute('aria-hidden')") == hidden
    assert tab.eval("document.querySelector('[data-row=h1] .opener').click(), [...document.querySelectorAll('[data-row=h1] .pane')].map(p => !p.hidden)") == [False, True], "the evidence follows the switch"
    tab.eval("document.querySelector('.ro[data-mode=hosted]').click()")
    tab.pump(1.3)
    pairs = tab.eval("[...document.querySelectorAll('#ledger .swap .v.h [data-fact]')].map(e => [e.dataset.fact, e.textContent])")
    assert all(text == want[key] for key, text in pairs)
    assert tab.errors == []


@needs_browser
def test_the_ledger_switch_is_instant_with_reduced_motion_and_works_from_the_keyboard(served):
    base, browser = served
    want = expected()
    tab = new_tab(browser)
    tab.open(base, still=True)
    tab.eval("document.querySelector('.ro[data-mode=open]').focus()")
    press(tab, "Enter", 13, "\r")
    assert tab.eval("document.querySelector('#ledger').dataset.mode") == "open"
    pairs = tab.eval("[...document.querySelectorAll('#ledger .swap .v.o [data-fact]')].map(e => [e.dataset.fact, e.textContent])")
    assert pairs and all(text == want[key] for key, text in pairs), "no count, the figures at once"


@needs_browser
def test_a_row_opens_to_its_interval_its_counts_its_dots_and_its_sources(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, still=True)
    jump(tab, "#ledger")
    assert tab.eval("document.getElementById('ev-h1').hidden") is True
    tab.eval("document.querySelector('[data-row=h1] .opener').focus()")
    press(tab, "Enter", 13, "\r")
    assert tab.eval("document.getElementById('ev-h1').hidden") is False
    assert tab.eval("document.querySelector('[data-row=h1] .opener').getAttribute('aria-expanded')") == "true"
    visible = "[data-row=h1] .pane:not([hidden])"
    assert tab.eval(f"document.querySelectorAll('{visible} svg.dots').length") == 2
    assert tab.eval(f"[...document.querySelectorAll('{visible} svg.dots')].every(s => s.dataset.dots === '1000')")
    assert tab.eval(f"document.querySelectorAll('{visible} .mk').length") == 2 and tab.eval(f"document.querySelectorAll('{visible} .mk .bar').length") == 2
    hrefs = tab.eval(f"[...document.querySelectorAll('{visible} .src a')].map(a => a.href)")
    assert hrefs == [f"{landing.REPO}/blob/main/results/test_report.json", f"{landing.REPO}/blob/main/PREREGISTRATION.md"]
    tab.eval("document.querySelector('[data-row=h1] .opener').click()")
    assert tab.eval("document.getElementById('ev-h1').hidden") is True


@needs_browser
def test_the_condition_chart_turns_an_arm_off_and_gives_its_figures(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, still=True)
    jump(tab, "#ledger")
    tab.eval("document.querySelector('[data-row=h3] .opener').click()")
    assert tab.eval("document.querySelectorAll('.cond .cb').length") == 12
    assert tab.eval("document.querySelectorAll('.cond table.sr tbody tr').length") == 4
    tab.eval("document.querySelector('.cond .lg.b').click()")
    assert tab.eval("document.querySelector('.cond').dataset.off") == "b"
    assert tab.eval("document.querySelector('.cond .lg.b').getAttribute('aria-pressed')") == "false"
    assert tab.eval("getComputedStyle(document.querySelector('.cond .cb.b')).opacity") == "0.1"
    assert tab.eval("getComputedStyle(document.querySelector('.cond .cb.a')).opacity") == "1"
    tab.eval("document.querySelector('.cond .lg.b').click()")
    assert tab.eval("document.querySelector('.cond').dataset.off") == ""


@needs_browser
def test_a_step_opens_what_it_checks_and_what_happens_when_it_fails(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, still=True)
    assert tab.eval("[...document.querySelectorAll('.spanel')].every(p => p.hidden)")
    tab.eval("document.querySelectorAll('.pstep')[4].focus()")
    press(tab, "Enter", 13, "\r")
    assert tab.eval("[...document.querySelectorAll('.spanel')].map(p => !p.hidden)") == [False, False, False, False, True, False, False]
    text = tab.eval("document.getElementById('step-5').innerText")
    assert "What it checks." in text and "When it fails." in text and "blind read is not fully independent" in text
    tab.eval("document.querySelectorAll('.pstep')[2].click()")
    assert tab.eval("[...document.querySelectorAll('.pstep')].map(b => b.getAttribute('aria-expanded'))") == ["false", "false", "true", "false", "false", "false", "false"]
    press(tab, "Escape", 27)
    assert tab.eval("[...document.querySelectorAll('.spanel')].every(p => p.hidden)")


@needs_browser
def test_the_range_chart_shows_where_each_pair_of_intervals_overlaps_and_the_corrected_key_waits(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, still=True)
    rows = tab.eval("document.querySelectorAll('.rg-set[data-key=official] .rg-row').length")
    assert rows == 6, "four variants hosted, two on open weights"
    v1, ow = jload(landing.REAL_SCORE)["labels"], jload(landing.OPEN_SCORE)["open_weights"]
    pairs = [v1[v]["overall"] for v in VARIANTS] + [ow[v]["overall"] for v in ("kept/as_run", "left_out/as_run")]
    overlapping = sum(max(p["single_read_error"]["ci"][0], p["archivist_error"]["ci"][0]) <= min(p["single_read_error"]["ci"][1], p["archivist_error"]["ci"][1]) for p in pairs)
    assert tab.eval("document.querySelectorAll('.rg-set[data-key=official] .band').length") == overlapping == 6
    assert tab.eval("[...document.querySelectorAll('.rg-set[data-key=official] .rg-l .tag')].map(t => t.textContent)") == ["not met"] * 4 + ["target not met"]
    if not all((ROOT / p).is_file() for p in landing.CORRECTED.values()):
        key = tab.eval("(()=>{const b=document.querySelector('.ks[data-key=corrected]');return [b.disabled,b.getAttribute('aria-disabled'),b.textContent.trim()]})()")
        assert key == [True, "true", "Corrected key pending"]
        assert tab.eval("document.querySelectorAll('.rg-set').length") == 1
        tab.eval("document.querySelector('.ks[data-key=corrected]').click()")
        assert tab.eval("document.querySelector('.ks[data-key=official]').getAttribute('aria-pressed')") == "true", "a disabled key does not switch"


@needs_browser
def test_a_mark_says_what_it_is_when_focused_hovered_or_tapped_and_stops_when_asked(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    jump(tab, "#range")
    tab.eval("document.querySelector('.rg-set .mk.arch').focus()")
    tab.pump(0.3)
    text = tab.eval("document.querySelector('.tooltip').textContent")
    assert tab.eval("document.querySelector('.tooltip').classList.contains('on')") and "Archivist" in text and "interval" in text and "%" in text
    press(tab, "Escape", 27)
    assert not tab.eval("document.querySelector('.tooltip').classList.contains('on')")
    jump(tab, ".causes")
    hover(tab, ".seg b")
    tab.pump(0.3)
    text = tab.eval("document.querySelector('.tooltip').textContent")
    assert re.search(r"Layout drift: \d+ of \d+ wrong values, \d+%", text), text
    tab.call("Input.dispatchMouseEvent", type="mouseMoved", x=5, y=5)
    tab.pump(0.3)
    assert not tab.eval("document.querySelector('.tooltip').classList.contains('on')")
    tab.eval("document.querySelectorAll('.seg b')[1].click()")  # a tap: it stays until the next tap
    assert tab.eval("document.querySelector('.tooltip').classList.contains('on')")
    tab.eval("document.body.click()")
    assert not tab.eval("document.querySelector('.tooltip').classList.contains('on')")


@needs_browser
def test_a_commit_shows_its_message_on_focus_and_links_to_github(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    jump(tab, "#planned")
    tip = "document.querySelectorAll('.tl .ev')[1].querySelector('.tip')"
    assert tab.eval(f"getComputedStyle({tip}).opacity") == "0"
    tab.eval("document.querySelectorAll('.tl .ev a')[1].focus()")
    tab.wait_for(f"getComputedStyle({tip}).opacity === '1'", 5)
    proof = jload(landing.PROOF_FILE)
    assert tab.eval(f"{tip}.textContent") == proof["registration"]["message"]
    assert tab.eval("document.querySelectorAll('.tl .ev a')[1].href") == f"{landing.REPO}/commit/{proof['registration']['sha']}"
    assert tab.eval("document.querySelectorAll('.tl .ev a')[1].rel") == "noopener"


@needs_browser
def test_the_theme_switch_is_a_circular_reveal_from_the_toggle(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    try:
        tab.eval("localStorage.removeItem('archivist-theme')")
        tab.eval("window.__vt = []; const real = document.startViewTransition.bind(document); document.startViewTransition = (cb) => { window.__vt.push(1); return real(cb); }")
        src_before = tab.eval("document.querySelector('.brand img').getAttribute('src')")
        word_before = tab.eval("getComputedStyle(document.querySelector('.wordmark')).color")
        tab.eval("document.querySelector('[data-theme-toggle]').click()")
        tab.wait_for("document.documentElement.dataset.theme === 'dark'", 10)
        tab.pump(1.0)
        assert tab.eval("window.__vt.length") == 1, "through the browser's View Transition"
        assert tab.eval("localStorage.getItem('archivist-theme')") == "dark", "the app's own key"
        assert tab.eval("document.querySelector('[data-theme-toggle]').getAttribute('aria-pressed')") == "true"
        assert tab.eval("document.querySelector('.brand img').getAttribute('src')") == src_before, "the mark is the same mark"
        assert tab.eval("getComputedStyle(document.querySelector('.wordmark')).color") != word_before, "the wordmark's colour follows the theme"
        assert tab.eval("getComputedStyle(document.body).backgroundColor") == "rgb(10, 11, 14)"
        assert tab.errors == []
    finally:
        tab.eval("localStorage.removeItem('archivist-theme')")


@needs_browser
def test_where_the_browser_has_no_view_transitions_the_colours_cross_fade(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    try:
        tab.eval("localStorage.removeItem('archivist-theme'); document.startViewTransition = undefined")
        tab.eval("document.querySelector('[data-theme-toggle]').click()")
        assert tab.eval("document.documentElement.dataset.theme") == "dark"
        assert tab.eval("document.documentElement.classList.contains('theme-fade')"), "a gentle cross-fade, then it is removed"
        tab.wait_for("!document.documentElement.classList.contains('theme-fade')", 5)
    finally:
        tab.eval("localStorage.removeItem('archivist-theme')")


@needs_browser
def test_with_reduced_motion_a_theme_change_is_instant(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False, still=True)
    try:
        tab.eval("localStorage.removeItem('archivist-theme'); window.__vt = 0; const real = document.startViewTransition.bind(document); document.startViewTransition = (cb) => { window.__vt++; return real(cb); }")
        tab.eval("document.querySelector('[data-theme-toggle]').click()")
        assert tab.eval("document.documentElement.dataset.theme") == "dark", "at once"
        assert tab.eval("window.__vt") == 0 and not tab.eval("document.documentElement.classList.contains('theme-fade')")
        assert tab.eval("document.getAnimations().length") == 0
    finally:
        tab.eval("localStorage.removeItem('archivist-theme')")


@needs_browser
def test_the_glass_is_sparing_frosted_and_catches_the_pointer(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    tab.pump(0.5)
    glass = tab.eval("[...document.querySelectorAll('.glass, .btn.sec')].map(e => e.className.split(' ')[0] + ':' + (getComputedStyle(e).backdropFilter || getComputedStyle(e).webkitBackdropFilter))")
    assert glass and all("blur" in g for g in glass), glass
    pieces = tab.eval("[...new Set([...document.querySelectorAll('[data-glass]')].map(e => e.matches('.pill') ? 'pill' : e.matches('.frame') ? 'frame' : e.matches('.ledger') ? 'ledger' : e.matches('.btn.sec') ? 'button' : 'switch'))].sort()")
    assert pieces == ["button", "frame", "ledger", "pill", "switch"], "the navigation, the specimen's frame, the ledger, the secondary buttons"
    assert tab.eval("[...document.querySelectorAll('.card, .notes li, .pane, .spanel, .limit, .cond')].every(e => (getComputedStyle(e).backdropFilter || 'none') === 'none')"), "content is never glass"
    hover(tab, ".pill")
    tab.pump(0.4)
    assert tab.eval("document.querySelector('.pill').style.getPropertyValue('--mx')") != ""
    assert tab.eval("getComputedStyle(document.querySelector('.pill > .shine i')).transform") != "none", "the highlight moves by transform"
    tab.wait_for("getComputedStyle(document.querySelector('.pill > .shine i')).opacity === '1'", 5)


@needs_browser
def test_a_visitor_who_asked_for_less_transparency_or_a_slow_machine_gets_solid_surfaces(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False, still=True)
    tab.eval("document.documentElement.classList.add('calm')")
    assert tab.eval("[...document.querySelectorAll('.glass, .btn.sec')].every(e => (getComputedStyle(e).backdropFilter || 'none') === 'none')")
    css = (ROOT / "docs/landing/landing.css").read_text()
    assert "prefers-reduced-transparency:reduce" in css and "html.calm .bg i{animation:none" in css


@needs_browser
def test_the_page_can_be_used_from_the_keyboard_with_a_visible_focus(served):
    base, browser = served
    tab = new_tab(browser)
    tab.open(base, dark=False)
    tab.pump(0.3)
    reached = []
    for _ in range(14):
        press(tab, "Tab", 9)
        reached.append(tab.eval("(()=>{const a=document.activeElement;const s=getComputedStyle(a);return [a.className||a.tagName, a.matches(':focus-visible'), s.outlineStyle, s.outlineWidth]})()"))
    assert all(r[1] and r[2] == "solid" and r[3] == "2px" for r in reached), reached
    assert any(str(r[0]).startswith("skip") for r in reached[:1]), "the skip link first"
    assert any("tog" in str(r[0]) for r in reached), "the theme toggle"
    assert tab.eval("document.querySelector('.skip').getAttribute('href')") == "#main"


@needs_browser
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("phone", [False, True], ids=["desktop", "phone"])
def test_the_page_fits_the_screen_in_light_and_dark(served, dark, phone):
    base, browser = served
    tab = new_tab(browser)
    width, height = (390, 844) if phone else (1440, 900)
    tab.open(base, width=width, height=height, dark=dark, mobile=phone, still=True)
    tab.pump(0.8)
    assert tab.eval("document.documentElement.scrollWidth") <= width, "no sideways scroll"
    assert tab.eval("[...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1 && !e.closest('svg, pre, .shine, .tip')).length") == 0
    background = tab.eval("getComputedStyle(document.body).backgroundColor")
    assert background == ("rgb(10, 11, 14)" if dark else "rgb(246, 246, 243)")
    assert tab.eval("getComputedStyle(document.querySelector('h1')).color") == ("rgb(232, 233, 237)" if dark else "rgb(22, 24, 29)")
    assert tab.eval("document.querySelector('h1').getBoundingClientRect().top < innerHeight / 2"), "the headline is in the first screen"
    assert tab.eval("document.querySelector('.hero .btn.primary').getBoundingClientRect().bottom < innerHeight")
    assert tab.eval("getComputedStyle(document.querySelector('h1')).fontFamily").startswith('Newsreader'), "headlines in Newsreader"
    assert tab.eval("getComputedStyle(document.body).fontFamily").startswith("Geist")
    assert tab.eval("getComputedStyle(document.querySelector('code')).fontFamily").startswith('"Geist Mono"')
    assert tab.eval("getComputedStyle(document.querySelector('.lt-table td')).fontVariantNumeric").count("tabular-nums") == 1
    if phone:
        assert tab.eval("document.querySelector('.notes li').getBoundingClientRect().top >= document.querySelector('.scan svg').getBoundingClientRect().bottom"), "the notes stack under the scan"
        assert tab.eval("document.querySelectorAll('.leader').length") == 0
    else:
        left = tab.eval("[...document.querySelectorAll('.notes li[data-side=l]')].every(e => e.getBoundingClientRect().right < document.querySelector('.scan svg').getBoundingClientRect().left)")
        right = tab.eval("[...document.querySelectorAll('.notes li[data-side=r]')].every(e => e.getBoundingClientRect().left > document.querySelector('.scan svg').getBoundingClientRect().right)")
        assert left and right, "a note in each margin, left and right of the value"
        assert tab.eval("document.querySelector('.notes li[data-side=l]').getBoundingClientRect().top < innerHeight")
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
    tab = new_tab(browser)
    tab.open(base, still=True)
    tab.eval("document.querySelector('.hero .btn.primary').click()")
    tab.wait_for("location.pathname.endsWith('/ui/') && document.documentElement.dataset.ready === '1'", 60)
    assert tab.eval("location.hash") == "#replay"
    assert tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)") == ["v-replay"]
    chip = tab.eval("document.getElementById('where').textContent")
    assert "Run on" in chip and "Meta’s API" in chip, "the app says it the way the page's switch does"
