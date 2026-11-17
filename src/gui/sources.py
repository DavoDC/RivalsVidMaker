"""Data sources for the GUI (DESIGN-PLAN sections 5 and 6).

A Source returns the raw inputs for one snapshot as plain dicts. view_model
turns them into the /state.json contract; nothing here shapes UI rows.

READ-ONLY: this module must never move, rename, delete or write a file, and
must never create a folder. It may use only these engine helpers:
  state.load, clip_cache.cache_load, batcher.make_batches,
  clip_scanner (VIDEO_EXTS, Clip) and the Config type.
tests/gui/test_gui_sources.py parses this file and fails on anything else.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

import batcher
import clip_cache
import state
from clip_scanner import VIDEO_EXTS, Clip
from config import Config
from gui import fixtures


@runtime_checkable
class Source(Protocol):
    """fixture: scenario name, or None for real data. read(): one payload dict."""

    fixture: str | None

    def read(self) -> dict: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _video_files(folder: Path) -> list[Path]:
    """Direct children only (nested folders such as vid1_uploaded are not clips)."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def _visible_dirs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def _cache_entry(path: Path, cache_dir: Path) -> dict | None:
    hit, entry = clip_cache.cache_load(str(path), str(cache_dir))
    return entry if hit and entry is not None else None


def _tier_counts(paths: list[Path], cache_dir: Path) -> dict:
    counts = {t: 0 for t in fixtures.TIERS}
    for path in paths:
        entry = _cache_entry(path, cache_dir)
        result = entry.get("ko_result") if entry else None
        tier = result.get("tier") if isinstance(result, dict) else None
        if tier in counts:
            counts[tier] += 1
    return counts


def _tool_problems(cfg: Config) -> list[str]:
    checks = (("ffmpeg", cfg.ffmpeg), ("ffprobe", cfg.ffprobe), ("tesseract", cfg.tesseract))
    return [f"{label} not found" for label, path in checks if not Path(path).exists()]


def _unsorted(cfg: Config) -> list[dict]:
    paths = _video_files(cfg.clips_path)
    cut = len(paths) - max(0, cfg.protect_recent_clips)
    return [{"name": p.name, "protected": i >= cut} for i, p in enumerate(paths)]


def _character(folder: Path, cfg: Config) -> dict:
    paths = _video_files(folder)
    scanned: list[Clip] = []
    for path in paths:
        entry = _cache_entry(path, cfg.cache_dir)
        duration = entry.get("duration") if entry else None
        if isinstance(duration, (int, float)) and duration > 0:
            scanned.append(Clip(path=path, duration=float(duration)))
    total = sum(c.duration for c in scanned)
    batches = batcher.make_batches(scanned, target=cfg.target_batch_seconds)
    return {
        "name": folder.name,
        "clips": len(paths),
        "minutes": round(total / 60, 1),
        "scanned": len(scanned),
        "unscanned": len(paths) - len(scanned),
        "tiers": _tier_counts(paths, cfg.cache_dir),
        "ready": any(b.total_duration >= cfg.min_batch_seconds for b in batches),
    }


def _characters(cfg: Config) -> list[dict]:
    return [_character(d, cfg) for d in _visible_dirs(cfg.clips_path)]


def _output_folders(cfg: Config, state_data: dict) -> list[dict]:
    folders = state_data.get("output_folders")
    safe_state = {"output_folders": folders if isinstance(folders, dict) else {}}
    rows = []
    for folder in _visible_dirs(cfg.output_path):
        info = safe_state["output_folders"].get(folder.name)
        info = info if isinstance(info, dict) else {}
        rows.append({
            "slug": folder.name,
            "video_count": len(_video_files(folder)),
            "youtube_confirmed": state.is_youtube_confirmed(safe_state, folder.name),
            "confirmed_at": info.get("confirmed_at"),
        })
    return rows


def _archive(cfg: Config) -> dict:
    rows = []
    for folder in _visible_dirs(cfg.archive_path):
        paths = _video_files(folder)
        rows.append({
            "name": folder.name,
            "count": len(paths),
            "tiers": _tier_counts(paths, cfg.cache_dir),
        })
    return {"total": sum(r["count"] for r in rows), "by_character": rows}


class RealSource:
    """Reads the Highlights and Output folders, the KO cache and state.json."""

    def __init__(self, config: Config):
        self.config = config
        self.fixture: str | None = None

    def read(self) -> dict:
        cfg = self.config
        state_data = state.load(cfg.state_path)
        return {
            "fixture": None,
            "generated_at": _now_iso(),
            "stale": False,
            "config_problems": _tool_problems(cfg),
            "job": None,
            "unsorted": _unsorted(cfg),
            "characters": _characters(cfg),
            "low_value": [],
            "compile_plan": None,
            "output_folders": _output_folders(cfg, state_data),
            "cleanup_plan": None,
            "archive": _archive(cfg),
            "activity": [],
            "notices": [],
        }


class FixtureSource:
    """One section 11 scenario from fixtures.py, as a fresh copy per read."""

    def __init__(self, name: str):
        if name not in fixtures.SCENARIOS:
            raise ValueError(f"unknown fixture scenario: {name!r}")
        self.fixture: str | None = name

    def read(self) -> dict:
        return fixtures.scenario(self.fixture)
