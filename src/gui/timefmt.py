# copied from a sibling local GUI kit (timefmt.py)
"""Display times for visible UI text: DD/MM/YYYY h:mmam/pm (e.g. 17/11/2026 2:14pm).

Only rendered text uses this. JSON state payloads, logs, filenames and baselines stay ISO.
Standard library only. A tz-aware value keeps its own wall clock (no zone conversion), and
input that does not parse comes back unchanged, so a bad value never breaks a page.
"""
from __future__ import annotations

from datetime import datetime


def stamp(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value)
    hour = dt.hour % 12 or 12
    suffix = "am" if dt.hour < 12 else "pm"
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year} {hour}:{dt.minute:02d}{suffix}"


def duration(seconds) -> str:
    """Elapsed seconds as mm:ss under an hour, h:mm:ss from an hour up. None is a dash."""
    if seconds is None:
        return "-"
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def ago(seconds) -> str:
    """Age in seconds as a short relative label, e.g. 1s ago, 3m ago, 2h ago, 1d ago."""
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s ago"
    if total < 3600:
        return f"{total // 60}m ago"
    if total < 86400:
        return f"{total // 3600}h ago"
    return f"{total // 86400}d ago"
