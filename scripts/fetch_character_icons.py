"""
fetch_character_icons.py - download one portrait per character into the local assets folder.

The GUI shows assets/characters/<FOLDER>.png next to each character when the file exists.
The art belongs to the game publisher, so each user fetches it on their own machine.
The folder is gitignored and nothing fetched here is committed.

The script reads the live heroes page and never hardcodes image URLs, because the build
segment in the URLs changes with site patches.

Stdlib only.

Usage:
    python scripts/fetch_character_icons.py [--dest DIR] [--force] [--dry-run]
"""

import argparse
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = REPO_ROOT / "assets" / "characters"
HEROES_URL = "https://www.marvelrivals.com/heroes/"
ALLOWED_PREFIX = "https://www.marvelrivals.com/"
USER_AGENT = "RivalsVidMaker icon fetch"
FETCH_TIMEOUT_S = 20
IMAGE_PAUSE_S = 0.3
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_NAME_RE = re.compile(r'\sdata-name="([^"]*)"')
_IMG_SRC_RE = re.compile(r'<img\b[^>]*?\ssrc="([^"]+)"', re.I)


def parse_heroes(page_html: str) -> list[tuple[str, str]]:
    """(FOLDER, avatar URL) for each hero anchor, in page order, one entry per folder."""
    heroes = []
    seen = set()
    for attrs, body in _ANCHOR_RE.findall(page_html):
        name_match = _NAME_RE.search(attrs)
        if not name_match:
            continue
        folder = re.sub(r"\s+", "_", html.unescape(name_match.group(1)).strip().upper())
        if not folder or folder in seen:
            continue
        avatar = None
        for src in _IMG_SRC_RE.findall(body):
            if src.rsplit("/", 1)[-1].startswith("avatar_"):
                avatar = src
                break
        if avatar is None:
            continue
        seen.add(folder)
        heroes.append((folder, avatar))
    return heroes


def fetch(url: str) -> bytes:
    """GET a marvelrivals.com URL and return the body. Any other URL is refused before a request."""
    if not url.startswith(ALLOWED_PREFIX):
        raise ValueError(f"refusing to fetch outside {ALLOWED_PREFIX}: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
        return response.read()


DEFAULT_FETCH = fetch


def _reason(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def main(argv=None, fetch=fetch) -> int:
    parser = argparse.ArgumentParser(description="Fetch character portraits into assets/characters.")
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help="folder to write <FOLDER>.png into")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    args = parser.parse_args(argv)

    dest = Path(args.dest)
    use_pause = fetch is DEFAULT_FETCH

    try:
        page = fetch(HEROES_URL).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"could not fetch the heroes page: {_reason(exc)}")
        return 1

    heroes = parse_heroes(page)
    if not heroes:
        print("No heroes found on the page; the site layout may have changed.")
        return 1

    if args.dry_run:
        would_save = would_keep = 0
        for folder, url in heroes:
            target = dest / f"{folder}.png"
            if target.exists() and not args.force:
                would_keep += 1
                print(f"keep: {folder}.png")
            else:
                would_save += 1
                print(f"save: {folder}.png from {url}")
        print(f"Would save {would_save}, keep {would_keep}. Folder: {dest}")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    saved = kept = failed = 0
    for folder, url in heroes:
        target = dest / f"{folder}.png"
        if target.exists() and not args.force:
            kept += 1
            continue
        try:
            data = fetch(url)
            if not data.startswith(PNG_SIGNATURE):
                raise ValueError("not a PNG")
            target.write_bytes(data)
            saved += 1
        except Exception as exc:
            failed += 1
            print(f"failed: {folder}: {_reason(exc)}")
        if use_pause:
            time.sleep(IMAGE_PAUSE_S)

    print(f"Saved {saved}, kept {kept}, failed {failed}. Folder: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
