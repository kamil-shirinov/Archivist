"""The labelling pages, served on this machine only, from a side's draw (labelling.draw) and its
layout record (results/real_test/<side>/layout_check.json).

- http://127.0.0.1:8765/ labels the 400 cells in the draw's order; ?pass=relabel labels the 40
  again, in their shuffled order, only once every cell has a first label and 24 hours have
  passed since the last one, and without showing the first labels.
- http://127.0.0.1:8765/check marks each of the 50 pages right table or wrong table for the family
  the sweep gave it.
- http://127.0.0.1:8765/layout marks each deep-check page the OCR layer could not settle same
  layout, changed layout or different table, beside its template's expected columns, with a
  note. It needs no draw; the other two wait for one.

What reaches the browser is the page image, the cell's box as a locator, its row's label and
heading as the first read returned them (Deviations) with its position as a hint, which occurrence
of that label the row is on its page where the label repeats (counted in the draw's row order from
the top), its column's heading, and the person's own answers in the same pass: never a figure the
model read, a verdict or the box's source. The answer is the printed value, blank, can't read, row not on the page, or
column not on this page. Each answer is appended to a file as it is given, so a session can
stop and resume; the last answer for a cell stands.

uv run python -m labelling.serve --side held_out  # then open http://127.0.0.1:8765/
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from archivist.pipeline import extract
from archivist.templates import real_test
from labelling.draw import DRAW_FILE, names

HERE = Path(__file__).parent
FILES = {"first": "labels.jsonl", "relabel": "relabels.jsonl", "check": "pages_checked.jsonl"}
CHOICES = ("value", "blank", "cant_read", "not_on_page", "column_not_on_page")
VERDICTS = ("right", "wrong")
LAYOUTS = ("same", "changed", "different_table")
LAYOUT_RECORD = "layout_check.json"
LAYOUT_ANSWERS = "layouts_checked.jsonl"
WAIT = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def counted(rows: Mapping[str, Mapping[str, str]]) -> dict[str, tuple[int, int]]:
    """For each row of a page whose printed label repeats on it: which occurrence of the label the
    row is, counted in the draw's row order (labelling.draw.names) from the top, and how many rows
    of the page have the label. Labels are compared with their spaces collapsed; a row the read
    gave no label is not counted, and a label that occurs once is not listed."""
    labels = {key: " ".join(row["label"].split()) for key, row in rows.items()}
    totals = Counter(label for label in labels.values() if label)
    seen: Counter[str] = Counter()
    found = {}
    for key, label in labels.items():
        if label and totals[label] > 1:
            seen[label] += 1
            found[key] = (seen[label], totals[label])
    return found


def answers(path: Path, key: str) -> dict[str, dict]:
    """The standing answer for each cell or page in an answers file: the last one given."""
    if not path.exists():
        return {}
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {line[key]: line for line in lines}


class Labels:
    """A side's draw, its boxes and its answer files; the only state the pages read or write."""

    def __init__(self, side: str, labels: Path, root: Path = real_test.DEFAULT_ROOT) -> None:
        self.side, self.labels, self.root = side, labels, root
        self.draw = json.loads((labels / DRAW_FILE).read_text(encoding="utf-8"))
        if self.draw["side"] != side:
            raise ValueError(f"{labels / DRAW_FILE} is the {self.draw['side']} side's draw")
        records = real_test.OUT_DIR / side
        wanted = {s["cell"] for s in self.draw["sample"]}
        read = {p.page_id: p for p in extract.load_predictions(records / "predictions.jsonl")}
        self.boxes = {
            v.field_id: None if v.citation is None else v.citation.bbox.model_dump()
            for page in read.values()
            for v in page.values
            if v.field_id in wanted
        }
        doc_types = real_test._types(real_test.CONFIG)
        # only row labels come out of the read here, as in the draw: no figure, verdict or box
        self.repeats = {
            page: counted(names(doc_types[read[page].doc_type], read[page]))
            for page in {s["page"] for s in self.draw["sample"]}
        }
        self.titles = {f: doc_types[f].template.identity.title for f in real_test.FAMILIES}
        self.units = {f: doc_types[f].layout.unit for f in real_test.FAMILIES}
        self.pages = {s["page"] for s in self.draw["sample"]} | {
            p["page"] for p in self.draw["pages_checked"]
        }
        self.lock = threading.Lock()

    def path(self, name: str) -> Path:
        return self.labels / FILES[name]

    def blocked(self, which: str) -> str | None:
        """Why the relabel pass cannot start yet, or None."""
        if which != "relabel":
            return None
        first = answers(self.path("first"), "cell")
        missing = sum(s["cell"] not in first for s in self.draw["sample"])
        if missing:
            return f"{missing} cells have no first label yet: the relabel pass comes after them all"
        last = max(datetime.fromisoformat(a["labelled_at"]) for a in first.values())
        if _now() < last + WAIT:
            return f"the relabel pass opens at {(last + WAIT).isoformat(timespec='minutes')}"
        return None

    def cells(self, which: str) -> dict:
        reason = self.blocked(which)
        if reason:
            return {"pass": which, "blocked": reason, "cells": [], "answers": {}}
        by_cell = {s["cell"]: s for s in self.draw["sample"]}
        order = self.draw["relabel"] if which == "relabel" else [s["cell"] for s in self.draw["sample"]]
        shown = [
            {
                "n": n,
                "cell": cell,
                "page": by_cell[cell]["page"],
                "title": self.titles[by_cell[cell]["family"]],
                "unit": self.units[by_cell[cell]["family"]],
                "row_label": by_cell[cell]["row_label"],
                "row_heading": by_cell[cell]["row_heading"],
                "row_hint": by_cell[cell]["row_hint"],
                "occurrence": self._occurrence(by_cell[cell]),
                "column": by_cell[cell]["column_heading"],
                "box": self.boxes.get(cell),
            }
            for n, cell in enumerate(order, 1)
        ]
        own = {
            cell: {"choice": a["choice"], "value": a["value"]}
            for cell, a in answers(self.path(which), "cell").items()
        }
        return {"pass": which, "blocked": None, "cells": shown, "answers": own}

    def _occurrence(self, drawn: dict) -> dict[str, int] | None:
        """{"n": 8, "of": 10} where the cell's row label repeats on its page, else None."""
        found = self.repeats[drawn["page"]].get(drawn["row"])
        return None if found is None else {"n": found[0], "of": found[1]}

    def checks(self) -> dict:
        shown = [
            {"n": n, "page": p["page"], "family": p["family"], "title": self.titles[p["family"]]}
            for n, p in enumerate(self.draw["pages_checked"], 1)
        ]
        own = {
            page: {"verdict": a["verdict"]}
            for page, a in answers(self.path("check"), "page").items()
        }
        return {"pages": shown, "answers": own}

    def answer(self, body: dict) -> dict:
        which, cell, choice = body.get("pass"), body.get("cell"), body.get("choice")
        if which not in ("first", "relabel") or self.blocked(which):
            raise ValueError("not a pass open for labelling")
        allowed = self.draw["relabel"] if which == "relabel" else [s["cell"] for s in self.draw["sample"]]
        if cell not in allowed:
            raise ValueError(f"{cell!r} is not drawn for this pass")
        if choice not in CHOICES:
            raise ValueError(f"choice must be one of {CHOICES}")
        value = body.get("value") if choice == "value" else None
        if choice == "value" and not (isinstance(value, str) and value.strip()):
            raise ValueError("a printed value is typed as printed, not left empty")
        line = {
            "cell": cell,
            "choice": choice,
            "value": value.strip() if value else None,
            "labelled_at": _now().isoformat(timespec="seconds"),
        }
        self._append(which, line)
        return line

    def check(self, body: dict) -> dict:
        page, verdict = body.get("page"), body.get("verdict")
        if page not in {p["page"] for p in self.draw["pages_checked"]}:
            raise ValueError(f"{page!r} is not drawn for the check")
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}")
        line = {"page": page, "verdict": verdict, "checked_at": _now().isoformat(timespec="seconds")}
        self._append("check", line)
        return line

    def _append(self, name: str, line: dict) -> None:
        with self.lock:
            append(self.path(name), line)

    def image(self, page: str) -> bytes:
        if page not in self.pages:
            raise ValueError(f"{page!r} is not drawn")
        return real_test.resolve(page, self.side, self.root).path.read_bytes()


