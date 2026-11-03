"""The README's first screen, its pictures, its links and its numbers (P54, P55).

The README is what a judge reads first, so what it promises is tested: the order of the first screen (a centred
header with the mark beside the name, the tagline, the badges, an animated banner, and no GIF), the banner itself
(outlines, no font, light and dark, still where reduced motion is asked for, animating as an image in a browser),
the three pictures of "What you get" (taken at 2x, each with a light and a dark variant), the weight of every image,
a page that stays calm (short paragraphs, long reference sections folded away, no emoji, nothing said twice between
the bullets and the judges table), the paragraph the author wrote for "The problem", the links that must resolve,
the three community files, the empty .env.example, and that archivist.verify fails when a figure the README quotes
stops being what its result file says.
"""

import re
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from archivist import verify
from browser import Browser, find_browser, serve

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
DOCS = ("README.md", "eval/README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md")

PROBLEM = (
    "During a bank internship I used AI to build two things: a parser that turned about 2,000 legacy memos into a "
    "clean spreadsheet database, and a working prototype of an automated loan-processing system. Both hit the same "
    "wall. Nobody held all the memos in one place, there was no archive, and the oldest records existed only on "
    "paper; businesses applying for loans brought their earnings in notebooks and loose sheets that staff typed in "
    "by hand. Archivist is the tool I wanted then: it turns scanned financial records into a verified database, "
    "with every value cited to its spot on the page, read twice, checked by arithmetic, and sent to a person when "
    "in doubt."
)
SOLO = "Solo entry by Kamil Shirinov for the Meta Global AI Developer Hackathon 2026: Indie Developer track, Build for Your World."


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(text: str) -> set[str]:
    return {slug(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, re.M)}


def links(text: str) -> list[str]:
    found = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'(?:href|src)="([^"]+)"', text)
    return [u for u in found if not re.match(r"[a-z]+:|mailto:", u)]


def test_the_first_screen_is_in_the_order_judges_read_it():
    order = [
        README.index('<h1 align="center"><img src="assets/brand/logo-light.svg"'),
        README.index("Archivist</h1>"),
        README.index("**The archive that shows its work.**"),
        README.index("[![Live demo]"),
        README.index('srcset="docs/img/banner-still-dark.svg"'),
        README.index('<img src="docs/img/banner-light.svg"'),
        README.index("[Start here](#start-here) ·"),
        README.index("- **What it does.**"),
        README.index("- **How well.**"),
        README.index("- **Where your data goes.**"),
        README.index("**Built during the hackathon.**"),
        README.index("\n## Start here\n"),
        README.index("\n## For judges\n"),
        README.index("\n## The problem\n"),
    ]
    assert order == sorted(order)


def test_the_header_is_a_real_centred_heading_with_the_mark_beside_the_name():
    heading = re.search(r"<h1 align=\"center\">(.*?)</h1>", README, re.S)
    assert heading, "the name is not a real heading"
    inner = heading.group(1)
    mark = re.search(r'<img src="assets/brand/logo-light\.svg" alt="" width="(\d+)" height="(\d+)"[^>]*>', inner)
    assert mark and mark.group(1) == mark.group(2), "the mark is not one square image"
    assert inner[mark.end():].strip() == "Archivist", "the word is not to the right of the mark"
    assert "<picture>" not in inner, "the mark has one version, the same in both themes"
    assert README.index("</h1>") < README.index('<div align="center">') < README.index("**The archive that shows its work.**")


def test_nothing_animated_but_the_banner_is_on_the_first_screen_and_no_gif_is_left():
    first = README.split("\n## Start here\n", 1)[0]
    shown = re.findall(r'<img[^>]*src="([^"]+)"', first)
    assert shown == ["assets/brand/logo-light.svg", "docs/img/banner-light.svg"]
    assert ".gif" not in README.lower() and not list((ROOT / "docs/img").glob("*.gif")), "a GIF has to earn its place, with a caption that says how it was recorded"


