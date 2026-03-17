# YouTube Publishing — Research & Design

**Project:** CompilationVidMaker (CVM) — Marvel Rivals gameplay compilations
**Date:** 2026-03-08

---

## 1. YouTube Data API v3 Capabilities

### 1.1 Upload a video and set it as private

Yes. The `videos.insert` endpoint accepts a `status.privacyStatus` field.

```
POST https://www.googleapis.com/upload/youtube/v3/videos
  ?part=snippet,status
```

Set `status.privacyStatus` to `"private"`. The video remains hidden until you change it.

```json
{
  "snippet": { "title": "...", "description": "..." },
  "status":  { "privacyStatus": "private" }
}
```

### 1.2 Set the "Game" / game title to "Marvel Rivals"

**Partially — with caveats.**

The game link ("Marvel Rivals" appearing under the video as a clickable link) is set through
YouTube Studio UI and is **not exposed in the Data API v3**.

**What you can do via API:**
- Set `snippet.categoryId = "20"` to mark as Gaming.
- Add `"Marvel Rivals"` as a tag in `snippet.tags`.

**Practical recommendation:** Upload via API, then manually set the game link in Studio. Takes 5 seconds.

### 1.3 Add a video to an existing playlist

Yes. Use `playlistItems.insert`.

```json
{
  "snippet": {
    "playlistId": "PLxxxxxxxxxxxxxx",
    "resourceId": { "kind": "youtube#video", "videoId": "VIDEO_ID" }
  }
}
```

Store the playlist ID from the Studio URL (`...?list=PLxxxxxx`) in config.

### 1.4 Set/update a video thumbnail

Yes, using `thumbnails.set`.

```
POST https://www.googleapis.com/upload/youtube/v3/thumbnails/set
  ?videoId=VIDEO_ID
Content-Type: image/jpeg
[raw image bytes]
```

**Constraints:** < 2 MB, recommended 1280×720 (16:9), JPEG/PNG. Channel must be verified (phone number).

### 1.5 OAuth Scopes Required

| Scope | Why needed |
|---|---|
| `https://www.googleapis.com/auth/youtube.upload` | Upload videos |
| `https://www.googleapis.com/auth/youtube` | Thumbnails, metadata, playlists |

Request both together. `youtube.upload` alone is **not** sufficient for thumbnails or playlists.

**OAuth flow:** "Installed application" / desktop flow. First run opens browser for consent;
subsequent runs use stored `token.json`. Handled entirely by `google-api-python-client`.

### 1.6 API Quota Costs

Daily quota: **10,000 units** per project (resets midnight Pacific).

| Operation | Endpoint | Quota Cost |
|---|---|---|
| Upload video | `videos.insert` | **1,600 units** |
| Update metadata | `videos.update` | 50 units |
| Add to playlist | `playlistItems.insert` | 50 units |
| Set thumbnail | `thumbnails.set` | 50 units |
| List videos (read) | `videos.list` | 1 unit |

**Cost per full pipeline run:** ~1,750 units. Free quota allows ~5 videos/day — sufficient for a personal channel.

---

## 2. Thumbnail Generation

### Python library: Pillow

```python
from PIL import Image, ImageDraw, ImageFont

frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
img = Image.fromarray(frame_rgb)
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("Impact.ttf", size=90)

draw.text((52, 52), "PENTA KILL", font=font, fill=(0, 0, 0))      # shadow
draw.text((50, 50), "PENTA KILL", font=font, fill=(255, 220, 0))  # gold text

img.save("thumbnail.jpg", quality=95)
```

OpenCV's `cv2.putText` only supports basic built-in fonts — use Pillow for thumbnails.

### Recommended fonts

| Font | Notes |
|---|---|
| **Impact** | Classic YouTube thumbnail font — bundled with Windows (`C:\Windows\Fonts\impact.ttf`) |
| **Bebas Neue** | Clean all-caps, popular for gaming — free on Google Fonts |
| **Anton** | Similar to Bebas Neue, slightly wider — free on Google Fonts |

