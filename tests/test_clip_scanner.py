"""
Tests for clip_scanner.py — folder scanning and duration probing.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clip_scanner import Clip, probe_duration, scan_folder, summarize_folder


class TestProbeDuration:

    def test_golden_path(self):
        with patch("clip_scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="42.5\n")
            dur = probe_duration(Path("clip.mp4"), Path("ffprobe"))
        assert dur == pytest.approx(42.5)

    def test_integer_duration(self):
        with patch("clip_scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="30\n")
            dur = probe_duration(Path("clip.mp4"), Path("ffprobe"))
        assert dur == pytest.approx(30.0)

    def test_invalid_output_returns_zero(self):
        with patch("clip_scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="N/A\n")
            dur = probe_duration(Path("clip.mp4"), Path("ffprobe"))
        assert dur == 0.0

    def test_empty_output_returns_zero(self):
        with patch("clip_scanner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            dur = probe_duration(Path("clip.mp4"), Path("ffprobe"))
        assert dur == 0.0


class TestScanFolder:

    def test_golden_path(self, tmp_path):
        (tmp_path / "clip_a.mp4").touch()
        (tmp_path / "clip_b.mp4").touch()
        (tmp_path / "notes.txt").touch()   # non-video, should be ignored

        with patch("clip_scanner.probe_duration", return_value=30.0):
            clips = scan_folder(tmp_path, Path("ffprobe"))

        assert len(clips) == 2
        assert all(isinstance(c, Clip) for c in clips)
        assert all(c.duration == pytest.approx(30.0) for c in clips)

    def test_empty_folder_returns_empty_list(self, tmp_path):
        clips = scan_folder(tmp_path, Path("ffprobe"))
        assert clips == []

    def test_non_video_files_ignored(self, tmp_path):
        for name in ["video.mp4", "image.jpg", "doc.txt", "archive.zip"]:
            (tmp_path / name).touch()

        with patch("clip_scanner.probe_duration", return_value=10.0):
            clips = scan_folder(tmp_path, Path("ffprobe"))

        assert len(clips) == 1
        assert clips[0].name == "video.mp4"

    def test_clips_sorted_alphabetically(self, tmp_path):
        for name in ["c.mp4", "a.mp4", "b.mp4"]:
            (tmp_path / name).touch()

        with patch("clip_scanner.probe_duration", return_value=10.0):
            clips = scan_folder(tmp_path, Path("ffprobe"))

        assert [c.name for c in clips] == ["a.mp4", "b.mp4", "c.mp4"]

    def test_zero_duration_clips_skipped(self, tmp_path):
        (tmp_path / "good.mp4").touch()
        (tmp_path / "bad.mp4").touch()

        def fake_probe(path, _):
            return 30.0 if path.name == "good.mp4" else 0.0

        with patch("clip_scanner.probe_duration", side_effect=fake_probe):
            clips = scan_folder(tmp_path, Path("ffprobe"))

        assert len(clips) == 1
        assert clips[0].name == "good.mp4"

    def test_supports_multiple_extensions(self, tmp_path):
        for name in ["a.mp4", "b.mov", "c.mkv", "d.avi", "e.webm"]:
            (tmp_path / name).touch()

        with patch("clip_scanner.probe_duration", return_value=10.0):
            clips = scan_folder(tmp_path, Path("ffprobe"))

        assert len(clips) == 5


class TestSummarizeFolder:

    def test_empty_folder_returns_zeros(self, tmp_path):
        count, total = summarize_folder(tmp_path, Path("ffprobe"))
        assert count == 0
        assert total == 0.0

    def test_single_clip(self, tmp_path):
        (tmp_path / "clip.mp4").touch()
        with patch("clip_scanner.probe_duration", return_value=45.0):
            count, total = summarize_folder(tmp_path, Path("ffprobe"))
        assert count == 1
        assert total == pytest.approx(45.0)

    def test_multiple_clips_summed(self, tmp_path):
        for name in ["a.mp4", "b.mp4", "c.mp4"]:
            (tmp_path / name).touch()
        with patch("clip_scanner.probe_duration", return_value=30.0):
            count, total = summarize_folder(tmp_path, Path("ffprobe"))
        assert count == 3
        assert total == pytest.approx(90.0)

    def test_zero_duration_clips_excluded_from_count_and_total(self, tmp_path):
        (tmp_path / "good.mp4").touch()
        (tmp_path / "bad.mp4").touch()

        def fake_probe(path, _):
            return 60.0 if path.name == "good.mp4" else 0.0

        with patch("clip_scanner.probe_duration", side_effect=fake_probe):
            count, total = summarize_folder(tmp_path, Path("ffprobe"))

        assert count == 1
        assert total == pytest.approx(60.0)

    def test_non_video_files_ignored(self, tmp_path):
        (tmp_path / "clip.mp4").touch()
        (tmp_path / "notes.txt").touch()
        with patch("clip_scanner.probe_duration", return_value=10.0):
            count, total = summarize_folder(tmp_path, Path("ffprobe"))
        assert count == 1
