"""A model drafts a template from a few page images (P21b).

    python -m archivist.templates.draft --family <name> --pages <id> <id> [<id>]

Sends 2-3 page images (pages.py decides which may be sent) to the drafter role of --config
(default config/templates.toml, Muse Spark 1.3), through archivist.models, so the call is cached
and budgeted. The prompt asks for a template in the P21a format: the table's title, a one-line
description and title patterns, its layout (unit, printed precision, fixed or read rows, columns
with their kinds) and every identity the model believes the printed figures satisfy, in the
template language as it stands (cells, including the previous row's, sums and differences). It
describes only what that language can express: it never names a document type of ours, a rule
of theirs, nor the family the draft is saved as. With --title, for pages that print more than one
table, it adds one sentence naming the printed title of the table to describe, and nothing else.

The answer is checked as a template is: the title, the patterns and the layout must validate, or
the model is asked once more with what was wrong; each identity is then checked on its own, and
one that doesn't validate against the layout is left out and noted in the provenance. A pattern
that doesn't compile is dropped; with none left, the title itself, spacing loosened, is the
pattern. The draft is written to <dir>/<family>.yaml with status "draft" and its provenance (the
model, the pages, the date). An approved template is never overwritten.

With --panels (P21d), for a table printed in panels, the prompt adds PANELS_NOTE and asks for the
table's panels in place of one layout: each panel's key, its heading, how many times a page prints
it at most, and its own layout and identities, checked as one table's are; an identity is left out
on its own, named "<panel>.<id>".
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from archivist.doctypes import REGISTRY, UNSUPPORTED
from archivist.doctypes.template import (
    KEY,
    NUMERIC,
    TEMPLATES_DIR,
    Family,
    Layout,
    Panel,
    Template,
    TemplateError,
    read_template,
)
from archivist.models import LLMRequest, VisionLLM, load_roles
from archivist.templates.pages import resolve

CONFIG = Path("config/templates.toml")
ROLE = "drafter"
DRAFT_TOKENS = 32_000
MIN_PAGES, MAX_PAGES = 2, 3

_NAME = {"type": "string"}
_NAMES = {"type": ["array", "null"], "items": _NAME}
_OPTIONAL = {"type": ["string", "null"]}
BLANK_MEANS = ["zero", "unknown", None]
_COUNT = {"type": "integer"}


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_CELL = _object(
    {
        "cell": _object(
            {
                "row": _OPTIONAL,
                "column": _OPTIONAL,
                "previous_row": {"type": ["boolean", "null"]},
                "section": _OPTIONAL,
            }
        )
    }
)
_SUM = _object(
    {
        "sum": _object(
            {
                "rows": _NAMES,
                "columns": _NAMES,
                "sections": _NAMES,
                "row": _OPTIONAL,
                "column": _OPTIONAL,
            }
        )
    }
)
_SIMPLE = {"anyOf": [_CELL, _SUM]}
_DIFFERENCE = _object(
    {"difference": {"type": "array", "items": _SIMPLE, "minItems": 2, "maxItems": 2}}
)
_EXPR = {"anyOf": [_CELL, _SUM, _DIFFERENCE]}
_LABEL = _object({"key": _NAME, "printed": _NAME})
SCHEMA = _object(
    {
        "identity": _object(
            {
                "title": _NAME,
                "description": _NAME,
                "title_patterns": {"type": "array", "items": _NAME},
            }
        ),
        "layout": _object(
            {
                "unit": _NAME,
                "precision": {"type": "string", "enum": ["1", "0.1", "0.01", "0.001"]},
                "rows": {
                    "anyOf": [
                        {"type": "array", "items": _LABEL},
                        _object({"read": {"type": "integer"}}),
                        _object(
                            {
                                "sections": {
                                    "type": "array",
                                    "items": _object(
                                        {"key": _NAME, "printed": _NAME, "read": _COUNT}
                                    ),
                                }
                            }
                        ),
                    ]
                },
                "columns": {
                    "type": "array",
                    "items": _object(
                        {
                            "key": _NAME,
                            "printed": _NAME,
                            "kind": {
                                "type": "string",
                                "enum": ["money", "count", "percent", "date", "text"],
                            },
                            "blank_means": {"type": ["string", "null"], "enum": BLANK_MEANS},
                        }
                    ),
                },
            }
        ),
        "identities": {
            "type": "array",
            "items": _object(
                {
                    "id": _NAME,
                    "description": _NAME,
                    "for_each": {
                        "type": "string",
                        "enum": ["table", "row", "column", "position"],
                    },
                    "over": _NAMES,
                    "left": _EXPR,
                    "right": _EXPR,
                }
            ),
        },
    }
)

PANELS_SCHEMA = _object(
    {
        "identity": SCHEMA["properties"]["identity"],
        "panels": {
            "type": "array",
            "items": _object(
                {
                    "key": _NAME,
                    "title": _NAME,
                    "repeats": _COUNT,
                    "layout": SCHEMA["properties"]["layout"],
                    "identities": SCHEMA["properties"]["identities"],
                }
            ),
        },
    }
)

PROMPT = """\
These {n} images are scanned pages. Each shows the same kind of printed table, from a different \
page or issue. Write a template for that kind of table: a description from which a program can \
read every cell of the table on any page of this kind, and check its figures against each other.

