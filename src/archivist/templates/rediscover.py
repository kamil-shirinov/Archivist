"""Can the drafter find the rules our built-in types already check? A measurement (P21b).

    python -m archivist.templates.rediscover   # -> results/templates/rediscovery_v2.md

Drafts a template for ledger cards and one for payment memos, each from 3 synthetic val pages
(the val split, seed 2002; the 3 pages of each kind drawn with random.Random(2002) from the
sorted file names, card-* and memo-*), with the same prompt as any family: it never names a
document type of ours nor a rule of theirs. Each draft goes through the same arithmetic test as a
Treasury family, with the template types' box strategy. Drafts and evidence go to
results/templates/rediscovery_v2/, never templates/.

The first measurement, results/templates/rediscovery.md (3 dev pages of each kind, seed 1001,
before the template language could name the previous row), is kept as it was written; its drafts
in results/templates/rediscovery/ are judged here again by the same matcher, for comparison.

The drafted identities are then compared with the built-in checks (KNOWN, doctypes/ledger.py):
a drafted identity finds a known rule at each place it applies where its equation is that rule's
on the cells the printed headings name (debit, credit, balance; the brought and carried forward
rows; line n, or the n-th row of a table whose rows are read from the top). Every known rule is
listed, found or missed, with whether the template format can express it at all; every other
drafted identity is an extra, with whether it held. The
report is written whatever it shows.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from archivist.doctypes.template import (
    Template,
    TemplateType,
    evidence_path,
    file_sha256,
    read_template,
    written,
)
from archivist.models import describe_config, load_roles
from archivist.pipeline import extract
from archivist.schema import PageExtraction
from archivist.templates.draft import CONFIG, ROLE, draft
from archivist.templates.test import run_test

SPLIT, SEED = "val", 2002
PER_KIND = 3
MANIFEST = Path(f"data/{SPLIT}/manifest.json")
OUT_DIR = Path("results/templates/rediscovery_v2")
REPORT = Path("results/templates/rediscovery_v2.md")
FIRST_DIR = Path("results/templates/rediscovery")  # the first measurement: dev, seed 1001
FIRST_REPORT = Path("results/templates/rediscovery.md")
KINDS = {  # family -> (the document, the prefix of its file names)
    "rediscovery_cards": ("ledger card", "card-"),
    "rediscovery_memos": ("payment memo", "memo-"),
}


@dataclass(frozen=True)
class Known:
    id: str
    document: str
    rule: str
    expressible: str  # in the template format: "yes", or why not


KNOWN = (
    Known(
        "running_balance",
        "ledger card",
        "each line's balance is the one before (the brought forward on line 1), less its debit, "
        "plus its credit",
        "yes: for each row, with the balance of the previous row",
    ),
    Known(
        "carried_forward",
        "ledger card",
        "the carried forward is the last line's balance",
        "only for a full card: the last line used changes from card to card",
    ),
    Known(
        "one_side",
        "ledger card",
        "a line has a debit or a credit, not both or neither",
        "no: not an equation",
    ),
    Known(
        "dates_ascend",
        "ledger card",
        "dates never go backwards down the card",
        "no: an order, not an equation",
    ),
    Known(
        "cheques_ascend",
        "ledger card",
        "cheque numbers never go backwards down the card",
        "no: an order, not an equation",
    ),
    Known(
        "carry_across_sheets",
        "ledger card",
        "the next sheet of the account brings forward what this one carried forward",
        "no: across pages of one account, not tables of one issue",
    ),
    Known(
        "sequences_across_sheets",
        "ledger card",
        "dates and cheque numbers don't go backwards from one sheet to the next",
        "no: an order across pages",
    ),
    Known(
        "account_and_holder",
        "ledger card",
        "an account's sheets share its number and holder, in sheet order",
        "no: text across pages",
    ),
    Known(
        "words_figures",
        "payment memo",
        "the amount in words is the amount in figures",
        "no: words are text, and only figures enter an identity",
    ),
    Known(
        "memo_amount_posted",
        "payment memo",
        "the ledger line the memo cites debits the memo's amount",
        "no: across pages, found by the reference's sheet and line",
    ),
    Known(
        "memo_date_before_posting",
        "payment memo",
        "the memo is dated no later than its posting and at most 30 days before it",
        "no: an order across pages",
    ),
    Known(
        "memo_account",
        "payment memo",
        "the memo's account is the cited card's account",
        "no: text across pages",
    ),
)


def sample(manifest: Path = MANIFEST) -> dict[str, list[str]]:
    """The val pages each draft is made from, as page references."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data["seed"] != SEED:
        raise ValueError(f"{manifest} is seed {data['seed']}, not {SEED}")
    stems = sorted(Path(n).stem for n in data["files"] if n.startswith("images/"))
    rng = random.Random(SEED)
    drawn = {}
    for family, (_, prefix) in KINDS.items():
        kind = [s for s in stems if s.startswith(prefix)]
        drawn[family] = sorted(f"{SPLIT}/{s}" for s in rng.sample(kind, PER_KIND))
    return drawn


