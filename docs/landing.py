"""The landing page at the published site's root (P51, redesigned in P52), written by docs/make_site.py.

    python docs/landing.py             # print the page to standard output (a look, nothing is written)

The site's front door says in a few seconds what Archivist does, why it matters, what was measured and where
to try it, and the app stays at /ui/. The page is static: no model call, no key, no request to another site.
Standard library only. Its order: a centred hero with the three headline numbers, the replay drawn on the 1939
page in a glass frame, one ledger of every pre-registered target (a switch between Meta's API and your own
hardware, each row opening its evidence), the seven steps as a pipeline, the real scans (a range chart, the
diagnosis), the commits as a timeline, the honest limits, and how to try it. Expandable panels only add depth:
what a fair reader needs, a missed target above all, is always on the page.

Every number on it is read here, at build time, from a committed file, and written through fact(), which
marks it (data-fact="<key>") so that tests/test_landing.py can recompute each one from its file and fail if
the page differs, or if a digit sits anywhere on the page that is not a marked fact. Nothing is typed by hand:

  * the headline numbers, the ledger's rows (each with its interval, counts and 1,000-dot grid), the review
    rate by page condition and the test's size, date and review share: results/test_report.json and the run
    records in results/runs/ (the date), the registration commit from git;
  * the real scans: the official scores (results/real_test/held_out/score/score.json and
    results/real_openw/held_out/score/score.json), what the diagnosis found (a table in
    results/real_test/held_out/diagnosis.md, parsed), and the corrected key's scores only if their files exist;
    held-out results appear as aggregate numbers alone (overall, by stratum, by family), never a page, a cell,
    a value or an image of one;
  * the pre-registrations' commits, their messages, tags and dates: git, or docs/landing_proof.json where there
    is no git history (the Docker image); a test proves the two agree;
  * the replay: one recorded decision of the development run on the Treasury Bulletin (a public-domain page),
    its steps, models, rule, loop and counts from that run's bundle, and a fixed choice of value that the
    code checks still qualifies (accepted, the blind read agrees, a rule held, a clean pen loop);
  * the Docker commands: README.md; the Meta models: the model ids in config/.

A claim that has no file behind it is left out (CLAUDE.md, P51). Nothing moves except by opacity and transform
(tests/test_landing.py reads the stylesheet to check), and nothing moves at all for a visitor who asked for less.
"""

from __future__ import annotations

import html
import json
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPO = "https://github.com/kamil-shirinov/Archivist"
HOME = "replay"  # the view of the app that Watch it work opens
ASSETS = (
    "docs/landing/landing.css",
    "docs/landing/landing.js",
    "docs/landing/fonts/Newsreader-Latin.woff2",
    "docs/landing/fonts/Geist-Latin.woff2",
    "docs/landing/fonts/GeistMono-Latin.woff2",
    "docs/landing/fonts/NEWSREADER-OFL.txt",
    "assets/brand/logo-light.svg",  # the brand mark, in both themes: only the wordmark's colour follows the theme
)
PROOF_FILE = "docs/landing_proof.json"

TEST_REPORT = "results/test_report.json"
REAL_SCORE = "results/real_test/held_out/score/score.json"
OPEN_SCORE = "results/real_openw/held_out/score/score.json"
DIAGNOSIS = "results/real_test/held_out/diagnosis.md"
SWEEP = "results/real_test/held_out/sweep.json"
PLAN_SYNTHETIC = "PREREGISTRATION.md"
PLAN_REAL = "PREREGISTRATION_REAL.md"
PLAN_OPENW = "PREREGISTRATION_OPENW.md"
STORE = "ui/js/store.js"  # the review app's names for the four condition levels (COND)
CORRECTED = {
    "version_1": "results/real_test/held_out/score_corrected/score.json",
    "open_weights": "results/real_openw/held_out/score_corrected/score.json",
}
BUNDLES = "data/bundles"
REPLAY_RUN = "treasury-development"
# The one recorded decision the replay plays: a figure on a December 1939 Treasury Bulletin page, whose pen loop
# was looked at on the page and clears the printed figures around it. qualifying() checks it still qualifies.
REPLAY_FIELD = "T.receipts_and_expenditures_under_railroad:1939-12_p025:13:to_unemployment"
CROP = (680, 270)  # the band of the page the specimen shows, in the scan's own pixels, centred on the value

MODEL_CONFIGS = ("config/archive_glimmer.toml", "config/models.toml", "config/models_open.toml")
MODEL_NAMES = (  # a model id's mark and the name it goes by, in the order of the pipeline
    ("muse-glimmer", "Muse Glimmer"),
    ("muse-spark-1.3", "Muse Spark 1.3"),
    ("sam-3.1", "SAM 3.1"),
    ("muse-spark-open", "Muse Spark Open"),
)
PLAN_TAGS = ("prereg-real-treasury", "run-real-treasury", "prereg-real-openw", "run-real-openw")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LONG_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


class Refused(Exception):
    """Something that must not be published, or a file the build needs that is not there or not as expected."""


# --- reading ---------------------------------------------------------------------------------------


def _text(root: Path, path: str) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        raise Refused(f"the landing page needs {path}: {error.strerror}") from None


def _json(root: Path, path: str) -> dict:
    try:
        return json.loads(_text(root, path))
    except ValueError as error:
        raise Refused(f"{path} is not JSON: {error}") from None


def _utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def pct(value: float, places: int = 2) -> str:
    return f"{value * 100:.{places}f}%"


def span(interval: list[float], places: int = 1) -> str:
    return f"{pct(interval[0], places)}–{pct(interval[1], places)}"


def num(value: int) -> str:
    return f"{value:,}"


def day(stamp: str) -> str:
    t = _utc(stamp)
    return f"{t.day} {MONTHS[t.month - 1]} {t.year}"


def clock(stamp: str) -> str:
    t = _utc(stamp)
    return f"{t.day} {MONTHS[t.month - 1]} {t.year}, {t:%H:%M} UTC"


def apart(first: str, second: str) -> str:
    """How long before `second` was `first`, in words."""
    minutes = round((_utc(second) - _utc(first)).total_seconds() / 60)
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}" + (f" {rest} minutes" if rest else "")
    days = round(minutes / 1440)
    return f"{days} day{'s' if days != 1 else ''}"


# --- git, and its snapshot -----------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _commit(root: Path, *args: str) -> dict | None:
    """A commit's short hash, committer date and subject line (the timeline shows the subject on hover)."""
    line = _git(root, "log", "-1", "--format=%H%x1f%cI%x1f%s", *args)
    if not line or line.count("\x1f") != 2:
        return None
    sha, stamp, message = line.split("\x1f", 2)
    return {"sha": sha[:7], "date": _utc(stamp).strftime("%Y-%m-%dT%H:%M:%SZ"), "message": message}


def git_facts(root: Path = ROOT) -> dict | None:
    """The commits and tags the page cites, from git; None where there is no full history to read them from."""
    if _git(root, "rev-parse", "--is-shallow-repository") != "false":
        return None
    added = _git(root, "log", "--diff-filter=A", "--format=%H", "--", PLAN_SYNTHETIC)
    roots = (_git(root, "rev-list", "--max-parents=0", "HEAD") or "").split()
    if not added or len(roots) != 1:
        return None
    facts: dict = {
        "first_commit": _commit(root, roots[0]),
        "registration": _commit(root, added.splitlines()[-1]),
        "tags": {tag: _commit(root, f"refs/tags/{tag}^{{commit}}") for tag in PLAN_TAGS},
    }
    if facts["registration"] is None:
        return None
    if facts["first_commit"] is None or None in facts["tags"].values():
        return None
    return facts


def proof(root: Path = ROOT) -> dict:
    """git's facts where the build has the history (the Pages checkout does), else the committed snapshot
    (the Docker image has no git); tests/test_landing.py proves the two are the same."""
    facts = git_facts(root)
    if facts is not None:
        return facts
    if not (root / PROOF_FILE).is_file():
        raise Refused(f"no git history to read the pre-registration dates from, and no {PROOF_FILE}")
    print(f"landing: no git history here; the pre-registration dates come from {PROOF_FILE}", file=sys.stderr)
    return _json(root, PROOF_FILE)


# --- what the page says -------------------------------------------------------------------------------


def models(root: Path) -> dict[str, str]:
    """The Meta models the repository's configs name, by the name each goes by, in pipeline order."""
    ids: list[str] = []
    for path in MODEL_CONFIGS:
        ids += re.findall(r'model_id\s*=\s*"([^"]+)"', _text(root, path))
    found: dict[str, str] = {}
    for mark, name in MODEL_NAMES:
        if any(mark in i.lower() for i in ids):
            found[mark] = name
    for i in ids:
        if not any(mark in i.lower() for mark, _ in MODEL_NAMES):
            raise Refused(f"the config names a model with no name on the page: {i}")
    return found


def synthetic(root: Path) -> dict:
    """The pre-registered synthetic test: the three numbers, and the line under them."""
    report = _json(root, TEST_REPORT)
    cfg = report["configurations"]
    a, base, b = cfg["A"]["stats"], cfg["baseline"]["stats"], cfg["B"]["stats"]
    h3, h5 = report["hypotheses"]["H3"], report["hypotheses"]["H5"]
    runs = {cfg[k]["runs"][part]["run"] for k in cfg for part in cfg[k]["runs"]}
    stamps = [_json(root, f"results/runs/{name}/run.json") for name in sorted(runs)]
    start, end = min(s["started_at"] for s in stamps), max(s["finished_at"] for s in stamps)
    return {
        "pages": report["n_pages"],
        "fields": report["n_fields"],
        "started": start,
        "dates": day(start) if day(start) == day(end) else f"{day(start)} to {day(end)}",
        "a": a,
        "base": base,
        "b": b,
        "b_alone": cfg["B"]["extraction_alone"],
        "cost": {"a": cfg["A"]["cost"]["per_page_usd"], "b": cfg["B"]["cost"]["per_page_usd"]},
        # A single read's own cost a page, where the report records one: the baseline is the hosted single read (it
        # verifies nothing, so its cost is the read's alone). The report records no open-weights single read on its
        # own (arm B's reads are priced with the checks that follow them), so that side has none: a dash.
        "single_cost": {"hosted": cfg["baseline"]["cost"]["per_page_usd"], "open": None},
        "h1": report["hypotheses"]["H1"],
        "h2": report["hypotheses"]["H2"],
        "h3": h3,
        "h4": report["hypotheses"]["H4"],
        "h5": h5,
        "cfg": cfg,
        "resamples": report["bootstrap"]["resamples"],
        "conditions": conditions(root),
    }


def conditions(root: Path) -> list[str]:
    """The review app's names for the four damage levels, so the page and the app cannot disagree (as make_charts does)."""
    found = re.search(r"export const COND = \[(.*?)\];", _text(root, STORE))
    names = re.findall(r'"([^"]+)"', found.group(1)) if found else []
    if len(names) != 4:
        raise Refused(f"{STORE} no longer lists four condition names in COND")
    return names


def interval_level(root: Path) -> tuple[str, str]:
    """The level of the intervals and the number of resamples, as the real-scan plan states them
    ("95% percentile intervals from 2,000 bootstrap resamples by page")."""
    found = re.search(r"(\d+)% percentile intervals from ([\d,]+) bootstrap resamples", _text(root, PLAN_REAL))
    if not found:
        raise Refused(f"{PLAN_REAL} no longer states the level of its intervals")
    return f"{found.group(1)}%", found.group(2)


def real_scores(root: Path) -> dict:
    v1, ow = _json(root, REAL_SCORE), _json(root, OPEN_SCORE)
    level, resamples = interval_level(root)
    return {
        "v1": v1["labels"],
        "ow": ow["open_weights"],
        "o1": ow["o1"],
        "every": v1["every_cell"],
        "families": v1["weights"]["families"],
        "sweep": v1["sweep"],
        "sam": v1["sam"],
        "stalled": bool(ow["stalled"]) or bool(ow["asked_again"]["cells"]),
        "pages_checked": v1["sam"]["pages"],
        "changed": len(v1["both_ways_pages"]),
        "started": _json(root, SWEEP)["started_at"],
        "ow_started": ow["run"]["started_at"],
        "level": level,
        "resamples": resamples,
    }


