"""Single-use, expiring plan tokens for the local GUI (DESIGN-PLAN.md section 8)."""
from gui import nonce


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


PLAN = {"character": "Ana", "batches": [{"number": 1, "clips": ["a.mp4"]}]}


def test_default_ttl_is_ten_minutes():
    assert nonce.NONCE_TTL == 600.0


def test_token_redeems_once_then_fails():
    store = nonce.NonceStore(clock=FakeClock())
    token = store.issue(PLAN)
    assert store.consume(token, PLAN) is True
    assert store.consume(token, PLAN) is False


def test_expired_token_fails():
    clock = FakeClock()
    store = nonce.NonceStore(ttl=600.0, clock=clock)
    token = store.issue(PLAN)
    clock.advance(601.0)
    assert store.consume(token, PLAN) is False


def test_token_still_valid_just_before_expiry():
    clock = FakeClock()
    store = nonce.NonceStore(ttl=600.0, clock=clock)
    token = store.issue(PLAN)
    clock.advance(599.0)
    assert store.consume(token, PLAN) is True


def test_default_store_uses_ten_minute_ttl():
    clock = FakeClock()
    store = nonce.NonceStore(clock=clock)
    token = store.issue(PLAN)
    clock.advance(599.0)
    assert store.consume(token, PLAN) is True
    token2 = store.issue(PLAN)
    clock.advance(601.0)
    assert store.consume(token2, PLAN) is False


def test_unknown_token_fails():
    store = nonce.NonceStore(clock=FakeClock())
    store.issue(PLAN)
    assert store.consume("not-a-real-token", PLAN) is False


def test_token_is_bound_to_its_plan_payload():
    store = nonce.NonceStore(clock=FakeClock())
    token = store.issue(PLAN)
    other = {"character": "Ben", "batches": []}
    assert store.consume(token, other) is False
    # a wrong-payload attempt spends the token, so the right payload fails too
    assert store.consume(token, PLAN) is False


def test_issued_tokens_are_distinct_and_url_safe():
    store = nonce.NonceStore(clock=FakeClock())
    tokens = {store.issue(PLAN) for _ in range(50)}
    assert len(tokens) == 50
    assert all(t.replace("-", "").replace("_", "").isalnum() for t in tokens)


def test_oldest_token_evicted_past_limit():
    store = nonce.NonceStore(clock=FakeClock())
    first = store.issue(PLAN)
    for _ in range(nonce.NONCE_LIMIT):
        store.issue(PLAN)
    assert store.consume(first, PLAN) is False