def append(path: Path, line: dict) -> None:
    """One answer appended and flushed to disk before the page is told it is kept."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(line) + "\n")
        sink.flush()
        os.fsync(sink.fileno())


class Layouts:
    """The deep-check pages whose column layout a person checks by eye: those the OCR layer could
    not settle in the side's layout record (layout_check.json, Deviations). Needs no draw."""

    def __init__(
        self, side: str, labels: Path, record: Path | None = None, root: Path = real_test.DEFAULT_ROOT
    ) -> None:
        self.side, self.root = side, root
        record = record or real_test.OUT_DIR / side / LAYOUT_RECORD
        found = json.loads(record.read_text(encoding="utf-8"))["pages"]
        self.pages = [p for p in found if p["check_by_eye"]]
        doc_types = real_test._types(real_test.CONFIG)
        self.expected = {
            f: {
                "title": doc_types[f].template.identity.title,
                "columns": [c.printed for c in doc_types[f].layout.columns],
            }
            for f in real_test.FAMILIES
        }
        self.path = labels / LAYOUT_ANSWERS
        self.lock = threading.Lock()

    def state(self) -> dict:
        shown = [
            {"n": n, "page": p["page"], "family": p["family"], "ocr": p["ocr"], **self.expected[p["family"]]}
            for n, p in enumerate(self.pages, 1)
        ]
        own = {
            page: {"layout": a["layout"], "note": a["note"]}
            for page, a in answers(self.path, "page").items()
        }
        return {"pages": shown, "answers": own}

    def mark(self, body: dict) -> dict:
        page, layout, note = body.get("page"), body.get("layout"), body.get("note") or ""
        if page not in {p["page"] for p in self.pages}:
            raise ValueError(f"{page!r} is not a page to check by eye")
        if layout not in LAYOUTS:
            raise ValueError(f"layout must be one of {LAYOUTS}")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("a note is text, at most 2,000 characters")
        line = {
            "page": page,
            "layout": layout,
            "note": note.strip(),
            "checked_at": _now().isoformat(timespec="seconds"),
        }
        with self.lock:
            append(self.path, line)
        return line

    def image(self, page: str) -> bytes:
        if page not in {p["page"] for p in self.pages}:
            raise ValueError(f"{page!r} is not a page to check by eye")
        return real_test.resolve(page, self.side, self.root).path.read_bytes()


