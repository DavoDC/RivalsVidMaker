"""One tab in one state, as a PNG: the shot verb.

    PYTHONPATH=src python -m gui shot compile --fixture plan click:Compile
    PYTHONPATH=src python -m gui shot compile --url http://127.0.0.1:8476 wait:2

Starts a fixture server (or connects to --url, which must already be running), drives one headless
Chrome through capture.Browser, runs the optional STEPs on the page, then writes the PNG to
data/captures/shot/<tab>-<width>.png (gitignored) and prints its absolute path, the toast texts and
the first 1500 characters of the page text.

STEP grammar: click:<button text>  tap:<label>  select:<css>=<option>  fill:<css>=<value>  wait:<seconds>
  eval:<javascript expression>  (prints EVAL <expression> => <result as JSON>; a thrown error exits 1)
Exit 0 ok, 1 server or browser failure or a thrown eval, 2 bad arguments, 3 a step target missing (MISSING: <step>).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from gui import capture, fixtures, tabdefs

SHOT_DIR = capture.REPO / "data" / "captures" / "shot"
SETTLE_BUDGET_S = 60.0  # per click or select: sample the header until it says Idle twice
TEXT_CHARS = 1500
DEFAULT_FIXTURE = "ready"

BODY_JS = "document.body ? document.body.innerText : ''"
HDR_JS = "(document.querySelector('header')||document.body).innerText.slice(0,200)"
TOAST_JS = "JSON.stringify([...document.querySelectorAll('.q-notification__message, #rvm-toast')].map(e=>(e.innerText||'').trim()))"
ICON_WORD = re.compile(r"^[a-z_]+$")


class Missing(Exception):
    """A step's target is not on the page. Carries the step as written."""

    def __init__(self, step: str, candidates: str = ""):
        super().__init__(step)
        self.step, self.candidates = step, candidates


def shot_path(tab: str, width: int) -> Path:
    return SHOT_DIR / ("%s-%d.png" % (tab, width))


def parse_step(raw: str):
    """Return ('click', text) | ('tap', label) | ('select', css, option) | ('fill', css, value) | ('wait', seconds)
    | ('eval', expression).
    Raises ValueError for an unknown prefix or a malformed step."""
    kind, sep, rest = raw.partition(":")
    if not sep or not rest:
        raise ValueError("bad step: %r" % raw)
    if kind in ("click", "tap", "eval"):
        return (kind, rest)
    if kind in ("select", "fill"):
        target, eq, value = rest.rpartition("=")
        if not eq or not target or (kind == "select" and not value):
            raise ValueError("bad %s step, want %s:<css>=<value>: %r" % (kind, kind, raw))
        return (kind, target, value)
    if kind == "wait":
        try:
            return ("wait", float(rest))
        except ValueError:
            raise ValueError("bad wait step, want wait:<seconds>: %r" % raw) from None
    raise ValueError("unknown step kind: %r" % raw)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m gui shot",
                                 description="One tab in one state as a PNG, plus its toasts and page text.")
    ap.add_argument("tab", choices=tabdefs.KEYS)
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--fixture", default=None, help="fixture scenario to serve (default: %s)" % DEFAULT_FIXTURE)
    source.add_argument("--url", default=None, help="a server already running at this address")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--no-settle", action="store_true", dest="no_settle",
                    help="after a click or select, pump 1 s instead of waiting for Idle (capture a running job)")
    ap.add_argument("steps", nargs="*", metavar="STEP", help="click:, tap:, select:, fill:, wait: steps")
    args = ap.parse_intermixed_args(argv)
    if args.fixture is None and args.url is None:
        args.fixture = DEFAULT_FIXTURE
    if args.fixture is not None and args.fixture not in fixtures.SCENARIOS:
        ap.error("unknown fixture: %s" % args.fixture)
    for raw in args.steps:
        try:
            parse_step(raw)
        except ValueError as exc:
            ap.error(str(exc))
    return args


# -- the step driver (ported from the scratch probe; the browser helpers come from capture) ----------

def _say(text: str) -> None:
    sys.stdout.write(text + "\n")


