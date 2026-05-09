"""
uploader.py - YouTube API Phase 2 integration.

Handles OAuth authentication, channel validation, and video upload to YouTube.
Reuses OAuth logic from scripts/once_off/yt_upload_test.py.

Usage (from pipeline):
    youtube = uploader.get_authenticated_service()
    uploader.validate_channel_id(youtube, config.youtube_channel_id)
    uploader.upload_and_save_state(youtube, video_path, title, description, slug, state_path)
"""

import logging
import sys
from pathlib import Path
import json
import os

# Allow running from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent

TOKEN_PATH = REPO_ROOT / "config" / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _credentials_candidates():
    """Auto-detect any client_secret_*.json Google downloads into config/."""
    return sorted((REPO_ROOT / "config").glob("client_secret_*.json"))


def find_credentials() -> Path:
    """Find OAuth credentials file in config/. Raises FileNotFoundError if not found."""
    candidates = _credentials_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No client_secret_*.json found in {REPO_ROOT / 'config'}. "
        "Download from Google Cloud Console: "
        "APIs & Services -> Credentials -> OAuth 2.0 Client IDs -> Desktop app -> Download JSON"
    )


def get_authenticated_service():
    """Get authenticated YouTube v3 service. Handles token refresh and OAuth flow."""
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        import google.auth
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logging.error("Missing dependencies. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        raise

    creds = None
    if TOKEN_PATH.exists():
        creds, _ = google.auth.load_credentials_from_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_path = find_credentials()
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        logging.info("Token saved to %s", TOKEN_PATH)

    return build("youtube", "v3", credentials=creds)


def validate_channel_id(youtube, expected_channel_id: str) -> bool:
    """Validate that authenticated user's channel matches config. Raises ValueError on mismatch."""
    request = youtube.channels().list(part="id", mine=True)
    response = request.execute()

    if not response.get("items"):
        raise ValueError("Could not retrieve channel info from YouTube")

    actual_channel_id = response["items"][0]["id"]
    if actual_channel_id != expected_channel_id:
        raise ValueError(
            f"Channel ID mismatch. Expected {expected_channel_id}, but authenticated as {actual_channel_id}. "
            "Check config.json youtube_channel_id or re-authenticate."
        )

    logging.info("Channel validation OK: %s", actual_channel_id)
    return True


def parse_description_file(desc_path: Path) -> tuple[str, str]:
    """Parse title and description from _description.txt.

    Expected format (from description_writer.py):
      First line = Video title
      Remaining = description with timestamps

    Returns (title, description) tuple.
    """
    lines = desc_path.read_text(encoding="utf-8").strip().split("\n")
    if not lines:
        raise ValueError(f"Description file is empty: {desc_path}")

    title = lines[0].strip()
    description = "\n".join(lines[1:]).strip()

    logging.debug("Parsed description: title=%r, desc_len=%d", title, len(description))
    return title, description


def upload_video(youtube, mp4_path: Path, title: str, description: str) -> str:
    """Upload video to YouTube and return video ID.

    Args:
        youtube: authenticated YouTube v3 service
        mp4_path: path to .mp4 file
        title: video title
        description: full description (with timestamps)

    Returns:
        video_id of the uploaded video
    """
    from googleapiclient.http import MediaFileUpload

    file_size_mb = mp4_path.stat().st_size / (1024 * 1024)
    logging.info("Uploading: %s (%.1f MB)", mp4_path.name, file_size_mb)
    logging.info("Title: %s", title)

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["Marvel Rivals"],
                "categoryId": "20",  # Gaming
            },
            "status": {"privacyStatus": "private"},  # Always private; user makes public manually
        },
        media_body=MediaFileUpload(str(mp4_path), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logging.info("  Upload progress: %d%%", pct)

    video_id = response["id"]
    logging.info("Upload successful! Video ID: %s", video_id)
    return video_id


def upload_and_save_state(youtube, mp4_path: Path, title: str, description: str,
                         slug: str, state_path: Path) -> str:
    """Upload video and save metadata to state.json.

    Args:
        youtube: authenticated YouTube v3 service
        mp4_path: path to .mp4 file
        title: video title
        description: full description (with timestamps)
        slug: output folder name (e.g. THOR_FEB-MAR_2026_BATCH1)
        state_path: path to data/state.json

    Returns:
        video_id
    """
    from state import load, save

    video_id = upload_video(youtube, mp4_path, title, description)
    url = f"https://www.youtube.com/watch?v={video_id}"

    # Load current state and add video metadata
    state = load(state_path)
    if "videos" not in state:
        state["videos"] = {}

    state["videos"][slug] = {
        "video_id": video_id,
        "url": url,
        "title": title,
    }

    save(state, state_path)
    logging.info("Video metadata saved to state.json")
    logging.info("Watch: %s", url)

    return video_id
