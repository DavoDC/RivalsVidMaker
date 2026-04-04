"""
yt_upload_test.py - Phase 1 YouTube API feasibility probe.

Authenticates via OAuth and uploads a single video as PRIVATE.
Success = a private video appears on the channel with the given title.

Usage:
    python scripts/once_off/yt_upload_test.py <path_to_video.mp4>

Prerequisites:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

    A client_secret_*.json file must exist in config/.
    Download from Google Cloud Console -> APIs & Services -> Credentials -> OAuth 2.0 Client IDs -> Desktop app.
    Never commit client_secret_*.json or token.json to git.

On first run, a browser window opens for OAuth consent. token.json is saved for future runs.
"""

import sys
import os
from pathlib import Path

# Allow running from any directory
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---- find credentials.json ----
# Google downloads credentials as client_secret_<id>.apps.googleusercontent.com.json
# Accept that name too so no manual rename is needed.
TOKEN_PATH = REPO_ROOT / "token.json"


def _credentials_candidates():
    # Auto-detect any client_secret_*.json Google downloads into config/
    return sorted((REPO_ROOT / "config").glob("client_secret_*.json"))

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def find_credentials() -> Path:
    candidates = _credentials_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    print("ERROR: No client_secret_*.json found in config/")
    print()
    print("Download from Google Cloud Console:")
    print("  APIs & Services -> Credentials -> OAuth 2.0 Client IDs -> Desktop app -> Download JSON")
    print("  Save to: config/")
    sys.exit(1)


def get_authenticated_service():
    try:
        import google.auth
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Missing dependencies. Run:")
        print("  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

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
        print(f"Token saved to {TOKEN_PATH}")

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, mp4_path: Path, title: str) -> str:
    from googleapiclient.http import MediaFileUpload

    print(f"Uploading: {mp4_path.name} ({mp4_path.stat().st_size / 1_048_576:.1f} MB)")
    print("Privacy: PRIVATE")

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": "RivalsVidMaker upload test - safe to delete.",
                "tags": ["Marvel Rivals", "test"],
                "categoryId": "20",  # Gaming
            },
            "status": {"privacyStatus": "private"},
        },
        media_body=MediaFileUpload(str(mp4_path), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Upload progress: {pct}%", end="\r")

    print()
    return response["id"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/yt_upload_test.py <path_to_video.mp4>")
        print()
        print("Tip: use any short .mp4 file - even a 5-second test clip works.")
        sys.exit(1)

    mp4_path = Path(sys.argv[1])
    if not mp4_path.exists():
        print(f"ERROR: File not found: {mp4_path}")
        sys.exit(1)
    if mp4_path.suffix.lower() != ".mp4":
        print(f"WARNING: Expected .mp4, got {mp4_path.suffix} - proceeding anyway.")

    title = f"[TEST - DELETE ME] {mp4_path.stem}"

    print("Authenticating with YouTube...")
    youtube = get_authenticated_service()
    print("Authenticated OK.")

    video_id = upload_video(youtube, mp4_path, title)

    print()
    print("=" * 60)
    print("Upload successful!")
    print(f"  Video ID : {video_id}")
    print(f"  Watch URL: https://www.youtube.com/watch?v={video_id}")
    print(f"  Edit URL : https://studio.youtube.com/video/{video_id}/edit")
    print("=" * 60)
    print("The video is PRIVATE. Check YouTube Studio to confirm it appeared.")
    print("Delete it from Studio when done testing.")


if __name__ == "__main__":
    main()