def rect_js(finder: str) -> str:
    """JS that scrolls the element found by `finder` into view and returns its centre as JSON, or 'null'."""
    return ("(function(){const el=(%s);if(!el)return 'null';el.scrollIntoView({block:'center'});"
            "const r=el.getBoundingClientRect();return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()" % finder)


def find_button_js(text: str) -> str:
    return rect_js("[...document.querySelectorAll('button')].find(b=>(b.innerText||'').includes(%s)"
                   "&&b.getBoundingClientRect().width>0)" % json.dumps(text))


def find_option_js(text: str) -> str:
    return rect_js("[...document.querySelectorAll('[role=option], .q-item')].find(e=>(e.textContent||'').trim()===%s"
                   "&&e.getBoundingClientRect().width>0)" % json.dumps(text))


def find_checkbox_js(text: str) -> str:
    return rect_js("[...document.querySelectorAll('.q-checkbox, .q-toggle, [role=checkbox], [role=switch]')]"
                   ".find(e=>(e.textContent||'').includes(%s)&&e.getBoundingClientRect().width>0)" % json.dumps(text))


def find_selector_js(css: str) -> str:
    return rect_js("document.querySelector(%s)" % json.dumps(css))


def native_select_js(css: str, text: str) -> str:
    return ("(function(){const s=document.querySelector(%s);if(!s||s.tagName!=='SELECT')return 'no';"
            "const o=[...s.options].find(o=>o.text.trim()===%s);if(!o)return 'no';s.value=o.value;"
            "s.dispatchEvent(new Event('change',{bubbles:true}));return 'ok';})()" % (json.dumps(css), json.dumps(text)))


def visible_texts_js(css: str) -> str:
    return ("JSON.stringify([...document.querySelectorAll(%s)].filter(e=>e.getBoundingClientRect().width>0)"
            ".map(e=>(e.innerText||e.textContent||'').trim().replace(/\\n/g,' ')).filter(Boolean))" % json.dumps(css))


def visible_names(session, css: str) -> str:
    return " || ".join(json.loads(session.evaluate(visible_texts_js(css)) or "[]"))


def click_xy(session, x: float, y: float) -> None:
    for kind in ("mousePressed", "mouseReleased"):
        session.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})


def click_target(session, js: str, step: str, what: str, css: str) -> None:
    box = session.evaluate(js)
    if not box or box == "null":
        raise Missing(step, "visible %s: %s" % (what, visible_names(session, css)))
    pos = json.loads(box)
    click_xy(session, pos["x"], pos["y"])


def clean_toast(text: str) -> str:
    """One toast as one line: whitespace collapsed, and a leading Material icon word (check_circle) dropped."""
    collapsed = " ".join(text.split())
    head, sep, rest = collapsed.partition(" ")
    if sep and rest and ICON_WORD.match(head):
        return rest
    return collapsed


def note_toasts(session, seen: list) -> None:
    for text in json.loads(session.evaluate(TOAST_JS) or "[]"):
        text = clean_toast(text)
        if text and text not in seen:
            seen.append(text)


def settle(session, seen: list) -> None:
    """Pump 1 s, then sample the header once a second until it says Idle twice, or the budget passes."""
    session.pump(1.0)
    start = time.monotonic()
    prev, stable = None, 0
    while time.monotonic() - start < SETTLE_BUDGET_S:
        hdr = session.evaluate(HDR_JS) or ""
        note_toasts(session, seen)
        stable = stable + 1 if ("Idle" in hdr and hdr == prev) else 0
        prev = hdr
        if stable >= 2:
            return
        session.pump(1.0)


def eval_expression(session, expression: str):
    """Evaluate `expression` in the page and return its value. A thrown error raises RuntimeError."""
    res = session.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    if "exceptionDetails" in res:
        details = res["exceptionDetails"]
        raise RuntimeError("eval threw: %s" % (details.get("exception", {}).get("description") or details.get("text", "")))
    return res.get("result", {}).get("value")


