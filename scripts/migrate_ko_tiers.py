"""
migrate_ko_tiers.py - One-off KO-tier rename migration for legacy output folders.

Scans clips that have no KO-tier suffix in their filename, runs ko_detect on each,
and renames them with the detected tier (e.g. _QUAD, _PENTA, _HEXA).

Usage:
    python scripts/migrate_ko_tiers.py            # dry-run (no files changed)
    python scripts/migrate_ko_tiers.py --execute  # actually rename files

Legacy folders targeted:
    Output/thor_vid1/          (clips in root, no clips/ subfolder)
    Output/thor_vid2/vid2_clips/
"""

import argparse
import re
import sys
import time
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ko_detect
from clip_scanner import VIDEO_EXTS
from config import load as load_config


TIER_SUFFIX_PAT = re.compile(r'_(KO|DOUBLE|TRIPLE|QUAD|PENTA|HEXA)$', re.IGNORECASE)
CLIP_NAME_PAT = re.compile(r'^\w+_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}')  # CHAR_YYYY-MM-DD_HH-MM-SS


def already_has_tier(stem: str) -> bool:
    return bool(TIER_SUFFIX_PAT.search(stem))


def scan_and_rename(folder: Path, config, dry_run: bool) -> tuple[int, int, int]:
    """Scan all clips in folder, rename those with a detected KO tier.

    Returns (total, renamed, skipped_already_tagged).
    """
    if not folder.exists():
        print(f"  [SKIP] Folder not found: {folder}")
        return 0, 0, 0

    clips = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in VIDEO_EXTS
                   and CLIP_NAME_PAT.match(p.stem))

    total = len(clips)
    renamed = 0
    already_tagged = 0

    print(f"\n  Folder: {folder}")
    print(f"  {total} clip(s) found")

    # Derive char name from first clip filename
    char_name = clips[0].stem.split("_")[0] if clips else "UNKNOWN"
    ko_detect.configure(
        ffmpeg=str(config.ffmpeg),
        tesseract=str(config.tesseract),
        cache_dir=str(config.cache_dir / char_name),
    )

    for clip in clips:
        if already_has_tier(clip.stem):
            print(f"  [SKIP] Already tagged: {clip.name}")
            already_tagged += 1
            continue

        was_cached = ko_detect.cache_exists(str(clip))
        t0 = time.perf_counter()
        result = ko_detect.scan_clip(str(clip), use_cache=True)
        elapsed = time.perf_counter() - t0
        cache_tag = "[cached] " if was_cached else f"[{elapsed:.1f}s] "

        if result:
            tier = result["tier"]
            new_name = clip.stem + f"_{tier}" + clip.suffix
            new_path = clip.parent / new_name
            if dry_run:
                print(f"  {cache_tag}WOULD RENAME: {clip.name} -> {new_name}")
            else:
                clip.rename(new_path)
                print(f"  {cache_tag}RENAMED: {clip.name} -> {new_name}")
            renamed += 1
        else:
            print(f"  {cache_tag}No kill detected: {clip.name}")

    return total, renamed, already_tagged


def main():
    parser = argparse.ArgumentParser(description="Migrate legacy clips to KO-tier filenames.")
    parser.add_argument("--execute", action="store_true",
                        help="Actually rename files (default is dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute

    config = load_config()

    # Scan all clips/ subfolders within Output
    folders = sorted(config.output_path.rglob("clips"))

    print("=" * 60)
    print("KO-Tier Migration", "- DRY RUN (pass --execute to apply)" if dry_run else "- EXECUTING")
    print("=" * 60)

    total_clips = 0
    total_renamed = 0

    for folder in folders:
        t, r, s = scan_and_rename(folder, config, dry_run)
        total_clips += t
        total_renamed += r

    print()
    print("=" * 60)
    action = "Would rename" if dry_run else "Renamed"
    print(f"  {action} {total_renamed} of {total_clips} clip(s)")
    if dry_run:
        print("  Run with --execute to apply changes.")
    print("=" * 60)


if __name__ == "__main__":
    main()
