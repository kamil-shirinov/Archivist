"""The held-out scoring, as PREREGISTRATION_REAL.md and its Deviations fix it, once labelled.

It runs only on the code tagged run-real-treasury, never on main: the command is run from a
checkout of the tag (a detached git worktree with its own environment, built from the tag's
uv.lock), so `import archivist`, config/ and templates/ are the tag's, and labelling/ (this file,
which is not frozen) comes from the main checkout by PYTHONPATH. Before anything is read it checks
that the archivist it imported lives in a checkout whose HEAD is the tag's commit, that the tag's
own frozen() passes there, and that it is run from that checkout; otherwise it refuses.

    git worktree add --detach <wt> run-real-treasury && (cd <wt> && uv sync --frozen)
    cd <wt> && PYTHONPATH=<main> .venv/bin/python -m labelling.score --data <main>

It reads the records, labels, page images and cache under <main> and writes
results/real_test/held_out/score/ there, once. No model is called: SAM's detections and the
re-reads' cache keys are recomputed with the tag's own functions and read from the cache, and a
missing cache entry is an error, never a call.

- A read is right when it equals the label under the template's comparison
  (TemplateType.canonical). "Row not on the page" and "column not on this page" are wrong for the
  single read, and for Archivist wherever it accepted the cell (Deviations). Can't read, and a
  cell the first read abstained on, are outside every error rate and counted.
- Weights: a labelled cell's family pages over its family's deep-check pages, times its stratum's
  cells over its stratum's sampled cells; a deep-check cell's, the first factor alone. The
  family's pages are the pages that count (POPULATION): since the title check the deep check
  draws from them (Deviations), so they make the weight the inverse of a cell's chance of being
  labelled.
- Every rate is a ratio of weighted sums. Intervals: 2,000 resamples, numpy.random.default_rng(0),
  pages resampled with replacement within each stratum (strata in name order, pages in id order,
  each page keeping its cells and weights); Wilson 95% for the relabelled cells and the checked
  pages.
- Both ways, as Deviations commits: the 40 changed-layout pages' cells left out or kept
  (LAYOUTS); and the cells whose re-read went unanswered and was asked again (3,322 + 32 keys),
  as run or sent to review as failed re-reads (REREADS).
- Also: coverage by page and by family (rows and figure cells the read did not return or left
  empty), the identities on changed-layout pages against the others, template drift on the
  total-claims pages, the Revisions page, the pages set aside, SAM's detections, how cells were
  boxed, the relabel agreement and the classification check (each "pending" until done).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import archivist
from archivist.pipeline import extract
from archivist.schema import PageExtraction, VerdictRecord
from archivist.templates import real_test
from labelling.draw import DRAW_FILE, STRATA, by_family, cells_of, parts
from labelling.serve import FILES, LAYOUT_ANSWERS, LAYOUT_RECORD, answers

SIDE = "held_out"
OUT = "score"
RESAMPLES = 2000
SEED = 0
Z = 1.959963984540054  # the standard normal's 97.5th percentile
POPULATION = "confirmed"
LAYOUTS = ("left_out", "kept")
REREADS = ("as_run", "failed_to_review")
UNANSWERED = ("unanswered_rereads.jsonl", "unanswered_rereads_2.jsonl")
WRONG_LABELS = ("not_on_page", "column_not_on_page")
OUTCOMES = ("right", "wrong", "cant_read", "abstained")
STRATUM_OF = {family: name for name, families in STRATA.items() for family in families}

# The both-ways set, fixed in Deviations before any verdict was written; recomputed from the
# layout records and compared, so records that disagree stop the scoring.
BOTH_WAYS = frozenset(
    f"{issue}_p{page}"
    for issue, pages in {
        "1940-04": ("055", "059"),
        "1940-06": ("063", "069"),
        "1940-07": ("031",),
        "1940-08": ("024",),
        "1940-10": ("023", "059", "062"),
        "1940-11": ("051", "060"),
        "1940-12": ("024", "059"),
        "1941-01": ("022", "058"),
        "1941-02": ("024", "058"),
        "1941-03": ("056", "069"),
        "1941-04": ("019", "058", "059", "063", "068"),
        "1941-05": ("021", "062"),
        "1941-06": ("023", "065"),
        "1941-07": ("071", "074"),
        "1941-08": ("065", "069", "074"),
        "1941-09": ("065", "075"),
        "1941-10": ("086", "087", "092"),
        "1942-01": ("025",),
        "1942-03": ("090",),
    }.items()
    for page in pages
)
REVISIONS = "1941-03_p069"
DRIFT_FAMILY = "total_claims_by_country"
IRELAND = ("1989-06_p099", "1990-06_p103", "1991-06_p107", "1993-06_p097", "1994-06_p099")
NO_GDR_FROM = "1993"  # the first issue without a German Democratic Republic row
GDR_ROW = "german_democratic_republic"
EUROPE_RULE = f"{DRIFT_FAMILY}.total_europe"


class NotFrozen(RuntimeError):
    pass


# --- Provenance ---------------------------------------------------------------------------------


def provenance(data: Path, git: Callable[..., subprocess.CompletedProcess] | None = None) -> dict:
    """Refuses unless archivist was imported from a checkout of the tag, the tag's own frozen()
    passes there and the command runs from it; returns what the score records of it."""
    code = Path(archivist.__file__).resolve().parents[2]

    def run(*args: str) -> subprocess.CompletedProcess:
        command = ["git", "-C", str(code), *args]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    git = git or run
    tag = git("rev-parse", "-q", "--verify", f"{real_test.TAG}^{{commit}}").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    if not tag or head != tag:
        raise NotFrozen(f"archivist is imported from a checkout at {head or '?'}, not {real_test.TAG}")
    try:
        real_test.frozen(git)
    except real_test.NotFrozen as error:
        raise NotFrozen(str(error)) from error
    if Path.cwd().resolve() != code:
        raise NotFrozen("run it from the tag's checkout, so config/ and templates/ are the tag's")
    command = ["git", "-C", str(data), "rev-parse", "HEAD"]
    records = subprocess.run(command, capture_output=True, text=True, check=False).stdout.strip()
    return {
        "tag": real_test.TAG,
        "commit": tag,
        "archivist_from_tag_checkout": True,
        "frozen_check": "passed",
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "records_commit": records,
    }


# --- Statistics ---------------------------------------------------------------------------------

# A rate's contribution of one unit: (numerator, denominator), so a rate is a ratio of sums.
Part = Callable[[object], tuple[float, float]]


def ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def wilson(successes: int, n: int, z: float = Z) -> tuple[float, float] | None:
    """The Wilson 95% interval of a proportion; None for no trials."""
    if n == 0:
        return None
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def stratified_ci(
    sums: Mapping[str, np.ndarray], n: int = RESAMPLES, seed: int = SEED
) -> tuple[float, float] | None:
    """95% percentile interval of a ratio of sums from resampling pages with replacement within
    each stratum. sums maps a stratum to its pages' (numerator, denominator) rows, in page-id
    order; strata are taken in name order. Resamples with a zero denominator are dropped; None if
    every one has."""
    strata = [sums[name] for name in sorted(sums) if len(sums[name])]
    if not strata:
        return None
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n):
        total = np.zeros(2)
        for rows in strata:
            total += rows[rng.integers(0, len(rows), size=len(rows))].sum(axis=0)
        if total[1] != 0:
            values.append(total[0] / total[1])
    if not values:
        return None
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def estimate[T](units: Sequence[T], parts_of: Mapping[str, Callable[[T], tuple[float, float]]]):
    """Each rate's value and interval over units, which carry .stratum and .page."""
    pages: dict[str, dict[str, list[T]]] = defaultdict(lambda: defaultdict(list))
    for unit in units:
        pages[unit.stratum][unit.page].append(unit)
    out = {}
    for name, part in parts_of.items():
        sums = {
            stratum: np.array(
                [np.sum([part(u) for u in by_page[p]], axis=0) for p in sorted(by_page)], dtype=float
            ).reshape(-1, 2)
            for stratum, by_page in pages.items()
        }
        total = np.sum([part(u) for u in units], axis=0) if units else np.zeros(2)
        out[name] = {"value": ratio(float(total[0]), float(total[1])), "ci": stratified_ci(sums)}
    return out