def test_one_row_of_badges_with_the_four_meta_models():
    row = next(line for line in README.splitlines() if line.startswith("[![Live demo]"))
    alts = re.findall(r"\[!\[([^\]]+)\]", row)
    assert alts == ["Live demo", "CI", "Apache-2.0", "Docker", "Muse Spark 1.3", "Muse Spark Open", "Muse Glimmer", "SAM 3.1"]


def test_the_problem_is_the_authors_paragraph_and_the_solo_line_follows():
    section = README.split("\n## The problem\n", 1)[1].split("\n## ", 1)[0]
    assert section.strip().split("\n\n") == [PROBLEM, SOLO]


def test_start_here_and_for_judges_have_their_rows():
    start = README.split("\n## Start here\n", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| \*\*(\w+)\*\* \|", start, re.M)
    assert rows == ["Watch", "Try", "Run", "Read"]
    assert "[link pending]" in start.split("**Try**")[0]
    for needle in ("eval/README.md", "PREREGISTRATION_REAL.md", "PREREGISTRATION_OPENW.md", "diagnosis.md", "docker run --rm -p 8000:8000 archivist"):
        assert needle in start
    judges = README.split("\n## For judges\n", 1)[1].split("\n## ", 1)[0]
    assert re.findall(r"^\| \*\*([^*]+)\*\* \((\d+)%\)", judges, re.M) == [
        ("Impact", "30"), ("Use of Meta's models", "25"), ("Demo", "25"), ("Technical depth", "20"),
    ]


def test_the_open_weights_section_claims_the_bonus_by_name_and_keeps_its_caveat():
    heading = "## Open weights: the same pipeline on your own hardware"
    section = README.split(heading, 1)[1].split("\n## ", 1)[0]
    assert section.lstrip().startswith("This is Archivist's entry for the open-weights bonus prize.")
    assert "One scheme, one swap" not in README
    for needle in ("Muse Spark Open for both reads", "Muse Glimmer sorting pages", "Two hosts compared", "Not yet proven on-site"):
        assert needle in section


def test_the_logo_is_one_file_and_the_credits_say_so():
    assert "The two files in `assets/brand/`" not in README and "logo-dark" not in README
    assert "The one file `assets/brand/logo-light.svg`" in README
    assert sorted(p.name for p in (ROOT / "assets/brand").iterdir()) == ["logo-light.svg"]


@pytest.mark.parametrize("doc", DOCS)
def test_every_relative_link_resolves(doc):
    path = ROOT / doc
    text = path.read_text(encoding="utf-8")
    for url in links(text):
        target, _, anchor = url.partition("#")
        file = path if not target else (path.parent / target)
        assert file.exists(), f"{doc} links {url}, which is not there"
        if anchor and file.suffix == ".md":
            assert anchor in anchors(file.read_text(encoding="utf-8")), f"{doc} links {url}, but {file.name} has no such heading"


# --- the images -------------------------------------------------------------------------------------------------

IMG = ROOT / "docs/img"
SHIELDS = ("https://img.shields.io/", "https://github.com/kamil-shirinov/Archivist/actions/workflows/ci.yml/badge.svg")


def section(name: str) -> str:
    return README.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0]


def local_images() -> set[str]:
    """Every committed image the README names, in <img src>, <source srcset> and ![](...)."""
    found = re.findall(r'(?:src|srcset)="([^"]+)"', README) + re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", README)
    return {u for u in found if not u.startswith("http")}


