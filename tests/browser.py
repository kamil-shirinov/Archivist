"""A small Chromium driver for the UI test: headless Chromium or Chrome over the DevTools protocol,
in the standard library alone (a WebSocket client of a few dozen lines), so the test adds no
dependency, and a static server on localhost for the repository as GitHub Pages would serve it.

    with serve(ROOT) as base, Browser() as browser:
        tab = browser.tab()
        tab.open(base + "/ui/#overview", width=1440, height=900, dark=True)
        tab.screenshot("overview.png")
        assert not tab.errors

Nothing here leaves the machine: the server listens on 127.0.0.1 and the browser is pointed only at
it. find_browser() looks where Playwright, Chrome and Chromium put themselves; ARCHIVIST_BROWSER
names a binary explicitly.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import glob
import http.client
import http.server
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

BROWSER_PATTERNS = (
    "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-arm64/"
    "chrome-headless-shell",
    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell",
    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
BROWSER_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def find_browser() -> str | None:
    """A Chromium or Chrome binary on this machine, the newest where there are several."""
    if (named := os.environ.get("ARCHIVIST_BROWSER")) and Path(named).exists():
        return named
    for pattern in BROWSER_PATTERNS:
        found = sorted(glob.glob(os.path.expanduser(pattern)))
        if found:
            return found[-1]
    for name in BROWSER_NAMES:
        if path := shutil.which(name):
            return path
    return None


# --- a static server for the repository -----------------------------------------------------------


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass


class _Server(http.server.ThreadingHTTPServer):
    request_queue_size = (
        256  # a page opens a dozen modules at once; the default queue of 5 drops some
    )
    daemon_threads = True


@contextlib.contextmanager
def serve(root: Path) -> Iterator[str]:
    """The repository served as files on localhost; yields its base URL."""
    handler = functools.partial(_Quiet, directory=str(root))
    server = _Server(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


# --- a WebSocket client: just enough for the DevTools protocol ------------------------------------


class _Socket:
    def __init__(self, url: str) -> None:
        match = re.fullmatch(r"ws://([^:/]+):(\d+)(/.*)", url)
        assert match, url
        host, port, path = match.group(1), int(match.group(2)), match.group(3)
        self.sock = socket.create_connection((host, port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("the browser closed the connection")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.decode(errors="replace"))

    def _read(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("the browser closed the connection")
            data += chunk
        return data

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self) -> str:
        message = b""
        while True:
            first, second = self._read(2)
            opcode, length = first & 0x0F, second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length)  # a server's frames are never masked
            if opcode == 0x9:  # ping
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if opcode == 0x8:
                raise ConnectionError("the browser closed the page")
            message += payload
            if first & 0x80:
                return message.decode()

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()


# --- the browser and its tabs ---------------------------------------------------------------------


class Tab:
    """One page. Console errors, uncaught exceptions and failed requests collect in `errors`."""

    def __init__(self, ws_url: str) -> None:
        self.ws = _Socket(ws_url)
        self.next_id = 0
        self.errors: list[str] = []
        self.messages: list[str] = []
        self.requests: list[str] = []
        for method in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            self.call(method)

    def call(self, method: str, **params: object) -> dict:
        self.next_id += 1
        want = self.next_id
        self.ws.send(json.dumps({"id": want, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == want:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self._event(message)

    def _event(self, message: dict) -> None:
        method, params = message.get("method"), message.get("params", {})
        if method == "Runtime.consoleAPICalled":
            text = " ".join(str(a.get("value", a.get("description", ""))) for a in params["args"])
            self.messages.append(f"{params['type']}: {text}")
            if params["type"] in ("error", "assert"):
                self.errors.append(f"console.{params['type']}: {text}")
        elif method == "Runtime.exceptionThrown":
            detail = params["exceptionDetails"]
            what = detail.get("exception", {}).get("description") or detail.get("text", "")
            self.errors.append(f"uncaught: {what}")
        elif method == "Log.entryAdded":
            entry = params["entry"]
            if entry["level"] == "error":
                self.errors.append(f"log: {entry['text']} {entry.get('url', '')}")
        elif method == "Network.requestWillBeSent":
            self.requests.append(params["request"]["url"])
        elif method == "Network.loadingFailed" and not params.get("canceled"):
            self.errors.append(f"request failed: {params.get('errorText')}")

    def pump(self, seconds: float) -> None:
        """Let events arrive for a while."""
        self.ws.sock.settimeout(0.05)
        end = time.time() + seconds
        try:
            while time.time() < end:
                try:
                    self._event(json.loads(self.ws.recv()))
                except (TimeoutError, socket.timeout):
                    continue
        finally:
            self.ws.sock.settimeout(60)

    def eval(self, js: str) -> object:
        result = self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            raise RuntimeError(detail.get("exception", {}).get("description", detail["text"]))
        return result["result"].get("value")

    def wait_for(self, js: str, timeout: float = 30.0) -> None:
        """Wait until the JavaScript expression is truthy."""
        end = time.time() + timeout
        last = None
        while time.time() < end:
            try:
                if self.eval(js):
                    return
            except RuntimeError as error:  # the page is between two documents
                last = error
            self.pump(0.1)
        raise TimeoutError(
            f"still false after {timeout}s: {js}\nlast error: {last}\nerrors so far: {self.errors}"
        )

    def open(
        self,
        url: str,
        width: int = 1440,
        height: int = 900,
        dark: bool = False,
        mobile: bool = False,
        still: bool = False,
    ) -> None:
        """Navigate to url in a window of this size, in light or dark, and with `still` as if the
        visitor asked for reduced motion (nothing animates, so a screenshot is the settled page)."""
        self.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=mobile,
        )
        self.call(
            "Emulation.setEmulatedMedia",
            features=[
                {"name": "prefers-color-scheme", "value": "dark" if dark else "light"},
                {"name": "prefers-reduced-motion", "value": "reduce" if still else "no-preference"},
            ],
        )
        self.call("Page.navigate", url=url)
        self.wait_for("document.readyState === 'complete'")

    def screenshot(self, path: Path | str, full_page: bool = False) -> None:
        shot = self.call("Page.captureScreenshot", format="png", captureBeyondViewport=full_page)
        Path(path).write_bytes(base64.b64decode(shot["data"]))

    def close(self) -> None:
        self.ws.close()


class Browser:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_browser()
        if self.binary is None:
            raise FileNotFoundError("no Chromium or Chrome found; set ARCHIVIST_BROWSER")
        self.profile = tempfile.mkdtemp(prefix="archivist-browser-")
        self.process: subprocess.Popen | None = None
        self.port = 0
        self.tabs: list[Tab] = []

    def __enter__(self) -> Browser:
        self.process = subprocess.Popen(
            [
                self.binary,
                "--headless=new" if "headless" not in self.binary else "--headless",
                "--remote-debugging-port=0",
                f"--user-data-dir={self.profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-sandbox",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert self.process.stderr is not None
        end = time.time() + 30
        while time.time() < end:
            line = self.process.stderr.readline()
            if match := re.search(r"DevTools listening on ws://127\.0\.0\.1:(\d+)/", line):
                self.port = int(match.group(1))
                break
            if not line and self.process.poll() is not None:
                raise RuntimeError("the browser exited before it was ready")
        else:
            raise TimeoutError("the browser did not say where it listens")
        return self

    def tab(self) -> Tab:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        connection.request("PUT", "/json/new?about:blank")
        target = json.loads(connection.getresponse().read())
        connection.close()
        tab = Tab(target["webSocketDebuggerUrl"])
        self.tabs.append(tab)
        return tab

    def __exit__(self, *exc: object) -> None:
        for tab in self.tabs:
            tab.close()
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
        shutil.rmtree(self.profile, ignore_errors=True)
