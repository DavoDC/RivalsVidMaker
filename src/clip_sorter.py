"""
clip_sorter.py - Move unsorted clip files from clips_path root into per-character subfolders.

Filename convention: {CHARACTER NAME}_{YYYY}-{MM}-{DD}_{HH}-{MM}-{SS}.mp4
Character names may contain letters, digits, spaces, or underscores.
Spaces in the character name are normalised to underscores in the folder name.

Examples:
    THOR_2026-02-06_22-38-56.mp4            →  THOR/
    SQUIRREL GIRL_2026-03-13_21-51-02.mp4   →  SQUIRREL_GIRL/
    BLACK WIDOW_2026-01-15_08-00-00.mp4     →  BLACK_WIDOW/

Only files sitting directly in clips_path are touched.
Subfolders (e.g. THOR/vid1_uploaded/) are never read or modified here.

Safety rules:
- Uses shutil.move() - atomic rename on same filesystem, no copy+delete.
- Skips any file whose character name cannot be parsed.
- Skips if the destination already exists (never overwrites).
- Returns the number of files successfully moved.
"""

import logging
import re
import shutil
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Lazily match everything up to the first _YYYY-MM-DD_ date stamp.
# The character name must start with a letter.
_CHAR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _]*)_(\d{4}-\d{2}-\d{2}_)")


def extract_character(stem: str) -> str | None:
    """
    Parse and normalise the character name from a clip filename stem.

    Returns the folder-safe character name (spaces → underscores),
    or None if the filename doesn't match the expected convention.

    Examples:
        "THOR_2026-02-06_22-38-56"           → "THOR"
        "SQUIRREL GIRL_2026-03-13_21-51-02"  → "SQUIRREL_GIRL"
        "just_a_random_file"                 → None
    """
    m = _CHAR_RE.match(stem)
    if not m:
        return None
    char_raw = m.group(1).strip()
    if not char_raw:
        return None
    return re.sub(r"\s+", "_", char_raw)


def sort_clips(clips_path: Path, protect_recent: int = 0) -> int:
    """
    Move any video files sitting directly in clips_path into per-character subfolders.

    protect_recent: leave the N most recently saved clips (last N alphabetically)
    in the root untouched, so their saved status stays visible in the game UI.

    Subfolders that already exist (e.g. THOR/vid1_uploaded/) are not touched.
    Returns the number of files moved.
    """
    video_files = sorted(
        p for p in clips_path.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )

    if not video_files:
        logging.info("Sorting clips... 0 file(s) moved.")
        return 0

    if protect_recent > 0 and protect_recent < len(video_files):
        to_sort = video_files[:-protect_recent]
        protected_count = protect_recent
    elif protect_recent >= len(video_files):
        logging.info(
            "Sorting clips... 0 file(s) moved. (%d kept unsorted - protected)",
            len(video_files),
        )
        return 0
    else:
        to_sort = video_files
        protected_count = 0

    moved = 0

    for src in to_sort:
        char = extract_character(src.stem)
        if char is None:
            logging.warning("  SKIP (cannot parse character name): %s", src.name)
            continue

        dest_dir = clips_path / char
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / src.name

        if dest.exists():
            logging.warning(
                "  SKIP (destination already exists): %s -> %s/", src.name, char
            )
            continue

        logging.debug("  Moving: %s -> %s/", src.name, char)
        shutil.move(str(src), str(dest))
        moved += 1

    if protected_count:
        logging.info(
            "Sorting clips... %d file(s) moved. (%d kept unsorted - protected)",
            moved, protected_count,
        )
    else:
        logging.info("Sorting clips... %d file(s) moved.", moved)

    return moved
