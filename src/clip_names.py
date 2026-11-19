"""
clip_names.py - Read the character from a clip file name. Pure: no file system access.

Filename convention: {CHARACTER NAME}_{YYYY}-{MM}-{DD}_{HH}-{MM}-{SS}.mp4
Shared by clip_sorter (which moves files) and the read-only GUI sources.
"""

import re
from datetime import datetime


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


_KNOWN_TIERS = ("KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA")
_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


def standard_clip_name(character: str, capture_dt: datetime, tier: str | None = None) -> str:
    """
    Build the archive file name: {CHARACTER}_{YYYY-MM-DD}_{HH-MM-SS}[_{TIER}].mp4

    Datetime comes before the tier, as in ClipArchive. The character keeps the game's spacing
    ("SQUIRREL GIRL"); the folder name uses underscores via extract_character. Raises ValueError
    if the name would not parse back to the same character and tier.

    Examples:
        ("THOR", 2026-02-06 22:38:56, "QUAD") → "THOR_2026-02-06_22-38-56_QUAD.mp4"
        ("SQUIRREL GIRL", 2026-03-13 21:51:02, None) → "SQUIRREL GIRL_2026-03-13_21-51-02.mp4"
    """
    char = character.strip()
    if tier is not None:
        tier = tier.upper()
        if tier not in _KNOWN_TIERS:
            raise ValueError(f"unknown tier: {tier!r}")
    stem = f"{char}_{capture_dt.strftime(_STAMP_FORMAT)}"
    name = f"{stem}_{tier}.mp4" if tier else f"{stem}.mp4"

    # Inverse check through the same parsers the pipeline uses.
    if extract_character(stem) != re.sub(r"\s+", "_", char) or tier_from_name(name) != tier:
        raise ValueError(f"clip name does not round-trip: {name!r}")
    return name