# --- The labelled cells -------------------------------------------------------------------------


@dataclass(frozen=True)
class Scored:
    """A labelled cell: its first read judged against its first label."""

    cell: str
    stratum: str
    family: str
    page: str
    weight: float
    choice: str
    outcome: str  # right, wrong, cant_read or abstained
    status: str  # Archivist's v2 status, as run
    unanswered: bool  # its re-read went unanswered and was asked again
    both_ways: bool


def judged(field_id: str, choice: str, label: str | None, read: str | None, canonical) -> str:
    """right or wrong where the label judges the read; cant_read or abstained where it is outside
    the error rates."""
    if choice == "cant_read":
        return "cant_read"
    if read is None:
        return "abstained"
    if choice in WRONG_LABELS:
        return "wrong"
    truth = label if choice == "value" else ""
    return "right" if canonical(field_id, read) == canonical(field_id, truth or "") else "wrong"


def accepted(status: str, unanswered: bool, rereads: str) -> bool:
    """Accepted under the variant: with failed_to_review, a cell whose re-read went unanswered
    goes to review, as a failed re-read does."""
    return status == "accepted" and not (rereads == "failed_to_review" and unanswered)


def label_parts(rereads: str) -> dict[str, Callable[[Scored], tuple[float, float]]]:
    """R1's two error rates and the catch rate."""

    def given(c: Scored) -> bool:
        return c.outcome in ("right", "wrong")

    def took(c: Scored) -> bool:
        return given(c) and accepted(c.status, c.unanswered, rereads)

    def wrong(c: Scored) -> bool:
        return c.outcome == "wrong"

    return {
        "single_read_error": lambda c: (c.weight * wrong(c), c.weight * given(c)),
        "archivist_error": lambda c: (c.weight * (took(c) and wrong(c)), c.weight * took(c)),
        "catch_rate": lambda c: (c.weight * (wrong(c) and not took(c)), c.weight * wrong(c)),
    }


