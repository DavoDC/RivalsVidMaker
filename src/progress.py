"""
progress.py -- Animated terminal progress ticker.

Reusable context manager that redraws a progress line at a fixed rate,
independent of how fast the work being tracked actually completes.
This avoids the freeze-then-jump effect that occurs when progress is only
updated on task completion in slow parallel workloads.

Usage - count-based (shows "Label N/total..."):
    with AnimatedTicker("Scanning", total=28) as ticker:
        for future in as_completed(futures):
            process(future.result())
            ticker.increment()

Usage - indeterminate spinner (shows "Label..."):
    with AnimatedTicker("Encoding"):
        subprocess.run(cmd, ...)
"""

import logging
import threading
from collections.abc import Callable


_DOTS = (".", "..", "...")

log = logging.getLogger(__name__)

# Listeners receive (done, total, label) each time a ticker count changes.
# total is None for indeterminate spinners. Terminal output is unaffected.
_listeners: list[Callable[[int, int | None, str], None]] = []


def add_listener(fn: Callable[[int, int | None, str], None]) -> None:
    """Subscribe fn to ticker count updates."""
    _listeners.append(fn)


def remove_listener(fn: Callable[[int, int | None, str], None]) -> None:
    """Unsubscribe fn. Unknown listeners are ignored."""
    if fn in _listeners:
        _listeners.remove(fn)


def _notify(done: int, total: int | None, label: str) -> None:
    for fn in list(_listeners):
        try:
            fn(done, total, label)
        except Exception:
            log.warning("progress listener %r failed", fn, exc_info=True)


class AnimatedTicker:
    """Prints an animated progress line at a fixed rate on a background thread.

    When total is set: "Label N/total..."
    When total is None: "Label..." (indeterminate spinner)
    """

    def __init__(self, label: str, total: int | None = None, interval: float = 0.1):
        self._label = label
        self._total = total
        self._interval = interval
        self._done = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def increment(self) -> None:
        """Increment the completed count by one. Only meaningful when total is set."""
        with self._lock:
            self._done += 1
            n = self._done
        _notify(n, self._total, self._label)

    def _tick(self) -> None:
        frame = 0
        while not self._stop.wait(self._interval):
            with self._lock:
                n = self._done
            frame = (frame + 1) % len(_DOTS)
            if self._total is not None:
                print(f"\r{self._label} {n}/{self._total}{_DOTS[frame]}", end="", flush=True)
            else:
                print(f"\r{self._label}{_DOTS[frame]}", end="", flush=True)

    def __enter__(self) -> "AnimatedTicker":
        if self._total is not None:
            print(f"\r{self._label} 0/{self._total} ", end="", flush=True)
        else:
            print(f"\r{self._label} ", end="", flush=True)
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        if self._total is not None:
            # Print final count and clear any trailing dot characters
            print(f"\r{self._label} {self._total}/{self._total}   ")
        else:
            # Clear the spinner line - callers log their own completion message
            print(f"\r{' ' * (len(self._label) + 10)}\r", end="", flush=True)
