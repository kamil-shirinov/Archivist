"""Draw the README's three charts as SVG from the committed test report.

    uv run python docs/make_charts.py            # writes docs/img/chart-*.svg
    uv run python docs/make_charts.py --check    # fails if a committed chart differs from the data

Reads results/test_report.json (written by archivist.eval.test_report from the committed
runs) and the review app's list of condition names (ui/js/store.js), and nothing else; every number on a chart is read from it or is a plain rescaling of one
(a rate times 1,000). Output is byte-identical for the same input, so the committed SVGs cannot
drift from the data without --check saying so.

Each SVG carries its own card background, so it reads on GitHub's light and dark themes; the
colours switch with the viewer's colour scheme. Purple is a Meta model's work, teal is a result
for people, grey is plain code (only the diagrams use grey). Mark colours were checked with the
dataviz palette validator on both surfaces. An open-weights bar is the same colour with a
diagonal hatch, so the two arms differ by texture and by label, never by colour alone.
"""

from __future__ import annotations

import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "results" / "test_report.json"
STORE = ROOT / "ui" / "js" / "store.js"
OUT = ROOT / "docs" / "img"

FONT = '-apple-system, "Segoe UI", Helvetica, Arial, sans-serif'
STYLE = f"""
  text {{ font-family: {FONT}; }}
  .card {{ fill: #ffffff; stroke: #d0d7de; }}
  .t {{ fill: #1f2328; }}
  .m {{ fill: #59636e; }}
  .grid {{ stroke: #e3e7eb; stroke-width: 1; }}
  .axis {{ stroke: #8c959f; stroke-width: 1; }}
  .whisk {{ stroke: #1f2328; stroke-width: 1.5; fill: none; }}
  .purple {{ fill: #6d3fd0; }}
  .teal {{ fill: #00907f; }}
  .pline {{ stroke: #6d3fd0; }}
  .tline {{ stroke: #00907f; }}
  .pstroke {{ stroke: #6d3fd0; stroke-width: 1.5; }}
  .tstroke {{ stroke: #00907f; stroke-width: 1.5; }}
  .surface {{ fill: #ffffff; }}
  @media (prefers-color-scheme: dark) {{
    .card {{ fill: #0d1117; stroke: #30363d; }}
    .t {{ fill: #e6edf3; }}
    .m {{ fill: #9aa4b0; }}
    .grid {{ stroke: #21262d; }}
    .axis {{ stroke: #6e7681; }}
    .whisk {{ stroke: #e6edf3; }}
    .purple {{ fill: #9575ec; }}
    .teal {{ fill: #22a595; }}
    .pline {{ stroke: #9575ec; }}
    .tline {{ stroke: #22a595; }}
    .pstroke {{ stroke: #9575ec; }}
    .tstroke {{ stroke: #22a595; }}
    .surface {{ fill: #0d1117; }}
  }}
"""

# Textures on the card colour tell the arms apart without colour: solid, a diagonal hatch, dots.
DEFS = """<defs>
    <pattern id="hatch-purple" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="6" height="6" class="surface"/>
      <line x1="0" y1="0" x2="0" y2="6" class="pline" stroke-width="3"/>
    </pattern>
    <pattern id="hatch-teal" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="6" height="6" class="surface"/>
      <line x1="0" y1="0" x2="0" y2="6" class="tline" stroke-width="3"/>
    </pattern>
    <pattern id="dots-purple" width="6" height="6" patternUnits="userSpaceOnUse">
      <rect width="6" height="6" class="surface"/>
      <circle cx="3" cy="3" r="1.7" class="purple"/>
    </pattern>
    <pattern id="dots-teal" width="6" height="6" patternUnits="userSpaceOnUse">
      <rect width="6" height="6" class="surface"/>
      <circle cx="3" cy="3" r="1.7" class="teal"/>
    </pattern>
  </defs>"""

W = 720


def n(x: float) -> str:
    """A coordinate, trimmed so the file stays small and stable."""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


