# copied from a sibling local GUI kit (jobs.py)
"""Single-use, expiring plan tokens for the local GUI.

The bridge stores a plan under a nonce; the GUI sends the nonce back to run the plan.
A nonce works once, only before it expires, and only with the payload it was issued for.
"""
import secrets
import threading
import time
from typing import Any, Callable, Dict, Tuple

NONCE_TTL = 600.0   # seconds a plan token stays valid
NONCE_LIMIT = 100   # most live tokens kept; the oldest is dropped past this


class NonceStore:
    """Single-use, expiring confirm tokens bound to one plan payload."""

    def __init__(self, ttl: float = NONCE_TTL, clock: Callable[[], float] = time.monotonic):
        self._ttl, self._clock = ttl, clock
        self._items: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def issue(self, payload: Any) -> str:
        with self._lock:
            now = self._clock()
            self._items = {n: v for n, v in self._items.items() if v[1] > now}
            if len(self._items) >= NONCE_LIMIT:
                oldest = min(self._items, key=lambda n: self._items[n][1])
                del self._items[oldest]
            nonce = secrets.token_urlsafe(18)
            self._items[nonce] = (payload, now + self._ttl)
            return nonce

    def consume(self, nonce: str, payload: Any) -> bool:
        """True once per nonce, only for the payload it was issued for and only before it expires."""
        with self._lock:
            item = self._items.pop(nonce, None)
            return bool(item and item[0] == payload and item[1] > self._clock())
