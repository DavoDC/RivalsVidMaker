"""
Tests for preprocess.py - KO cache-warming mode.

Uses tmp_path for filesystem; mocks ko_detect so no FFmpeg/Tesseract needed.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from config import Config
from preprocess import preprocess_all


def make_config(clips_path: Path, protect_recent_clips: int = 0) -> Config:
    return Config(
        clips_path=clips_path,
        output_path=clips_path.parent / "Output",
        archive_path=clips_path.parent / "ClipArchive",
        ffmpeg=Path("dependencies/ffmpeg/ffmpeg.exe"),
        ffprobe=Path("dependencies/ffmpeg/ffprobe.exe"),
        cache_dir=Path("data/cache"),
        tesseract=Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        min_batch_seconds=600,
        force_rescan_cache=False,
        use_pass2_scanner=False,
        target_batch_seconds=900,
        protect_recent_clips=protect_recent_clips,
        state_path=Path("data/state.json"),
    )


def _make_clip(directory: Path, name: str) -> Path:
    p = directory / name
    p.write_bytes(b"")
    return p


class TestPreprocessAll:

    def test_returns_empty_when_no_char_folders(self, tmp_path):
        config = make_config(tmp_path)
        result = preprocess_all(config)
        assert result == {}

    def test_raises_when_clips_path_missing(self, tmp_path):
        config = make_config(tmp_path / "missing")
        with pytest.raises(FileNotFoundError):
            preprocess_all(config)

    def test_scans_single_clip(self, tmp_path):
        char_dir = tmp_path / "THOR"
        char_dir.mkdir()
        _make_clip(char_dir, "THOR_2026-02-06_22-38-56.mp4")

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.cache_load.return_value = (False, None)
            mock_ko.scan_clip.return_value = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0}

            result = preprocess_all(make_config(tmp_path))

        assert result == {"THOR": 1}
        mock_ko.scan_clip.assert_called_once()

    def test_skips_cached_clips(self, tmp_path):
        char_dir = tmp_path / "THOR"
        char_dir.mkdir()
        # Clip has suffix so already_processed=True; a cache hit then skips the scan
        _make_clip(char_dir, "THOR_2026-02-06_22-38-56_QUAD.mp4")

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
            mock_ko.NULL_RESULT_SUFFIX = "NONE"
            mock_ko.cache_load.return_value = (True, {"tier": "QUAD"})

            result = preprocess_all(make_config(tmp_path))

        assert result == {"THOR": 1}
        mock_ko.scan_clip.assert_not_called()

    def test_multiple_characters(self, tmp_path):
        for char, clip in [
            ("THOR", "THOR_2026-02-06_22-38-56.mp4"),
            ("STORM", "STORM_2026-03-01_10-00-00.mp4"),
        ]:
            d = tmp_path / char
            d.mkdir()
            _make_clip(d, clip)

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
            mock_ko.NULL_RESULT_SUFFIX = "NONE"
            mock_ko.cache_load.return_value = (False, None)
            mock_ko.scan_clip.return_value = {"tier": "DOUBLE"}

            result = preprocess_all(make_config(tmp_path))

        assert set(result.keys()) == {"THOR", "STORM"}
        assert result["THOR"] == 1
        assert result["STORM"] == 1

    def test_ignores_non_video_files(self, tmp_path):
        char_dir = tmp_path / "THOR"
        char_dir.mkdir()
        (char_dir / "notes.txt").write_text("hello")
        (char_dir / "thumbnail.png").write_bytes(b"")

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.cache_load.return_value = (False, None)
            mock_ko.scan_clip.return_value = None

            result = preprocess_all(make_config(tmp_path))

        # No video files found - character still visited but nothing scanned
        assert result == {}
        mock_ko.scan_clip.assert_not_called()

    def test_configure_called_per_character(self, tmp_path):
        for char in ["THOR", "STORM"]:
            d = tmp_path / char
            d.mkdir()
            _make_clip(d, f"{char}_2026-02-06_22-38-56.mp4")

        config = make_config(tmp_path)

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
            mock_ko.NULL_RESULT_SUFFIX = "NONE"
            mock_ko.cache_load.return_value = (False, None)
            mock_ko.scan_clip.return_value = {"tier": "DOUBLE"}

            preprocess_all(config)

        assert mock_ko.configure.call_count == 2

    def test_multiple_clips_same_character(self, tmp_path):
        char_dir = tmp_path / "THOR"
        char_dir.mkdir()
        for name in [
            "THOR_2026-02-06_22-38-56.mp4",
            "THOR_2026-02-07_18-00-00.mp4",
            "THOR_2026-02-08_12-00-00.mp4",
        ]:
            _make_clip(char_dir, name)

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
            mock_ko.NULL_RESULT_SUFFIX = "NONE"
            mock_ko.cache_load.return_value = (False, None)
            mock_ko.scan_clip.return_value = {"tier": "DOUBLE"}

            result = preprocess_all(make_config(tmp_path))

        assert result["THOR"] == 3
        assert mock_ko.scan_clip.call_count == 3

    def test_protect_recent_clips_not_applied_to_char_subfolders(self, tmp_path):
        """protect_recent_clips must not restrict scanning in character subfolders.

        Regression: previously clips[:-N] was applied to character folders,
        so a folder with <= N clips would produce an empty list and scan nothing.
        """
        char_dir = tmp_path / "SQUIRREL_GIRL"
        char_dir.mkdir()
        for name in [
            "SQUIRREL_GIRL_2026-03-01_10-00-00.mp4",
            "SQUIRREL_GIRL_2026-03-02_11-00-00.mp4",
            "SQUIRREL_GIRL_2026-03-03_12-00-00.mp4",
        ]:
            _make_clip(char_dir, name)

        # protect_recent_clips=5 > clip count (3) - previously this zeroed the list
        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
            mock_ko.NULL_RESULT_SUFFIX = "NONE"
            mock_ko.cache_load.return_value = (False, None)
            mock_ko.scan_clip.return_value = {"tier": "DOUBLE"}

            result = preprocess_all(make_config(tmp_path, protect_recent_clips=5))

        assert result["SQUIRREL_GIRL"] == 3
        assert mock_ko.scan_clip.call_count == 3

    def test_mix_of_cached_and_uncached(self, tmp_path):
        char_dir = tmp_path / "THOR"
        char_dir.mkdir()
        # First clip has suffix (already processed) so a cache hit skips it.
        # Second clip has no suffix and no cache entry, so it gets scanned.
        _make_clip(char_dir, "THOR_2026-02-06_22-38-56_QUAD.mp4")
        _make_clip(char_dir, "THOR_2026-02-07_18-00-00.mp4")

        def fake_cache_load(path):
            return (True, {"tier": "QUAD"}) if "02-06" in path else (False, None)

        with patch("preprocess.ko_detect") as mock_ko:
            mock_ko.TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
            mock_ko.NULL_RESULT_SUFFIX = "NONE"
            mock_ko.cache_load.side_effect = fake_cache_load
            mock_ko.scan_clip.return_value = {"tier": "DOUBLE"}

            result = preprocess_all(make_config(tmp_path))

        assert result["THOR"] == 2
        assert mock_ko.scan_clip.call_count == 1  # only the uncached clip