class Svg:
    def __init__(self, height: int, title: str, desc: str) -> None:
        self.h = height
        self.title = title
        self.desc = desc
        self.parts: list[str] = []

    def text(self, x, y, s, cls="t", size=13, anchor="start", weight="400") -> None:
        self.parts.append(
            f'<text x="{n(x)}" y="{n(y)}" class="{cls}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>'
        )

    def line(self, x1, y1, x2, y2, cls) -> None:
        self.parts.append(f'<line x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}" class="{cls}"/>')

    def bar(self, x, y, w, h, hue: str, style: str | bool = "solid") -> None:
        """A bar from the baseline: rounded at the data end only, as a path."""
        style = {False: "solid", True: "hatch"}.get(style, style)
        r = min(4, h / 2, w)
        if w <= 0:
            return
        d = (f"M{n(x)} {n(y)}H{n(x + w - r)}A{n(r)} {n(r)} 0 0 1 {n(x + w)} {n(y + r)}"
             f"V{n(y + h - r)}A{n(r)} {n(r)} 0 0 1 {n(x + w - r)} {n(y + h)}H{n(x)}Z")
        if style != "solid":
            self.parts.append(f'<path d="{d}" fill="url(#{style}-{hue})" class="{hue[0]}stroke"/>')
        else:
            self.parts.append(f'<path d="{d}" class="{hue}"/>')

    def whisker(self, x_lo, x_hi, y) -> None:
        """A 95% interval: a line with end caps, drawn over the bar."""
        self.parts.append(
            f'<path d="M{n(x_lo)} {n(y - 4)}V{n(y + 4)}M{n(x_lo)} {n(y)}H{n(x_hi)}'
            f'M{n(x_hi)} {n(y - 4)}V{n(y + 4)}" class="whisk"/>'
        )

    def render(self) -> str:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" width="{W}" '
            f'height="{self.h}" role="img" aria-labelledby="title desc">\n'
            f"  <title id=\"title\">{escape(self.title)}</title>\n"
            f"  <desc id=\"desc\">{escape(self.desc)}</desc>\n"
            f"  <style>{STYLE}</style>\n  {DEFS}\n"
            f'  <rect x="0.5" y="0.5" width="{W - 1}" height="{self.h - 1}" rx="8" class="card"/>\n'
        )
        return head + "\n".join("  " + p for p in self.parts) + "\n</svg>\n"


def axis(svg: Svg, x0: float, x1: float, y_top: float, y_bot: float, top: float, step: float,
         fmt, label_y: float) -> float:
    """Hairline grid and tick labels for a 0..top scale; returns the pixels per unit."""
    k = (x1 - x0) / top
    v = 0.0
    while v <= top + 1e-9:
        x = x0 + v * k
        svg.line(x, y_top, x, y_bot, "axis" if v == 0 else "grid")
        svg.text(x, label_y, fmt(v), "m", 11, "middle")
        v += step
    return k


def legend(svg: Svg, x: float, y: float, hue: str, items: list[tuple[str, str | bool]],
           vertical: bool = False) -> None:
    for label, style in items:
        svg.bar(x, y - 10, 22, 12, hue, style)
        svg.text(x + 30, y, label, "t", 12)
        if vertical:
            y += 20
        else:
            x += 30 + 7.2 * len(label) + 22


def load() -> dict:
    return json.loads(REPORT.read_text())


def conditions() -> list[str]:
    """The review app's names for the four damage levels, so the charts and the app cannot disagree."""
    m = re.search(r"export const COND = \[(.*?)\];", STORE.read_text())
    names = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    if len(names) != 4:
        raise SystemExit("ui/js/store.js no longer lists four condition names in COND")
    return names


def per_1000(rate: float) -> float:
    return rate * 1000


def pct(rate: float) -> float:
    return rate * 100


# ---------------------------------------------------------------- chart 1


