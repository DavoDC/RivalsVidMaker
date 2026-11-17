"""State API routes (design plan sections 6 and 12): in-process, no server is bound."""
from fastapi import FastAPI
from starlette.testclient import TestClient

from gui import build_info, fixtures, security, state_api, view_model
from gui.sources import FixtureSource

PORT = 8476
GOOD_HOST = f"127.0.0.1:{PORT}"
TOKEN_HEADER = {"X-RVM-Token": security.TOKEN}


class CountingSource:
    """Wraps a FixtureSource and counts reads, so caching is observable."""

    def __init__(self, name):
        self.inner = FixtureSource(name)
        self.fixture = name
        self.reads = 0

    def read(self):
        self.reads += 1
        return self.inner.read()


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make_client(name="empty", clock=None, sink=None, source=None):
    app = FastAPI()
    clock = clock or FakeClock()
    sink_calls = []
    sink = sink or (lambda kind, message: sink_calls.append((kind, message)))
    src = source or FixtureSource(name)
    api = state_api.register(app, src, clock=clock, sink=sink)
    guarded = security.LoopbackGuard(app, lambda: PORT)
    client = TestClient(guarded, base_url=f"http://{GOOD_HOST}")
    return client, api, sink_calls, clock


def test_state_json_has_documented_keys():
    client, _, _, _ = make_client("empty")
    res = client.get("/state.json")
    assert res.status_code == 200
    body = res.json()
    for key in ("schema", "generated_at", "stale", "poll_interval", "boot_id", "build", "fixture",
                "job", "summary", "clips", "compile", "videos", "archive", "activity",
                "config_problems", "notices"):
        assert key in body, key
    assert body["schema"] == view_model.SCHEMA
    assert body["poll_interval"] == view_model.POLL_INTERVAL
    assert res.headers["cache-control"] == "no-store"


def test_each_tab_route_returns_its_section():
    client, _, _, _ = make_client("ready")
    for tab in state_api.TABS:
        res = client.get(f"/state/{tab}.json")
        assert res.status_code == 200, tab
        body = res.json()
        assert body["tab"] == tab
        assert "data" in body and "generated_at" in body and "stale" in body
        assert res.headers["cache-control"] == "no-store"


def test_unknown_tab_and_unknown_route_404():
    client, _, _, _ = make_client("empty")
    assert client.get("/state/nope.json").status_code == 404
    assert client.get("/no/such/route").status_code == 404


def test_api_build_has_line_sha_boot_id_and_fixture():
    client, _, _, _ = make_client("needs_decision")
    body = client.get("/api/build").json()
    assert body["line"] == build_info.line(build_info.describe())
    for key in ("sha", "dirty", "date", "boot_id", "started_at"):
        assert key in body
    assert body["fixture"] == "needs_decision"


def test_foreign_host_is_refused():
    client, _, _, _ = make_client("empty")
    res = client.get("/state.json", headers={"host": "evil.example:8476"})
    assert res.status_code == 403
    assert res.text == "403 bad Host"


def test_log_without_token_is_refused_and_not_recorded():
    client, _, sink_calls, _ = make_client("empty")
    res = client.post("/__log", json={"kind": "error", "message": "boom"})
    assert res.status_code == 403
    assert sink_calls == []


def test_log_with_wrong_token_is_refused():
    client, _, sink_calls, _ = make_client("empty")
    res = client.post("/__log", json={"kind": "error", "message": "boom"},
                      headers={"X-RVM-Token": "wrong"})
    assert res.status_code == 403
    assert sink_calls == []


def test_log_with_token_returns_204_and_records_one_line():
    client, _, sink_calls, _ = make_client("empty")
    res = client.post("/__log", json={"kind": "error", "message": "line one\nline two"},
                      headers=TOKEN_HEADER)
    assert res.status_code == 204
    assert sink_calls == [("error", "line one line two")]


def test_log_bad_json_is_400():
    client, _, sink_calls, _ = make_client("empty")
    res = client.post("/__log", content=b"not json",
                      headers={**TOKEN_HEADER, "content-type": "application/json"})
    assert res.status_code == 400
    assert sink_calls == []


def test_log_is_rate_limited_after_the_window_fills():
    client, _, sink_calls, clock = make_client("empty")
    statuses = [client.post("/__log", json={"kind": "e", "message": str(i)},
                            headers=TOKEN_HEADER).status_code
                for i in range(state_api.LOG_LIMIT + 1)]
    assert statuses[:-1] == [204] * state_api.LOG_LIMIT
    assert statuses[-1] == 429
    assert len(sink_calls) == state_api.LOG_LIMIT


def test_log_budget_refills_after_the_window():
    client, _, _, clock = make_client("empty")
    for _ in range(state_api.LOG_LIMIT):
        client.post("/__log", json={"kind": "e", "message": "x"}, headers=TOKEN_HEADER)
    assert client.post("/__log", json={"kind": "e", "message": "x"},
                       headers=TOKEN_HEADER).status_code == 429
    clock.now += state_api.LOG_WINDOW
    assert client.post("/__log", json={"kind": "e", "message": "x"},
                       headers=TOKEN_HEADER).status_code == 204


def test_refused_tokenless_log_does_not_use_the_budget():
    client, _, _, _ = make_client("empty")
    for _ in range(state_api.LOG_LIMIT + 5):
        client.post("/__log", json={"kind": "e", "message": "x"})
    assert client.post("/__log", json={"kind": "e", "message": "x"},
                       headers=TOKEN_HEADER).status_code == 204


def test_boot_id_is_stable_across_two_calls():
    client, _, _, clock = make_client("empty")
    first = client.get("/api/build").json()["boot_id"]
    clock.now += 60
    second = client.get("/state.json").json()["boot_id"]
    assert first == second == build_info.BOOT_ID


def test_stale_fixture_reports_stale_true():
    client, _, _, _ = make_client("stale")
    assert client.get("/state.json").json()["stale"] is True


def test_non_stale_fixture_reports_stale_false():
    client, _, _, _ = make_client("empty")
    assert client.get("/state.json").json()["stale"] is False


def test_snapshot_is_cached_for_one_poll_interval():
    source = CountingSource("empty")
    client, _, _, clock = make_client(source=source)
    client.get("/state.json")
    client.get("/state.json")
    client.get("/state/clips.json")
    assert source.reads == 1
    clock.now += view_model.POLL_INTERVAL
    client.get("/state.json")
    assert source.reads == 2


def test_every_route_listed_in_endpoints_is_registered():
    app = FastAPI()
    state_api.register(app, FixtureSource("empty"), clock=FakeClock(), sink=lambda k, m: None)
    registered = {getattr(r, "path", None) for r in app.routes}
    for entry in state_api.ENDPOINTS:
        assert entry["path"] in registered, entry


def test_fixture_scenarios_all_serve_state_json():
    for name in fixtures.SCENARIOS:
        client, _, _, _ = make_client(name)
        res = client.get("/state.json")
        assert res.status_code == 200, name
        assert res.json()["fixture"] == name
