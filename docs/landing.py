"""The landing page at the published site's root (P51), written by docs/make_site.py.

    python docs/landing.py             # print the page to standard output (a look, nothing is written)

The site's front door says in a few seconds what Archivist does, why it matters, what was measured and where
to try it, and the app stays at /ui/. The page is static: no model call, no key, no request to another site.
Standard library only.

Every number on it is read here, at build time, from a committed file, and written through fact(), which
marks it (data-fact="<key>") so that tests/test_landing.py can recompute each one from its file and fail if
the page differs, or if a digit sits anywhere on the page that is not a marked fact. Nothing is typed by hand:

  * the three numbers and the test's size, date and review share: results/test_report.json and the run
    records in results/runs/ (the date), the registration commit from git;
  * the real scans: the official scores (results/real_test/held_out/score/score.json and
    results/real_openw/held_out/score/score.json), what the diagnosis found (a table in
    results/real_test/held_out/diagnosis.md, parsed), and the corrected key's scores only if their files exist;
    held-out results appear as aggregate numbers alone, never a cell, a value or a page image;
  * the pre-registrations' commits, tags and dates: git, or docs/landing_proof.json where there is no git
    history (the Docker image); a test proves the two agree;
  * the replay: one recorded decision of the development run on the Treasury Bulletin (a public-domain page),
    its steps, models, rule, loop and counts from that run's bundle, and a fixed choice of value that the
    code checks still qualifies (accepted, the blind read agrees, a rule held, a clean pen loop);
  * the Docker commands: README.md; the Meta models: the model ids in config/.

A claim that has no file behind it is left out (CLAUDE.md, P51).
"""

from __future__ import annotations

import html
import json
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
    "assets/brand/logo-light.svg",
    "assets/brand/logo-dark.svg",
)
PROOF_FILE = "docs/landing_proof.json"

TEST_REPORT = "results/test_report.json"
REAL_SCORE = "results/real_test/held_out/score/score.json"
OPEN_SCORE = "results/real_openw/held_out/score/score.json"
DIAGNOSIS = "results/real_test/held_out/diagnosis.md"
SWEEP = "results/real_test/held_out/sweep.json"
CORRECTED = {
    "version_1": "results/real_test/held_out/score_corrected/score.json",
    "open_weights": "results/real_openw/held_out/score_corrected/score.json",
}
BUNDLES = "data/bundles"
REPLAY_RUN = "treasury-development"
# The one recorded decision the replay plays: a figure on a December 1939 Treasury Bulletin page, whose pen loop
# was looked at on the page and clears the printed figures around it. qualifying() checks it still qualifies.
REPLAY_FIELD = "T.receipts_and_expenditures_under_railroad:1939-12_p025:13:to_unemployment"
CROP = (230, 82)  # the crop of the page the replay shows, in the scan's own pixels

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


def span(interval: list[float]) -> str:
    return f"{pct(interval[0], 1)}–{pct(interval[1], 1)}"


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
    line = _git(root, "log", "-1", "--format=%H %cI", *args)
    if not line or " " not in line:
        return None
    sha, stamp = line.split(" ", 1)
    return {"sha": sha[:7], "date": _utc(stamp).strftime("%Y-%m-%dT%H:%M:%SZ")}


def git_facts(root: Path = ROOT) -> dict | None:
    """The commits and tags the page cites, from git; None where there is no full history to read them from."""
    if _git(root, "rev-parse", "--is-shallow-repository") != "false":
        return None
    added = _git(root, "log", "--diff-filter=A", "--format=%H %cI", "--", "PREREGISTRATION.md")
    roots = (_git(root, "rev-list", "--max-parents=0", "HEAD") or "").split()
    if not added or len(roots) != 1:
        return None
    sha, stamp = added.splitlines()[-1].split(" ", 1)
    facts: dict = {
        "first_commit": _commit(root, roots[0]),
        "registration": {"sha": sha[:7], "date": _utc(stamp).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "tags": {tag: _commit(root, f"refs/tags/{tag}^{{commit}}") for tag in PLAN_TAGS},
    }
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
        "h3": h3,
        "h5": h5,
    }


