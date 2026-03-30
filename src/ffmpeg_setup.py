"""
ffmpeg_setup.py - Ensure FFmpeg binaries exist; auto-download if missing.

Called on startup. Checks for ffmpeg.exe and ffprobe.exe at the configured
path. If either is missing, downloads the latest FFmpeg Windows build from
GitHub (BtbN/FFmpeg-Builds) and extracts the binaries.
"""

import logging
import tempfile
import urllib.request
import zipfile
from pathlib import Path

_FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
_FFMPEG_BINS = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}


def ensure_ffmpeg(ffmpeg_dir: Path) -> bool:
    """
    Check if ffmpeg.exe and ffprobe.exe exist at ffmpeg_dir.
    If not, download the latest FFmpeg Windows GPL build and extract them.

    Returns True if binaries are ready, False if download failed.
    """
    if (ffmpeg_dir / "ffmpeg.exe").exists() and (ffmpeg_dir / "ffprobe.exe").exists():
        return True

    logging.info("FFmpeg not found at %s - downloading...", ffmpeg_dir)
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip")
    tmp_path = Path(tmp_name)
    import os
    os.close(tmp_fd)

    try:
        print(f"Downloading FFmpeg from GitHub (this may take a minute)...")
        urllib.request.urlretrieve(_FFMPEG_URL, str(tmp_path), _progress_cb)
        print()  # newline after inline progress

        logging.info("Extracting FFmpeg binaries...")
        extracted = 0
        with zipfile.ZipFile(str(tmp_path)) as zf:
            for member in zf.namelist():
                name = Path(member).name
                if name in _FFMPEG_BINS:
                    data = zf.read(member)
                    out = ffmpeg_dir / name
                    out.write_bytes(data)
                    logging.info("  Extracted: %s (%.1f MB)", name, len(data) / 1024 / 1024)
                    extracted += 1

        if extracted == 0:
            logging.error("No FFmpeg binaries found in downloaded archive.")
            return False

        logging.info("FFmpeg ready at %s", ffmpeg_dir)
        return True

    except Exception as e:
        logging.error("Failed to download FFmpeg: %s", e)
        logging.error(
            "Download manually from https://ffmpeg.org/download.html "
            "and place in %s",
            ffmpeg_dir,
        )
        return False
    finally:
        tmp_path.unlink(missing_ok=True)


def _progress_cb(count: int, block_size: int, total_size: int) -> None:
    """urllib progress callback - prints inline percentage."""
    if total_size > 0:
        pct = min(count * block_size * 100 / total_size, 100)
        downloaded_mb = count * block_size / 1024 / 1024
        total_mb = total_size / 1024 / 1024
        print(
            f"\r  {pct:.0f}%  ({downloaded_mb:.1f} / {total_mb:.0f} MB)",
            end="",
            flush=True,
        )
