"""The review UI in a real browser (Chromium over the DevTools protocol, tests/browser.py): every view
in light and dark, at a desktop and a phone width, with a screenshot of each saved to
ui/screenshots/, and any console error, uncaught exception, failed or off-machine request a failure.

The app is a static page over the committed bundle, so the repository is served as files on localhost,
as GitHub Pages serves it. No model, no key and no network beyond localhost. The tests skip, saying so,
where no Chromium or Chrome can be found (set ARCHIVIST_BROWSER to name one).
"""

import json
import re
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
    "accounts": ("#accounts", "document.querySelectorAll('#acct-rows tr[data-acct]').length > 0"),
    "account": (
        "#acct-84608901",
        "document.querySelectorAll('#chain .sheetbox').length === 3 && document.querySelectorAll('#balchart polyline').length === 1",
    ),
    "transactions": (
        "#transactions",
        "document.querySelectorAll('#tx-rows tr[data-i]').length > 0 && !!document.querySelector('#tstage img')?.complete",
    ),
    "types": ("#types", "document.querySelectorAll('#ty-list details').length === 7"),
    "replay": (
        f"#replay-{CARD}",
        "!!document.querySelector('#wstage img')?.complete && document.querySelectorAll('#w-steps li').length === 7",
    ),
    "accuracy": ("#accuracy", "!!document.querySelector('#acc-test .acc-lead')"),
}


DEV = "?run=treasury-development"
DESCRIPTION = (
    "The development run read four pages and recorded no values for a fifth "
    "(June 1984, page 66), which is left out of this collection."
)
TABLE = "1939-12_p053"
# The development collection of real Treasury Bulletin pages, in the same views.
VIEWS |= {
    "development-overview": (f"{DEV}#overview", VIEWS["overview"][1]),
    "development-documents": (f"{DEV}#documents", VIEWS["documents"][1]),
    "development-document": (
        f"{DEV}#doc-{TABLE}",
        "!!document.querySelector('#dpaper img')?.complete && !!document.querySelector('#drecord table')",
    ),
    "development-review": (f"{DEV}#review", VIEWS["review"][1]),
    "development-types": (f"{DEV}#types", VIEWS["types"][1]),
}


@pytest.fixture(scope="module")
def site():
    with serve(ROOT) as base:
        yield base


@pytest.fixture(scope="module")
def tab(site):
    with Browser() as browser:
        yield browser.tab()


def load(tab, base, hash_, size="desktop", theme="light", still=True, height=None):
    width, high = SIZES[size]
    height = height or high
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


def test_the_development_pages_are_marked_as_development_with_their_real_titles(tab, site):
    load(tab, site, f"{DEV}#documents")
    settle(tab, VIEWS["documents"][1])
    bar = tab.eval("document.getElementById('runbar').textContent")
    for words in (
        "Real pages, development",
        "not a measured result",
        "Treasury Bulletin",
        "No Copyright",
    ):
        assert words in bar, bar
    assert tab.eval("document.getElementById('sample').textContent") == "Development pages"
    assert tab.eval("document.getElementById('coll-name').textContent") == "US Treasury Bulletin"
    rows = tab.eval("[...document.querySelectorAll('#doc-rows tr')].map(r => r.textContent)")
    assert len(rows) == 4
    assert any(
        "December 1939, page 53" in r and "Short-Term Foreign Liabilities" in r for r in rows
    )
    assert not any("1984" in r for r in rows), "the page the run recorded nothing for is left out"
    assert DESCRIPTION in tab.eval("document.getElementById('dc-sub').textContent")
    assert tab.errors == []


def test_a_printed_table_is_a_grid_of_its_cells_that_can_be_pointed_at(tab, site):
    load(tab, site, f"{DEV}#doc-{TABLE}", still=False)
    settle(tab, VIEWS["development-document"][1])
    heads = tab.eval("[...document.querySelectorAll('#drecord thead th')].map(t => t.textContent)")
    assert "United Kingdom" in heads and "Grand total" in heads
    assert "Short-Term Foreign Liabilities" in tab.eval(
        "document.getElementById('dd-t').textContent"
    )
    assert "December 1939, page 53" in tab.eval("document.getElementById('dd-sub').textContent")
    assert "Rules" in tab.eval("document.getElementById('dd-links-h').textContent")
    assert "Held in" in tab.eval("document.getElementById('dd-links').textContent")
    cell = "document.querySelector('#drecord [data-field$=\":15:germany\"]')"
    tab.eval(f"{cell}.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}))")
    tab.wait_for("document.querySelectorAll('#dpaper .ov .hl').length === 1")
    assert tab.eval("document.querySelectorAll('#dpaper .ov .pen').length") >= 1
    assert tab.errors == []