def after_action(session, seen: list, no_settle: bool) -> None:
    """After a click or select: wait for the header to settle, or with --no-settle only pump 1 s (a running job)."""
    if no_settle:
        session.pump(1.0)
    else:
        settle(session, seen)


def run_steps(session, steps: list[str], seen: list, no_settle: bool = False) -> None:
    for raw in steps:
        step = parse_step(raw)
        if step[0] == "click":
            click_target(session, find_button_js(step[1]), raw, "buttons", "button")
            after_action(session, seen, no_settle)
        elif step[0] == "select":
            _, css, text = step
            if session.evaluate(native_select_js(css, text)) != "ok":
                box = session.evaluate(find_selector_js(css))
                if not box or box == "null":
                    raise Missing(raw)
                pos = json.loads(box)
                click_xy(session, pos["x"], pos["y"])
                session.pump(1.0)
                click_target(session, find_option_js(text), raw, "options", "[role=option], .q-item")
            after_action(session, seen, no_settle)
        elif step[0] == "fill":
            _, css, value = step
            if not session.evaluate("!!document.querySelector(%s)" % json.dumps(css)):
                raise Missing(raw)
            session.evaluate("(function(){const e=document.querySelector(%s);e.focus();if(e.select)e.select();})()"
                             % json.dumps(css))
            session.call("Input.insertText", {"text": value})
            session.pump(1.0)
        elif step[0] == "tap":
            click_target(session, find_checkbox_js(step[1]), raw, "checkboxes",
                         ".q-checkbox, .q-toggle, [role=checkbox], [role=switch]")
            session.pump(1.0)
        elif step[0] == "wait":
            session.pump(step[1])
        elif step[0] == "eval":
            _say("EVAL %s => %s" % (step[1], json.dumps(eval_expression(session, step[1]))))
        note_toasts(session, seen)


def screenshot_now(session, png: Path, width: int) -> None:
    """Screenshot the page as it is now. capture.Browser.visit always navigates first, so it cannot
    shoot the state the steps left behind; this uses the same clip rule (capture.py visit)."""
    size = session.call("Page.getLayoutMetrics")["cssContentSize"]
    shot = session.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True,
                                                   "clip": {"x": 0, "y": 0, "width": width,
                                                            "height": min(size["height"], 6000), "scale": 1}})
    png.write_bytes(base64.b64decode(shot["data"]))


# -- the verb -------------------------------------------------------------------------------------

def _check_reachable(base: str) -> None:
    try:
        urllib.request.urlopen(base + "/api/build", timeout=5).read()
    except OSError as exc:
        raise OSError("no server answers at %s (%s)" % (base, exc)) from None


def run(args: argparse.Namespace, png: Path) -> int:
    chrome = capture.find_chrome()
    if not chrome:
        _say("Could not run: Chrome was not found.")
        return 1
    server = None
    browser = None
    seen: list = []
    try:
        if args.url:
            base = args.url.rstrip("/")
            _check_reachable(base)
        else:
            server = capture.DemoServer(args.fixture)
            base = server.base
        browser = capture.Browser(chrome)
        browser.visit(capture.tab_url(base, args.tab), png, args.width, args.tab, height=args.height)
        session = browser.session
        if args.steps:
            run_steps(session, args.steps, seen, no_settle=args.no_settle)
            screenshot_now(session, png, args.width)
        note_toasts(session, seen)
        text = (session.evaluate(BODY_JS) or "")[:TEXT_CHARS]
    except Missing as exc:
        png.unlink(missing_ok=True)  # a stale shot would show the state before the failed step
        _say("MISSING: %s" % exc.step)
        if exc.candidates:
            _say(exc.candidates)
        return 3
    except (OSError, RuntimeError) as exc:
        _say("Could not run: %s" % exc)
        return 1
    finally:
        if browser:
            browser.close()
        if server:
            server.stop()
    _say("png: %s" % png.resolve())
    _say("toasts: %s" % (" | ".join(seen) if seen else "none"))
    _say("text:")
    _say(text)
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    return run(args, shot_path(args.tab, args.width))


if __name__ == "__main__":
    sys.exit(main())