# --- Matching drafted identities to the known rules ---------------------------------------------


def _column_meaning(printed: str) -> str | None:
    text = printed.lower()
    for name in ("debit", "credit", "balance"):
        if name in text:
            return name
    return None


def _row_place(key: str, printed: str | None) -> int | str | None:
    """A row as a place on the card: 0 the brought forward, n line n, "cf" the carried forward."""
    text = f"{printed or ''} {key}".lower()
    if "brought" in text:
        return 0
    if "carried" in text:
        return "cf"
    digits = re.findall(r"\d+", printed if printed is not None else key)
    return int(digits[0]) if len(digits) == 1 else None


def meaning(template: Template) -> tuple[dict[str, str | None], dict[str, int | str | None]]:
    """What the printed headings say each column and row is."""
    columns = {c.key: _column_meaning(c.printed) for c in template.layout.columns}
    if isinstance(template.layout.rows, list):
        rows = {r.key: _row_place(r.key, r.printed) for r in template.layout.rows}
    else:  # read rows are numbered from the top: the n-th row is line n
        rows = {key: int(key) for key in template.layout.row_keys}
    return columns, rows


def _cells(instance_fields, columns, rows) -> dict[tuple[str, int | str], int] | None:
    out: dict[tuple[str, int | str], int] = {}
    for field_id, coef, *_ in instance_fields:
        *_, row, column = field_id.split(":")
        what, where = columns.get(column), rows.get(row)
        if what is None or where is None:
            return None
        if where == 0 and what != "balance":
            return None
        out[(what, where)] = out.get((what, where), 0) + coef
    return {k: v for k, v in out.items() if v}


def _is_running_balance(cells: Mapping[tuple[str, int | str], int]) -> bool:
    lines = [p for (_, p) in cells if isinstance(p, int) and p > 0]
    if not lines or len(cells) != 4:
        return False
    p = max(lines)
    s = cells.get(("balance", p))
    if s not in (1, -1):
        return False
    expected = {("balance", p): s, ("balance", p - 1): -s, ("debit", p): s, ("credit", p): -s}
    return dict(cells) == expected


def _is_carried_forward(cells: Mapping[tuple[str, int | str], int]) -> bool:
    if len(cells) != 2 or cells.get(("balance", "cf")) not in (1, -1):
        return False
    (other, coef), = [(k, v) for k, v in cells.items() if k != ("balance", "cf")]
    return other[0] == "balance" and isinstance(other[1], int) and coef == -cells[("balance", "cf")]


MATCHERS = {"running_balance": _is_running_balance, "carried_forward": _is_carried_forward}


@dataclass(frozen=True)
class Found:
    rule: str | None  # the known rule the identity is at most of its places, None if at none
    at: int  # how many of its places it is that rule
    of: int  # how many places it applies to


