"""P55: the README's banner, drawn from the landing page's own headline font as outlines (no font in the file).

    uvx --from "fonttools[woff]" --with uharfbuzz python docs/make_banner.py

writes docs/img/banner-light.svg and banner-dark.svg (animated) and banner-still-light.svg and banner-still-dark.svg
(the last frame alone). fontTools and HarfBuzz are not dependencies of
this project; they are fetched by uvx for this one run and the two SVGs are committed (docs/landing/fonts/README.md
does the same for the fonts).

The line is "Every value, <word>." with the last word changing: cited, then read twice, then checked (in the brand
indigo, #4A55D4), each fading in as it rises a few pixels and fading out as it keeps rising, looping. Every glyph is
a path taken from docs/landing/fonts/Newsreader-Latin.woff2 (SIL OFL 1.1, NEWSREADER-OFL.txt beside it), weight 500,
placed by HarfBuzz so the kerning is the font's own. Nothing is fetched and nothing runs: the animation is CSS inside
the file, in prefers-reduced-motion: no-preference, so wherever motion is not wanted (or CSS animation is not run at
all) the last frame, "Every value, checked.", is what shows. A browser may not tell an SVG used as an image what the
system's reduced-motion setting is, so the README's <picture> also names the still files for that setting.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "docs/landing/fonts/Newsreader-Latin.woff2"
OUT = ROOT / "docs/img"

W, H = 1200, 220
SIZE = 92  # em, in SVG units
BASELINE = 128
WEIGHT = 500
PREFIX = "Every value,"
WORDS = ("cited.", "read twice.", "checked.")
INDIGO = "#4A55D4"

THEMES = {
    "light": dict(ink="#16181D", fill="#FBFBF9", line="#E3E2DC", glow_a="#4A55D4", glow_a_op=".085", glow_b="#F4B23A", glow_b_op=".13"),
    "dark": dict(ink="#E8E9ED", fill="#0E1016", line="#23262F", glow_a="#4A55D4", glow_a_op=".16", glow_b="#F4B23A", glow_b_op=".06"),
}

# Keyframes as (second, opacity, translateY in px). A word fades in as it rises 12 px, holds, then fades out as it
# keeps rising 8 px; the next one comes in after a short gap, so two words are never on top of each other.
# "checked." holds longest, and "cited." comes in again at the end of the loop, so the loop has no jump.
LOOP = 11.6  # seconds
KEYFRAMES = {
    "w1": [(0, 1, 0), (2.7, 1, 0), (3.1, 0, -8), (10.7, 0, 12), (11.3, 1, 0), (LOOP, 1, 0)],
    "w2": [(0, 0, 12), (3.2, 0, 12), (3.8, 1, 0), (6.1, 1, 0), (6.5, 0, -8), (LOOP, 0, -8)],
    "w3": [(0, 0, 12), (6.6, 0, 12), (7.2, 1, 0), (10.2, 1, 0), (10.6, 0, -8), (LOOP, 0, -8)],
}


def load():
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = TTFont(str(FONT))
    font = instancer.instantiateVariableFont(font, {"wght": WEIGHT})
    font.flavor = None
    buf = io.BytesIO()
    font.save(buf)
    return TTFont(io.BytesIO(buf.getvalue())), buf.getvalue()


def shape(data: bytes, text: str):
    import uharfbuzz as hb

    face = hb.Face(hb.Blob(data))
    hbfont = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})
    return [(i.codepoint, p.x_advance, p.x_offset, p.y_offset) for i, p in zip(buf.glyph_infos, buf.glyph_positions)]


def num(v: float) -> str:
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def outline(font, data: bytes, text: str, x: float) -> tuple[str, float]:
    """The path data of text with its origin at x on the baseline, and its advance, both in SVG units."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen

    upm = font["head"].unitsPerEm
    k = SIZE / upm
    order = font.getGlyphOrder()
    glyphs = font.getGlyphSet()
    pen = SVGPathPen(glyphs, ntos=num)
    pos = 0
    for gid, advance, dx, dy in shape(data, text):
        tp = TransformPen(pen, (k, 0, 0, -k, x + (pos + dx) * k, BASELINE - dy * k))
        glyphs[order[gid]].draw(tp)
        pos += advance
    return pen.getCommands(), pos * k


