"""
clip_scanner.py - Scan a folder for video clips and probe their durations in parallel.

Replaces C++: ClipList.cpp
"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import clip_cache

VIDEO_EXTS = {".mp4"}  # Marvel Rivals only saves .mp4


@dataclass
class Clip:
    path: Path
    duration: float  # seconds

    @property
    def name(self) -> str:
        return self.path.name


def probe_duration(path: Path, ffprobe: Path) -> float:
    """Return clip duration in seconds, or 0.0 on failure."""
    result = subprocess.run(
        [str(ffprobe), "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _probe_with_cache(path: Path, ffprobe: Path, cache_dir: Path | None) -> float:
    """Probe duration, reading from and writing to .clip.json cache if cache_dir provided.

    On a cache hit, returns the stored duration without calling ffprobe.
    On a cache miss, calls probe_combined (fetches duration + resolution in one
    ffprobe call) and saves both to the cache entry.
    Falls back to probe_duration (no cache) when cache_dir is None.
    """
    if cache_dir is not None:
        hit, entry = clip_cache.cache_load(str(path), str(cache_dir))
        if hit and entry is not None and "duration" in entry:
            return entry["duration"]
        # Cache miss: probe duration + resolution together
        dur, w, h = clip_cache.probe_combined(str(path), str(ffprobe))
        if dur > 0:
            fields: dict = {"duration": round(dur, 2)}
            if w:
                fields["width"] = w
            if h:
                fields["height"] = h
            try:
                clip_cache.cache_save(str(path), str(cache_dir), **fields)
            except Exception as e:
                logging.debug("clip_scanner: could not save duration cache for %s: %s", path.name, e)
        return dur
    return probe_duration(path, ffprobe)


def summarize_folder(
    folder: Path,
    ffprobe: Path,
    workers: int = 8,
    cache_dir: Path | None = None,
) -> tuple[int, float]:
    """Return (clip_count, total_duration_seconds) without printing. Fast parallel probe.

    If cache_dir is provided, durations are read from .clip.json and newly
    probed durations are written there.
    """
    paths = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    if not paths:
        return 0, 0.0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        durations = list(pool.map(lambda p: _probe_with_cache(p, ffprobe, cache_dir), paths))
    count = sum(1 for d in durations if d > 0)
    total = sum(d for d in durations if d > 0)
    return count, total


def scan_folder(
    folder: Path,
    ffprobe: Path,
    workers: int = 8,
    protect_recent: int = 0,
    cache_dir: Path | None = None,
) -> list[Clip]:
    """
    Return all video clips in a folder, sorted alphabetically (= chronological
    for timestamp-named files), with durations probed in parallel.

    protect_recent: skip the N most recently saved clips (last N alphabetically).
    These stay untouched so their saved status remains visible in the game UI.

    If cache_dir is provided, durations are read from .clip.json and newly
    probed durations are written there (along with resolution).

    Clips that fail duration probing are skipped with a warning.
    """
    paths = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    if not paths:
        return []

    if protect_recent > 0:
        protected = paths[-protect_recent:]
        paths = paths[:-protect_recent]
        logging.info(
            "Found %d video file(s), protecting %d most recent.",
            len(paths) + len(protected),
            len(protected),
        )
        if not paths:
            logging.info("All clips are protected - nothing to process.")
            return []
    else:
        logging.info("Found %d video file(s). Probing durations...", len(paths))

    # Probe all durations in parallel - ffprobe is an external process so
    # threads give real concurrency here.
    ordered: list[Clip | None] = [None] * len(paths)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_probe_with_cache, p, ffprobe, cache_dir): i
            for i, p in enumerate(paths)
        }
        for future in as_completed(futures):
            i = futures[future]
            dur = future.result()
            if dur > 0:
                ordered[i] = Clip(path=paths[i], duration=dur)
                logging.debug("  Probed %s - %.1fs", paths[i].name, dur)
            else:
                logging.warning("Could not probe duration for %s - skipping.", paths[i].name)

    clips = [c for c in ordered if c is not None]
    logging.info("Loaded %d clip(s).", len(clips))
    return clips