Answer as JSON, in this form:

- identity.title: the table's title as printed, on one line, without what changes from page to \
page (a date, a month, a sheet number) or footnote marks.
- identity.description: one line that tells a page of this kind apart from any other page, for a \
page classifier.
- identity.title_patterns: one or more regular expressions, matched with case ignored, that find \
the printed title on every page of this kind.
- layout.unit: what the figures are counted in, as the page says (e.g. "thousands of dollars"), \
or "as printed" if it doesn't say.
- layout.precision: the last digit the figures are printed to: "1" for whole numbers, "0.1" for \
one decimal place, "0.01" for two.
- layout.rows: either a list of the rows every page of this kind prints, in order from the top, \
each {{"key": ..., "printed": its label as printed}}; or {{"read": n}} when the rows change from \
page to page (dates, a rolling run of months), to read n rows in order from the top, n at least \
as many as any page prints. With "read", a column holds each row's label, and the rows are keyed \
"01", "02", ... from the top. Or, when the rows fall into sections, each under a printed heading \
with rows that change from page to page, {{"sections": [{{"key": ..., "printed": its heading as \
printed, "read": n}}, ...]}} in order from the top, n at least as many rows as any page prints \
under that heading; a section's rows are keyed "<key>_01", "<key>_02", ... from its top.
- layout.columns: every column, left to right, each {{"key": ..., "printed": its heading as \
printed, "kind": ..., "blank_means": ...}}; kind is "money" for an amount, "count" for a whole \
number of things, "percent", "date", or "text" for labels and anything else. The column of row \
labels is a column too, of kind "text". blank_means says what a blank cell of a money, count or \
percent column stands for in a relation: "zero" when a blank there is nothing, an amount of 0; \
"unknown" (or null) when a blank is a figure not given, so a relation that needs it is not \
checked. A text or date column's is null.
- identities: every arithmetic relation you believe the printed figures satisfy, such as a total \
and its parts, a subtotal, a difference. For each: "id", a one-line "description", "left" and \
"right", the two sides that are equal, and where it applies: "for_each" is "table" for a \
relation between named cells, "row" for one that holds along each row, "column" for one that \
holds down each column, "position" (rows in sections only) for one that holds at each row \
position within sections (the first row of each section, the second, ...) in each figure \
column; "over" lists the rows or the columns it applies to, or is null for every one. Each side \
is one of:
  - {{"cell": {{"row": ..., "column": ...}}}}: a cell; leave out (null) the row or the column \
