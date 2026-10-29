"""The two labelling pages, served on this machine only, from a side's draw (labelling.draw).

- http://127.0.0.1:8765/ labels the 400 cells in the draw's order; ?pass=relabel labels the 40
  again, in their shuffled order, only once every cell has a first label and 24 hours have
  passed since the last one, and without showing the first labels.
- http://127.0.0.1:8765/check marks each of the 50 pages right table or wrong table for the family
  the sweep gave it.

What reaches the browser is the page image, the cell's box as a locator, its row and column as
the template names them, and the person's own answers in the same pass: never a model's read, a
verdict or the box's source. Each answer is appended to a file as it is given, so a session can
stop and resume; the last answer for a cell stands.

uv run python -m labelling.serve --side held_out  # then open http://127.0.0.1:8765/
"""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from archivist.pipeline import extract
from archivist.templates import real_test
from labelling.draw import DRAW_FILE

HERE = Path(__file__).parent
FILES = {"first": "labels.jsonl", "relabel": "relabels.jsonl", "check": "pages_checked.jsonl"}
CHOICES = ("value", "blank", "cant_read")
VERDICTS = ("right", "wrong")
WAIT = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


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
        self.boxes = {
            v.field_id: None if v.citation is None else v.citation.bbox.model_dump()
            for page in extract.load_predictions(records / "predictions.jsonl")
            for v in page.values
            if v.field_id in wanted
        }
        doc_types = real_test._types(real_test.CONFIG)
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
                "row": by_cell[cell]["row_named"],
                "column": by_cell[cell]["column_named"],
                "box": self.boxes.get(cell),
            }
            for n, cell in enumerate(order, 1)
        ]
        own = {
            cell: {"choice": a["choice"], "value": a["value"]}
            for cell, a in answers(self.path(which), "cell").items()
        }
        return {"pass": which, "blocked": None, "cells": shown, "answers": own}

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
        with self.lock, self.path(name).open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(line) + "\n")
            sink.flush()
            os.fsync(sink.fileno())

    def image(self, page: str) -> bytes:
        if page not in self.pages:
            raise ValueError(f"{page!r} is not drawn")
        return real_test.resolve(page, self.side, self.root).path.read_bytes()


def handler(labels: Labels) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == "/":
                    self._send(HERE / "label.html")
                elif url.path == "/check":
                    self._send(HERE / "check.html")
                elif url.path == "/api/cells":
                    which = query.get("pass", ["first"])[0]
                    if which not in ("first", "relabel"):
                        raise ValueError("pass is first or relabel")
                    self._json(labels.cells(which))
                elif url.path == "/api/pages":
                    self._json(labels.checks())
                elif url.path.startswith("/image/"):
                    self._bytes(labels.image(url.path.removeprefix("/image/")), "image/jpeg")
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except ValueError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                if self.path == "/api/answer":
                    self._json(labels.answer(body))
                elif self.path == "/api/check":
                    self._json(labels.check(body))
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
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    labels = Labels(args.side, args.labels or real_test.OUT_DIR / args.side / "labels")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(labels))
    print(f"labelling {args.side}: http://127.0.0.1:{args.port}/ and /check (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