def handler(labels: Labels | None, layouts: Layouts | None = None) -> type[BaseHTTPRequestHandler]:
    def need(what: object, name: str) -> object:
        if what is None:
            raise ValueError(f"no {name} yet")
        return what

    def image(page: str) -> bytes:
        for source in (labels, layouts):
            if source is not None:
                try:
                    return source.image(page)
                except ValueError:
                    pass
        raise ValueError(f"{page!r} is not a page to show")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == "/":
                    self._send(HERE / "label.html")
                elif url.path == "/check":
                    self._send(HERE / "check.html")
                elif url.path == "/layout":
                    self._send(HERE / "layout.html")
                elif url.path == "/api/cells":
                    which = query.get("pass", ["first"])[0]
                    if which not in ("first", "relabel"):
                        raise ValueError("pass is first or relabel")
                    self._json(need(labels, "draw").cells(which))
                elif url.path == "/api/pages":
                    self._json(need(labels, "draw").checks())
                elif url.path == "/api/layouts":
                    self._json(need(layouts, "layout record").state())
                elif url.path.startswith("/image/"):
                    self._bytes(image(url.path.removeprefix("/image/")), "image/jpeg")
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except ValueError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                if self.path == "/api/answer":
                    self._json(need(labels, "draw").answer(body))
                elif self.path == "/api/check":
                    self._json(need(labels, "draw").check(body))
                elif self.path == "/api/layout":
                    self._json(need(layouts, "layout record").mark(body))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except ValueError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def _send(self, path: Path) -> None:
            self._bytes(path.read_bytes(), "text/html; charset=utf-8")

        def _json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._bytes(json.dumps(data).encode(), "application/json", status)

        def _bytes(self, data: bytes, kind: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:  # quiet
            pass

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--side", choices=real_test.SIDES, required=True)
    parser.add_argument("--labels", type=Path, help="default results/real_test/<side>/labels")
    parser.add_argument("--layouts", type=Path, help=f"default results/real_test/<side>/{LAYOUT_RECORD}")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    directory = args.labels or real_test.OUT_DIR / args.side / "labels"
    record = args.layouts or real_test.OUT_DIR / args.side / LAYOUT_RECORD
    labels = Labels(args.side, directory) if (directory / DRAW_FILE).exists() else None
    layouts = Layouts(args.side, directory, record) if record.exists() else None
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(labels, layouts))
    base = f"http://127.0.0.1:{args.port}"
    print(f"labelling {args.side} (Ctrl-C to stop):")
    print(f"  {base}/ and {base}/check" + ("" if labels else ": no draw yet"))
    print(f"  {base}/layout" + ("" if layouts else f": no {record}"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