that for_each supplies. With for_each "row", {{"cell": {{"column": ..., "previous_row": true}}}} \
is that column's cell in the row directly above the one the relation is applied to; a relation \
that uses it is not applied to the first row;
  - {{"sum": {{"rows": [...], "column": ...}}}}: named rows of one column, or {{"sum": \
{{"columns": [...], "row": ...}}}}: named columns of one row; null for what is not used or \
what for_each supplies;
  - with for_each "position", {{"cell": {{"section": ...}}}}: the named section's cell at that \
position, and {{"sum": {{"sections": [...]}}}}: the named sections' cells at that position, \
added;
  - {{"difference": [a, b]}}: a minus b, each a cell or a sum.
  Only figures (money, count or percent columns) can be in a relation. Figures are rounded as \
printed, so a relation only has to hold to within that rounding.

Every key is lower case, letters, digits and "_", starting with a letter; row and column keys \
are unique, and a relation names only keys of this template. List only relations you believe \
hold on every page of this kind."""

PANELS_NOTE = """

This table is printed in panels: blocks, each with its own heading, column headings and rows, set \
one above another or side by side. Answer with "panels" in place of "layout" and "identities": a \
list of the panels, in order from the top (from the left where they are side by side), each with \
"key"; "title", the panel's heading as printed, or, for a panel printed once for each of several \
things (a State, a year), what that heading names; "repeats", the most such panels any of these \
pages prints (1 for a panel printed once); and "layout" and "identities" as above, for that panel \
alone, its relations naming only its own rows and columns. identity.title is the title printed \
over the whole table."""

TITLE_NOTE = (
    '\n\nA page may print more than one table. Describe only the table whose printed title is '
    '"{title}", and nothing else on the page.'
)

RETRY_NOTE = (
    "\n\nYour previous answer could not be used as a template: {error}. Answer again in full, as "
    "JSON that matches the schema."
)


class DraftFailed(RuntimeError):
    pass


def _key(text: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]
    return key if re.fullmatch(KEY, key) else f"k_{key}"[:40].rstrip("_")


def _patterns(patterns: Sequence[str], title: str) -> list[str]:
    usable = []
    for pattern in patterns:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        usable.append(pattern)
    return usable or [r"\s+".join(re.escape(word) for word in title.split())]


def _without_nulls(value: object) -> object:
    """The answer without its nulls, nor a previous_row that is false: both mean "not given"."""
    if isinstance(value, dict):
        return {
            k: _without_nulls(v)
            for k, v in value.items()
            if v is not None and not (k == "previous_row" and v is False)
        }
    if isinstance(value, list):
        return [_without_nulls(v) for v in value]
    return value


def _figures_only(layout: object) -> object:
    """The layout with blank_means kept only on a figure's column, where it means something."""
    if isinstance(layout, dict) and isinstance(layout.get("columns"), list):
        for column in layout["columns"]:
            if isinstance(column, dict) and column.get("kind") not in NUMERIC:
                column.pop("blank_means", None)
    return layout


