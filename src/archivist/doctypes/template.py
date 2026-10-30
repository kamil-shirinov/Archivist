"""Document types defined by a reviewed template file instead of code (P21a).

A template, templates/<family>.yaml, describes one printed table: what it is called and how the
page classifier should know it (identity), its rows and columns as printed with each column's kind
and the table's unit (layout), the identities its figures satisfy (identities), and who drafted
it (and from which pages), who approved it, when, on what evidence and with the sha256 of the
evidence file beside it, and which drafted identities were left out (provenance; the drafter, the
arithmetic test and the approval are archivist.templates). Template validates the file;
TemplateType is the DocType built from it. It asks for every cell as the ledger family does
({"value", "box"}, ledger.py), under the same rules, so verify.py and the exporter take its pages
as they take a card's.

Identities are data, never code: two structured expressions over cells held equal. An expression
is a cell, a sum over named rows or columns, or a difference of two expressions; a cell may be the
same cell in another table of the same issue, named by that table's family, or, in an identity
applied to every row, the cell in the row directly above (previous_row), so a row's figure can be
worked out from the one before it; such an identity does not apply to the first row. evaluate()
works them out in Decimal from the read values; nothing is ever passed to eval. Printed figures
are rounded, so an identity over n printed values holds when its two sides differ by no more
than n half-units of the printed precision (half a unit of each table's own precision, for a cell
in another table).

An identity applies to the whole table, to every used row, or to every numeric column (for_each),
or only to the rows or columns it names (over). A failed identity flags every cell in it with the
same detail, "identity <family>.<id> on <where>: ...", and each with the value that cell would have
to read for the identity to hold exactly, as it would be printed. The detail's opening names the
rule (rule()) and, with the batch, the cells of its equation (equation()), which is how the
exporter explains it. check is "arithmetic" when every cell is on the page, "crossdoc" when one is
in another table. A numeric cell that can't be read as a figure is flagged as the ledger's are.

Rows are fixed, each with a key and its printed label, or read: numbered "01", "02", ... from the
top, for a table whose rows change from issue to issue (a rolling run of months), with the row's
label read as one of the columns; or read in sections, for a table printed as sections under
headings, each with such rows: "<section>_01", "<section>_02", ... from the top of the section. An
identity for_each: position holds at each position within sections (the first row of each, the
second, ...) in every numeric column, its cells naming a section ({"cell": {"section": ...}}) or
summing several ({"sum": {"sections": [...]}}) at that position; a position at which no section
prints a row on a page is skipped there. A row whose cells are all blank is unused, and identities
skip it; a value not read leaves an identity that needs it unchecked. A lone dash is nil. What a
blank cell means is the column's blank_means: "unknown" (the default) leaves an identity that
needs it unchecked, as for a figure not printed; "zero" counts it as 0, for a column where a blank
is nothing (only a figure's column may say so). A blank counted as 0 is not a printed value, so it
adds nothing to the rounding tolerance; an identity whose values are all such blanks reads 0 = 0,
which proves nothing, so it is never evaluated (empty()).

A page's issue is its id up to the last "_" ("1939-09_p057" is issue "1939-09"). An identity that
needs another table is unresolvable (a note, as the ledger's are) when its page has no issue, or
the issue has no page of that table in the batch, or more than one.

A table printed in panels (P21d) is described panel by panel: in place of one layout and its
identities, the template lists its panels, each a block with its own heading, rows, columns and
identities, in order from the top (left to right where side by side). A panel printed once for each
of several things on a page (a State, a year) is described once, with repeats the most a page
prints; its copies are keyed "<key>_1", "<key>_2", ... from the top. A cell of a panel is named with
its copy before its row ("T.<family>:<page>:<copy>.<row>:<column>"), and a panel's identities name
only its own cells. The page is still classified as one type (PanelledType), and each panel is read
on its own (archivist.templates.panels finds where). A template with one layout means what it
always meant: nothing about it changed, so neither did its file or its sha256.

load_templates validates every file in the directory, drafts included, and the references between
them, so a malformed template is refused rather than ignored; only approved ones become types.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from archivist.doctypes.ledger import (
    UNRESOLVABLE,
    _cells,
    _object,
    _prompt,
    _reread_prompt,
    _section,
    _value,
    calendar_date,
)
from archivist.schema import ExtractedValue, Flag, PageExtraction

TEMPLATES_DIR = Path("templates")
PREFIX = "T."  # a template field id: T.<family>:<page id>:<row>:<column>
KEY = r"^[a-z][a-z0-9_]*$"
NUMERIC = frozenset({"money", "count", "percent"})
DASHES = frozenset({"-", "–", "—", "−"})  # nil, as statistical tables print it
CITATIONS = "S0+grid"  # every template's box strategy, by the rule: templates/citations_dev_v3.md
_FIGURE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)?(?:\.(\d+))?")
SPACED = re.compile(r"(?<=\d), +(?=\d{3}(?!\d))")  # "29, 139": a space after a thousands comma
_DETAIL = re.compile(
    r"^identity (\S+) on (row \S+|column \S+|position \d+ in column \S+|the table): "
)
_FOOTNOTE = re.compile(r"\s*\d+/")


class TemplateError(ValueError):
    pass


# --- The file ----------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Family(_Strict):
    """What the table is: its name, the classifier's one line, and how its title is printed."""

    family: str = Field(pattern=KEY, max_length=40)
    title: str = Field(min_length=1)  # as printed
    description: str = Field(min_length=1)  # one line, shown to the page classifier
    title_patterns: list[str] = Field(min_length=1)  # regular expressions, case ignored

    @field_validator("description", "title")
    @classmethod
    def _one_line(cls, text: str) -> str:
        if "\n" in text.strip():
            raise ValueError("must be one line")
        return text.strip()

    @field_validator("title_patterns")
    @classmethod
    def _compiles(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as error:
                raise ValueError(f"title pattern {pattern!r}: {error}") from error
        return patterns


class Label(_Strict):
    key: str = Field(pattern=KEY, max_length=40)
    printed: str = Field(min_length=1)


class Column(Label):
    kind: Literal["money", "count", "percent", "date", "text"]
    blank_means: Literal["zero", "unknown"] = "unknown"  # in an identity

    @model_validator(mode="after")
    def _zero_is_a_figure(self) -> Column:
        if self.blank_means == "zero" and self.kind not in NUMERIC:
            raise ValueError(f"column {self.key!r} is {self.kind}: only a figure's blank is zero")
        return self


class ReadRows(_Strict):
    read: int = Field(ge=1, le=99)  # how many rows to ask for, numbered from the top


class Section(_Strict):
    """Rows printed under one heading, read from the top of the section."""

    key: str = Field(pattern=KEY, max_length=36)
    printed: str = Field(min_length=1)  # the heading, as printed
    read: int = Field(ge=1, le=99)  # how many rows to ask for under it


class Sections(_Strict):
    sections: list[Section] = Field(min_length=1)


class Layout(_Strict):
    unit: str = Field(min_length=1)  # e.g. "millions of dollars"
    precision: str = Field(pattern=r"^(1|0\.0*1)$")  # the last printed digit: "0.1", "1"
    rows: list[Label] | ReadRows | Sections
    columns: list[Column] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> Layout:
        for what, keys in (("row", self.row_keys), ("column", [c.key for c in self.columns])):
            if len(set(keys)) != len(keys):
                raise ValueError(f"{what} keys repeat: {keys}")
        return self

    @property
    def row_keys(self) -> list[str]:
        if isinstance(self.rows, ReadRows):
            return [f"{n:02d}" for n in range(1, self.rows.read + 1)]
        if isinstance(self.rows, Sections):
            return [f"{s.key}_{n:02d}" for s in self.rows.sections for n in range(1, s.read + 1)]
        return [row.key for row in self.rows]

    def section(self, key: str) -> Section | None:
        if not isinstance(self.rows, Sections):
            return None
        return next((s for s in self.rows.sections if s.key == key), None)

    @property
    def step(self) -> Decimal:
        return Decimal(self.precision)

    def column(self, key: str) -> Column | None:
        return next((c for c in self.columns if c.key == key), None)

    def numeric(self) -> list[str]:
        return [c.key for c in self.columns if c.kind in NUMERIC]


class CellRef(_Strict):
    """A cell; a row or column left out is the one the identity is being applied to."""

    table: str | None = Field(default=None, pattern=KEY)  # another table of the same issue
    row: str | None = None
    column: str | None = None
    previous_row: Literal[True] | None = None  # the row above the one for_each: row supplies
    section: str | None = Field(default=None, pattern=KEY)  # its row at for_each: position

    @model_validator(mode="after")
    def _above(self) -> CellRef:
        if self.previous_row and (self.row is not None or self.table is not None):
            raise ValueError("previous_row is the row above this table's own: name no row or table")
        if self.section is not None and (
            self.row is not None or self.table is not None or self.previous_row
        ):
            raise ValueError("a section's cell takes its row from for_each: position alone")
        return self


class Cell(_Strict):
    cell: CellRef


class Over(_Strict):
    """Named rows of one column, named columns of one row, or, at for_each: position, the cells
    of named sections at that position."""

    table: str | None = Field(default=None, pattern=KEY)
    rows: list[str] | None = None
    columns: list[str] | None = None
    sections: list[str] | None = None
    row: str | None = None  # the row of the named columns
    column: str | None = None  # the column of the named rows or sections

    @model_validator(mode="after")
    def _one_axis(self) -> Over:
        named = [n for n in (self.rows, self.columns, self.sections) if n is not None]
        if len(named) != 1:
            raise ValueError("a sum names rows, columns or sections, one of them")
        if not named[0]:
            raise ValueError("a sum names at least one row, column or section")
        if (self.rows is not None or self.sections is not None) and self.row is not None:
            raise ValueError("a sum over rows or sections takes a column, not a row")
        if self.columns is not None and self.column is not None:
            raise ValueError("a sum over columns takes a row, not a column")
        if self.sections is not None and self.table is not None:
            raise ValueError("a sum over sections is of this table's own")
        return self


class Sum(_Strict):
    sum: Over


class Difference(_Strict):
    difference: tuple[Expr, Expr]


Expr = Cell | Sum | Difference
Difference.model_rebuild()


class Identity(_Strict):
    """left = right, to within the rounding of the printed values."""

    id: str = Field(pattern=KEY, max_length=40)
    description: str = Field(min_length=1)
    for_each: Literal["table", "row", "column", "position"] = "table"
    over: list[str] | None = None  # the rows or columns it applies to; default every one
    left: Expr
    right: Expr


class Drafter(_Strict):
    kind: Literal["model", "person"]
    id: str = Field(min_length=1)  # a model id, or who the person is (never personal data)


class Dropped(_Strict):
    """An identity the draft proposed and the approved template leaves out, and why; in a table
    printed in panels, named "<panel>.<id>"."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$", max_length=65)
    by: Literal["arithmetic test", "approver"]
    why: str = Field(min_length=1)


class Provenance(_Strict):
    status: Literal["approved", "draft", "example, not approved"]
    drafted_by: Drafter
    drafted_on: date
    drafted_from: list[str] = []  # the page ids a model drafted it from
    approved_by: str | None = None
    approved_on: date | None = None
    evidence: list[str] = []  # what it was drafted from and approved on: pages, runs, notes
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dropped: list[Dropped] = []  # the draft's identities left out at approval

    @model_validator(mode="after")
    def _signed(self) -> Provenance:
        if self.approved:
            if not (self.approved_by and self.approved_on and self.evidence):
                raise ValueError("an approved template names who approved it, when, and on what")
            if self.approved_on < self.drafted_on:
                raise ValueError("approved before it was drafted")
        elif self.approved_by is not None or self.approved_on is not None:
            raise ValueError(f"a template that is {self.status!r} has no approval")
        elif self.evidence_sha256 is not None or self.dropped:
            raise ValueError(f"a template that is {self.status!r} has no approval evidence")
        return self

    @property
    def approved(self) -> bool:
        return self.status == "approved"


def _resolve(identities: Sequence[Identity], layout: Layout, family: str, own_only: bool) -> None:
    """Every identity names cells the layout has (or another table's, unless own_only)."""
    ids = [i.id for i in identities]
    if len(set(ids)) != len(ids):
        raise ValueError(f"identity ids repeat: {ids}")
    for identity in identities:
        try:
            for place in _contexts(identity, layout):
                terms = _linear(identity, place)
                if not any(t.table is None for t in terms):
                    raise ValueError("no cell of this table")
                for term in terms:
                    if term.table is not None and own_only:
                        raise ValueError("a panel's identity names only its own cells")
                    if term.table == family:
                        raise ValueError("name another table, or leave the table out")
                    if term.table is None:
                        _check_cell(layout, term, "this table")
        except ValueError as error:
            raise ValueError(f"identity {identity.id!r}: {error}") from error


class Panel(_Strict):
    """One panel of a table printed in panels: a block with its own heading, rows, columns and
    identities. One printed once for each of several things (a State, a year) is described once,
    with repeats the most a page prints."""

    key: str = Field(pattern=KEY, max_length=24)
    title: str = Field(min_length=1)  # its heading as printed, or what the heading names
    repeats: int = Field(default=1, ge=1, le=9)
    layout: Layout
    identities: list[Identity] = []

    @field_validator("title")
    @classmethod
    def _one_line(cls, text: str) -> str:
        if "\n" in text.strip():
            raise ValueError("must be one line")
        return text.strip()

    @property
    def copies(self) -> list[str]:
        """The keys of its copies on a page, from the top."""
        if self.repeats == 1:
            return [self.key]
        return [f"{self.key}_{n}" for n in range(1, self.repeats + 1)]


class Template(_Strict):
    identity: Family
    layout: Layout | None = None  # one table; or, printed in panels, panels
    identities: list[Identity] = []
    panels: list[Panel] | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def _identities_resolve(self) -> Template:
        if (self.layout is None) == (self.panels is None):
            raise ValueError("a template has a layout, or panels, not both")
        if self.panels is None:
            _resolve(self.identities, self.layout, self.identity.family, own_only=False)
            return self
        if self.identities:
            raise ValueError("a table printed in panels keeps its identities in its panels")
        if not self.panels:
            raise ValueError("a table printed in panels has at least one panel")
        copies = [c for p in self.panels for c in p.copies]
        if len(set(copies)) != len(copies):
            raise ValueError(f"panel keys repeat: {copies}")
        for panel in self.panels:
            try:
                _resolve(panel.identities, panel.layout, self.identity.family, own_only=True)
            except ValueError as error:
                raise ValueError(f"panel {panel.key!r}: {error}") from error
        return self

    @property
    def family(self) -> str:
        return self.identity.family


@dataclass(frozen=True)
class Term:
    table: str | None  # None: the identity's own table
    row: str
    column: str
    coef: int  # +1 on the left, −1 on the right (a difference flips its second part)


def _uses_previous(expr: Expr) -> bool:
    if isinstance(expr, Cell):
        return bool(expr.cell.previous_row)
    if isinstance(expr, Difference):
        return any(_uses_previous(part) for part in expr.difference)
    return False


def _sections_in(expr: Expr) -> set[str]:
    if isinstance(expr, Cell):
        return {expr.cell.section} if expr.cell.section else set()
    if isinstance(expr, Sum):
        return set(expr.sum.sections or ())
    return set().union(*(_sections_in(part) for part in expr.difference))


@dataclass(frozen=True)
class Place:
    """Where an identity is applied: the row or column for_each supplies, the row above it, or
    the position within sections."""

    row: str | None
    column: str | None
    where: str
    above: str | None = None
    position: int | None = None


def _contexts(identity: Identity, layout: Layout) -> Iterator[Place]:
    """Each place the identity applies: every row of a read table (an identity that names the
    previous row skips the first), every numeric column, or every position within the sections it
    names, as deep as the shallowest of them, in every numeric column."""
    if identity.for_each == "table":
        if identity.over is not None:
            raise ValueError("over needs for_each: row, column or position")
        yield Place(None, None, "the table")
    elif identity.for_each == "row":
        keys = layout.row_keys
        previous = _uses_previous(identity.left) or _uses_previous(identity.right)
        for row in identity.over or keys:
            if row not in keys:
                raise ValueError(f"unknown row {row!r}")
            above = keys[keys.index(row) - 1] if keys.index(row) else None
            if previous and above is None:
                continue
            yield Place(row, None, f"row {row}", above)
    else:
        if identity.for_each == "position":
            named = _sections_in(identity.left) | _sections_in(identity.right)
            if not isinstance(layout.rows, Sections) or not named:
                raise ValueError("for_each: position names sections of a table read in sections")
            unknown = sorted(k for k in named if layout.section(k) is None)
            if unknown:
                raise ValueError(f"unknown sections {unknown}")
            depth = min(layout.section(k).read for k in named)
        for column in identity.over or layout.numeric():
            if column not in layout.numeric():
                raise ValueError(f"{column!r} is not a numeric column")
            if identity.for_each == "column":
                yield Place(None, column, f"column {column}")
                continue
            for n in range(1, depth + 1):
                yield Place(None, column, f"position {n:02d} in column {column}", position=n)


def _terms(expr: Expr, place: Place, coef: int) -> list[Term]:
    if isinstance(expr, Cell):
        ref = expr.cell
        if ref.previous_row and place.row is None:
            raise ValueError("previous_row needs for_each: row")
        if ref.section is not None:
            if place.position is None:
                raise ValueError("a section's cell needs for_each: position")
            r = f"{ref.section}_{place.position:02d}"
        else:
            r = place.above if ref.previous_row else ref.row or place.row
        c = ref.column or place.column
        if r is None or c is None:
            raise ValueError("a cell needs a row and a column, given or from for_each")
        return [Term(ref.table, r, c, coef)]
    if isinstance(expr, Sum):
        over = expr.sum
        if over.rows is not None or over.sections is not None:
            c = over.column or place.column
            if c is None:
                raise ValueError("a sum over rows or sections needs a column, given or by for_each")
            if over.rows is not None:
                return [Term(over.table, r, c, coef) for r in over.rows]
            if place.position is None:
                raise ValueError("a sum over sections needs for_each: position")
            return [Term(None, f"{k}_{place.position:02d}", c, coef) for k in over.sections]
        r = over.row or place.row
        if r is None:
            raise ValueError("a sum over columns needs a row, given or from for_each")
        return [Term(over.table, r, c, coef) for c in over.columns]
    first, second = expr.difference
    return _terms(first, place, coef) + _terms(second, place, -coef)


def _linear(identity: Identity, place: Place) -> list[Term]:
    """The identity as left − right = 0: every printed value with its sign."""
    return _terms(identity.left, place, 1) + _terms(identity.right, place, -1)


def _check_cell(layout: Layout, term: Term, where: str) -> None:
    if term.row not in layout.row_keys:
        raise ValueError(f"unknown row {term.row!r} in {where}")
    column = layout.column(term.column)
    if column is None:
        raise ValueError(f"unknown column {term.column!r} in {where}")
    if column.kind not in NUMERIC:
        raise ValueError(f"column {term.column!r} in {where} is {column.kind}, not a figure")


def _render(expr: Expr) -> str:
    """An expression in words for a flag: cells by key, another table's as table.key."""
    if isinstance(expr, Cell):
        ref = expr.cell
        parts = [p for p in (ref.section or ref.row, ref.column) if p]
        name = "/".join(parts) or "the cell"
        if ref.previous_row:
            name += " (row above)"
        return f"{ref.table}.{name}" if ref.table else name
    if isinstance(expr, Sum):
        over = expr.sum
        names = next(n for n in (over.rows, over.columns, over.sections) if n is not None)
        prefix = f"{over.table}." if over.table else ""
        return " + ".join(prefix + n for n in names)
    first, second = expr.difference
    second_text = _render(second)
    if not isinstance(second, Cell):
        second_text = f"({second_text})"
    return f"{_render(first)} − {second_text}"


def written(identity: Identity) -> str:
    """The identity in words, "left = right", cells by key."""
    return f"{_render(identity.left)} = {_render(identity.right)}"


def check_references(template: Template, tables: Mapping[str, Template]) -> None:
    """Every cell in another table names a table in tables and a numeric cell it has."""
    for identity in template.identities:
        for place in _contexts(identity, template.layout):
            for term in _linear(identity, place):
                if term.table is None:
                    continue
                other = tables.get(term.table)
                where = f"table {term.table!r}"
                try:
                    if other is None:
                        raise ValueError(f"{where} is not a known (approved) template")
                    if other.layout is None:
                        raise ValueError(f"{where} is printed in panels: its cells can't be named")
                    _check_cell(other.layout, term, where)
                except ValueError as error:
                    raise TemplateError(
                        f"{template.family}: identity {identity.id!r}: {error}"
                    ) from error


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_path(path: Path) -> Path:
    """Where a template's arithmetic evidence is kept: <family>.evidence.json beside it."""
    return path.with_name(f"{path.stem}.evidence.json")


def read_template(path: Path) -> Template:
    """One template file, validated; raises TemplateError naming the file. An approved template
    that names the sha256 of its evidence must have that evidence file beside it, unchanged."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        template = Template.model_validate(data)
    except (yaml.YAMLError, ValidationError) as error:
        raise TemplateError(f"{path}: {error}") from error
    if template.family != path.stem:
        raise TemplateError(f"{path}: the family is {template.family!r}, the file {path.stem!r}")
    if (digest := template.provenance.evidence_sha256) is not None:
        evidence = evidence_path(path)
        if not evidence.is_file() or file_sha256(evidence) != digest:
            raise TemplateError(f"{path}: {evidence} is missing or not what it was approved on")
    return template


def drafted_types(directory: Path = TEMPLATES_DIR) -> list[TemplateType]:
    """Every template in directory that a model drafted from pages, draft or approved, as a type
    in family order; a hand-written example is left out, and so is a table printed in panels,
    since what these types are used for measures the boxes of one table on a page."""
    out = []
    for path in sorted(directory.glob("*.yaml")):
        template = read_template(path)
        if template.provenance.drafted_from and template.panels is None:
            out.append(TemplateType(template, sha256=file_sha256(path)))
    return out


def load_templates(
    directory: Path, reserved: Collection[str] = ()
) -> list[TemplateType | PanelledType]:
    """The approved templates in directory as document types, in family order; one printed in
    panels as a PanelledType.

    Every file must validate and every reference must resolve among the files, drafts included;
    an approved template may refer only to other approved ones, and no family may take a reserved
    name (a built-in type's). Each type keeps its file's sha256, which a run records.
    """
    if not directory.is_dir():
        return []
    templates: dict[str, Template] = {}
    digests: dict[str, str] = {}
    for path in sorted(directory.glob("*.yaml")):
        template = read_template(path)
        templates[template.family], digests[template.family] = template, file_sha256(path)
    for template in templates.values():
        if template.family in reserved:
            raise TemplateError(f"{template.family}: the name is reserved or already registered")
        check_references(template, templates)
    approved = {k: t for k, t in templates.items() if t.provenance.approved}
    return [
        PanelledType(t, sha256=digests[k])
        if t.panels is not None
        else TemplateType(t, approved, sha256=digests[k])
        for k, t in approved.items()
    ]


# --- Reading figures ---------------------------------------------------------------------------


def number(text: str, kind: str) -> Decimal | None:
    """A figure as a statistical table prints it: "1,234.5", "-12", "(12)", ".4", "-" for nil;
    a percentage may end in "%", and a count has no decimal point. A space after a thousands
    comma, between digits, is read through ("29, 139" is 29139), as old type often sets it; the
    ledger family's figures are read by its own rules, not these."""
    t = text.strip()
    if kind == "percent":
        t = t.removesuffix("%").strip()
    if t in DASHES:
        return Decimal(0)
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative, t = True, t[1:-1].strip()
    elif t[:1] in DASHES:
        negative, t = True, t[1:].strip()
    t = SPACED.sub(",", t)
    match = _FIGURE.fullmatch(t)
    if match is None or not t or (kind == "count" and match.group(2) is not None):
        return None
    whole, fraction = match.groups()
    value = Decimal((whole or "0").replace(",", "") + (f".{fraction}" if fraction else ""))
    return -value if negative else value


def figure(text: str | None, kind: str, blank_is_zero: bool) -> Decimal | None:
    """A cell's figure for an identity: None if unread, blank (unless a blank is zero) or not a
    figure."""
    if text is None:
        return None
    if not text.strip():
        return Decimal(0) if blank_is_zero else None
    return number(text, kind)


def _places(step: Decimal) -> int:
    return max(0, -step.as_tuple().exponent)


def _fmt(value: Decimal, step: Decimal) -> str:
    return f"{value:,.{_places(step)}f}"


def issue_of(page_id: str) -> str | None:
    return page_id.rsplit("_", 1)[0] if "_" in page_id else None


def cell_id(family: str, page_id: str, row: str, column: str) -> str:
    return f"{PREFIX}{family}:{page_id}:{row}:{column}"


@dataclass(frozen=True)
class Instance:
    """One identity applied at one place of one page, its cells found in the batch."""

    rule: str
    where: str
    identity: Identity
    fields: tuple[tuple[str, int, Decimal, str], ...]  # field id, coef, precision, kind
    left: int  # how many of fields are on the left
    cross: bool  # a cell is in another table
    unresolved: str | None  # why another table's cells could not be found
    zero: frozenset[str] = frozenset()  # the fields whose column counts a blank as 0

    def own_field(self) -> str:
        return self.fields[0][0]


# --- The document type -------------------------------------------------------------------------


class TemplateType:
    """A DocType built from an approved template (doctypes.DocType, doctypes.RuleReader)."""

    def __init__(
        self,
        template: Template,
        tables: Mapping[str, Template] | None = None,
        *,
        sha256: str | None = None,  # the template file's, which a run records
        panel: str | None = None,  # a copy of a panel (PanelledType): its key leads each row's
        intro: str | None = None,  # a panel's: what the read is told it is looking at
    ) -> None:
        if template.layout is None:
            raise TemplateError(f"{template.family} is printed in panels: it is a PanelledType")
        self.template = template
        self.sha256 = sha256
        self.tables = dict(tables or {})
        check_references(template, self.tables)
        self.layout = template.layout
        self.name = template.family
        self.panel = panel
        self.intro = intro
        self.rule_name = f"{self.name}.{panel}" if panel else self.name
        self.description = template.identity.description
        self.money_fields = frozenset(c.key for c in self.layout.columns if c.kind == "money")
        self.citations = CITATIONS
        self._patterns = [re.compile(p, re.IGNORECASE) for p in template.identity.title_patterns]

    def _id(self, page_id: str, row: str, column: str) -> str:
        """The field id of a cell of this table (of this copy of a panel)."""
        return cell_id(self.name, page_id, f"{self.panel}.{row}" if self.panel else row, column)

    def matches_title(self, text: str) -> bool:
        return any(p.search(text) for p in self._patterns)

    def field_ids(self, page_id: str) -> list[str]:
        return [
            self._id(page_id, row, column.key)
            for row in self.layout.row_keys
            for column in self.layout.columns
        ]

    def extraction_prompt(self, grounding: bool = False) -> str:
        layout, title = self.layout, self.template.identity.title
        opening = self.intro or (
            f'This is a scanned page with the table "{title}" ({layout.unit}). Read every cell '
            "of that table, and nothing outside it."
        )
        dash = 'A dash printed in a cell is copied as "-".\n\n'
        return _prompt(f"{opening}\n\n{self.rows_and_columns()}{dash}", grounding)

    def rows_and_columns(self) -> str:
        """The prompt's account of the rows to give and the columns each row has."""
        layout = self.layout
        if isinstance(layout.rows, ReadRows):
            n = layout.rows.read
            rows = (
                f'"rows" holds one entry for each of {n} rows, keyed "01" to "{n:02d}" in order '
                'from the top: "01" is the first row below the column headings. Give every '
                'entry; a row below the last printed row has "" for each cell.\n'
            )
        elif isinstance(layout.rows, Sections):
            rows = (
                '"rows" holds one entry for each key below. The table is printed in sections, '
                "each under its heading, and a section's rows are keyed in order from the top of "
                "that section, the first row below its heading first:\n"
                + "".join(
                    f'- under the heading "{s.printed}": "{s.key}_01" to "{s.key}_{s.read:02d}"\n'
                    for s in layout.rows.sections
                )
                + 'Give every entry; a key below a section\'s last printed row has "" for each '
                "cell.\n"
            )
        else:
            rows = '"rows" holds one entry for each row, keyed:\n' + "".join(
                f'- "{row.key}": the row printed "{row.printed}"\n' for row in layout.rows
            )
        columns = "".join(f'- {c.key}: the "{c.printed}" column\n' for c in layout.columns)
        return f"{rows}Each row has:\n{columns}"

    def extraction_schema(self) -> dict:
        names = tuple(c.key for c in self.layout.columns)
        return _object({"rows": _object({row: _cells(names) for row in self.layout.row_keys})})

    def parse(self, page_id: str, data: object, width: int, height: int) -> list[ExtractedValue]:
        names = tuple(c.key for c in self.layout.columns)
        rows = _section(data, "rows", tuple(self.layout.row_keys))
        cells: dict[str, object] = {}
        for row, line in rows.items():
            if not isinstance(line, dict) or set(line) != set(names):
                raise ValueError(f"row {row}: expected the columns {list(names)}, got {line!r}")
            for column, cell in line.items():
                cells[self._id(page_id, row, column)] = cell
        return [_value(page_id, f, cells[f], width, height) for f in self.field_ids(page_id)]

    def reread_prompt(self, field_id: str) -> str:
        """The blind re-read of one cell, by its column and table; no digit, so no value, leaks."""
        heading = self.layout.column(field_id.rsplit(":", 1)[-1]).printed
        what = f'a cell in the "{heading}" column of the table "{self.template.identity.title}"'
        return _reread_prompt(" ".join(re.sub(r"\d", "", _FOOTNOTE.sub("", what)).split()))

    def _kind(self, field_id: str) -> str:
        return self.layout.column(field_id.rsplit(":", 1)[-1]).kind

    def canonical(self, field_id: str, text: str) -> str:
        """Figures as their value, dates as a calendar date, anything else as text with spacing
        and case ignored."""
        if not text.strip():
            return ""
        kind = self._kind(field_id)
        if kind in NUMERIC and (value := number(text, kind)) is not None:
            return format(value.normalize(), "f") if value else "0"
        if kind == "date" and (day := calendar_date(text)) is not None:
            return day.isoformat()
        return " ".join(text.split()).upper()

    def money(self, text: str) -> Decimal | None:
        return number(text, "money")

    def calendar_date(self, text: str) -> date | None:
        return calendar_date(text)

    # --- Identities ----------------------------------------------------------------------------

    def _used(self, texts: Mapping[str, str | None], page_id: str, row: str) -> bool:
        cells = [texts.get(self._id(page_id, row, c.key)) for c in self.layout.columns]
        return not all(t is not None and not t.strip() for t in cells)

    def _instances(
        self,
        page: PageExtraction,
        texts: Mapping[str, str | None],
        by_issue: Mapping[tuple[str, str | None], list[str]],
    ) -> Iterator[Instance]:
        page_id, issue = page.page_id, issue_of(page.page_id)
        for identity in self.template.identities:
            for place in _contexts(identity, self.layout):
                if place.row is not None and not self._used(texts, page_id, place.row):
                    continue
                terms = _linear(identity, place)
                if place.position is not None and not any(
                    self._used(texts, page_id, t.row) for t in terms
                ):
                    continue  # no section prints a row at this position on this page
                fields, unresolved, zero = [], None, set()
                for term in terms:
                    table = term.table or self.name
                    layout = self.tables[table].layout if term.table else self.layout
                    on = page_id
                    if term.table is not None:
                        found = by_issue.get((table, issue), [])
                        if issue is None:
                            unresolved = f"page {page_id} has no issue to find {table} in"
                        elif len(found) != 1:
                            count = "no page" if not found else f"{len(found)} pages"
                            unresolved = f"{count} of {table} for issue {issue} in this batch"
                        else:
                            on = found[0]
                    column = layout.column(term.column)
                    field_id = (
                        cell_id(table, on, term.row, term.column)
                        if term.table
                        else self._id(on, term.row, term.column)
                    )
                    fields.append((field_id, term.coef, layout.step, column.kind))
                    if column.blank_means == "zero":
                        zero.add(field_id)
                yield Instance(
                    rule=f"{self.rule_name}.{identity.id}",
                    where=place.where,
                    identity=identity,
                    fields=tuple(fields),
                    left=len(_terms(identity.left, place, 1)),
                    cross=any(t.table is not None for t in terms),
                    unresolved=unresolved,
                    zero=frozenset(zero),
                )

    def _batch(self, pages: Sequence[PageExtraction]):
        texts = {
            v.field_id: None if v.abstained else v.value for page in pages for v in page.values
        }
        by_issue: dict[tuple[str, str | None], list[str]] = defaultdict(list)
        for page in pages:
            by_issue[(page.doc_type, issue_of(page.page_id))].append(page.page_id)
        own = [p for p in pages if p.doc_type == self.name]
        return texts, by_issue, own

    def instances(self, pages: Sequence[PageExtraction]) -> Iterator[Instance]:
        """Every identity wherever it applies on this type's pages in the batch, as the checks
        apply them: a row is used, and another table's cells found, by the pages' read values."""
        texts, by_issue, own = self._batch(pages)
        for page in own:
            yield from self._instances(page, texts, by_issue)

    def evaluate(
        self, instance: Instance, texts: Mapping[str, str | None]
    ) -> tuple[Decimal, Decimal, Decimal] | None:
        """(left, right, tolerance) from the read values; None if any value is unread, blank
        where a blank is unknown, or not a figure, or if every value is a blank counted as 0. The
        tolerance is half a unit per printed value."""
        if self.empty(instance, texts):
            return None
        values, tolerance = [], Decimal(0)
        for field_id, _, step, kind in instance.fields:
            value = figure(texts.get(field_id), kind, field_id in instance.zero)
            if value is None:
                return None
            values.append(value)
            if texts[field_id].strip():
                tolerance += step / 2
        signed = [v * coef for v, (_, coef, _, _) in zip(values, instance.fields, strict=True)]
        left, right = (
            sum(signed[: instance.left], Decimal(0)),
            -sum(signed[instance.left :], Decimal(0)),
        )
        return left, right, tolerance

    def empty(self, instance: Instance, texts: Mapping[str, str | None]) -> bool:
        """Every value of the instance is a blank counted as 0: it would read 0 = 0, which holds
        whatever the table says."""

        def blank(field_id: str) -> bool:
            text = texts.get(field_id)
            return text is not None and not text.strip()

        return all(f in instance.zero and blank(f) for f, *_ in instance.fields)

    def printed(self, instance: Instance, texts: Mapping[str, str | None]) -> int:
        """How many of the instance's values are printed, not blank."""
        return sum(bool((texts.get(f) or "").strip()) for f, *_ in instance.fields)

    def _unreadable(self, page: PageExtraction, texts: Mapping[str, str | None]) -> list[Flag]:
        what = {
            "money": f"an amount in {self.layout.unit}",
            "count": "a count",
            "percent": "a percentage",
        }
        flags = []
        for row in self.layout.row_keys:
            if not self._used(texts, page.page_id, row):
                continue
            for column in self.layout.columns:
                field_id = self._id(page.page_id, row, column.key)
                text = texts.get(field_id)
                if (
                    column.kind in NUMERIC
                    and text
                    and text.strip()
                    and number(text, column.kind) is None
                ):
                    detail = f"{text!r} can't be read as {what[column.kind]}"
                    flags.append(Flag(field_id=field_id, check="arithmetic", detail=detail))
        return flags

    def checks(self, pages: list[PageExtraction]) -> list[Flag]:
        """Each page's unreadable figures, then every identity wherever it applies."""
        texts, by_issue, own = self._batch(pages)
        flags: list[Flag] = []
        for page in own:
            flags += self._unreadable(page, texts)
            noted: set[str] = set()
            for instance in self._instances(page, texts, by_issue):
                if instance.unresolved is not None:
                    if instance.rule not in noted:
                        noted.add(instance.rule)
                        detail = f"{UNRESOLVABLE}identity {instance.rule}: {instance.unresolved}"
                        flags.append(
                            Flag(field_id=instance.own_field(), check="crossdoc", detail=detail)
                        )
                    continue
                flags += self._failed(instance, texts)
        return flags

    def _failed(self, instance: Instance, texts: Mapping[str, str | None]) -> list[Flag]:
        result = self.evaluate(instance, texts)
        if result is None:
            return []
        left, right, tolerance = result
        residual = left - right
        if abs(residual) <= tolerance:
            return []
        step = self.layout.step
        identity = instance.identity
        detail = (
            f"identity {instance.rule} on {instance.where}: {_render(identity.left)} is "
            f"{_fmt(left, step)}, but {_render(identity.right)} is {_fmt(right, step)}, a "
            f"difference of {_fmt(abs(residual), step)}, more than the rounding tolerance of "
            f"{format(tolerance.normalize(), 'f')} for {self.printed(instance, texts)} printed "
            f"values ({identity.description})"
        )
        coefs: dict[str, int] = defaultdict(int)
        meta = {}
        for field_id, coef, field_step, kind in instance.fields:
            coefs[field_id] += coef
            meta[field_id] = (field_step, kind)
        check = "crossdoc" if instance.cross else "arithmetic"
        flags = []
        for field_id, coef in coefs.items():
            field_step, kind = meta[field_id]
            suggested = None
            if coef:
                read = figure(texts[field_id], kind, field_id in instance.zero)
                implied = read - residual / coef
                suggested = _fmt(implied, field_step)
            flags.append(Flag(field_id=field_id, check=check, detail=detail, suggested=suggested))
        return flags

    def balanced(self, pages: Sequence[PageExtraction]) -> set[str]:
        """The cells of every identity that holds with all its values read."""
        texts, by_issue, own = self._batch(pages)
        out: set[str] = set()
        for page in own:
            for instance in self._instances(page, texts, by_issue):
                if instance.unresolved is None and (result := self.evaluate(instance, texts)):
                    left, right, tolerance = result
                    if abs(left - right) <= tolerance:
                        out |= {field_id for field_id, *_ in instance.fields}
        return out

    # --- What the exporter asks (doctypes.RuleReader) ------------------------------------------

    def rule(self, flag: Flag) -> str | None:
        """The identity that raised the flag, "<family>.<id>"; None if not one of this type's."""
        match = _DETAIL.match(flag.detail)
        if match is None or match.group(1).split(".", 1)[0] != self.name:
            return None
        return match.group(1)

    def equation(self, flag: Flag, pages: Sequence[PageExtraction]) -> list[str]:
        """Every cell of the identity instance the flag was raised on, as the checks found them."""
        match = _DETAIL.match(flag.detail)
        if match is None:
            return []
        rule, where = match.groups()
        texts, by_issue, own = self._batch(sorted(pages, key=lambda p: p.page_id))
        for page in own:
            for instance in self._instances(page, texts, by_issue):
                ids = [field_id for field_id, *_ in instance.fields]
                if (instance.rule, instance.where) == (rule, where) and flag.field_id in ids:
                    return list(dict.fromkeys(ids))
        return []


# --- A table printed in panels (P21d) ------------------------------------------------------------

ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")


def panel_template(template: Template, panel: Panel) -> Template:
    """One panel as a table of its own: its title, layout and identities, under the family."""
    identity = template.identity.model_copy(update={"title": panel.title})
    return Template(
        identity=identity,
        layout=panel.layout,
        identities=panel.identities,
        provenance=template.provenance,
    )


def _which(template: Template, panel: Panel, n: int) -> str:
    what = f'the panel "{panel.title}" ({panel.layout.unit})'
    if panel.repeats > 1:
        what += f", the {ORDINALS[n - 1]} such panel from the top"
    return what


def cropped_intro(template: Template, panel: Panel, n: int) -> str:
    """What a read of a panel's crop is told: it sees one panel, cut from the page."""
    return (
        f'This image is cut from a scanned page. It shows one panel of the table '
        f'"{template.identity.title}": {_which(template, panel, n)}. Read every cell of that '
        "panel, and nothing outside it."
    )


def page_intro(template: Template, panel: Panel, n: int) -> str:
    """What a read of a panel on the whole page is told, where the panel was not found."""
    return (
        f'This is a scanned page with the table "{template.identity.title}", printed in '
        f"panels, each with its own heading, rows and columns. Read every cell of one panel: "
        f"{_which(template, panel, n)}, and nothing outside it. If the page does not print that "
        'panel, give "" for every cell.'
    )


class PanelledType:
    """A DocType built from an approved template printed in panels (doctypes.DocType,
    doctypes.RuleReader): one TemplateType for each copy of each panel, whose field ids lead each
    row with the copy's key. The page is classified as this one type; each panel is read on its
    own where archivist.templates.panels finds it, and the whole page is read at once only by the
    pipeline, which knows nothing of panels (extraction_prompt)."""

    def __init__(self, template: Template, *, sha256: str | None = None) -> None:
        if template.panels is None:
            raise TemplateError(f"{template.family} is one table: it is a TemplateType")
        self.template = template
        self.sha256 = sha256
        self.name = template.family
        self.description = template.identity.description
        self.citations = CITATIONS
        self.parts: dict[str, TemplateType] = {}
        self.kinds: dict[str, Panel] = {}  # copy -> its panel
        self.cropped: dict[str, TemplateType] = {}  # copy -> its read on a crop, plain field ids
        self.whole: dict[str, TemplateType] = {}  # copy -> its read on the page, plain field ids
        for panel in template.panels:
            own = panel_template(template, panel)
            for n, copy in enumerate(panel.copies, 1):
                self.kinds[copy] = panel
                self.parts[copy] = TemplateType(own, sha256=sha256, panel=copy)
                self.cropped[copy] = TemplateType(own, intro=cropped_intro(template, panel, n))
                self.whole[copy] = TemplateType(own, intro=page_intro(template, panel, n))
        self.money_fields = frozenset().union(*(p.money_fields for p in self.parts.values()))
        self._patterns = [re.compile(p, re.IGNORECASE) for p in template.identity.title_patterns]

    @property
    def copies(self) -> list[str]:
        return list(self.parts)

    def part(self, field_id: str) -> TemplateType:
        """The copy of a panel a field belongs to."""
        row = field_id.split(":")[2]
        return self.parts[row.split(".", 1)[0]]

    def matches_title(self, text: str) -> bool:
        return any(p.search(text) for p in self._patterns)

    def field_ids(self, page_id: str) -> list[str]:
        return [f for part in self.parts.values() for f in part.field_ids(page_id)]

    def extraction_prompt(self, grounding: bool = False) -> str:
        """The whole page at once, every panel under its own key: what the pipeline asks."""
        title = self.template.identity.title
        parts = "".join(
            f'\n"{copy}": {_which(self.template, panel, panel.copies.index(copy) + 1)}. '
            f"{part.rows_and_columns()}"
            for copy, part in self.parts.items()
            for panel in [self.kinds[copy]]
        )
        body = (
            f'This is a scanned page with the table "{title}", printed in panels, each with its '
            'own heading, rows and columns. Read every cell of every panel. "panels" holds one '
            "entry for each panel below, and each entry holds that panel's \"rows\". A panel the "
            'page does not print has "" for every cell.\n'
            f"{parts}\n"
            'A dash printed in a cell is copied as "-".\n\n'
        )
        return _prompt(body, grounding)

    def extraction_schema(self) -> dict:
        return _object(
            {"panels": _object({c: p.extraction_schema() for c, p in self.parts.items()})}
        )

    def parse(self, page_id: str, data: object, width: int, height: int) -> list[ExtractedValue]:
        panels = _section(data, "panels", tuple(self.parts))
        return [
            v
            for copy, part in self.parts.items()
            for v in part.parse(page_id, panels[copy], width, height)
        ]

    def reread_prompt(self, field_id: str) -> str:
        return self.part(field_id).reread_prompt(field_id)

    def canonical(self, field_id: str, text: str) -> str:
        return self.part(field_id).canonical(field_id, text)

    def money(self, text: str) -> Decimal | None:
        return number(text, "money")

    def calendar_date(self, text: str) -> date | None:
        return calendar_date(text)

    def instances(self, pages: Sequence[PageExtraction]) -> Iterator[Instance]:
        for part in self.parts.values():
            yield from part.instances(pages)

    def evaluate(
        self, instance: Instance, texts: Mapping[str, str | None]
    ) -> tuple[Decimal, Decimal, Decimal] | None:
        return self.part(instance.own_field()).evaluate(instance, texts)

    def empty(self, instance: Instance, texts: Mapping[str, str | None]) -> bool:
        return self.part(instance.own_field()).empty(instance, texts)

    def printed(self, instance: Instance, texts: Mapping[str, str | None]) -> int:
        return self.part(instance.own_field()).printed(instance, texts)

    def checks(self, pages: list[PageExtraction]) -> list[Flag]:
        return [flag for part in self.parts.values() for flag in part.checks(pages)]

    def balanced(self, pages: Sequence[PageExtraction]) -> set[str]:
        return set().union(*(part.balanced(pages) for part in self.parts.values()))

    def label(self, instance: Instance) -> str:
        """The identity an instance applies, as "<panel>.<id>" whichever copy it is on."""
        copy, identity = instance.rule.split(".", 1)[1].split(".", 1)
        return f"{self.kinds[copy].key}.{identity}"

    def rule(self, flag: Flag) -> str | None:
        match = _DETAIL.match(flag.detail)
        if match is None or match.group(1).split(".", 1)[0] != self.name:
            return None
        return match.group(1)

    def equation(self, flag: Flag, pages: Sequence[PageExtraction]) -> list[str]:
        for part in self.parts.values():
            if found := part.equation(flag, pages):
                return found
        return []
