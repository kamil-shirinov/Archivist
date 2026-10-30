"""The review UI in a real browser (Chromium over the DevTools protocol, tests/browser.py): every view
in light and dark, at a desktop and a phone width, with a screenshot of each saved to
ui/screenshots/, and any console error, uncaught exception, failed or off-machine request a failure.

The app is a static page over the committed bundle, so the repository is served as files on localhost,
as GitHub Pages serves it. No model, no key and no network beyond localhost. The tests skip, saying so,
where no Chromium or Chrome can be found (set ARCHIVIST_BROWSER to name one).
"""

import json
from pathlib import Path

import pytest

from browser import Browser, find_browser, serve

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "ui" / "screenshots"
BUNDLES = ROOT / "data" / "bundles"

if find_browser() is None:
    pytest.skip("no Chromium or Chrome found (set ARCHIVIST_BROWSER)", allow_module_level=True)

SIZES = {"desktop": (1440, 900), "phone": (390, 844)}
THEMES = {"light": False, "dark": True}
MEMO = "memo-0001"
CARD = "card-01-2"
# Each view: its hash, and a script that is true once it has drawn what it should.
VIEWS = {
    "overview": ("#overview", "document.querySelectorAll('#ov-kpis .kpi').length === 4"),
    "documents": ("#documents", "document.querySelectorAll('#doc-rows tr[data-page]').length > 0"),
    "document": (
        f"#doc-{CARD}",
        "!!document.querySelector('#dpaper img')?.complete && !!document.querySelector('#drecord table')",
    ),
    "review": (
        "#review",
        "!!document.querySelector('#stage img')?.complete && document.getElementById('p-field').textContent.length > 0",
    ),
    "replay": (
        f"#replay-{CARD}",
        "!!document.querySelector('#wstage img')?.complete && document.querySelectorAll('#w-steps li').length === 7",
    ),
    "accuracy": ("#accuracy", "!!document.querySelector('#acc-test .acc-lead')"),
}


@pytest.fixture(scope="module")
def site():
    with serve(ROOT) as base:
        yield base


@pytest.fixture(scope="module")
def tab(site):
    with Browser() as browser:
        yield browser.tab()


def load(tab, base, hash_, size="desktop", theme="light", still=True):
    width, height = SIZES[size]
    tab.errors.clear()
    tab.requests.clear()
    tab.open(f"{base}/ui/{hash_}", width=width, height=height, dark=THEMES[theme], still=still)
    tab.wait_for("document.documentElement.dataset.ready === '1'", 60)


def settle(tab, ready):
    tab.wait_for(ready, 30)
    tab.pump(1.0)  # transitions and the camera come to rest


def local(tab, base):
    """No request left the machine: every one went to the server the page came from."""
    return [u for u in tab.requests if not (u.startswith(base) or u.startswith("data:"))]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("view", VIEWS)
def test_every_view_opens_without_a_console_error_and_is_photographed(tab, site, view, size, theme):
    hash_, ready = VIEWS[view]
    load(tab, site, hash_, size, theme)
    settle(tab, ready)
    shown = tab.eval(
        "[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)"
    )
    assert len(shown) == 1, shown
    assert tab.eval("document.querySelector('main .view:not([hidden]) h1').textContent.length > 0")
    assert tab.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"), (
        "the page scrolls sideways"
    )
    dark = tab.eval("getComputedStyle(document.body).backgroundColor")
    assert (dark == "rgb(10, 11, 14)") == (theme == "dark"), dark
    assert tab.errors == []
    assert local(tab, site) == []
    SHOTS.mkdir(exist_ok=True)
    tab.screenshot(SHOTS / f"{view}-{size}-{theme}.png")
    if (size, theme) == ("desktop", "light"):  # and the whole of each view, below the fold too
        tab.screenshot(SHOTS / f"{view}-desktop-light-full.png", full_page=True)


