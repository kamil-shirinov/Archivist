"""Every template family's committed evidence, recounted under the all-blank rule (P26).

    python -m archivist.templates.recount [--workers 8]

An identity instance whose cells are all blanks counted as zero reads 0 = 0, which holds whatever
the table says; until P26 the arithmetic test counted it as held. This recounts the evidence of
every family that had any when the rule changed (BEFORE), the approved ones included, and never
writes an evidence file: an approval is tied to its evidence file's sha256.

For each family:

1. The template it was tested on, by the sha256 its evidence records: a version of the file in git
   up to BEFORE, or one with its approval undone (the draft as draft.py writes it; only an approval
   that dropped nothing and set no column back can be undone). A family whose tested template
   can't be found is reported, not recounted. A template with no column where a blank counts as
   zero can have no all-blank instance, so the rule cannot change its counts.
2. Its reads replayed from the cache alone, both spend caps zero, so a miss stops that family: the
   evidence's pages and box strategy through test.read_pages, under today's code, twice. First with
   figures read as before P26 (figures_before_p26), so the all-blank rule is the only change: its
   pages' records must equal the committed ones, and each identity's held count may fall only by
   the instances now all blank, with nothing else changed ("explained"). Then under every P26 rule,
   which also reads a space after a thousands comma through ("29, 139"), so more reads agree; the
   counts that changes are reported apart, with how many reads printed such a space.
3. The accepted identities of an approved template left with no pass under either are listed.

Writes results/templates/recount.md; spends nothing.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path

import yaml
from pydantic import ValidationError

from archivist.doctypes import template as template_module
from archivist.doctypes.template import SPACED, TEMPLATES_DIR, Template, TemplateType
from archivist.models import BudgetExceeded, describe_config, load_roles
from archivist.models.budget import BACKEND_CAPS
from archivist.pipeline import reread
from archivist.templates.draft import CONFIG, to_yaml
from archivist.templates.pages import resolve
from archivist.schema import PageExtraction
from archivist.templates.test import BLANK, DISAGREE, EMPTY, ONCE, needed, read_pages, tally

BEFORE = "2364d02"  # the last commit before P26: the evidence as it was counted
OUT = Path("results/templates/recount.md")
COUNTS = ("applies", "evaluated", "held", "failed", "outcome")
PASSES = ("rule", "p26")  # the all-blank rule alone; every P26 rule
SHORT = {DISAGREE: "reads disagree", ONCE: "not read twice", BLANK: "blank", EMPTY: "all blank"}


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def _sha256(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def _parse(text: bytes) -> Template | None:
    try:
        return Template.model_validate(yaml.safe_load(text))
    except (yaml.YAMLError, ValidationError):
        return None  # a version from before the template language could say it


@contextlib.contextmanager
def figures_before_p26() -> Iterator[None]:
    """Template figures read as before P26, a space after a thousands comma not read through."""
    spaced = template_module.SPACED
    template_module.SPACED = re.compile(r"(?!)")  # matches nothing
    try:
        yield
    finally:
        template_module.SPACED = spaced


def committed_evidence() -> dict[str, dict]:
    """Each family's evidence file as it was at BEFORE."""
    names = _git("ls-tree", "--name-only", BEFORE, f"{TEMPLATES_DIR.as_posix()}/").decode()
    return {
        Path(name).name.removesuffix(".evidence.json"): json.loads(_git("show", f"{BEFORE}:{name}"))
        for name in names.split()
        if name.endswith(".evidence.json")
    }


def undo_approval(template: Template) -> bytes | None:
    """The draft an approval was made from, as draft.py wrote it; None if the approval dropped an
    identity or set a column back, which can't be undone from the approved file."""
    p = template.provenance
    if not p.approved or p.dropped or any(n.startswith("approver: ") for n in p.evidence):
        return None
    evidence = f"{template.family}.evidence.json"  # the approval's note: "<its path>: the test of"
    notes = [n for n in p.evidence if not n.split(": ", 1)[0].endswith(evidence)]
    provenance = p.model_dump(
        exclude_none=True, exclude={"approved_by", "approved_on", "evidence_sha256", "dropped"}
    ) | {"status": "draft", "evidence": notes}
    draft = Template.model_validate(
        template.model_dump(exclude_none=True) | {"provenance": provenance}
    )
    header = (  # draft.draft's
        f"Drafted by {p.drafted_by.id} from {', '.join(p.drafted_from)} on "
        f"{p.drafted_on.isoformat()} (P21b).\n"
        "A draft: validated, never registered. python -m archivist.templates.test checks its\n"
        "identities; only a person, with python -m archivist.templates.approve, approves it."
    )
    return to_yaml(draft, header).encode("utf-8")