def real_scores(root: Path) -> dict:
    v1, ow = _json(root, REAL_SCORE), _json(root, OPEN_SCORE)
    return {
        "v1": v1["labels"],
        "ow": ow["open_weights"],
        "o1": ow["o1"],
        "every": v1["every_cell"],
        "pages_checked": v1["sam"]["pages"],
        "changed": len(v1["both_ways_pages"]),
        "started": _json(root, SWEEP)["started_at"],
        "ow_started": ow["run"]["started_at"],
    }


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
                found[(*key, row[0])] = {"wrong": wrong, "drift": drift, "format": fmt, "reading": missing + mis + digit + other}
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
    """Each pre-registration: when its plan was registered, when its code was frozen, when its run began."""
    tags = git["tags"]

    def at(tag: str) -> tuple[str, str]:
        return tags[tag]["sha"], tags[tag]["date"]

    return [
        {
            "file": "PREREGISTRATION.md",
            "name": "synthetic",
            "events": [("Plan registered", git["registration"]["sha"], git["registration"]["date"]), ("First run began", None, syn["started"])],
            "gap": (git["registration"]["date"], syn["started"]),
        },
        {
            "file": "PREREGISTRATION_REAL.md",
            "name": "real",
            "events": [("Plan registered", *at("prereg-real-treasury")), ("Runner frozen", *at("run-real-treasury")), ("Held-out sweep began", None, real["started"])],
            "gap": (at("prereg-real-treasury")[1], real["started"]),
        },
        {
            "file": "PREREGISTRATION_OPENW.md",
            "name": "openw",
            "events": [("Plan registered", *at("prereg-real-openw")), ("Runner frozen", *at("run-real-openw")), ("Held-out run began", None, real["ow_started"])],
            "gap": (at("prereg-real-openw")[1], real["ow_started"]),
        },
    ]


# --- writing HTML --------------------------------------------------------------------------------------


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def fact(key: str, text: object) -> str:
    """A fact read from a file, marked so that a test can find it and compare it with its source."""
    return f'<span data-fact="{esc(key)}">{esc(text)}</span>'


def ref(name: str) -> str:
    """A name the page refers to that has a digit in it (a hypothesis, a decision), not a number of its own."""
    return f'<span data-ok="ref">{esc(name)}</span>'


def link(href: str, text: str, extra: str = ' rel="noopener"') -> str:
    return f'<a href="{esc(href)}"{extra}>{text}</a>'


def blob(path: str) -> str:
    return f"{REPO}/blob/main/{path}"


def threshold(value: float) -> str:
    """A target as the report states it: 0.2 is 20%."""
    return f"{value * 100:g}%"


def bar(label: str, share: float, kind: str = "") -> str:
    return f'<div class="bar {kind}"><span>{label}</span><i style="--w:{share * 100:.1f}%"></i></div>'


def hero(names: dict[str, str], panel: str) -> str:
    listed = [fact("model", n) for n in names.values()]
    models_text = ", ".join(listed[:-1]) + " and " + listed[-1]
    return f"""<section class="hero wrap" id="top">
  <div class="hero-copy">
    <p class="eyebrow rise" style="--i:0">Public code<span class="sep">·</span>Pre-registered<span class="sep">·</span>Built on Meta’s {models_text}</p>
    <h1 class="rise" style="--i:1">The archive that shows its work.</h1>
    <p class="lede rise" style="--i:2">Banks hold decades of records as scans. Typing them in is slow, and a model reading them alone gets some values wrong without saying which. I saw this problem first-hand during a bank internship.</p>
    <p class="lede rise" style="--i:3"><strong>Archivist</strong> turns scanned financial archives into a verified database: every value is cited to its spot on the page, read twice with the second read blind, checked by arithmetic, and sent to a person when in doubt.</p>
    <div class="cta rise" style="--i:4">
      <a class="btn primary" href="ui/#{HOME}">Watch it work</a>
      <a class="btn" href="{REPO}#run-it-yourself" rel="noopener">Run it yourself</a>
    </div>
  </div>
  {panel}
</section>"""


