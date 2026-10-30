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
    load(tab, site, f"#doc-{CARD}")
    settle(tab, VIEWS["document"][1])
    assert tab.eval(
        "[...document.querySelectorAll('#runbar .runswitch button')].map(b => b.textContent)"
    ) == [
        "Hosted",
        "Open weights",
    ]
    tab.eval("document.querySelector('#runbar [data-run=\"test-archivist-B\"]').click()")
    tab.wait_for(
        "location.search.includes('test-archivist-B') && document.documentElement.dataset.ready === '1'",
        60,
    )
    settle(tab, VIEWS["document"][1])
    assert tab.eval("location.hash") == f"#doc-{CARD}"
    bar = tab.eval("document.getElementById('runbar').textContent")
    assert "test-archivist-B" in bar and "Muse Spark Open" in bar and "open-weight" in bar
    assert (
        tab.eval(
            "document.querySelector('#runbar [data-run=\"test-archivist-B\"]').getAttribute('aria-pressed')"
        )
        == "true"
    )
    assert tab.errors == []


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
