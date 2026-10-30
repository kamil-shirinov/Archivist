"""Approve a drafted template, identity by identity: a person's decision, never a program's (P21b).

    python -m archivist.templates.approve --family <name>

Interactive. Reads <dir>/<family>.yaml (default templates/), which must be a draft, and its
evidence, <family>.evidence.json from archivist.templates.test, which must have been made from
this very draft (its sha256). It shows the template, the pages it was tested on, and each identity
with its evidence: where it applies, how often it held, why it wasn't evaluated where it wasn't,
and every failure with the cells and both reads. A column the draft reads a blank in as zero
(blank_means) is accepted as drafted or set back to unknown by the person, before the identities,
whose evidence was made with it. An identity the test rejected (it never held) is dropped without
asking; every other is accepted or dropped by the person, with a reason for a drop. The person
then says who they are, as it will be published, and confirms.

Only then is the file rewritten: status "approved", approved_by, approved_on (today), the evidence
file's sha256, the identities dropped (by whom, and why), and a note for each column set back to
unknown; the identities accepted stay as they were drafted. Nothing is written if the person
stops. The template is registered from then on, but no run enables it until a run config names
it ([doc_types] enabled). A table printed in panels (P21d) is approved panel by panel: each
panel's columns, then its identities, named "<panel>.<id>" as its evidence names them.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

from archivist.doctypes.template import (
    TEMPLATES_DIR,
    Column,
    Dropped,
    Identity,
    Layout,
    Template,
    evidence_path,
    file_sha256,
    read_template,
)
from archivist.templates.draft import to_yaml


class NotApproved(RuntimeError):
    pass


def _identity_text(item: dict) -> list[str]:
    where = item["for_each"] if item["over"] is None else f"{item['for_each']}s {item['over']}"
    rate = "-" if item["hold_rate"] is None else f"{item['hold_rate']:.1%}"
    lines = [
        f"identity {item['id']}: {item['description']}",
        f"  {item['equation']}, for each {where}",
        f"  test: {item['outcome']}; held {item['held']} of {item['evaluated']} evaluated "
        f"({rate}), at {item['applies']} places",
    ]
    lines += [f"  not evaluated, {n}: {reason}" for reason, n in item["not_evaluated"].items()]
    for failure in item["failures"]:
        lines.append(
            f"  FAILED on {failure['page']}, {failure['where']}: left {failure['left']}, right "
            f"{failure['right']}, off by {failure['difference']} (tolerance {failure['tolerance']})"
        )
        lines += [
            f"    {c['side']:<5} {c['sign']} {c['row']}/{c['column']}: read {c['read']!r}, "
            f"re-read {c['reread']!r}"
            for c in failure["cells"]
        ]
    return lines


def _tables(template: Template) -> list[tuple[str, Layout, list[Identity]]]:
    """(how its identities are named, its layout, its identities): the table, or each panel."""
    if template.panels is None:
        return [("", template.layout, template.identities)]
    return [(f"{p.key}.", p.layout, p.identities) for p in template.panels]


def _summary(template: Template, evidence: dict) -> list[str]:
    lines = [
        f"{template.family}: {template.identity.title}",
        f"  description: {template.identity.description}",
        f"  title patterns: {template.identity.title_patterns}",
    ]
    for panel in template.panels or ():
        copies = f", printed up to {panel.repeats} times a page" if panel.repeats > 1 else ""
        lines.append(f"  panel {panel.key}: {panel.title}{copies}")
    for prefix, layout, _ in _tables(template):
        lines.append(
            f"  {prefix}{layout.unit}, printed to {layout.precision}; {len(layout.row_keys)} rows, "
            "columns "
            + ", ".join(
                f"{c.key} ({c.kind}{', a blank is zero' if c.blank_means == 'zero' else ''})"
                for c in layout.columns
            )
        )
    lines += [
        f"  drafted by {template.provenance.drafted_by.id} on {template.provenance.drafted_on} "
        f"from {', '.join(template.provenance.drafted_from)}",
        f"  tested on {evidence['tested_on']} with {evidence['config']}",
    ]
    for page in evidence["pages"]:
        if page["read"] != "ok":
            lines.append(f"  page {page['ref']}: the read {page['read']}")
            continue
        lines.append(
            f"  page {page['ref']}: classified {page['classified_as']}; {page['cells']} cells, "
            f"{page['read_twice']} needed cells read twice, {page['agree']} agree"
        )
    return lines


def _choose(ask: Callable[[str], str], question: str, options: dict[str, str]) -> str:
    while True:
        answer = ask(question).strip().lower()
        if answer in options:
            return options[answer]


def approve(
    family: str,
    *,
    directory: Path = TEMPLATES_DIR,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
    today: date | None = None,
) -> Path:
    """Ask the person about each identity, then write the approved template; raises NotApproved
    if the template or its evidence can't be approved, or the person stops."""
    path = directory / f"{family}.yaml"
    template = read_template(path)
    if template.provenance.status != "draft":
        raise NotApproved(f"{path} is {template.provenance.status!r}: only a draft is approved")
    evidence_file = evidence_path(path)
    if not evidence_file.is_file():
        raise NotApproved(f"{evidence_file} is missing: run archivist.templates.test first")
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    if evidence.get("template_sha256") != file_sha256(path):
        raise NotApproved(f"{evidence_file} is not this draft's: rerun archivist.templates.test")
    tables = _tables(template)
    items = {item["id"]: item for item in evidence["identities"]}
    if list(items) != [prefix + i.id for prefix, _, ids in tables for i in ids]:
        raise NotApproved(f"{evidence_file} does not cover this draft's identities")

    for line in _summary(template, evidence):
        say(line)
    columns: list[list[Column]] = []
    unknown: list[str] = []
    for prefix, layout, _ in tables:
        columns.append([])
        for column in layout.columns:
            if column.blank_means == "zero":
                say("")
                say(
                    f"column {prefix}{column.key} ({column.printed!r}): a blank cell counts as 0 "
                    "in identities"
                )
                question = "  [a]ccept, or [u]nknown (a blank leaves an identity unchecked)? "
                if _choose(ask, question, {"a": "zero", "u": "unknown"}) == "unknown":
                    column = column.model_copy(update={"blank_means": "unknown"})
                    unknown.append(prefix + column.key)
            columns[-1].append(column)
    kept: list[list[Identity]] = []
    dropped = []
    for prefix, _, identities in tables:
        kept.append([])
        for identity in identities:
            name = prefix + identity.id
            item = items[name]
            say("")
            for line in _identity_text(item):
                say(line)
            if item["outcome"] == "rejected":
                why = f"never held: failed all {item['failed']} times it was evaluated"
                say(f"  dropped by the arithmetic test: {why}")
                dropped.append(Dropped(id=name, by="arithmetic test", why=why))
                continue
            choice = _choose(ask, "  [a]ccept or [d]rop? ", {"a": "accept", "d": "drop"})
            if choice == "accept":
                kept[-1].append(identity)
                continue
            why = ask("  why? ").strip() or "dropped by the approver"
            dropped.append(Dropped(id=name, by="approver", why=why))

    say("")
    say(f"{sum(map(len, kept))} identities accepted, {len(dropped)} dropped.")
    while True:
        who = ask("Approved by (as it will be published in a public repository; no email): ")
        who = " ".join(who.split())
        if who and "@" not in who:
            break
        say("  a name or a role, without an email address")
    if _choose(ask, f"Write {path} as approved by {who}? [y/n] ", {"y": True, "n": False}) is False:
        raise NotApproved("stopped: nothing was written")

    today = today or date.today()
    digest = file_sha256(evidence_file)
    notes = [
        *template.provenance.evidence,
        f"{evidence_file.as_posix()}: the arithmetic test of {evidence['tested_on']} on "
        + ", ".join(p["ref"] for p in evidence["pages"]),
        *(
            f"approver: a blank in column {key!r} is unknown, not zero as drafted and tested"
            for key in unknown
        ),
    ]
    provenance = template.provenance.model_copy(
        update={
            "status": "approved",
            "approved_by": who,
            "approved_on": today,
            "evidence": notes,
            "evidence_sha256": digest,
            "dropped": dropped,
        }
    )
    if template.panels is None:
        approved = Template.model_validate(
            {
                **template.model_dump(exclude_none=True),
                "layout": template.layout.model_copy(update={"columns": columns[0]}).model_dump(
                    exclude_none=True
                ),
                "identities": [i.model_dump(exclude_none=True) for i in kept[0]],
                "provenance": provenance.model_dump(exclude_none=True),
            }
        )
    else:
        panels = [
            panel.model_copy(
                update={
                    "layout": panel.layout.model_copy(update={"columns": own_columns}),
                    "identities": own,
                }
            ).model_dump(exclude_none=True)
            for panel, own_columns, own in zip(template.panels, columns, kept, strict=True)
        ]
        approved = Template.model_validate(
            {
                **template.model_dump(exclude_none=True, exclude={"identities"}),
                "panels": panels,
                "provenance": provenance.model_dump(exclude_none=True),
            }
        )
    drafted = template.provenance
    header = (
        f"Drafted by {drafted.drafted_by.id} from {', '.join(drafted.drafted_from)} on "
        f"{drafted.drafted_on} (P21b).\n"
        f"Approved by {who} on {today.isoformat()}, identity by identity, on the evidence in\n"
        f"{evidence_file.name} (sha256 {digest}).\n"
        "Registered, but no run enables it until a run config names it ([doc_types] enabled)."
    )
    path.write_text(to_yaml(approved, header), encoding="utf-8")
    read_template(path)  # and the evidence file is still the one it was approved on
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--family", required=True)
    parser.add_argument("--dir", type=Path, default=TEMPLATES_DIR)
    args = parser.parse_args(argv)
    try:
        path = approve(args.family, directory=args.dir)
    except NotApproved as error:
        raise SystemExit(str(error)) from error
    print(f"{path} approved. Enable it in a new run's config to use it: [doc_types] enabled.")


if __name__ == "__main__":
    main()