def chart_mistakes(rep: dict) -> str:
    base = rep["configurations"]["baseline"]["stats"]
    arch = rep["configurations"]["A"]["stats"]
    rows = [
        ("Read once, no checks", "Muse Spark 1.3", base, "purple"),
        ("Archivist", "hosted, Muse Spark 1.3", arch, "teal"),
    ]
    vals = []
    for _, _, s, _ in rows:
        lo, hi = s["error_rate_accepted_ci95"]
        vals.append((per_1000(s["error_rate_accepted"]), per_1000(lo), per_1000(hi), s))
    top = 20 * (int(max(v[2] for v in vals) // 20) + 1)
    h = 262
    svg = Svg(h, "Wrong values that reach the database, per 1,000 accepted",
              "Bar chart on the pre-registered synthetic test. " + "; ".join(
                  f"{r[0]}: {v[0]:.1f} wrong per 1,000 accepted values, 95% interval {v[1]:.1f} to {v[2]:.1f}"
                  for r, v in zip(rows, vals)) + ".")
    svg.text(24, 34, "Wrong values that reach the database, per 1,000 accepted", "t", 16, weight="600")
    svg.text(24, 54, f"{rep['n_pages']} synthetic test pages, {rep['n_fields']:,} fields. "
             "Lines are 95% intervals (pages resampled 2,000 times).", "m", 12)
    x0, x1, y_top, y_bot = 200, 520, 76, 190
    k = axis(svg, x0, x1, y_top, y_bot, top, 20, lambda v: f"{v:g}", y_bot + 18)
    for i, ((label, sub, s, hue), (v, lo, hi, _)) in enumerate(zip(rows, vals)):
        yc = y_top + 30 + i * 52
        svg.text(x0 - 14, yc - 2, label, "t", 13, "end", "600")
        svg.text(x0 - 14, yc + 14, sub, "m", 11, "end")
        svg.bar(x0, yc - 10, v * k, 20, hue, False)
        svg.whisker(x0 + lo * k, x0 + hi * k, yc)
        svg.text(548, yc - 2, f"{v:.1f}", "t", 15, weight="600")
        svg.text(548, yc + 14, f"interval {lo:.1f} to {hi:.1f}", "m", 11)
        svg.text(548, yc + 28, f"{s['errors_missed']} of "
                 f"{s['n_accepted']:,} accepted", "m", 11)
    svg.text(24, h - 14, "Source: results/test_report.json (pre-registered in PREREGISTRATION.md). "
             "Rate of wrong values among accepted fields, times 1,000.", "m", 11)
    return svg.render()


# ---------------------------------------------------------------- chart 2


def chart_hosted_vs_open(rep: dict) -> str:
    arms = [
        ("Muse Spark 1.3", "Muse Spark 1.3 for both reads, on Meta's API (arm A)", "solid", rep["configurations"]["A"]["stats"]),
        ("Muse Spark Open", "Muse Spark Open for both reads, on Baseten (arm B)", "hatch", rep["configurations"]["B"]["stats"]),
        ("Mixed", "Mixed: Muse Spark 1.3 first, Muse Spark Open second (arm C)", "dots", rep["configurations"]["C"]["stats"]),
    ]
    panels = [
        ("Wrong values among those accepted, per 1,000 (lower is better)",
         "error_rate_accepted", "error_rate_accepted_ci95", per_1000, 10, 2, lambda v: f"{v:.1f}"),
        ("Share of the wrong values that were caught and sent to a person (higher is better)",
         "catch_rate", "catch_rate_ci95", pct, 100, 20, lambda v: f"{v:.1f}%"),
        ("Share of all values sent to a person (lower is better; target 20% or less)",
         "review_rate", "review_rate_ci95", pct, 40, 10, lambda v: f"{v:.1f}%"),
    ]
    h = 676
    rows = []
    for title, key, cikey, conv, top, step, fmt in panels:
        for name, _, _, s in arms:
            lo, hi = s[cikey]
            rows.append(f"{title.split(' (')[0]}, {name}: {fmt(conv(s[key]))} "
                        f"(95% interval {fmt(conv(lo))} to {fmt(conv(hi))})")
    svg = Svg(h, "The two models, and the two mixed, on the same synthetic test",
              "Three small bar charts comparing Muse Spark 1.3 for both reads (arm A), Muse Spark Open for both reads (arm B) "
              "and the mixed set-up (arm C). " + "; ".join(rows) + ".")
    svg.text(24, 34, "Muse Spark 1.3, Muse Spark Open, and the two mixed", "t", 16, weight="600")
    svg.text(24, 54, "Same 157 synthetic test pages. Lines are 95% intervals (pages resampled 2,000 times).", "m", 12)
    legend(svg, 24, 80, "purple", [(label, style) for _, label, style, _ in arms], vertical=True)
    x0, x1 = 150, 500
    for p, (title, key, cikey, conv, top, step, fmt) in enumerate(panels):
        y0 = 160 + p * 150
        svg.text(24, y0, title, "t", 12, weight="600")
        y_top, y_bot = y0 + 12, y0 + 108
        k = axis(svg, x0, x1, y_top, y_bot, top, step, lambda v: f"{v:g}", y_bot + 16)
        for i, (name, _, style, s) in enumerate(arms):
            v = conv(s[key])
            lo, hi = (conv(c) for c in s[cikey])
            yc = y_top + 20 + i * 30
            svg.text(x0 - 12, yc + 4, name, "t", 12, "end")
            svg.bar(x0, yc - 9, v * k, 18, "purple", style)
            svg.whisker(x0 + lo * k, x0 + hi * k, yc)
            svg.text(522, yc - 1, fmt(v), "t", 13, weight="600")
            svg.text(522, yc + 12, f"interval {fmt(lo)} to {fmt(hi)}", "m", 11)
    svg.text(24, h - 38, "Source: results/test_report.json, arms A, B and C. Wrong values caught = sent to review.", "m", 11)
    svg.text(24, h - 24, "Mixed did worse than either model alone, on wrong values accepted and on values sent to a person.", "m", 11)
    svg.text(24, h - 10, "Arm B also extracted with Muse Spark Open, so it compares whole set-ups, not the second read alone.", "m", 11)
    return svg.render()


# ---------------------------------------------------------------- chart 3


def chart_review_by_condition(rep: dict) -> str:
    a = rep["configurations"]["A"]["by_severity"]
    b = rep["configurations"]["B"]["by_severity"]
    names = {str(i): c for i, c in enumerate(conditions())}
    h = 398
    desc = "; ".join(
        f"{names[s]}: Muse Spark 1.3 {pct(a[s]['review_rate']):.1f}% ({a[s]['n_review']} of {a[s]['n_fields']:,}), "
        f"Muse Spark Open {pct(b[s]['review_rate']):.1f}% ({b[s]['n_review']} of {b[s]['n_fields']:,})"
        for s in names)
    svg = Svg(h, "Share of values sent to a person, by condition of the scan",
              "Grouped bar chart on the pre-registered synthetic test. " + desc + ".")
    svg.text(24, 34, "Share of values sent to a person, by condition of the scan", "t", 16, weight="600")
    svg.text(24, 54, "How worn the page was made, from clean to heavy wear. Same pages for both models.", "m", 12)
    legend(svg, 24, 80, "teal", [("Muse Spark 1.3 (arm A)", "solid"), ("Muse Spark Open (arm B)", "hatch")])
    x0, x1, y_top, y_bot = 190, 500, 100, 330
    k = axis(svg, x0, x1, y_top, y_bot, 50, 10, lambda v: f"{v:g}%", y_bot + 18)
    for g, s in enumerate(names):
        gy = y_top + 14 + g * 56
        svg.text(x0 - 14, gy + 24, names[s], "t", 12, "end", "600")
        for i, (arm, hatched) in enumerate(((a, False), (b, True))):
            r = arm[s]
            yb = gy + i * 22
            v = pct(r["review_rate"])
            svg.bar(x0, yb, v * k, 18, "teal", hatched)
            svg.text(x0 + v * k + 8, yb + 13, f"{v:.1f}%", "t", 12, weight="600")
            svg.text(560, yb + 13, f"{r['n_review']} of {r['n_fields']:,}", "m", 11)
    svg.text(24, h - 28, "Source: results/test_report.json, by_severity of arms A and B. Condition names are the review app's "
             "(ui/js/store.js).", "m", 11)
    svg.text(24, h - 12, "The report gives no interval for each condition.", "m", 11)
    return svg.render()


CHARTS = {
    "chart-mistakes.svg": chart_mistakes,
    "chart-hosted-vs-open.svg": chart_hosted_vs_open,
    "chart-review-by-condition.svg": chart_review_by_condition,
}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    rep = load()
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, make in CHARTS.items():
        svg = make(rep)
        path = OUT / name
        if check:
            if not path.exists() or path.read_text() != svg:
                stale.append(name)
        else:
            path.write_text(svg)
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("out of date with results/test_report.json: " + ", ".join(stale))
        return 1
    if check:
        print("charts match the report")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