def test_every_image_is_a_committed_file_or_a_shields_badge():
    external = {u for u in re.findall(r'(?:src|srcset)="([^"]+)"', README) + re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", README) if u.startswith("http")}
    assert external and all(u.startswith(SHIELDS) for u in external), sorted(u for u in external if not u.startswith(SHIELDS))
    for name in local_images():
        assert (ROOT / name).is_file(), f"the README shows {name}, which is not committed"


def test_the_readmes_images_stay_under_about_eight_megabytes_and_none_is_left_over():
    files = local_images()
    assert sum((ROOT / f).stat().st_size for f in files) < 8_000_000
    assert {f for f in files if f.startswith("docs/img/")} == {f"docs/img/{p.name}" for p in IMG.iterdir()}, "a file in docs/img is not in the README"


def test_what_you_get_has_three_pictures_taken_at_2x_each_in_light_and_dark():
    block = section("What you get")
    pictures = re.findall(r"<picture>(.*?)</picture>", block, re.S)
    assert len(pictures) == 3 and len(re.findall(r"<img\b", block)) == 3
    assert [re.search(r'<img src="docs/img/(\w+)-light\.png"', p).group(1) for p in pictures] == ["specimen", "review", "record"]
    for name, p in zip(("specimen", "review", "record"), pictures):
        assert f'<source media="(prefers-color-scheme: dark)" srcset="docs/img/{name}-dark.png">' in p
        assert re.search(r'alt="[^"]{60,}"', p), f"{name} has no description"
        for theme in ("light", "dark"):
            with Image.open(IMG / f"{name}-{theme}.png") as im:
                assert im.format == "PNG" and im.width >= 1900, f"{name}-{theme}.png is not a 2x capture"
    assert "local build" in block, "the screenshots say how they were made"


# --- the banner ---------------------------------------------------------------------------------------------------

THEMES = ("light", "dark")
WORD = {"light": "#4A55D4", "dark": "#8A93F5"}  # the brand indigo on the light panel, a lighter tint of it on the dark one


def luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def banner(name: str) -> str:
    return (IMG / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("theme", THEMES)
def test_the_banner_is_drawn_as_outlines_with_the_brand_indigo_and_nothing_fetched(theme):
    svg = banner(f"banner-{theme}.svg")
    assert 'viewBox="0 0 1200 220"' in svg and 'width="1200" height="220"' in svg
    assert len(svg.encode()) < 150_000
    for forbidden in ("<text", "<tspan", "<script", "<image", "<foreignObject", "@font-face", "@import", "url(http", "href=", "<use", "onload"):
        assert forbidden not in svg, forbidden
    words = re.findall(r'<path class="w (w\d)" fill="([^"]+)" d="([^"]+)"', svg)
    assert [(c, fill) for c, fill, _ in words] == [(w, WORD[theme]) for w in ("w1", "w2", "w3")]
    assert all(len(d) > 200 for _, _, d in words), "a word is not outlined"
    assert len(set(d for _, _, d in words)) == 3
    label = re.search(r'aria-label="([^"]+)"', svg).group(1)
    assert all(f"Every value, {w}." in label for w in ("cited", "read twice", "checked")) and f"<title>{label}</title>" in svg


def test_the_banners_light_and_dark_differ_in_ground_and_ink_but_not_in_the_words():
    light, dark = banner("banner-light.svg"), banner("banner-dark.svg")
    assert light != dark and re.findall(r' d="[^"]+"', light) == re.findall(r' d="[^"]+"', dark), "the same outlines"
    assert 'fill="#16181D"' in light and 'fill="#E8E9ED"' in dark


@pytest.mark.parametrize("theme", THEMES)
def test_the_changing_word_reads_at_4_5_to_1_on_its_panel_in_both_themes(theme):
    """The brand indigo is 3.2:1 on the dark panel and looked dim, so the dark banner uses a lighter tint of it; the light
    one keeps #4A55D4. The panel is the base fill, and also the base fill under the strongest of its two glows."""
    svg = banner(f"banner-{theme}.svg")
    fill = re.search(r'<rect x="\.5" y="\.5" width="1199" height="219" rx="22" fill="(#[0-9A-F]{6})"', svg).group(1)
    glow = re.search(r'<stop offset="0" stop-color="(#[0-9A-F]{6})" stop-opacity="([\d.]+)"/>', svg)
    base = [int(fill[i : i + 2], 16) for i in (1, 3, 5)]
    tint = [int(glow.group(1)[i : i + 2], 16) for i in (1, 3, 5)]
    a = float(glow.group(2))
    under_glow = "#" + "".join(f"{round(a * t + (1 - a) * b):02X}" for t, b in zip(tint, base))
    assert contrast(WORD[theme], fill) >= 4.5 and contrast(WORD[theme], under_glow) >= 4.5, (theme, contrast(WORD[theme], fill), contrast(WORD[theme], under_glow))
    assert WORD["light"] == "#4A55D4" and contrast("#4A55D4", "#0E1016") < 4.5, "the brand indigo itself is why the dark one is lighter"


@pytest.mark.parametrize("theme", THEMES)
def test_the_banner_moves_only_by_opacity_and_a_few_pixels_and_its_last_frame_is_the_still(theme):
    svg = banner(f"banner-{theme}.svg")
    css = re.search(r"<style>(.*?)</style>", svg, re.S).group(1)
    assert css.startswith(".w{opacity:0}.w3{opacity:1}"), "without motion the last word shows alone"
    head, motion = css.split("@media (prefers-reduced-motion:no-preference){", 1)
    assert "animation" not in head and "keyframes" not in head, "motion outside the no-preference block"
    assert re.findall(r"@keyframes (w\d)", motion) == ["w1", "w2", "w3"]
    declared = set(re.findall(r"([a-z-]+):", " ".join(re.findall(r"\{(opacity:[^{}]*)\}", motion))))
    assert declared == {"opacity", "transform"}
    assert all(abs(int(y)) <= 14 for y in re.findall(r"translateY\((-?\d+)px\)", motion)), "a few pixels only"
    assert re.findall(r"animation:w\d (\d+(?:\.\d+)?)s", motion) == ["11.6"] * 3


@pytest.mark.parametrize("theme", THEMES)
def test_the_still_banner_is_the_last_frame_alone(theme):
    still, moving = banner(f"banner-still-{theme}.svg"), banner(f"banner-{theme}.svg")
    for gone in ("<style", "animation", "@keyframes", 'class="w w1"', 'class="w w2"', 'class="w w3"'):
        assert gone not in still, gone
    last = re.search(rf'<path class="w w3" fill="{WORD[theme]}" d="([^"]+)"', moving).group(1)
    assert f'fill="{WORD[theme]}" d="{last}"' in still
    assert len(re.findall(r"<path ", still)) == 2, "the first words and the last, nothing else"


def test_the_picture_names_a_still_for_reduced_motion_before_the_moving_banner():
    picture = re.search(r"<picture>(.*?)</picture>", README, re.S).group(1)
    sources = re.findall(r'<source media="([^"]+)" srcset="([^"]+)">', picture)
    assert sources == [
        ("(prefers-reduced-motion: reduce) and (prefers-color-scheme: dark)", "docs/img/banner-still-dark.svg"),
        ("(prefers-reduced-motion: reduce)", "docs/img/banner-still-light.svg"),
        ("(prefers-color-scheme: dark)", "docs/img/banner-dark.svg"),
    ]
    assert re.search(r'<img src="docs/img/banner-light\.svg" alt="[^"]{20,}"', picture)


needs_browser = pytest.mark.skipif(find_browser() is None, reason="no Chromium or Chrome found (set ARCHIVIST_BROWSER)")


@pytest.fixture(scope="module")
def banner_page(tmp_path_factory):
    """The README's own <picture> for the banner, on a page beside copies of the files, served from localhost."""
    top = tmp_path_factory.mktemp("banner")
    (top / "docs/img").mkdir(parents=True)
    for p in IMG.glob("banner-*.svg"):
        (top / "docs/img" / p.name).write_bytes(p.read_bytes())
    picture = re.search(r"<picture>.*?</picture>", README, re.S).group(0)
    (top / "page.html").write_text(f'<!doctype html><meta charset="utf-8"><body style="margin:0">{picture.replace(chr(34) + "100%" + chr(34), chr(34) + "1200" + chr(34))}', encoding="utf-8")
    with serve(top) as base, Browser() as browser:
        yield base + "/page.html", browser


def frames(browser, url, tmp_path, dark, still, count=7, every=0.9):
    tab = browser.tab()
    tab.call("Page.bringToFront")
    tab.call("Emulation.setFocusEmulationEnabled", enabled=True)
    tab.open(url, width=1200, height=220, dark=dark, still=still)
    tab.wait_for("document.querySelector('img').complete && document.querySelector('img').naturalWidth > 0")
    shown = tab.eval("document.querySelector('img').currentSrc.split('/').pop()")
    images = []
    for k in range(count):
        tab.screenshot(tmp_path / f"f{k}.png")
        images.append(Image.open(tmp_path / f"f{k}.png").convert("RGB"))
        tab.pump(every)
    tab.close()
    return shown, images


def changed(a, b) -> int:
    """How many pixels differ by more than 24 in any colour channel."""
    r, g, bl = ImageChops.difference(a, b).split()
    return sum(ImageChops.lighter(ImageChops.lighter(r, g), bl).histogram()[25:])


@needs_browser
@pytest.mark.parametrize("dark", [False, True])
def test_the_banner_animates_as_an_image_and_the_words_change(banner_page, tmp_path, dark):
    url, browser = banner_page
    shown, images = frames(browser, url, tmp_path, dark=dark, still=False)
    assert shown == ("banner-dark.svg" if dark else "banner-light.svg")
    assert max(changed(images[0], im) for im in images[1:]) > 3000, "the banner did not change in about six seconds"


@needs_browser
@pytest.mark.parametrize("dark", [False, True])
def test_where_reduced_motion_is_asked_for_the_banner_is_the_still_last_frame(banner_page, tmp_path, dark):
    url, browser = banner_page
    shown, images = frames(browser, url, tmp_path, dark=dark, still=True, count=3, every=0.7)
    assert shown == ("banner-still-dark.svg" if dark else "banner-still-light.svg")
    assert all(changed(images[0], im) == 0 for im in images[1:]), "something moved"


# --- a page that stays calm ----------------------------------------------------------------------------------------


def outside_details(text: str) -> str:
    return re.sub(r"<details>.*?</details>", "", text, flags=re.S)


def test_the_long_reference_sections_are_folded_away_with_a_summary_that_says_what_is_inside():
    for name in ("What we tried and dropped", "Code tour"):
        block = section(name)
        assert "<details>" in block and "</details>" in block, name
        assert "|" not in outside_details(block), f"{name} has a table outside its details"
    summaries = re.findall(r"<summary>(.*?)</summary>", README)
    assert len(summaries) >= 8 and all(len(s.split()) >= 4 for s in summaries), summaries
    tables = re.findall(r"(?:^\|.*\n)+", re.sub(r"```.*?```", "", outside_details(README), flags=re.S), re.M)
    assert all(t.count("\n") <= 7 for t in tables), "a long table is in the open"


def test_paragraphs_are_short_and_there_is_no_emoji():
    body = re.sub(r"```.*?```", "", outside_details(README), flags=re.S)
    prose = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.lstrip().startswith(("|", "<", "#", "-", "1.", "[", "!"))]
    too_long = [p[:50] for p in prose if len(p) > 350 and not p.startswith("During a bank internship")]
    assert not too_long, too_long
    assert all(len(i) <= 470 for i in re.findall(r"^(?:- |\d+\. ).+$", body, re.M))
    assert not re.search("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]", README), "an emoji"


def sentences(text: str) -> set[str]:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text.replace("<br>", " "))
    text = re.sub(r"[*`|]", "", text)
    parts = re.split(r"(?<=[.!?;:])\s+", text)
    return {re.sub(r"\W+", " ", p).strip().lower() for p in parts if len(p.split()) >= 6}