def keyframes(name: str) -> str:
    steps = "".join(f"{num(t / LOOP * 100)}%{{opacity:{o};transform:translateY({y}px)}}" for t, o, y in KEYFRAMES[name])
    return f"@keyframes {name}{{{steps}}}"


def build(theme: str, font, data: bytes) -> str:
    t = THEMES[theme]
    prefix_adv = outline(font, data, PREFIX, 0)[1]
    space = outline(font, data, " ", 0)[1]
    widths = {w: outline(font, data, w, 0)[1] for w in WORDS}
    # The prefix stays where it is; the whole line is centred for the held, last frame.
    left = (W - (prefix_adv + space + widths[WORDS[-1]])) / 2
    word_x = left + prefix_adv + space
    longest = max(widths.values())
    if left < 56 or word_x + longest > W - 56:
        raise SystemExit(f"the longest line does not fit with a margin: from {left:.0f} to {word_x + longest:.0f} of {W}")
    prefix_d = outline(font, data, PREFIX, left)[0]
    words = []
    for cls, w in zip(("w1", "w2", "w3"), WORDS):
        words.append(f'<path class="w {cls}" fill="{INDIGO}" d="{outline(font, data, w, word_x)[0]}"/>')
    # The still is the last frame; the motion is added only where it is not unwanted.
    css = (
        f".w{{opacity:0}}.w3{{opacity:1}}"
        f"@media (prefers-reduced-motion:no-preference){{"
        + "".join(f".{c}{{animation:{c} {LOOP}s ease-in-out infinite both}}" for c in ("w1", "w2", "w3"))
        + "".join(keyframes(c) for c in ("w1", "w2", "w3"))
        + "}"
    )
    label = "Every value, cited. Every value, read twice. Every value, checked."
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">'
        f"<title>{label}</title>"
        f"<style>{css}</style>"
        f'<defs><radialGradient id="a" cx="14%" cy="0%" r="62%"><stop offset="0" stop-color="{t["glow_a"]}" stop-opacity="{t["glow_a_op"]}"/><stop offset="1" stop-color="{t["glow_a"]}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="b" cx="88%" cy="108%" r="56%"><stop offset="0" stop-color="{t["glow_b"]}" stop-opacity="{t["glow_b_op"]}"/><stop offset="1" stop-color="{t["glow_b"]}" stop-opacity="0"/></radialGradient></defs>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="{t["fill"]}" stroke="{t["line"]}"/>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="url(#a)"/>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="url(#b)"/>'
        f'<path fill="{t["ink"]}" d="{prefix_d}"/>'
        + "".join(words)
        + "</svg>\n"
    )


def build_still(theme: str, font, data: bytes) -> str:
    """The last frame alone, with no style and nothing that moves: what the README's <picture> gives to a reader whose
    system asks for reduced motion (an SVG used as an image may not be told that preference by every browser)."""
    svg = build(theme, font, data)
    svg = svg.replace(svg[svg.index("<style>") : svg.index("</style>") + 8], "")
    for cls in ("w1", "w2"):
        svg = svg.replace(svg[svg.index(f'<path class="w {cls}"') :].split("/>", 1)[0] + "/>", "")
    return svg.replace('class="w w3" ', "")


def main(out: Path = OUT) -> None:
    font, data = load()
    for theme in THEMES:
        for name, svg in ((f"banner-{theme}.svg", build(theme, font, data)), (f"banner-still-{theme}.svg", build_still(theme, font, data))):
            (out / name).write_text(svg, encoding="utf-8")
            print(f"{name}: {len(svg.encode()) / 1024:.1f} KB")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
