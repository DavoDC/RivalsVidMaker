"""
make_scratch_library.py - build a small fake clip library and a matching config.json.

The GUI can then run end to end on the scratch library without touching the real one:
    python -m gui --config DEST/config.json

Stdlib only, plus ffmpeg to encode the placeholder clips.

Usage:
    python scripts/make_scratch_library.py DEST [--ffmpeg-dir DIR] [--seconds N] [--force]
"""

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FFMPEG_DIR = REPO_ROOT / "dependencies" / "ffmpeg"
MARKER = ".scratch-library"
BASE_TIME = dt.datetime(2026, 11, 1, 10, 0, 0)
CLIP_TIMEOUT_S = 60

# Folder (relative to DEST) -> number of clips. Order is creation order.
LAYOUT = {
    "Highlights": 3,
    "Highlights/THOR": 4,
    "Highlights/HELA": 3,
    "Output": 0,
    "ClipArchive": 0,
    "cache": 0,
}


def clip_names(count, start_index):
    """Clip file names with increasing timestamps, so name order is creation order."""
    names = []
    for k in range(count):
        when = BASE_TIME + dt.timedelta(minutes=start_index + k)
        names.append(f"Marvel Rivals_{when:%Y.%m.%d-%H.%M.%S}.mp4")
    return names


def layout():
    """Folder (relative to DEST) -> clip count, in creation order."""
    return dict(LAYOUT)


def config_dict(dest, ffmpeg_dir):
    """The config.json contents, with every path absolute and inside dest."""
    root = Path(dest).resolve()
    return {
        "clips_path": str(root / "Highlights"),
        "output_path": str(root / "Output"),
        "archive_path": str(root / "ClipArchive"),
        "cache_dir": str(root / "cache"),
        "state_path": str(root / "state.json"),
        "ffmpeg_path": str(Path(ffmpeg_dir).resolve()),
        "youtube_channel_id": "SCRATCH",
        "min_batch_seconds": 20,
        "target_batch_seconds": 40,
        "protect_recent_clips": 1,
        "force_rescan_cache": False,
    }


def write_config(dest, ffmpeg_dir):
    """Write DEST/config.json and return its path."""
    path = Path(dest) / "config.json"
    path.write_text(json.dumps(config_dict(dest, ffmpeg_dir), indent=2) + "\n", encoding="utf-8")
    return path


def check_dest(dest, force):
    """None when DEST may be built into, else the one-sentence refusal."""
    dest = Path(dest)
    if not dest.exists():
        return None
    if not dest.is_dir():
        return "DEST exists and is not a folder, so it will not be touched."
    if not any(dest.iterdir()):
        return None
    if not (dest / MARKER).is_file():
        return "DEST is not empty and was not made by this script, so it will not be touched."
    if force:
        return None
    return "DEST already holds a scratch library; rerun with --force to rebuild it."


def make_clip(ffmpeg, path, seconds):
    """Encode one placeholder clip: test pattern video plus a 440 Hz tone."""
    cmd = [
        str(ffmpeg), "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440",
        "-t", str(seconds),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(
        cmd,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=CLIP_TIMEOUT_S,
        creationflags=flags,
    )


def _parse(argv):
    parser = argparse.ArgumentParser(description="Build a fake clip library and config.json.")
    parser.add_argument("dest", help="folder to build the scratch library in")
    parser.add_argument("--ffmpeg-dir", type=Path, default=DEFAULT_FFMPEG_DIR,
                        help="folder holding ffmpeg.exe (default: dependencies/ffmpeg)")
    parser.add_argument("--seconds", type=int, default=8, help="length of each clip (default: 8)")
    parser.add_argument("--force", action="store_true",
                        help="rebuild DEST, only if it holds this script's marker file")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse(argv)
    started = time.monotonic()
    dest = Path(args.dest).resolve()

    reason = check_dest(dest, args.force)
    if reason:
        print(reason, file=sys.stderr)
        return 2

    ffdir = Path(args.ffmpeg_dir).resolve()
    ffmpeg = ffdir / "ffmpeg.exe"
    if not ffmpeg.is_file():
        print(f"ffmpeg.exe not found at {ffmpeg}; pass --ffmpeg-dir.", file=sys.stderr)
        return 2

    if dest.exists():
        shutil.rmtree(dest)  # reached only when check_dest accepted: empty, or marked with --force
    dest.mkdir(parents=True)
    (dest / MARKER).write_text("Written by scripts/make_scratch_library.py.\n", encoding="utf-8")

    counts = layout()
    for folder in counts:
        (dest / folder).mkdir(parents=True, exist_ok=True)

    index = 0
    for folder, count in counts.items():
        for name in clip_names(count, index):
            try:
                make_clip(ffmpeg, dest / folder / name, args.seconds)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                print(f"ffmpeg failed on {name}: {exc}", file=sys.stderr)
                return 1
        index += count

    (dest / "state.json").write_text("{}\n", encoding="utf-8")
    cfg_path = write_config(dest, ffdir)
    elapsed = time.monotonic() - started
    print(f"config: {cfg_path}")
    print(f"clips: {sum(counts.values())} (loose {counts['Highlights']}, "
          f"THOR {counts['Highlights/THOR']}, HELA {counts['Highlights/HELA']}); "
          f"elapsed {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