def family_weights(families: Mapping[str, Mapping[str, int]]) -> dict[str, float]:
    """Each family's pages that count over its deep-check pages."""
    return {f: c[POPULATION] / c["deep_pages"] for f, c in families.items() if c["deep_pages"]}


def cell_weights(draw: Mapping) -> dict[str, float]:
    """Each sampled cell's weight, the inverse of its chance of being labelled."""
    family = family_weights(draw["families"])
    strata = {n: s["cells"] / s["sampled"] for n, s in draw["strata"].items() if s["sampled"]}
    return {s["cell"]: family[s["family"]] * strata[s["stratum"]] for s in draw["sample"]}


def r1(overall: Mapping[str, Mapping]) -> dict:
    """Met when Archivist's interval lies wholly below the single read's."""
    mine, single = overall["archivist_error"]["ci"], overall["single_read_error"]["ci"]
    met = mine is not None and single is not None and mine[1] < single[0]
    return {"met": met, "archivist_ci": mine, "single_read_ci": single}


def counted(cells: Sequence[Scored]) -> dict:
    return {
        "cells": len(cells),
        "pages": len({c.page for c in cells}),
        "by_choice": dict(sorted(Counter(c.choice for c in cells).items())),
        "by_outcome": {o: sum(c.outcome == o for c in cells) for o in OUTCOMES},
    }


def label_results(cells: Sequence[Scored]) -> dict:
    """Every variant: the rates overall and by stratum, R1, and what was counted."""
    out = {}
    for layout in LAYOUTS:
        kept = [c for c in cells if layout == "kept" or not c.both_ways]
        for rereads in REREADS:
            overall = estimate(kept, label_parts(rereads))
            out[f"{layout}/{rereads}"] = {
                **counted(kept),
                "overall": overall,
                "r1": r1(overall),
                "by_stratum": {
                    name: estimate([c for c in kept if c.stratum == name], label_parts(rereads))
                    | {"counted": counted([c for c in kept if c.stratum == name])}
                    for name in STRATA
                },
            }
    return out


# --- Every deep-check cell ----------------------------------------------------------------------


@dataclass(frozen=True)
class Judged:
    """A deep-check cell's verdict, for the rates over every cell."""

    field_id: str
    family: str
    stratum: str
    page: str
    weight: float
    status: str
    unanswered: bool
    both_ways: bool
    source: str | None  # its box's source; None where boxes.jsonl has none for it


def population_parts(rereads: str) -> dict[str, Callable[[Judged], tuple[float, float]]]:
    """The review rate and the share of cells boxed from each source."""

    def review(u: Judged) -> tuple[float, float]:
        sent = u.status == "review" or (u.status == "accepted" and not accepted(u.status, u.unanswered, rereads))
        return u.weight * sent, u.weight

    def boxed(source: str) -> Callable[[Judged], tuple[float, float]]:
        return lambda u: (u.weight * (u.source == source), u.weight * (u.source is not None))

    return {"review_rate": review, **{f"boxed_{s}": boxed(s) for s in ("ocr", "grid", "model")}}