def tested_template(family: str, sha256: str) -> tuple[Template, str] | None:
    """The template the evidence was made on, and where it was found."""
    path = f"{TEMPLATES_DIR.as_posix()}/{family}.yaml"
    for commit in _git("log", "--format=%h", BEFORE, "--", path).decode().split():
        text = _git("show", f"{commit}:{path}")
        if (template := _parse(text)) is None:
            continue
        if _sha256(text) == sha256:
            return template, f"the file at {commit}"
        undone = undo_approval(template)
        if undone is not None and _sha256(undone) == sha256:
            return _parse(undone), f"the file at {commit}, its approval undone"
    return None


def _changed(old: Mapping, new: Mapping) -> dict:
    return {k: (old[k], new[k]) for k in (*COUNTS, "not_evaluated") if old[k] != new[k]}


def _explained(old: Mapping, new: Mapping, differ: Mapping[str, dict]) -> str:
    """"yes" if the held count fell by exactly the instances now all blank and nothing else
    changed; also if the rest moved only on pages not replayed as committed whose first reads are
    all blank, where nothing could have held but an all-blank instance."""
    rest = {k: v for k, v in new["not_evaluated"].items() if k != EMPTY}
    held = (
        old["held"] == new["held"] + new["not_evaluated"].get(EMPTY, 0)
        and old["failed"] == new["failed"]
        and old["applies"] == new["applies"]
    )
    if held and old["not_evaluated"] == rest:
        return "yes"
    if held and differ and all(page["blank"] for page in differ.values()):
        return f"yes; the rest moved on {', '.join(differ)}, whose first reads are all blank"
    return "**no**"


def _shared(doc_type: TemplateType, page: PageExtraction) -> dict:
    """Of the page's re-read cells, how many ask the very request another does (the same crop
    with the same prompt), and whether every first read on the page is blank."""
    requests = Counter(
        (repr(reread.region(v.citation)), doc_type.reread_prompt(v.field_id))
        for v in page.values
        if v.field_id in needed(doc_type, page) and v.citation is not None and v.value is not None
    )
    return {
        "reread": sum(requests.values()),
        "shared": sum(n for n in requests.values() if n > 1),
        "blank": all(not (v.value or "").strip() for v in page.values),
    }


def recount_family(family: str, evidence: Mapping, roles: Mapping, workers: int) -> dict:
    found = tested_template(family, evidence["template_sha256"])
    if found is None:
        return {"family": family, "problem": "the template it was tested on is not found"}
    template, source = found
    current = Template.model_validate(
        yaml.safe_load((TEMPLATES_DIR / f"{family}.yaml").read_bytes())
    )
    approved = current.provenance.approved
    out: dict = {
        "family": family,
        "approved": approved,
        "accepted": [i.id for i in current.identities] if approved else [],
        "tested_template": source,
        "zero_columns": [c.key for c in template.layout.columns if c.blank_means == "zero"],
    }
    doc_type = TemplateType(template, sha256=evidence["template_sha256"])
    pages = [resolve(page["ref"]) for page in evidence["pages"]]
    passes = {}
    for name, reading in zip(PASSES, (figures_before_p26, contextlib.nullcontext), strict=True):
        with reading():
            try:
                extracted, seconds, records = read_pages(
                    doc_type, pages, roles, workers, evidence["citations"]
                )
            except BudgetExceeded as error:
                return out | {"problem": f"a read is not in the cache: {error}"[:200]}
            identities = tally(doc_type, extracted, seconds)
        replayed = json.loads(json.dumps(records))
        differ = [
            new["ref"] for old, new in zip(evidence["pages"], replayed, strict=True) if old != new
        ]
        passes[name] = {"pages_differ": differ, "identities": identities}
        if name == "rule":
            out["pages_differ"] = {
                page.page_id: _shared(doc_type, page)
                for page in extracted
                if page.page_id in differ
            }
    out["spaced"] = sum(
        bool(text and SPACED.search(text))
        for page in extracted
        for text in [v.value for v in page.values]
        + [r.text for r in seconds[page.page_id].values()]
    )
    committed = {item["id"]: item for item in evidence["identities"]}
    out["identities"] = []
    for rule, p26 in zip(
        passes["rule"]["identities"], passes["p26"]["identities"], strict=True
    ):
        old = committed[rule["id"]]
        out["identities"].append(
            {
                "id": rule["id"],
                "old": old,
                "rule": rule,
                "p26": p26,
                "all_blank": rule["not_evaluated"].get(EMPTY, 0),
                "by_rule": _changed(old, rule),
                "explained": _explained(old, rule, out["pages_differ"]),
                "by_spacing": _changed(rule, p26),
            }
        )
    return out


