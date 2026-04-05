"""
migrate_ko_json.py - One-off migration from .ko.json to .clip.json cache format.

Reads each .ko.json file in the cache tree, writes a .clip.json equivalent,
then deletes the original .ko.json.

Run ONCE after updating to the .clip.json cache format. Safe to re-run:
files already migrated (have a .clip.json) are skipped.

Usage:
    python scripts/once_off/migrate_ko_json.py [cache_dir]

    cache_dir: path to the cache root (default: data/cache/ next to this script)

The script walks the full cache tree recursively so month subfolders
(e.g. data/cache/THOR/2026-02/) are handled automatically.
"""

import json
import os
import sys
import time
from pathlib import Path


def _migrate_one(ko_path: Path, cache_root: Path) -> bool:
    """Migrate a single .ko.json to .clip.json. Returns True if migrated, False if skipped."""
    clip_path = ko_path.with_suffix("").with_suffix(".clip.json")

    if clip_path.exists():
        return False  # already migrated

    try:
        raw = json.loads(ko_path.read_text())
    except (OSError, ValueError) as e:
        print(f"  [ERROR] Could not read {ko_path.name}: {e}")
        return False

    # Build the new .clip.json entry
    entry: dict = {}

    # Copy cache key fields
    if "file_mtime" in raw:
        entry["file_mtime"] = raw["file_mtime"]

    # Reconstruct ko_result from old flat format
    if raw.get("_null_result"):
        entry["ko_result"] = None
    elif "tier" in raw:
        ko_result = {k: v for k, v in raw.items()
                     if k not in ("file_mtime", "clip_duration", "scan_time", "scan_pass")}
        entry["ko_result"] = ko_result
    else:
        # Bare empty dict or unrecognised format - treat as null result
        entry["ko_result"] = None

    # Carry over timing/metadata fields
    if "clip_duration" in raw:
        entry["duration"] = raw["clip_duration"]
    if "scan_time" in raw:
        entry["scan_time"] = raw["scan_time"]
    if "scan_pass" in raw:
        entry["scan_pass"] = raw["scan_pass"]

    # file_size was not stored in .ko.json - leave absent so cache_load
    # accepts the entry via the mtime-only backward-compat path.

    try:
        tmp = str(clip_path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(entry, f)
        os.replace(tmp, str(clip_path))
        ko_path.unlink()
        return True
    except OSError as e:
        print(f"  [ERROR] Could not write {clip_path.name}: {e}")
        return False


def migrate(cache_dir: Path) -> None:
    t0 = time.perf_counter()

    if not cache_dir.exists():
        print(f"Cache dir not found: {cache_dir}")
        sys.exit(1)

    ko_files = list(cache_dir.rglob("*.ko.json"))
    if not ko_files:
        print(f"No .ko.json files found in {cache_dir}")
        return

    print(f"Found {len(ko_files)} .ko.json file(s) in {cache_dir}")
    migrated = 0
    skipped = 0

    for ko_path in sorted(ko_files):
        rel = ko_path.relative_to(cache_dir)
        if _migrate_one(ko_path, cache_dir):
            print(f"  Migrated: {rel}")
            migrated += 1
        else:
            print(f"  Skipped:  {rel} (.clip.json already exists)")
            skipped += 1

    elapsed = time.perf_counter() - t0
    print()
    print(f"Done in {elapsed:.1f}s: {migrated} migrated, {skipped} skipped.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cache_dir = Path(sys.argv[1])
    else:
        # Default: data/cache/ two levels up from this script
        cache_dir = Path(__file__).parent.parent.parent / "data" / "cache"

    migrate(cache_dir)
