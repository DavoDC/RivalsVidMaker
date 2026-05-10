# YouTube Publishing -- Research & Design

**Project:** RivalsVidMaker -- Marvel Rivals gameplay compilations
**Last updated:** 2026-05-09

> Note: References to "CVM" throughout legacy sections are old naming (CompilationVidMaker).
> This project is now RivalsVidMaker. API research and architecture notes remain valid.

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

### 1.2 Set video metadata after upload (title, tags, category, language, etc.)

**Yes -- via `videos.update` call.**

After `videos.insert` completes and you have the videoId, call `videos.update` with the `snippet` and `status` parts to set additional metadata. Cost: 50 units per update call. You can set metadata during the initial insert call (include it in the request body), or update it separately after the upload finishes.

**Settable via API in snippet (videos.update or videos.insert):**
- `snippet.title` - Video title (max 100 chars)
- `snippet.description` - Video description (max 5000 bytes)
- `snippet.categoryId` - Category ID (e.g., "20" = Gaming)
- `snippet.tags` - List of keyword tags (max 500 chars total)
- `snippet.defaultLanguage` - Language of the video (e.g., "en" for English)
- `snippet.localizations.(language).title` - Localized title for a specific language
- `snippet.localizations.(language).description` - Localized description

**Settable via API in status (videos.update or videos.insert):**
- `status.privacyStatus` - `"private"`, `"public"`, or `"unlisted"`
- `status.license` - `"youtube"` or `"creativeCommon"`
- `status.embeddable` - boolean (allow embedding)
- `status.publicStatsViewable` - boolean (show view counts)
- `status.madeForKids` - boolean (child-directed content)
- `status.publishAt` - Scheduled publish time (ISO 8601, only for private videos)
- `status.recordingDetails.recordingDate` - Recording date (ISO 8601)
- `status.paidProductPlacementDetails.hasPaidProductPlacement` - boolean

**NOT settable via API (manual in YouTube Studio):**
- Game title link ("Marvel Rivals" clickable link) - not exposed in Data API v3
- Caption certification - manual selection only

**Practical approach:** Set `categoryId`, `tags`, `defaultLanguage` during `videos.insert`. Optionally call `videos.update` afterward to set additional fields like `license`, `publicStatsViewable`, or playlist assignment.

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

**Constraints:** < 2 MB, recommended 1280x720 (16:9), JPEG/PNG. Channel must be verified (phone number).

### 1.5 OAuth Scopes Required

| Scope | Why needed |
|---|---|
| `https://www.googleapis.com/auth/youtube.upload` | Upload videos |
| `https://www.googleapis.com/auth/youtube` | Thumbnails, metadata, playlists |

Request both together. `youtube.upload` alone is **not** sufficient for thumbnails or playlists.

**OAuth flow:** "Installed application" / desktop flow. First run opens browser for consent;
subsequent runs use stored `token.json`. Handled entirely by `google-api-python-client`.

### 1.6 API Quota Costs

Daily quota: **10,000 units** per project (resets midnight Pacific). **Free tier -- no payment required** unless you exceed the quota significantly and apply for an increase.

| Operation | Endpoint | Quota Cost |
|---|---|---|
| Upload video | `videos.insert` | **1,600 units** |
| Update metadata | `videos.update` | 50 units |
| Add to playlist | `playlistItems.insert` | 50 units |
| Set thumbnail | `thumbnails.set` | 50 units |
| List videos (read) | `videos.list` | 1 unit |

**Cost per full pipeline run (upload + metadata + playlist + thumbnail):** ~1,750 units.

**Free quota capacity:**
- Single video per day: ~1,700 units = **plenty of room (6x overhead)**
- Batch of 5 videos: ~8,500 units = **within free quota**
- Batch of 10 videos: ~17,000 units = **exceeds free quota by 70% -- will fail on 7th video**

**For a 1-video-per-day workflow:** quota is not a constraint. You use ~17% of daily quota and have headroom for retries or additional metadata calls.

**Best practice:** Always diagnose upload failures before retrying. At 1,600 units/retry, blind retries exhaust quota fast.

---

## 2. Resumable Upload -- Protocol Reference

### 2.1 Two protocols exist -- do NOT mix them

Google exposes two distinct resumable upload protocols at the same endpoint. Mixing them (custom-protocol init + standard-protocol chunks) produces a **silent mid-transfer SSL connection abort** (`[WinError 10053]`) that looks like a network error but is actually a protocol rejection. This is the hardest failure mode to diagnose because the error is network-shaped, not protocol-shaped.

#### Standard resumable protocol (USE THIS)

**Init request:**
```
POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
Headers:
  Authorization: Bearer <token>
  Content-Type: application/json; charset=UTF-8
  X-Upload-Content-Length: <total bytes>
  X-Upload-Content-Type: video/*
Body: <metadata JSON>
```

**Init response:**
```
200 OK
Location: https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=...
```

