# YouTube Publishing Pipeline — Research Report

**Project:** CompilationVidMaker (CVM) — Marvel Rivals gameplay compilations
**Date:** 2026-03-08
**Purpose:** Inform the design of a Python companion tool that auto-publishes CVM output to YouTube

---

## 1. YouTube Data API v3 Capabilities

### 1.1 Can you upload a video and set it as private?

Yes. The `videos.insert` endpoint accepts a `status.privacyStatus` field.

```
POST https://www.googleapis.com/upload/youtube/v3/videos
  ?part=snippet,status
```

Set `status.privacyStatus` to `"private"` in the request body. The video remains unlisted from public search until you explicitly change it. This is the correct default for a review-then-publish workflow.

```json
{
  "snippet": { "title": "...", "description": "..." },
  "status":  { "privacyStatus": "private" }
}
```

### 1.2 Can you set the "Game" / game title to "Marvel Rivals"?

**Partially — with important caveats.**

YouTube's API does not have a dedicated `gamingDetails.game` field for gaming content creators in the regular `videos.insert` / `videos.update` endpoints. The `snippet.categoryId` field lets you set the broad category to `"20"` (Gaming), but you cannot programmatically tag a video as being specifically about "Marvel Rivals" through the public Data API v3.

Game tagging ("Marvel Rivals" appears under the video as a clickable game link) is set through YouTube Studio's UI and is linked to YouTube's internal game database. This is **not exposed in the Data API v3**.

**What you can do instead via API:**
- Set `snippet.categoryId = "20"` to mark the video as Gaming.
- Add `"Marvel Rivals"` as a tag in `snippet.tags` — this helps search/discovery even if it doesn't create the game link.
- Include the game name prominently in the title and description.

**Practical recommendation:** Upload via API, then manually set the game link in YouTube Studio once. It takes 5 seconds per video.

### 1.3 Can you add a video to an existing playlist via API?

Yes. Use `playlistItems.insert`.

```
POST https://www.googleapis.com/youtube/v3/playlistItems
  ?part=snippet
```

Request body:
```json
{
  "snippet": {
    "playlistId": "PLxxxxxxxxxxxxxx",
    "resourceId": {
      "kind": "youtube#video",
      "videoId": "VIDEO_ID_RETURNED_FROM_UPLOAD"
    }
  }
}
```

You must know the playlist ID in advance. Get it from the YouTube Studio URL when viewing the playlist: `...?list=PLxxxxxx`. Store it in the tool's config file. You do **not** need to create a new playlist — inserting into an existing one is fully supported.

### 1.4 Can you set/update a video thumbnail via API?

Yes, using `thumbnails.set`.

```
POST https://www.googleapis.com/upload/youtube/v3/thumbnails/set
  ?videoId=VIDEO_ID
Content-Type: image/jpeg
[raw image bytes]
```

**Constraints:**
- Image must be under 2 MB.
- Recommended resolution: 1280×720 pixels (16:9).
- Accepted formats: JPEG, PNG, GIF, BMP (JPEG is standard).
- Your channel must be verified to set custom thumbnails. Verification requires a phone number on the Google account.

This is a separate API call made after the video upload returns the video ID.

### 1.5 OAuth Scopes Required

| Scope | Why needed |
|---|---|
| `https://www.googleapis.com/auth/youtube.upload` | Upload videos (`videos.insert`) |
| `https://www.googleapis.com/auth/youtube` | Set thumbnails, update metadata, manage playlists |

In practice, request both scopes together. The `youtube` scope is a superset of most management operations. The `youtube.upload` scope alone is **not** sufficient for thumbnails or playlist insertion.

**OAuth flow:** Use the "installed application" / "desktop" OAuth flow (not a web server flow). The first run opens a browser for consent; subsequent runs use a stored `token.json` refresh token. The Google API Python client library (`google-api-python-client`) handles this entirely.

### 1.6 API Quota Costs

YouTube Data API v3 has a daily quota of **10,000 units** per project (as of 2025). Reset is at midnight Pacific time.

| Operation | Endpoint | Quota Cost |
|---|---|---|
| Upload video | `videos.insert` | **1,600 units** |
| Update video metadata | `videos.update` | 50 units |
| Add to playlist | `playlistItems.insert` | 50 units |
| Set thumbnail | `thumbnails.set` | 50 units |
| List videos (read) | `videos.list` | 1 unit |

**Cost per full pipeline run (1 video):** ~1,750 units.
**Videos per day within free quota:** ~5 videos before hitting the 10,000 limit.