def numbers(s: dict) -> str:
    a, base, b, alone = s["a"], s["base"], s["b"], s["b_alone"]
    top = max(base["error_rate_accepted"], alone["error_rate_accepted"])
    review = s["h3"]["numbers"]
    verdict = "was met" if s["h3"]["met"] else '<span class="miss">was missed</span>'
    a_n = f"{a['errors_missed']} of {num(a['n_accepted'])}"
    base_n = f"{base['errors_missed']} of {num(base['n_accepted'])}"
    caught_n = f"{a['errors_caught']} of {a['n_wrong']}"
    base_caught_n = f"{base['errors_caught']} of {base['n_wrong']}"
    open_n = f"{b['errors_missed']} of {num(b['n_accepted'])}"
    open_base_n = f"{alone['errors_missed']} of {num(alone['n_accepted'])}"
    review_n = f"{num(review['review'])} of {num(review['fields'])}"
    return f"""<section class="numbers wrap reveal" aria-labelledby="numbers-h">
  <h2 class="sr" id="numbers-h">What was measured</h2>
  <div class="stats">
    <div class="stat">
      <div class="stat-k">Wrong among accepted values</div>
      <div class="stat-v">{fact("stat.a_wrong", pct(a["error_rate_accepted"]))}</div>
      <div class="stat-c">Reading once: <b>{fact("stat.base_wrong", pct(base["error_rate_accepted"]))}</b> wrong. {fact("stat.a_wrong_n", a_n)} values Archivist accepted were wrong, against {fact("stat.base_wrong_n", base_n)} for the single read.</div>
      <div class="bars" aria-hidden="true">{bar("Archivist", a["error_rate_accepted"] / top)}{bar("Read once", base["error_rate_accepted"] / top, "once")}</div>
    </div>
    <div class="stat">
      <div class="stat-k">Wrong values caught</div>
      <div class="stat-v good">{fact("stat.caught", pct(a["catch_rate"]))}</div>
      <div class="stat-c">{fact("stat.caught_n", caught_n)} wrong values were sent to a person. Reading once catches {fact("stat.base_caught_n", base_caught_n)}: it flags nothing.</div>
      <div class="bars" aria-hidden="true">{bar("Archivist", a["catch_rate"])}{bar("Read once", base["catch_rate"], "once none")}</div>
    </div>
    <div class="stat">
      <div class="stat-k">Wrong on open weights</div>
      <div class="stat-v">{fact("stat.open_wrong", pct(b["error_rate_accepted"]))}</div>
      <div class="stat-c">Both reads by Muse Spark Open. Reading once with the same model: <b>{fact("stat.open_base", pct(alone["error_rate_accepted"]))}</b> wrong. {fact("stat.open_wrong_n", open_n)} accepted values were wrong, against {fact("stat.open_base_n", open_base_n)}.</div>
      <div class="bars" aria-hidden="true">{bar("Archivist", b["error_rate_accepted"] / top)}{bar("Read once", alone["error_rate_accepted"] / top, "once")}</div>
    </div>
  </div>
  <p class="line">The pre-registered test of {fact("test.pages", num(s["pages"]))} synthetic pages and {fact("test.fields", num(s["fields"]))} values, run on {fact("test.date", s["dates"])} and registered at commit <code>{fact("test.commit", s["commit"])}</code>. Archivist sent {fact("test.review", pct(review["rate"]))} of the values ({fact("test.review_n", review_n)}) to a person; its target was {fact("test.target", threshold(review["threshold"]))}, which {verdict}. {link(blob("results/TEST_RESULTS.md"), "All results")}.</p>
</section>"""


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


def causes(diag: dict, config: str, title: str) -> str:
    out = f'<div class="cause-g"><h4>{title}</h4>'
    for who, label in (("single", "Wrong single reads"), ("accepted", "Wrong values Archivist accepted")):
        d = diag[(config, who, "kept")]
        parts = (("s-drift", d["drift"], "layout drift"), ("s-format", d["format"], "format only"), ("s-read", d["reading"], "reading errors"))
        said = ", ".join(f"{c} {t}" for _, c, t in parts)
        segments = ""
        for kind, count, name in parts:
            if count:
                shown = fact(f"diag.{config}.{who}.{name}", count) if count / d["wrong"] >= 0.07 else ""
                segments += f'<b class="{kind}" style="flex:{count} 1 0" title="{count} {name}">{shown}</b>'
        out += f'<div class="cause-r"><span>{label}: {fact(f"diag.{config}.{who}.wrong", d["wrong"])}</span><div class="seg" role="img" aria-label="{esc(said)}">{segments}</div></div>'
    return out + "</div>"


