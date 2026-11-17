"""Character names and avatars for the Clips tab: display_name turns a folder name into words, avatar_html draws
the portrait when one is in assets/characters, else an initials badge. Portraits are game art fetched locally
and never committed (.gitignore), so the badge is the normal state in a fresh clone.

Colours and sizes come from tokens.py only. register() mounts the asset folder at /characters.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

from gui import tokens

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = REPO_ROOT / "assets" / "characters"
URL_PREFIX = "/characters"

_SIZE = 28
_SMALL_WORDS = frozenset({"the", "of", "and"})
_SPLIT = re.compile(r"[_\s]+")


def _words(folder: str) -> list[str]:
    return [w for w in _SPLIT.split(folder) if w]


def display_name(folder: str) -> str:
    """DOCTOR_STRANGE reads Doctor Strange; the small words stay lower case except as the first word."""
    out = []
    for index, word in enumerate(_words(folder)):
        lower = word.lower()
        out.append(lower if index and lower in _SMALL_WORDS else lower.capitalize())
    return " ".join(out)


def initials(folder: str) -> str:
    """First letters of the first and last word (DS); a single word gives its first two letters (TH)."""
    words = _words(folder)
    if not words:
        return ""
    if len(words) >= 2:
        return (words[0][0] + words[-1][0]).upper()
    return words[0][:2].upper()


def _has_portrait(folder: str, asset_dir: Path) -> bool:
    try:
        return (asset_dir / f"{folder}.png").is_file()
    except OSError:
        return False


def avatar_html(folder: str, asset_dir: Path | None = None) -> str:
    """A 28 px square: the portrait when <asset_dir>/<FOLDER>.png exists, else the initials badge."""
    folder_dir = ASSET_DIR if asset_dir is None else asset_dir
    base = (f"flex:none;width:{_SIZE}px;height:{_SIZE}px;border-radius:{tokens.RADIUS_PANEL}px;"
            f"box-sizing:border-box;")
    name = escape(folder, quote=True)
    if _has_portrait(folder, folder_dir):
        return (f'<img src="{URL_PREFIX}/{name}.png" alt="" aria-hidden="true" width="{_SIZE}" height="{_SIZE}" '
                f'style="{base}object-fit:cover;">')
    style = (f"{base}display:inline-flex;align-items:center;justify-content:center;"
             f"background:{tokens.PANEL};border:1px solid {tokens.LINE};color:{tokens.TEXT_DIM};"
             f"font-size:{tokens.SIZE_FINE}px;font-weight:600;")
    return f'<span aria-hidden="true" style="{style}">{escape(initials(folder))}</span>'


def register(app) -> None:
    """Create the asset folder (it may be empty) and serve it at /characters."""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    app.add_static_files(URL_PREFIX, str(ASSET_DIR))