For a personal channel uploading a few videos per week, the free quota is sufficient with no issues. If you exceed quota, the API returns HTTP 403 with `quotaExceeded`. Quota increase requests can be submitted to Google but require justification.

---

## 2. KO Frame Detection Approach

### 2.1 The Detection Goal

Marvel Rivals displays kill-streak text on the **right side** of the screen:
- KO, Double, Triple — ignore these
- **Quadra, Penta, Hexa** — detect these as highlight moments

The goal is to find the timestamp(s) in the compiled video where these appear, so they can be added to the YouTube description as clickable timestamps.

### 2.2 OpenCV Template Matching

**Viability: High for controlled conditions.**

Template matching (`cv2.matchTemplate`) works by sliding a reference image (a crop of the "Quadra Kill" text as it appears in-game) over each frame and computing similarity. When similarity exceeds a threshold, a match is recorded.

**Strengths:**
- Extremely fast per-frame — typically 1–5 ms per frame at 1080p for a small template.
- No model training needed.
- Works well when the UI element is pixel-consistent (same font, same position, same color).

**Weaknesses:**
- Sensitive to resolution changes or UI scaling. If recorded at a different resolution/UI scale than the template, it fails.
- Fails if the game patches its UI visuals.
- Requires one reference template image per kill tier (Quadra, Penta, Hexa) — 3 images total.

**Implementation sketch:**
```python
import cv2
import numpy as np

templates = {
    "Quadra": cv2.imread("templates/quadra.png", cv2.IMREAD_GRAYSCALE),
    "Penta":  cv2.imread("templates/penta.png",  cv2.IMREAD_GRAYSCALE),
    "Hexa":   cv2.imread("templates/hexa.png",   cv2.IMREAD_GRAYSCALE),
}
THRESHOLD = 0.80

cap = cv2.VideoCapture("video.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)

frame_idx = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Crop right 25% of frame
    h, w = frame.shape[:2]
    roi = frame[:, int(w * 0.75):]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    for tier, tmpl in templates.items():
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        if res.max() >= THRESHOLD:
            ts_sec = frame_idx / fps
            print(f"{tier} at {ts_sec:.1f}s")

    frame_idx += 1

cap.release()
```

**Recommendation:** Start with template matching. Capture the kill-streak text from an actual game recording, crop it cleanly, save as PNG. Test threshold values between 0.75–0.85.

### 2.3 pytesseract OCR

**Viability: Medium — useful as a fallback or complement.**

pytesseract is a Python wrapper for Tesseract OCR (optical character recognition). It reads text from image regions.

**Strengths:**
- Does not require reference images.
- Handles font variations and scaling better than template matching.
- Can read any text, so it also picks up new kill tiers if the game adds them.

**Weaknesses:**
- Slower than template matching: ~50–150 ms per frame (10–30x slower).
- Marvel Rivals uses a stylised HUD font with glow/outline effects — Tesseract may misread characters (e.g., confusing "PENTA" with "PEMTA").
- Requires preprocessing: increase contrast, threshold the image to isolate white/bright text.
- Needs Tesseract installed separately (not just pip install).

**Preprocessing recommendation for better OCR:**
```python
import pytesseract
from PIL import Image
import cv2

roi_bgr = frame[:, int(w*0.75):]  # right quarter
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
text = pytesseract.image_to_string(thresh, config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ")
for kw in ["QUADRA", "PENTA", "HEXA"]:
    if kw in text.upper():
        # record timestamp
```

**Recommendation:** Use template matching as the primary method. If it proves unreliable across patches, add OCR as a fallback.

### 2.4 Best Python Libraries for Frame-by-Frame Video Analysis

| Library | Role | Install |
|---|---|---|
| `opencv-python` | Video I/O, template matching, image processing | `pip install opencv-python` |
| `numpy` | Array operations (included with OpenCV) | `pip install numpy` |
| `pytesseract` | OCR fallback | `pip install pytesseract` + Tesseract binary |
| `Pillow` | Image manipulation for thumbnails | `pip install Pillow` |

`opencv-python` is the correct package name (not `cv2` on PyPI). It includes the `cv2` module.

### 2.5 Performance: 15-Minute 1080p Video Analysis

**Raw frame counts:**
- 15 minutes at 60 fps = 54,000 frames
- 15 minutes at 30 fps = 27,000 frames

**Template matching speed (approximate, modern CPU):**
- Per frame (right-quarter crop, 3 templates): ~3–8 ms
- Full 54,000 frames at 60fps: **2.7–7 minutes** of CPU processing time
- Full 27,000 frames at 30fps: **1.4–3.5 minutes**

