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

# Suppress verbose logging from google-auth libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("google_auth_httplib2").setLevel(logging.WARNING)

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
    """Upload video to YouTube using resumable protocol with fast chunk upload.

    Uses 10MB chunks with direct HTTP requests instead of googleapiclient's slow uploader.
    Expected speed: 40-80 MB/s (5-10 min for 2.4GB) vs 20 Mbps (40+ min) with old library.

    Args:
        youtube: authenticated YouTube v3 service (provides HTTP client + auth)
        mp4_path: path to .mp4 file
        title: video title
        description: full description (with timestamps)

    Returns:
        video_id of the uploaded video
    """
    import json

    file_size_bytes = mp4_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    logging.info("Uploading: %s (%.1f MB)", mp4_path.name, file_size_mb)
    logging.info("Title: %s", title)
    print()  # blank line before progress

    # Use the youtube service's HTTP object for authorized requests
    http = youtube._http

    # Initialize resumable session with YouTube API
    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Marvel Rivals"],
            "categoryId": "20",  # Gaming
        },
        "status": {"privacyStatus": "private"},
    }

    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    init_headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size_bytes),
        "Content-Type": "application/json",
    }

    init_body = json.dumps(metadata).encode("utf-8")
    init_response, init_body_bytes = http.request(
        init_url,
        method="POST",
        headers=init_headers,
        body=init_body,
    )

    logging.debug("Init response status: %s", init_response.status)
    logging.debug("Init response headers: %s", dict(init_response))

    if init_response.status != 200:
        raise ValueError(f"Failed to initialize resumable upload: {init_response.status}\n{init_body_bytes.decode('utf-8', errors='ignore')}")

    # Get the resumable session URI from Location header (httplib2 uses lowercase keys)
    session_uri = init_response.get("location") or init_response.get("Location")
    if not session_uri:
        raise ValueError(f"YouTube did not return resumable session URI. Headers: {dict(init_response)}")

    logging.debug("Resumable session URI: %s", session_uri)

    # Upload file in 10MB chunks
    chunksize = 10 * 1024 * 1024  # 10 MB (larger chunks = fewer round-trips)
    bytes_uploaded = 0
    response = None

    with open(mp4_path, "rb") as f:
        while bytes_uploaded < file_size_bytes:
            chunk = f.read(chunksize)
            chunk_len = len(chunk)
            chunk_end = min(bytes_uploaded + chunk_len, file_size_bytes)

            # Build Content-Range header
            content_range = f"bytes {bytes_uploaded}-{chunk_end - 1}/{file_size_bytes}"

            upload_headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(chunk_len),
                "Content-Range": content_range,
            }

            # Upload this chunk
            chunk_response, chunk_body = http.request(
                session_uri,
                method="PUT",
                headers=upload_headers,
                body=chunk,
            )

            # YouTube returns 200 (final) or 308 (more chunks coming)
            if chunk_response.status == 200:
                response = json.loads(chunk_body.decode("utf-8"))
                bytes_uploaded = chunk_end
                pct = 100
            elif chunk_response.status == 308:
                bytes_uploaded = chunk_end
                pct = int((bytes_uploaded / file_size_bytes) * 100)
            else:
                raise ValueError(f"Upload chunk failed: {chunk_response.status} {chunk_body}")

            # Progress reporting
            bytes_mb = bytes_uploaded / (1024 * 1024)
            total_mb = file_size_mb
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