def population_results(units: Sequence[Judged]) -> dict:
    out = {}
    for layout in LAYOUTS:
        kept = [u for u in units if layout == "kept" or not u.both_ways]
        for rereads in REREADS:
            parts_of = population_parts(rereads)
            out[f"{layout}/{rereads}"] = {
                "cells": len(kept),
                "overall": estimate(kept, parts_of),
                "by_family": {
                    family: estimate(mine, parts_of) | {"cells": len(mine)}
                    for family in real_test.FAMILIES
                    if (mine := [u for u in kept if u.family == family])
                },
            }
    return out


# --- What else the results report ---------------------------------------------------------------


def both_ways(layout_record: Mapping, marks: Mapping[str, Mapping]) -> set[str]:
    """The changed-layout pages: changed or a different table by the OCR check (one of them, by
    its record, settled by eye), or marked changed or different table by eye."""
    found = {
        page["page"]
        for page in layout_record["pages"]
        if page["ocr"].startswith(("changed", "a different table")) or "; changed" in page["ocr"]
    }
    return found | {p for p, mark in marks.items() if mark["layout"] in ("changed", "different_table")}


def relabel_agreement(draw: Mapping, first: Mapping, second: Mapping, canonical) -> dict:
    """The relabelled cells' two labels: the same choice and, for a printed value, the same under
    the template's comparison."""
    wanted = draw["relabel"]
    done = [c for c in wanted if c in second]
    if len(done) < len(wanted):
        return {"status": "pending", "relabelled": len(done), "of": len(wanted)}
    agree = 0
    for cell in wanted:
        a, b = first[cell], second[cell]
        same = a["choice"] == b["choice"] and (
            a["choice"] != "value" or canonical(cell, a["value"]) == canonical(cell, b["value"])
        )
        agree += same
    return {"status": "done", "agree": agree, "of": len(wanted), "wilson": wilson(agree, len(wanted))}


def precision(draw: Mapping, checked: Mapping[str, Mapping]) -> dict:
    """The classification check: pages that print the table of the family they were given."""
    wanted = [p["page"] for p in draw["pages_checked"]]
    done = [p for p in wanted if p in checked]
    if len(done) < len(wanted):
        return {"status": "pending", "checked": len(done), "of": len(wanted)}
    right = sum(checked[p]["verdict"] == "right" for p in wanted)
    return {
        "status": "done",
        "right": right,
        "of": len(wanted),
        "wilson": wilson(right, len(wanted)),
        "wrong_pages": sorted(p for p in wanted if checked[p]["verdict"] != "right"),
    }


def _outcome(doc_type, instance, texts: Mapping[str, str | None]) -> str:
    if instance.unresolved is not None or (found := doc_type.evaluate(instance, texts)) is None:
        return "unchecked"
    left, right, tolerance = found
    return "held" if abs(left - right) <= tolerance else "failed"


def _texts(pages: Iterable[PageExtraction]) -> dict[str, str | None]:
    return {v.field_id: None if v.abstained else v.value for p in pages for v in p.values}


def identities(doc_types: Mapping, pages: Sequence[PageExtraction], changed: set[str]) -> dict:
    """Each identity's instances on the in-context values that held, failed or could not be
    checked, on changed-layout pages and on the others."""
    texts = _texts(pages)
    tally: dict[str, dict[str, Counter]] = defaultdict(
        lambda: {"changed_layout": Counter(), "other": Counter()}
    )
    for family in sorted({p.doc_type for p in pages}):
        doc_type = doc_types[family]
        for instance in doc_type.instances(list(pages)):
            group = "changed_layout" if parts(instance.own_field())[1] in changed else "other"
            tally[instance.rule][group][_outcome(doc_type, instance, texts)] += 1
    keys = ("held", "failed", "unchecked")
    return {
        rule: {group: {k: counts[k] for k in keys} for group, counts in groups.items()}
        for rule, groups in sorted(tally.items())
    }


