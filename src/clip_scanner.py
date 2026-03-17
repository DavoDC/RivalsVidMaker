"""
clip_scanner.py — Scan a folder for video clips and probe their durations in parallel.

Replaces C++: ClipList.cpp
"""

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


def scan_folder(folder: Path, ffprobe: Path, workers: int = 8) -> list[Clip]:
    """
    Return all video clips in a folder, sorted alphabetically (= chronological
    for timestamp-named files), with durations probed in parallel.

    Clips that fail duration probing are skipped with a warning.
    """
    paths = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    if not paths:
        return []

    print(f"  Found {len(paths)} video file(s). Probing durations...")

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
            else:
                print(f"  WARNING: could not probe duration for {paths[i].name} — skipping.")

    clips = [c for c in ordered if c is not None]
    print(f"  Loaded {len(clips)} clip(s).")
    return clips
