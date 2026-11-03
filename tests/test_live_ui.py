"""The local app's live view in a real browser (Chromium over the DevTools protocol, tests/browser.py).

archivist.live's server is run on a free port over a scripted backend, with a drawn page: the test
picks the page, reads it live and then replays it, and checks the seven steps, the list of model
calls, the values on the page, the mode shown on every view, and the finish in the normal document
view and review queue. The other half of the test is the published site: the plain file server, as
GitHub Pages serves the repository, must show none of it. Nothing leaves the machine, no model or
key is used, and the tests skip, saying so, where no Chromium or Chrome can be found
(set ARCHIVIST_BROWSER to name one).
"""

import threading
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from browser import Browser, find_browser, serve
from test_live import MEMO_FIELDS, PAGE, ROOT, Running, Scripted, world  # noqa: F401

if find_browser() is None:
    pytest.skip("no Chromium or Chrome found (set ARCHIVIST_BROWSER)", allow_module_level=True)

SHOTS = ROOT / "ui" / "screenshots"
READY = "document.documentElement.dataset.ready === '1'"


def drawn_page(path: Path) -> None:
    """A memo-sized page with a bar of ink where each value is cited."""
    image = Image.new("RGB", (400, 300), "white")
    canvas = ImageDraw.Draw(image)
    for i in range(len(MEMO_FIELDS)):
        y = int((60 + 100 * i) * 0.3)
        canvas.rectangle([42, y + 2, 150, y + 8], fill=(30, 30, 30))
    image.save(path)


@pytest.fixture
def local(world):  # noqa: F811
    drawn_page(world.synthetic_root / "dev" / "images" / "memo-0001.jpg")
    Scripted.delay = 0.04
    running = Running(world)
    yield world, f"http://127.0.0.1:{running.port}"
    if Scripted.gate is not None:
        Scripted.gate.set()  # a test that failed while holding a call must not leave it held
    Scripted.delay = 0.0
    running.close()


def text(tab, selector: str) -> str:
    return tab.eval(f"document.querySelector({selector!r})?.textContent ?? ''")


def press(tab, element: str) -> None:
    """Click a button once it is enabled. After a page loads, the local app keeps its read button
    disabled until the server has answered its status request, and a click on a disabled button does
    nothing; on a slow machine a click made at once would leave the test waiting for a read that never began."""
    tab.wait_for(f"!document.getElementById({element!r}).disabled")
    tab.eval(f"document.getElementById({element!r}).click()")