Session URI comes back in the **`Location` header**.

**Chunk PUT (if chunking):**
```
PUT <session URI>
Headers:
  Authorization: Bearer <token>
  Content-Type: application/octet-stream
  Content-Length: <chunk bytes>
  Content-Range: bytes <start>-<end>/<total>
Body: <chunk bytes>
```

Responses: `308 Resume Incomplete` (more chunks), `200 OK` (done, body contains video metadata).

#### Custom protocol (DO NOT USE for chunk uploads)

Uses `X-Goog-Upload-Protocol: resumable`, `X-Goog-Upload-Command: start/upload/finalize`, and
`X-Goog-Upload-Offset` on chunks instead of `Content-Range`. Session URI comes back in
`x-goog-upload-url` header. **If you init with this protocol, chunks MUST also use it.**
Sending `Content-Range` to a custom-protocol session URI causes the server to abort the SSL
connection mid-transfer with `[WinError 10053]`.

### 2.2 Single-chunk vs chunked upload

**Current implementation:** single-chunk (entire file in one PUT, streamed via generator).

| Approach | Pros | Cons |
|---|---|---|
| Single-chunk | No round-trip overhead, simpler code, smooth continuous progress | No resumability -- connection drop = restart from 0 |
| Chunked (32MB) | Resumable on failure | ~75 round-trips for 2.4GB, same YouTube speed throttle |

For a home connection uploading 2.4GB, single-chunk is a ~10-11 minute uninterrupted request.
Failures are unlikely on a stable connection. If it fails, just retry -- the resumable session
init takes <1s.

### 2.3 Upload speed -- YouTube throttles API clients

**Confirmed finding (2026-05-09):** YouTube throttles programmatic API uploads to ~3-4 MB/s.
This is NOT a client-side bug. Evidence:

- Same file uploads faster in browser (browser clients get higher server-side quota)
- Initial burst hits ~4 MB/s then throttles to ~0.8-1 MB/s over time
- Reported across Java, .NET, Python clients since 2016 -- long-standing, not a regression
- HTTP/2 does not help -- bottleneck is server-side request processing, not protocol overhead
- Single-chunk vs 32MB chunks vs 1MB chunks -- all produce the same effective throughput
- Google does not document the throttle rate

**For a 2.4GB file:** expect 10-15 minutes regardless of client-side tuning.

**No known workaround** that brings API speed to browser speed. The gap appears to be intentional
server-side differentiation between browser and API clients.

**VPS investigation - CLOSED (2026-05-10):** A GCP VPS does not help. The YouTube API throttle
applies to any OAuth API client regardless of source IP or network proximity to Google. A GCP VM
calling `videos.insert` lands in the same throttled bucket as a home PC. Home upload is 47.71 Mbps
(~6 MB/s) - already above the API ceiling, so home bandwidth is not the constraint.

The only genuine bypass would have been the old YouTube Studio "Import from Google Drive" feature,
which triggered a server-side Drive->YouTube copy that never touched the upload API. Google removed
this feature (present in classic Studio, gone in 2026 modern Studio). No equivalent exists.

**Correct response to the throttle:** schedule uploads to run unattended (overnight). The
10-15 minute window is fixed; make it invisible rather than trying to eliminate it.

### 2.4 Current implementation (uploader.py)

Uses `httpx` with HTTP/2 and a streaming generator for single-chunk upload:

```python
import httpx

def _stream(mp4_path, file_size_bytes, file_size_mb):
    read_buf = 256 * 1024
    bytes_sent = 0
    with open(mp4_path, "rb") as f:
        while True:
            buf = f.read(read_buf)
            if not buf:
                break
            bytes_sent += len(buf)
            pct = int(bytes_sent / file_size_bytes * 100)
            mb = bytes_sent / (1024 * 1024)
            print(f"\r  {pct}%  ({mb:.1f} / {file_size_mb:.0f} MB)", end="", flush=True)
            yield buf

with httpx.Client(http2=True, timeout=httpx.Timeout(30.0, read=3600.0)) as client:
    # 1. Init resumable session (standard protocol)
    init_resp = client.post(init_url, headers=init_headers, json=metadata)
    session_uri = init_resp.headers["location"]

    # 2. Upload entire file in one PUT
    upload_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size_bytes),
        "Content-Range": f"bytes 0-{file_size_bytes - 1}/{file_size_bytes}",
    }
    response = client.put(session_uri, headers=upload_headers,
                          content=_stream(mp4_path, file_size_bytes, file_size_mb),
                          timeout=httpx.Timeout(30.0, read=3600.0))

video_id = response.json()["id"]
```

**Why httpx over requests:**
- HTTP/2 support built-in (`http2=True`) -- reduces per-request overhead
- `content=<iterable>` accepts a generator for streaming without loading file into memory
- `requests` only supports HTTP/1.1

