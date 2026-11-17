# copied from a sibling local GUI kit (api.py)
"""HTTP surface for the state contract, build info and the browser log relay.

GET /state.json, GET /state/<tab>.json and GET /api/build are read-only and come from one
cached snapshot per poll interval. POST /__log relays one browser error line; it needs the
per-launch token in X-RVM-Token and is rate limited, so a page error loop cannot flood the log.
Nothing here writes to the library or starts a job.
"""
from __future__ import annotations

import logging
import time
from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from gui import build_info, security, view_model

NO_STORE = {"Cache-Control": "no-store"}
TABS = ("clips", "compile", "videos", "archive", "activity")
LOG_LIMIT = 20      # relayed browser lines allowed per window
LOG_WINDOW = 10.0   # seconds
MAX_KIND = 200
MAX_MESSAGE = 2000

ENDPOINTS = [
    {"path": "/api/build", "method": "GET", "returns": "build line, sha, dirty flag, boot id, fixture"},
    {"path": "/state.json", "method": "GET", "returns": "every tab's state contract"},
    {"path": "/state/{tab}.json", "method": "GET", "returns": "one tab's state contract"},
    {"path": "/__log", "method": "POST", "returns": "relay a browser error line (X-RVM-Token)"},
]

_log = logging.getLogger("rvm.gui")


def _default_sink(kind: str, message: str) -> None:
    _log.warning("[app-error] %s: %s", kind, message)


class RateWindow:
    """At most `limit` allowed events in any `window` seconds; refused events do not count."""

    def __init__(self, limit: int, window: float, clock):
        self._limit, self._window, self._clock = limit, window, clock
        self._hits: deque[float] = deque()

    def allow(self) -> bool:
        now = self._clock()
        while self._hits and now - self._hits[0] >= self._window:
            self._hits.popleft()
        if len(self._hits) >= self._limit:
            return False
        self._hits.append(now)
        return True


class StateApi:
    """Routes' logic without the HTTP layer: one cached snapshot, build info and log relay."""

    def __init__(self, source, clock=time.monotonic, sink=None):
        self.source = source
        self._clock = clock
        self._sink = sink or _default_sink
        self._cached: dict | None = None
        self._cached_at: float | None = None
        self.log_window = RateWindow(LOG_LIMIT, LOG_WINDOW, clock)

    def snapshot(self) -> dict:
        now = self._clock()
        fresh = self._cached_at is not None and now - self._cached_at < view_model.POLL_INTERVAL
        if not fresh:
            self._cached = view_model.snapshot(self.source)
            self._cached_at = now
        return self._cached

    def tab(self, key: str) -> dict | None:
        if key not in TABS:
            return None
        snap = self.snapshot()
        return {"schema": snap["schema"], "generated_at": snap["generated_at"],
                "stale": snap["stale"], "tab": key, "data": snap[key]}

    def build(self) -> dict:
        return {**build_info.as_dict(), "fixture": self.source.fixture}

    def relay(self, body: dict) -> None:
        kind = str(body.get("kind", "?")).replace("\r", " ").replace("\n", " ")[:MAX_KIND]
        message = str(body.get("message", "")).replace("\r", " ").replace("\n", " ")[:MAX_MESSAGE]
        self._sink(kind, message)


def _json(payload, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers=NO_STORE)


def register(app: FastAPI, source, clock=time.monotonic, sink=None) -> StateApi:
    api = StateApi(source, clock=clock, sink=sink)

    # Plain `def` handlers run in FastAPI's threadpool; only log_relay awaits the request body.
    def state_all():
        return _json(api.snapshot())

    def state_tab(tab: str):
        payload = api.tab(tab)
        return _json(payload if payload is not None else {"error": f"unknown tab {tab}"},
                     200 if payload is not None else 404)

    def api_build():
        return _json(api.build())

    async def log_relay(request: Request):
        if not security.check_token(request.headers.get("x-rvm-token", "")):
            return _json({"error": "bad token"}, 403)
        if not api.log_window.allow():
            return _json({"error": "rate limited"}, 429)
        try:
            body = await request.json()
        except Exception:
            return _json({"error": "bad json"}, 400)
        if not isinstance(body, dict):
            return _json({"error": "bad json"}, 400)
        api.relay(body)
        return Response(status_code=204, headers=NO_STORE)

    app.add_api_route("/api/build", api_build, methods=["GET"])
    app.add_api_route("/state.json", state_all, methods=["GET"])
    app.add_api_route("/state/{tab}.json", state_tab, methods=["GET"])
    app.add_api_route("/__log", log_relay, methods=["POST"])
    return api
