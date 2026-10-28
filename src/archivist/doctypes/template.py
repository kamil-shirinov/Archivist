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
label read as one of the columns. A row whose cells are all blank is unused, and identities skip
it; a value not read leaves an identity that needs it unchecked. A lone dash is nil. What a blank
cell means is the column's blank_means: "unknown" (the default) leaves an identity that needs it
unchecked, as for a figure not printed; "zero" counts it as 0, for a column where a blank is
nothing (only a figure's column may say so). A blank counted as 0 is not a printed value, so it
adds nothing to the rounding tolerance.

A page's issue is its id up to the last "_" ("1939-09_p057" is issue "1939-09"). An identity that
needs another table is unresolvable (a note, as the ledger's are) when its page has no issue, or
the issue has no page of that table in the batch, or more than one.

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
CITATIONS = "S0+ocr"  # every template's box strategy, by the rule: templates/citations_dev_v2.md
_FIGURE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)?(?:\.(\d+))?")
_DETAIL = re.compile(r"^identity (\S+) on (row \S+|column \S+|the table): ")
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


class Layout(_Strict):
    unit: str = Field(min_length=1)  # e.g. "millions of dollars"
    precision: str = Field(pattern=r"^(1|0\.0*1)$")  # the last printed digit: "0.1", "1"
    rows: list[Label] | ReadRows
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
        return [row.key for row in self.rows]

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

    @model_validator(mode="after")
    def _above(self) -> CellRef:
        if self.previous_row and (self.row is not None or self.table is not None):
            raise ValueError("previous_row is the row above this table's own: name no row or table")
        return self


class Cell(_Strict):
    cell: CellRef


class Over(_Strict):
    """Named rows of one column, or named columns of one row."""

    table: str | None = Field(default=None, pattern=KEY)
    rows: list[str] | None = None
    columns: list[str] | None = None
    row: str | None = None  # the row of the named columns
    column: str | None = None  # the column of the named rows

    @model_validator(mode="after")
    def _one_axis(self) -> Over:
        if (self.rows is None) == (self.columns is None):
            raise ValueError("a sum names either rows or columns")
        if not (self.rows or self.columns):
            raise ValueError("a sum names at least one row or column")
        if (self.rows is not None and self.row is not None) or (
            self.columns is not None and self.column is not None
        ):
            raise ValueError("a sum over rows takes a column, a sum over columns a row")
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
    for_each: Literal["table", "row", "column"] = "table"
    over: list[str] | None = None  # the rows or columns it applies to; default every one
    left: Expr
    right: Expr


class Drafter(_Strict):
    kind: Literal["model", "person"]
    id: str = Field(min_length=1)  # a model id, or who the person is (never personal data)


class Dropped(_Strict):
    """An identity the draft proposed and the approved template leaves out, and why."""

    id: str = Field(pattern=KEY, max_length=40)
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


class Template(_Strict):
    identity: Family
    layout: Layout
    identities: list[Identity] = []
    provenance: Provenance

    @model_validator(mode="after")
    def _identities_resolve(self) -> Template:
        ids = [i.id for i in self.identities]
        if len(set(ids)) != len(ids):
            raise ValueError(f"identity ids repeat: {ids}")
        for identity in self.identities:
            try:
                instances = list(_contexts(identity, self.layout))
                for row, column, _, above in instances:
                    terms = _linear(identity, row, column, above)
                    if not any(t.table is None for t in terms):
                        raise ValueError("no cell of this table")
                    for term in terms:
                        if term.table == self.identity.family:
                            raise ValueError("name another table, or leave the table out")
                        if term.table is None:
                            _check_cell(self.layout, term, "this table")
            except ValueError as error:
                raise ValueError(f"identity {identity.id!r}: {error}") from error
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


Context = tuple[str | None, str | None, str, str | None]  # row, column, where, the row above


def _contexts(identity: Identity, layout: Layout) -> Iterator[Context]:
    """(row, column, where, the row above) for each place the identity applies, every row of a
    read table; an identity that names the previous row skips the first."""
    if identity.for_each == "table":
        if identity.over is not None:
            raise ValueError("over needs for_each: row or column")
        yield None, None, "the table", None
    elif identity.for_each == "row":
        keys = layout.row_keys
        previous = _uses_previous(identity.left) or _uses_previous(identity.right)
        for row in identity.over or keys:
            if row not in keys:
                raise ValueError(f"unknown row {row!r}")
            above = keys[keys.index(row) - 1] if keys.index(row) else None
            if previous and above is None:
                continue
            yield row, None, f"row {row}", above
    else:
        for column in identity.over or layout.numeric():
            if column not in layout.numeric():
                raise ValueError(f"{column!r} is not a numeric column")
            yield None, column, f"column {column}", None


def _terms(
    expr: Expr, row: str | None, column: str | None, coef: int, above: str | None = None
) -> list[Term]:
    if isinstance(expr, Cell):
        if expr.cell.previous_row and row is None:
            raise ValueError("previous_row needs for_each: row")
        r = above if expr.cell.previous_row else expr.cell.row or row
        c = expr.cell.column or column
        if r is None or c is None:
            raise ValueError("a cell needs a row and a column, given or from for_each")
        return [Term(expr.cell.table, r, c, coef)]
    if isinstance(expr, Sum):
        over = expr.sum
        if over.rows is not None:
            c = over.column or column
            if c is None:
                raise ValueError("a sum over rows needs a column, given or from for_each")
            return [Term(over.table, r, c, coef) for r in over.rows]
        r = over.row or row
        if r is None:
            raise ValueError("a sum over columns needs a row, given or from for_each")
        return [Term(over.table, r, c, coef) for c in over.columns]
    first, second = expr.difference
    return _terms(first, row, column, coef, above) + _terms(second, row, column, -coef, above)


def _linear(
    identity: Identity, row: str | None, column: str | None, above: str | None = None
) -> list[Term]:
    """The identity as left − right = 0: every printed value with its sign."""
    return _terms(identity.left, row, column, 1, above) + _terms(
        identity.right, row, column, -1, above
    )


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
        parts = [p for p in (ref.row, ref.column) if p]
        name = "/".join(parts) or "the cell"
        if ref.previous_row:
            name += " (row above)"
        return f"{ref.table}.{name}" if ref.table else name
    if isinstance(expr, Sum):
        over = expr.sum
        names = over.rows if over.rows is not None else over.columns
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
        for row, column, _, above in _contexts(identity, template.layout):
            for term in _linear(identity, row, column, above):
                if term.table is None:
                    continue
                other = tables.get(term.table)
                where = f"table {term.table!r}"
                try:
                    if other is None:
                        raise ValueError(f"{where} is not a known (approved) template")
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


def load_templates(directory: Path, reserved: Collection[str] = ()) -> list[TemplateType]:
    """The approved templates in directory as document types, in family order.

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
    return [TemplateType(t, approved, sha256=digests[k]) for k, t in approved.items()]


# --- Reading figures ---------------------------------------------------------------------------


def number(text: str, kind: str) -> Decimal | None:
    """A figure as a statistical table prints it: "1,234.5", "-12", "(12)", ".4", "-" for nil;
    a percentage may end in "%", and a count has no decimal point."""
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
    ) -> None:
        self.template = template
        self.sha256 = sha256
        self.tables = dict(tables or {})
        check_references(template, self.tables)
        self.layout = template.layout
        self.name = template.family
        self.description = template.identity.description
        self.money_fields = frozenset(c.key for c in self.layout.columns if c.kind == "money")
        self.citations = CITATIONS
        self._patterns = [re.compile(p, re.IGNORECASE) for p in template.identity.title_patterns]

    def matches_title(self, text: str) -> bool:
        return any(p.search(text) for p in self._patterns)

    def field_ids(self, page_id: str) -> list[str]:
        return [
            cell_id(self.name, page_id, row, column.key)
            for row in self.layout.row_keys
            for column in self.layout.columns
        ]

    def extraction_prompt(self, grounding: bool = False) -> str:
        layout, title = self.layout, self.template.identity.title
        if isinstance(layout.rows, ReadRows):
            n = layout.rows.read
            rows = (
                f'"rows" holds one entry for each of {n} rows, keyed "01" to "{n:02d}" in order '
                'from the top: "01" is the first row below the column headings. Give every '
                'entry; a row below the last printed row has "" for each cell.\n'
            )
        else:
            rows = '"rows" holds one entry for each row, keyed:\n' + "".join(
                f'- "{row.key}": the row printed "{row.printed}"\n' for row in layout.rows
            )
        columns = "".join(f'- {c.key}: the "{c.printed}" column\n' for c in layout.columns)
        body = (
            f'This is a scanned page with the table "{title}" ({layout.unit}). Read every cell '
            "of that table, and nothing outside it.\n\n"
            f"{rows}Each row has:\n{columns}"
            'A dash printed in a cell is copied as "-".\n\n'
        )
        return _prompt(body, grounding)

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
                cells[cell_id(self.name, page_id, row, column)] = cell
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
        cells = [texts.get(cell_id(self.name, page_id, row, c.key)) for c in self.layout.columns]
        return not all(t is not None and not t.strip() for t in cells)

    def _instances(
        self,
        page: PageExtraction,
        texts: Mapping[str, str | None],
        by_issue: Mapping[tuple[str, str | None], list[str]],
    ) -> Iterator[Instance]:
        page_id, issue = page.page_id, issue_of(page.page_id)
        for identity in self.template.identities:
            for row, column, where, above in _contexts(identity, self.layout):
                if row is not None and not self._used(texts, page_id, row):
                    continue
                terms = _linear(identity, row, column, above)
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
                    field_id = cell_id(table, on, term.row, term.column)
                    fields.append((field_id, term.coef, layout.step, column.kind))
                    if column.blank_means == "zero":
                        zero.add(field_id)
                yield Instance(
                    rule=f"{self.name}.{identity.id}",
                    where=where,
                    identity=identity,
                    fields=tuple(fields),
                    left=len(_terms(identity.left, row, column, 1, above)),
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
        where a blank is unknown, or not a figure. The tolerance is half a unit per printed
        value."""
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
                field_id = cell_id(self.name, page.page_id, row, column.key)
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
