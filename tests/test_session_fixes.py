"""
Tests for this session's P0 bug fixes and Preprocess feature.

- Retry YouTube upload detection with output_folders state structure
- Uncompile full folder deletion
- token.json auto-fix missing "type" field
- Preprocess top-level menu option
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestRetryUploadStateStructure:
    """Test Retry YouTube upload with correct state.json structure (output_folders)."""

    def test_has_failed_upload_with_output_folders_structure(self, tmp_path):
        """Folder with .mp4 + _description.txt but not in state['output_folders'] = retryable."""
        from menu import _has_failed_upload

        folder = tmp_path / "THOR_MAR_2026"
        folder.mkdir()
        (folder / "THOR_MAR_2026.mp4").write_text("fake video")
        (folder / "THOR_MAR_2026_description.txt").write_text("Title\nDescription")

        # Correct state structure: output_folders, not videos
        state = {"output_folders": {}}

        assert _has_failed_upload(folder, state) is True

    def test_has_failed_upload_when_already_confirmed_in_output_folders(self, tmp_path):
        """Folder in state['output_folders'] with youtube_confirmed=True = not retryable."""
        from menu import _has_failed_upload

        folder = tmp_path / "THOR_MAR_2026"
        folder.mkdir()
        (folder / "THOR_MAR_2026.mp4").write_text("fake video")
        (folder / "THOR_MAR_2026_description.txt").write_text("Title\nDescription")

        state = {
            "output_folders": {
                "THOR_MAR_2026": {"youtube_confirmed": True}
            }
        }

        assert _has_failed_upload(folder, state) is False


class TestUncompileFullDelete:
    """Test that uncompile fully deletes output folder even if some files fail."""

    def test_uncompile_removes_folder_even_if_some_files_fail(self, tmp_path):
        """uncompile should fully remove output folder even if some file deletions fail."""
        from cleanup import run_uncompile

        output_folder = tmp_path / "THOR_MAR_2026"
        output_folder.mkdir()
        clips_dir = output_folder / "clips"
        clips_dir.mkdir()

        # Create test files
        (output_folder / "THOR_MAR_2026.mp4").write_text("video")
        (output_folder / "THOR_MAR_2026_description.txt").write_text("Title\nDesc")
        (clips_dir / "THOR_2026-01-01_00-00-00_QUAD.mp4").write_text("clip")

        highlights = tmp_path / "Highlights" / "THOR"
        highlights.mkdir(parents=True)

        # Mock user confirmation
        with patch("builtins.input", return_value="y"):
            # Mock send2trash to fail on clips.json (simulate file-in-use)
            with patch("cleanup.send2trash") as mock_trash:
                def side_effect(path):
                    if "clips.json" in str(path):
                        raise OSError("File in use")
                    # Otherwise succeed
                mock_trash.side_effect = side_effect

                run_uncompile(output_folder, tmp_path / "Highlights")

        # Folder should be fully removed despite clips.json failure
        assert not output_folder.exists()

    def test_uncompile_removes_empty_clips_dir(self, tmp_path):
        """uncompile should remove the clips/ directory after moving clips."""
        from cleanup import run_uncompile

        output_folder = tmp_path / "THOR_MAR_2026"
        output_folder.mkdir()
        clips_dir = output_folder / "clips"
        clips_dir.mkdir()
        (clips_dir / "THOR_2026-01-01_00-00-00_QUAD.mp4").write_text("clip")

        highlights = tmp_path / "Highlights" / "THOR"
        highlights.mkdir(parents=True)

        with patch("builtins.input", return_value="y"):
            run_uncompile(output_folder, tmp_path / "Highlights")

        assert not clips_dir.exists()
        assert not output_folder.exists()


class TestTokenJsonAutoFix:
    """Test token.json auto-adds missing 'type' field during generation."""

    def test_generated_token_has_type_field(self):
        """When token.json is generated, it must include 'type': 'authorized_user'."""
        from uploader import get_authenticated_service
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"

            with patch("uploader.TOKEN_PATH", token_path):
                with patch("uploader.find_credentials", return_value=Path("dummy")):
                    with patch("google_auth_oauthlib.flow.InstalledAppFlow") as mock_flow_class:
                        mock_flow = MagicMock()
                        mock_creds = MagicMock()
                        # Simulate creds.to_json() missing 'type' field
                        mock_creds.to_json.return_value = '{"token": "abc123"}'
                        mock_creds.valid = True
                        mock_flow.run_local_server.return_value = mock_creds
                        mock_flow_class.from_client_secrets_file.return_value = mock_flow

                        with patch("googleapiclient.discovery.build"):
                            get_authenticated_service()

                        # Verify token.json was written with 'type' field
                        token_content = json.loads(token_path.read_text())
                        assert "type" in token_content
                        assert token_content["type"] == "authorized_user"


class TestPreprocessTopLevelMenu:
    """Test Preprocess appears as top-level menu option."""

    def test_preprocess_option_in_top_level_menu(self, tmp_path):
        """Preprocess should be available as top-level menu option."""
        from menu import pick_action

        char_folders = [tmp_path / "THOR"]
        char_folders[0].mkdir()

        with patch("menu.questionary.select") as mock_select:
            # User selects Preprocess directly from level 1
            mock_select.return_value.ask.return_value = "preprocess"
            result = pick_action(char_folders, [(10, 600.0)], [], {}, target_batch_seconds=900)

        assert result["type"] == "preprocess"

    def test_preprocess_runs_all_cacheable_work(self, tmp_path):
        """Preprocess should run KO detection on all clips across all characters."""
        from preprocess import preprocess_all
        from config import Config

        # Create minimal test structure
        char_folders = [tmp_path / "THOR", tmp_path / "IRONMAN"]
        for folder in char_folders:
            folder.mkdir()
            (folder / "clip1.mp4").write_text("clip")

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.clips_path = tmp_path
        mock_config.ffmpeg = "ffmpeg"
        mock_config.ffprobe = "ffprobe"
        mock_config.tesseract = "tesseract"
        mock_config.cache_dir = tmp_path / "cache"
        mock_config.force_rescan_cache = False
        mock_config.use_pass2_scanner = False

        with patch("preprocess.ko_detect.scan_clip") as mock_scan:
            mock_scan.return_value = {"tier": "QUAD"}

            results = preprocess_all(mock_config)

        # Should return results for both characters
        assert "THOR" in results
        assert "IRONMAN" in results
        assert results["THOR"] >= 1
        assert results["IRONMAN"] >= 1
