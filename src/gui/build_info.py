"""Which build is running: repo name, short sha, commit date, dirty marker, boot id.

Standard library only. Git runs at most once per process (cached per repo root); it never
raises. Outside a git checkout, or with no git installed, the sha is "unknown" and the
line reads "RivalsVidMaker unknown".
"""
from __future__ import annotations

import subprocess
import uuid
from datetime import datetime
from pathlib import Path

REPO_NAME = "RivalsVidMaker"
REPO_ROOT = Path(__file__).resolve().parents[2]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# New value every process start; a hot reload re-execs, so an open page sees it change.
BOOT_ID = uuid.uuid4().hex[:12]
STARTED_AT = datetime.now().astimezone().isoformat(timespec="seconds")
_cache: dict[str, dict] = {}


def _git(root: Path, runner, *args: str) -> str | None:
    try:
        out = runner(["git", "-C", str(root), *args], capture_output=True, text=True,
                     timeout=5, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return out.stdout if out.returncode == 0 else None


def _clock(dt: datetime) -> str:
    """Commit time as h:mmam or h:mmpm, lower case, no leading zero (9:36am, 12:05pm)."""
    return dt.strftime("%I:%M%p").lstrip("0").lower()


def _describe(root: Path, runner) -> dict:
    sha = "unknown"
    date = "unknown"
    time = "unknown"
    dirty = False
    head = _git(root, runner, "log", "-1", "--format=%H %cI")
    if head and len(head.split()) == 2:
        full, iso = head.split()
        try:
            # Commit date and time in the machine's local zone: DD/MM/YYYY and h:mmam.
            local = datetime.fromisoformat(iso).astimezone()
            date = local.strftime("%d/%m/%Y")
            time = _clock(local)
            sha = full[:7]
        except (ValueError, OverflowError):
            date = "unknown"
            time = "unknown"
            sha = full[:7]
        # Tracked files only; untracked logs and caches must not read as a dirty build.
        status = _git(root, runner, "status", "--porcelain", "--untracked-files=no")
        dirty = bool(status and status.strip())
    return {"sha": sha, "date": date, "time": time, "dirty": dirty}


def describe(repo_root: Path | None = None, runner=None, refresh: bool = False) -> dict:
    """Sha, date and dirty flag for a checkout. Cached per root; pass refresh=True to re-ask git."""
    root = Path(repo_root or REPO_ROOT)
    key = str(root)
    if refresh or key not in _cache:
        _cache[key] = _describe(root, runner or subprocess.run)
    return dict(_cache[key])


def line(info: dict | None = None) -> str:
    """Footer line: RivalsVidMaker <7 char sha> <DD/MM/YYYY>, with ' +dirty' when tracked files changed."""
    info = info or describe()
    text = f"{REPO_NAME} {info['sha']} {info['date']}"
    if info["sha"] == "unknown":
        text = f"{REPO_NAME} unknown"
    if info["dirty"]:
        text += " +dirty"
    return text


def short(info: dict | None = None) -> str:
    """Footer text: <7 char sha> <h:mmam commit time>, with ' +dirty' last when tracked files changed."""
    info = info or describe()
    if info["sha"] == "unknown":
        return "unknown"
    text = f"{info['sha']} {info['time']}"
    if info["dirty"]:
        text += " +dirty"
    return text


def as_dict() -> dict:
    info = describe()
    return {"line": line(info), "sha": info["sha"], "dirty": info["dirty"], "date": info["date"],
            "boot_id": BOOT_ID, "started_at": STARTED_AT}
