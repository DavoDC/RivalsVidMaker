# Ideas & Future Work

Single source of truth for all pending work.

**Do not ship until SHIPPING BLOCKERS are resolved.**

---

## SHIPPING BLOCKERS

Work that makes the program unusable or unpresentable. Cannot ship without these.

**YouTube upload fails with socket connection abort ([WinError 10053]) - IMPLEMENTATION BUG, NOT NETWORK**

**Status:** CONFIRMED - Network/ISP/Firewall are NOT the issue (browser uploads work fine, proven 2026-05-09 23:00).

**Symptoms:**
- Upload initialization succeeds: POST to https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable returns 200 OK with x-goog-upload-url header
- Response headers include: x-goog-upload-status: active, x-goog-upload-url (correct resumable session URI), x-goog-upload-chunk-granularity: 262144
- First chunk PUT fails mid-transfer with: [WinError 10053] "An established connection was aborted by the software in your host machine" 
- Happens in SSL layer during data transfer (python ssl.py _sslobj.write())
- Retries (3-10 attempts with exponential backoff) all fail identically
- BOTH httplib2 AND requests libraries fail the same way → library agnostic issue

**Investigation (Session 230124, 22:29-23:01 AWST):**
1. Replaced slow google-api-python-client resumable upload (20 Mbps limit) with direct requests/httplib2 (goal: 40-80 MB/s like Chrome)
2. Fixed protocol bug: YouTube uses x-goog-upload-url header, not standard Location header
3. Tried chunk sizes: 10MB, 1MB, 256KB - all fail at first chunk
4. Tried both httplib2 (youtube._http) and requests library - same failure
5. Added retry logic (5-10 attempts) with exponential backoff - no improvement
6. Created isolated test script (test_upload_isolated.py) for standalone debugging
7. User verified: "Just did upload in browser and works fine" → Network/ISP/Firewall are proven OK
8. Commits: 11 total (7cfd047 through 22fabe4)

**Root cause likely (unconfirmed):**
- Content-Range header format incorrect? (currently: "bytes 0-1048575/2515441711")
- Request body encoding issue? (reading file as binary, sending via data= parameter)
- Missing header that browser sends automatically?
- SSL/TLS connection pool management (persistent vs new connection per chunk)?
- youtube._http object has different behavior than standalone requests?
- Authorization header format issue? (using token from token.json directly as "Bearer {token}")

**What works in browser:**
- Chrome/Firefox native upload to YouTube
- Same file (THOR_Mar-Apr_2026_BATCH1.mp4, 2.4GB)
- Same YouTube API endpoint
- Takes 5-10 minutes (vs our code hanging at 1% with retries)

**Next debugging steps:**
1. Compare Content-Range header format between our code and browser network trace
2. Test if issue is specific to file size (try 100MB test file)
3. Try google-api-python-client MediaFileUpload.getbytes() method (different chunking mechanism)
4. Inspect SSL/TLS socket options (timeout, keep-alive, buffer size)
5. Try HTTP/2 vs HTTP/1.1 (requests forces HTTP/1.1)
6. Verify Authorization header is being sent (add logging for actual request headers)
7. Test with curl directly against the resumable session URI
8. Check if token expires during upload (add token refresh logic)

---

**Ellipsis animation broken during KO scanning/fingerprinting**

Progress indicators with "..." animation during KO scan and fingerprinting: cursor moves through positions but the dots stay visible the whole time. Should clear/overwrite previous dots as it cycles. Currently shows accumulated dots instead of animated cycling.

**OAuth prompt shows channel ID instead of channel name**

During OAuth flow, user is asked to "Select the account that owns: UC4xPDj5h-MRmTaa8-xIBfaA". The channel ID is not human-readable. Should query YouTube API during get_authenticated_service() to fetch the channel name and display: "Select the account that owns: [Channel Name] (UC4xPDj5h-MRmTaa8-xIBfaA)" for clarity.

---


## CORE WORKFLOW

Features needed for smooth operation but with workarounds.

---

**Output batch folders don't persist clip metadata**

When a batch is compiled (e.g., THOR_Mar-Apr_2026_BATCH1), the muxed video and description file are created successfully, but the UI dashboard shows "-" for the Clips column because it only counts individual clip files in the folder (unlike Highlights which has 35 individual .mp4 files). Solution: create `batch-metadata.json` in the output folder with the clip list when the batch is compiled, or update the UI to parse the description file's clip section.

Root cause found in logs: 2026-05-09 20:55:11.997 - batch compilation succeeded but UI can't track the 35 source clips that went into it.

---

## POLISH / NICE-TO-HAVE

Visual improvements and quality-of-life features. Non-blocking.

---



**Code duplication analysis**

Scan codebase for: duplicate/similar logic, files over 300 lines, modularity improvements. Do in a dedicated session after the main items above are done and the codebase has stabilised.

Highest-impact files are likely `pipeline.py` (540 lines) and `description_writer.py`.

---

**FFmpeg auto-download test on clean machine** (Manual test for later)

Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts correctly. ~70MB download. Only needed before shipping to a new machine. Manual verification only, not automated.

---

## FUTURE - PHASE 2+

Extra functionality beyond core highlight workflow. Do not start until SHIPPING BLOCKERS + CORE WORKFLOW are solid.

---

**Best-of compilation from Archive**

Extra feature for archive management. Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`.

13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but feature is ready to build.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

---

**Automated tests for KO detection**

pytest tests for `scan_clip` and OCR logic. Prerequisite for confident scaling in OldCompilations Phase 2 (large-file scanning).

Test clip strategy to resolve: commit a very short clip (~5s) as a fixture, or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation.

Tests to write:
- Ground truth clip detects QUAD at correct timestamp
- OCR reads each tier correctly from known crops
- Cache hit/miss behaviour

---

**KO scanner large-file efficiency**

Performance optimization for TIER 4 OldCompilations Phase 2 only. Not needed for current highlight workflow.

Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale.

Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each.

Improvement: after detecting a kill event, skip ahead confidently (banner is ~2s, mandatory 2s cooldown). Also investigate ffmpeg seek-based extraction vs piping all frames for sparse scanning of long videos.

---

**OldCompilations - retrospective Best-of**

Lower priority extra feature. Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.

Location: `C:\Users\David\Videos\MarvelRivals\OldCompilations\`
Playlist: `https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W`

Phase 1 (download) complete - see `docs/HISTORY.md`. 27 videos downloaded (20 compilations, 7 gameplay streams).

**Phase 2 - KO scan** (prerequisite: KO scanner large-file efficiency solved first).

Scan order: compilation videos first (clean, no kill-cam false positives), stream VODs last (up to 4hr/7GB, kill-cam risk - treat results as needing manual verification).

**Phase 3 - Segment extraction:** FFmpeg-cut each Quad+ segment (with padding) into individual clips, output to `ClipArchive/`.

**Phase 4 - Description fetch via YouTube API (low priority):** Fetch each OldCompilations video's YouTube description (manually-entered timestamps + original clip filenames). Save as `<video_stem>_description.txt`. Uses: timestamp validation against KO scanner output, clip reconstruction via transition-counting. Auth reuses `config/token.json`.

---

## See also

- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/HISTORY.md` - completed features, settled design decisions, parked ideas
