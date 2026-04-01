"""
config.py — Load configuration from config.json.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    clips_path: Path
    output_path: Path
    archive_path: Path
    ffmpeg: Path
    ffprobe: Path
    cache_dir: Path
    tesseract: Path
    min_batch_seconds: int    # skip batches shorter than this
    target_batch_seconds: int  # aim for this duration per batch
    protect_recent_clips: int  # skip this many most-recent clips from batching
    state_path: Path           # persistent state log (youtube_confirmed, etc.)
    force_rescan_cache: bool   # if True, pre-process ignores existing cache entries and rescans all clips
    use_pass2_scanner: bool    # if True, scan_clip falls back to pass 2 when pass 1 finds nothing (rescan/data mode only)


def load(path: Path = Path("config/config.json")) -> Config:
    """Load configuration from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"config.json not found at: {path.resolve()}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    required = ("clips_path", "output_path", "ffmpeg_path")
    missing = [k for k in required if k not in raw]
    if missing:
        raise KeyError(
            f"config.json is missing required field(s): {', '.join(missing)}\n"
            f"  See config/config.example.json for the expected format."
        )

    clips_path = Path(raw["clips_path"])
    ffmpeg_dir = Path(raw["ffmpeg_path"])
    return Config(
        clips_path=clips_path,
        output_path=Path(raw["output_path"]),
        archive_path=Path(raw.get("archive_path", str(clips_path.parent / "ClipArchive"))),
        ffmpeg=ffmpeg_dir / "ffmpeg.exe",
        ffprobe=ffmpeg_dir / "ffprobe.exe",
        cache_dir=Path(raw.get("cache_dir", "data/cache")),
        tesseract=Path(
            raw.get("tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        ),
        min_batch_seconds=int(raw.get("min_batch_seconds", 600)),
        target_batch_seconds=int(raw.get("target_batch_seconds", 900)),
        protect_recent_clips=int(raw.get("protect_recent_clips", 5)),
        state_path=Path(raw.get("state_path", "data/state.json")),
        force_rescan_cache=bool(raw.get("force_rescan_cache", False)),
        use_pass2_scanner=bool(raw.get("use_pass2_scanner", False)),
    )