def match(doc_type: TemplateType) -> dict[str, Found]:
    """Each drafted identity's known rule: the one its equation is at the most places it applies
    (every row taken as used: a page with nothing read), with at how many of them."""
    template = doc_type.template
    columns, rows = meaning(template)
    found: dict[str, Counter] = {i.id: Counter() for i in template.identities}
    blank = PageExtraction(page_id="blank", doc_type=doc_type.name, values=[])
    for instance in doc_type.instances([blank]):
        cells = _cells(instance.fields, columns, rows)
        rule = None
        if cells is not None:
            rule = next((name for name, test in MATCHERS.items() if test(cells)), None)
        found[instance.rule.split(".", 1)[1]][rule] += 1
    out = {}
    for name, counts in found.items():
        known = [(n, r) for r, n in counts.most_common() if r is not None]
        rule, at = (known[0][1], known[0][0]) if known else (None, 0)
        out[name] = Found(rule, at, sum(counts.values()))
    return out


def _where(found: Found) -> str:
    return f"at {found.at} of {found.of} places" if found.at < found.of else "at every place"


# --- The report ----------------------------------------------------------------------------------


def _not_evaluated(item: Mapping) -> str:
    return "; ".join(f"{why} ({n})" for why, n in item["not_evaluated"].items()) or "-"


def report(
    results: Mapping[str, dict], config: Mapping[str, object], first: Mapping[str, dict]
) -> str:
    lines = [
        "# Rediscovery: can the drafter find the rules our built-in types check?",
        "",
        "Made by `python -m archivist.templates.rediscover`. A measurement, reported whatever it "
        "shows; the second, after the template language gained a cell of the previous row. The "
        "drafter (Muse Spark 1.3, the `drafter` role of `config/templates.toml`) was given "
        f"{PER_KIND} synthetic {SPLIT} pages of each kind ({SPLIT} split, seed {SEED}; pages "
        f"drawn with `random.Random({SEED})`) and the same prompt as every family, which "
        "describes what the template language can express and never names a document type of "
        "ours nor a rule of theirs. Each draft then went through the arithmetic test (read, "
        "cite, blind second read; identities evaluated on cells whose two reads agree), with the "
        "template types' box strategy.",
        "",
        f"The first measurement, `{FIRST_REPORT.as_posix()}` (dev split, seed 1001, before the "
        "previous row could be named), is kept as written; its drafts are judged again by the "
        "same matcher at the end.",
        "",
        "Matching, changed after this measurement's card draft was seen: a drafted identity finds "
        "a known rule at the places where its equation is that rule, and the report says at how "
        "many of the places it applies. Before, it had to be that rule at every place, and an "
        "identity that is the running balance on every line and something else on one more row "
        "counted as missed. Both measurements are judged by the changed matcher.",
        "",
        f"Config: `{json.dumps(dict(config))}`",
        "",
    ]
    for family, result in results.items():
        document, _ = KINDS[family]
        template, evidence, matched = result["template"], result["evidence"], result["matched"]
        items = {i["id"]: i for i in evidence["identities"]}
        lines += [
            f"## {document.capitalize()}s: `{family}`",
            "",
            f"Drafted from {', '.join(template.provenance.drafted_from)}: "
            f"\"{template.identity.title}\", {len(template.layout.row_keys)} rows "
            f"({'read' if not isinstance(template.layout.rows, list) else 'fixed'}) x "
            f"{len(template.layout.columns)} columns, {len(template.identities)} identities "
            f"kept at drafting. Files: `{result['path'].as_posix()}`, "
            f"`{evidence_path(result['path']).as_posix()}`. Boxes: {evidence['citations']}.",
            "",
        ]
        lines += [f"- {note}" for note in template.provenance.evidence if "left out" in note]
        lines += [
            "",
            "| Page | Classified as the draft | Read | Needed cells read twice | Agree |",
            "|---|---|---|--:|--:|",
            *(
                f"| {p['ref']} | {'yes' if p['classified_as'] == family else p['classified_as']} | "
                f"{p['read'] if p['read'] != 'ok' else 'ok'} | {p.get('read_twice', '-')} | "
                f"{p.get('agree', '-')} |"
                for p in evidence["pages"]
            ),
            "",
            "Known rules:",
            "",
            "| Known rule | Expressible as a template identity | Found by |",
            "|---|---|---|",
        ]
        for known in (k for k in KNOWN if k.document == document):
            by = [i for i, found in matched.items() if found.rule == known.id]
            lines.append(
                f"| `{known.id}`: {known.rule} | {known.expressible} | "
                + (", ".join(f"`{i}` ({_where(matched[i])})" for i in by) if by else "missed")
                + " |"
            )
        extras = [i for i in template.identities if matched[i.id].rule is None]
        lines += ["", f"Extra identities proposed ({len(extras)}):", ""]
        if extras:
            lines += [
                "| Identity | Equation | Test outcome | Held / evaluated | Not evaluated |",
                "|---|---|---|--:|---|",
                *(
                    f"| `{i.id}`: {i.description} | `{written(i)}` (for each {i.for_each}) | "
                    f"{items[i.id]['outcome']} | {items[i.id]['held']} / "
                    f"{items[i.id]['evaluated']} | {_not_evaluated(items[i.id])} |"
                    for i in extras
                ),
            ]
        found = [i for i in template.identities if matched[i.id].rule is not None]
        if found:
            lines += [
                "",
                "How the identities that found a known rule fared in the test:",
                "",
                "| Identity | Known rule | Test outcome | Held / evaluated | Not evaluated |",
                "|---|---|---|--:|---|",
                *(
                    f"| `{i.id}` | `{matched[i.id].rule}` ({_where(matched[i.id])}) | "
                    f"{items[i.id]['outcome']} | "
                    f"{items[i.id]['held']} / {items[i.id]['evaluated']} | "
                    f"{_not_evaluated(items[i.id])} |"
                    for i in found
                ),
            ]
        lines.append("")
    lines += [
        "## Both measurements, judged by the same matcher",
        "",
        "| Kind | Measurement | Identities kept | Known rules found | Extras |",
        "|---|---|--:|---|--:|",
    ]
    measurements = (("first (dev, 1001)", first), (f"second ({SPLIT}, {SEED})", results))
    for family, (document, _) in KINDS.items():
        for name, result in ((name, found.get(family)) for name, found in measurements):
            if result is None:
                lines.append(f"| {document} | {name} | no draft | | |")
                continue
            matched = result["matched"]
            known = sorted({f.rule for f in matched.values() if f.rule is not None})
            extras = sum(f.rule is None for f in matched.values())
            lines.append(
                f"| {document} | {name} | {len(matched)} | "
                f"{', '.join(f'`{k}`' for k in known) or 'none'} | {extras} |"
            )
    lines.append("")
    return "\n".join(lines)


