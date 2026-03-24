"""
Tests for config.py — configuration loading and validation.
"""

import json
from pathlib import Path

import pytest

from config import Config, load


def write_config(directory: Path, data: dict) -> Path:
    """Write a config JSON to a temp directory and return its path."""
    p = directory / "config.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


MINIMAL_CONFIG = {
    "clips_path": "C:/Videos/MarvelRivals/Highlights",
    "output_path": "C:/Videos/MarvelRivals/Output",
    "ffmpeg_path": "tools",
}

FULL_CONFIG = {
    **MINIMAL_CONFIG,
    "archive_path": "C:/Videos/MarvelRivals/ClipArchive",
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "cache_dir": "data/cache",
    "min_batch_seconds": 600,
    "target_batch_seconds": 900,
}


class TestLoad:

    def test_minimal_config_loads(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        assert isinstance(config, Config)

    def test_full_config_loads(self, tmp_path):
        cfg_path = write_config(tmp_path, FULL_CONFIG)
        config = load(cfg_path)
        assert config.min_batch_seconds == 600
        assert config.target_batch_seconds == 900

    def test_clips_path_is_path_object(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        assert isinstance(config.clips_path, Path)

    def test_ffmpeg_path_appends_exe(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        assert config.ffmpeg.name == "ffmpeg.exe"
        assert config.ffprobe.name == "ffprobe.exe"

    def test_archive_path_defaults_when_absent(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        # Default: clips_path.parent / "ClipArchive"
        assert config.archive_path.name == "ClipArchive"

    def test_cache_dir_defaults_when_absent(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        assert config.cache_dir == Path("data/cache")

    def test_target_batch_seconds_defaults_to_900(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        assert config.target_batch_seconds == 900

    def test_min_batch_seconds_defaults_to_600(self, tmp_path):
        cfg_path = write_config(tmp_path, MINIMAL_CONFIG)
        config = load(cfg_path)
        assert config.min_batch_seconds == 600

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="config.json not found"):
            load(tmp_path / "nonexistent.json")

    def test_missing_clips_path_raises_key_error(self, tmp_path):
        data = {k: v for k, v in MINIMAL_CONFIG.items() if k != "clips_path"}
        cfg_path = write_config(tmp_path, data)
        with pytest.raises(KeyError, match="clips_path"):
            load(cfg_path)

    def test_missing_output_path_raises_key_error(self, tmp_path):
        data = {k: v for k, v in MINIMAL_CONFIG.items() if k != "output_path"}
        cfg_path = write_config(tmp_path, data)
        with pytest.raises(KeyError, match="output_path"):
            load(cfg_path)

    def test_missing_ffmpeg_path_raises_key_error(self, tmp_path):
        data = {k: v for k, v in MINIMAL_CONFIG.items() if k != "ffmpeg_path"}
        cfg_path = write_config(tmp_path, data)
        with pytest.raises(KeyError, match="ffmpeg_path"):
            load(cfg_path)

    def test_error_message_mentions_config_example(self, tmp_path):
        data = {k: v for k, v in MINIMAL_CONFIG.items() if k != "clips_path"}
        cfg_path = write_config(tmp_path, data)
        with pytest.raises(KeyError, match="config.example.json"):
            load(cfg_path)

    def test_custom_target_batch_seconds(self, tmp_path):
        data = {**FULL_CONFIG, "target_batch_seconds": 1200}
        cfg_path = write_config(tmp_path, data)
        config = load(cfg_path)
        assert config.target_batch_seconds == 1200
