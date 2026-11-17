"""
encoder.py - Concatenate a batch of clips into a single MP4 via FFmpeg stream copy.

Uses -c copy (no re-encode) since all Marvel Rivals clips are uniform:
H.264 1920x1080 120fps AAC audio. Stream copy completes 15-min videos in ~10 seconds,
vs 5-10 minutes for GPU re-encoding (50-100x faster depending on baseline).
DTS non-monotonic warnings from ffmpeg concat are cosmetic - ffmpeg auto-corrects them.
"""

import logging
import subprocess
import tempfile
import time
from pathlib import Path

from batcher import Batch
from progress import AnimatedTicker

# ffmpeg writes machine-readable progress (key=value lines) to stdout.
PROGRESS_FLAGS = ["-progress", "pipe:1", "-nostats"]


def _parse_out_time_seconds(line: str) -> float | None:
    """Return encoded seconds from a '-progress' line, or None if not a usable value.

    ffmpeg's out_time_ms key is actually microseconds, so divide by 1e6.
    Lines such as 'out_time_ms=N/A' (emitted at startup) return None.
    """
    if not line.startswith("out_time_ms="):
        return None
    try:
        return float(line.split("=", 1)[1]) / 1_000_000
    except ValueError:
        return None


def _run_with_progress(cmd: list, total: float, on_progress) -> tuple[int, str]:
    """Run ffmpeg, streaming stdout progress to on_progress(encoded, total).

    stderr goes to a temp file rather than a PIPE: an unread stderr PIPE can
    fill and deadlock ffmpeg while we are blocked reading stdout.
    Returns (returncode, stderr_text).
    """
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err_f:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=err_f,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in proc.stdout:
            encoded = _parse_out_time_seconds(line.strip())
            if encoded is not None:
                on_progress(encoded, total)
        proc.stdout.close()
        returncode = proc.wait()
        err_f.seek(0)
        return returncode, err_f.read()


def encode(
    batch: Batch,
    char_name: str,
    output_dir: Path,
    ffmpeg: Path,
    out_stem: str | None = None,
    force: bool = False,
    on_progress=None,
) -> Path:
    """
    Concatenate all clips in the batch into a single MP4 via stream copy.

    Returns the path to the output file.
    Uses a temporary concat list file that is cleaned up after encoding.

    If the output file already exists and force=False, encoding is skipped and
    the existing file path is returned.  Pass force=True to re-encode anyway.

    on_progress, if given, is called as on_progress(encoded_seconds, total_seconds)
    while ffmpeg runs, where total_seconds is the batch duration.
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

    logging.info("Muxing %s (%s) via stream copy...", out_stem, batch.duration_str)

    cmd = [
        str(ffmpeg), "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy",
        "-movflags", "+faststart",
        *PROGRESS_FLAGS,
        str(out_path),
    ]
    logging.debug("  FFmpeg cmd: %s", " ".join(cmd))

    t0 = time.perf_counter()
    try:
        with AnimatedTicker("Muxing"):
            if on_progress is None:
                result = subprocess.run(cmd, capture_output=True, text=True)
                returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
            else:
                returncode, stderr = _run_with_progress(cmd, batch.total_duration, on_progress)
                stdout = ""
        if stderr:
            logging.debug("  FFmpeg stderr:\n%s", stderr.strip())
        if returncode != 0:
            logging.error("FFmpeg failed (exit %d):\n%s", returncode, stderr.strip())
            raise subprocess.CalledProcessError(returncode, cmd, stdout, stderr)
    finally:
        Path(concat_list).unlink(missing_ok=True)

    elapsed = time.perf_counter() - t0
    elapsed_mins = int(elapsed) // 60
    elapsed_secs = int(elapsed) % 60
    elapsed_fmt = f"{elapsed_mins}m {elapsed_secs:02d}s" if elapsed_mins else f"{elapsed_secs}s"
    logging.info("Muxing done in %s", elapsed_fmt)
    return out_path