def family_titles(root: Path) -> dict[str, str]:
    """Each approved Treasury table family's printed title, from the development bundle's document types."""
    index = _json(root, f"{BUNDLES}/index.json")
    entry = next((r for r in index["runs"] if r["run_id"] == REPLAY_RUN), None)
    if entry is None:
        raise Refused(f"{REPLAY_RUN} is not in the bundle index")
    return {t["name"]: t["title"] for t in _json(root, f"{BUNDLES}/{entry['path']}")["doc_types"]}


DIAGNOSIS_TABLES = {
    ("v1", "single"): "Version 1, wrong values in the single read",
    ("v1", "accepted"): "Version 1, wrong values Archivist accepted",
    ("ow", "single"): "Open weights, wrong values in the single read",
    ("ow", "accepted"): "Open weights, wrong values Archivist accepted",
}
DIAGNOSIS_COLUMNS = ["Layout", "Group", "Wrong", "Layout drift", "Row not on page", "Format only", "Misalignment", "Digit misread", "Other"]


def diagnosis(root: Path) -> dict:
    """The causes of the wrong values, from the tables of the diagnosis: {(configuration, who, layout): counts}."""
    text = _text(root, DIAGNOSIS)
    found: dict = {}
    for key, heading in DIAGNOSIS_TABLES.items():
        start = text.find(f"#### {heading}")
        if start < 0:
            raise Refused(f"{DIAGNOSIS} has no table headed {heading!r}")
        block = text[start:].split("\n####", 1)[0].split("\n## ", 1)[0]
        rows = [[c.strip().replace("**", "") for c in line.strip().strip("|").split("|")] for line in block.splitlines() if line.startswith("|")]
        if not rows or rows[0] != DIAGNOSIS_COLUMNS:
            raise Refused(f"the table {heading!r} in {DIAGNOSIS} no longer has the columns this page reads")
        for row in rows[2:]:
            if row[1] == "All":
                counts = [int(c) for c in row[2:]]
                wrong, causes = counts[0], counts[1:]
                if wrong != sum(causes):
                    raise Refused(f"the causes in {heading!r} ({row[0]}) do not add up to its wrong values")
                drift, missing, fmt, mis, digit, other = causes
                found[(*key, row[0])] = {
                    "wrong": wrong,
                    "drift": drift,
                    "format": fmt,
                    "reading": missing + mis + digit + other,
                    "missing": missing,
                    "misaligned": mis,
                    "digit": digit,
                    "other": other,
                }
        for layout in ("kept", "left out"):
            if (*key, layout) not in found:
                raise Refused(f"the table {heading!r} in {DIAGNOSIS} has no {layout!r} row for All")
    return found


def corrected(root: Path) -> dict:
    """The corrected key's scores, for each configuration whose result file exists (the dash check has run)."""
    found = {}
    for name, path in CORRECTED.items():
        if (root / path).is_file():
            found[name] = _json(root, path)
    return found


def docker_commands(root: Path) -> list[str]:
    """The Docker lines of the README's "Run it yourself"."""
    readme = _text(root, "README.md")
    section = readme.split("## Run it yourself", 1)
    block = re.search(r"```bash\n(.*?)```", section[1], re.S) if len(section) == 2 else None
    lines = [ln for ln in (block.group(1).splitlines() if block else []) if ln.startswith("docker ")]
    if not lines:
        raise Refused("README.md has no Docker commands under Run it yourself")
    return lines


# --- the replay ----------------------------------------------------------------------------------------


def _pen_points(d: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in re.findall(r"[ML]\s*(-?[\d.]+)[ ,](-?[\d.]+)", d)]


def qualifying(field: dict, rules: list[dict], page: dict) -> list[str]:
    """What is wrong with this value as the replay's example, in words: nothing, when it qualifies."""
    problems = []
    if field["status"] != "accepted":
        problems.append("it was not accepted")
    if field["reread_status"] != "agrees" or field["reread"] != field["value"]:
        problems.append("the blind read does not agree")
    if not rules or not all(r["ok"] for r in rules):
        problems.append("no rule covers it, or one failed")
    if field["occluders"]:
        problems.append("ink covers it")
    loop = field.get("loop")
    if not loop or loop["kind"] != "loop":
        problems.append("its mark is not a pen loop")
    else:
        ink = loop["ink"]
        points = _pen_points(loop["d"])
        if not points or any(ink[0] <= x <= ink[2] and ink[1] <= y <= ink[3] for x, y in points):
            problems.append("its loop runs through its own ink")
    if page["failure"]:
        problems.append("the page failed")
    return problems


def replay(root: Path) -> dict:
    """The recorded decision, from the development run's bundle."""
    index = _json(root, f"{BUNDLES}/index.json")
    entry = next((r for r in index["runs"] if r["run_id"] == REPLAY_RUN), None)
    if entry is None or entry.get("stage") != "development" or entry.get("source") != "public-domain scans":
        raise Refused(f"{REPLAY_RUN} is not a development run on public-domain scans, so it is not shown")
    folder = f"{BUNDLES}/{entry['path']}".rsplit("/", 1)[0]
    bundle = _json(root, f"{BUNDLES}/{entry['path']}")
    fields = {f["field_id"]: f for f in bundle["fields"]}
    field = fields.get(REPLAY_FIELD)
    if field is None:
        raise Refused(f"{REPLAY_FIELD} is not in the {REPLAY_RUN} bundle")
    page = next(p for p in bundle["pages"] if p["page_id"] == field["page_id"])
    rules = [r for r in bundle["rule_results"] if REPLAY_FIELD in r["fields"]]
    problems = qualifying(field, rules, page)
    if problems:
        raise Refused(f"the replay's value no longer qualifies: {'; '.join(problems)}")
    steps = {s["key"]: s for s in page["steps"]}
    rule = rules[0]
    try:
        parts = [Decimal(fields[f]["value"]) for f in rule["fields"]]
    except ArithmeticError:
        raise Refused("a figure of the replay's rule is not a number") from None
    if parts[0] != sum(parts[1:], Decimal(0)):
        raise Refused("the rule's printed total is not the sum of its parts")
    url = (root / folder / page["image"]["url"]).resolve().relative_to(root.resolve()).as_posix()
    doc_type = next(t for t in bundle["doc_types"] if t["name"] == page["doc_type"])
    column = next(c["printed"] for c in doc_type["columns"] if c["key"] == field["name"])
    period = fields[f"T.{field['doc_type']}:{field['page_id']}:{field['row']}:period"]["value"].strip(" .")
    year, month = page["issue"].split("-")
    return {
        "field": field,
        "page": page,
        "rule": rule,
        "steps": steps,
        "sum": parts,
        "image": url,
        "title": doc_type["title"],
        "column": column,
        "period": period,
        "issue": f"{LONG_MONTHS[int(month) - 1]} {year}",
        "year": year,
        "rights": bundle["run"]["publication"]["rights"],
        "models": list(dict.fromkeys(s["model"] for s in page["steps"] if s["model"])),
    }


def plans(git: dict, syn: dict, real: dict) -> list[dict]:
    """Each pre-registration: when its plan was registered, when its code was frozen, when its run began.
    An event is (what, commit hash or None, when, the commit's message or None)."""
    tags = git["tags"]

    def at(tag: str) -> tuple[str, str, str]:
        return tags[tag]["sha"], tags[tag]["date"], tags[tag]["message"]

    reg = git["registration"]
    return [
        {
            "file": PLAN_SYNTHETIC,
            "name": "synthetic",
            "events": [("Plan registered", reg["sha"], reg["date"], reg["message"]), ("First run began", None, syn["started"], None)],
            "gap": (reg["date"], syn["started"]),
        },
        {
            "file": PLAN_REAL,
            "name": "real",
            "events": [
                ("Plan registered", *at("prereg-real-treasury")),
                ("Runner frozen", *at("run-real-treasury")),
                ("Held-out sweep began", None, real["started"], None),
            ],
            "gap": (at("prereg-real-treasury")[1], real["started"]),
        },
        {
            "file": PLAN_OPENW,
            "name": "openw",
            "events": [
                ("Plan registered", *at("prereg-real-openw")),
                ("Runner frozen", *at("run-real-openw")),
                ("Held-out run began", None, real["ow_started"], None),
            ],
            "gap": (at("prereg-real-openw")[1], real["ow_started"]),
        },
    ]


# --- writing HTML --------------------------------------------------------------------------------------

DOTS = 1000  # the size of every dot grid: a rate drawn as that many dots, whole dots, rounded
DOT_COLS, DOT_ROWS = 40, 25
AXIS_STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def fact(key: str, text: object) -> str:
    """A fact read from a file, marked so that a test can find it and compare it with its source."""
    return f'<span data-fact="{esc(key)}">{esc(text)}</span>'


def ref(name: str) -> str:
    """A name the page refers to that has a digit in it (a hypothesis, a decision), not a number of its own."""
    return f'<span data-ok="ref">{esc(name)}</span>'


def tick(text: str) -> str:
    """A label on a chart's axis: a position on its scale, not a result."""
    return f'<span class="tk" data-ok="axis">{esc(text)}</span>'


def step_no(n: int) -> str:
    return f'<span class="n" data-ok="step">{n}</span>'


def link(href: str, text: str, extra: str = ' rel="noopener"') -> str:
    return f'<a href="{esc(href)}"{extra}>{text}</a>'


def blob(path: str) -> str:
    return f"{REPO}/blob/main/{path}"


def commit_url(sha: str) -> str:
    return f"{REPO}/commit/{sha}"


def threshold(value: float) -> str:
    """A target as the report states it: 0.2 is 20%."""
    return f"{value * 100:g}%"


def tip(inner: str) -> str:
    """What a mark says when it is hovered, tapped or focused. It is on the page as text for everyone; the script
    shows it beside the mark, and it is how a screen reader reaches what the mark means."""
    return f'<span class="tip">{inner}</span>'


def dash(why: str) -> str:
    """An empty cell: a dash that says why when it is hovered or tapped. The page's own tooltip does that (never the
    browser's title tooltip), and the same words are on the page as text for a screen reader."""
    return f'<span class="mut dash">—{tip(esc(why))}</span>'


def nice_axis(highest: float) -> float:
    """The first round number above what a chart has to show."""
    return next((step for step in AXIS_STEPS if step >= highest * 1.04), 1.0)


def axis(top: float) -> str:
    """Three labels, 0, half and the top of the scale, laid out as the chart's own columns."""
    return f'<div class="ax" aria-hidden="true">{tick("0%")}{tick(f"{top / 2 * 100:g}%")}{tick(f"{top * 100:g}%")}</div>'


def where(value: float, top: float) -> str:
    """A position on a scale, as a share of its width."""
    return f"{min(max(value / top, 0), 1) * 100:.2f}%"


# --- a dot grid -----------------------------------------------------------------------------------------