def drift(
    doc_type, pages: Sequence[PageExtraction], verdicts: Sequence[VerdictRecord], scored: Sequence[Scored]
) -> dict:
    """Template drift on total claims (Deviations), page by page: the pages printing an Ireland
    row, which Total Europe includes and the rule does not list, and those without a German
    Democratic Republic row, with the cells and flags affected on each."""
    own = sorted(p.page_id for p in pages if p.doc_type == DRIFT_FAMILY)
    missing = sorted(set(IRELAND) - set(own))
    if missing:
        raise ValueError(f"pages printing an Ireland row are not in the deep check: {missing}")
    gone = [p for p in own if p >= NO_GDR_FROM]
    texts = _texts(pages)
    europe: dict[str, Counter] = defaultdict(Counter)
    for instance in doc_type.instances(list(pages)):
        if instance.rule == EUROPE_RULE:
            europe[parts(instance.own_field())[1]][_outcome(doc_type, instance, texts)] += 1
    out = {}
    for page in sorted(set(IRELAND) | set(gone)):
        mine = [v for v in verdicts if v.page_id == page]
        flagged = [v for v in mine if any(doc_type.rule(f) == EUROPE_RULE for f in v.flags)]
        record = {
            "prints_ireland_row": page in IRELAND,
            "prints_gdr_row": page not in gone,
            "total_europe": {k: europe[page][k] for k in ("held", "failed", "unchecked")},
            "cells_flagged_by_total_europe": len(flagged),
            "flagged_by_status": dict(sorted(Counter(v.status for v in flagged).items())),
            "labelled_cells": {o: sum(c.page == page and c.outcome == o for c in scored) for o in OUTCOMES},
        }
        if page in gone:
            gdr = [
                v
                for v in mine
                if parts(v.field_id)[2] == GDR_ROW and parts(v.field_id)[3] in doc_type.money_fields
            ]
            read = [v for v in gdr if (v.value or "").strip()]
            labelled = [c for c in scored if c.page == page and parts(c.cell)[2] == GDR_ROW]
            record |= {
                "gdr_figure_cells": len(gdr),
                "gdr_figure_cells_read": len(read),
                "gdr_read_by_status": dict(sorted(Counter(v.status for v in read).items())),
                "gdr_read_flags": sum(len(v.flags) for v in read),
                "gdr_labelled_cells": {o: sum(c.outcome == o for c in labelled) for o in OUTCOMES},
            }
        out[page] = record
    return out


def revisions(verdicts: Sequence[VerdictRecord], scored: Sequence[Scored]) -> dict:
    """The Revisions page, which both the classifier and the title check wrongly confirmed."""
    mine = [v for v in verdicts if v.page_id == REVISIONS]
    return {
        "page": REVISIONS,
        "family": "security_transactions_as_reported_by",
        "what": (
            "a different table (Revisions – Security Transactions …), confirmed by both the "
            "classifier and the title check, which accepts any page whose title contains the "
            "family's approved title: a weakness of the title check"
        ),
        "in_both_ways_set": REVISIONS in BOTH_WAYS,
        "cells": len(mine),
        "by_status": dict(sorted(Counter(v.status for v in mine).items())),
        "labelled_cells": {o: sum(c.page == REVISIONS and c.outcome == o for c in scored) for o in OUTCOMES},
    }


def sam(verdicts: Sequence[VerdictRecord], detections: Mapping[str, Mapping[str, int]]) -> dict:
    """SAM's detections on the deep-check pages, by prompt, and the cells it marked occluded, by
    the occluding region's label."""
    occluded = [v for v in verdicts if v.evidence.occluded_by]
    prompts = sorted({prompt for counts in detections.values() for prompt in counts})
    return {
        "pages": len(detections),
        "pages_with_a_detection": sum(any(c.values()) for c in detections.values()),
        "by_prompt": {
            prompt: {
                "pages_with_a_detection": sum(bool(c.get(prompt)) for c in detections.values()),
                "detections": sum(c.get(prompt, 0) for c in detections.values()),
            }
            for prompt in prompts
        },
        "cells_occluded": len(occluded),
        "cells_occluded_by_label": dict(
            sorted(Counter(label for v in occluded for label in {o.label for o in v.evidence.occluded_by}).items())
        ),
    }


def sweep_summary(sweep: Mapping) -> dict:
    return {
        "pages": sweep["pages"],
        "classified": sweep["classified"],
        "failed": len(sweep["failed"]),
        "by_family": sweep["by_family"],
        "set_aside_by_classifier": sweep["set_aside_by_classifier"],
        "set_aside_by_title_check": sweep["type_unconfirmed"],
        "by_era": sweep["by_era"],
    }


