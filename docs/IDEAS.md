# Ideas & Future Work

Single source of truth for all pending work.

---

## Current Directive

**Finish items 1-4 in order, minimising token usage per session. Then do a full Thor compilation run through the entire pipeline and publish.**

---

## Pending - ordered by priority (quick wins first)

**1. Fast concat / stream-copy encode**

The pipeline does a straight ffmpeg concat with re-encode (NVENC or libx264) - no transitions, overlays, or filtering. Since all clips are H.264 1920x1080 120fps (confirmed uniform), stream copy (`-c copy`) is viable: skip re-encode entirely and mux clips directly. Potentially 10-50x faster encode. Resolution stored in `.clip.json` (item 4 - unified clip cache) can be used to verify all clips match before attempting stream copy. Audio re-encode (AAC) may still be needed if source audio codec differs.

---

**2. Estimate: add per-stage timing logs** *(small)*

Add timing instrumentation around each pipeline stage: KO scanning, fingerprinting, encoding. Log each stage's actual elapsed time so real data accumulates over runs. Used to validate and refine the composite estimate (item 2).

---

**3. Estimate: composite estimate (KO + fingerprint + encode)** *(medium)*

Replace the single encode-only estimate with a composite: KO scan estimate + fingerprint estimate + encode estimate = overall. Each stage modelled separately. Depends on item 1 being done first to have real per-stage timing data.

---

**4. Unified clip cache (.clip.json) - fingerprint, duration, resolution** *(medium)*

Currently: every run re-fingerprints all clips from scratch (dedup.py), and re-probes duration via ffprobe on every startup (scan_folder + summarize_folder both call probe_duration independently).

Design: single `.clip.json` per clip (replaces `.ko.json`) containing everything we know about it. Cache key: path + mtime + size. Skip unchanged clips on re-run.

Fields to cache:
- **KO result** (tier, timestamp) - migrated from existing `.ko.json`
- **Fingerprint hashes** (N pHash values for dedup)
- **Duration** (seconds) - probe_duration is called on every startup for every clip; caching eliminates all those ffprobe calls
- **Resolution** (width x height) - free from same ffprobe call; useful for filtering wrong-res clips and future features. Confirmed: all clips are 1920x1080 H.264 120fps (Marvel Rivals always saves same format), so resolution unlikely to vary but cheap to store.

Implementation notes:
- Replace `probe_duration` (minimal ffprobe call) with a single wider ffprobe call that fetches duration + resolution in one shot
- Migration: one-off script to read existing `.ko.json` files and write `.clip.json` equivalents, then delete old files
- `ko_detect.py` and `dedup.py` both need updating to read/write the new format

---

## Lower priority / future

*(ordered by size - smaller first)*

**Preprocess: top-level menu + run all cacheable work** *(medium, depends on item 3)*

Preprocess is buried in a submenu. Move it to the top-level menu. When selected, run ALL cacheable work: KO scanning + fingerprinting (item 8). Intended for "going AFK" use. Show overall progress bar across all characters. Text on menu item: "Preprocess all (warm cache)".

---

**Test FFmpeg auto-download on a clean machine**

Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts correctly. ~70MB download. Only needed before shipping to a new machine.

---

**Animated ticker spacing**

Ticker visually appears to alternate between " .." and "..." - looks uneven. Root cause unknown (may be rendering/timing, not the string values). Investigate before fixing.

---

**Code duplication analysis**

Scan codebase for: duplicate/similar logic, files over 300 lines, modularity improvements. Do in a dedicated session after the main items above are done and the codebase has stabilised. Highest-impact files are likely `pipeline.py` (540 lines) and `description_writer.py`.

---

**Automated tests for KO detection**

pytest tests for `scan_clip` and OCR logic. Want KO detection solid before running big scans (OldCompilations, Best-of). Test clip strategy to resolve: commit a very short clip (~5s) as a fixture, or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation. Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier correctly from known crops, cache hit/miss behaviour.

---

**KO scanner large-file efficiency** *(prerequisite for OldCompilations Phase 2)*

Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale.
- Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each
- Improvement: after detecting a kill event, skip ahead confidently (banner is ~2s, mandatory 2s cooldown). Also investigate ffmpeg seek-based extraction vs piping all frames for sparse scanning of long videos.
- Must solve before running OldCompilations Phase 2 on stream VODs.

---