def parse_draft(
    data: object, family: str, provenance: dict
) -> tuple[Template, list[tuple[str, str]]]:
    """The template an answer describes, and the identities left out with why; raises
    ValueError when the title, the patterns or the layout don't validate."""
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {data!r}")
    try:
        found = data["identity"]
        title = " ".join(str(found["title"]).split())
        identity = Family(
            family=family,
            title=title,
            description=" ".join(str(found["description"]).split()),
            title_patterns=_patterns([str(p) for p in found["title_patterns"]], title),
        )
        layout = Layout.model_validate(_figures_only(_without_nulls(data["layout"])))
    except (KeyError, TypeError, ValidationError) as error:
        raise ValueError(f"{type(error).__name__}: {error}"[:1500]) from error

    base = {"identity": identity.model_dump(), "layout": layout.model_dump(exclude_none=True)}
    kept: list[dict] = []
    left_out: list[tuple[str, str]] = []
    for raw in data.get("identities") or []:
        if not isinstance(raw, dict):
            left_out.append(("?", f"not an object: {raw!r}"[:300]))
            continue
        candidate = _without_nulls(raw)
        name = _key(str(candidate.get("id", "identity")))
        taken = {i["id"] for i in kept}
        n = 2
        while name in taken:
            name, n = f"{_key(str(candidate.get('id', 'identity')))[:36]}_{n}", n + 1
        candidate["id"] = name
        try:
            Template.model_validate({**base, "identities": [candidate], "provenance": provenance})
        except ValidationError as error:
            reason = "; ".join(e["msg"] for e in error.errors())
            left_out.append((name, reason[:300]))
            continue
        kept.append(candidate)
    template = Template.model_validate({**base, "identities": kept, "provenance": provenance})
    return template, left_out


def parse_panelled(
    data: object, family: str, provenance: dict
) -> tuple[Template, list[tuple[str, str]]]:
    """The template an answer in panels describes, and the identities left out with why ("<panel>.
    <id>"); raises ValueError when the title, the patterns or a panel's layout don't validate."""
    if not isinstance(data, dict) or not isinstance(data.get("panels"), list) or not data["panels"]:
        raise ValueError(f"expected a JSON object with a list of panels, got {data!r}"[:1500])
    panels: list[Panel] = []
    left_out: list[tuple[str, str]] = []
    keys: set[str] = set()
    for n, raw in enumerate(data["panels"], 1):
        if not isinstance(raw, dict):
            raise ValueError(f"panel {n} is not an object: {raw!r}"[:1500])
        key = _key(str(raw.get("key") or f"panel_{n}"))[:24].rstrip("_")
        while key in keys:
            key = f"{key[:21]}_{n}"
        keys.add(key)
        repeats = raw.get("repeats")
        repeats = min(9, max(1, repeats)) if isinstance(repeats, int) else 1
        single, out = parse_draft(
            {"identity": data.get("identity"), "layout": raw.get("layout"),
             "identities": raw.get("identities")},
            family,
            provenance,
        )
        try:
            panels.append(
                Panel(
                    key=key,
                    title=" ".join(str(raw.get("title") or key).split()),
                    repeats=repeats,
                    layout=single.layout,
                    identities=single.identities,
                )
            )
        except ValidationError as error:
            raise ValueError(f"panel {key}: {error}"[:1500]) from error
        left_out += [(f"{key}.{name}", why) for name, why in out]
    try:
        template = Template(identity=single.identity, panels=panels, provenance=provenance)
    except ValidationError as error:
        raise ValueError(f"{error}"[:1500]) from error
    return template, left_out


def ask(
    llm: VisionLLM,
    images: Sequence[bytes],
    family: str,
    provenance: dict,
    title: str | None = None,
    panelled: bool = False,
):
    """The drafter's template for the pages, of the table printed with title if given, in panels
    if panelled; asked once more if it can't be used."""
    prompt = PROMPT.format(n=len(images)) + (PANELS_NOTE if panelled else "")
    prompt += TITLE_NOTE.format(title=title) if title else ""
    parse = parse_panelled if panelled else parse_draft
    errors: list[str] = []
    for retry in (False, True):
        request = LLMRequest(
            role=ROLE,
            prompt=prompt + RETRY_NOTE.format(error=errors[-1]) if retry else prompt,
            images=tuple(images),
            json_schema=PANELS_SCHEMA if panelled else SCHEMA,
            max_output_tokens=DRAFT_TOKENS,
        )
        text = llm.complete(request).text
        try:
            return parse(json.loads(text), family, provenance)
        except ValueError as error:  # bad JSON, or a template that doesn't validate
            errors.append(str(error)[:1500])
    raise DraftFailed(" | retry: ".join(e[:500] for e in errors))


