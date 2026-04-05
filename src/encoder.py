"""
encoder.py - Encode a batch of clips into a single MP4 via FFmpeg concat.

Replaces C++: Encoder.cpp
Uses NVENC (GPU) if available, falls back to libx264 (CPU).
"""

import logging
import subprocess
import tempfile
import time
from pathlib import Path

from batcher import Batch
from progress import AnimatedTicker


def check_nvenc(ffmpeg: Path) -> bool:
    """Return True if h264_nvenc is available on this machine."""
    result = subprocess.run(
        [str(ffmpeg), "-encoders"],
        capture_output=True, text=True,
    )
    return "h264_nvenc" in (result.stdout + result.stderr)


def encode(
    batch: Batch,
    char_name: str,
    output_dir: Path,
    ffmpeg: Path,
    out_stem: str | None = None,
    force: bool = False,
) -> Path:
    """
    Concatenate all clips in the batch into a single MP4.

    Returns the path to the encoded file.
    Uses a temporary concat list file that is cleaned up after encoding.

    If the output file already exists and force=False, encoding is skipped and
    the existing file path is returned.  Pass force=True to re-encode anyway.
    """
    if out_stem is None:
        out_stem = f"{char_name}_batch{batch.number}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{out_stem}.mp4"

    if out_path.exists() and not force:
        logging.warning("Output already exists: %s. Use --force to re-encode.", out_path)
        print(f"[WARNING] Output already exists: {out_path}. Use --force to re-encode.")
        return out_path

    # Remove any partial file left by a previously interrupted encode so it
    # cannot be mistaken for a completed output on the next run.
    out_path.unlink(missing_ok=True)

    # Write the ffmpeg concat list to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_concat.txt", delete=False, encoding="utf-8"
    ) as f:
        for clip in batch.clips:
            # ffmpeg concat format requires forward slashes
            fp = str(clip.path).replace("\\", "/")
            f.write(f"file '{fp}'\n")
        concat_list = f.name

    use_nvenc = check_nvenc(ffmpeg)
    codec_args = (
        ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
        if use_nvenc
        else ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    )

    encoder_label = "NVENC (GPU)" if use_nvenc else "libx264 (CPU)"
    logging.debug("Encoder: %s", encoder_label)
    logging.info("Encoding %s (%s)...", out_stem, batch.duration_str)

    cmd = [
        str(ffmpeg), "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        *codec_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    logging.debug("  FFmpeg cmd: %s", " ".join(cmd))

    t0 = time.perf_counter()
    try:
        with AnimatedTicker("Encoding"):
            result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stderr:
            logging.debug("  FFmpeg stderr:\n%s", result.stderr.strip())
        if result.returncode != 0:
            logging.error("FFmpeg failed (exit %d):\n%s", result.returncode, result.stderr.strip())
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    finally:
        Path(concat_list).unlink(missing_ok=True)

    elapsed = time.perf_counter() - t0
    elapsed_mins = int(elapsed) // 60
    elapsed_secs = int(elapsed) % 60
    elapsed_fmt = f"{elapsed_mins}m {elapsed_secs:02d}s" if elapsed_mins else f"{elapsed_secs}s"
    logging.info("Encoding done in %s", elapsed_fmt)
    return out_path
