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
    ffmpeg: Path
    ffprobe: Path
    cache_dir: Path
    tesseract: Path
    min_batch_seconds: int    # skip batches shorter than this
    target_batch_seconds: int  # aim for this duration per batch


def load(path: Path = Path("config.json")) -> Config:
    """Load configuration from a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"config.json not found at: {path.resolve()}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    ffmpeg_dir = Path(raw["ffmpeg_path"])
    return Config(
        clips_path=Path(raw["clips_path"]),
        output_path=Path(raw["output_path"]),
        ffmpeg=ffmpeg_dir / "ffmpeg.exe",
        ffprobe=ffmpeg_dir / "ffprobe.exe",
        cache_dir=Path(raw.get("cache_dir", "data/cache")),
        tesseract=Path(
            raw.get("tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        ),
        min_batch_seconds=int(raw.get("min_batch_seconds", 600)),
        target_batch_seconds=int(raw.get("target_batch_seconds", 900)),
    )