def test_the_how_well_bullet_carries_the_synthetic_headline_as_one_clause_and_verify_checks_it(at_root, monkeypatch, tmp_path):
    bullet = next(line for line in README.split("\n## Start here\n", 1)[0].splitlines() if line.startswith("- **How well.**"))
    clause = "0.36% of accepted values were wrong against 4.45% for a single read"
    assert clause in bullet and "synthetic" in bullet and "not met" in bullet, "the headline, and the misses, are on the first screen"
    edited = tmp_path / "README.md"
    edited.write_text(README.replace(clause, "0.35% of accepted values were wrong against 4.45% for a single read"), encoding="utf-8")
    monkeypatch.setattr(verify, "README", edited)
    found = verify.check_readme()
    assert found[0].status == verify.FAIL and any("How well" in p for p in found[0].problems)


def test_no_sentence_is_said_twice_between_the_first_screen_bullets_and_the_judges_table():
    bullets = "\n".join(re.findall(r"^- \*\*.+$", README.split("\n## Start here\n", 1)[0], re.M))
    assert len(bullets.splitlines()) == 3
    assert not sentences(bullets) & sentences(section("For judges")), sentences(bullets) & sentences(section("For judges"))


def test_the_community_files_have_no_email_address_and_say_where_to_report():
    for doc in ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), f"{doc} holds an email address"
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Report a vulnerability" in security and "main" in security and "static" in security
    conduct = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    assert "version 2.1" in conduct and "Report a vulnerability" in conduct
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for needle in ("uv sync --frozen", "uv run pytest -q && uv run python -m archivist.replay", "DECISIONS.md", "archivist.templates.approve", "No tuning on held-out pages"):
        assert needle in contributing