def judged(path: Path) -> dict:
    """A rediscovery draft, its evidence, and the known rule each of its identities finds."""
    template = read_template(path)
    doc_type = TemplateType(template, sha256=file_sha256(path))
    evidence = json.loads(evidence_path(path).read_text(encoding="utf-8"))
    return {"path": path, "template": template, "evidence": evidence, "matched": match(doc_type)}


def first_measurement(directory: Path = FIRST_DIR) -> dict[str, dict]:
    """The first measurement's drafts, as they were written, judged by today's matcher."""
    paths = {family: directory / f"{family}.yaml" for family in KINDS}
    return {family: judged(path) for family, path in paths.items() if path.is_file()}


def rediscover(roles: Mapping[str, object], config: Mapping[str, object], workers: int) -> dict:
    results = {}
    for family, refs in sample().items():
        path = draft(family, refs, roles[ROLE], directory=OUT_DIR)
        run_test(family, roles, directory=OUT_DIR, config=config, workers=workers)
        results[family] = judged(path)
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    roles = load_roles(args.config)
    guard = roles[extract.ROLE].inner.guard
    before = guard.spent()
    config = describe_config(args.config)
    results = rediscover(roles, config, args.workers)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(results, config, first_measurement()), encoding="utf-8")
    print(f"wrote {REPORT}; ${guard.spent() - before:.4f} spent")


if __name__ == "__main__":
    main()
