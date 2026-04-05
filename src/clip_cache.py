"""
clip_cache.py - Unified per-clip cache (.clip.json).

Replaces .ko.json from ko_detect.py. Stores all per-clip data in one place:
KO result, fingerprint hashes, duration, resolution.

Cache key: file mtime + size (both must match for a cache hit).
Partial updates: cache_save() merges new fields into an existing entry
so ko_detect.py and dedup.py can each write their own fields independently.

File layout (mirrors old .ko.json structure):
  <cache_dir>/<YYYY-MM>/<stem>.clip.json  (dated clips, e.g. THOR_2026-02-06)
  <cache_dir>/<stem>.clip.json            (undated clips)

Field semantics:
  file_mtime   float      - cache key (auto-updated on every save)
  file_size    int        - cache key (auto-updated on every save)
  ko_result    dict|None  - KO detection output; None = scanned, no kill found
                           Key ABSENT = not yet scanned (distinguishes from null result)
  fingerprint  list[str]  - pHash hex strings (one per sampled frame)
                           Key ABSENT = not yet fingerprinted
  duration     float      - seconds (from ffprobe)
  width        int        - pixels
  height       int        - pixels
"""

import json
import os
import re
import subprocess
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _month_from_stem(stem: str) -> str | None:
    """Extract YYYY-MM from a clip stem like THOR_2026-02-06_22-38-56."""
    m = re.search(r"(\d{4}-\d{2})-\d{2}", stem)
    return m.group(1) if m else None


def _file_mtime(clip_path: str) -> float:
    try:
        return os.path.getmtime(clip_path)
    except OSError:
        return 0.0


def _file_size(clip_path: str) -> int:
    try:
        return os.path.getsize(clip_path)
    except OSError:
        return 0


# ── Public API ────────────────────────────────────────────────────────────────

def cache_path(clip_path: str, cache_dir: str) -> str:
    """Return the .clip.json path for a clip.

    Dated clips (YYYY-MM-DD in stem) get a YYYY-MM month subfolder.
    Undated clips fall back to the cache_dir root.
    """
    stem = Path(clip_path).stem
    month = _month_from_stem(stem)
    if month:
        return os.path.join(cache_dir, month, f"{stem}.clip.json")
    return os.path.join(cache_dir, f"{stem}.clip.json")


def cache_load(clip_path: str, cache_dir: str) -> tuple[bool, dict | None]:
    """Load cache entry for a clip.

    Returns (hit, entry_dict).
      hit=False -> not in cache, cache file corrupt, or stale (mtime or size changed)
      hit=True  -> entry_dict contains cached fields (may be missing optional fields)

    The returned entry_dict includes all stored fields. Callers check for
    specific field presence (e.g. "ko_result" in entry) rather than a hit flag
    per field.
    """
    p = cache_path(clip_path, cache_dir)
    if not os.path.exists(p):
        return False, None
    try:
        with open(p) as f:
            entry = json.load(f)
    except (OSError, ValueError):
        return False, None

    if not isinstance(entry, dict):
        return False, None

    # Validate cache key: both mtime and size must match
    stored_mtime = entry.get("file_mtime")
    stored_size = entry.get("file_size")

    current_mtime = _file_mtime(clip_path)
    current_size = _file_size(clip_path)

    # Missing mtime means the clip file is gone (or permission error)
    if current_mtime == 0.0 or current_size == 0:
        return False, None

    if stored_mtime is not None and stored_mtime != current_mtime:
        return False, None
    if stored_size is not None and stored_size != current_size:
        return False, None

    # Strip internal cache-key fields before returning to callers
    data = {k: v for k, v in entry.items() if k not in ("file_mtime", "file_size")}
    return True, data


def cache_save(clip_path: str, cache_dir: str, **fields) -> None:
    """Write or update a cache entry for a clip.

    Merges `fields` into any existing entry, then refreshes the cache key
    (file_mtime and file_size). Creating new entries and partial updates
    (e.g. adding fingerprint to an entry that already has ko_result) both
    use this same function.

    Writes atomically via a .tmp file so a crash mid-write never leaves a
    corrupt entry.
    """
    p = cache_path(clip_path, cache_dir)

    # Load existing entry (if any) so partial updates preserve other fields
    existing: dict = {}
    if os.path.exists(p):
        try:
            with open(p) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}

    # Merge new fields over existing
    existing.update(fields)

    # Refresh cache key
    existing["file_mtime"] = _file_mtime(clip_path)
    existing["file_size"] = _file_size(clip_path)

    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(existing, f)
    os.replace(tmp, p)


def probe_combined(clip_path: str, ffprobe: str) -> tuple[float, int, int]:
    """Probe duration + resolution in a single ffprobe call.

    Returns (duration_secs, width, height).
    Returns (0.0, 0, 0) on any failure.

    Replaces probe_duration() (minimal call) with a single wider call that
    fetches all cacheable metadata at once.
    """
    r = subprocess.run(
        [ffprobe, "-v", "error",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json",
         clip_path],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(r.stdout)
        duration = float(data.get("format", {}).get("duration", 0) or 0)
        for stream in data.get("streams", []):
            w = stream.get("width")
            h = stream.get("height")
            if w and h:
                return duration, int(w), int(h)
        return duration, 0, 0
    except (ValueError, KeyError, TypeError):
        return 0.0, 0, 0