def to_yaml(template: Template, header: str) -> str:
    data = template.model_dump(mode="json", exclude_none=True)
    if template.panels is not None:
        data.pop("identities")  # a table printed in panels keeps them in its panels
    comment = "".join(f"# {line}\n" for line in header.splitlines())
    return comment + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def draft(
    family: str,
    refs: Sequence[str],
    llm: VisionLLM,
    *,
    directory: Path = TEMPLATES_DIR,
    today: date | None = None,
    title: str | None = None,
    panelled: bool = False,
) -> Path:
    """Draft <directory>/<family>.yaml from the pages, of the table printed with title if given
    (for pages that print more than one table), in panels if panelled; returns its path."""
    if re.fullmatch(KEY, family) is None or len(family) > 40:
        raise ValueError(f"{family!r} is not a family name: lower case, letters, digits and _")
    if family in REGISTRY or family == UNSUPPORTED:
        raise ValueError(f"{family!r} is a registered document type")
    if not MIN_PAGES <= len(refs) <= MAX_PAGES or len(set(refs)) != len(refs):
        raise ValueError(f"draft from {MIN_PAGES} to {MAX_PAGES} different pages, not {refs}")
    path = directory / f"{family}.yaml"
    if path.exists():
        try:
            if read_template(path).provenance.approved:
                raise ValueError(f"{path} is approved: it is never redrafted in place")
        except TemplateError:
            pass  # a broken file is replaced
    pages = [resolve(ref) for ref in refs]  # refuses a page that may not be sent, before any call
    today = today or date.today()
    provenance = {
        "status": "draft",
        "drafted_by": {"kind": "model", "id": llm.model_id},
        "drafted_on": today.isoformat(),
        "drafted_from": list(refs),
    }
    images = [p.path.read_bytes() for p in pages]
    template, left_out = ask(llm, images, family, provenance, title, panelled)
    notes = [f"drafted by {llm.model_id} from {', '.join(refs)} ({ROLE} role, P21b)"]
    if title:
        notes.append(f"told to describe only the table printed as {title!r}")
    if panelled:
        notes.append("drafted as a table printed in panels (P21d)")
    notes += [f"left out at drafting: identity {name!r}: {why}" for name, why in left_out]
    template = template.model_copy(
        update={"provenance": template.provenance.model_copy(update={"evidence": notes})}
    )
    header = (
        f"Drafted by {llm.model_id} from {', '.join(refs)} on {today.isoformat()} (P21b).\n"
        "A draft: validated, never registered. python -m archivist.templates.test checks its\n"
        "identities; only a person, with python -m archivist.templates.approve, approves it."
    )
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(to_yaml(template, header), encoding="utf-8")
    read_template(path)  # what was written reads back as the template it is
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--family", required=True)
    parser.add_argument("--pages", nargs="+", required=True)
    parser.add_argument(
        "--title", help="the printed title of the table to describe, if a page prints several"
    )
    parser.add_argument(
        "--panels", action="store_true", help="the table is printed in panels (P21d)"
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dir", type=Path, default=TEMPLATES_DIR)
    args = parser.parse_args(argv)
    roles = load_roles(args.config)
    llm = roles[ROLE]
    guard = llm.inner.guard  # Cache -> Budget -> the guard shared by every role
    before = guard.spent()
    path = draft(
        args.family, args.pages, llm, directory=args.dir, title=args.title, panelled=args.panels
    )
    template = read_template(path)
    tables = [(f"{p.key}: ", p.layout, p.identities) for p in template.panels or ()] or [
        ("", template.layout, template.identities)
    ]
    for name, layout, identities in tables:
        print(
            f"{path}: {name}{template.identity.title!r}, {len(layout.row_keys)} rows x "
            f"{len(layout.columns)} columns, {len(identities)} identities"
        )
    print(f"${guard.spent() - before:.4f} spent")


if __name__ == "__main__":
    main()
