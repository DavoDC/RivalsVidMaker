"""
Tests for encoder.py — FFmpeg batch encoding.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from batcher import Batch
from clip_scanner import Clip
from encoder import check_nvenc, encode


def make_batch(number: int = 1, durations: tuple[float, ...] = (30.0, 30.0)) -> Batch:
    clips = [
        Clip(path=Path(f"/videos/clip_{i}.mp4"), duration=d)
        for i, d in enumerate(durations)
    ]
    return Batch(number=number, clips=clips)


class TestCheckNvenc:

    def test_nvenc_available(self):
        with patch("encoder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="h264_nvenc encoder", stderr="")
            assert check_nvenc(Path("ffmpeg")) is True

    def test_nvenc_unavailable(self):
        with patch("encoder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="libx264 encoder", stderr="")
            assert check_nvenc(Path("ffmpeg")) is False

    def test_nvenc_in_stderr(self):
        # Some ffmpeg builds report encoders to stderr
        with patch("encoder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="h264_nvenc listed")
            assert check_nvenc(Path("ffmpeg")) is True


class TestEncode:

    def test_golden_path_uses_nvenc(self, tmp_path):
        batch = make_batch()
        with patch("encoder.check_nvenc", return_value=True), \
             patch("encoder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            out = encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        assert out == tmp_path / "THOR_batch1.mp4"
        cmd_args = mock_run.call_args[0][0]
        assert "h264_nvenc" in cmd_args

    def test_cpu_fallback_when_no_nvenc(self, tmp_path):
        batch = make_batch()
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        cmd_args = mock_run.call_args[0][0]
        assert "libx264" in cmd_args
        assert "h264_nvenc" not in cmd_args

    def test_output_path_uses_char_name_and_batch_number(self, tmp_path):
        batch = make_batch(number=3)
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=0)):
            out = encode(batch, "SQUIRREL_GIRL", tmp_path, Path("ffmpeg"))

        assert out.name == "SQUIRREL_GIRL_batch3.mp4"

    def test_output_dir_created_if_missing(self, tmp_path):
        out_dir = tmp_path / "new" / "nested" / "dir"
        batch = make_batch()
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=0)):
            encode(batch, "THOR", out_dir, Path("ffmpeg"))

        assert out_dir.exists()

    def test_skip_if_output_exists(self, tmp_path):
        """If the output file already exists, encode() skips FFmpeg and returns the path."""
        batch = make_batch()
        existing = tmp_path / "THOR_batch1.mp4"
        existing.write_bytes(b"original")
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run") as mock_run:
            out = encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        assert out == existing
        mock_run.assert_not_called()
        assert existing.read_bytes() == b"original"  # file is untouched

    def test_force_flag_re_encodes_existing_output(self, tmp_path):
        """force=True must encode even when the output file already exists."""
        batch = make_batch()
        existing = tmp_path / "THOR_batch1.mp4"
        existing.write_bytes(b"original")
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            encode(batch, "THOR", tmp_path, Path("ffmpeg"), force=True)

        # FFmpeg must have been called
        assert mock_run.call_count >= 1  # at least the encode call (check_nvenc uses mock too)

    def test_encodes_when_output_absent(self, tmp_path):
        """Normal path: no existing file → FFmpeg is invoked."""
        batch = make_batch()
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        # At least one subprocess.run call (the actual encode)
        encode_calls = [
            c for c in mock_run.call_args_list
            if "concat" in str(c)
        ]
        assert len(encode_calls) >= 1

    def test_concat_list_cleaned_up(self, tmp_path):
        """Temp concat list file should not persist after encoding."""
        import tempfile
        batch = make_batch()
        created_files: list[str] = []

        original_NamedTemporaryFile = tempfile.NamedTemporaryFile

        def tracking_ntf(**kwargs):
            f = original_NamedTemporaryFile(**kwargs)
            created_files.append(f.name)
            return f

        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=0)), \
             patch("encoder.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        for path in created_files:
            assert not Path(path).exists(), f"Concat list not cleaned up: {path}"

    def test_ffmpeg_failure_raises_and_logs(self, tmp_path):
        """A non-zero ffmpeg exit code should raise CalledProcessError after logging."""
        import subprocess as _subprocess
        batch = make_batch()
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some ffmpeg error")
            with pytest.raises(_subprocess.CalledProcessError):
                encode(batch, "THOR", tmp_path, Path("ffmpeg"))

    def test_concat_list_cleaned_up_on_failure(self, tmp_path):
        """Temp concat list file must be removed even when ffmpeg fails."""
        import tempfile, subprocess as _subprocess
        batch = make_batch()
        created_files: list[str] = []
        original_NamedTemporaryFile = tempfile.NamedTemporaryFile

        def tracking_ntf(**kwargs):
            f = original_NamedTemporaryFile(**kwargs)
            created_files.append(f.name)
            return f

        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="")), \
             patch("encoder.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            try:
                encode(batch, "THOR", tmp_path, Path("ffmpeg"))
            except _subprocess.CalledProcessError:
                pass

        for path in created_files:
            assert not Path(path).exists(), f"Concat list not cleaned up on failure: {path}"

    def test_out_stem_override(self, tmp_path):
        """Passing out_stem overrides the default char_name_batchN filename."""
        batch = make_batch()
        with patch("encoder.check_nvenc", return_value=False), \
             patch("encoder.subprocess.run", return_value=MagicMock(returncode=0)):
            out = encode(batch, "THOR", tmp_path, Path("ffmpeg"), out_stem="THOR_Feb_2026")
        assert out.name == "THOR_Feb_2026.mp4"