**Is sampling every N frames viable?**

Yes, and it is strongly recommended. Kill-streak text in Marvel Rivals stays on screen for approximately 2–3 seconds. Sampling every 10 frames (at 60fps = every 0.16s) is more than sufficient to catch every event while reducing processing time by 10x.

| Sample rate | Frames processed (15min @ 60fps) | Estimated time |
|---|---|---|
| Every frame | 54,000 | 2.7–7 min |
| Every 5 frames | 10,800 | 30–90 sec |
| Every 10 frames | 5,400 | 15–45 sec |
| Every 30 frames | 1,800 | 5–15 sec |

**Recommended:** Sample every 10 frames. At 60fps this samples at 6Hz, which is well above what is needed to detect a 2-second on-screen event. Once a hit is detected, you can seek back to find the precise first frame.

**Avoid duplicate timestamps:** After detecting an event, suppress further detections for ~5 seconds (300 frames at 60fps) to avoid reporting the same kill streak multiple times.

---

## 3. Thumbnail Generation

### 3.1 Python Libraries for Overlaying Text on a Video Frame

**Pillow (PIL fork)** is the recommended library.

```python
from PIL import Image, ImageDraw, ImageFont

# Load frame (from OpenCV, convert BGR→RGB)
frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
img = Image.fromarray(frame_rgb)

draw = ImageDraw.Draw(img)
font = ImageFont.truetype("Impact.ttf", size=90)

# Drop shadow for readability
draw.text((52, 52), "PENTA KILL", font=font, fill=(0, 0, 0))       # shadow
draw.text((50, 50), "PENTA KILL", font=font, fill=(255, 220, 0))   # gold text

img.save("thumbnail.jpg", quality=95)
```

**OpenCV** can also overlay text (`cv2.putText`) but has limited font support — only basic built-in fonts, no TTF loading. Pillow is superior for thumbnail work.

### 3.2 Recommended Fonts for YouTube Thumbnails

YouTube thumbnails compete for attention at small sizes. Bold, blocky fonts with high contrast are standard.

| Font | Why it works | Availability |
|---|---|---|
| **Impact** | Classic YouTube thumbnail font — extremely bold, narrow, high legibility | Bundled with Windows (`C:\Windows\Fonts\impact.ttf`) |
| **Bebas Neue** | Clean all-caps, very popular for gaming thumbnails | Free on Google Fonts |
| **Anton** | Similar to Bebas Neue, slightly wider | Free on Google Fonts |
| **Russo One** | Slightly futuristic, suits gaming content | Free on Google Fonts |

**Recommended for Marvel Rivals content:** Impact or Bebas Neue. Use white text with a black outline/drop shadow, or gold/yellow text with a dark shadow. Avoid thin fonts — they become illegible at small thumbnail sizes.

**Adding a text outline with Pillow:**
```python
def draw_outlined_text(draw, pos, text, font, fill, outline_color, outline_width=3):
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
    draw.text(pos, text, font=font, fill=fill)
```

### 3.3 Thumbnail Strategy for This Project

Best thumbnail frame = the frame where the highest kill tier was detected (Penta/Hexa preferred over Quadra). Overlay the kill tier text and optionally a "Part N" label.

**Resolution:** Output at exactly 1280×720 to match YouTube's recommended thumbnail size.

---

## 4. Recommended Architecture

### 4.1 Separate Python Companion Tool vs. Integrated

**Recommendation: Separate Python companion tool**, named `CVM-Publisher` (or `cvm_publisher`).

**Reasons:**
- CVM is C++ on Windows — embedding a YouTube OAuth flow in C++ would require significant extra work (libcurl, JSON parsing, OAuth token management).
- Python has first-class support for the Google API client library (`google-api-python-client`), OpenCV, and Pillow. These are 3-line installs.
- The tools have different lifecycles: CVM runs to encode; the publisher runs later when you decide to upload.
- Keeping them separate means CVM stays simple and fast, and the publisher can evolve independently.

### 4.2 Full Pipeline Outline

```
CVM Output/
├── marvel_rivals_batch1.mp4
├── marvel_rivals_batch1_description.txt
├── marvel_rivals_batch2.mp4
└── marvel_rivals_batch2_description.txt
```

**CVM-Publisher pipeline for each batch:**

