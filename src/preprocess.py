"""
preprocess.py — Pre-process mode: warm the KO detection cache for all clips.

Scans every clip across all character folders in config.clips_path and writes
cache entries so that future pipeline runs skip the slow detection step.

Does NOT batch, encode, or move any files — purely a cache-warming pass.

Usage:
    python src/preprocess.py              # uses config/config.json
    python src/preprocess.py my_cfg.json  # explicit config path
"""

import logging
import sys
import time
from pathlib import Path

import ko_detect
from clip_scanner import VIDEO_EXTS
from config import Config


def _rename_clip(clip_path: Path, tier: str | None) -> Path:
    """Rename a clip in-place to embed _TIER in the stem. Also renames the cache file.

    Returns the new path (or original path if no rename needed).
    """
    if not tier:
        return clip_path
    stem = clip_path.stem
    if any(stem.endswith(f"_{t}") for t in ko_detect.TIERS):
        return clip_path  # already renamed
    new_path = clip_path.with_stem(f"{stem}_{tier}")
    try:
        clip_path.rename(new_path)
        old_cache = Path(ko_detect.cache_path(str(clip_path)))
        new_cache = Path(ko_detect.cache_path(str(new_path)))
        if old_cache.exists() and not new_cache.exists():
            new_cache.parent.mkdir(parents=True, exist_ok=True)
            old_cache.rename(new_cache)
        logging.info("Renamed: %s -> %s", clip_path.name, new_path.name)
        return new_path
    except OSError as e:
        logging.warning("Could not rename %s: %s", clip_path.name, e)
        return clip_path


def preprocess_all(config: Config) -> dict[str, int]:
    """
    Scan all clips in all character subfolders of config.clips_path.

    For each clip:
      - If a cache entry already exists, skip (counts as scanned).
      - Otherwise run KO detection and write the cache entry.

    Returns {char_name: clip_count} for every character processed.
    Progress is logged at INFO level so it appears in the terminal.
    """
    clips_path = config.clips_path
    if not clips_path.exists():
        raise FileNotFoundError(f"Clips path not found: {clips_path}")

    char_folders = sorted(f for f in clips_path.iterdir() if f.is_dir())
    if not char_folders:
        logging.info("Pre-process: no character folders found in %s", clips_path)
        return {}

    # Count total clips upfront for overall progress reporting (excluding protected)
    all_clips: list[tuple[str, Path]] = []  # (char_name, clip_path)
    for folder in char_folders:
        folder_clips = sorted(p for p in folder.iterdir()
                              if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
        for p in folder_clips:
            all_clips.append((folder.name, p))

    if not all_clips:
        logging.info("Pre-process: no video clips found.")
        return {}

    total = len(all_clips)
    logging.info("Pre-processing %d clip(s) across %d character folder(s)...",
                 total, len(char_folders))

    results: dict[str, int] = {}
    done = 0
    t_start = time.perf_counter()

    # Process character by character so configure() is called once per character
    for folder in char_folders:
        char_name = folder.name
        clips = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        )
        if not clips:
            continue

        ko_detect.configure(
            ffmpeg=str(config.ffmpeg),
            tesseract=str(config.tesseract),
            cache_dir=str(config.cache_dir / char_name),
        )

        char_done = 0
        for clip_path in clips:
            done += 1
            hit, cached_result = ko_detect.cache_load(str(clip_path))
            if hit:
                tier = cached_result["tier"] if cached_result else None
                clip_path = _rename_clip(clip_path, tier)
                logging.info("[%d/%d] [cached] %s", done, total, clip_path.name)
                char_done += 1
                continue

            logging.info("[%d/%d] Scanning %s...", done, total, clip_path.name)
            t0 = time.perf_counter()
            result = ko_detect.scan_clip(str(clip_path), use_cache=True)
            elapsed = time.perf_counter() - t0

            tier = result["tier"] if result else None
            tier_label = tier or "none"
            elapsed_str = (
                f"{int(elapsed) // 60}m{int(elapsed) % 60:02d}s"
                if elapsed >= 60
                else f"{elapsed:.1f}s"
            )
            logging.info("[%d/%d] Done (%s) - %s", done, total, elapsed_str, tier_label)
            clip_path = _rename_clip(clip_path, tier)
            char_done += 1

        results[char_name] = char_done

    total_elapsed = time.perf_counter() - t_start
    elapsed_str = (
        f"{int(total_elapsed) // 60}m {int(total_elapsed) % 60:02d}s"
        if total_elapsed >= 60
        else f"{total_elapsed:.1f}s"
    )
    logging.info("Pre-processing complete — %d clip(s) in %s", total, elapsed_str)
    return results


if __name__ == "__main__":
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    from config import load as load_config

    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/config.json")
    try:
        cfg = load_config(cfg_path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    preprocess_all(cfg)
