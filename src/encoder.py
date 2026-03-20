"""
encoder.py — Encode a batch of clips into a single MP4 via FFmpeg concat.

Replaces C++: Encoder.cpp
Uses NVENC (GPU) if available, falls back to libx264 (CPU).
"""

import logging
import subprocess
import tempfile
from pathlib import Path

from batcher import Batch


def check_nvenc(ffmpeg: Path) -> bool:
    """Return True if h264_nvenc is available on this machine."""
    result = subprocess.run(
        [str(ffmpeg), "-encoders"],
        capture_output=True, text=True,
    )
    return "h264_nvenc" in (result.stdout + result.stderr)


def encode(batch: Batch, char_name: str, output_dir: Path, ffmpeg: Path) -> Path:
    """
    Concatenate all clips in the batch into a single MP4.

    Returns the path to the encoded file.
    Uses a temporary concat list file that is cleaned up after encoding.
    Passing -y to ffmpeg makes re-running idempotent (overwrites existing output).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{char_name}_batch{batch.number}.mp4"

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
    logging.info("  Encoder: %s", encoder_label)
    logging.info("  Encoding %s batch %d (%s)...", char_name, batch.number, batch.duration_str)

    cmd = [
        str(ffmpeg), "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        *codec_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    logging.debug("  FFmpeg cmd: %s", " ".join(cmd))

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            logging.debug("  FFmpeg stderr:\n%s", result.stderr.strip())
    finally:
        Path(concat_list).unlink(missing_ok=True)

    logging.info("  Encoded → %s", out_path)
    return out_path