def dot_path(indexes: list[int]) -> str:
    """One path of small circles, at the positions of a 40 by 25 grid, for these dot numbers."""
    parts = []
    for i in indexes:
        cx, cy = 3.5 + (i % DOT_COLS) * 7, 3.5 + (i // DOT_COLS) * 7
        parts.append(f"M{cx - 2.2:g} {cy:g}a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0-4.4 0")
    return "".join(parts)


def dot_grid(seed: str, rate: float, kind: str, label: str) -> tuple[str, int]:
    """A rate as 1,000 dots, a whole number of them drawn in the colour of what is counted and the rest as plain
    dots, scattered the same way every build. Returns the grid and how many dots are marked (rounded)."""
    marked = round(rate * DOTS)
    chosen = sorted(random.Random(seed).sample(range(DOTS), marked))
    if marked > DOTS // 2:  # draw the smaller set: the complement, over a base of marked dots
        rest = sorted(set(range(DOTS)) - set(chosen))
        drawn = f'<rect width="280" height="175" fill="url(#dot-{kind})"/><path class="plain" d="{dot_path(rest)}"/>'
    else:
        drawn = f'<rect width="280" height="175" fill="url(#dot-plain)"/><path class="{kind}" d="{dot_path(chosen)}"/>'
    svg = f'<svg class="dots" viewBox="0 0 280 175" role="img" aria-label="{esc(label)}" data-dots="{DOTS}" data-marked="{marked}" preserveAspectRatio="xMidYMid meet">{drawn}</svg>'
    return svg, marked


DOT_DEFS = (
    '<svg class="defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>'
    + "".join(
        f'<pattern id="dot-{kind}" width="7" height="7" patternUnits="userSpaceOnUse"><circle class="{kind}" cx="3.5" cy="3.5" r="2.2"/></pattern>'
        for kind in ("plain", "wrong", "caught", "sent", "once")
    )
    + "</defs></svg>"
)


# --- an interval drawn as a bar ----------------------------------------------------------------------------


def mark(kind: str, value: float, interval: list[float] | None, top: float, said: str) -> str:
    """One estimate on a scale: its interval as a bar, the estimate as a dot, and what it says as a tip."""
    bar = ""
    if interval is not None:
        left, right = where(interval[0], top), where(interval[1], top)
        bar = f'<i class="bar" style="--l:{left};--r:{right}"></i>'
    return f'<span class="mk {kind}" tabindex="0" style="--v:{where(value, top)}">{bar}<i class="pt"></i>{tip(said)}</span>'


def target_line(value: float, top: float, said: str) -> str:
    return f'<i class="tgt" style="--t:{where(value, top)}"><span class="tgl">{said}</span></i>'


def overlap_note(one: list[float], other: list[float]) -> str:
    """Whether two intervals overlap, in words (the test for a pre-registered 'intervals apart')."""
    return "The intervals overlap." if max(one[0], other[0]) <= min(one[1], other[1]) else "The intervals do not overlap."


# --- the ledger: every pre-registered target as a row -----------------------------------------------------

MODES = ("hosted", "open")
MODE_NAME = {"hosted": "Meta’s API", "open": "Your own hardware"}


def quantity(key: str, value: float, interval: list[float] | None = None, found: int | None = None, of: int | None = None, places: int = 2) -> dict:
    """A rate with its interval and the counts behind it, and the keys its facts are marked with."""
    return {"key": key, "value": value, "ci": interval, "found": found, "of": of, "places": places}


def ledger_rows(s: dict, r: dict) -> list[dict]:
    """The ledger: one row for each pre-registered target. A row has two sides, as the page's switch has: what
    Meta's API gave (the headline arm) and what your own hardware gave (Muse Spark Open). Open weights was
    given only two targets; on its other rows the numbers stand without one."""
    cfg = s["cfg"]
    base, b = cfg["baseline"]["stats"], cfg["B"]["stats"]
    alone = cfg["B"]["extraction_alone"]
    h1, h2, h3, h4, h5 = (s[k]["numbers"] for k in ("h1", "h2", "h3", "h4", "h5"))
    met = {k: s[k]["met"] for k in ("h1", "h2", "h3", "h4", "h5")}
    v1, o1 = r["v1"]["kept/as_run"], r["o1"]
    ow = r["ow"]["kept/as_run"]

    def q(row: str, mode: str, who: str, value: float, ci, found=None, of=None, key=None, places=2) -> dict:
        return quantity(key or f"ledger.{row}.{mode}.{who}", value, ci, found, of, places)

    rows = [
        {
            "id": "h1", "label": "Wrong among accepted, synthetic test", "note": "", "kind": "wrong", "unit": "accepted values", "verb": "were wrong",
            "source": TEST_REPORT, "plan": PLAN_SYNTHETIC,
            "hosted": {
                "arch": q("h1", "hosted", "arch", h1["headline"]["rate"], h1["headline"]["ci95"], h1["headline"]["wrong"], h1["headline"]["accepted"], key="hw.wrong.hosted"),
                "single": q("h1", "hosted", "single", h1["baseline"]["rate"], h1["baseline"]["ci95"], h1["baseline"]["wrong"], h1["baseline"]["accepted"]),
                "target": {"words": "Lower than the single read, intervals apart"}, "met": met["h1"], "tags": ("met", "missed"), "ref": "H1",
            },
            "open": {
                "arch": q("h1", "open", "arch", h4["rate"], h4["ci95"], h4["wrong"], h4["accepted"], key="hw.wrong.open"),
                "single": q("h1", "open", "single", alone["error_rate_accepted"], alone["error_rate_accepted_ci95"], alone["errors_missed"], alone["n_accepted"]),
                "target": {"lead": "Under", "value": h4["threshold"]}, "met": met["h4"], "tags": ("met", "missed"), "ref": "H4",
            },
        },
        {
            "id": "h2", "label": "Wrong values caught", "note": "", "kind": "caught", "unit": "wrong values", "verb": "were sent to a person",
            "source": TEST_REPORT, "plan": PLAN_SYNTHETIC,
            "hosted": {
                "arch": q("h2", "hosted", "arch", h2["rate"], h2["ci95"], h2["caught"], h2["wrong"], key="hw.caught.hosted"),
                "single": q("h2", "hosted", "single", base["catch_rate"], base["catch_rate_ci95"], base["errors_caught"], base["n_wrong"]),
                "target": {"lead": "At least", "value": h2["threshold"]}, "met": met["h2"], "tags": ("met", "missed"), "ref": "H2",
            },
            "open": {
                "arch": q("h2", "open", "arch", b["catch_rate"], b["catch_rate_ci95"], b["errors_caught"], b["n_wrong"], key="hw.caught.open"),
                "single": None, "target": None, "met": None, "tags": ("met", "missed"), "ref": None,
            },
        },
        {
            "id": "h3", "label": "Sent to a person", "note": "", "kind": "sent", "unit": "values", "verb": "were sent to a person",
            "source": TEST_REPORT, "plan": PLAN_SYNTHETIC,
            "hosted": {
                "arch": q("h3", "hosted", "arch", h3["rate"], h3["ci95"], h3["review"], h3["fields"], key="hw.review.hosted"),
                "single": q("h3", "hosted", "single", base["review_rate"], base["review_rate_ci95"], base["n_review"], base["n_fields"]),
                "target": {"lead": "At most", "value": h3["threshold"]}, "met": met["h3"], "tags": ("met", "missed"), "ref": "H3",
            },
            "open": {
                "arch": q("h3", "open", "arch", b["review_rate"], b["review_rate_ci95"], b["n_review"], b["n_fields"], key="hw.review.open"),
                "single": None, "target": None, "met": None, "tags": ("met", "missed"), "ref": None,
            },
        },
        {
            "id": "h5", "label": "Planted source errors flagged", "note": "", "kind": "caught", "unit": "planted source errors", "verb": "were flagged",
            "source": TEST_REPORT, "plan": PLAN_SYNTHETIC,
            "hosted": {
                "arch": q("h5", "hosted", "arch", h5["rate"], None, h5["found"], h5["planted"], key="hw.flagged.hosted"),
                "single": q("h5", "hosted", "single", base["source_error_recall"], None, base["source_errors_found"], base["n_source_errors"]),
                "target": {"lead": "At least", "value": h5["threshold"]}, "met": met["h5"], "tags": ("met", "missed"), "ref": "H5",
            },
            "open": {
                "arch": q("h5", "open", "arch", b["source_error_recall"], None, b["source_errors_found"], b["n_source_errors"], key="hw.flagged.open"),
                "single": None, "target": None, "met": None, "tags": ("met", "missed"), "ref": None,
            },
        },
        {
            "id": "r1", "label": "Wrong among accepted, real scans", "note": "every labelled cell", "kind": "wrong", "unit": "accepted cells", "verb": "were wrong",
            "source": REAL_SCORE, "plan": PLAN_REAL, "source_open": OPEN_SCORE, "plan_open": PLAN_OPENW,
            "hosted": {
                "arch": q("r1", "hosted", "arch", v1["overall"]["archivist_error"]["value"], v1["overall"]["archivist_error"]["ci"], key="hw.real.hosted", places=1),
                "single": q("r1", "hosted", "single", v1["overall"]["single_read_error"]["value"], v1["overall"]["single_read_error"]["ci"], places=1),
                "target": {"words": "Lower than the single read, intervals apart"}, "met": v1["r1"]["met"], "tags": ("met", "not met"), "ref": "R1", "cells": v1,
            },
            "open": {
                "arch": q("r1", "open", "arch", ow["overall"]["archivist_error"]["value"], ow["overall"]["archivist_error"]["ci"], key="hw.real.open", places=1),
                "single": q("r1", "open", "single", ow["overall"]["single_read_error"]["value"], ow["overall"]["single_read_error"]["ci"], places=1),
                "target": {"lead": "Under", "value": o1["threshold"], "key": "hw.target"}, "met": o1["met"], "tags": ("target met", "target not met"), "ref": "O1", "cells": ow,
            },
        },
    ]
    return rows


def shown(q: dict) -> str:
    return pct(q["value"], q["places"])


def counted(q: dict) -> str | None:
    return None if q["found"] is None else f"{num(q['found'])} of {num(q['of'])}"


def swap(hosted: str, open_: str) -> str:
    """One cell with both sides in it, one shown at a time: the switch chooses (a cell's two sides stack in one
    place, so the column is as wide as the wider)."""
    return f'<span class="swap"><span class="v h">{hosted}</span><span class="v o" aria-hidden="true">{open_}</span></span>'


def value_cell(q: dict | None, level: str) -> str:
    """A rate and its interval, as one cell shows them; a dash where the file has none."""
    if q is None:
        return dash("Not reported for this set-up")
    parts = f'<span class="big">{fact(q["key"], shown(q))}</span>'
    if q["ci"] is not None:
        parts += f'<small class="ci">{fact(ci_key(q), span(q["ci"], q["places"]))}</small>'
    return parts


def ci_key(q: dict) -> str:
    """The fact key of a rate's interval: its own key with .ci; the headline keys (hw.*) are shortened to their row."""
    return q["key"] + ".ci"


def target_cell(t: dict | None, key: str) -> str:
    if t is None:
        return '<span class="mut">—</span>'
    if "words" in t:
        return esc(t["words"])
    return f'{esc(t["lead"])} {fact(t.get("key", key), threshold(t["value"]))}'


def result_cell(m: dict) -> str:
    if m["met"] is None:
        return '<span class="tag none">no target</span>'
    yes, no = m["tags"]
    return f'<span class="tag yes">{yes}</span>' if m["met"] else f'<span class="tag no">{no}</span>'


def interval_figure(row: dict, mode: str, level: str) -> str:
    """Each estimate's interval as a bar on one scale, the target as a line across it, and in words whether the two
    intervals overlap."""
    m = row[mode]
    items = [("arch", "Archivist", m["arch"]), ("single", "Single read", m["single"])]
    items = [i for i in items if i[2] is not None]
    reach = [q["ci"][1] if q["ci"] else q["value"] for _, _, q in items]
    if m["target"] and "value" in m["target"]:
        reach.append(m["target"]["value"])
    top = nice_axis(max(reach))
    tracks = ""
    for who, label, q in items:
        said = f'{label}: {fact(q["key"], shown(q))}'
        if q["ci"] is not None:
            said += f', {fact("ci.level", level)} interval {fact(ci_key(q), span(q["ci"], q["places"]))}'
        line = ""
        if m["target"] and "value" in m["target"]:
            line = target_line(m["target"]["value"], top, f'Target: {esc(m["target"]["lead"].lower())} {fact(m["target"].get("key", f"ledger.{row["id"]}.{mode}.target"), threshold(m["target"]["value"]))}')
        tracks += f'<div class="iv-r"><span class="iv-l">{label}</span><div class="iv-t">{line}{mark(who, q["value"], q["ci"], top, said)}</div></div>'
    note = ""
    if m["target"] and "words" in m["target"] and m["single"] and m["arch"]["ci"] and m["single"]["ci"]:
        note = f'<p class="fine iv-note">{overlap_note(m["arch"]["ci"], m["single"]["ci"])}</p>'
    return f'<figure class="iv"><div class="iv-rows">{tracks}</div>{axis(top)}</figure>{note}'


def dot_figures(row: dict, mode: str) -> str:
    """The rates as 1,000 dots each: how many of every thousand, for Archivist and for the single read."""
    m, out = row[mode], ""
    # what a dot counts decides its colour, not whose it is: the wrong values are the same red in both grids; for the
    # other rows the single read's own marked dots stay neutral
    single_kind = row["kind"] if row["kind"] == "wrong" else "once"
    for who, label, kind in (("arch", "Archivist", row["kind"]), ("single", "Single read", single_kind)):
        q = m[who]
        if q is None:
            continue
        svg, marked = dot_grid(f"{row['id']}.{mode}.{who}", q["value"], kind, f"{label}: {marked_words(marked_of(q))}")
        said = (f'about {fact(f"ledger.{row["id"]}.{mode}.{who}.dots", marked)} {esc(row["verb"])}' if marked else f'none {esc(row["verb"])}')
        out += f'<figure class="dotfig"><figcaption><b>{label}</b></figcaption>{svg}<p class="fine">Of every <span data-ok="grid">{num(DOTS)}</span> {esc(row["unit"])}, {said}.</p></figure>'
    return out


def marked_of(q: dict) -> int:
    return round(q["value"] * DOTS)


def marked_words(k: int) -> str:
    return "none of the dots are marked" if k == 0 else "some of the dots are marked, rounded to whole dots"


def counts_text(row: dict, mode: str, s: dict, r: dict, names: dict[str, str]) -> str:
    """What was counted, in a sentence or two. The first rows keep the sentences P51 gave under its three numbers."""
    a, base, b, alone = s["a"], s["base"], s["b"], s["b_alone"]
    m = row[mode]
    rid = row["id"]
    if rid == "h1" and mode == "hosted":
        return (
            f'<p>Reading once: <b>{fact("stat.base_wrong", pct(base["error_rate_accepted"]))}</b> wrong. {fact("stat.a_wrong_n", f"{a["errors_missed"]} of {num(a["n_accepted"])}")} '
            f'values Archivist accepted were wrong, against {fact("stat.base_wrong_n", f"{base["errors_missed"]} of {num(base["n_accepted"])}")} for the single read.</p>'
        )
    if rid == "h1":
        return (
            f'<p>Both reads by {fact("model", names["muse-spark-open"])}. Reading once with the same model: <b>{fact("stat.open_base", pct(alone["error_rate_accepted"]))}</b> wrong. '
            f'{fact("stat.open_wrong_n", f"{b["errors_missed"]} of {num(b["n_accepted"])}")} accepted values were wrong, against {fact("stat.open_base_n", f"{alone["errors_missed"]} of {num(alone["n_accepted"])}")}.</p>'
        )
    if rid == "h2" and mode == "hosted":
        return (
            f'<p>{fact("stat.caught_n", f"{a["errors_caught"]} of {a["n_wrong"]}")} wrong values were sent to a person. '
            f'Reading once catches {fact("stat.base_caught_n", f"{base["errors_caught"]} of {base["n_wrong"]}")}: it flags nothing.</p>'
        )
    arch_n = fact(f"ledger.{rid}.{mode}.arch.n", counted(m["arch"])) if counted(m["arch"]) else ""
    if rid == "h2":
        return f"<p>{arch_n} wrong values were sent to a person.</p>"
    if rid == "h3":
        single = f' Reading once sends {fact(f"ledger.h3.hosted.single.n", counted(m["single"]))}: it flags nothing.' if m["single"] else ""
        return f"<p>{arch_n} values were sent to a person.{single}</p>"
    if rid == "h5":
        single = f' Reading once finds {fact(f"ledger.h5.hosted.single.n", counted(m["single"]))}.' if m["single"] else ""
        return f"<p>{arch_n} planted source errors had a field sent to a person.{single}</p>"
    cells = m["cells"]
    out = cells["by_outcome"]
    return (
        f'<p>Of {fact(f"ledger.r1.{mode}.cells", num(cells["cells"]))} labelled cells on {fact(f"ledger.r1.{mode}.pages", cells["pages"])} pages, the single read was right on '
        f'{fact(f"ledger.r1.{mode}.right", out["right"])} and wrong on {fact(f"ledger.r1.{mode}.wrong", out["wrong"])}; the labeller could not read {fact(f"ledger.r1.{mode}.cant", out["cant_read"])} '
        f'and the single read gave no value on {fact(f"ledger.r1.{mode}.abstained", out["abstained"])}.</p>'
    )


def sources(row: dict, mode: str) -> str:
    """Where the numbers come from and the plan that set the target."""
    path, plan = (row["source_open"], row["plan_open"]) if mode == "open" and "source_open" in row else (row["source"], row["plan"])
    ref_id = row[mode]["ref"]
    plan_ref = f", {ref(ref_id)}" if ref_id else ""
    return (
        f'<p class="src">Source {link(blob(path), "<code>" + esc(path) + "</code>")} · Plan {link(blob(plan), "<code>" + esc(plan) + "</code>")}{plan_ref}</p>'
    )


def condition_chart(s: dict, names: dict[str, str]) -> str:
    """The review rate by the condition of the page, for arms A, B and C: three bars to a condition, each a tip
    of its count; the legend turns an arm off and on."""
    arms = (
        ("A", f'{fact("model", names["muse-spark-1.3"])} (arm A)', "a"),
        ("B", f'{fact("model", names["muse-spark-open"])} (arm B)', "b"),
        ("C", "Mixed (arm C)", "c"),
    )
    cfg, names = s["cfg"], s["conditions"]
    top = nice_axis(max(cfg[k]["by_severity"][str(i)]["review_rate"] for k, _, _ in arms for i in range(4)))
    legend = "".join(f'<button type="button" class="lg {c}" aria-pressed="true" data-arm="{c}"><i></i><span>{label}</span></button>' for _, label, c in arms)
    groups, table = "", ""
    for i, name in enumerate(names):
        bars, cells = "", ""
        for key, label, c in arms:
            st = cfg[key]["by_severity"][str(i)]
            said = f'{label}: {fact(f"cond.{key}.{i}.rate", pct(st["review_rate"], 1))}, {fact(f"cond.{key}.{i}.n", f"{num(st["n_review"])} of {num(st["n_fields"])}")} values'
            bars += f'<span class="cb {c}" tabindex="0" data-arm="{c}" style="--w:{where(st["review_rate"], top)}"><i></i><span class="cv">{fact(f"cond.{key}.{i}.rate", pct(st["review_rate"], 1))}</span>{tip(said)}</span>'
            cells += f'<td>{fact(f"cond.{key}.{i}.rate", pct(st["review_rate"], 1))}</td>'
        groups += f'<div class="cg"><span class="cn">{esc(name)}</span><div class="cbs">{bars}</div></div>'
        table += f'<tr><th scope="row">{esc(name)}</th>{cells}</tr>'
    head = "".join(f'<th scope="col">{label}</th>' for _, label, _ in arms)
    return (
        f'<figure class="cond" data-chart="condition"><figcaption><b>Review rate by condition of the page</b><span class="fine">How worn the page was made, from clean to heavy wear. The same pages for all three arms.</span></figcaption>'
        f'<div class="lgs" role="group" aria-label="Arms shown">{legend}</div><div class="cgs">{groups}</div>{axis(top)}'
        f'<table class="sr"><caption>Share of values sent to a person, by condition of the page</caption><thead><tr><th></th>{head}</tr></thead><tbody>{table}</tbody></table></figure>'
    )


def pane(row: dict, mode: str, s: dict, r: dict, names: dict[str, str], level: str, resamples: str, hidden: bool) -> str:
    return (
        f'<div class="pane" data-mode="{mode}"{" hidden" if hidden else ""}>'
        f'<div class="pcol"><h4>{fact("ci.level", level)} interval</h4>{interval_figure(row, mode, level)}<p class="fine">From {fact("ci.resamples", resamples)} bootstrap resamples of pages.</p></div>'
        f'<div class="pcol"><h4>In <span data-ok="grid">{num(DOTS)}</span></h4><div class="dotpair">{dot_figures(row, mode)}</div></div>'
        f'<div class="pcol"><h4>Counts</h4>{counts_text(row, mode, s, r, names)}{sources(row, mode)}</div>'
        "</div>"
    )


def ledger_row(row: dict, s: dict, r: dict, names: dict[str, str], level: str, resamples: str) -> str:
    rid = row["id"]
    h, o = row["hosted"], row["open"]
    note = f"<small>{esc(row['note'])}</small>" if row["note"] else ""
    cell = lambda who: swap(value_cell(h[who], level), value_cell(o[who], level))  # noqa: E731
    target = swap(target_cell(h["target"], f"ledger.{rid}.hosted.target"), target_cell(o["target"], f"ledger.{rid}.open.target"))
    result = swap(result_cell(h), result_cell(o))
    extra = condition_chart(s, names) if rid == "h3" else ""
    return (
        f'<tbody class="lrow" data-row="{rid}"><tr class="main">'
        f'<th scope="row"><button class="opener" type="button" aria-expanded="false" aria-controls="ev-{rid}"><span class="chev" aria-hidden="true"></span><span class="lt">{esc(row["label"])}</span></button>{note}</th>'
        f'<td data-label="Archivist">{cell("arch")}</td><td data-label="Single read">{cell("single")}</td><td data-label="Target">{target}</td><td data-label="Result">{result}</td></tr>'
        f'<tr class="detail" id="ev-{rid}" hidden><td colspan="5"><div class="xp"><div class="xp-in">{pane(row, "hosted", s, r, names, level, resamples, False)}{pane(row, "open", s, r, names, level, resamples, True)}{extra}</div></div></td></tr></tbody>'
    )


def ledger_section(s: dict, r: dict, names: dict[str, str]) -> str:
    level, resamples = r["level"], r["resamples"]
    rows = ledger_rows(s, r)
    body = "".join(ledger_row(row, s, r, names, level, resamples) for row in rows)
    spark, open_, sam = (fact("model", names[k]) for k in ("muse-spark-1.3", "muse-spark-open", "sam-3.1"))
    cost_cell = swap(*(f'<span class="big">{fact(f"hw.cost.{key}", f"${s['cost'][k]:.4f}")}</span>' for key, k in (("hosted", "a"), ("open", "b"))))
    single = (
        f'<span class="big">{fact(f"hw.cost.single.{key}", f"${s['single_cost'][key]:.4f}")}</span>' if s["single_cost"][key] is not None
        else dash("The test report records no cost a page for this single read")
        for key in MODES
    )
    cost = (
        '<tbody class="cost"><tr class="main"><th scope="row"><span class="lt">Cost a page</span><small>hosted at the hackathon’s discount</small></th>'
        f'<td data-label="Archivist">{cost_cell}</td><td data-label="Single read">{swap(*single)}</td><td colspan="2"></td></tr></tbody>'
    )
    h3 = s["h3"]["numbers"]
    verdict = "was met" if s["h3"]["met"] else '<span class="miss">was missed</span>'
    review_n = f"{num(h3['review'])} of {num(h3['fields'])}"
    line = (
        f'<p class="line">The pre-registered test of {fact("test.pages", num(s["pages"]))} synthetic pages and {fact("test.fields", num(s["fields"]))} values, run on {fact("test.date", s["dates"])} '
        f'and registered at commit <code>{fact("test.commit", s["commit"])}</code>. Archivist sent {fact("test.review", pct(h3["rate"]))} of the values ({fact("test.review_n", review_n)}) to a person; '
        f'its target was {fact("test.target", threshold(h3["threshold"]))}, which {verdict}. {link(blob("results/TEST_RESULTS.md"), "All results")}.</p>'
    )
    only_two = (
        f'<p class="fine">Only two targets were set for open weights, each of under {fact("open.target.synthetic", threshold(s["h4"]["numbers"]["threshold"]))} wrong among accepted: '
        f'one on the synthetic test, one on the real scans. Every other row is shown without one.</p>'
    )
    target = fact("hw.target", threshold(r["o1"]["threshold"]))
    switch = (
        f'<div class="runon" role="group" aria-label="Run on"><span class="ro-l">Run on</span><div class="ro-opts" data-glass>'
        f'<button type="button" class="ro" data-mode="hosted" aria-pressed="true"><b>{MODE_NAME["hosted"]}</b><small>{spark}</small></button>'
        f'<button type="button" class="ro" data-mode="open" aria-pressed="false"><b>{MODE_NAME["open"]}</b><small>{open_}</small></button><i class="ro-thumb" aria-hidden="true"></i></div></div>'
    )
    return f"""<section id="measured"><div class="wrap">
  <p class="kicker">One scheme, one swap</p>
  <h2>What was measured</h2>
  <p class="sec-lede">Each row is a target set before the runs. Pick where Archivist runs and the numbers re-count; open a row for its interval, counts and the rate as <span data-ok="grid">{num(DOTS)}</span> dots.</p>
  <div class="ledger glass reveal" data-glass data-mode="hosted" id="ledger">
    <div class="lhead">{switch}</div>
    <table class="lt-table"><caption class="sr">Every pre-registered target: Archivist, the single read, the target and whether it was met</caption>
    <thead><tr><th scope="col">Measure</th><th scope="col">Archivist</th><th scope="col">Single read</th><th scope="col">Target set</th><th scope="col">Result</th></tr></thead>
    {body}{cost}</table>
  </div>
  {line}
  {only_two}
  <h3 class="sub" id="hardware">On your own hardware</h3>
  <p class="sec-lede tight">{open_} is a model whose trained weights are published. It can replace {spark} for both reads, so a bank that cannot send documents out can run the reading on its own machines.</p>
  <ul class="pts">
    <li><b>Not yet proven on-site.</b> No measured run kept a page on a bank’s own machines: {open_} ran on Baseten, and {sam} still used Meta’s API.</li>
    <li><b>On the real scans it missed its own target</b> of under {target} wrong among accepted: {fact("hw.o1", pct(r["o1"]["value"], 1))}.</li>
    <li><b>The same seven steps.</b> Only the two reads change; the arithmetic, the blind second read and the person do not.</li>
  </ul>
</div></section>"""


# --- the hero and the specimen -----------------------------------------------------------------------------


def hero(names: dict[str, str], s: dict) -> str:
    listed = [fact("model", n) for n in names.values()]
    models_text = ", ".join(listed[:-1]) + " and " + listed[-1]
    a, b = s["a"], s["b"]
    heads = (
        ("stat.a_wrong", pct(a["error_rate_accepted"]), "Wrong among accepted values", ""),
        ("stat.caught", pct(a["catch_rate"]), "Wrong values caught", " good"),
        ("stat.open_wrong", pct(b["error_rate_accepted"]), "Wrong on open weights", ""),
    )
    line = "".join(f'<li><span class="hv{tone}">{fact(key, text)}</span> <span class="hk">{label}</span></li>' for key, text, label, tone in heads)
    return f"""<section class="hero wrap" id="top">
  <p class="eyebrow rise" style="--i:0">Public code<span class="sep">·</span>Pre-registered<span class="sep">·</span>Built on Meta’s {models_text}</p>
  <h1 class="rise" style="--i:1">The archive that <span class="acc">shows its work.</span></h1>
  <p class="lede rise" style="--i:2">Banks hold decades of records as scans. Typing them in is slow, and a model reading them alone gets some values wrong without saying which. I saw this problem first-hand during a bank internship.</p>
  <p class="lede rise" style="--i:3"><strong>Archivist</strong> turns scanned financial archives into a verified database: every value is cited to its spot on the page, read twice with the second read blind, checked by arithmetic, and sent to a person when in doubt.</p>
  <div class="cta rise" style="--i:4">
    <a class="btn primary" href="ui/#{HOME}">Watch it work</a>
    <a class="btn sec" data-glass href="{REPO}#run-it-yourself" rel="noopener">Run it yourself</a>
  </div>
  <ul class="heads rise" style="--i:5" aria-label="The three headline numbers">{line}</ul>
</section>"""


STEP_SIDES = ("l", "l", "l", "l", "r", "r", "r")  # which margin each step's note goes in


def specimen(rp: dict) -> str:
    """The 1939 page as a wide specimen in a glass frame, the replay drawn on the page itself: each step's note in a
    margin, joined to the value by a leader the script draws, and a rail of the seven steps."""
    f, page, steps, rule = rp["field"], rp["page"], rp["steps"], rp["rule"]
    who = {k: v["model"] for k, v in steps.items()}

    def note(k: int, key: str, title: str, detail: str, outcome: str | None = None) -> str:
        model = who[key]
        chips = f'<span class="chip model">{fact("model", model)}</span>' if model else '<span class="chip code">Plain code</span>'
        if outcome:
            chips += f' <span class="chip done">{esc(outcome)}</span>'
        kind = "result" if outcome else ("model" if model else "code")
        return f'<li data-step="{k}" data-side="{STEP_SIDES[k - 1]}" data-kind="{kind}"><span class="t">{step_no(k)}{esc(title)} {chips}</span><p class="d">{detail}</p></li>'

    box, original = f["box"], f["original_box"]
    moved = box != original
    snap, sam, decide = steps["snap"]["facts"], steps["sam"]["facts"], steps["decide"]["facts"]
    read = steps["read"]["facts"]["values"]
    if decide["accepted"] + decide["review"] + decide["abstained"] != read:
        raise Refused("the page's decisions do not add up to the values it read")
    total, *parts = rp["sum"]
    equation = " + ".join(str(p) for p in parts) + f" = {total}"
    value = f'<span class="mono">{fact("replay.value", f["value"])}</span>'
    reread = f'<span class="mono">{fact("replay.reread", f["reread"])}</span>'
    snapped = "The box was moved to fit the printed figure." if moved else "The box already sits on the printed figure."
    fitted = f"Boxes moved on this page: {fact('replay.moved', snap['moved'])} of {fact('replay.boxes', snap['boxes'])}."
    covered = "No stamp or stain on this page, so nothing covers the value." if not sam["detections"] else "Some marks were found on this page, but none covers this value."
    log = [
        note(1, "recognise", "Sort the page", f"Recognised as a table of {fact('replay.type', rp['title'])}."),
        note(2, "read", "Read and cite", f"Read {value} in “{fact('replay.column', rp['column'])}”, row “{fact('replay.period', rp['period'])}”, and boxed where it saw it."),
        note(3, "snap", "Snap to the ink", f"{snapped} {fitted}"),
        note(4, "sam", "Look for covered ink", covered),
        note(5, "blind", "Read again, blind", f"Shown only a crop of the cell, never the first answer, it read {reread}: it agrees."),
        note(6, "rules", "Check the arithmetic", f"{esc(rule['label'])} Row {fact('replay.row', f['row'])}: <span class=\"mono\">{fact('replay.sum', equation)}</span>: it holds."),
        note(7, "decide", "Decide", "Both reads agree and the rule holds, so the value is accepted.", outcome="Accepted"),
    ]
    x0, y0, x1, y1 = f["loop"]["ink"]
    w, h = CROP
    vx = min(max((x0 + x1) / 2 - w / 2, 0), page["width"] - w)
    vy = min(max((y0 + y1) / 2 - h / 2, 0), page["height"] - h)
    k = page["text_height"] / 14
    crop = f["crop"]
    models_used = " + ".join(fact("model", m) for m in rp["models"])
    heading = f"Recorded run · {models_used} · public-domain {fact('replay.year', rp['year'])} Treasury page"
    figure = f"""<svg viewBox="{vx:.0f} {vy:.0f} {w} {h}" role="img" aria-label="A crop of the printed page, with the figure {esc(f['value'])} circled by the pen loop the app draws">
        <image href="{esc(rp['image'])}" x="0" y="0" width="{page['width']}" height="{page['height']}"/>
        <rect class="layer cropbox" data-from="5" data-to="6" x="{crop['x0']}" y="{crop['y0']}" width="{crop['x1'] - crop['x0']}" height="{crop['y1'] - crop['y0']}" rx="2"/>
        <rect class="layer snapbox" data-from="3" data-to="4" x="{box['x0']}" y="{box['y0']}" width="{box['x1'] - box['x0']}" height="{box['y1'] - box['y0']}" rx="2"/>
        <path class="layer pen" data-from="2" d="{esc(f['loop']['d'])}" stroke-width="{f['loop']['width']}" pathLength="1"/>
        <g class="layer tick" data-from="7" transform="translate({x1 + 8 * k:.1f} {(y0 + y1) / 2 - 7 * k:.1f}) scale({k:.3f})"><path d="M2 8l5 5L18 1"/></g>
      </svg>"""
    caption = f"Treasury Bulletin, {fact('replay.issue', rp['issue'])}, page {fact('replay.number', page['number'])}. A development page, never held out. Public domain: FRASER’s “{esc(rp['rights'])}”."
    rail = "".join(
        f'<li><button type="button" data-goto="{i}" aria-label="Show step {i}: {esc(title)}">{step_no(i)}</button></li>'
        for i, title in enumerate(("Sort the page", "Read and cite", "Snap to the ink", "Look for covered ink", "Read again, blind", "Check the arithmetic", "Decide"), start=1)
    )
    return f"""<section class="specimen" id="replay" aria-label="One recorded decision, replayed"><div class="wrap-wide">
  <div class="frame glass rise" style="--i:6" data-glass data-replay>
    <div class="rp-h"><i aria-hidden="true"></i><span class="rp-t">{heading}</span><span class="rp-ctl"><button class="btn small sec" data-glass type="button" data-act="replay">Replay</button><button class="btn small sec" data-glass type="button" data-act="pause">Pause</button></span></div>
    <div class="stage">
      <figure class="scan">{figure}<figcaption>{caption}</figcaption></figure>
      <ol class="notes" role="list">{"".join(log)}</ol>
      <div class="leaders" aria-hidden="true"></div>
    </div>
    <div class="rail-wrap"><ol class="rail" aria-label="The seven steps of the recorded decision">{rail}</ol><i class="rail-fill" aria-hidden="true"></i></div>
    <p class="rp-count">On this page: <b>{fact("replay.accepted", decide["accepted"])}</b> values accepted, <b>{fact("replay.review", decide["review"])}</b> sent to a person, of <b>{fact("replay.read", read)}</b> read.</p>
  </div>
</div></section>"""


# --- how it works: the seven steps as a pipeline -----------------------------------------------------------

STEPS = (
    ("model", "Sort the page", "glimmer", "Untrained, it picks the table type from the page’s text; a plain-code title check confirms it."),
    ("model", "Read and cite", "spark", "Reads every value and boxes where it saw it."),
    ("code", "Snap to the ink", None, "Plain code fits each box to the printed figure."),
    ("model", "Find covered ink", "sam", "Looks for stamps and stains over a value."),
    ("model", "Read again, blind", "spark", "Re-reads each value from a small crop, never seeing the first answer."),
    ("code", "Check the arithmetic", None, "Plain code tests rules a person approved: running balances, totals that must add up."),
    ("code", "Decide", None, "Accepted only if both reads agree and every rule holds."),
)
STEP_CODE = (  # the file behind each step, linked from its panel
    "src/archivist/doctypes/titles.py",
    "src/archivist/pipeline/extract.py",
    "src/archivist/templates/grid.py",
    "src/archivist/pipeline/occlusion.py",
    "src/archivist/pipeline/reread.py",
    "src/archivist/doctypes/template.py",
    "src/archivist/pipeline/verify.py",
)


def step_panels(s: dict, r: dict, names: dict[str, str]) -> list[tuple[str, str]]:
    """What each step checks and what happens when it fails, in the words of the code's own documentation
    (src/archivist/pipeline/verify.py, the README) and with the numbers the result files give."""
    a, sweep, sam = s["a"], r["sweep"], r["sam"]
    glimmer = fact("model", names["muse-glimmer"])
    named = sum(v["classified"] for v in sweep["by_family"].values())
    confirmed = sum(v["confirmed"] for v in sweep["by_family"].values())
    return [
        (
            f"Which table type the page is. {glimmer} picks it from the page’s text, and a plain-code title check then confirms it against the type’s approved titles.",
            f"A page whose title is not confirmed is set aside, and nothing is read from it as that type. On the held-out issues the sweep looked at {fact('step.1.pages', num(sweep['pages']))} pages; "
            f"the classifier named a table family for {fact('step.1.named', num(named))}, and the title check confirmed {fact('step.1.confirmed', num(confirmed))} of them and set {fact('step.1.set_aside', num(sweep['set_aside_by_title_check']))} aside.",
        ),
        (
            "That every value comes with a box: the place on the page where the model saw it.",
            "A value with no box cannot be read again, so it goes to a person. A value the model leaves empty is marked abstained and is not read again; a page that fails to extract counts all its values as omitted.",
        ),
        (
            "That each box sits on the printed figure. The archive’s own text layer, or the table’s ruled lines, place it.",
            f"Where neither finds the figure, the box stays where the model put it, and the record says so. On the real scans an estimated {fact('limit.model_box', pct(r['every']['kept/as_run']['overall']['boxed_model']['value'], 1))} of cells were boxed by the model alone.",
        ),
        (
            "Whether a stamp or a stain covers a value: one detected region over a tenth of a value’s box counts as covering it.",
            f"A covered value is accepted only if everything else agrees, and with lower confidence. On the held-out pages it looked at {fact('step.4.pages', sam['pages'])} pages and found a stamp or stain on {fact('step.4.with', sam['pages_with_a_detection'])} of them.",
        ),
        (
            "Whether a second read, from a small crop of the cell alone and never shown the first answer, agrees with the first.",
            f"A disagreement, an illegible answer or a failed second read sends the value to a person. The blind read is not fully independent: on the synthetic test, of {fact('step.5.wrong', a['reread_on_wrong'])} wrong values it agreed with the wrong one on {fact('step.5.agreed', a['reread_agreed_with_wrong'])}.",
        ),
        (
            "Rules a person approved: running balances, totals that must add up, each within the printed precision.",
            "A rule that fails sends every value it covers to a person, with the value the rule implies shown as a proposal. The value read is never changed.",
        ),
        (
            "That both reads agree and every rule holds.",
            f"Anything else goes to a person, who decides: Archivist proposes a correction with its evidence and never changes a value. On the synthetic test {fact('step.7.accepted', num(a['n_accepted']))} of {fact('step.7.fields', num(a['n_fields']))} values were accepted, "
            f"{fact('step.7.review', num(a['n_review']))} sent to a person and {fact('step.7.abstained', num(a['n_abstained']))} left unread.",
        ),
    ]


def how_it_works(names: dict[str, str], s: dict, r: dict) -> str:
    who = {
        "glimmer": fact("model", names["muse-glimmer"]),
        "spark": f"{fact('model', names['muse-spark-1.3'])} or {fact('model', names['muse-spark-open'])}",
        "sam": fact("model", names["sam-3.1"]),
        None: "Plain code",
    }
    nodes, panels = "", ""
    for i, ((kind, title, model, text), (checks, fails)) in enumerate(zip(STEPS, step_panels(s, r, names)), start=1):
        nodes += (
            f'<li class="pn {kind}"><button type="button" class="pstep" aria-expanded="false" aria-controls="step-{i}">{step_no(i)}'
            f'<span class="pt">{esc(title)}</span><span class="who">{who[model]}</span><span class="pd">{esc(text)}</span></button></li>'
        )
        code = STEP_CODE[i - 1]
        panels += (
            f'<div class="spanel xp" id="step-{i}" role="region" aria-label="{esc(title)}" hidden><div class="xp-in"><h3>{step_no(i)}{esc(title)}</h3>'
            f'<p><b>What it checks.</b> {checks}</p><p><b>When it fails.</b> {fails}</p><p class="src">Code {link(blob(code), "<code>" + esc(code) + "</code>")}</p></div></div>'
        )
    return f"""<section id="how" class="reveal"><div class="wrap">
  <p class="kicker">Seven steps</p>
  <h2>How it works</h2>
  <p class="sec-lede">A value is accepted only when independent checks agree. No model grades its own work, and Archivist never changes a value: it proposes a correction with its evidence, and a person decides.</p>
  <ul class="legend"><li><i class="k-model"></i>A Meta model</li><li><i class="k-code"></i>Plain code</li><li><i class="k-person"></i>A result, or a person</li></ul>
  <ol class="pipe" role="list">{nodes}</ol>
  <div class="outs" aria-label="The two outcomes"><div class="out person"><span class="lab">Accepted</span><h3>Verified database</h3></div><div class="out person"><span class="lab">In doubt</span><h3>A person reviews</h3></div></div>
  <p class="fine hint">Select a step to see what it checks and what happens when it fails.</p>
  <div class="spanels">{panels}</div>
</div></section>"""


# --- real government scans ---------------------------------------------------------------------------------


def _tag(met: bool, yes: str = "met", no: str = "not met") -> str:
    return f'<span class="tag yes">{yes}</span>' if met else f'<span class="tag no">{no}</span>'


def _number(key: str, value: float, interval: list[float], big: bool = True) -> str:
    cls = ' class="big"' if big else ""
    return f"<span{cls}>{fact(key, pct(value, 1))}</span><small>{fact(key + '.ci', span(interval))}</small>"


def _score_row(label: str, key: str, o: dict, last: str, last_label: str) -> str:
    single, archivist, caught = o["single_read_error"], o["archivist_error"], o["catch_rate"]
    return (
        f"<tr><td>{label}</td>"
        f'<td data-label="Single read wrong">{_number(key + ".single", single["value"], single["ci"])}</td>'
        f'<td data-label="Archivist wrong among accepted">{_number(key + ".archivist", archivist["value"], archivist["ci"])}</td>'
        f'<td data-label="Wrong values caught">{_number(key + ".caught", caught["value"], caught["ci"], big=False)}</td>'
        f'<td data-label="{last_label}">{last}</td></tr>'
    )


def corrected_card(fixed: dict) -> str:
    """The corrected key beside the official result, from the result files of the configurations that have them."""
    rows = ""
    version = fixed.get("version_1")
    if version:
        for variant, title, key in (("kept/as_run", "Every labelled cell", "fixed.kept"), ("left_out/as_run", "Pages whose layout matches their template", "fixed.left")):
            res = version["corrected_key"]["labels"][variant]
            rows += _score_row(title, key, res["overall"], _tag(res["r1"]["met"]), "Hypothesis")
    else:
        rows += '<tr><td colspan="5"><span class="tag wait">Hosted: pending, after the dash check</span></td></tr>'
    open_weights = fixed.get("open_weights")
    if open_weights:
        res = open_weights["corrected_key"]["open_weights"]["kept/as_run"]["overall"]
        o1 = open_weights["corrected_key"]["o1"]
        rows += _score_row("Open weights, every labelled cell", "fixed.open", res, _tag(o1["met"], "target met", "target not met"), "Target")
    else:
        rows += '<tr><td colspan="5"><span class="tag wait">Open weights: pending, after the dash check</span></td></tr>'
    return f"""<div class="card">
      <h3>Corrected key</h3>
      <table class="res"><thead><tr><th>Cells</th><th>Single read wrong</th><th>Archivist wrong among accepted</th><th>Wrong values caught</th><th>Hypothesis</th></tr></thead><tbody>{rows}</tbody></table>
      <p class="fine" style="margin-top:12px">Scored under unchanged rules, beside the official result.</p>
    </div>"""


VARIANTS = (
    ("kept/as_run", "Every labelled cell", "real.kept"),
    ("left_out/as_run", "Pages whose layout matches their template", "real.left"),
    ("kept/failed_to_review", "Every labelled cell, unanswered re-reads sent to a person", None),
    ("left_out/failed_to_review", "Matching layouts, unanswered re-reads sent to a person", None),
)


def range_pair(label: str, tag: str, single: dict, arch: dict, keys: tuple[str, str], top: float, level: str, line: str = "", places: int = 1) -> str:
    """One variant: the single read's interval above Archivist's, on the page's own scale, the overlap between
    them shaded: where the two bars overlap, the hypothesis is not met."""
    s_q = quantity(keys[0], single["value"], single["ci"], places=places)
    a_q = quantity(keys[1], arch["value"], arch["ci"], places=places)
    tracks = ""
    for who, who_label, q in (("single", "Single read", s_q), ("arch", "Archivist", a_q)):
        said = f'{who_label}: {fact(q["key"], shown(q))}, {fact("ci.level", level)} interval {fact(ci_key(q), span(q["ci"], places))}'
        tracks += f'<div class="iv-t">{line}{mark(who, q["value"], q["ci"], top, said)}</div>'
    lo, hi = max(single["ci"][0], arch["ci"][0]), min(single["ci"][1], arch["ci"][1])
    band = f'<i class="band" style="--l:{where(lo, top)};--r:{where(hi, top)}"></i>' if lo <= hi else ""
    return f'<div class="rg-row"><div class="rg-l"><span>{label}</span>{tag}</div><div class="rg-tracks">{band}{tracks}</div></div>'


def range_set(key: str, groups: list[tuple[str, list[str]]]) -> str:
    """The rows of one answer key (the official one, or the corrected one), in its groups."""
    out = f'<div class="rg-set" data-key="{key}"{"" if key == "official" else " hidden"}>'
    for title, rows in groups:
        out += f'<div class="rg-g"><h4>{title}</h4>{"".join(rows)}</div>'
    return out + "</div>"


def range_chart(r: dict, fixed: dict, names: dict[str, str]) -> str:
    """A range chart of each variant's intervals, the single read against Archivist, with a switch between the
    official key and the corrected one (disabled, and marked pending, until the corrected file exists)."""
    level, o1 = r["level"], r["o1"]
    spark, open_ = fact("model", names["muse-spark-1.3"]), fact("model", names["muse-spark-open"])
    version, open_fixed = fixed.get("version_1"), fixed.get("open_weights")
    pools = [r["v1"][v]["overall"] for v, _, _ in VARIANTS] + [r["ow"][v]["overall"] for v in ("kept/as_run", "left_out/as_run")]
    if version:
        pools += [version["corrected_key"]["labels"][v]["overall"] for v in ("kept/as_run", "left_out/as_run")]
    if open_fixed:
        pools.append(open_fixed["corrected_key"]["open_weights"]["kept/as_run"]["overall"])
    top = nice_axis(max(p[w]["ci"][1] for p in pools for w in ("single_read_error", "archivist_error")))
    target = target_line(o1["threshold"], top, f'Target: under {fact("hw.target", threshold(o1["threshold"]))}')

    def official() -> list[tuple[str, list[str]]]:
        hosted, own = [], []
        for variant, label, key in VARIANTS:
            res = r["v1"][variant]
            keys = (f"{key}.single", f"{key}.archivist") if key else (f"range.v1.{variant.replace('/', '.')}.single", f"range.v1.{variant.replace('/', '.')}.archivist")
            hosted.append(range_pair(label, _tag(res["r1"]["met"]), res["overall"]["single_read_error"], res["overall"]["archivist_error"], keys, top, level))
        for variant, label, key in VARIANTS[:2]:
            res = r["ow"][variant]
            keys = ("open.single", "open.archivist") if variant == "kept/as_run" else (f"range.ow.{variant.replace('/', '.')}.single", f"range.ow.{variant.replace('/', '.')}.archivist")
            tag = _tag(o1["met"], "target met", "target not met") if variant == "kept/as_run" else ""
            own.append(range_pair(f"Open weights: {label[0].lower()}{label[1:]}", tag, res["overall"]["single_read_error"], res["overall"]["archivist_error"], keys, top, level, line=target if variant == "kept/as_run" else ""))
        return [(f"Hosted, {spark}", hosted), (f"Open weights, {open_}", own)]

    def corrected() -> list[tuple[str, list[str]]]:
        hosted, own = [], []
        if version:
            for variant, label, key in (("kept/as_run", "Every labelled cell", "fixed.kept"), ("left_out/as_run", "Pages whose layout matches their template", "fixed.left")):
                res = version["corrected_key"]["labels"][variant]
                hosted.append(range_pair(label, _tag(res["r1"]["met"]), res["overall"]["single_read_error"], res["overall"]["archivist_error"], (f"{key}.single", f"{key}.archivist"), top, level))
        else:
            hosted.append('<p class="fine"><span class="tag wait">Hosted: pending, after the dash check</span></p>')
        if open_fixed:
            res = open_fixed["corrected_key"]["open_weights"]["kept/as_run"]["overall"]
            own.append(range_pair("Open weights: every labelled cell", _tag(open_fixed["corrected_key"]["o1"]["met"], "target met", "target not met"), res["single_read_error"], res["archivist_error"], ("fixed.open.single", "fixed.open.archivist"), top, level, line=target))
        else:
            own.append('<p class="fine"><span class="tag wait">Open weights: pending, after the dash check</span></p>')
        return [(f"Hosted, {spark}", hosted), (f"Open weights, {open_}", own)]

    ready = bool(version or open_fixed)
    switch = (
        '<div class="keysw" role="group" aria-label="Answer key"><button type="button" class="ks" data-key="official" aria-pressed="true">Official</button>'
        + (
            '<button type="button" class="ks" data-key="corrected" aria-pressed="false">Corrected key</button>'
            if ready
            else '<button type="button" class="ks" data-key="corrected" aria-pressed="false" disabled aria-disabled="true">Corrected key <span class="pend">pending</span></button>'
        )
        + "</div>"
    )
    sets = range_set("official", official()) + (range_set("corrected", corrected()) if ready else "")
    note = "" if r["stalled"] else '<p class="fine">No re-read went unanswered in the open-weights run, so it has one variant of each kind, as run.</p>'
    return f"""<div class="card chart" id="range" data-chart="range">
      <div class="chart-h"><div><h3>Where the intervals fall</h3><p class="fine">Each pair is the single read (grey) against Archivist (indigo): the bar is the {fact("ci.level", level)} interval, the dot the estimate. Where the two bars overlap, the hypothesis is not met.</p></div>{switch}</div>
      {sets}{axis(top)}{note}
    </div>"""


def causes(diag: dict, config: str, title: str) -> str:
    """The wrong values counted by cause, as bars: hover, tap or focus a part for its cause, its count and its share."""
    out = f'<div class="cause-g"><h4>{title}</h4>'
    for who, label in (("single", "Wrong single reads"), ("accepted", "Wrong values Archivist accepted")):
        d = diag[(config, who, "kept")]
        parts = (("s-drift", "drift", "layout drift"), ("s-format", "format", "format only"), ("s-read", "reading", "reading errors"))
        said = ", ".join(f"{d[field]} {name}" for _, field, name in parts)
        segments = ""
        for kind, field, name in parts:
            count = d[field]
            if not count:
                continue
            share = count / d["wrong"]
            shown_count = fact(f"diag.{config}.{who}.{name}", count) if share >= 0.07 else ""
            said_tip = f'{esc(name.capitalize())}: {fact(f"diag.tip.{config}.{who}.{field}.n", f"{count} of {d["wrong"]}")} wrong values, {fact(f"diag.tip.{config}.{who}.{field}.share", pct(share, 0))}'
            if field == "reading":
                said_tip += (
                    f'. A row the page does not show {fact(f"diag.tip.{config}.{who}.read.missing", d["missing"])}, misalignment {fact(f"diag.tip.{config}.{who}.read.misaligned", d["misaligned"])}, '
                    f'digit misread {fact(f"diag.tip.{config}.{who}.read.digit", d["digit"])}, other {fact(f"diag.tip.{config}.{who}.read.other", d["other"])}'
                )
            segments += f'<b class="{kind}" tabindex="0" style="flex:{count} 1 0">{shown_count}{tip(said_tip)}</b>'
        out += f'<div class="cause-r"><span>{label}: {fact(f"diag.{config}.{who}.wrong", d["wrong"])}</span><div class="seg" role="group" aria-label="{esc(label)} by cause: {esc(said)}">{segments}</div></div>'
    return out + "</div>"


def depth(r: dict, titles: dict[str, str], names: dict[str, str]) -> str:
    """Held-out results by stratum and by family, as the score files hold them: aggregates, never a page or a cell."""
    level = r["level"]
    spark, open_ = fact("model", names["muse-spark-1.3"]), fact("model", names["muse-spark-open"])
    strata = [k for k in r["v1"]["kept/as_run"]["by_stratum"]]
    top = nice_axis(max(
        res["by_stratum"][st][w]["ci"][1]
        for res in (r["v1"]["kept/as_run"], r["v1"]["left_out/as_run"], r["ow"]["kept/as_run"], r["ow"]["left_out/as_run"])
        for st in strata for w in ("single_read_error", "archivist_error")
    ))

    def stratum_name(st: str) -> str:
        return fact(f"strat.{st}.name", st.replace("_", "–")) if st[0].isdigit() else esc(st.replace("_", " ").capitalize())

    blocks = ""
    for cfg, heading, labels, source in (("v1", f"Hosted, {spark}", r["v1"], REAL_SCORE), ("ow", f"Open weights, {open_}", r["ow"], OPEN_SCORE)):
        rows = ""
        for variant, vlabel, _ in VARIANTS[:2]:
            for st in strata:
                d = labels[variant]["by_stratum"][st]
                n = d["counted"]
                kk = f"strat.{cfg}.{variant.replace('/', '.')}.{st}"
                label = f'{stratum_name(st)} <small>{vlabel}: {fact(kk + ".cells", num(n["cells"]))} cells on {fact(kk + ".pages", n["pages"])} pages</small>'
                rows += range_pair(label, "", d["single_read_error"], d["archivist_error"], (kk + ".single", kk + ".archivist"), top, level)
        blocks += f'<div class="rg-g"><h4>{heading}</h4>{rows}</div>'
    fam_rows = ""
    for fam, w in r["families"].items():
        e = r["every"]["kept/as_run"]["by_family"][fam]
        k = f"fam.{fam}"
        fam_rows += (
            f'<tr><th scope="row">{fact(k + ".title", titles[fam])}</th>'
            f'<td data-label="Named">{fact(k + ".named", w["classified"])}</td><td data-label="Confirmed">{fact(k + ".confirmed", w["confirmed"])}</td><td data-label="Read in full">{fact(k + ".read", w["deep_pages"])}</td>'
            f'<td data-label="Cells">{fact(k + ".cells", num(e["cells"]))}</td><td data-label="Sent to a person">{fact(k + ".review", pct(e["review_rate"]["value"], 1))}</td>'
            f'<td data-label="Boxed by the model alone">{fact(k + ".model", pct(e["boxed_model"]["value"], 1))}</td><td data-label="By the text layer">{fact(k + ".ocr", pct(e["boxed_ocr"]["value"], 1))}</td><td data-label="By the grid">{fact(k + ".grid", pct(e["boxed_grid"]["value"], 1))}</td></tr>'
        )
    return f"""<details class="depth" id="depth"><summary><span class="chev" aria-hidden="true"></span>By stratum and by family</summary>
  <div class="xp"><div class="xp-in depth-in">
    <p class="fine">The cells were drawn in strata, and each is weighted by the inverse of its chance of being labelled. Aggregates only, from {link(blob(REAL_SCORE), "<code>" + esc(REAL_SCORE) + "</code>")} and {link(blob(OPEN_SCORE), "<code>" + esc(OPEN_SCORE) + "</code>")}.</p>
    <div class="chart" data-chart="strata"><h4>Wrong among accepted, by stratum</h4>{blocks}{axis(top)}</div>
    <div class="chart"><h4>By table family, hosted</h4>
    <table class="fam"><caption class="sr">Pages, cells, review rate and how cells were boxed, for each table family</caption><thead><tr><th scope="col">Table</th><th scope="col">Named</th><th scope="col">Confirmed</th><th scope="col">Read in full</th><th scope="col">Cells</th><th scope="col">Sent to a person</th><th scope="col">Boxed by the model alone</th><th scope="col">By the text layer</th><th scope="col">By the grid</th></tr></thead><tbody>{fam_rows}</tbody></table></div>
  </div></div></details>"""


def real_scans(r: dict, diag: dict, fixed: dict, names: dict[str, str], titles: dict[str, str]) -> str:
    kept, left, ow = r["v1"]["kept/as_run"], r["v1"]["left_out/as_run"], r["ow"]["kept/as_run"]
    o1 = r["o1"]
    cells, blanks = kept["cells"], kept["by_choice"]["blank"]
    rows = _score_row(f"Every labelled cell<small>all {fact('real.cells', num(cells))}</small>", "real.kept", kept["overall"], _tag(kept["r1"]["met"]), "Hypothesis")
    rows += _score_row(f"Pages whose layout matches their template<small>{fact('real.left_cells', num(left['cells']))} cells</small>", "real.left", left["overall"], _tag(left["r1"]["met"]), "Hypothesis")
    target = fact("open.target", threshold(o1["threshold"]))
    rows += _score_row(
        f"Open weights, every labelled cell<small>its target: under {target} wrong among accepted</small>",
        "open",
        ow["overall"],
        _tag(o1["met"], "target met", "target not met"),
        "Target",
    )
    if fixed:
        second = corrected_card(fixed)
    else:
        second = f"""<div class="card pending">
      <h3>Corrected key</h3>
      <p class="big">Pending, after the dash check</p>
      <p class="fine">The author looks at the {fact("real.blank", num(blanks))} cells first labelled blank, on the printed page, and marks where a dash is printed. Those answers become “-”, and the same scorer scores them beside the official result, under unchanged rules. The result file does not exist yet.</p>
    </div>"""
    v_left, v_left_acc = diag[("v1", "single", "left out")], diag[("v1", "accepted", "left out")]
    v_kept, v_kept_acc = diag[("v1", "single", "kept")], diag[("v1", "accepted", "kept")]
    left_n = f"{v_left['format']} of {v_left['wrong']}"
    left_acc_n = f"{v_left_acc['format']} of {v_left_acc['wrong']}"
    drift_n = f"{v_kept['drift']} of {v_kept['wrong']}"
    drift_acc_n = f"{v_kept_acc['drift']} of {v_kept_acc['wrong']}"
    reading_n = f"{v_kept['reading']} of {v_kept['wrong']}"
    reading_acc_n = f"{v_kept_acc['reading']} of {v_kept_acc['wrong']}"
    spark, open_ = fact("model", names["muse-spark-1.3"]), fact("model", names["muse-spark-open"])
    return f"""<section id="scans" class="reveal"><div class="wrap">
  <p class="kicker">Measured on the real thing</p>
  <h2>Real government scans</h2>
  <p class="sec-lede">The pre-registered test on held-out pages of the Treasury Bulletin, which no model had seen: {fact("real.cells", num(cells))} cells drawn in advance and labelled by the author from the printed page, never shown a model’s answer. Its one hypothesis, {ref("R1")}, said Archivist’s wrong values among those it accepts would be fewer than the single read’s, with the intervals apart. It was not met, in any variant. This is the official result, as scored.</p>
  {range_chart(r, fixed, names)}
  <div class="scans">
    <div class="card">
      <h3>Official result</h3>
      <table class="res"><thead><tr><th>Cells</th><th>Single read wrong</th><th>Archivist wrong among accepted</th><th>Wrong values caught</th><th>Hypothesis</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    {second}
  </div>
  {depth(r, titles, names)}
  <h3 class="sub">What the diagnosis found</h3>
  <p class="sec-lede tight">Why the scores came out as they did: the wrong values counted by cause, from the committed records. It changes no score.</p>
  <div class="card causes">
    {causes(diag, "v1", f"Hosted, {spark}")}
    {causes(diag, "ow", f"Open weights, {open_}")}
    <ul class="key"><li><i class="s-drift"></i>Layout drift: the page prints other columns than the template describes</li><li><i class="s-format"></i>Format only: mostly a dash read where the key says blank</li><li><i class="s-read"></i>Reading errors: misalignment, digit misreads, a missing row, the rest</li></ul>
  </div>
  <ul class="finds">
    <li><b>On pages whose layout matches, almost every wrong value is a dash read where the key says blank:</b> {fact("diag.left.single", left_n)} of the single read’s wrong values, and {fact("diag.left.accepted", left_acc_n)} of those Archivist accepted. The official score depends on that convention more than on anything else.</li>
    <li><b>With every page kept, layout drift is the largest cause:</b> {fact("diag.kept.drift", drift_n)} wrong single reads and {fact("diag.kept.drift_acc", drift_acc_n)} accepted ones. The templates describe an earlier layout than the pages that came later.</li>
    <li><b>Reading errors proper are few:</b> {fact("diag.kept.reading", reading_n)} wrong single reads and {fact("diag.kept.reading_acc", reading_acc_n)} accepted values. {link(blob(DIAGNOSIS), "The diagnosis")} has the method and the tables.</li>
  </ul>
</div></section>"""


# --- planned before the data: a timeline of the commits -------------------------------------------------------

PLAN_TITLES = {
    "synthetic": ("The synthetic test", "Ledger cards and payment memos, one run of each configuration."),
    "real": ("Real Treasury scans", "Held-out Treasury Bulletin pages, read through Meta’s API."),
    "openw": ("Open weights on the real scans", "The same pages and answer key, read by Muse Spark Open."),
}


def planned(git: dict, plan_list: list[dict]) -> str:
    groups = ""
    for p in plan_list:
        title, what = PLAN_TITLES[p["name"]]
        items = ""
        last = len(p["events"]) - 1
        for i, (event, sha, stamp, message) in enumerate(p["events"]):
            key = f"plan.{p['name']}.{i}"
            if sha:
                code = f' {link(commit_url(sha), "<code>" + fact(key + ".sha", sha) + "</code>")}'
                said = f'<span class="tip" role="tooltip">{fact(key + ".msg", message)}</span>'
            else:
                code, said = "", ""
            gap = f'<span class="gap">{fact("plan." + p["name"] + ".gap", apart(*p["gap"]))} after the plan was registered</span>' if i == last else ""
            items += f'<li class="{"run" if i else ""}"><span class="ev">{esc(event)}{code}{said}</span><span class="when">{fact(key + ".when", clock(stamp))}</span>{gap}</li>'
        groups += (
            f'<li class="tl-g"><h3>{esc(title)}</h3><p class="what">{esc(what)}</p><ol class="tl-ev">{items}</ol>'
            f'<p class="fine" style="margin:12px 0 0">{link(blob(p["file"]), "<code>" + esc(p["file"]) + "</code>")}</p></li>'
        )
    first = git["first_commit"]
    opening = (
        '<li class="tl-g"><h3>The first commit</h3><ol class="tl-ev"><li><span class="ev">First commit '
        f'{link(commit_url(first["sha"]), "<code>" + fact("plan.first.sha", first["sha"]) + "</code>")}<span class="tip" role="tooltip">{fact("plan.first.msg", first["message"])}</span></span>'
        f'<span class="when">{fact("plan.first.when", clock(first["date"]))}</span></li></ol></li>'
    )
    return f"""<section id="planned" class="reveal"><div class="wrap tl-wrap">
  <div class="tl-intro">
  <p class="kicker">Read from git</p>
  <h2>Planned before the data</h2>
  <p class="sec-lede">Each plan was committed before the runs it governs, with its hypotheses, its scorer and its targets, so a result cannot be tuned afterwards. The dates are the committer’s clock from git, not a third-party timestamp. The first commit is <code>{fact("plan.first.sha", first["sha"])}</code>, {fact("plan.first.when", clock(first["date"]))}.</p>
  <p class="fine">Hover or focus a commit to read its message; each links to it on GitHub.</p>
  </div>
  <ol class="tl">{opening}{groups}</ol>
</div></section>"""


# --- honest limits, try it, the page ---------------------------------------------------------------------------


def limits(s: dict, r: dict) -> str:
    every = r["every"]["kept/as_run"]["overall"]
    h3, h5 = s["h3"]["numbers"], s["h5"]["numbers"]
    found = f"{h5['found']} of {h5['planted']}"
    changed = f"{r['changed']} of {r['pages_checked']}"
    o1_target = fact("limit.o1_target", threshold(r["o1"]["threshold"]))
    sparkft = f"{REPO}/blob/main/results/sparkft/REPORT.md#cached-boxes-no-reusable-conversion-found"
    return f"""<section id="limits" class="reveal"><div class="wrap">
  <p class="kicker">Said plainly</p>
  <h2>Honest limits</h2>
  <div class="limits">
    <div class="card limit"><h3>Targets missed</h3>
      <p>On the synthetic test, Archivist sent <b>{fact("limit.h3", pct(h3["rate"]))}</b> of values to a person against a target of {fact("limit.h3_target", threshold(h3["threshold"]))}, and flagged <b>{fact("limit.h5", pct(h5["rate"]))}</b> ({fact("limit.h5_n", found)}) of the planted source errors against a target of {fact("limit.h5_target", threshold(h5["threshold"]))}.</p>
      <p>On the real scans the hypothesis was not met in any variant, and open weights missed its target of under {o1_target}.</p></div>
    <div class="card limit"><h3>The box offset</h3>
      <p>Boxes can sit away from the printed value. On the real scans an estimated {fact("limit.model_box", pct(every["boxed_model"]["value"], 1))} of cells were boxed by the model alone; only {fact("limit.ocr_box", pct(every["boxed_ocr"]["value"], 1))} were anchored by the page’s text layer and {fact("limit.grid_box", pct(every["boxed_grid"]["value"], 1))} by the table’s grid. {link(sparkft, "Cached measurements")} found no reusable conversion.</p></div>
    <div class="card limit"><h3>Layout drift</h3>
      <p>The templates were drafted from development pages, and the held-out pages come from later issues, whose layout drifted. Of the {fact("limit.pages", r["pages_checked"])} pages the deep check read, {fact("limit.changed", changed)} print different columns than their template or are a different table, and the scores count a value given for a column the page does not print as wrong.</p></div>
    <div class="card limit"><h3>The hackathon’s discount</h3>
      <p>Hosted reads ran in Contributor mode, the hackathon’s discounted price (decision {ref("D19")}), so <b>{fact("limit.cost_a", f"${s['cost']['a']:.4f}")}</b> a page flatters the hosted side; a real deployment would use Standard mode or open weights. Open weights cost <b>{fact("limit.cost_b", f"${s['cost']['b']:.4f}")}</b> a page at Baseten’s printed prices, which are not a contract.</p></div>
    <div class="card limit"><h3>One run, one labeller</h3>
      <p>Each configuration ran once. The synthetic accounts share names and amounts, so the intervals may understate the uncertainty. The author alone labels the real-scan answer key. {link(blob("README.md#honest-limits"), "The README lists the rest")}.</p></div>
  </div>
</div></section>"""


def try_it(commands: list[str]) -> str:
    code = esc("\n".join(commands))
    return f"""<section id="try" class="reveal"><div class="wrap">
  <p class="kicker">No key, no model call</p>
  <h2>Try it</h2>
  <div class="try">
    <div class="card"><h3>The live demo</h3><p>The review app over the recorded runs: Watch it work, the review queue, the accuracy report. Recorded runs only; nothing is called.</p><a class="btn primary" href="ui/#{HOME}">Watch it work</a></div>
    <div class="card"><h3>Docker</h3><pre><code data-fact="docker">{code}</code></pre><p>The first <code>run</code> serves this page at <code>/</code> and the review app at <code>/ui/</code>; the second runs the judge checks.</p></div>
    <div class="card"><h3>The repository</h3><p>The code, the plans, every result and the reasons for each decision.</p>{link(REPO, "kamil-shirinov/Archivist", ' class="btn sec" data-glass rel="noopener"')}</div>
  </div>
</div></section>"""


TOP = """<header class="pillbar"><div class="pill glass" data-glass>
  <a class="brand" href="#top"><img src="assets/brand/logo-light.svg" alt="" width="26" height="26"><span class="wordmark">Archivist</span></a>
  <nav class="nav" aria-label="On this page"><a href="#measured">Measured</a><a href="#how">How it works</a><a href="#scans">Real scans</a><a href="#planned">Planned first</a><a href="#limits">Limits</a><a href="#try">Try it</a></nav>
  <div class="pill-r"><a class="btn small sec" data-glass href="ui/#replay">Watch it work</a>
    <button class="tog" type="button" data-theme-toggle aria-label="Dark mode" aria-pressed="false"><svg class="only-light" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/></svg><svg class="only-dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/></svg></button></div>
</div></header>"""

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Archivist: the archive that shows its work</title>
<meta name="description" content="Archivist turns scanned financial archives into a verified database: every value cited to its spot on the page, read twice with the second read blind, checked by arithmetic, and sent to a person when in doubt.">
<link rel="icon" type="image/svg+xml" href="assets/brand/logo-light.svg">
<link rel="preload" href="docs/landing/fonts/Newsreader-Latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="docs/landing/fonts/Geist-Latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="docs/landing/landing.css">
<script>try{var t=localStorage.getItem("archivist-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}document.documentElement.classList.add("js");if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("play")</script>
<noscript><style>.notes li,.rp-count,.layer,.reveal,.rise{opacity:1!important;transform:none!important}.ledger .swap .v.o{visibility:visible!important}.ledger .swap{display:flex;gap:.6em}.ledger .detail,.spanel,.pane[hidden]{display:block!important}.spanel[hidden]{display:block!important}.rg-set[hidden]{display:block!important}.mk .bar,.cb i{transform:none!important}</style></noscript>
<script src="docs/landing/landing.js" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to the page</a>
<div class="bg" aria-hidden="true"><i class="g1"></i><i class="g2"></i><i class="g3"></i></div>
"""


def render(root: Path = ROOT) -> str:
    """The landing page, as one HTML document."""
    names = models(root)
    git = proof(root)
    s = synthetic(root)
    s["commit"] = git["registration"]["sha"]
    r = real_scores(root)
    level = next(re.search(r"_ci(\d+)$", k).group(1) for k in s["a"] if re.search(r"_ci(\d+)$", k))
    if f"{level}%" != r["level"] or num(s["resamples"]) != r["resamples"]:
        raise Refused("the synthetic test and the real-scan test state different intervals")
    rp = replay(root)
    footer = (
        f'<footer class="foot"><div class="wrap"><p>Archivist, built for the Meta Global AI Developer Hackathon from {fact("foot.first", day(git["first_commit"]["date"]))}. '
        f'The code is published for review, all rights reserved ({link(blob("LICENSE"), "LICENSE")}). Pages are from FRASER, the St. Louis Fed’s archive, or synthetic. '
        f'The type is Geist, under the SIL Open Font License ({link("ui/fonts/GEIST-OFL.txt", "licence", "")}). '
        f'Headlines are set in Newsreader, also under the SIL Open Font License ({link("docs/landing/fonts/NEWSREADER-OFL.txt", "licence", "")}).</p></div></footer>'
    )
    body = [
        DOT_DEFS,
        TOP,
        '<main id="main">',
        hero(names, s),
        specimen(rp),
        ledger_section(s, r, names),
        how_it_works(names, s, r),
        real_scans(r, diagnosis(root), corrected(root), names, family_titles(root)),
        planned(git, plans(git, s, r)),
        limits(s, r),
        try_it(docker_commands(root)),
        "</main>",
        footer,
        "</body>\n</html>\n",
    ]
    return HEAD + "\n".join(body)


if __name__ == "__main__":
    sys.stdout.write(render())