def test_env_example_lists_the_names_live_mode_reads_and_holds_no_value():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    names = re.findall(r"^#?\s*([A-Z][A-Z_]+)=", text, re.M)
    assert names == ["META_API_KEY", "BASETEN_API_KEY", "FIREWORKS_API_KEY", "BUDGET_CAP_USD", "BASETEN_CAP_USD", "FIREWORKS_CAP_USD", "GLIMMER_CAP_USD"]
    assert all(not line.partition("=")[2].strip() for line in text.splitlines() if re.match(r"[A-Z_]+_KEY=", line)), "a key holds a value"
    assert "need none" in text
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert ignored and subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=ROOT).returncode == 1


# --- archivist.verify's check of the README's numbers ------------------------------------------------------------


@pytest.fixture
def at_root(monkeypatch):
    monkeypatch.chdir(ROOT)


def test_verify_passes_on_the_readme_as_it_is(at_root):
    results = verify.check_readme()
    assert [r.status for r in results if r.name == "README numbers"] == [verify.PASS], [r.problems for r in results]


def test_verify_fails_when_a_quoted_figure_changes(at_root, monkeypatch, tmp_path):
    for old, new in (("0.36% (0.14% to 0.67%)", "0.35% (0.14% to 0.67%)"), ("36.9% (24.7%–50.4%)", "26.9% (24.7%–50.4%)"), ("27.1% (13.9%–49.9%)", "2.1% (13.9%–49.9%)")):
        assert old in README
        edited = tmp_path / "README.md"
        edited.write_text(README.replace(old, new), encoding="utf-8")
        monkeypatch.setattr(verify, "README", edited)
        found = verify.check_readme()
        assert found[0].status == verify.FAIL and any(old.split(" (")[0] in p or "does not say" in p for p in found[0].problems), old


def test_verify_fails_when_a_sentence_goes(at_root, monkeypatch, tmp_path):
    edited = tmp_path / "README.md"
    edited.write_text(README.replace("sorted all 4,569 held-out", "sorted all held-out"), encoding="utf-8")
    monkeypatch.setattr(verify, "README", edited)
    assert verify.check_readme()[0].status == verify.FAIL


def test_a_missing_run_record_is_skipped_not_passed(at_root, monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "RUN_V1", tmp_path / "run.json")
    results = verify.check_readme()
    assert [r.status for r in results] == [verify.PASS, verify.SKIP]


def test_verify_notices_a_verdict_that_flips(at_root):
    v1, open_ = verify._json(verify.SCORE_V1), verify._json(verify.SCORE_OPEN)
    assert all(ok for _, ok in verify._verdicts(v1, open_))
    open_["o1"]["met"] = True
    assert [what for what, ok in verify._verdicts(v1, open_) if not ok] == ["O1 is not met"]
