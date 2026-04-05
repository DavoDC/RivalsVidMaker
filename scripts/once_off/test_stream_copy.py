"""
test_stream_copy.py - Feasibility test for stream-copy concat (item 1).

Takes the first N clips from the clips folder (sorted by name) and concatenates
them with -c copy (no re-encode). Output goes to data/test_stream_copy.mp4.

Usage:
    python scripts/once_off/test_stream_copy.py [--count N]

Default: 5 clips. Use --count to test more if it looks good.

Checks to do after running:
  1. Does the file play at all?
  2. A/V in sync throughout?
  3. Any stutter or jump at clip boundaries?
  4. Compare file size vs a re-encoded version (stream copy should be much smaller
     if clips are already high-quality, or similar size if source bitrate is low).
"""

import argparse
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Run from repo root so config path resolves correctly
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import config as cfg_module

LOG_PATH = REPO_ROOT / "data" / "test_stream_copy.log"
OUTPUT_PATH = REPO_ROOT / "data" / "test_stream_copy.mp4"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

CLIP_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}


def find_clips(clips_path: Path, count: int) -> list[Path]:
    clips = sorted(
        [p for p in clips_path.rglob("*") if p.suffix.lower() in CLIP_EXTENSIONS],
        key=lambda p: p.name,
    )
    if not clips:
        logging.error("No clips found in %s", clips_path)
        sys.exit(1)
    return clips[:count]


def probe_audio_codec(ffprobe: Path, clip: Path) -> str:
    """Return the audio codec name for the clip (e.g. 'aac', 'pcm_s16le')."""
    result = subprocess.run(
        [
            str(ffprobe), "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(clip),
        ],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description="Test stream-copy concat")
    parser.add_argument("--count", type=int, default=5, help="Number of clips to concat (default: 5)")
    args = parser.parse_args()

    logging.info("=== Stream-copy feasibility test ===")
    logging.info("Clip count: %d", args.count)

    config = cfg_module.load(REPO_ROOT / "config" / "config.json")
    ffmpeg = config.ffmpeg
    ffprobe = config.ffprobe
    clips_path = config.clips_path

    logging.info("Clips path: %s", clips_path)
    logging.info("FFmpeg: %s", ffmpeg)

    clips = find_clips(clips_path, args.count)
    logging.info("Using %d clips:", len(clips))
    for i, c in enumerate(clips, 1):
        logging.info("  %d. %s", i, c.name)

    # Check audio codecs - stream copy requires all match
    logging.info("Checking audio codecs...")
    codecs = {}
    for c in clips:
        codec = probe_audio_codec(ffprobe, c)
        codecs[c.name] = codec
        logging.info("  %s -> %s", c.name, codec)

    unique_codecs = set(codecs.values())
    if len(unique_codecs) > 1:
        logging.warning("Mixed audio codecs: %s - stream copy may fail or produce broken audio!", unique_codecs)
    else:
        logging.info("Audio codec uniform: %s - stream copy should work", next(iter(unique_codecs)))

    # Write concat list
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_concat.txt", delete=False, encoding="utf-8", dir=REPO_ROOT / "data"
    ) as f:
        for clip in clips:
            fp = str(clip).replace("\\", "/")
            f.write(f"file '{fp}'\n")
        concat_list = Path(f.name)

    logging.info("Concat list: %s", concat_list)
    logging.info("Output: %s", OUTPUT_PATH)

    cmd = [
        str(ffmpeg), "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy",          # stream copy - no re-encode
        "-movflags", "+faststart",
        str(OUTPUT_PATH),
    ]
    logging.info("FFmpeg cmd: %s", " ".join(cmd))

    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    concat_list.unlink(missing_ok=True)

    if result.stderr:
        logging.debug("FFmpeg stderr:\n%s", result.stderr.strip())

    if result.returncode != 0:
        logging.error("FFmpeg FAILED (exit %d):\n%s", result.returncode, result.stderr.strip())
        sys.exit(1)

    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    logging.info("Done in %.1fs", elapsed)
    logging.info("Output: %s (%.1f MB)", OUTPUT_PATH, size_mb)
    logging.info("")
    logging.info("Please check:")
    logging.info("  1. Does the file play?")
    logging.info("  2. A/V in sync throughout?")
    logging.info("  3. Any stutter/jump at clip boundaries?")


if __name__ == "__main__":
    main()