```
Step 1: Scan Output/ folder
   └─ Find paired .mp4 + _description.txt files
   └─ Skip any already uploaded (track in uploaded.json)

Step 2: KO Frame Detection
   └─ Open .mp4 with cv2.VideoCapture
   └─ Sample every 10 frames, crop right 25%
   └─ Template match for Quadra/Penta/Hexa
   └─ Record list of (timestamp_seconds, tier) events
   └─ Pick best thumbnail frame (highest tier, earliest occurrence)

Step 3: Read Description File
   └─ Parse _description.txt written by CVM
   └─ Extract title, description body, existing timestamps
   └─ Merge detected frame timestamps with filename-based timestamps
      (frame detection is more precise; filenames are approximate)

Step 4: Generate Thumbnail
   └─ Extract best frame with cv2
   └─ Resize to 1280×720 with Pillow
   └─ Overlay kill tier text (Impact font, outlined)
   └─ Save as thumbnail.jpg (< 2 MB)

Step 5: Upload to YouTube (private)
   └─ Authenticate with OAuth (token.json, prompt browser on first run)
   └─ videos.insert — upload .mp4, set title/description/tags/categoryId=20, privacyStatus=private
   └─ Record returned videoId

Step 6: Set Thumbnail
   └─ thumbnails.set with videoId and thumbnail.jpg

Step 7: Add to Playlist
   └─ playlistItems.insert with videoId and configured playlistId

Step 8: Mark as uploaded
   └─ Append videoId + filename to uploaded.json
   └─ Print YouTube URL: https://studio.youtube.com/video/{videoId}/edit
```

### 4.3 Suggested File Structure for CVM-Publisher

```
CVM-Publisher/
├── cvm_publisher.py        # Main entry point — orchestrates the pipeline
├── config.json             # playlistId, channelId, output_dir path
├── credentials.json        # OAuth client secret (from Google Cloud Console, gitignored)
├── token.json              # OAuth refresh token (auto-generated, gitignored)
├── uploaded.json           # Tracks uploaded files to avoid duplicates
├── templates/
│   ├── quadra.png          # Template image crops from actual gameplay
│   ├── penta.png
│   └── hexa.png
├── fonts/
│   └── impact.ttf          # Or Bebas Neue etc.
├── modules/
│   ├── detector.py         # KO frame detection (OpenCV)
│   ├── thumbnail.py        # Thumbnail generation (Pillow)
│   ├── uploader.py         # YouTube API calls
│   └── description.py      # Parse CVM description .txt files
└── logs/
    └── publisher.log       # Timestamped run log
```

### 4.4 Key Python Dependencies

```
# requirements.txt
google-api-python-client>=2.100.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=1.0.0
opencv-python>=4.8.0
numpy>=1.24.0
Pillow>=10.0.0
pytesseract>=0.3.10   # optional, OCR fallback only
```

### 4.5 Getting Started with the YouTube API

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., "CVM-Publisher").
3. Enable the **YouTube Data API v3** in "APIs & Services > Library".
4. Create OAuth 2.0 credentials: "APIs & Services > Credentials > Create Credentials > OAuth client ID" — choose "Desktop app".
5. Download `credentials.json`.
6. On first run, the library opens a browser tab. Sign in, grant access. A `token.json` is saved for future runs.

**Never commit `credentials.json` or `token.json` to git.** Add both to `.gitignore`.

### 4.6 Minimal Upload Code Example

```python
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth
import pickle, os

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
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "20",  # Gaming
            },
            "status": {
                "privacyStatus": "private",
            },
        },
        media_body=MediaFileUpload(mp4_path, chunksize=-1, resumable=True),
    )
    response = request.execute()
    return response["id"]  # videoId
```

---

## 5. Summary of Key Decisions

| Question | Answer |
|---|---|
| Upload + set private via API? | Yes — `videos.insert` with `status.privacyStatus: "private"` |
| Set game to "Marvel Rivals" via API? | No — game link not in public API. Set `categoryId=20` + add as tag. Do manually in Studio. |
| Add to existing playlist via API? | Yes — `playlistItems.insert` with known `playlistId` |
| Set thumbnail via API? | Yes — `thumbnails.set` after upload |
| OAuth scopes? | `youtube.upload` + `youtube` |
| Quota cost per video? | ~1,750 units; free tier allows ~5 videos/day |
| KO frame detection method? | OpenCV template matching, crop right 25%, sample every 10 frames |
| OCR fallback? | pytesseract if template matching is unreliable |
| Analysis time for 15-min video? | ~15–45 seconds with every-10-frame sampling |
| Thumbnail library? | Pillow for text overlay; Impact or Bebas Neue font |
| Architecture? | Separate Python tool (CVM-Publisher), reads CVM's Output/ folder |