**For Marvel Rivals:** Impact or Bebas Neue. White text with black outline, or gold/yellow with dark shadow.

```python
def draw_outlined_text(draw, pos, text, font, fill, outline_color, outline_width=3):
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
    draw.text(pos, text, font=font, fill=fill)
```

**Best thumbnail frame:** The frame where the highest kill tier was detected (Penta/Hexa > Quad).
Output at exactly **1280×720** to match YouTube's recommended thumbnail size.

---

## 3. Recommended Architecture — CVM-Publisher

A separate Python tool (`cvm_publisher`) that reads CVM's output folder and handles upload.

**Why separate from CVM:**
- C++ has no first-class support for OAuth or YouTube API
- Python has 3-line installs for all needed libraries
- Different lifecycles: CVM encodes; publisher runs later when you decide to upload

### Pipeline per batch

```
Step 1: Scan data/output/ — find description.txt files not yet uploaded
Step 2: Upload .mp4 (private) via videos.insert — record videoId
Step 3: Set thumbnail via thumbnails.set
Step 4: Add to playlist via playlistItems.insert
Step 5: Mark as uploaded — append to uploaded.json
Step 6: Print YouTube Studio URL: https://studio.youtube.com/video/{videoId}/edit
```

### Suggested file structure

```
cvm_publisher/
├── cvm_publisher.py        # Main entry point
├── config.json             # playlistId, output_dir path
├── credentials.json        # OAuth client secret (gitignored)
├── token.json              # OAuth refresh token (gitignored)
├── uploaded.json           # Tracks uploaded files to avoid duplicates
├── templates/              # Reference banner crops (quadra.png, penta.png, hexa.png)
├── fonts/                  # impact.ttf or Bebas Neue
└── src/
    ├── detector.py         # KO frame detection
    ├── thumbnail.py        # Thumbnail generation
    ├── uploader.py         # YouTube API calls
    └── description.py      # Parse CVM description .txt files
```

### Python dependencies

```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=1.0.0
opencv-python>=4.8.0
Pillow>=10.0.0
pytesseract>=0.3.10   # optional OCR fallback
```

### Getting started with the YouTube API

1. Go to Google Cloud Console, create a project (e.g. "CVM-Publisher")
2. Enable **YouTube Data API v3** in "APIs & Services > Library"
3. Create OAuth 2.0 credentials: "Desktop app" type
4. Download `credentials.json`
5. First run opens browser for consent — `token.json` saved for future runs

**Never commit `credentials.json` or `token.json` to git.**

### Minimal upload code

```python
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth, os

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

def get_authenticated_service():
    creds = None
    if os.path.exists("token.json"):
        creds, _ = google.auth.load_credentials_from_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def upload_video(youtube, mp4_path, title, description, tags):
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description,
                        "tags": tags, "categoryId": "20"},
            "status": {"privacyStatus": "private"},
        },
        media_body=MediaFileUpload(mp4_path, chunksize=-1, resumable=True),
    )
    return request.execute()["id"]  # videoId
```

---

## 4. Summary

| Question | Answer |
|---|---|
| Upload + set private via API? | Yes — `videos.insert` with `privacyStatus: "private"` |
| Set game to "Marvel Rivals" via API? | No — set `categoryId=20` + add as tag; set game link manually in Studio |
| Add to existing playlist via API? | Yes — `playlistItems.insert` with known `playlistId` |
| Set thumbnail via API? | Yes — `thumbnails.set` after upload |
| OAuth scopes? | `youtube.upload` + `youtube` |
| Quota cost per video? | ~1,750 units; free tier allows ~5 videos/day |
| Thumbnail library? | Pillow; Impact or Bebas Neue font |
| Architecture? | Separate Python tool, reads CVM's `data/output/` folder |