def test_a_page_is_read_live_then_replayed_and_opened_in_the_normal_views(local):
    world, base = local
    SHOTS.mkdir(exist_ok=True)
    with Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/ui/#live", width=1440, height=900, still=False)
        tab.wait_for(READY + " && document.querySelectorAll('#l-page option').length > 0")
        tab.eval("sessionStorage.setItem('archivist-live-auto', '0')")

        # the app knows it is the local one, and says which mode it is in, on every view
        assert tab.eval("!!document.querySelector('meta[name=archivist-live]')")
        assert text(tab, "#mode-pill") == "Replay"
        assert "Read a page" in text(tab, ".side a[data-v=live]")
        for view in ("overview", "review", "documents"):
            tab.eval(f"location.hash = '{view}'")
            tab.wait_for(f"!document.getElementById('v-{view}').hidden")
            assert text(tab, "#mode-pill") in ("Replay", "Live calls")
            assert tab.eval("document.getElementById('mode-pill').getBoundingClientRect().width") > 0
        tab.eval("location.hash = 'live'")
        tab.wait_for("!document.getElementById('v-live').hidden")
        assert tab.eval("[...document.querySelectorAll('#l-page option')].map(o => o.value)") == [PAGE]

        # a live read, held at its first call so that it is still in flight when the test looks,
        # however slowly the test polls (a whole read takes less time than one slow poll)
        tab.eval("document.querySelector('#l-mode button[data-m=live]').click()")
        assert text(tab, "#mode-pill") == "Live calls"
        assert text(tab, "#l-go") == "Read live"
        Scripted.gate = threading.Event()
        press(tab, "l-go")
        tab.wait_for("document.getElementById('l-go').disabled && document.querySelectorAll('#l-calls li').length > 0")
        assert text(tab, "#mode-pill") == "Live calls"
        assert tab.eval("document.getElementById('mode-pill').hasAttribute('data-busy')")
        Scripted.gate.set()
        tab.wait_for("!!document.getElementById('l-open')", timeout=60)
        tab.screenshot(SHOTS / "live-done.png")

        steps = tab.eval("[...document.querySelectorAll('#l-steps li')].map(li => [li.dataset.k, li.classList.contains('done')])")
        assert steps == [[k, True] for k in ("recognise", "read", "snap", "sam", "blind", "rules", "decide")]
        rows = tab.eval(
            "[...document.querySelectorAll('#l-calls li')].map(li => [li.className, li.querySelector('b').textContent, li.querySelector('.lc-src').textContent])"
        )
        assert len(rows) == 2 + 2 + len(MEMO_FIELDS)  # recognise, read, stamp and stain, one re-read each
        assert {r[1] for r in rows} == {"Muse Spark 1.3", "SAM 3.1"}
        assert {r[2] for r in rows} == {"Live"}
        assert "live" in text(tab, "#l-tally") and "cache" in text(tab, "#l-tally")
        assert tab.eval("document.querySelectorAll('#lstage svg.ov rect.wbx').length") == len(MEMO_FIELDS)
        assert tab.eval("document.querySelectorAll('#lstage svg.ov rect.sam').length") == 1  # the stamp
        assert "Read in" in text(tab, "#l-now") and "to the models" in text(tab, "#l-now")
        assert text(tab, "#mode-pill") == "Live calls" and not tab.eval(
            "document.getElementById('mode-pill').hasAttribute('data-busy')"
        )

        # it opens in the normal document view
        tab.eval("document.getElementById('l-open').click()")
        tab.wait_for(READY + " && location.hash === '#doc-memo-0001' && !!document.querySelector('#dpaper img')?.complete")
        assert "run=live-" in tab.eval("location.search")
        assert "Live read" in text(tab, "#coll-name")
        assert text(tab, "#mode-pill") == "Live calls"
        assert "live-" in tab.eval("document.title")
        tab.wait_for("document.querySelectorAll('#drecord tr, #drecord .rec, #drecord div').length > 3")
        tab.screenshot(SHOTS / "live-document.png")
        tab.eval("location.hash = 'review-memo-0001'")
        tab.wait_for("!document.getElementById('v-review').hidden && !!document.querySelector('#stage img')?.complete")

        # a replay of the same page: the cache answers, nothing is asked, nothing is spent
        asked = len(Scripted.reached)
        tab.eval("location.hash = 'live'")
        tab.wait_for("!document.getElementById('v-live').hidden")
        tab.eval("document.querySelector('#l-mode button[data-m=replay]').click()")
        tab.eval("document.querySelector('#l-speed button[data-s=\"10\"]').click()")
        assert text(tab, "#mode-pill") == "Replay" and text(tab, "#l-go") == "Replay"
        press(tab, "l-go")  # this page was loaded afresh, so its status request may still be in flight
        tab.wait_for("!!document.getElementById('l-open')", timeout=60)
        tab.screenshot(SHOTS / "live-replay.png")
        sources = tab.eval("[...new Set([...document.querySelectorAll('#l-calls li .lc-src')].map(e => e.textContent))]")
        assert sources == ["Cache"]
        was = tab.eval("[...new Set([...document.querySelectorAll('#l-calls li .lc-t')].map(e => e.textContent.split(' ')[0]))]")
        assert was == ["was"]  # a hit shows how long its answer once took, never a time of its own
        assert "Nothing was asked and nothing was spent" in text(tab, "#l-now")
        assert text(tab, "#mode-pill") == "Replay"
        assert len(Scripted.reached) == asked
        tab.eval("document.getElementById('l-open').click()")
        tab.wait_for(READY + " && location.hash === '#doc-memo-0001' && !!document.querySelector('#dpaper img')?.complete")
        assert "Replay" in text(tab, "#coll-name") and text(tab, "#mode-pill") == "Replay"

        # the committed runs are still there beside them
        tab.eval("document.getElementById('coll').click()")
        menu = tab.eval("document.getElementById('coll-menu').textContent")
        assert "Box 14" in menu and "Live read" in menu and "Replay" in menu

        assert tab.errors == []
        assert all(url.startswith(base) or url.startswith("data:") for url in tab.requests)


def test_the_wording_of_a_step_names_the_model_that_runs_it():
    """Recognising a page is Muse Glimmer's step where it sorts and Muse Spark's where the page is read from its image."""
    with serve(ROOT) as base, Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/ui/index.html", still=True)
        said = tab.eval(
            """(async () => {
              const { whatItDoes } = await import('./js/live/words.js');
              const names = { extractor: 'Muse Spark 1.3', sorter: 'Muse Glimmer', segmenter: 'SAM 3.1', rereader: 'Muse Spark 1.3' };
              return {
                glimmer: whatItDoes('recognise', 'Muse Glimmer', names),
                spark: whatItDoes('recognise', 'Muse Spark 1.3', names),
                unrouted: whatItDoes('recognise', null, names),
                read: whatItDoes('read', 'Muse Spark 1.3', names),
                sam: whatItDoes('sam', null, names),
                code: whatItDoes('snap', null, names),
              };
            })()"""
        )
        assert said["glimmer"] == "Muse Glimmer is asked what kind of page this is."
        assert said["spark"] == "Muse Spark 1.3 is asked what kind of page this is."
        assert said["unrouted"] == "Muse Spark 1.3 is asked what kind of page this is.", "no model on the event: the extractor, as before"
        assert said["read"].startswith("Muse Spark 1.3 reads every value") and said["sam"].startswith("SAM 3.1 looks for")
        assert said["code"] == "Plain code moves each box onto the printed ink."
        assert tab.errors == []


