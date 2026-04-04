"""
dedup.py -- Perceptual-hash duplicate clip detection.

Fingerprints each clip by extracting N evenly-spaced frames via ffmpeg
and computing a pHash (DCT hash) for each frame. Two clips are flagged
as probable duplicates if their per-frame average Hamming distance is
below a threshold.

Called automatically before encode in pipeline.py. Does NOT remove any
clips -- prints a warning table and lets the user decide.
"""

import glob
import logging
import os
import shutil
import subprocess
from pathlib import Path

import imagehash
from PIL import Image

from clip_scanner import Clip

DEFAULT_N_FRAMES = 5
DEFAULT_THRESHOLD = 10  # avg Hamming distance per frame (bits); empirically determined


# ── Frame extraction ──────────────────────────────────────────────────────────

def _extract_frames(
    clip_path: str,
    ffmpeg: str,
    duration: float,
    n_frames: int,
    tmpdir: str,
) -> list[Image.Image]:
    """Extract n_frames evenly spaced frames from clip. Returns list of PIL Images.

    Uses fps=n_frames/duration so frames are spread uniformly across the clip.
    """
    fps = n_frames / max(duration, 0.1)  # guard against zero-duration clips
    pat = os.path.join(tmpdir, "f%05d.png")
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "quiet",
         "-i", clip_path,
         "-vf", f"fps={fps:.6f}",
         "-vframes", str(n_frames),
         "-q:v", "2",
         pat],
        check=True,
    )
    frame_files = sorted(glob.glob(os.path.join(tmpdir, "f*.png")))
    return [Image.open(f) for f in frame_files]


# ── Hashing ───────────────────────────────────────────────────────────────────

def fingerprint_clip(
    clip: Clip,
    ffmpeg: str,
    n_frames: int = DEFAULT_N_FRAMES,
    tmp_dir: Path | None = None,
) -> list[imagehash.ImageHash]:
    """Extract n_frames pHashes for the clip. Returns list of ImageHash objects.

    Uses Clip.duration (already probed) so no extra ffprobe call is needed.
    Frames are written to a per-clip subdir inside tmp_dir, then deleted.
    """
    base = Path(tmp_dir) if tmp_dir else Path("data/dedup_tmp")
    work_dir = base / clip.path.stem
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        images = _extract_frames(
            str(clip.path), ffmpeg=ffmpeg, duration=clip.duration,
            n_frames=n_frames, tmpdir=str(work_dir),
        )
        return [imagehash.phash(img) for img in images]
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def avg_distance(
    hashes_a: list[imagehash.ImageHash],
    hashes_b: list[imagehash.ImageHash],
) -> float:
    """Return average per-frame Hamming distance between two fingerprints.

    Returns 0.0 if either list is empty (defensive; shouldn't happen in practice).
    """
    if not hashes_a or not hashes_b:
        return 0.0
    total = sum(a - b for a, b in zip(hashes_a, hashes_b))
    return total / len(hashes_a)


# ── Duplicate detection ───────────────────────────────────────────────────────

def find_duplicates(
    clips: list[Clip],
    ffmpeg: str,
    threshold: int = DEFAULT_THRESHOLD,
    n_frames: int = DEFAULT_N_FRAMES,
    tmp_dir: Path | None = None,
) -> list[tuple[Clip, Clip, float]]:
    """Fingerprint all clips and return suspected duplicate pairs.

    A pair (A, B) is flagged when avg_distance(A, B) < threshold.
    The threshold is strict: distance == threshold is NOT flagged.

    Frame images are written under tmp_dir (default: data/dedup_tmp) and
    cleaned up per-clip. The tmp_dir itself is removed on completion.

    Returns list of (clip_a, clip_b, avg_distance) sorted by distance ascending.
    """
    if len(clips) < 2:
        return []

    base = Path(tmp_dir) if tmp_dir else Path("data/dedup_tmp")
    base.mkdir(parents=True, exist_ok=True)

    total = len(clips)
    fingerprints: dict[Path, list[imagehash.ImageHash]] = {}

    for i, clip in enumerate(clips, 1):
        print(f"Dedup [{i}/{total}]: fingerprinting {clip.name}...")
        try:
            fingerprints[clip.path] = fingerprint_clip(clip, ffmpeg, n_frames, tmp_dir=base)
        except Exception as e:
            logging.warning("Dedup: could not fingerprint %s: %s", clip.name, e)
            fingerprints[clip.path] = []

    # base dir (now empty - per-clip subdirs cleaned up by fingerprint_clip) can go
    shutil.rmtree(base, ignore_errors=True)

    pairs: list[tuple[Clip, Clip, float]] = []
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            a, b = clips[i], clips[j]
            fp_a = fingerprints.get(a.path, [])
            fp_b = fingerprints.get(b.path, [])
            if not fp_a or not fp_b:
                continue
            dist = avg_distance(fp_a, fp_b)
            if dist < threshold:
                pairs.append((a, b, dist))

    pairs.sort(key=lambda t: t[2])
    return pairs


# ── Output ────────────────────────────────────────────────────────────────────

def print_dup_table(pairs: list[tuple[Clip, Clip, float]]) -> None:
    """Print a warning table listing suspected duplicate pairs.

    Prints nothing if pairs is empty.
    """
    if not pairs:
        return

    print()
    print(f"*** WARNING: {len(pairs)} suspected duplicate pair(s) found ***")
    print()

    # Column widths
    name_w = max(
        len("Clip A"), len("Clip B"),
        *[len(a.name) for a, b, _ in pairs],
        *[len(b.name) for a, b, _ in pairs],
    )
    dist_w = max(len("Avg dist"), 8)

    def row(a: str, b: str, d: str) -> str:
        return f"  {a:<{name_w}}  {b:<{name_w}}  {d:>{dist_w}}"

    header = row("Clip A", "Clip B", "Avg dist")
    sep = "  " + "-" * (name_w) + "  " + "-" * (name_w) + "  " + "-" * dist_w
    print(header)
    print(sep)
    for clip_a, clip_b, dist in pairs:
        print(row(clip_a.name, clip_b.name, f"{dist:.1f}"))
    print()
    print("  Clips above are likely duplicates. Remove the copy before continuing.")
    print()
