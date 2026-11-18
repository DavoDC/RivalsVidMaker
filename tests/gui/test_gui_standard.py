# copied from a sibling local GUI kit (test_gui_standard.py)
"""Webapp-standard checks for the GUI: no external requests, one time formatter, literal loopback
bind plus the Host/Origin/token guard, and the security headers. Offline, no browser, no library."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from gui import security, theme, timefmt

ROOT = Path(__file__).resolve().parents[2]
PORT = 8476
URL_RE = re.compile(r"""(?:https?:)?//[A-Za-z0-9.-]+\.[a-z]{2,}""", re.I)


def _gui_text_files():
    for p in (ROOT / "src" / "gui").rglob("*"):
        if p.suffix in {".py", ".css", ".js", ".html"} and "__pycache__" not in p.parts:
            yield p


def test_no_external_urls_in_gui_sources():
    offenders = []
    for p in _gui_text_files():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "http://" in line or "https://" in line:
                if "localhost" in line or "127.0.0.1" in line:
                    continue
                offenders.append(f"{p.relative_to(ROOT)}:{n}")
    assert offenders == []


def test_head_html_loads_nothing_remote():
    assert "googleapis" not in theme.HEAD_HTML
    assert "gstatic" not in theme.HEAD_HTML
    assert not re.search(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", theme.HEAD_HTML)
    assert "@import" not in theme.HEAD_HTML


def test_head_css_uses_system_fonts_only():
    # Bahnschrift and Segoe UI come from the machine; no web font is downloaded.
    assert "@font-face" not in theme.HEAD_HTML
    assert not URL_RE.search(theme.HEAD_HTML)


def test_dark_only_no_light_mode():
    assert "prefers-color-scheme: light" not in theme.HEAD_HTML


@pytest.mark.parametrize(
    "dt,expected",
    [
        (datetime(2026, 10, 12, 15, 5), "12/10/2026 3:05pm"),
        (datetime(2026, 1, 2, 0, 0), "02/01/2026 12:00am"),
        (datetime(2026, 1, 2, 12, 0), "02/01/2026 12:00pm"),
        (datetime(2026, 12, 31, 23, 59), "31/12/2026 11:59pm"),
        (datetime(2026, 3, 4, 9, 7), "04/03/2026 9:07am"),
    ],
)
def test_time_formatter(dt, expected):
    assert timefmt.stamp(dt) == expected


def test_time_formatter_none_and_bad():
    assert timefmt.stamp(None) == "-"
    assert timefmt.stamp("garbage") == "garbage"


def test_gui_has_no_bare_time_strftime():
    for p in _gui_text_files():
        if p.suffix == ".py" and p.name != "timefmt.py":
            assert "%H:%M" not in p.read_text(encoding="utf-8"), p.name


def test_bind_is_literal_loopback():
    assert security.BIND_HOST == "127.0.0.1"
    assert security.DEFAULT_PORT == PORT


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(security.LoopbackGuard, port_fn=lambda: PORT)

    @app.get("/x")
    def x():
        return {"ok": 1}

    @app.post("/x")
    def px():
        return {"ok": 1}

    @app.get("/state.json")
    def state():
        return {"ok": 1}

    return TestClient(app, base_url=f"http://localhost:{PORT}")


@pytest.mark.parametrize(
    "host,ok",
    [
        (f"localhost:{PORT}", True),
        (f"127.0.0.1:{PORT}", True),
        ("evil.example:%d" % PORT, False),
        ("127.0.0.1.evil.example:%d" % PORT, False),
        (f"localhost:{PORT + 1}", False),
    ],
)
def test_host_allowlist(host, ok):
    status = _client().get("/x", headers={"Host": host}).status_code
    assert (status == 200) is ok


@pytest.mark.parametrize(
    "origin,ok",
    [
        (None, True),  # curl sends no Origin, so scripts still work
        (f"http://localhost:{PORT}", True),
        (f"http://127.0.0.1:{PORT}", True),
        ("http://evil.example", False),
        (f"http://localhost:{PORT + 1}", False),
        ("null", False),
    ],
)
def test_origin_guard_for_mutations(origin, ok):
    headers = {"x-rvm-token": security.TOKEN}
    if origin is not None:
        headers["Origin"] = origin
    assert (_client().post("/x", headers=headers).status_code == 200) is ok


def test_post_without_the_token_is_refused():
    assert _client().post("/x").status_code == 403


def test_forwarded_headers_are_refused():
    assert _client().get("/x", headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 403


def test_security_headers_block_framing_and_sniffing():
    r = _client().get("/x")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_json_state_is_not_cached():
    assert _client().get("/state.json").headers["cache-control"] == "no-store"


def test_clip_action_buttons_have_tooltips():
    from gui.tabs import clips
    assert clips.SORT_TIP and clips.SCAN_TIP
    assert "Nothing is moved" in clips.SCAN_TIP


def test_tooltips_are_wrapped_readable_boxes():
    css = theme.HEAD_HTML
    assert ".q-tooltip{font-size:16px" in css
    assert "max-width:320px" in css and "white-space:normal" in css
