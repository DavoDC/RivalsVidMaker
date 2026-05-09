"""Tests for YouTube upload retry loop in pipeline.py"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestPipelineUploadRetry:
    """Tests for upload retry logic in pipeline.run()"""

    def test_upload_failure_prompts_for_retry(self):
        """When upload fails, user is prompted to delete token and re-auth."""
        # This test will verify that the exception handler prompts the user
        # instead of immediately falling back to manual upload
        pass

    def test_upload_failure_user_refuses_retry_falls_back_to_manual(self):
        """User refuses retry → falls back to manual upload instructions."""
        # When user enters 'N' or refuses, the flow should continue to
        # manual upload instructions (no retry attempted)
        pass

    def test_upload_failure_user_accepts_retry_deletes_token(self):
        """User accepts retry → token.json is deleted."""
        # Verify that when user agrees, token.json is deleted before retry
        pass

    def test_upload_failure_user_accepts_retry_succeeds(self):
        """User accepts retry, token deleted, retry succeeds."""
        # Verify the complete happy path:
        # 1. Upload fails
        # 2. User prompted and accepts
        # 3. Token deleted
        # 4. OAuth flow triggered
        # 5. Retry succeeds
        # 6. yt_uploaded = True (cleanup proceeds)
        pass

    def test_upload_failure_retry_still_fails_loops_back(self):
        """Retry fails again → prompt user again for another retry."""
        # Verify that if retry upload still fails, user is prompted again
        # to prevent infinite loops, might want a max retry count
        pass

    def test_pipeline_full_path_compile_to_upload_failure_to_retry(self):
        """Integration test: full compile path with upload failure and successful retry."""
        # End-to-end test simulating:
        # 1. Run compile
        # 2. Encode succeeds
        # 3. Upload fails
        # 4. User prompted
        # 5. User accepts retry
        # 6. Token deleted and re-created via OAuth
        # 7. Retry succeeds
        # 8. Cleanup proceeds
        pass

    def test_token_json_deleted_triggers_fresh_oauth(self):
        """Deleting token.json ensures fresh OAuth on next auth attempt."""
        # Verify that uploader.get_authenticated_service() detects
        # missing token and triggers OAuth flow
        pass