# --- Reading the records, with the tag's functions ----------------------------------------------


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def reread_keys(pages, doc_types, llm, root: Path) -> dict[str, set[str]]:
    """The cache keys of each re-read verify asks, and of its retry, mapped to the cells asking
    it; as results/real_test/held_out/procedure/reread_keys.py computes them."""
    from PIL import Image

    from archivist.models import LLMRequest
    from archivist.models.cache import cache_key
    from archivist.pipeline import reread, verify

    cells: dict[str, set[str]] = defaultdict(set)
    for page in pages:
        image = Image.open(io.BytesIO(real_test.resolve(page.page_id, SIDE, root).path.read_bytes()))
        plugin = doc_types[page.doc_type]
        for value in page.values:
            if value.citation is None or not verify.needs_reread(value):
                continue
            picture = reread.crop(image, reread.region(value.citation))
            prompt = plugin.reread_prompt(value.field_id)
            for attempt in (prompt, prompt + reread.RETRY_NOTE):
                request = LLMRequest(
                    role=reread.ROLE,
                    prompt=attempt,
                    images=(picture,),
                    json_schema=reread.SCHEMA,
                    max_output_tokens=reread.REREAD_TOKENS,
                )
                cells[cache_key(llm.name, llm.model_id, request, llm.settings)].add(value.field_id)
    return cells


def detections(pages, segmenter, root: Path, cache: Path) -> dict[str, dict[str, int]]:
    """Each page's SAM detections by prompt, read from the cache entries verify's calls left."""
    from archivist.models import SegmentRequest
    from archivist.models.cache import cache_key
    from archivist.pipeline import occlusion

    found = {}
    for page in pages:
        image = real_test.resolve(page.page_id, SIDE, root).path.read_bytes()
        found[page.page_id] = {}
        for prompt in occlusion.PROMPTS:
            request = SegmentRequest(role=occlusion.ROLE, image=image, prompts=(prompt,))
            key = cache_key(segmenter.name, segmenter.model_id, request, segmenter.settings)
            entry = cache / key[:2] / f"{key}.json"
            if not entry.exists():
                raise FileNotFoundError(f"no cache entry for SAM's {prompt!r} on {page.page_id}")
            found[page.page_id][prompt] = len(json.loads(entry.read_text())["regions"])
    return found