def _count(item: Mapping) -> str:
    return f"{item['held']} / {item['failed']} / {item['evaluated']}"


def _arrow(old: Mapping, new: Mapping, key: str) -> str:
    return f"{old[key]} -> {new[key]}" if old[key] != new[key] else str(new[key])


def _reasons(old: Mapping, new: Mapping) -> str:
    """The not-evaluated counts that changed, by reason."""
    a, b = old["not_evaluated"], new["not_evaluated"]
    changed = [
        f"{SHORT[r]} {a.get(r, 0)} -> {b.get(r, 0)}" for r in SHORT if a.get(r, 0) != b.get(r, 0)
    ]
    return ", ".join(changed) or "-"


def _accepted(f: Mapping, identity: str) -> str:
    if not f["approved"]:
        return "draft"
    return "yes" if identity in f["accepted"] else "no"


def report(families: list[dict]) -> str:
    lines = [
        "# Recount: an all-blank instance proves nothing (P26)",
        "",
        "An identity instance whose cells are all blanks counted as zero reads 0 = 0, which holds "
        "whatever the table says. Until P26 the arithmetic test counted it as held; it is now "
        'not evaluated, "all blank". Every family\'s committed evidence (as at '
        f"{BEFORE}, the approved ones included) is recounted here from its reads, replayed from "
        "the cache with both spend caps at zero, through the template it was tested on. No "
        "evidence file is rewritten: an approval is tied to its evidence file's sha256. Written "
        "by `python -m archivist.templates.recount`.",
        "",
        "Each family is replayed twice. **The all-blank rule** reads figures as before P26, so "
        "the rule is the only change; its pages must replay exactly as committed, and a count "
        "is *explained* when the held count fell by exactly the instances now all blank and "
        "nothing else changed. **All of P26** also reads a space after a thousands comma "
        '("29, 139") as one figure, so more first and second reads agree; *spaced reads* is '
        "how many first or second reads printed such a space. Counts are held / failed / "
        "evaluated.",
        "",
        "## Families",
        "",
        "| family | status | tested template | columns where a blank is zero | replayed as "
        "committed | instances now all blank | changed by the rule | spaced reads | changed "
        "further by reading them |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in families:
        status = "approved" if f.get("approved") else "draft"
        zero = len(f.get("zero_columns", []))
        if "problem" in f:
            note = f["problem"]
            if "zero_columns" in f and not zero:
                note += "; no column counts a blank as zero, so no instance can be all blank"
            source = f.get("tested_template", "-")
            lines.append(f"| {f['family']} | {status} | {source} | {zero} | {note} | | | | |")
            continue
        identities = f["identities"]
        differ = ", ".join(f["pages_differ"])
        lines.append(
            f"| {f['family']} | {status} | {f['tested_template']} | {zero} | "
            f"{'all pages' if not differ else f'**not** {differ}'} | "
            f"{sum(i['all_blank'] for i in identities)} | "
            f"{sum(bool(i['by_rule']) for i in identities)} of {len(identities)} | "
            f"{f['spaced']} | {sum(bool(i['by_spacing']) for i in identities)} of "
            f"{len(identities)} |"
        )

    lines += [
        "",
        "## The all-blank rule: every count that changed",
        "",
        "| family | identity | accepted | applies | held / failed / evaluated | not evaluated | "
        "outcome | explained |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = [
        f"| {f['family']} | {i['id']} | {_accepted(f, i['id'])} | "
        f"{_arrow(i['old'], i['rule'], 'applies')} | {_count(i['old'])} -> {_count(i['rule'])} "
        f"| {_reasons(i['old'], i['rule'])} | {_arrow(i['old'], i['rule'], 'outcome')} | "
        f"{i['explained']} |"
        for f in families
        for i in f.get("identities", [])
        if i["by_rule"] or i["explained"] != "yes"
    ]
    lines += rows or ["| none | | | | | | | |"]
    notes = [
        f"- {f['family']}, {page_id}: {p['shared']} of its {p['reread']} re-read cells ask the "
        "very request another cell asks (the same crop with the same prompt). Before P26 "
        "identical requests made at once were each answered by the model while the cache kept "
        "one answer, so the committed reads of these cells need not be the cached ones; P26 "
        "answers them with one call (models/cache.py)."
        + (" Every first read on the page is blank." if p["blank"] else "")
        for f in families
        for page_id, p in f.get("pages_differ", {}).items()
    ]
    if notes:
        lines += ["", "Pages not replayed as committed under the all-blank rule:", "", *notes]

    no_pass = [
        (f, i)
        for f in families
        for i in f.get("identities", [])
        if i["id"] in f["accepted"] and min(i["rule"]["held"], i["p26"]["held"]) == 0
    ]
    lines += ["", "## Accepted identities left with no genuine pass", ""]
    if no_pass:
        lines += [
            "| family | identity | committed | the all-blank rule | all of P26 |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {f['family']} | {i['id']} | {_count(i['old'])} | {_count(i['rule'])} | "
            f"{_count(i['p26'])} |"
            for f, i in no_pass
        ]
    else:
        recounted = [f for f in families if f.get("approved") and "identities" in f]
        lines.append(
            f"None among the {sum(len(f['accepted']) for f in recounted)} accepted identities of "
            f"the {len(recounted)} approved families recounted: each still holds at least once "
            "under the all-blank rule, and under all of P26."
        )
    for f in families:
        if f.get("approved") and "problem" in f and not f.get("zero_columns", [None]):
            lines += [
                "",
                f"{f['family']} could not be recounted ({f['problem']}), but no column of the "
                "template it was tested on counts a blank as zero, so none of the passes of its "
                f"{len(f['accepted'])} accepted identities can have been all blank.",
            ]

    lines += [
        "",
        "## Reading spaced figures: every count that changed further",
        "",
        "| family | identity | accepted | held / failed / evaluated | not evaluated | outcome |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows = [
        f"| {f['family']} | {i['id']} | {_accepted(f, i['id'])} | "
        f"{_count(i['rule'])} -> {_count(i['p26'])} | {_reasons(i['rule'], i['p26'])} | "
        f"{_arrow(i['rule'], i['p26'], 'outcome')} |"
        for f in families
        for i in f.get("identities", [])
        if i["by_spacing"]
    ]
    lines += rows or ["| none | | | | | |"]

    lines += [
        "",
        "## Every identity",
        "",
        "| family | identity | committed | the all-blank rule | all blank | all of P26 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for f in families:
        for i in f.get("identities", []):
            lines.append(
                f"| {f['family']} | {i['id']} | {_count(i['old'])}, {i['old']['outcome']} | "
                f"{_count(i['rule'])}, {i['rule']['outcome']} | {i['all_blank']} | "
                f"{_count(i['p26'])}, {i['p26']['outcome']} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    for variable, _ in BACKEND_CAPS.values():
        os.environ[variable] = "0"  # any cache miss raises BudgetExceeded: nothing is spent
    roles = load_roles(CONFIG)
    families = []
    for family, evidence in committed_evidence().items():
        if evidence["config"] != describe_config(CONFIG):
            families.append({"family": family, "problem": f"tested with another config, {CONFIG}"})
            continue
        print(f"recounting {family}", flush=True)
        with contextlib.redirect_stdout(io.StringIO()):
            families.append(recount_family(family, evidence, roles, args.workers))
    OUT.write_text(report(families), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
