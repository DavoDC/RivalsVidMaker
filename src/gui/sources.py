"""Data sources for the GUI (design plan sections 5 and 6).

A Source returns the raw inputs for one snapshot as plain dicts. view_model
turns them into the /state.json contract; nothing here shapes UI rows.

READ-ONLY: this module must never move, rename, delete or write a file, and
must never create a folder. It may use only these engine helpers:
  state.load, clip_cache.cache_load, clip_cache.character_cache_dir,
  batcher.make_batches,
  clip_scanner (VIDEO_EXTS, Clip) and the Config type.
tests/gui/test_gui_sources.py parses this file and fails on anything else.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

import batcher
import clip_cache
import clip_names
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
        if tier not in counts:
            tier = clip_names.tier_from_name(path.name)
        if tier in counts:
            counts[tier] += 1
    return counts


def _tool_problems(cfg: Config) -> list[str]:
    checks = (("ffmpeg", cfg.ffmpeg), ("ffprobe", cfg.ffprobe), ("tesseract", cfg.tesseract))
    return [f"{label} not found" for label, path in checks if not Path(path).exists()]


def _unsorted(cfg: Config) -> list[dict]:
    paths = _video_files(cfg.clips_path)
    cut = len(paths) - max(0, cfg.protect_recent_clips)
    return [{"name": p.name, "protected": i >= cut,
             "recognised": clip_names.extract_character(p.stem) is not None}
            for i, p in enumerate(paths)]


def _character(folder: Path, cfg: Config) -> dict:
    paths = _video_files(folder)
    scanned: list[Clip] = []
    for path in paths:
        entry = _cache_entry(path, clip_cache.character_cache_dir(cfg.cache_dir, folder.name))
        duration = entry.get("duration") if entry else None
        if isinstance(duration, (int, float)) and duration > 0:
            scanned.append(Clip(path=path, duration=float(duration)))
    total = sum(c.duration for c in scanned)
    batches = batcher.make_batches(scanned, target=cfg.target_batch_seconds)
    return {
        "name": folder.name,
        "clips": len(paths),
        "minutes": round(total / 60, 1),
        "seconds": round(total),
        "scanned": len(scanned),
        "unscanned": len(paths) - len(scanned),
        "tiers": _tier_counts(paths, clip_cache.character_cache_dir(cfg.cache_dir, folder.name)),
        "ready": any(b.total_duration >= cfg.min_batch_seconds for b in batches),
    }


def _characters(cfg: Config) -> list[dict]:
    return [_character(d, cfg) for d in _visible_dirs(cfg.clips_path)]


QUAD_PLUS_TIERS = ("QUAD", "PENTA", "HEXA")  # the cleanup.ARCHIVE_MIN_TIERS set, as a tuple


def _clips_manifest(folder: Path) -> dict | None:
    """clips.json as a dict when readable JSON object, else None. Never raises."""
    try:
        data = json.loads((folder / "clips.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _manifest_clips(manifest: dict | None) -> list | None:
    clips = manifest.get("clips") if manifest else None
    return clips if isinstance(clips, list) else None


def _folder_character(folder: Path, manifest: dict | None) -> str:
    char = manifest.get("char") if manifest else None
    if isinstance(char, str):
        return char
    return folder.name.split("_", 1)[0].upper()


def _clip_counts(folder: Path, manifest: dict | None) -> tuple[int, int]:
    """(clips, quad_plus): clips.json entries when readable, else the clips/ folder count."""
    clips = _manifest_clips(manifest)
    if clips is None:
        return len(_video_files(folder / "clips")), 0
    quad_plus = sum(1 for c in clips if isinstance(c, dict) and c.get("tier") in QUAD_PLUS_TIERS)
    return len(clips), quad_plus


def _video_url(state_data: dict, slug: str) -> str | None:
    videos = state_data.get("videos")
    entry = videos.get(slug) if isinstance(videos, dict) else None
    url = entry.get("url") if isinstance(entry, dict) else None
    return url if isinstance(url, str) else None


def _output_folders(cfg: Config, state_data: dict) -> list[dict]:
    folders = state_data.get("output_folders")
    safe_state = {"output_folders": folders if isinstance(folders, dict) else {}}
    rows = []
    for folder in _visible_dirs(cfg.output_path):
        info = safe_state["output_folders"].get(folder.name)
        info = info if isinstance(info, dict) else {}
        manifest = _clips_manifest(folder)
        videos = _video_files(folder)
        clips, quad_plus = _clip_counts(folder, manifest)
        rows.append({
            "slug": folder.name,
            "character": _folder_character(folder, manifest),
            "months": None,  # no source yet; the key stays so the contract shape holds
            "video_count": len(videos),
            "has_video": len(videos) > 0,
            "has_desc": any(p.is_file() for p in folder.glob("*_description.txt")),
            "clips": clips,
            "quad_plus": quad_plus,
            "has_clips_dir": (folder / "clips").is_dir(),
            "video_url": _video_url(state_data, folder.name),
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
            "tiers": _tier_counts(paths, clip_cache.character_cache_dir(cfg.cache_dir, folder.name)),
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