**Best-of compilation from Archive**

Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`. 13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but build the feature ready.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

---

**YouTube API - Phase 2 pipeline integration** *(OAuth confirmed working 2026-04-04)*

See `docs/YOUTUBE_API.md` for full API reference and auth setup notes.

What works (confirmed):
- OAuth flow via `davo29rhino@gmail.com`, `youtube.upload` scope
- Working test script: `scripts/once_off/yt_upload_test.py`
- Credentials: `config/client_secret_*.json` (gitignored), token: `config/token.json` (gitignored)
- Set `OAUTHLIB_RELAX_TOKEN_SCOPE=1` - required when user grants narrower scope than requested in the consent screen
- `youtube.upload` scope alone is sufficient for video upload; full `youtube` scope needed for thumbnails/playlists

Phase 2 implementation plan:
- Add `src/uploader.py` - reuse auth logic from `scripts/once_off/yt_upload_test.py`
- Channel ID check: call `channels.list?part=id&mine=true`, compare against `"youtube_channel_id"` in config.json (target: `UC4xPDj5h-MRmTaa8-xIBfaA` / `@dave369_`). Abort if mismatch.
- Parse title + description from the `_description.txt` file written by `description_writer.py`
- After successful upload, write video ID + URL to state.json so cleanup can link to it
- Hook into `pipeline.py` after encode + describe steps

---

**OldCompilations - retrospective Best-of**

Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.
Location: `C:\Users\David\Videos\MarvelRivals\OldCompilations\`
Playlist: `https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W`

Phase 1 (download) complete - see `docs/HISTORY.md`. 27 videos downloaded (20 compilations, 7 gameplay streams).

**Phase 2 - KO scan** (prerequisite: large-file efficiency solved first, and KO detection tests passing).

Scan order: compilation videos first (clean, no kill-cam false positives), stream VODs last (up to 4hr/7GB, kill-cam risk - treat results as needing manual verification).

**Content inventory (27 videos):**

Compilation videos (20):
- `2025-05-18` THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]
- `2025-08-03` THOR HIGHLIGHTS, MULTIKILLS [JUL+AUG 2025]
- `2025-08-16` THOR HIGHLIGHTS, MULTIKILLS [AUG 2025][Part 1]
- `2025-08-30` THOR HIGHLIGHTS, MULTIKILLS [AUG 2025][Part 2]
- `2025-09-13` THOR HIGHLIGHTS, MULTIKILLS [SEP 2025][Part 1]
- `2025-09-13` THOR HIGHLIGHTS, MULTIKILLS [SEP 2025][Part 2]
- `2025-09-27` THOR HIGHLIGHTS, MULTIKILLS [SEP 2025][Part 3]
- `2025-10-01` THOR UNLEASHED - Relentless Multikills (Sep 2025) Part 4
- `2025-10-13` SQUIRREL GIRL HIGHLIGHTS [AUG-OCT 2025]
- `2025-10-13` THOR HIGHLIGHTS, MULTIKILLS [OCT 2025][Part 1]
- `2025-11-01` THOR HIGHLIGHTS, MULTIKILLS [OCT 2025][Part 2]
- `2025-11-03` SQUIRREL GIRL HIGHLIGHTS [OCT 2025]
- `2025-11-22` THOR HIGHLIGHTS, MULTIKILLS [NOV 2025][Part 1]
- `2025-12-07` SQUIRREL GIRL HIGHLIGHTS [NOV-DEC 2025]
- `2025-12-07` UNSTOPPABLE THOR - Multikill Highlights Nov-Dec 2025
- `2026-01-31` THOR AT PEAK POWER - Multikill Highlights (Jan 2026)
- `2026-01-31` THOR IN FULL CONTROL - Multikill Highlights (Dec 2025)
- `2026-02-14` SQUIRREL GIRL MULTIKILL MONTAGE (Dec 25 - Feb 26)
- `2026-03-17` THOR AWAKENS - Multikill Highlights (Feb 2026) **[already processed - clips saved]**
- `2026-03-17` THOR OVERLOAD - Back-to-Back Multikills (Feb-Mar 2026) **[already processed - clips saved]**

Gameplay stream videos (7, 39min+, up to ~4hr/7GB):
- `2025-08-12` THOR RIVALS GAMEPLAY (13th Aug 2025)
- `2025-09-09` THOR RIVALS GAMEPLAY (9th Sep 2025)
- `2025-09-11` THOR RIVALS GAMEPLAY (11th Sep 2025)
- `2025-09-12` THOR RIVALS GAMEPLAY (12th Sep 2025)
- `2025-09-23` THOR RIVALS GAMEPLAY (23rd Sep 2025)
- `2025-09-27` THOR RIVALS GAMEPLAY (27th Sep 2025)
- `2025-11-09` MARVEL RIVALS Gameplay (1st Nov 2025)

Already-processed: the two 2026-03-17 videos are done (clips saved). Keep as regression tests.

**Phase 3 - Segment extraction:** FFmpeg-cut each Quad+ segment (with padding) into individual clips, output to `ClipArchive/`.

**Phase 4 - Description fetch via YouTube API (low priority):** Fetch each OldCompilations video's YouTube description (manually-entered timestamps + original clip filenames). Save as `<video_stem>_description.txt`. Uses: timestamp validation against KO scanner output, clip reconstruction via transition-counting. Auth reuses `config/token.json`.

---

Settled design decisions and parked ideas are in `docs/HISTORY.md`.

---

## See also
- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/HISTORY.md` - completed features, settled design decisions, parked ideas
