"""preview_icon.py - write the app mark at 16, 32 and 64 px so a person can look at it.

Usage:
    python scripts/preview_icon.py --out DEST_FOLDER

Writes icon-16.png, icon-32.png and icon-64.png into DEST_FOLDER (created if missing).
Stdlib and Pillow only; the renderer lives in src/gui/icon.py.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from gui import icon  # noqa: E402  (needs the src path above)

SIZES = (16, 32, 64)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the app mark at 16, 32 and 64 px.")
    parser.add_argument("--out", required=True, type=Path, help="folder to write the PNG files into")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        path = args.out / f"icon-{size}.png"
        path.write_bytes(icon.png_bytes(size))
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
