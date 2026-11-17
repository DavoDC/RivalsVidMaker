# copied from a sibling local GUI kit (capture.py)
"""Headless Chrome capture matrix for the GUI.

    python -m gui capture                                      every tab x every fixture at 1024 and 1440
    python -m gui capture --scenarios ready,empty --widths 1440
    python -m gui capture --url http://127.0.0.1:8476          an already running server (label "live")

For each fixture it starts `python -m gui --fixture NAME` on a spare port, drives ONE headless Chrome with
a fresh temporary profile over the DevTools protocol, and for every tab and width writes <name>.png and
<name>.dom.html under data/captures/<scenario>/ (gitignored). A visit FAILS when the page logs an [app-error],
shows the error banner (or has none, meaning the page never ran), has no build line in the footer, lacks the
FIXTURE banner in a fixture run, has an empty tab, did not select the requested tab, scrolls horizontally,
or shows undefined / NaN / Traceback in its visible text.

Read-only: it only navigates, measures and screenshots; it never clicks, so it cannot run an action.
Standard library only, apart from the gui package itself. Exit 0 all pass, 1 a visit failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from gui import fixtures, tabdefs, ui_check

REPO = Path(__file__).resolve().parents[2]


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")

TABS = tabdefs.KEYS
SCENARIOS = tuple(fixtures.SCENARIOS)
WIDTHS = (1024, 1440)  # desktop-only GUI: a small and a large desktop width
PHONE_MAX = 500

CHROME_CANDIDATES = (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                     r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")

BUILD_RE = re.compile(r'<[^>]*data-testid="build-line"[^>]*>\s*RivalsVidMaker\s+\S+')
_FORBIDDEN_TEXT = (re.compile(r"\bundefined\b"), re.compile(r"\bNaN\b"),
                   re.compile(r"Traceback"), re.compile(r"\[app-error\]"))


def find_chrome():
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    return shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")


def _tag(dom: str, attr: str, value: str) -> str:
    m = re.search(r'<[^>]*\b%s="%s"[^>]*>' % (attr, re.escape(value)), dom)
    return m.group(0) if m else ""


def bad_text_problems(visible: str, console: str) -> list[str]:
    """Forbidden strings in one visit: undefined, NaN, Traceback or [app-error] in the visible text,
    and [app-error] or Traceback in the console. Whole words only, so Nancy and nan-free pass."""
    problems = []
    for pattern in _FORBIDDEN_TEXT:
        hit = pattern.search(visible or "")
        if hit:
            problems.append("visible text shows %r" % hit.group(0))
    for literal in ("[app-error]", "Traceback"):
        if literal in (console or ""):
            line = next((l.strip() for l in console.splitlines() if literal in l), literal)
            problems.append("console logged %s: %s" % (literal, line))
    return problems


def verify_dom(tab: str, dom: str, console: str, width: int | None = None, fixture: str | None = None,
               visible: str | None = None) -> list[str]:
    """Problems found in one rendered visit (empty list means it passes)."""
    problems = []
    if "[app-error]" in (console or ""):
        line = next((l.strip() for l in console.splitlines() if "[app-error]" in l), "")
        problems.append("console logged an [app-error]: " + line)
    banner = _tag(dom, "id", "error-banner")
    if not banner:
        problems.append("no error banner element in the page (the page never ran)")
    elif not re.search(r"\bhidden\b", banner):
        problems.append("error banner is visible")
    if not BUILD_RE.search(dom):
        problems.append("footer has no build line")
    if fixture and 'data-testid="fixture-banner"' not in dom:
        problems.append("fixture run without the FIXTURE banner")
    if 'aria-selected="true"' not in _tag(dom, "data-testid", "nav-" + tab):
        problems.append("tab %s was not selected" % tab)
    length = re.search(r'data-content-len="(\d+)"', dom)
    if not length:
        problems.append("tab content was not measured")
    elif int(length.group(1)) == 0:
        problems.append("tab %s is empty" % tab)
    if width and width <= PHONE_MAX:
        scroll = re.search(r'data-hscroll="(yes|no)"', dom)
        if not scroll:
            problems.append("page did not report its horizontal overflow")
        elif scroll.group(1) == "yes":
            problems.append("page scrolls horizontally at %dpx wide" % width)
    if visible is not None:
        problems += bad_text_problems(visible, console)
    return problems


# -- a tiny DevTools client (stdlib) ------------------------------------------------------------

def encode_frame(payload: bytes, opcode: int = 0x1, mask: bytes | None = None) -> bytes:
    mask = mask if mask is not None else os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class WebSocket:
    def __init__(self, url, timeout=30.0):
        rest = url.split("://", 1)[1]
        host_port, _, path = rest.partition("/")
        host, _, port = host_port.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                           % (path, host_port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("DevTools closed during the handshake")
            buf += chunk
        head, _, self._buf = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OSError("DevTools refused the WebSocket upgrade")

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OSError("DevTools closed the connection")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send(self, obj):
        self.sock.sendall(encode_frame(json.dumps(obj).encode("utf-8")))

    def recv(self):
        message = b""
        while True:
            b1, b2 = self._read(2)
            opcode, length = b1 & 0x0F, b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length)
            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self.sock.sendall(encode_frame(payload, opcode=0xA))
                continue
            if opcode in (0x0, 0x1, 0x2):
                message += payload
                if b1 & 0x80:
                    return json.loads(message.decode("utf-8"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Session:
    def __init__(self, ws):
        self.ws, self._id, self.events = ws, 0, []

    def call(self, method, params=None, timeout=30.0):
        self._id += 1
        mine = self._id
        self.ws.sock.settimeout(timeout)
        self.ws.send({"id": mine, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self.ws.recv()
            if msg is None:
                raise OSError("DevTools closed while waiting for " + method)
            if msg.get("id") == mine:
                if "error" in msg:
                    raise OSError("%s: %s" % (method, msg["error"].get("message")))
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
        raise OSError("timed out waiting for " + method)

    def pump(self, seconds):
        self.ws.sock.settimeout(0.2)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                msg = self.ws.recv()
            except (socket.timeout, TimeoutError):
                continue
            if msg is None:
                return
            if "method" in msg:
                self.events.append(msg)
        self.ws.sock.settimeout(30.0)

    def evaluate(self, expression):
        res = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return res.get("result", {}).get("value")


def console_text(events) -> str:
    lines = []
    for e in events:
        if e.get("method") == "Runtime.consoleAPICalled":
            args = e["params"].get("args", [])
            lines.append(" ".join(str(a.get("value", a.get("description", ""))) for a in args))
        elif e.get("method") == "Runtime.exceptionThrown":
            d = e["params"].get("exceptionDetails", {})
            lines.append("[app-error] uncaught: %s %s" % (d.get("text", ""),
                                                          d.get("exception", {}).get("description", "")))
    return "\n".join(lines)


def ready_js(tab: str) -> str:
    sel = '[data-testid="tab-%s"]' % tab
    return ('document.readyState==="complete" && !!document.querySelector(\'%s\')'
            ' && document.querySelector(\'%s\').innerText.trim().length>0' % (sel, sel))


def measure_js(tab: str) -> str:
    sel = '[data-testid="tab-%s"]' % tab
    return ('(function(){var d=document.documentElement,c=document.querySelector(\'%s\');'
            'd.setAttribute("data-hscroll",d.scrollWidth>d.clientWidth?"yes":"no");'
            'd.setAttribute("data-content-len",String(c?c.innerText.trim().length:0));})()' % sel)


class Browser:
    """One headless Chrome with a fresh temporary profile."""

    def __init__(self, chrome):
        self.profile = tempfile.mkdtemp(prefix="rvm-capture-")
        self.proc = subprocess.Popen(
            [chrome, "--headless=new", "--mute-audio", "--disable-gpu", "--no-first-run",
             "--user-data-dir=" + self.profile, "--remote-debugging-port=0", "--hide-scrollbars", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        marker = Path(self.profile) / "DevToolsActivePort"
        end = time.monotonic() + 20
        port = None
        while time.monotonic() < end and port is None:
            if marker.exists():
                lines = marker.read_text(encoding="utf-8").splitlines()
                if len(lines) >= 2 and lines[0].isdigit():
                    port = int(lines[0])
            if self.proc.poll() is not None:
                raise OSError("Chrome exited before DevTools was ready")
            time.sleep(0.1)
        if port is None:
            raise OSError("Chrome DevTools did not come up")
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=10).read())
        page = next(t for t in targets if t.get("type") == "page")
        self.ws = WebSocket(page["webSocketDebuggerUrl"])
        self.session = Session(self.ws)
        for domain in ("Page", "Runtime", "Log"):
            self.session.call(domain + ".enable")

    def visit(self, url, png, width, tab, height=900, eval_js=None):
        """Load one tab; returns (dom, console text, visible text). Writes the screenshot to png."""
        s = self.session
        s.events = []
        s.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                                                      "deviceScaleFactor": 1, "mobile": False})
        s.call("Page.navigate", {"url": url})
        end = time.monotonic() + 25
        while time.monotonic() < end and not s.evaluate(ready_js(tab)):
            s.pump(0.4)
        s.pump(1.5)
        if eval_js:  # optional page script run before the shot
            s.evaluate(eval_js)
            s.pump(1.5)
        s.evaluate(measure_js(tab))
        dom = s.evaluate("document.documentElement.outerHTML") or ""
        visible = s.evaluate("document.body ? document.body.innerText : ''") or ""
        size = s.call("Page.getLayoutMetrics")["cssContentSize"]
        shot = s.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True,
                                                  "clip": {"x": 0, "y": 0, "width": width,
                                                           "height": min(size["height"], 6000), "scale": 1}})
        png.write_bytes(base64.b64decode(shot["data"]))
        return "<!DOCTYPE html>" + dom, console_text(s.events), visible

    def close(self):
        self.ws.close()
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DemoServer:
    def __init__(self, scenario):
        self.port = free_port()
        argv = [sys.executable, "-m", "gui", "--fixture", scenario, "--port", str(self.port),
                "--no-watch", "--no-browser"]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("NICEGUI", "PYTEST"))}
        self.proc = subprocess.Popen(argv, cwd=str(REPO / "src"), env=env, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        end = time.monotonic() + 40
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                raise OSError("demo server (%s) exited early" % scenario)
            try:
                if urllib.request.urlopen(self.base + "/api/build", timeout=2).status == 200:
                    return
            except OSError:
                time.sleep(0.3)
        self.stop()
        raise OSError("demo server (%s) did not start" % scenario)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port  # not localhost: IPv6 attempt costs 2s per request

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def tab_url(base: str, tab: str) -> str:
    """The server routes /tab/<key> (a deep link that paints that tab first); ?tab= is client-side only."""
    return "%s/tab/%s" % (base, tab)


def capture(browser, base, outdir, tabs, widths, fixture=None, eval_js=None):
    outdir.mkdir(parents=True, exist_ok=True)
    results = {}
    for width in widths:
        for tab in tabs:
            name = "%s-%d" % (tab, width)
            png = outdir / (name + ".png")
            dom, console, visible = browser.visit(tab_url(base, tab), png, width, tab, eval_js=eval_js)
            (outdir / (name + ".dom.html")).write_text(dom, encoding="utf-8")
            problems = verify_dom(tab, dom, console, width, fixture, visible)
            if not png.exists() or png.stat().st_size == 0:
                problems.append("no screenshot was written")
            results[name] = problems
    return results


def painted_problems(browser, base, tabs, scratch: Path, width=1440, keep=None) -> list[str]:
    """ui_check over one running server: the row testids painted on each tab against the state rows.
    keep(testid) limits both sides to the rows it accepts (verify keeps only opted-in tabs' rows)."""
    state = json.loads(urllib.request.urlopen(base + "/state.json", timeout=10).read())
    state_ids = ui_check.painted_rows(ui_check.state_row_ids(state))
    painted = set()
    for tab in tabs:
        dom, _console, _visible = browser.visit(tab_url(base, tab), scratch / (tab + ".png"), width, tab)
        painted |= ui_check.painted_rows(ui_check.extract_testids(dom))
    if keep is not None:
        state_ids = {t for t in state_ids if keep(t)}
        painted = {t for t in painted if keep(t)}
    return ui_check.problems(state_ids, painted)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Headless Chrome capture of every GUI tab; exit 0 pass, 1 fail, 2 could not run.")
    ap.add_argument("--url", help="capture an already running server instead of starting fixtures (label: live)")
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--tabs", default=",".join(TABS))
    ap.add_argument("--widths", default=",".join(str(w) for w in WIDTHS))
    ap.add_argument("--out", default=str(REPO / "data" / "captures"))
    ap.add_argument("--eval", dest="eval_js", default=None,
                    help="JS run in each page after it is ready and before the screenshot (Chrome is muted)")
    args = ap.parse_args(argv)
    chrome = find_chrome()
    if not chrome:
        _say("Could not run: Chrome was not found.")
        return 2
    tabs = [t for t in args.tabs.split(",") if t]
    widths = [int(w) for w in args.widths.split(",") if w]
    scenarios = ["live"] if args.url else [s for s in args.scenarios.split(",") if s]
    started = time.monotonic()
    failed = total = 0
    browser = None
    try:
        browser = Browser(chrome)
        for scenario in scenarios:
            server = None if args.url else DemoServer(scenario)
            try:
                base = args.url.rstrip("/") if args.url else server.base
                results = capture(browser, base, Path(args.out) / scenario, tabs, widths,
                                  None if args.url else scenario, args.eval_js)
            finally:
                if server:
                    server.stop()
            for name, problems in results.items():
                total += 1
                failed += 1 if problems else 0
                _say("  %s %s/%s" % ("FAIL" if problems else "ok  ", scenario, name))
                for p in problems:
                    _say("       - " + p)
    except Exception as exc:
        _say("Could not run: %s" % exc)
        return 2
    finally:
        if browser:
            browser.close()
    _say("Captured %d visits to %s in %.1fs: %s" % (total, args.out, time.monotonic() - started,
                                                     "FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
