# copied from a sibling local GUI kit (timefmt.py)
"""Display times for visible UI text: DD/MM/YYYY h:mmam/pm (e.g. 17/11/2026 2:14pm).

Only rendered text uses this. JSON state payloads, logs, filenames and baselines stay ISO.
Standard library only. A tz-aware value keeps its own wall clock (no zone conversion), and
input that does not parse comes back unchanged, so a bad value never breaks a page.
"""
from __future__ import annotations

from datetime import datetime


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _as_datetime(value) -> datetime:
    """A datetime as is, or ISO text parsed; raises ValueError for text that is not a time."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _clock(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    suffix = "am" if dt.hour < 12 else "pm"
    return f"{hour}:{dt.minute:02d}{suffix}"


def stamp(value) -> str:
    if value is None:
        return "-"
    try:
        dt = _as_datetime(value)
    except ValueError:
        return str(value)
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year} {_clock(dt)}"


def short(value, now=None) -> str:
    """Compact time for narrow table cells: 12:50am on the same day as now, 17 Nov 11:52pm on another
    day of the same year, 17 Nov 2025 in another year. None is a dash; unparsable text comes back unchanged."""
    if value is None:
        return "-"
    try:
        dt = _as_datetime(value)
    except ValueError:
        return str(value)
    today = datetime.now() if now is None else now
    if dt.date() == today.date():
        return _clock(dt)
    month = _MONTHS[dt.month - 1]
    if dt.year == today.year:
        return f"{dt.day} {month} {_clock(dt)}"
    return f"{dt.day} {month} {dt.year}"


def duration(seconds) -> str:
    """Elapsed seconds as m:ss under an hour (0:00, 5:00, 7:05), h:mm:ss from an hour up. None is a dash."""
    if seconds is None:
        return "-"
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


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
