"""
Tests for encoder.py - FFmpeg stream-copy batch muxing.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from batcher import Batch
from clip_scanner import Clip
from encoder import encode


def make_batch(number: int = 1, durations: tuple[float, ...] = (30.0, 30.0)) -> Batch:
    clips = [
        Clip(path=Path(f"/videos/clip_{i}.mp4"), duration=d)
        for i, d in enumerate(durations)
    ]
    return Batch(number=number, clips=clips)


class TestEncode:

    def test_stream_copy_in_ffmpeg_command(self, tmp_path):
        batch = make_batch()
        with patch("encoder.subprocess.run") as mock_run, \
             patch("encoder.AnimatedTicker"):
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        cmd_args = mock_run.call_args[0][0]
        assert "-c" in cmd_args
        assert "copy" in cmd_args

    def test_output_path_uses_char_name_and_batch_number(self, tmp_path):
        batch = make_batch(number=3)
        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")), \
             patch("encoder.AnimatedTicker"):
            out = encode(batch, "SQUIRREL_GIRL", tmp_path, Path("ffmpeg"))

        assert out.name == "SQUIRREL_GIRL_batch3.mp4"

    def test_output_dir_created_if_missing(self, tmp_path):
        out_dir = tmp_path / "new" / "nested" / "dir"
        batch = make_batch()
        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")), \
             patch("encoder.AnimatedTicker"):
            encode(batch, "THOR", out_dir, Path("ffmpeg"))

        assert out_dir.exists()

    def test_skip_if_output_exists(self, tmp_path):
        """If the output file already exists, encode() skips FFmpeg and returns the path."""
        batch = make_batch()
        existing = tmp_path / "THOR_batch1.mp4"
        existing.write_bytes(b"original")
        with patch("encoder.subprocess.run") as mock_run, \
             patch("encoder.AnimatedTicker"):
            out = encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        assert out == existing
        mock_run.assert_not_called()
        assert existing.read_bytes() == b"original"

    def test_force_flag_re_encodes_existing_output(self, tmp_path):
        """force=True must encode even when the output file already exists."""
        batch = make_batch()
        existing = tmp_path / "THOR_batch1.mp4"
        existing.write_bytes(b"original")
        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")) as mock_run, \
             patch("encoder.AnimatedTicker"):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"), force=True)

        assert mock_run.call_count >= 1

    def test_encodes_when_output_absent(self, tmp_path):
        """Normal path: no existing file -> FFmpeg is invoked."""
        batch = make_batch()
        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")) as mock_run, \
             patch("encoder.AnimatedTicker"):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        encode_calls = [c for c in mock_run.call_args_list if "concat" in str(c)]
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

        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")), \
             patch("encoder.AnimatedTicker"), \
             patch("encoder.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        for path in created_files:
            assert not Path(path).exists(), f"Concat list not cleaned up: {path}"

    def test_ffmpeg_failure_raises(self, tmp_path):
        """A non-zero ffmpeg exit code should raise CalledProcessError."""
        import subprocess as _subprocess
        batch = make_batch()
        with patch("encoder.subprocess.run") as mock_run, \
             patch("encoder.AnimatedTicker"):
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")
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

        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="")), \
             patch("encoder.AnimatedTicker"), \
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
        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")), \
             patch("encoder.AnimatedTicker"):
            out = encode(batch, "THOR", tmp_path, Path("ffmpeg"), out_stem="THOR_Feb_2026")
        assert out.name == "THOR_Feb_2026.mp4"


def make_fake_popen(stdout_text: str, returncode: int = 0):
    """Fake subprocess.Popen whose stdout emits the given text line by line."""
    import io
    proc = MagicMock()
    proc.stdout = io.StringIO(stdout_text)
    proc.wait.return_value = returncode
    proc.returncode = returncode
    return proc


PROGRESS_STDOUT = (
    "frame=1\n"
    "out_time_ms=N/A\n"
    "progress=continue\n"
    "out_time_ms=10000000\n"
    "progress=continue\n"
    "out_time_ms=30000000\n"
    "progress=continue\n"
    "out_time_ms=60000000\n"
    "progress=end\n"
)


class TestEncodeProgress:

    def test_callback_receives_increasing_seconds_and_total(self, tmp_path):
        """ffmpeg out_time_ms is microseconds; callback gets seconds and batch total."""
        batch = make_batch(durations=(30.0, 30.0))
        calls: list[tuple[float, float]] = []
        with patch("encoder.subprocess.Popen", return_value=make_fake_popen(PROGRESS_STDOUT)), \
             patch("encoder.AnimatedTicker"):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"),
                   on_progress=lambda done, total: calls.append((done, total)))

        done_values = [d for d, _ in calls]
        assert done_values == [10.0, 30.0, 60.0]
        assert all(total == 60.0 for _, total in calls)

    def test_callback_path_passes_progress_flags_and_no_stderr_pipe(self, tmp_path):
        """Progress run streams stdout; stderr must not be an unread PIPE (deadlock)."""
        import subprocess as _subprocess
        batch = make_batch()
        with patch("encoder.subprocess.Popen", return_value=make_fake_popen(PROGRESS_STDOUT)) as mock_popen, \
             patch("encoder.AnimatedTicker"):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"), on_progress=lambda d, t: None)

        cmd_args = mock_popen.call_args[0][0]
        assert cmd_args[cmd_args.index("-progress") + 1] == "pipe:1"
        assert "-nostats" in cmd_args
        assert "-c" in cmd_args and "copy" in cmd_args
        assert mock_popen.call_args.kwargs["stdout"] == _subprocess.PIPE
        assert mock_popen.call_args.kwargs.get("stderr") != _subprocess.PIPE

    def test_no_callback_keeps_run_path_with_progress_flags(self, tmp_path):
        """Without a callback, subprocess.run is still used; only the progress flags are added."""
        batch = make_batch()
        with patch("encoder.subprocess.run", return_value=MagicMock(returncode=0, stderr="")) as mock_run, \
             patch("encoder.subprocess.Popen") as mock_popen, \
             patch("encoder.AnimatedTicker"):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"))

        mock_popen.assert_not_called()
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[cmd_args.index("-progress") + 1] == "pipe:1"
        assert "-nostats" in cmd_args

    def test_callback_path_ffmpeg_failure_raises(self, tmp_path):
        """Non-zero exit with a callback still raises CalledProcessError."""
        import subprocess as _subprocess
        batch = make_batch()
        with patch("encoder.subprocess.Popen", return_value=make_fake_popen("", returncode=1)), \
             patch("encoder.AnimatedTicker"):
            with pytest.raises(_subprocess.CalledProcessError):
                encode(batch, "THOR", tmp_path, Path("ffmpeg"), on_progress=lambda d, t: None)

    def test_callback_path_concat_list_cleaned_up(self, tmp_path):
        """Concat list is removed on the progress path too."""
        import tempfile
        batch = make_batch()
        created_files: list[str] = []
        original_NamedTemporaryFile = tempfile.NamedTemporaryFile

        def tracking_ntf(**kwargs):
            f = original_NamedTemporaryFile(**kwargs)
            created_files.append(f.name)
            return f

        with patch("encoder.subprocess.Popen", return_value=make_fake_popen(PROGRESS_STDOUT)), \
             patch("encoder.AnimatedTicker"), \
             patch("encoder.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            encode(batch, "THOR", tmp_path, Path("ffmpeg"), on_progress=lambda d, t: None)

        assert created_files
        for path in created_files:
            assert not Path(path).exists(), f"Concat list not cleaned up: {path}"
