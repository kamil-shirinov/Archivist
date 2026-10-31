"""The local app's live view in a real browser (Chromium over the DevTools protocol, tests/browser.py).

archivist.live's server is run on a free port over a scripted backend, with a drawn page: the test
picks the page, reads it live and then replays it, and checks the seven steps, the list of model
calls, the values on the page, the mode shown on every view, and the finish in the normal document
view and review queue. The other half of the test is the published site: the plain file server, as
GitHub Pages serves the repository, must show none of it. Nothing leaves the machine, no model or
key is used, and the tests skip, saying so, where no Chromium or Chrome can be found
(set ARCHIVIST_BROWSER to name one).
"""

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
    Scripted.delay = 0.0
    running.close()


def text(tab, selector: str) -> str:
    return tab.eval(f"document.querySelector({selector!r})?.textContent ?? ''")


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

        # a live read
        tab.eval("document.querySelector('#l-mode button[data-m=live]').click()")
        assert text(tab, "#mode-pill") == "Live calls"
        assert text(tab, "#l-go") == "Read live"
        tab.eval("document.getElementById('l-go').click()")
        tab.wait_for("document.getElementById('l-go').disabled && document.querySelectorAll('#l-calls li').length > 0")
        assert text(tab, "#mode-pill") == "Live calls"
        assert tab.eval("document.getElementById('mode-pill').hasAttribute('data-busy')")
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
        tab.eval("document.getElementById('l-go').click()")
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
