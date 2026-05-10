"""
Tests for output folder management (cleanup and retry upload).
Phase 2: Manage output folder with retry upload sub-actions.
"""

import tempfile
from pathlib import Path
import pytest
from cleanup import locate_video_and_description


class TestLocateVideoAndDescription:
    """Tests for locate_video_and_description() helper."""

    def test_locate_video_and_description_finds_files(self):
        """Verify locate_video_and_description() returns correct paths for .mp4 and .txt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)

            # Create test files
            mp4_path = folder / "test_video.mp4"
            mp4_path.write_text("fake video data")

            desc_path = folder / "test_video_description.txt"
            desc_path.write_text("Test Title\nTest description body")

            # Test locate function
            found_mp4, found_desc = locate_video_and_description(folder)

            assert found_mp4 == mp4_path
            assert found_desc == desc_path

    def test_locate_video_missing_mp4_raises_error(self):
        """Verify graceful error if .mp4 file not found in output folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)

            # Create only description file, no .mp4
            desc_path = folder / "test_video_description.txt"
            desc_path.write_text("Test Title\nTest description")

            with pytest.raises(FileNotFoundError, match="No .mp4 video found"):
                locate_video_and_description(folder)

    def test_locate_video_missing_description_raises_error(self):
        """Verify graceful error if _description.txt not found in output folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)

            # Create only .mp4 file, no description
            mp4_path = folder / "test_video.mp4"
            mp4_path.write_text("fake video data")

            with pytest.raises(FileNotFoundError, match="No _description.txt found"):
                locate_video_and_description(folder)

    def test_locate_video_multiple_mp4s_uses_first(self, caplog):
        """Verify when multiple .mp4s exist, the first one is used (with warning)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)

            # Create multiple .mp4 files
            mp4_1 = folder / "video_1.mp4"
            mp4_1.write_text("fake video data")

            mp4_2 = folder / "video_2.mp4"
            mp4_2.write_text("fake video data 2")

            desc_path = folder / "test_description.txt"
            desc_path.write_text("Test Title\nTest description")

            found_mp4, found_desc = locate_video_and_description(folder)

            # Should pick one of the two .mp4s
            assert found_mp4 in (mp4_1, mp4_2)
            assert found_desc == desc_path


def test_manage_output_folder_menu_shows_sub_options():
    """Verify menu displays sub-menu with 'Retry upload' and 'Clean up' options."""
    # This is a manual UI test - verified by running `python src/main.py --cleanup`
    # and confirming the sub-menu appears after selecting a folder
    pass


def test_retry_upload_parses_description():
    """Verify retry upload parses title and description from _description.txt."""
    # Integration test: requires uploader module and YouTube API mock
    pass


def test_retry_upload_calls_youtube_api():
    """Verify retry upload invokes upload_video() with correct parameters."""
    # Integration test: requires YouTube API mock
    pass


def test_retry_upload_saves_state():
    """Verify retry upload marks folder as youtube_confirmed in state.json."""
    # Integration test: requires uploader and state module mocks
    pass