def real_scans(r: dict, diag: dict, fixed: dict, names: dict[str, str]) -> str:
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
  <div class="scans">
    <div class="card">
      <h3>Official result</h3>
      <table class="res"><thead><tr><th>Cells</th><th>Single read wrong</th><th>Archivist wrong among accepted</th><th>Wrong values caught</th><th>Hypothesis</th></tr></thead><tbody>{rows}</tbody></table>
    </div>
    {second}
  </div>
  <h3 style="margin-top:44px">What the diagnosis found</h3>
  <p class="sec-lede" style="margin-top:6px">Why the scores came out as they did: the wrong values counted by cause, from the committed records. It changes no score.</p>
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


def replay_panel(rp: dict) -> str:
    f, page, steps, rule = rp["field"], rp["page"], rp["steps"], rp["rule"]
    who = {k: v["model"] for k, v in steps.items()}

    def row(key: str, title: str, detail: str, outcome: str | None = None) -> str:
        model = who[key]
        chips = f'<span class="chip model">{fact("model", model)}</span>' if model else '<span class="chip code">Plain code</span>'
        if outcome:
            chips += f' <span class="chip done">{esc(outcome)}</span>'
        kind = "result" if outcome else ("model" if model else "code")
        return f'<li data-kind="{kind}"><span class="dot"></span><span class="t">{esc(title)} {chips}</span><p class="d">{detail}</p></li>'

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
        row("recognise", "Sort the page", f"Recognised as a table of {fact('replay.type', rp['title'])}."),
        row("read", "Read and cite", f"Read {value} in “{fact('replay.column', rp['column'])}”, row “{fact('replay.period', rp['period'])}”, and boxed where it saw it."),
        row("snap", "Snap to the ink", f"{snapped} {fitted}"),
        row("sam", "Look for covered ink", covered),
        row("blind", "Read again, blind", f"Shown only a crop of the cell, never the first answer, it read {reread}: it agrees."),
        row("rules", "Check the arithmetic", f"{esc(rule['label'])} Row {fact('replay.row', f['row'])}: <span class=\"mono\">{fact('replay.sum', equation)}</span>: it holds."),
        row("decide", "Decide", "Both reads agree and the rule holds, so the value is accepted.", outcome="Accepted"),
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
    return f"""<aside class="replay rise" style="--i:3" data-replay aria-label="One recorded decision, replayed">
    <div class="rp-h"><i aria-hidden="true"></i><span>{heading}</span></div>
    <figure class="rp-crop">{figure}<figcaption>{caption}</figcaption></figure>
    <ol class="rp-log">{"".join(log)}</ol>
    <p class="rp-count">On this page: <b>{fact("replay.accepted", decide["accepted"])}</b> values accepted, <b>{fact("replay.review", decide["review"])}</b> sent to a person, of <b>{fact("replay.read", read)}</b> read.</p>
    <div class="rp-ctl"><button class="btn small" type="button" data-act="replay">Replay</button><button class="btn small" type="button" data-act="pause">Pause</button></div>
  </aside>"""


STEPS = (
    ("model", "Sort the page", "glimmer", "Untrained, it picks the table type from the page’s text; a plain-code title check confirms it."),
    ("model", "Read and cite", "spark", "Reads every value and boxes where it saw it."),
    ("code", "Snap to the ink", None, "Plain code fits each box to the printed figure."),
    ("model", "Find covered ink", "sam", "Looks for stamps and stains over a value."),
    ("model", "Read again, blind", "spark", "Re-reads each value from a small crop, never seeing the first answer."),
    ("code", "Check the arithmetic", None, "Plain code tests rules a person approved: running balances, totals that must add up."),
    ("code", "Decide", None, "Accepted only if both reads agree and every rule holds."),
)


