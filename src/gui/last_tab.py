"""The tab the user last showed, so the tray opens it again; in memory, one process."""
from __future__ import annotations

from gui import tabdefs

_last: str | None = None  # shortcut: in memory only, persist to a file if a restart should keep it


def remember(key: str) -> None:
    """Store key as the last tab shown; a key that is not a tab is ignored."""
    global _last
    if key in tabdefs.KEYS:
        _last = key


def get() -> str | None:
    return _last


def reset() -> None:
    global _last
    _last = None