def test_the_page_says_what_it_shows(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    bar = tab.eval("document.getElementById('runbar').textContent")
    for words in (
        "Synthetic test pages",
        "test-archivist-A",
        "policy v2",
        "Muse Spark 1.3",
        "SAM 3.1",
    ):
        assert words in bar, bar
    assert "Box 14" in tab.eval("document.getElementById('coll').textContent")
    assert "Muse Spark 1.3" in tab.eval("document.getElementById('side-foot').textContent")


def test_the_overview_numbers_are_the_bundles(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    data = json.loads((BUNDLES / "test-archivist-A" / "bundle.json").read_text("utf-8"))
    n = len(data["fields"])
    accepted = sum(f["status"] == "accepted" for f in data["fields"])
    text = tab.eval("document.getElementById('ov-kpis').textContent")
    assert f"{accepted:,} of {n:,} values" in text.replace(" ", ",")
    assert f"{accepted / n * 100:.1f}%" in text
    docs = tab.eval("document.querySelectorAll('#ov-accts tr').length")
    assert docs == 6


def test_pointing_at_a_value_shows_where_it_sits_and_pinning_keeps_it(tab, site):
    load(tab, site, f"#doc-{CARD}", still=False)
    settle(tab, VIEWS["document"][1])
    cell = "document.querySelector('#drecord [data-field$=\":05:balance\"]')"
    assert tab.eval(f"!!{cell}")
    tab.eval(f"{cell}.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}))")
    tab.wait_for("document.querySelectorAll('#dpaper .ov .hl').length === 1")
    assert tab.eval("document.querySelectorAll('#dpaper .ov .pen').length") >= 1
    assert tab.eval(f"{cell}.classList.contains('hot')")
    tab.pump(0.8)
    assert float(tab.eval("document.querySelector('#dthread path').style.opacity")) > 0  # the line
    tab.eval(f"{cell}.dispatchEvent(new MouseEvent('click', {{bubbles: true}}))")
    tab.eval("document.getElementById('drecord').dispatchEvent(new MouseEvent('mouseleave'))")
    assert tab.eval(f"{cell}.classList.contains('hot')"), "pinning keeps it"
    tab.eval(f"{cell}.dispatchEvent(new MouseEvent('click', {{bubbles: true}}))")
    tab.eval("document.getElementById('drecord').dispatchEvent(new MouseEvent('mouseleave'))")
    assert not tab.eval(f"{cell}.classList.contains('hot')"), "a second click lets it go"
    assert tab.errors == []


def test_pointing_at_the_page_finds_the_value_under_it(tab, site):
    load(tab, site, f"#doc-{CARD}")
    settle(tab, VIEWS["document"][1])
    data = json.loads((BUNDLES / "test-archivist-A" / "bundle.json").read_text("utf-8"))
    field = next(f for f in data["fields"] if f["field_id"] == f"L:{CARD}:05:balance")
    page = next(p for p in data["pages"] if p["page_id"] == CARD)
    x, y = (
        (field["box"]["x0"] + field["box"]["x1"]) / 2,
        (field["box"]["y0"] + field["box"]["y1"]) / 2,
    )
    tab.eval(
        f"""(() => {{
          const r = document.querySelector('#dpaper .sheet').getBoundingClientRect();
          document.getElementById('dpaper').dispatchEvent(new MouseEvent('mousemove', {{
            bubbles: true,
            clientX: r.left + {x} / {page["width"]} * r.width,
            clientY: r.top + {y} / {page["height"]} * r.height}}));
        }})()"""
    )
    tab.wait_for("!!document.querySelector('#drecord [data-field$=\":05:balance\"].hot')")
    assert tab.errors == []


def test_how_it_was_read_lists_every_step_in_order(tab, site):
    load(tab, site, f"#doc-{CARD}")
    settle(tab, VIEWS["document"][1])
    tab.eval("document.querySelector('#dd-tabs [data-tab=hist]').click()")
    tab.wait_for("document.querySelectorAll('#dh-list li').length >= 7")
    titles = tab.eval("[...document.querySelectorAll('#dh-list li b')].map(b => b.textContent)")
    assert titles[:7] == [
        "Recognised the page",
        "Read and cited 95 values",
        "Snapped every box to the ink",
        "Looked for covered ink",
        "Read every value again, blind",
        "Checked the bookkeeping rules",
        "Decided",
    ]
    assert tab.errors == []


def test_the_documents_list_filters_and_opens_a_document(tab, site):
    load(tab, site, "#documents")
    settle(tab, VIEWS["documents"][1])
    assert "157" in tab.eval("document.querySelector('#f-type button').textContent")
    tab.eval("document.querySelector('#f-type [data-t=memo]').click()")
    rows = tab.eval("document.querySelectorAll('#doc-rows tr[data-page]').length")
    assert rows == 25  # a page of memos
    assert tab.eval(
        "[...document.querySelectorAll('#doc-rows tr')].every(r => r.textContent.includes('Payment memo'))"
    )
    tab.eval("document.querySelector('#doc-rows tr[data-page]').click()")
    tab.wait_for("location.hash.startsWith('#doc-memo-')")
    settle(tab, VIEWS["document"][1])
    assert tab.errors == []


def test_the_review_queue_takes_an_answer_and_remembers_it(tab, site):
    load(tab, site, "#review")
    settle(tab, VIEWS["review"][1])
    before = int(tab.eval("document.getElementById('nav-count').textContent.replace(/,/g, '')"))
    assert tab.eval("document.querySelectorAll('#opts .opt').length") >= 1
    tab.eval("document.querySelector('#opts .opt').click()")
    tab.wait_for("!document.getElementById('outcome').hidden")
    after = int(tab.eval("document.getElementById('nav-count').textContent.replace(/,/g, '')"))
    assert after == before - 1 or after == before  # an exception stays out of the open count too
    assert (
        tab.eval(
            "Object.keys(JSON.parse(localStorage.getItem('archivist-answers:test-archivist-A'))).length"
        )
        == 1
    )
    assert tab.eval("document.getElementById('out-msg').textContent.length > 0")
    tab.eval("document.getElementById('out-next').click()")
    tab.pump(0.5)
    assert tab.errors == []
    tab.eval("localStorage.clear()")


def test_the_review_keys_move_and_answer(tab, site):
    load(tab, site, "#review")
    settle(tab, VIEWS["review"][1])
    key = "document.body.dispatchEvent(new KeyboardEvent('keydown', {key: '%s', bubbles: true}))"
    where = "+document.getElementById('pos').textContent.split(' of ')[0]"
    total = int(
        tab.eval("document.getElementById('pos').textContent.split(' of ')[1].split(' ')[0]")
    )
    start = tab.eval(where)
    assert total > 1
    tab.eval(key % "j")
    tab.pump(0.3)
    assert tab.eval(where) == start % total + 1
    tab.eval(key % "k")
    tab.pump(0.3)
    assert tab.eval(where) == start
    tab.eval(key % "1")  # the first answer offered
    tab.wait_for("!document.getElementById('outcome').hidden")
    assert tab.errors == []
    tab.eval("localStorage.clear()")


def test_a_recorded_read_replays_to_its_end(tab, site):
    load(tab, site, f"#replay-{MEMO}")
    settle(tab, VIEWS["replay"][1])
    assert tab.eval("document.getElementById('w-of').textContent") == "0 of 7 values"
    tab.eval("document.querySelector('#w-speed [data-s=\"10\"]').click()")
    tab.eval("document.getElementById('w-play').click()")
    tab.wait_for("document.getElementById('w-stagename').textContent === 'Done'", 60)
    assert tab.eval("document.getElementById('w-of').textContent") == "7 of 7 values"
    assert "done" in tab.eval("document.getElementById('w-now').textContent")
    assert tab.eval("document.querySelectorAll('#wstage .ov .wbx').length") >= 7
    assert tab.errors == []


def test_the_whole_box_fast_forwards(tab, site):
    load(tab, site, "#replay")
    settle(tab, VIEWS["replay"][1])
    tab.eval("document.getElementById('w-ff').click()")
    tab.wait_for("document.getElementById('w-boxsum').textContent.includes('How accurate')", 30)
    assert "157 of 157 pages" in tab.eval("document.getElementById('w-boxsum').textContent")
    assert tab.errors == []


def test_the_accuracy_report_has_the_test_reports_numbers_and_real_scans_are_pending(tab, site):
    load(tab, site, "#accuracy")
    settle(tab, VIEWS["accuracy"][1])
    text = tab.eval("document.getElementById('acc-test').textContent")
    report = json.loads((ROOT / "results" / "test_report.json").read_text("utf-8"))
    for h in report["hypotheses"].values():
        assert ("Met" if h["met"] else "Missed") in text
    assert "Missed" in text and "Met" in text
    assert "921 of 4,267" in text
    assert "twelve times fewer" in text
    assert "$0.056" in text  # arm B's cost a page, from the report
    tab.eval("document.querySelector('#acc-set [data-a=real]').click()")
    assert not tab.eval("document.getElementById('acc-real').hidden")
    assert tab.eval("document.getElementById('acc-test').hidden")
    assert "pending" in tab.eval("document.getElementById('acc-set').textContent")
    assert "Results come after the hand check" in tab.eval(
        "document.getElementById('acc-real').textContent"
    )
    assert tab.errors == []


def test_the_palette_opens_on_ctrl_k_searches_and_jumps(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    tab.eval(
        "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'k', ctrlKey: true, bubbles: true}))"
    )
    tab.wait_for("!document.getElementById('pal').hidden")
    tab.eval(
        "(() => { const i = document.getElementById('gq'); i.value = 'memo'; i.dispatchEvent(new Event('input')); })()"
    )
    tab.wait_for("document.querySelectorAll('#pal-list .pal-i').length > 1")
    tab.eval("document.querySelector('#pal-list .pal-i').click()")
    tab.wait_for("location.hash.length > 1 && document.getElementById('pal').hidden")
    assert tab.errors == []


def test_light_and_dark_and_compact_are_remembered(tab, site):
    load(tab, site, "#documents")
    settle(tab, VIEWS["documents"][1])
    tab.eval("document.getElementById('t-dark').click()")
    assert tab.eval("document.documentElement.dataset.theme") == "dark"
    tab.eval("document.getElementById('d-comp').click()")
    assert tab.eval("document.documentElement.dataset.density") == "compact"
    tab.open(f"{site}/ui/#documents", dark=False, still=True)
    tab.wait_for("document.documentElement.dataset.ready === '1'", 60)
    assert tab.eval("document.documentElement.dataset.theme") == "dark"
    assert tab.eval("document.documentElement.dataset.density") == "compact"
    tab.eval("localStorage.clear()")
    assert tab.errors == []