def test_the_collection_says_it_read_four_pages_and_left_out_a_fifth(tab, site):
    load(tab, site, f"{DEV}#overview")
    settle(tab, VIEWS["overview"][1])
    assert DESCRIPTION in tab.eval("document.getElementById('ov-sub').textContent")
    assert "5 pages, 4 kept" in tab.eval("document.getElementById('runinfo').textContent")
    tab.eval("document.getElementById('coll').click()")
    tab.wait_for("!document.getElementById('coll-menu').hidden")
    assert DESCRIPTION in tab.eval("document.getElementById('coll-menu').textContent")
    tab.eval("document.dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    tab.eval("location.hash = '#doc-1984-06_p066'")  # a page that is not in the collection
    tab.wait_for("location.hash === '#documents'")
    assert tab.errors == []


def test_nothing_is_drawn_on_a_page_that_the_bundle_does_not_hold(tab, site):
    data = json.loads((BUNDLES / "treasury-development" / "bundle.json").read_text("utf-8"))
    load(tab, site, f"{DEV}#doc-{TABLE}")
    settle(tab, VIEWS["development-document"][1])
    held = {f["loop"]["d"] for f in data["fields"] if f["page_id"] == TABLE and f["loop"]}
    drawn = tab.eval(
        "[...document.querySelectorAll('#dpaper .ov .pen')].map(p => p.getAttribute('d'))"
    )
    assert drawn and set(drawn) <= held, "every mark on the page is a mark the bundle holds"
    assert tab.eval("document.querySelectorAll('#dpaper .ov rect.pen').length") == 0, (
        "no ring of its own"
    )
    # a wash is the cited box and no bigger
    cell = "document.querySelector('#drecord [data-field$=\":15:germany\"]')"
    tab.eval(f"{cell}.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}))")
    tab.wait_for("document.querySelectorAll('#dpaper .ov .hl').length === 1")
    box = next(f for f in data["fields"] if f["field_id"].endswith(f"{TABLE}:15:germany"))["box"]
    wash = tab.eval(
        "(() => { const r = document.querySelector('#dpaper .ov .hl'); "
        "return [+r.getAttribute('x'), +r.getAttribute('y'), +r.getAttribute('width'), +r.getAttribute('height')]; })()"
    )
    assert wash == [box["x0"], box["y0"], box["x1"] - box["x0"], box["y1"] - box["y0"]]
    assert tab.errors == []


def test_the_run_switch_changes_the_arm_and_keeps_the_page(tab, site):
    """The Hosted / Open weights switch is now the chip "Run on" and its panel: Meta’s API
    (the default) or your own hardware (Muse Spark Open). Choosing one opens the same page on that run."""
    load(tab, site, f"#doc-{CARD}")
    settle(tab, VIEWS["document"][1])
    assert tab.eval("document.querySelector('#runbar .runswitch')") is None, "the old switch is gone"
    chip = tab.eval("document.getElementById('where').textContent")
    assert "Run on" in chip and "Meta’s API" in chip, chip
    assert tab.eval("document.getElementById('where').getAttribute('aria-expanded')") == "false"
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    assert tab.eval("document.getElementById('where').getAttribute('aria-expanded')") == "true"
    options = tab.eval(
        "[...document.querySelectorAll('#where-panel .wp-opt')].map(b => "
        "[b.dataset.where, b.querySelector('b').textContent, b.getAttribute('aria-pressed'), b.disabled])"
    )
    assert options == [
        ["api", "Meta’s API", "true", False],
        ["own", "Your own hardware", "false", False],
    ]
    tab.eval("document.querySelector('#where-panel [data-where=\"own\"]').click()")
    tab.wait_for(
        "location.search.includes('test-archivist-B') && document.documentElement.dataset.ready === '1'",
        60,
    )
    settle(tab, VIEWS["document"][1])
    assert tab.eval("location.hash") == f"#doc-{CARD}"
    bar = tab.eval("document.getElementById('runbar').textContent")
    assert "test-archivist-B" in bar and "Muse Spark Open" in bar and "open-weight" in bar
    assert "Your own hardware" in tab.eval("document.getElementById('where').textContent")
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    assert (
        tab.eval("document.querySelector('#where-panel [data-where=\"own\"]').getAttribute('aria-pressed')")
        == "true"
    )
    tab.eval("document.querySelector('#where-panel [data-where=\"api\"]').click()")  # and back
    tab.wait_for(
        "!location.search.includes('test-archivist-B') || location.search.includes('test-archivist-A')", 60
    )
    tab.wait_for("document.documentElement.dataset.ready === '1'", 60)
    assert "Meta’s API" in tab.eval("document.getElementById('where').textContent")
    assert tab.errors == []


def test_the_panel_says_the_seven_steps_are_the_same_and_only_the_two_reads_change(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    steps = tab.eval("[...document.querySelectorAll('#where-panel .wp-steps li')].map(l => l.textContent)")
    assert steps == [
        "1Recognise the page",
        "2Read and cite",
        "3Snap to the ink",
        "4Look for covered ink",
        "5Read again, blind",
        "6Check the rules",
        "7Decide",
    ]
    moves = tab.eval("[...document.querySelectorAll('#where-panel .wp-steps li')].map(l => l.classList.contains('moves'))")
    assert moves == [False, True, False, False, True, False, False], "the two reads are the only steps that move"
    text = tab.eval("document.getElementById('where-panel').textContent")
    assert "The same seven steps either way" in text and "steps 2 and 5" in text
    assert "Default" in text and "Muse Spark Open" in text
    # what the recording used is read from the bundle, and the panel's own caution agrees with the
    # open-weights run it points to: its reads went through Baseten, SAM 3.1 stayed on Meta’s API
    assert "This recording, test-archivist-A: Muse Spark 1.3 and SAM 3.1 on Meta’s API." in text
    b = json.loads((BUNDLES / "test-archivist-B" / "bundle.json").read_text("utf-8"))["run"]["models"]
    assert {m["role"]: m["backend"] for m in b} == {"extractor": "baseten", "rereader": "baseten", "segmenter": "meta"}
    assert "the recording ran Muse Spark Open on Baseten" in text
    assert "no measured run has kept a page on a bank’s own machines" in text
    assert "SAM 3.1 still runs on Meta’s API" in text
    # on the open-weights run the same line is read from its own bundle
    load(tab, site, "?run=test-archivist-B#overview")
    settle(tab, VIEWS["overview"][1])
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    assert (
        "This recording, test-archivist-B: Muse Spark Open on Baseten; SAM 3.1 on Meta’s API."
        in tab.eval("document.getElementById('where-panel').textContent")
    )
    assert tab.errors == []


def test_a_collection_with_one_run_offers_only_that_way_of_running(tab, site):
    load(tab, site, f"{DEV}#overview")
    settle(tab, VIEWS["overview"][1])
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    own = "document.querySelector('#where-panel [data-where=\"own\"]')"
    assert tab.eval(f"{own}.disabled") is True
    assert "No recording of these pages on Muse Spark Open." in tab.eval(f"{own}.textContent")
    assert tab.eval("document.querySelector('#where-panel [data-where=\"api\"]').getAttribute('aria-pressed')") == "true"
    tab.eval(f"{own}.click()")
    tab.pump(0.3)
    assert tab.eval("location.search") == DEV, "a way of running nobody recorded is not a link"
    assert tab.errors == []


@pytest.mark.parametrize("size", SIZES)
def test_the_panel_stays_inside_the_window_and_closes_on_escape_a_click_elsewhere_or_another_menu(tab, site, size):
    load(tab, site, "#overview", size)
    settle(tab, VIEWS["overview"][1])
    shown = "!document.getElementById('where-panel').hidden"
    tab.eval("document.getElementById('where').click()")
    tab.wait_for(shown)
    box = tab.eval(
        "(() => { const r = document.getElementById('where-panel').getBoundingClientRect(); "
        "return [r.left, r.top, r.right, innerWidth]; })()"
    )
    assert box[0] >= 0 and box[2] <= box[3] and box[1] >= 0, box
    assert tab.eval("document.activeElement.className").startswith("wp-opt"), "focus moves into the panel"
    tab.eval("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
    assert tab.eval("document.getElementById('where-panel').hidden")
    assert tab.eval("document.activeElement.id") == "where", "and goes back to the chip"
    assert tab.eval("document.getElementById('where').getAttribute('aria-expanded')") == "false"
    tab.eval("document.getElementById('where').click()")
    tab.wait_for(shown)
    tab.eval("document.querySelector('main h1').dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    assert tab.eval("document.getElementById('where-panel').hidden"), "a click elsewhere closes it"
    # one at a time: the collection menu closes it, and it closes the collection menu
    tab.eval("document.getElementById('where').click()")
    tab.wait_for(shown)
    tab.eval("document.getElementById('coll').click()")
    tab.wait_for("!document.getElementById('coll-menu').hidden")
    assert tab.eval("document.getElementById('where-panel').hidden")
    tab.eval("document.getElementById('where').click()")
    tab.wait_for(shown)
    assert tab.eval("document.getElementById('coll-menu').hidden")
    # and the palette closes it
    tab.eval("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'k', ctrlKey: true, bubbles: true}))")
    tab.wait_for("!document.getElementById('pal').hidden")
    assert tab.eval("document.getElementById('where-panel').hidden")
    assert tab.errors == []


# --- glass (ui/css/glass.css) ---------------------------------------------------------------------------
# Glass is on the top bar and on what floats above the page, and never on content, so a change of view
# has nothing to blur behind it. Animations touch only opacity and movement, never blur, and none run
# when the visitor asks for reduced motion.

FLOATING = ".top, .pal, .coll-menu, .where-panel, .toast"


def alpha(color):
    """The alpha of a computed colour: rgb(…), rgba(…) or color(srgb … / a)."""
    found = re.search(r"/\s*([0-9.]+)\s*\)$", color) or re.search(r"rgba\([^)]*,\s*([0-9.]+)\)$", color)
    return float(found.group(1)) if found else 1.0


@pytest.mark.parametrize("theme", THEMES)
def test_the_top_bar_and_what_floats_are_translucent_and_blurred(tab, site, theme):
    load(tab, site, "#overview", theme=theme)
    settle(tab, VIEWS["overview"][1])
    found = tab.eval(
        f"[...document.querySelectorAll('{FLOATING}')].map(e => [e.className, getComputedStyle(e).backdropFilter, "
        "getComputedStyle(e).backgroundColor])"
    )
    assert {c.split()[0] for c, *_ in found} == {"top", "pal", "coll-menu", "where-panel", "toast"}, found
    for name, blur, color in found:
        assert "blur(" in blur, (name, blur)
        assert 0.4 < alpha(color) < 1, (name, color)
    # the scrim behind the palette is plain: a blurred scrim would leave the palette nothing sharp to blur
    assert tab.eval("getComputedStyle(document.getElementById('pal')).backdropFilter") == "none"


@pytest.mark.parametrize("view", [k for k in VIEWS if not k.startswith("development-")])
def test_no_content_is_blurred_and_cards_are_solid_or_a_touch_translucent(tab, site, view):
    hash_, ready = VIEWS[view]
    load(tab, site, hash_)
    settle(tab, ready)
    blurred = tab.eval(
        """[...document.querySelectorAll('main, main *, .side, .side *, .runbar, .runbar *')].filter(e => {
          const s = getComputedStyle(e);
          return s.backdropFilter !== 'none' || s.filter !== 'none';
        }).map(e => e.id || e.className)"""
    )
    assert blurred == [], blurred
    cards = tab.eval(
        "[...document.querySelectorAll('main .panel, main .kpis')].map(e => getComputedStyle(e).backgroundColor)"
    )
    assert cards, "every view has cards"
    # solid, or a touch translucent; the dashed placeholder for a new type is the v7 design's transparent one
    assert all(alpha(c) == 0 or alpha(c) >= 0.9 for c in cards), cards


def test_the_wash_behind_the_page_is_still_and_takes_no_clicks(tab, site):
    load(tab, site, "#overview", still=False)
    settle(tab, VIEWS["overview"][1])
    wash = tab.eval(
        "(() => { const s = getComputedStyle(document.body, '::after'); "
        "return [s.position, s.pointerEvents, s.zIndex, s.animationName, s.backgroundImage.split('(')[0]]; })()"
    )
    assert wash == ["fixed", "none", "-1", "none", "radial-gradient"], wash
    assert tab.eval("document.getAnimations().filter(a => a.effect && a.effect.target === document.body).length") == 0
    assert tab.eval("getComputedStyle(document.body).backgroundColor") == "rgb(246, 246, 243)", "the page colour is unchanged"


def open_everything_that_floats(tab):
    """Open the palette, the collection menu, the panel and the toast, one after another."""
    tab.eval("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'k', ctrlKey: true, bubbles: true}))")
    tab.wait_for("!document.getElementById('pal').hidden")
    tab.eval("document.getElementById('pal').hidden = true")
    tab.eval("document.getElementById('coll').click()")
    tab.wait_for("!document.getElementById('coll-menu').hidden")
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    tab.eval("document.getElementById('add-doc').click()")
    tab.pump(0.05)


def test_floating_things_animate_only_opacity_and_movement(tab, site):
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    tab.eval("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'k', ctrlKey: true, bubbles: true}))")
    tab.wait_for("!document.getElementById('pal').hidden")
    started = tab.eval(
        """document.getAnimations().filter(a => a.effect && a.effect.target && a.effect.target.closest('.pal-wrap'))
             .map(a => [a.animationName, a.effect.pseudoElement, a.effect.getKeyframes().flatMap(k => Object.keys(k))])"""
    )
    assert started and {n for n, *_ in started} == {"scrim-in", "float-in"}, started
    props = {p for *_, keys in started for p in keys} - {"offset", "easing", "composite", "computedOffset"}
    assert props == {"opacity", "transform"}, props
    tab.eval("document.getElementById('pal').hidden = true")
    tab.eval("document.getElementById('coll').click()")
    tab.eval("document.getElementById('where').click()")
    tab.eval("document.getElementById('add-doc').click()")
    tab.pump(0.05)
    moving = tab.eval(
        """document.getAnimations().filter(a => a.effect && a.effect.target &&
             a.effect.target.closest('.pal-wrap, .coll-menu, .where-panel, #toast'))
           .map(a => a.transitionProperty || a.animationName)"""
    )
    assert moving, "the menus and the toast came in with an animation or a transition"
    assert set(moving) <= {"float-in", "scrim-in", "opacity", "transform"}, moving


def test_nothing_above_a_blurred_surface_is_a_backdrop_root(tab, site):
    """A parent with an opacity animation (or a filter, a mask, will-change...) is a backdrop root: the
    blur inside it would see only that parent, not the page. This is how the palette once blurred nothing."""
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    tab.eval("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'k', ctrlKey: true, bubbles: true}))")
    tab.wait_for("!document.getElementById('pal').hidden")
    tab.eval("document.getElementById('coll').click()")
    tab.eval("document.getElementById('where').click()")
    tab.wait_for("!document.getElementById('where-panel').hidden")
    tab.pump(1.0)  # the entrances are over: what is left is what stays
    roots = tab.eval(
        """(() => {
          const out = [];
          for (const e of document.querySelectorAll('.top, .pal, .coll-menu, .where-panel, .toast')) {
            for (let a = e.parentElement; a; a = a.parentElement) {
              const s = getComputedStyle(a);
              const why = [];
              if (s.opacity !== '1') why.push('opacity ' + s.opacity);
              if (s.filter !== 'none') why.push('filter');
              if (s.backdropFilter !== 'none') why.push('backdrop-filter');
              if (s.animationName !== 'none') why.push('animation ' + s.animationName);
              if (/opacity|filter|transform/.test(s.willChange)) why.push('will-change ' + s.willChange);
              if (s.mixBlendMode !== 'normal') why.push('mix-blend-mode');
              if (s.clipPath !== 'none') why.push('clip-path');
              if (s.maskImage !== 'none') why.push('mask');
              if (why.length) out.push([e.className.split(' ')[0], a.tagName + '.' + a.className, why.join(', ')]);
            }
          }
          return out;
        })()"""
    )
    assert roots == [], roots


def test_no_stylesheet_animates_or_transitions_a_blur(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    bad = tab.eval(
        """(() => {
          const out = [];
          const walk = (rules, sheet) => { for (const r of rules) {
            if (r instanceof CSSKeyframesRule) {
              for (const k of r.cssRules) if (/filter|blur/i.test(k.style.cssText)) out.push(sheet + ' @keyframes ' + r.name);
            } else if (r.style) {
              const t = r.style.getPropertyValue('transition') + r.style.getPropertyValue('transition-property') + r.style.getPropertyValue('will-change');
              if (/filter|blur/i.test(t)) out.push(sheet + ' ' + r.selectorText);
            }
            if (r.cssRules && !(r instanceof CSSKeyframesRule)) walk(r.cssRules, sheet);
          } };
          for (const s of document.styleSheets) walk(s.cssRules, s.href);
          return out;
        })()"""
    )
    assert bad == [], bad


def test_with_reduced_motion_nothing_that_floats_animates(tab, site):
    load(tab, site, "#documents", still=True)
    settle(tab, VIEWS["documents"][1])
    open_everything_that_floats(tab)
    running = tab.eval(
        """document.getAnimations().filter(a => a.effect && a.effect.target &&
             a.effect.target.closest('.pal-wrap, .coll-menu, .where-panel, #toast'))
           .map(a => a.transitionProperty || a.animationName)"""
    )
    assert running == [], running
    # and what opened is there, fully drawn
    for sel in (".coll-menu", ".where-panel"):
        assert tab.eval(f"getComputedStyle(document.querySelector('{sel}')).opacity") == "1", sel
    assert tab.eval("getComputedStyle(document.getElementById('toast')).opacity") == "1"
    assert tab.errors == []


def test_less_transparency_gives_solid_surfaces_where_the_browser_can_say_so(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    tab.call(
        "Emulation.setEmulatedMedia",
        features=[
            {"name": "prefers-color-scheme", "value": "light"},
            {"name": "prefers-reduced-motion", "value": "no-preference"},
            {"name": "prefers-reduced-transparency", "value": "reduce"},
        ],
    )
    if not tab.eval("matchMedia('(prefers-reduced-transparency: reduce)').matches"):
        pytest.skip("this browser has no prefers-reduced-transparency")
    found = tab.eval(
        f"[...document.querySelectorAll('{FLOATING}')].map(e => [e.className, getComputedStyle(e).backdropFilter, "
        "getComputedStyle(e).backgroundColor])"
    )
    for name, blur, color in found:
        if not name.startswith("toast"):
            assert blur == "none" and alpha(color) == 1, (name, blur, color)


def test_the_collection_menu_lists_every_collection_and_run_and_switches(tab, site):
    load(tab, site, "#overview")
    settle(tab, VIEWS["overview"][1])
    tab.eval("document.getElementById('coll').click()")
    tab.wait_for("!document.getElementById('coll-menu').hidden")
    items = tab.eval("[...document.querySelectorAll('#coll-menu .cm-i')].map(b => b.dataset.run)")
    assert items == ["test-archivist-A", "test-archivist-B", "treasury-development"]
    groups = tab.eval(
        "[...document.querySelectorAll('#coll-menu .cm-g b')].map(g => g.textContent)"
    )
    assert groups == ["Box 14", "US Treasury Bulletin"]
    tab.eval("document.querySelector('#coll-menu [data-run=treasury-development]').click()")
    tab.wait_for(
        "location.search.includes('treasury-development') && document.documentElement.dataset.ready === '1'",
        60,
    )
    assert "Real pages, development" in tab.eval("document.getElementById('runbar').textContent")
    assert tab.errors == []


def test_the_accuracy_report_of_development_pages_claims_no_measure(tab, site):
    load(tab, site, f"{DEV}#accuracy")
    settle(tab, "document.getElementById('acc-test').textContent.length > 0")
    text = tab.eval("document.getElementById('acc-test').textContent")
    assert "no measured result" in text and "not an accuracy" in text
    assert "Twelve" not in text and "wrong in every 1,000" not in text
    assert tab.errors == []


def test_the_accounts_list_opens_an_account_with_its_chain_and_memos(tab, site):
    data = json.loads((BUNDLES / "test-archivist-A" / "bundle.json").read_text("utf-8"))
    load(tab, site, "#accounts")
    settle(tab, VIEWS["accounts"][1])
    assert tab.eval("document.querySelectorAll('#acct-rows tr').length") == len(data["accounts"])
    tab.eval("document.querySelector('#acct-rows tr[data-acct=\"84608901\"]').click()")
    tab.wait_for("location.hash === '#acct-84608901'")
    settle(tab, VIEWS["account"][1])
    assert tab.eval("document.getElementById('ad-t').textContent") == "Donald Briggs"
    assert "£1,452.61" in tab.eval("document.getElementById('ad-kpis').textContent")
    assert tab.eval("document.querySelectorAll('#ad-memos tr[data-page]').length") == 11
    tab.eval("document.querySelector('#chain .sheetbox').click()")
    tab.wait_for("location.hash.startsWith('#doc-card-')")
    assert tab.errors == []


def test_transactions_are_searched_in_plain_words_and_show_their_page(tab, site):
    load(tab, site, "#transactions")
    settle(tab, VIEWS["transactions"][1])
    total = tab.eval("document.querySelectorAll('#tx-rows tr[data-i]').length")
    tab.eval(
        "(() => { const i = document.getElementById('q'); i.value = 'payments over 100'; i.dispatchEvent(new Event('input')); })()"
    )
    chips = tab.eval("document.getElementById('chips').textContent")
    assert "money out" in chips and "over £100.00" in chips
    debits = tab.eval(
        "[...document.querySelectorAll('#tx-rows tr[data-i]')].map(r => parseFloat(r.children[3].textContent.replace(/,/g, '')))"
    )
    assert 0 < len(debits) < total and all(d > 100 for d in debits)
    assert tab.eval("document.getElementById('tx-count').textContent").startswith(
        f"{len(debits)} of"
    )
    assert "Sheet" in tab.eval("document.getElementById('d-sub').textContent")
    assert tab.eval("document.querySelectorAll('#tstage .ov .hl').length") == 1
    tab.eval("document.querySelector('#chips .clear').click()")
    assert tab.eval("document.querySelectorAll('#tx-rows tr[data-i]').length") == total
    assert tab.errors == []


def test_document_types_list_each_rule_its_evidence_and_who_approved_it(tab, site):
    data = json.loads((BUNDLES / "test-archivist-A" / "bundle.json").read_text("utf-8"))
    load(tab, site, "#types")
    settle(tab, VIEWS["types"][1])
    names = tab.eval(
        "[...document.querySelectorAll('#ty-list details h2')].map(h => h.textContent)"
    )
    assert names == [t["title"] for t in data["doc_types"]]
    tab.eval("document.querySelectorAll('#ty-list details').forEach(d => d.open = true)")
    text = tab.eval("document.getElementById('ty-list').textContent")
    approvers = {t["approval"]["approved_by"] for t in data["doc_types"] if t["approval"]}
    assert approvers and all(a in text for a in approvers)
    assert "Held in" in text and "Evidence file" in text and "sha256" in text
    assert text.count("Approved by") >= 5
    assert tab.errors == []


# --- moving between views (js/transition.js) -------------------------------------------------------------

MOTION = {"normal": False, "reduced": True}
# Set up in the page once it has settled, to see what a change of view does: how many view
# transitions it starts, which elements the page names for them, every entrance animation as it starts
# (with its timing), whether anything in the top bar, the run bar or the side bar was animated or moved,
# and how many entrances have ended.
RECORD = """(() => {
  const root = document.documentElement;
  const log = (window.__nav = { vt: 0, named: [], started: [], rects: [], entered: 0 });
  const rects = () => ['.top', '.side', '#runbar'].map((s) => {
    const r = document.querySelector(s).getBoundingClientRect();
    return [r.x, r.y, r.width, r.height].map(Math.round).join(',');
  }).join(' | ');
  const named = () => [...document.querySelectorAll('.top, .side, #runbar, main, .view')]
    .filter((e) => getComputedStyle(e).viewTransitionName !== 'none').map((e) => e.id || e.className);
  log.rects.push(rects());
  const start = document.startViewTransition && document.startViewTransition.bind(document);
  if (start) document.startViewTransition = (update) => {
    log.vt++;
    log.named.push(named());
    return start(() => {
      const result = update();
      log.named.push(named());
      log.rects.push(rects());
      return result;
    });
  };
  document.addEventListener('animationstart', (e) => {
    const s = getComputedStyle(e.target);
    log.started.push({
      name: e.animationName,
      inView: !!e.target.parentElement && e.target.parentElement.classList.contains('view'),
      chrome: !!e.target.closest('.top, .side, #runbar'),
      delay: s.animationDelay, duration: s.animationDuration, ease: s.animationTimingFunction,
      transform: s.transform,
    });
    log.rects.push(rects());
  }, true);
  let was = false;
  new MutationObserver(() => {
    const now = !!root.dataset.entering;
    if (was && !now) log.entered++;
    was = now;
  }).observe(root, { attributes: true, attributeFilter: ['data-entering'] });
})()"""


def watch(tab):
    tab.eval(RECORD)


def go(tab, hash_, timeout=20):
    """Change the view by the hash, as a visitor's click does, and wait until its entrance is over."""
    before = tab.eval("window.__nav.entered")
    tab.eval(f"location.hash = {json.dumps(hash_)}")
    tab.wait_for(f"window.__nav.entered > {before} && !document.documentElement.dataset.vt", timeout)


@pytest.mark.parametrize("motion", MOTION)
@pytest.mark.parametrize("view", VIEWS)
def test_every_view_opens_without_a_console_error_in_normal_and_reduced_motion(tab, site, view, motion):
    hash_, ready = VIEWS[view]
    load(tab, site, hash_, still=MOTION[motion])
    settle(tab, ready)
    tab.wait_for("!document.documentElement.dataset.entering", 5)
    shown = tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)")
    assert len(shown) == 1, shown
    assert tab.eval("document.querySelector('main .view:not([hidden]) h1').textContent.length > 0")
    assert tab.eval("getComputedStyle(document.querySelector('main .view:not([hidden])')).opacity") == "1"
    assert tab.errors == []
    assert local(tab, site) == []


@pytest.mark.parametrize("motion", MOTION)
@pytest.mark.parametrize("collection", ["synthetic", "development"])
def test_every_view_opens_when_reached_from_another_view_in_normal_and_reduced_motion(tab, site, collection, motion):
    mine = [k for k in VIEWS if k.startswith("development-") == (collection == "development")]
    first, rest = mine[0], mine[1:]
    load(tab, site, VIEWS[first][0], still=MOTION[motion])
    settle(tab, VIEWS[first][1])
    watch(tab)
    for k in rest + [first]:  # every other view, then back to the first
        go(tab, "#" + VIEWS[k][0].split("#")[-1])
        tab.wait_for(VIEWS[k][1], 30)
        shown = tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)")
        assert len(shown) == 1, (k, shown)
        assert tab.eval("document.querySelector('main .view:not([hidden]) h1').textContent.length > 0"), k
        assert tab.eval("scrollY") == 0, f"{k} starts at the top"
        assert tab.eval("getComputedStyle(document.querySelector('main .view:not([hidden])')).opacity") == "1", k
        assert tab.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"), k
    assert tab.errors == []
    assert local(tab, site) == []
    log = tab.eval("window.__nav")
    moves = len(rest) + 1
    if MOTION[motion]:
        assert log["vt"] == 0, "reduced motion: no view transition"
        assert {a["name"] for a in log["started"] if a["inView"]} == {"view-fade"}
    else:
        assert log["vt"] == moves, "one view transition for each change of view, none for the first load"
        assert {a["name"] for a in log["started"] if a["inView"]} == {"view-in"}


def test_the_entrance_is_a_6px_rise_over_220ms_header_first_then_the_panels_30ms_apart(tab, site):
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    watch(tab)
    go(tab, "#overview")
    started = [a for a in tab.eval("window.__nav.started") if a["inView"]]
    assert started, "the new view's content animated"
    assert {a["name"] for a in started} == {"view-in"}
    assert {a["duration"] for a in started} == {"0.22s"}
    assert {a["ease"] for a in started} == {"cubic-bezier(0.2, 0.8, 0.2, 1)"}
    delays = [round(float(a["delay"][:-1]) * 1000) for a in started]
    # the crumbs and the header together, then each panel 30ms after the one before
    assert delays == [0, 0, 30, 60, 90, 120], delays
    # the keyframes: from opacity 0, 6px down, to rest
    frames = tab.eval(
        """(() => { const k = [...document.styleSheets].flatMap((s) => [...s.cssRules])
             .find((r) => r.name === 'view-in'); return [...k.cssRules].map((r) => r.cssText); })()"""
    )
    assert any("opacity: 0" in f and "translateY(6px)" in f for f in frames), frames
    assert any("opacity: 1" in f and "transform: none" in f for f in frames), frames


def test_a_view_with_many_panels_still_takes_six_steps_at_most(tab, site):
    load(tab, site, "#overview", still=False)
    settle(tab, VIEWS["overview"][1])
    delays = tab.eval(
        """(() => {
          const v = document.querySelector('main .view:not([hidden])');
          for (let i = 0; i < 6; i++) v.append(document.createElement('div'));
          v.classList.remove('enter'); void v.offsetWidth; v.classList.add('enter');
          return [...v.children].map((e) => getComputedStyle(e).animationDelay);
        })()"""
    )
    ms = [round(float(d[:-1]) * 1000) for d in delays]
    assert len(ms) == 12 and ms[:6] == [0, 0, 30, 60, 90, 120] and set(ms[6:]) == {150}, ms
    assert max(ms) + 220 <= 370, "the last panel is in by 370ms"


def test_only_the_main_content_moves_the_top_bar_and_the_side_bar_stay_perfectly_still(tab, site):
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    watch(tab)
    for hash_ in ["#overview", f"#doc-{CARD}", "#review", "#accuracy", "#transactions", "#documents"]:
        go(tab, hash_)
    log = tab.eval("window.__nav")
    assert log["vt"] == 6
    assert [a for a in log["started"] if a["chrome"]] == [], "nothing in the top bar, run bar or side bar animated"
    assert len(set(log["rects"])) == 1, "the top bar, run bar and side bar never moved or changed size"
    # only the view being shown is named for a transition, and only while it runs
    for named in log["named"]:
        assert len(named) == 1 and named[0].startswith("v-"), named
    assert tab.eval(
        "[...document.querySelectorAll('.top, .side, #runbar, main, .view')]"
        ".filter((e) => getComputedStyle(e).viewTransitionName !== 'none').length"
    ) == 0
    assert tab.eval("document.documentElement.dataset.vt") is None
    assert tab.errors == []


def test_the_old_content_fades_out_in_100ms_under_the_new(tab, site):
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    running = tab.eval(
        """new Promise((done) => {
          const start = document.startViewTransition.bind(document);
          document.startViewTransition = (update) => {
            const t = start(update);
            t.ready.then(
              () => done(document.getAnimations().filter((a) => a.effect && a.effect.pseudoElement)
                .map((a) => [a.effect.pseudoElement, a.animationName, a.effect.getComputedTiming().duration])),
              () => done(null));
            return t;
          };
          location.hash = '#overview';
          setTimeout(() => done(null), 5000);
        })"""
    )
    assert running, "a view transition ran"
    assert ["::view-transition-old(main-view)", "view-out", 100] in running, running
    assert not [r for r in running if r[0] == "::view-transition-new(main-view)"], "the new view is not faded again"
    assert not [r for r in running if r[0].endswith("(root)") and r[0].startswith("::view-transition-group")], (
        "the page around the content is held, not animated"
    )


def test_stepping_to_the_next_and_previous_document_animates_only_the_document(tab, site):
    load(tab, site, f"#doc-{CARD}", still=False, height=560)
    settle(tab, VIEWS["document"][1])
    watch(tab)
    title = tab.eval("document.getElementById('dd-t').textContent")
    assert tab.eval("document.getElementById('dd-next').disabled") is False
    tab.eval("scrollTo(0, 80)")
    assert tab.eval("scrollY") > 0, "the page can be scrolled, so starting at the top is a real check"
    for button, differs in [("dd-next", True), ("dd-prev", False)]:
        before = tab.eval("window.__nav.entered")
        tab.eval(f"document.getElementById('{button}').click()")
        tab.wait_for(f"window.__nav.entered > {before} && !document.documentElement.dataset.vt", 20)
        tab.wait_for("!!document.querySelector('#dpaper img')?.complete", 20)
        now = tab.eval("document.getElementById('dd-t').textContent")
        assert (now != title) == differs, (button, title, now)
        assert tab.eval("scrollY") == 0
        tab.eval("scrollTo(0, 80)")
    log = tab.eval("window.__nav")
    assert log["vt"] == 2
    assert [a["name"] for a in log["started"] if a["inView"]].count("view-in") >= 6
    assert [a for a in log["started"] if a["chrome"]] == []
    assert len(set(log["rects"])) == 1
    assert tab.errors == []


def test_reduced_motion_is_a_plain_120ms_fade_with_no_movement_and_no_view_transition(tab, site):
    load(tab, site, "#documents", still=True)
    settle(tab, VIEWS["documents"][1])
    watch(tab)
    for hash_ in ["#overview", f"#doc-{CARD}", "#accuracy"]:
        go(tab, hash_)
    log = tab.eval("window.__nav")
    started = [a for a in log["started"] if a["inView"]]
    assert started and {a["name"] for a in started} == {"view-fade"}
    assert {a["duration"] for a in started} == {"0.12s"}
    assert {a["ease"] for a in started} == {"linear"}
    assert {a["delay"] for a in started} == {"0s"}, "no stagger"
    assert {a["transform"] for a in started} == {"none"}, "nothing moves"
    assert log["vt"] == 0
    assert tab.eval("document.getAnimations().filter((a) => a.animationName === 'view-in').length") == 0
    assert tab.errors == []


def test_without_view_transitions_the_new_content_still_comes_in_and_the_old_is_replaced(tab, site):
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    tab.eval("document.startViewTransition = undefined")  # as in a browser that has none
    watch(tab)
    for hash_ in ["#overview", f"#doc-{CARD}", "#accuracy", "#documents"]:
        go(tab, hash_)
        shown = tab.eval("[...document.querySelectorAll('main .view')].filter(v => !v.hidden).map(v => v.id)")
        assert len(shown) == 1, shown
    log = tab.eval("window.__nav")
    assert log["vt"] == 0
    started = [a for a in log["started"] if a["inView"]]
    assert started and {a["name"] for a in started} == {"view-in"}
    assert {a["duration"] for a in started} == {"0.22s"}
    assert [a for a in log["started"] if a["chrome"]] == []
    assert len(set(log["rects"])) == 1
    assert tab.eval("document.documentElement.dataset.vt") is None
    assert tab.errors == []


def test_the_thread_waits_for_the_entrance_to_end_and_is_then_drawn_where_the_content_rests(tab, site):
    pin = f"L:{CARD}:05:balance"
    load(tab, site, "#documents", still=False)
    settle(tab, VIEWS["documents"][1])
    watch(tab)
    tab.eval(
        f"""(() => {{
          window.__seen = [];
          const path = document.querySelector('#dthread path');
          new MutationObserver(() => window.__seen.push([
            !!document.documentElement.dataset.entering, parseFloat(path.style.opacity || 0)])
          ).observe(path, {{ attributes: true, attributeFilter: ['style'] }});
          location.hash = '#doc-{CARD}?pin=' + encodeURIComponent('{pin}');
        }})()"""
    )
    tab.wait_for("window.__nav.entered > 0 && !document.documentElement.dataset.vt", 20)
    settle(tab, VIEWS["document"][1])
    seen = tab.eval("window.__seen")
    assert [o for e, o in seen if e and o > 0] == [], "the line is never drawn while the content moves"
    assert seen and seen[-1] == [False, 0.9], seen
    assert tab.eval("parseFloat(document.querySelector('#dthread path').style.opacity)") > 0, "drawn once it is over"
    drawn = tab.eval("document.querySelector('#dthread path').getAttribute('d')")
    tab.eval("window.dispatchEvent(new Event('scroll'))")  # draw it again from where everything now is
    assert tab.eval("document.querySelector('#dthread path').getAttribute('d')") == drawn
    assert tab.errors == []


@pytest.mark.parametrize("motion", MOTION)
def test_a_new_view_starts_at_the_top_and_going_back_restores_the_scroll(tab, site, motion):
    load(tab, site, "#documents", still=MOTION[motion], height=600)
    settle(tab, VIEWS["documents"][1])
    watch(tab)
    tab.eval("scrollTo(0, 150)")
    tab.pump(0.2)
    assert tab.eval("scrollY") == 150
    go(tab, "#accuracy")
    tab.wait_for(VIEWS["accuracy"][1], 20)
    assert tab.eval("scrollY") == 0
    tab.eval("scrollTo(0, 60)")
    before = tab.eval("window.__nav.entered")
    tab.eval("history.back()")
    tab.wait_for(f"window.__nav.entered > {before} && location.hash === '#documents'", 20)
    tab.wait_for("scrollY === 150", 5)
    go(tab, "#overview")
    assert tab.eval("scrollY") == 0
    assert tab.errors == []
