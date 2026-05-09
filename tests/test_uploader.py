import pytest
from unittest.mock import Mock, patch, MagicMock
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

Quad Kill @ 1:36
Triple Kill @ 2:30
Quad Kill @ 3:52"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='_description.txt', delete=False) as f:
            f.write(content)
            return Path(f.name)

    def test_channel_id_validation_success(self):
        """Channel ID from API matches config.json - upload proceeds."""
        from uploader import validate_channel_id
        # Create a mock YouTube service
        mock_youtube = MagicMock()
        mock_youtube.channels().list().execute.return_value = {
            "items": [{"id": "UC4xPDj5h-MRmTaa8-xIBfaA"}]
        }
        config_channel = "UC4xPDj5h-MRmTaa8-xIBfaA"
        assert validate_channel_id(mock_youtube, config_channel) is True

    def test_channel_id_validation_mismatch(self):
        """Channel ID mismatch - upload aborts with clear error."""
        from uploader import validate_channel_id
        # Mock YouTube service returning different channel ID
        mock_youtube = MagicMock()
        mock_youtube.channels().list().execute.return_value = {
            "items": [{"id": "UCWrongChannelID1234567890"}]
        }
        config_channel = "UC4xPDj5h-MRmTaa8-xIBfaA"
        with pytest.raises(ValueError, match="Channel ID mismatch"):
            validate_channel_id(mock_youtube, config_channel)

    def test_upload_success_writes_state_json(self):
        """Successful upload writes video ID and URL to state.json."""
        from uploader import upload_and_save_state
        from state import load
        # Mock YouTube service and upload
        mock_youtube = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            with tempfile.NamedTemporaryFile(suffix='.mp4', dir=tmpdir, delete=False) as f:
                video_path = Path(f.name)
                f.write(b"fake video data")

            # Mock upload_video to return a video ID
            with patch('uploader.upload_video', return_value="dQw4w9WgXcQ"):
                state_path = Path(tmpdir) / "state.json"
                upload_and_save_state(mock_youtube, video_path, "Test Video",
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
        assert "Quad Kill" in desc
        assert "1:36" in desc

    def test_upload_with_missing_credentials(self):
        """Missing token.json or config - upload fails gracefully."""
        from uploader import find_credentials
        # When credentials don't exist, should raise FileNotFoundError
        with patch('uploader._credentials_candidates', return_value=[]):
            with pytest.raises(FileNotFoundError):
                find_credentials()

    def test_uploader_callable(self):
        """Verify uploader module is importable and functions are callable."""
        import uploader
        assert callable(uploader.get_authenticated_service)
        assert callable(uploader.validate_channel_id)
        assert callable(uploader.upload_video)
        assert callable(uploader.upload_and_save_state)
        assert callable(uploader.parse_description_file)
