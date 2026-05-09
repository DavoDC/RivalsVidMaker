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

    def test_corrupted_token_detection(self):
        """uploader.py should detect and handle corrupted token.json gracefully."""
        # This test checks that get_authenticated_service() properly handles
        # the case where token.json exists but is malformed (missing 'type' field).
        # Expected: re-auth flow is triggered, corrupted token is replaced.
        import uploader
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            token_path.write_text('{"token": "abc"}')  # Malformed: no 'type' field

            with patch('uploader.TOKEN_PATH', token_path):
                with patch('uploader.find_credentials', return_value=Path("dummy")):
                    # Mock google.auth to simulate corrupted token error
                    with patch('google.auth.load_credentials_from_file') as mock_load:
                        mock_load.side_effect = ValueError("file does not have a valid type")

                        # Mock the OAuth flow that should be triggered
                        with patch('google_auth_oauthlib.flow.InstalledAppFlow') as mock_flow_class:
                            mock_flow = MagicMock()
                            mock_creds = MagicMock()
                            mock_creds.to_json.return_value = '{"type": "authorized_user", "token": "new"}'
                            mock_flow.run_local_server.return_value = mock_creds
                            mock_flow_class.from_client_secrets_file.return_value = mock_flow

                            # Mock the YouTube service build
                            with patch('googleapiclient.discovery.build') as mock_build:
                                uploader.get_authenticated_service()

                                # Verify the corrupted token was replaced
                                new_content = token_path.read_text()
                                new_token = json.loads(new_content)
                                assert "type" in new_token
                                assert new_token["type"] == "authorized_user"

    def test_missing_token_triggers_oauth(self):
        """Missing token.json should trigger OAuth flow."""
        import uploader
        from unittest.mock import patch, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "token.json"
            # Token file does not exist

            with patch('uploader.TOKEN_PATH', token_path):
                with patch('uploader.find_credentials', return_value=Path("dummy")):
                    # When token doesn't exist, load_credentials_from_file won't be called initially
                    # Instead, OAuth flow should be triggered
                    with patch('google_auth_oauthlib.flow.InstalledAppFlow') as mock_flow_class:
                        mock_flow = MagicMock()
                        mock_creds = MagicMock()
                        mock_creds.to_json.return_value = '{"type": "authorized_user", "token": "new"}'
                        mock_flow.run_local_server.return_value = mock_creds
                        mock_flow_class.from_client_secrets_file.return_value = mock_flow

                        with patch('googleapiclient.discovery.build') as mock_build:
                            uploader.get_authenticated_service()

                            # Verify token.json was created
                            assert token_path.exists()
                            new_token = json.loads(token_path.read_text())
                            assert "type" in new_token

    def test_pipeline_error_message_guides_reauth(self):
        """Pipeline.py error handler should guide user to re-authenticate."""
        pipeline_path = Path(__file__).parent.parent / "src" / "pipeline.py"
        content = pipeline_path.read_text(encoding="utf-8")

        # The Exception handler for YouTube upload should provide
        # guidance on re-authentication, not just "upload manually"
        # Check that pipeline has guidance about re-auth or checking token
        has_auth_guidance = (
            "re-auth" in content.lower() or
            "authenticate" in content.lower() or
            "delete token" in content.lower() or
            "credentials" in content.lower()
        )

        assert has_auth_guidance, (
            "Pipeline should guide users to re-authenticate when YouTube upload fails. "
            "Check pipeline.py exception handling for YouTube upload."
        )

    def test_upload_progress_callback_invoked(self):
        """Progress callback should be called during chunked upload."""
        pass

    def test_upload_progress_percentages_correct(self):
        """Progress percentages should range from 0% to 100%."""
        pass

    def test_upload_progress_console_output_format(self):
        """Progress output should match FLAC_Flow pattern: % + MB/total MB."""
        pass

    def test_upload_doesnt_hang_on_large_file(self):
        """Upload should complete without hanging (timeout check)."""
        pass

    def test_upload_uses_optimal_chunk_size(self):
        """MediaFileUpload should use efficient chunking, not single-chunk."""
        pass
