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


def _print_oauth_instructions(expected_channel_id: str = None):
    """Print clear instructions for OAuth flow to terminal."""
    print("\n" + "="*70)
    print("YOUTUBE LOGIN")
    print("="*70)
    print()
    print("1. Browser will open for YouTube login")
    print("2. You may see 'Google hasn't verified this app' - click [Continue]")
    if expected_channel_id:
        print(f"3. Select the account that owns: {expected_channel_id}")
    else:
        print("3. Select your YouTube account")
    print("4. Grant permissions when prompted")
    print("5. Return to terminal - login will complete automatically")
    print()
    print("="*70)
    print()


def get_authenticated_service(expected_channel_id: str = None):
    """Get authenticated YouTube v3 service. Handles token refresh and OAuth flow.

    If token.json exists but is corrupted/empty, it will be deleted and a new
    OAuth flow will be triggered to create a fresh token.

    Args:
        expected_channel_id: If provided, print instructions showing which account to select during OAuth.
    """
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
        try:
            creds, _ = google.auth.load_credentials_from_file(str(TOKEN_PATH), SCOPES)
        except (ValueError, KeyError) as e:
            # Token file is corrupted/malformed (missing 'type' field, invalid JSON, etc)
            logging.warning("Token file corrupted or invalid: %s", e)
            logging.warning("Deleting corrupted token and triggering re-authentication...")
            TOKEN_PATH.unlink()
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_path = find_credentials()
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            _print_oauth_instructions(expected_channel_id)
            creds = flow.run_local_server(port=0)
        token_json = json.loads(creds.to_json())
        # Ensure 'type' field is present (required by google.auth)
        if "type" not in token_json:
            token_json["type"] = "authorized_user"
        tmp = TOKEN_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(token_json), encoding="utf-8")
        tmp.replace(TOKEN_PATH)
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

    file_size_bytes = mp4_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    logging.info("Uploading: %s (%.1f MB)", mp4_path.name, file_size_mb)
    logging.info("Title: %s", title)
    print()  # blank line before progress

    # Use 5MB chunks (not -1, which uploads entire file as one request)
    # 5MB is efficient for typical broadband speeds without excessive memory use
    chunksize = 5 * 1024 * 1024  # 5 MB

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
        media_body=MediaFileUpload(str(mp4_path), chunksize=chunksize, resumable=True),
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            bytes_uploaded = int(file_size_bytes * status.progress())
            bytes_mb = bytes_uploaded / (1024 * 1024)
            total_mb = file_size_mb
            # Print to console in real-time (FLAC_Flow pattern)
            print(f"\r  {pct:.0f}%  ({bytes_mb:.1f} / {total_mb:.0f} MB)", end="", flush=True)
            logging.debug("  Upload progress: %d%% (%d bytes)", pct, bytes_uploaded)

    print()  # newline after progress
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
