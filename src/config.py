"""
config.py — Load configuration from config.txt (key=value format).
"""

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
    min_batch_seconds: int   # skip batches shorter than this
    target_batch_seconds: int  # aim for this duration per batch


def load(path: Path = Path("config.txt")) -> "Config":
    """Parse a key=value config file, ignoring blank lines and # comments."""
    if not path.exists():
        raise FileNotFoundError(f"config.txt not found at: {path.resolve()}")

    raw: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        raw[key.strip()] = val.strip()

    ffmpeg_dir = Path(raw["FFMPEGPath"])
    return Config(
        clips_path=Path(raw["ClipsPath"]),
        output_path=Path(raw["OutputPath"]),
        ffmpeg=ffmpeg_dir / "ffmpeg.exe",
        ffprobe=ffmpeg_dir / "ffprobe.exe",
        cache_dir=Path(raw.get("CacheDir", "data/cache")),
        tesseract=Path(
            raw.get("TesseractPath", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        ),
        min_batch_seconds=int(raw.get("MinBatchSeconds", 600)),
        target_batch_seconds=int(raw.get("TargetBatchSeconds", 900)),
    )