def score(data: Path) -> dict:
    """Everything the results report, from the records under data, on the tag's code."""
    from archivist.models import load_roles

    records = data / real_test.OUT_DIR / SIDE
    labels_dir = records / "labels"
    draw = json.loads((labels_dir / DRAW_FILE).read_text(encoding="utf-8"))
    first = answers(labels_dir / FILES["first"], "cell")
    unlabelled = [s["cell"] for s in draw["sample"] if s["cell"] not in first]
    if unlabelled:
        raise ValueError(f"{len(unlabelled)} of {len(draw['sample'])} cells have no first label")

    layout_record = json.loads((records / LAYOUT_RECORD).read_text(encoding="utf-8"))
    changed = both_ways(layout_record, answers(labels_dir / LAYOUT_ANSWERS, "page"))
    if changed != BOTH_WAYS:
        raise ValueError(f"the layout records give another both-ways set: {sorted(changed ^ BOTH_WAYS)}")

    doc_types = real_test._types(real_test.CONFIG)
    pages = sorted(extract.load_predictions(records / "predictions.jsonl"), key=lambda p: p.page_id)
    reads = {v.field_id: v for p in pages for v in p.values}
    verdicts = [VerdictRecord.model_validate_json(line) for line in (records / "verdicts.jsonl").open()]
    for v in verdicts:
        read = reads[v.field_id]
        if v.value != (None if read.abstained else read.value):
            raise ValueError(f"{v.field_id}: the verdict's value is not the first read's")
    status = {v.field_id: v.status for v in verdicts}

    strata, coverage = cells_of(pages, doc_types)
    if coverage != draw["coverage_by_page"] or any(
        len(strata[n]) != s["cells"] for n, s in draw["strata"].items()
    ):
        raise ValueError("the first read's coverage differs from the draw's")

    roles = load_roles(real_test.CONFIG, cache_dir=data / "cache")
    root = data / real_test.DEFAULT_ROOT
    keys = reread_keys(pages, doc_types, roles["rereader"], root)
    lists = {name: [line["key"] for line in _lines(records / name)] for name in UNANSWERED}
    strays = [k for found in lists.values() for k in found if k not in keys]
    if strays:
        raise ValueError(f"{len(strays)} unanswered keys match no re-read of the deep check")
    unanswered = {cell for found in lists.values() for k in found for cell in keys[k]}

    canonical = {f: doc_types[f].canonical for f in real_test.FAMILIES}
    weights = cell_weights(draw)
    scored = []
    for s in draw["sample"]:
        cell, label = s["cell"], first[s["cell"]]
        read = reads[cell]
        scored.append(
            Scored(
                cell=cell,
                stratum=s["stratum"],
                family=s["family"],
                page=s["page"],
                weight=weights[cell],
                choice=label["choice"],
                outcome=judged(
                    cell,
                    label["choice"],
                    label["value"],
                    None if read.abstained else read.value,
                    canonical[s["family"]],
                ),
                status=status[cell],
                unanswered=cell in unanswered,
                both_ways=s["page"] in BOTH_WAYS,
            )
        )
    family_weight = family_weights(draw["families"])
    sources = {
        field: source for line in _lines(records / "boxes.jsonl") for field, source in line["box_sources"].items()
    }
    units = [
        Judged(
            field_id=v.field_id,
            family=v.doc_type,
            stratum=STRATUM_OF[v.doc_type],
            page=v.page_id,
            weight=family_weight[v.doc_type],
            status=v.status,
            unanswered=v.field_id in unanswered,
            both_ways=v.page_id in BOTH_WAYS,
            source=sources.get(v.field_id),
        )
        for v in verdicts
    ]
    second = answers(labels_dir / FILES["relabel"], "cell")
    checked = answers(labels_dir / FILES["check"], "page")
    sweep = json.loads((records / "sweep.json").read_text(encoding="utf-8"))

    def canonical_of(cell: str, text: str) -> str:
        return canonical[parts(cell)[0]](cell, text)

    return {
        "weights": {
            "population": POPULATION,
            "families": draw["families"],
            "family_weights": family_weight,
            "strata": draw["strata"],
        },
        "both_ways_pages": sorted(BOTH_WAYS),
        "labels": label_results(scored),
        "every_cell": population_results(units),
        "unanswered_rereads": {
            "keys": {name: len(found) for name, found in lists.items()},
            "cells": len(unanswered),
            "accepted_as_run": sum(status[c] == "accepted" for c in unanswered),
            "sampled_cells": sum(c.unanswered for c in scored),
            "sampled_accepted_as_run": sum(c.unanswered and c.status == "accepted" for c in scored),
        },
        "coverage_by_page": coverage,
        "coverage_by_family": by_family(coverage),
        "identities": identities(doc_types, pages, BOTH_WAYS),
        "template_drift": drift(doc_types[DRIFT_FAMILY], pages, verdicts, scored),
        "revisions_page": revisions(verdicts, scored),
        "sweep": sweep_summary(sweep),
        "sam": sam(verdicts, detections(pages, roles["segmenter"], root, data / "cache")),
        "relabel": relabel_agreement(draw, first, second, canonical_of),
        "classification_check": precision(draw, checked),
    }


# --- The report ---------------------------------------------------------------------------------


def _pct(estimate: Mapping) -> str:
    value, ci = estimate["value"], estimate["ci"]
    if value is None:
        return "—"
    shown = f"{value:.1%}"
    return shown if ci is None else f"{shown} ({ci[0]:.1%}–{ci[1]:.1%})"