**Why httpx over google-api-python-client MediaFileUpload:**
- `MediaFileUpload` uses the library's own chunking and HTTP stack (httplib2)
- Same YouTube throttle applies -- no speed advantage
- Direct httpx gives full control over headers, timeouts, and streaming

### 2.5 Token extraction for direct HTTP calls

The `youtube` service object from `build("youtube", "v3", credentials=creds)` handles auth
internally for library calls but does not expose the Bearer token for direct HTTP. Extract from
`token.json` instead:

```python
token_data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
access_token = token_data.get("token") or token_data.get("access_token")
auth_header = f"Bearer {access_token}"
```

The field name is `"token"` in tokens written by newer google-auth versions and `"access_token"`
in older ones. Check both.

### 2.6 Debugging checklist for upload failures

1. **Init response returns `x-goog-upload-url` instead of `Location`** -- you used the custom
   protocol for init. Switch to standard (remove `X-Goog-Upload-*` headers, add
   `X-Upload-Content-Length` and `X-Upload-Content-Type`).

2. **SSL/socket abort mid-transfer (`[WinError 10053]`)** -- protocol mismatch (see 2.1).
   NOT a network issue. Proven by: browser uploads same file without error.

3. **401 Unauthorized** -- token expired. Re-authenticate (`python pipeline.py` triggers OAuth
   flow) or delete `config/token.json` to force fresh login.

4. **403 Forbidden** -- wrong account (channel ID mismatch) or quota exhausted. Check
   `validate_channel_id()` output and Google Cloud Console quota usage.

5. **Slow upload / throttled** -- expected. See 2.3. Not a bug.

6. **`ValueError: No token in token.json`** -- token file written by older auth version uses
   `access_token` key, newer uses `token`. The extractor in uploader.py checks both.

---

## 3. Thumbnail Generation

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

OpenCV's `cv2.putText` only supports basic built-in fonts -- use Pillow for thumbnails.

### Recommended fonts

| Font | Notes |
|---|---|
| **Impact** | Classic YouTube thumbnail font -- bundled with Windows (`C:\Windows\Fonts\impact.ttf`) |
| **Bebas Neue** | Clean all-caps, popular for gaming -- free on Google Fonts |
| **Anton** | Similar to Bebas Neue, slightly wider -- free on Google Fonts |

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
Output at exactly **1280x720** to match YouTube's recommended thumbnail size.

---

## 4. Architecture (legacy reference)

> **Note:** This section described a separate `cvm_publisher` tool when the pipeline was C++.
> The pipeline is now Python throughout and upload is integrated directly into RivalsVidMaker
> via `src/uploader.py`. The pipeline steps and file structure below are kept as reference only.

### Pipeline per batch

```
Step 1: Scan data/output/ -- find description.txt files not yet uploaded
Step 2: Upload .mp4 (private) via videos.insert -- record videoId
Step 3: Set thumbnail via thumbnails.set
Step 4: Add to playlist via playlistItems.insert
Step 5: Mark as uploaded -- append to uploaded.json
Step 6: Print YouTube Studio URL: https://studio.youtube.com/video/{videoId}/edit
```

### Python dependencies (upload-related)

```
google-api-python-client>=2.100.0   # auth + youtube service object
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=1.0.0
httpx[http2]>=0.27                  # direct HTTP upload (replaces requests)
```

### Getting started with the YouTube API

1. Go to Google Cloud Console, create a project (e.g. "RivalsVidMaker")
2. Enable **YouTube Data API v3** in "APIs & Services > Library"
3. Create OAuth 2.0 credentials: "Desktop app" type
4. Download `client_secret_*.json` into `config/`
5. First run opens browser for consent -- `config/token.json` saved for future runs

**Never commit `client_secret_*.json` or `token.json` to git.**

---

## 5. Summary

| Question | Answer |
|---|---|
| Upload + set private via API? | Yes -- `videos.insert` with `privacyStatus: "private"` |
| Set game to "Marvel Rivals" via API? | No -- set `categoryId=20` + add as tag; set game link manually in Studio |
| Add to existing playlist via API? | Yes -- `playlistItems.insert` with known `playlistId` |
| Set thumbnail via API? | Yes -- `thumbnails.set` after upload |
| OAuth scopes? | `youtube.upload` + `youtube` |
| Quota cost per video? | ~1,750 units; free tier allows ~5 videos/day |
| Which resumable protocol? | Standard (Location header, Content-Range chunks) -- NOT custom (X-Goog-Upload-*) |
| Why not mix the two protocols? | Silent SSL abort mid-transfer -- hardest bug to diagnose |
| HTTP library? | `httpx` with `http2=True` -- streaming generator, no memory load |
| Single-chunk or chunked? | Single-chunk -- no resumability tradeoff is acceptable on stable connection |
| Expected upload speed? | 3-4 MB/s -- YouTube throttles API clients server-side, no client fix exists |
| Thumbnail library? | Pillow; Impact or Bebas Neue font |