def how_it_works(names: dict[str, str]) -> str:
    who = {
        "glimmer": fact("model", names["muse-glimmer"]),
        "spark": f"{fact('model', names['muse-spark-1.3'])} or {fact('model', names['muse-spark-open'])}",
        "sam": fact("model", names["sam-3.1"]),
        None: "Plain code",
    }
    cards = ""
    for i, (kind, title, model, text) in enumerate(STEPS, start=1):
        cards += f'<li class="step {kind}"><span class="n" data-ok="step">{i}</span><h3>{esc(title)}</h3><span class="who">{who[model]}</span><p>{esc(text)}</p></li>'
    return f"""<section id="how" class="reveal"><div class="wrap">
  <p class="kicker">Seven steps</p>
  <h2>How it works</h2>
  <p class="sec-lede">A value is accepted only when independent checks agree. No model grades its own work, and Archivist never changes a value: it proposes a correction with its evidence, and a person decides.</p>
  <ul class="legend"><li><i class="k-model"></i>A Meta model</li><li><i class="k-code"></i>Plain code</li><li><i class="k-person"></i>A result, or a person</li></ul>
  <ol class="steps">{cards}<li class="step person outcome"><span class="lab">Accepted</span><h3>Verified database</h3><span class="lab">In doubt</span><h3>A person reviews</h3></li></ol>
</div></section>"""


PLAN_TITLES = {
    "synthetic": ("The synthetic test", "Ledger cards and payment memos, one run of each configuration."),
    "real": ("Real Treasury scans", "Held-out Treasury Bulletin pages, read through Meta’s API."),
    "openw": ("Open weights on the real scans", "The same pages and answer key, read by Muse Spark Open."),
}


def planned(git: dict, plan_list: list[dict]) -> str:
    cards = ""
    for p in plan_list:
        title, what = PLAN_TITLES[p["name"]]
        items = ""
        last = len(p["events"]) - 1
        for i, (event, sha, stamp) in enumerate(p["events"]):
            key = f"plan.{p['name']}.{i}"
            code = f" <code>{fact(key + '.sha', sha)}</code>" if sha else ""
            gap = f'<span class="gap">{fact("plan." + p["name"] + ".gap", apart(*p["gap"]))} after the plan was registered</span>' if i == last else ""
            items += f'<li class="{"run" if i else ""}"><span class="ev">{esc(event)}{code}</span><span class="when">{fact(key + ".when", clock(stamp))}</span>{gap}</li>'
        cards += f'<article class="card plan"><h3>{esc(title)}</h3><p class="what">{esc(what)}</p><ol>{items}</ol><p class="fine" style="margin:14px 0 0">{link(blob(p["file"]), "<code>" + esc(p["file"]) + "</code>")}</p></article>'
    first = git["first_commit"]
    return f"""<section id="planned" class="reveal"><div class="wrap">
  <p class="kicker">Read from git</p>
  <h2>Planned before the data</h2>
  <p class="sec-lede">Each plan was committed before the runs it governs, with its hypotheses, its scorer and its targets, so a result cannot be tuned afterwards. The dates are the committer’s clock from git, not a third-party timestamp. The first commit is <code>{fact("plan.first.sha", first["sha"])}</code>, {fact("plan.first.when", clock(first["date"]))}.</p>
  <div class="plans">{cards}</div>
</div></section>"""


