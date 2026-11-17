"""Loopback security for the GUI: pure ASGI checks, no server started."""
import asyncio

from gui import security

PORT = 8476
GOOD_HOST = f"127.0.0.1:{PORT}"


def run_guard(scope, body=b""):
    """Run LoopbackGuard once; return (app_calls, sent_messages)."""
    app_calls = []
    sent = []

    async def app(s, receive, send):
        app_calls.append(s)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    guard = security.LoopbackGuard(app, lambda: PORT)
    asyncio.run(guard(scope, receive, send))
    return app_calls, sent


def http_scope(method="GET", path="/", host=GOOD_HOST, headers=()):
    raw = [(b"host", host.encode())] + [(k.encode(), v.encode()) for k, v in headers]
    return {"type": "http", "method": method, "path": path, "headers": raw}


def ws_scope(path="/_nicegui_ws/socket", host=GOOD_HOST, origin=None):
    raw = [(b"host", host.encode())]
    if origin is not None:
        raw.append((b"origin", origin.encode()))
    return {"type": "websocket", "path": path, "headers": raw}


def status_of(sent):
    return sent[0]["status"]


def body_of(sent):
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def test_bind_host_is_loopback_literal():
    assert security.BIND_HOST == "127.0.0.1"


def test_default_port_is_8476():
    assert security.DEFAULT_PORT == 8476


def test_foreign_host_refused():
    calls, sent = run_guard(http_scope(host="evil.example:8476"))
    assert calls == []
    assert status_of(sent) == 403
    assert b"bad Host" in body_of(sent)


def test_loopback_host_with_wrong_port_refused():
    calls, sent = run_guard(http_scope(host="127.0.0.1:9999"))
    assert calls == []
    assert status_of(sent) == 403


def test_missing_host_refused():
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    calls, sent = run_guard(scope)
    assert calls == []
    assert status_of(sent) == 403


def test_localhost_get_with_good_host_passes():
    calls, sent = run_guard(http_scope(host=f"localhost:{PORT}"))
    assert len(calls) == 1
    assert status_of(sent) == 200


def test_ip_get_with_good_host_passes():
    calls, sent = run_guard(http_scope(host=GOOD_HOST))
    assert len(calls) == 1
    assert status_of(sent) == 200


def test_get_response_carries_security_headers():
    _, sent = run_guard(http_scope())
    headers = dict(sent[0]["headers"])
    assert headers[b"x-frame-options"] == b"DENY"
    assert headers[b"x-content-type-options"] == b"nosniff"


def test_proxy_header_refused():
    calls, sent = run_guard(http_scope(headers=[("X-Forwarded-For", "10.0.0.1")]))
    assert calls == []
    assert status_of(sent) == 403


def test_foreign_origin_on_post_refused():
    token_header = [("X-RVM-Token", security.TOKEN), ("Origin", "http://evil.example")]
    calls, sent = run_guard(http_scope(method="POST", path="/api/x", headers=token_header))
    assert calls == []
    assert status_of(sent) == 403
    assert b"bad Origin" in body_of(sent)


def test_same_origin_post_with_token_passes():
    headers = [("X-RVM-Token", security.TOKEN), ("Origin", f"http://localhost:{PORT}")]
    calls, sent = run_guard(http_scope(method="POST", path="/api/x", headers=headers))
    assert len(calls) == 1
    assert status_of(sent) == 200


def test_post_without_token_refused():
    calls, sent = run_guard(http_scope(method="POST", path="/api/x"))
    assert calls == []
    assert status_of(sent) == 403
    assert b"missing or wrong token" in body_of(sent)


def test_post_with_wrong_token_refused():
    calls, sent = run_guard(http_scope(method="POST", path="/api/x", headers=[("X-RVM-Token", "nope")]))
    assert calls == []
    assert status_of(sent) == 403


def test_nicegui_transport_post_exempt_from_token():
    calls, sent = run_guard(http_scope(method="POST", path="/_nicegui/client/abc"))
    assert len(calls) == 1
    assert status_of(sent) == 200


def test_foreign_origin_on_websocket_refused():
    calls, sent = run_guard(ws_scope(origin="http://evil.example"))
    assert calls == []
    assert sent[0] == {"type": "websocket.close", "code": 1008}


def test_foreign_host_on_websocket_refused():
    calls, sent = run_guard(ws_scope(host="evil.example:8476"))
    assert calls == []
    assert sent[0] == {"type": "websocket.close", "code": 1008}


def test_same_origin_websocket_passes():
    calls, _ = run_guard(ws_scope(origin=f"http://127.0.0.1:{PORT}"))
    assert len(calls) == 1


def test_websocket_without_origin_passes():
    calls, _ = run_guard(ws_scope())
    assert len(calls) == 1


def test_check_token_accepts_only_this_launch_token():
    assert security.check_token(security.TOKEN) is True
    assert security.check_token("") is False
    assert security.check_token(None) is False
    assert security.check_token(security.TOKEN + "x") is False


def test_token_is_per_launch_and_long_enough():
    assert len(security.TOKEN) >= 32


def test_open_url_uses_localhost_not_bind_host():
    assert security.open_url(PORT) == f"http://localhost:{PORT}/"