@pytest.mark.parametrize("who", ["Muse Glimmer", "Muse Spark 1.3"])
def test_the_now_panel_and_the_step_list_name_the_model_the_server_says_ran_the_recognise_step(local, who):
    world, base = local
    with Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/ui/#live", width=1440, height=900, still=True)
        tab.wait_for(READY + " && document.querySelectorAll('#l-page option').length > 0")
        tab.eval("sessionStorage.setItem('archivist-live-auto', '0')")
        # the session as the server tells it, with the recognise step carrying the model that ran it
        tab.eval(
            """(() => {
              const real = window.fetch.bind(window), who = %r;
              window.fetch = async (url, init) => {
                const res = await real(url, init);
                if (!String(url).includes('/session/')) return res;
                const body = await res.json(), first = body.events[0];
                const models = [{ role: 'extractor', name: 'Muse Spark 1.3' }, { role: 'rereader', name: 'Muse Spark 1.3' }, { role: 'segmenter', name: 'SAM 3.1' }, ...(who === 'Muse Glimmer' ? [{ role: 'sorter', name: who }] : [])];
                const step = { type: 'step', seq: 1000, step: 'recognise', state: 'start', index: 0, model: who, facts: {} };
                return new Response(JSON.stringify({ ...body, events: [{ ...first, models }, step] }), { status: 200, headers: { 'content-type': 'application/json' } });
              };
            })()"""
            % who
        )
        tab.eval("document.querySelector('#l-mode button[data-m=live]').click()")
        Scripted.gate = threading.Event()
        press(tab, "l-go")
        tab.wait_for("!!document.querySelector('#l-steps li[data-k=recognise].on')")
        assert text(tab, "#l-now p") == f"{who} is asked what kind of page this is."
        assert text(tab, "#l-steps li[data-k=recognise] span") == who
        assert text(tab, "#l-now h3") == "Recognise the page"
        Scripted.gate.set()
        assert tab.errors == []


def test_the_pill_and_the_view_work_at_a_phone_width(local):
    world, base = local
    with Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/ui/#live", width=390, height=844, mobile=True)
        tab.wait_for(READY + " && document.querySelectorAll('#l-page option').length > 0")
        box = tab.eval("(r => [r.left, r.right, r.top, r.bottom])(document.getElementById('mode-pill').getBoundingClientRect())")
        assert 0 <= box[0] and box[1] <= 390 and box[3] <= 60
        assert text(tab, "#mode-pill") == "Replay"
        SHOTS.mkdir(exist_ok=True)
        tab.screenshot(SHOTS / "live-phone.png")
        assert tab.errors == []


def test_a_stopped_or_failed_read_says_so_and_the_mode_stays_honest(local):
    world, base = local
    Scripted.gate = None
    world.cache_dir.mkdir(exist_ok=True)
    with Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/ui/#live", width=1440, height=900)
        tab.wait_for(READY + " && document.querySelectorAll('#l-page option').length > 0")
        # nothing is cached: a replay says so and does not start
        assert tab.eval("document.getElementById('l-go').disabled")
        assert "nothing is cached" in text(tab, "#l-note").lower()
        tab.eval("document.querySelector('#l-mode button[data-m=live]').click()")
        assert not tab.eval("document.getElementById('l-go').disabled")
        Scripted.delay = 0.5
        tab.eval("document.getElementById('l-go').click()")
        tab.wait_for("!document.getElementById('l-stop').hidden")
        tab.eval("document.getElementById('l-stop').click()")
        tab.wait_for("document.getElementById('l-stage').textContent === 'Stopped'", timeout=30)
        assert "Nothing further was asked" in text(tab, "#l-now")
        assert text(tab, "#mode-pill") == "Live calls"
        assert not tab.eval("document.getElementById('mode-pill').hasAttribute('data-busy')")
        assert not tab.eval("document.getElementById('l-go').disabled")
        time.sleep(0.1)
        assert tab.errors == []


def test_the_published_site_has_no_live_read_and_no_upload_box():
    """The repository served as plain files, as GitHub Pages serves it: none of the local app."""
    with serve(ROOT) as base, Browser() as browser:
        tab = browser.tab()
        tab.open(f"{base}/ui/#overview", width=1440, height=900)
        tab.wait_for(READY)
        assert not tab.eval("!!document.querySelector('meta[name=archivist-live]')")
        assert not tab.eval("!!document.getElementById('mode-pill') || !!document.getElementById('v-live')")
        assert "Read a page" not in tab.eval("document.querySelector('.side').textContent")
        assert tab.eval("document.querySelectorAll('input[type=file]').length") == 0
        tab.eval("location.hash = 'documents'")
        tab.wait_for("!document.getElementById('v-documents').hidden")
        tab.eval("document.getElementById('add-doc').click()")
        assert "replays recorded runs only" in text(tab, "#toast")
        tab.eval("location.hash = 'live'")  # no such view here: the overview stands
        tab.wait_for("!document.getElementById('v-overview').hidden")
        tab.pump(0.3)
        assert not [u for u in tab.requests if "/api/" in u or "live.js" in u or "live.css" in u]
        assert tab.errors == []