def hardware(s: dict, r: dict, names: dict[str, str]) -> str:
    a, b = s["a"], s["b"]
    ow, v1 = r["ow"]["kept/as_run"]["overall"], r["v1"]["kept/as_run"]["overall"]
    rows = (
        ("Wrong among accepted, synthetic test", "hw.wrong", pct(a["error_rate_accepted"]), pct(b["error_rate_accepted"]), ""),
        ("Wrong values caught", "hw.caught", pct(a["catch_rate"]), pct(b["catch_rate"]), ""),
        ("Sent to a person", "hw.review", pct(a["review_rate"]), pct(b["review_rate"]), ""),
        ("Wrong among accepted, real scans", "hw.real", pct(v1["archivist_error"]["value"], 1), pct(ow["archivist_error"]["value"], 1), "every labelled cell"),
        ("Cost a page", "hw.cost", f"${s['cost']['a']:.4f}", f"${s['cost']['b']:.4f}", "hosted at the hackathon’s discount"),
    )
    body = ""
    for label, key, hosted, open_weights, note in rows:
        small = f"<small>{esc(note)}</small>" if note else ""
        body += f"<tr><td>{esc(label)}{small}</td><td>{fact(key + '.hosted', hosted)}</td><td>{fact(key + '.open', open_weights)}</td></tr>"
    spark, open_, sam = (fact("model", names[k]) for k in ("muse-spark-1.3", "muse-spark-open", "sam-3.1"))
    target = fact("hw.target", threshold(r["o1"]["threshold"]))
    return f"""<section id="hardware" class="reveal"><div class="wrap">
  <p class="kicker">One scheme, one swap</p>
  <h2>On your own hardware</h2>
  <p class="sec-lede">{open_} is a model whose trained weights are published. It can replace {spark} for both reads, so a bank that cannot send documents out can run the reading on its own machines.</p>
  <div class="hw">
    <div class="card"><table class="cmp"><thead><tr><th></th><th>Hosted<br><span class="mono">{spark}</span></th><th>Open weights<br><span class="mono">{open_}</span></th></tr></thead><tbody>{body}</tbody></table></div>
    <ul class="pts">
      <li><b>Not yet proven on-site.</b> No measured run kept a page on a bank’s own machines: {open_} ran on Baseten, and {sam} still used Meta’s API.</li>
      <li><b>On the real scans it missed its own target</b> of under {target} wrong among accepted: {fact("hw.o1", pct(r["o1"]["value"], 1))}.</li>
      <li><b>The same seven steps.</b> Only the two reads change; the arithmetic, the blind second read and the person do not.</li>
    </ul>
  </div>
</div></section>"""


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
    <div class="card"><h3>The repository</h3><p>The code, the plans, every result and the reasons for each decision.</p>{link(REPO, "kamil-shirinov/Archivist", ' class="btn" rel="noopener"')}</div>
  </div>
</div></section>"""


TOP = """<header class="top"><div class="wrap">
  <a class="brand" href="#top"><img class="only-light" src="assets/brand/logo-light.svg" alt="" width="26" height="26"><img class="only-dark" src="assets/brand/logo-dark.svg" alt="" width="26" height="26"><span>Archivist</span></a>
  <nav class="nav" aria-label="On this page"><a href="#how">How it works</a><a href="#planned">Planned first</a><a href="#scans">Real scans</a><a href="#hardware">Your hardware</a><a href="#limits">Limits</a><a href="#try">Try it</a></nav>
  <div class="top-r"><a class="btn small" href="ui/#replay">Watch it work</a>
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
<link rel="stylesheet" href="docs/landing/landing.css">
<script>try{var t=localStorage.getItem("archivist-theme");if(t)document.documentElement.dataset.theme=t}catch(e){}document.documentElement.classList.add("js");if(!matchMedia("(prefers-reduced-motion: reduce)").matches)document.documentElement.classList.add("play")</script>
<noscript><style>.rp-log li,.rp-count,.layer,.reveal{opacity:1!important;transform:none!important;stroke-dashoffset:0!important}</style></noscript>
<script src="docs/landing/landing.js" defer></script>
</head>
<body>
<a class="skip" href="#main">Skip to the page</a>
"""


def render(root: Path = ROOT) -> str:
    """The landing page, as one HTML document."""
    names = models(root)
    git = proof(root)
    s = synthetic(root)
    s["commit"] = git["registration"]["sha"]
    r = real_scores(root)
    rp = replay(root)
    footer = (
        f'<footer class="foot"><div class="wrap"><p>Archivist, built for the Meta Global AI Developer Hackathon from {fact("foot.first", day(git["first_commit"]["date"]))}. '
        f'The code is published for review, all rights reserved ({link(blob("LICENSE"), "LICENSE")}). Pages are from FRASER, the St. Louis Fed’s archive, or synthetic. '
        f'The type is Geist, under the SIL Open Font License ({link("ui/fonts/GEIST-OFL.txt", "licence", "")}).</p></div></footer>'
    )
    body = [
        TOP,
        '<main id="main">',
        hero(names, replay_panel(rp)),
        numbers(s),
        how_it_works(names),
        planned(git, plans(git, s, r)),
        real_scans(r, diagnosis(root), corrected(root), names),
        hardware(s, r, names),
        limits(s, r),
        try_it(docker_commands(root)),
        "</main>",
        footer,
        "</body>\n</html>\n",
    ]
    return HEAD + "\n".join(body)


if __name__ == "__main__":
    sys.stdout.write(render())
