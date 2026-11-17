"""
clip_names.py - Read the character from a clip file name. Pure: no file system access.

Filename convention: {CHARACTER NAME}_{YYYY}-{MM}-{DD}_{HH}-{MM}-{SS}.mp4
Shared by clip_sorter (which moves files) and the read-only GUI sources.
"""

import re


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


# Regex that matches the _TIER suffix embedded in a clip filename
TIER_SUFFIX_RE = re.compile(r"_(QUAD|PENTA|HEXA|TRIPLE|DOUBLE|KO)(?=\.mp4$)", re.IGNORECASE)


def tier_from_name(name: str) -> str | None:
    """Extract the embedded KO tier from a clip filename, e.g. '_QUAD' → 'QUAD'."""
    m = TIER_SUFFIX_RE.search(name)
    return m.group(1).upper() if m else None