def render(record: Mapping) -> str:
    """score.md: the record's tables, every variant side by side; score.json has everything."""
    lines = [
        "# Held-out scoring — Treasury Bulletin (PREREGISTRATION_REAL.md)",
        "",
        f"Code: `{record['provenance']['tag']}` ({record['provenance']['commit'][:7]}), checked "
        f"frozen; scorer sha256 `{record['provenance']['scorer_sha256'][:12]}`. Weights' page "
        f"counts: {record['weights']['population']}. Intervals: 95%, page bootstrap within strata "
        "(rates) or Wilson (counts).",
        "",
        "## Labelled cells",
        "",
        "| Variant | Cells | Single read error | Archivist error (accepted) | Catch rate | R1 |",
        "|---|--:|---|---|---|---|",
    ]
    for name, result in record["labels"].items():
        o = result["overall"]
        lines.append(
            f"| {name} | {result['cells']} | {_pct(o['single_read_error'])} | "
            f"{_pct(o['archivist_error'])} | {_pct(o['catch_rate'])} | "
            f"{'met' if result['r1']['met'] else 'not met'} |"
        )
    lines += ["", "By stratum:", "", "| Variant | Stratum | Single read error | Archivist error | Catch rate |"]
    lines.append("|---|---|---|---|---|")
    for name, result in record["labels"].items():
        for stratum, o in result["by_stratum"].items():
            lines.append(
                f"| {name} | {stratum} | {_pct(o['single_read_error'])} | "
                f"{_pct(o['archivist_error'])} | {_pct(o['catch_rate'])} |"
            )
    lines += ["", "Labels and outcomes (variant: by choice; by outcome):", ""]
    for name, result in record["labels"].items():
        lines.append(f"- {name}: {result['by_choice']}; {result['by_outcome']}")
    lines += [
        "",
        "## Every deep-check cell",
        "",
        "| Variant | Cells | Review rate | Boxed OCR | Boxed grid | Boxed model |",
        "|---|--:|---|---|---|---|",
    ]
    for name, result in record["every_cell"].items():
        o = result["overall"]
        lines.append(
            f"| {name} | {result['cells']} | {_pct(o['review_rate'])} | {_pct(o['boxed_ocr'])} | "
            f"{_pct(o['boxed_grid'])} | {_pct(o['boxed_model'])} |"
        )
    kept = record["every_cell"]["kept/as_run"]["by_family"]
    lines += ["", "By family (kept/as_run):", "", "| Family | Cells | Review rate | OCR | Grid | Model |"]
    lines.append("|---|--:|---|---|---|---|")
    for family, o in kept.items():
        lines.append(
            f"| {family} | {o['cells']} | {_pct(o['review_rate'])} | {_pct(o['boxed_ocr'])} | "
            f"{_pct(o['boxed_grid'])} | {_pct(o['boxed_model'])} |"
        )
    u = record["unanswered_rereads"]
    lines += [
        "",
        "## Re-reads asked again",
        "",
        f"Keys {u['keys']}; {u['cells']} cells ({u['accepted_as_run']} accepted as run); "
        f"{u['sampled_cells']} labelled ({u['sampled_accepted_as_run']} accepted as run).",
        "",
        "## Coverage by page",
        "",
        "| Page | Family | Rows | Not returned | Left empty | Figure cells | Not returned | Left empty |",
        "|---|---|--:|--:|--:|--:|--:|--:|",
    ]
    for page, c in record["coverage_by_page"].items():
        lines.append(
            f"| {page} | {c['family']} | {c['rows']} | {c['rows_not_returned']} | "
            f"{c['rows_left_empty']} | {c['figure_cells']} | {c['figure_cells_not_returned']} | "
            f"{c['figure_cells_left_empty']} |"
        )
    lines += ["", "By family:", "", "| Family | Pages | Rows | Not returned | Left empty | Figure cells | Not returned | Left empty |"]
    lines.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for family, c in record["coverage_by_family"].items():
        lines.append(
            f"| {family} | {c['pages']} | {c['rows']} | {c['rows_not_returned']} | "
            f"{c['rows_left_empty']} | {c['figure_cells']} | {c['figure_cells_not_returned']} | "
            f"{c['figure_cells_left_empty']} |"
        )
    lines += ["", "## Identities, changed-layout pages against the others", ""]
    lines += ["| Identity | Changed: held / failed / unchecked | Other: held / failed / unchecked |", "|---|---|---|"]
    for rule, groups in record["identities"].items():
        cells = [f"{g['held']} / {g['failed']} / {g['unchecked']}" for g in groups.values()]
        lines.append(f"| {rule} | {cells[0]} | {cells[1]} |")
    lines += ["", "## Template drift (total claims)", ""]
    for page, d in record["template_drift"].items():
        lines.append(f"- {page}: {json.dumps(d)}")
    r = record["revisions_page"]
    lines += ["", "## The Revisions page", "", f"{r['page']}: {r['what']}. {json.dumps({k: r[k] for k in ('cells', 'by_status', 'labelled_cells')})}"]
    lines += ["", "## Pages set aside (sweep)", "", f"```\n{json.dumps(record['sweep'], indent=2)}\n```"]
    lines += ["", "## SAM's detections", "", f"```\n{json.dumps(record['sam'], indent=2)}\n```"]
    lines += ["", "## Relabel agreement", "", f"`{json.dumps(record['relabel'])}`"]
    lines += ["", "## Classification check", "", f"`{json.dumps(record['classification_check'])}`", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--data", type=Path, required=True, help="the main checkout, with the records")
    args = parser.parse_args(argv)
    data = args.data.resolve()
    origin = provenance(data)
    out = data / real_test.OUT_DIR / SIDE / OUT
    if out.exists():
        parser.error(f"{out} exists: the held-out side is scored once")
    record = {"provenance": origin, **score(data)}
    out.mkdir(parents=True)
    (out / "score.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "score.md").write_text(render(record), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
