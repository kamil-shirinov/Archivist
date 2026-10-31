"""The local server: the review app as it is, plus the live API (P35).

    uv run python -m archivist.live [--port 8000]

It serves the repository's ui/, data/bundles/ and data/pages/ and nothing else (never .env, never a
dotfile), the way any file server rooted at the repository serves the published app, and adds:

    GET  /api/live/status          which modes are possible, whether each key is set (never its
                                   value), the caps and what is spent
    GET  /api/live/pages           the development pages it offers
    GET  /api/live/page?ref=       one page's size and label
    GET  /api/live/image?ref=      its scan
    POST /api/live/read            {page, mode, arm, speed}: begin a read -> {session}
    POST /api/live/cancel          {session}
    GET  /api/live/events/<id>     the read's events as server-sent events
    GET  /api/live/session/<id>    the same events as one JSON list

The app is told it is in the local app by a <meta name="archivist-live"> that this server adds to
the page it serves; ui/index.html itself has none, so the published site never offers a live read
and has no upload box (D12, D13). A page the app is asked for goes through the gate whatever the
browser says (pages.resolve), and a read is begun only by a JSON POST carrying a header no other
site's form or script can send, from this server's own origin, to a Host that is this machine.

Reads leave their bundles under results/scratch/live/, which git ignores; the server shows them to
the app beside the committed bundles by answering data/bundles/index.json with both.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import socket
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from PIL import Image

from archivist.live import pages
from archivist.live.session import LiveApp, Request, StartRefused

MARKER = '<meta name="archivist-live" content="/api/live/">'
SERVED = ("ui", "data/bundles", "data/pages")  # the only places files are served from
HEADER = "X-Archivist-Live"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".txt": "text/plain; charset=utf-8",
}


def safe_join(base: Path, relative: str) -> Path | None:
    """base/relative if it is a file inside base and no part of it is hidden or climbs out."""
    parts = [p for p in unquote(relative).split("/") if p]
    if any(p.startswith(".") or "\\" in p or "\0" in p for p in parts):
        return None
    path = base.joinpath(*parts)
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
            return None
    except OSError:
        return None
    return resolved


def merged_index(repo: Path, live_bundles: Path) -> bytes:
    """data/bundles/index.json as the committed one lists it, and the reads of this app beside."""
    index = json.loads((repo / "data/bundles/index.json").read_text(encoding="utf-8"))
    live = live_bundles / "index.json"
    if live.is_file():
        known = {r["run_id"] for r in index["runs"]}
        mine = json.loads(live.read_text(encoding="utf-8"))["runs"]
        index["runs"] += [r for r in mine if r["run_id"] not in known]
    return (json.dumps(index, indent=1) + "\n").encode("utf-8")


def make_handler(app: LiveApp, repo: Path, hosts: set[str]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "archivist-live"

        def log_message(self, *args: object) -> None:  # the console shows reads, not requests
            pass

        # --- answers ------------------------------------------------------------------------

        def _send(self, status: int, body: bytes, kind: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: object) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        # --- who may ask --------------------------------------------------------------------

        def _local(self) -> bool:
            """The Host is this machine's own (a page on another name that points here, DNS
            rebinding, is refused)."""
            host = (self.headers.get("Host") or "").lower()
            return host in hosts

        def _own_origin(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin.lower() in {f"http://{h}" for h in hosts}

        # --- routes -------------------------------------------------------------------------

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            if not self._local():
                return self._error(HTTPStatus.FORBIDDEN, "this server answers only on this machine")
            url = urlsplit(self.path)
            path, query = url.path, parse_qs(url.query)
            if path.startswith("/api/live/"):
                return self._api_get(path[len("/api/live/") :], query)
            if path in ("/", ""):
                return self._send(
                    HTTPStatus.FOUND, b"", "text/plain", {"Location": "/ui/"}
                )
            self._static(path)

        def do_POST(self) -> None:  # noqa: N802
            if not (self._local() and self._own_origin()):
                return self._error(HTTPStatus.FORBIDDEN, "this server answers only on this machine")
            if self.headers.get(HEADER) != "1" or "application/json" not in (
                self.headers.get("Content-Type") or ""
            ):
                return self._error(
                    HTTPStatus.FORBIDDEN, f"a read is asked for by the app, with {HEADER}"
                )
            path = urlsplit(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(length, 10_000)) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("a JSON object is expected")
            except ValueError as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            if path == "/api/live/read":
                return self._read(body)
            if path == "/api/live/cancel":
                cancelled = app.cancel(str(body.get("session")))
                return self._json(HTTPStatus.OK, {"cancelled": cancelled})
            self._error(HTTPStatus.NOT_FOUND, "no such endpoint")

        def _read(self, body: dict) -> None:
            try:
                request = Request(
                    page=str(body.get("page", "")),
                    mode=str(body.get("mode", "")),
                    arm=str(body.get("arm", "a")),
                    speed=float(body.get("speed", 1.0)),
                    workers=int(body.get("workers", 4)),
                )
                session = app.start(request)
            except pages.PageRefused as error:
                return self._error(HTTPStatus.FORBIDDEN, str(error))
            except StartRefused as error:
                return self._error(error.status, error.message)
            except (TypeError, ValueError) as error:
                return self._error(HTTPStatus.BAD_REQUEST, str(error))
            self._json(HTTPStatus.OK, {"session": session.id})

        def _api_get(self, route: str, query: dict) -> None:
            if route == "status":
                return self._json(HTTPStatus.OK, app.status())
            if route == "pages":
                return self._json(HTTPStatus.OK, {"groups": app.pages()})
            if route in ("page", "image"):
                try:
                    page = app.resolve((query.get("ref") or [""])[0])
                except pages.PageRefused as error:
                    return self._error(HTTPStatus.FORBIDDEN, str(error))
                if route == "image":
                    return self._send(HTTPStatus.OK, page.path.read_bytes(), "image/jpeg")
                with Image.open(page.path) as scan:
                    width, height = scan.size
                label = pages.issue_label(page.ref) if page.kind == "treasury" else page.page_id
                return self._json(
                    HTTPStatus.OK,
                    {"ref": page.ref, "page_id": page.page_id, "kind": page.kind, "label": label,
                     "width": width, "height": height},
                )
            if route.startswith("events/") or route.startswith("session/"):
                return self._events(route, query)
            self._error(HTTPStatus.NOT_FOUND, "no such endpoint")

        def _events(self, route: str, query: dict) -> None:
            kind, _, session_id = route.partition("/")
            session = app.get(session_id)
            if session is None:
                return self._error(HTTPStatus.NOT_FOUND, "no such read")
            if kind == "session":
                return self._json(HTTPStatus.OK, {"events": session.log.events()})
            after = int(self.headers.get("Last-Event-ID") or (query.get("after") or ["-1"])[0])
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                while True:
                    fresh, finished = session.log.since(after)
                    for event in fresh:
                        data = json.dumps(event)
                        self.wfile.write(f"id: {event['seq']}\ndata: {data}\n\n".encode())
                        after = event["seq"]
                    if finished:
                        break
                    if not fresh:
                        self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        # --- files --------------------------------------------------------------------------

        def _static(self, path: str) -> None:
            relative = path.lstrip("/")
            if path.rstrip("/") == "/ui":
                relative = "ui/index.html"
            elif relative.endswith("/") and (repo / relative).is_dir():
                relative += "index.html"
            if not any(relative == s or relative.startswith(s + "/") for s in SERVED):
                return self._error(HTTPStatus.NOT_FOUND, "not served")
            if relative == "data/bundles/index.json":
                return self._send(
                    HTTPStatus.OK, merged_index(repo, app.root / "bundles"), TYPES[".json"]
                )
            found = None
            for prefix, live in (("data/bundles/", "bundles"), ("data/pages/", "pages")):
                if relative.startswith(prefix):
                    found = safe_join(app.root / live, relative[len(prefix) :])
            found = found or safe_join(repo, relative)
            if found is None:
                return self._error(HTTPStatus.NOT_FOUND, "not found")
            body = found.read_bytes()
            if found == (repo / "ui" / "index.html").resolve():
                body = body.replace(b"</head>", MARKER.encode() + b"\n</head>", 1)
            kind = TYPES.get(found.suffix) or mimetypes.guess_type(found.name)[0]
            self._send(HTTPStatus.OK, body, kind or "application/octet-stream")

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(app: LiveApp, repo: Path, host: str, port: int) -> ThreadingHTTPServer:
    """The server, bound but not yet serving; port 0 takes a free one."""
    if host not in LOOPBACK:
        raise SystemExit(f"{host}: the live app is local only and listens on {LOOPBACK} alone")
    hosts: set[str] = set()  # filled once the port is known

    class Bound(Server):
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET

    server = Bound((host, port), make_handler(app, repo, hosts))
    bound = server.server_address[1]
    hosts.update({f"127.0.0.1:{bound}", f"localhost:{bound}", f"[::1]:{bound}"})
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--host", default="127.0.0.1", help="loopback only")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="open the app in a browser")
    args = parser.parse_args(argv)

    repo = Path.cwd()
    if not (repo / "ui" / "index.html").is_file() or not (repo / "config").is_dir():
        raise SystemExit("run this from the repository root: uv run python -m archivist.live")
    app = LiveApp()
    server = serve(app, repo, args.host, args.port)
    url = f"http://localhost:{server.server_address[1]}/ui/"
    status = app.status()
    print(f"Archivist, local app: {url}")
    for name, present in status["keys"].items():
        print(f"  {name}: {'set' if present else 'not set'}")
    live = "available" if status["live"]["available"] else "needs the keys above"
    replay = "available" if status["replay"]["available"] else "needs cache/ (nothing cached here)"
    print(f"  Live calls: {live}. Replay: {replay}. Development pages only. Ctrl-C stops.")
    if args.open:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    server.server_close()
