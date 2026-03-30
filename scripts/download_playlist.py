"""
download_playlist.py - Download all videos from the Marvel Rivals YouTube playlist.

Downloads at highest available quality (bestvideo+bestaudio merged to mp4).
Skips already-downloaded files - safe to re-run at any time.

Setup: copy yt-dlp.exe to tools/ (from SBS_Download/dependencies/)
Usage: python scripts/download_playlist.py
"""

import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

YTDLP_PATH = Path(__file__).parent.parent / "tools" / "yt-dlp.exe"
OUTPUT_DIR = Path(r"C:\Users\David\Videos\MarvelRivals\OldCompilations")
PLAYLIST_URL = "https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W"

# ---------------------------------------------------------------------------


def build_command(output_dir: Path) -> list[str]:
    return [
        str(YTDLP_PATH),
        "--format", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--output", str(output_dir / "%(upload_date>%Y-%m-%d)s_%(title)s.%(ext)s"),
        "--windows-filenames",       # strip chars invalid on Windows
        "--no-overwrites",           # skip files that already exist
        "--ignore-errors",           # skip unavailable/private videos, keep going
        "--newline",                 # one progress line per update (cleaner output)
        "--progress",
        PLAYLIST_URL,
    ]


def run_download(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(output_dir)

    print(f"Output folder : {output_dir}")
    print(f"yt-dlp        : {YTDLP_PATH}")
    print(f"Playlist      : {PLAYLIST_URL}")
    print("-" * 60)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    for line in process.stdout:
        print(line, end="", flush=True)

    process.wait()
    return process.returncode


def main() -> None:
    if not YTDLP_PATH.exists():
        print(f"ERROR: yt-dlp.exe not found at {YTDLP_PATH}")
        print("Copy yt-dlp.exe into the tools/ folder and re-run.")
        sys.exit(1)

    returncode = run_download(OUTPUT_DIR)

    print("-" * 60)
    if returncode == 0:
        print("Done. All videos downloaded.")
    else:
        print(f"yt-dlp exited with code {returncode}. Check output above for failed videos.")
        sys.exit(returncode)


if __name__ == "__main__":
    main()
