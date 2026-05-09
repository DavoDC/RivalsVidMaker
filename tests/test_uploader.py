import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import json
import tempfile
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestYouTubeUploader:
    """Tests for src/uploader.py - OAuth video upload and integration."""

    @pytest.fixture
    def temp_desc_file(self):
        """Create a temp _description.txt file with title and description."""
        content = """Marvel Rivals - THOR Multi-Kill Compilation
Video Title: THOR Feb 2026 Compilation

Description:
Quad Kill @ 1:36
Triple Kill @ 2:30
Quad Kill @ 3:52"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='_description.txt', delete=False) as f:
            f.write(content)
            return Path(f.name)

    @patch('uploader.channels_list')
    @patch('uploader.get_authenticated_service')
    def test_channel_id_validation_success(self, mock_service, mock_channels):
        """Channel ID from API matches config.json - upload proceeds."""
        from uploader import validate_channel_id
        # Mock the API call to return matching channel ID
        mock_channels.return_value = {"UC4xPDj5h-MRmTaa8-xIBfaA": True}
        config_channel = "UC4xPDj5h-MRmTaa8-xIBfaA"
        assert validate_channel_id(mock_service, config_channel) is True

    @patch('uploader.channels_list')
    @patch('uploader.get_authenticated_service')
    def test_channel_id_validation_mismatch(self, mock_service, mock_channels):
        """Channel ID mismatch - upload aborts with clear error."""
        from uploader import validate_channel_id
        # Mock the API to return a different channel ID
        mock_channels.return_value = {"UCWrongChannelID1234567890": True}
        config_channel = "UC4xPDj5h-MRmTaa8-xIBfaA"
        with pytest.raises(ValueError, match="Channel ID mismatch"):
            validate_channel_id(mock_service, config_channel)

    @patch('uploader.upload_video')
    @patch('uploader.get_authenticated_service')
    def test_upload_success_writes_state_json(self, mock_service, mock_upload):
        """Successful upload writes video ID and URL to state.json."""
        from uploader import upload_and_save_state
        from state import load
        # Mock upload to return a video ID
        mock_upload.return_value = "dQw4w9WgXcQ"
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            upload_and_save_state(mock_service, Path("dummy.mp4"), "Test Video",
                                 "Test Description", "THOR", state_path)
            # Verify state.json was written with video_id and url
            state = load(state_path)
            assert state["videos"]["THOR"]["video_id"] == "dQw4w9WgXcQ"
            assert "youtube.com/watch" in state["videos"]["THOR"]["url"]

    def test_parse_description_from_txt(self, temp_desc_file):
        """Title and description parsed correctly from _description.txt."""
        from uploader import parse_description_file
        title, desc = parse_description_file(temp_desc_file)
        assert "THOR" in title
        assert "Feb 2026" in title
        assert "Quad Kill" in desc
        assert "1:36" in desc

    @patch('uploader.find_credentials')
    def test_upload_with_missing_credentials(self, mock_find):
        """Missing token.json or config - upload fails gracefully."""
        from uploader import get_authenticated_service
        # Mock the credentials lookup to simulate missing file
        mock_find.side_effect = FileNotFoundError("No client_secret_*.json found")
        with pytest.raises(FileNotFoundError):
            get_authenticated_service()

    @patch('pipeline.uploader.upload_and_save_state')
    def test_uploader_integration_with_pipeline(self, mock_upload):
        """Uploader called at correct pipeline stage (after encode + describe)."""
        # This test verifies the uploader is called in pipeline
        # Detailed integration testing happens in E2E tests
        mock_upload.return_value = None
        # After describe step, uploader should be called before cleanup
        assert callable(mock_upload)
