"""
clip_scanner.py — Scan a folder for video clips and probe their durations in parallel.

Replaces C++: ClipList.cpp
"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


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


def summarize_folder(folder: Path, ffprobe: Path, workers: int = 8) -> tuple[int, float]:
    """Return (clip_count, total_duration_seconds) without printing. Fast parallel probe."""
    paths = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    if not paths:
        return 0, 0.0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        durations = list(pool.map(lambda p: probe_duration(p, ffprobe), paths))
    count = sum(1 for d in durations if d > 0)
    total = sum(d for d in durations if d > 0)
    return count, total


def scan_folder(folder: Path, ffprobe: Path, workers: int = 8, protect_recent: int = 0) -> list[Clip]:
    """
    Return all video clips in a folder, sorted alphabetically (= chronological
    for timestamp-named files), with durations probed in parallel.

    protect_recent: skip the N most recently saved clips (last N alphabetically).
    These stay untouched so their saved status remains visible in the game UI.

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

    # Probe all durations in parallel — ffprobe is an external process so
    # threads give real concurrency here.
    ordered: list[Clip | None] = [None] * len(paths)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(probe_duration, p, ffprobe): i
            for i, p in enumerate(paths)
        }
        for future in as_completed(futures):
            i = futures[future]
            dur = future.result()
            if dur > 0:
                ordered[i] = Clip(path=paths[i], duration=dur)
                logging.debug("  Probed %s — %.1fs", paths[i].name, dur)
            else:
                logging.warning("Could not probe duration for %s — skipping.", paths[i].name)

    clips = [c for c in ordered if c is not None]
    logging.info("Loaded %d clip(s).", len(clips))
    return clips
