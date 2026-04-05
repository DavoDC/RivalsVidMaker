# Ideas & Future Work

Single source of truth for all pending work.

---

## Pending - ordered by priority

**1. End-to-end test - Thor Batch1** *(in progress)*

Dr Strange: DONE (2026-04-05).

Thor (in progress): 56 clips ready (48/56 KO-cached). Batch1 compiled and described. Remaining steps: upload to YouTube, confirm live, run cleanup (archive Quad+ to ClipArchive, delete rest).

Note: Batch1 included two KO-tier clips that probably shouldn't have been there (see item 2). Decision on whether to redo is part of item 2 - complete upload as-is for now unless item 2 decision says otherwise.

---

**2. KO/NONE clips: compile-time filter**

Thor Batch1 included `THOR_2026-03-17_22-20-29_NONE_KO.mp4` and `THOR_2026-03-22_23-19-10_KO.mp4`. Root cause: preprocess prompts user to delete KO/NONE clips, but if user says N (or skips preprocess), they stay in Highlights and get included - there is no compile-time guard.

Fix design: before encoding, warn if the batch contains any clip with a `_KO` or `_NONE` suffix and prompt: "X clip(s) are KO/NONE-tier (low value). Remove from batch? [y/N]". If Y, drop them and recheck batch length. If N, proceed. Silently filtering is wrong - user keeps control.

**Retroactive undo question:** should Thor Batch1 be re-run without those two clips? This is the user's call. Ask before doing anything.

---

**3. Estimate accuracy: NVENC encode multiplier**

Thor Batch1 example: estimated 6m10s, actual 2m50s. The encode estimate uses `total_dur * 0.4` (tuned for CPU). NVENC (GPU) encodes at ~0.10-0.15x real-time. Fix: call `encoder.check_nvenc()` at estimate time - if True use 0.15x, else 0.40x. Quick change in `pipeline._estimate_seconds`.

---

**4. Fingerprint/duration caching**

Every run re-fingerprints all clips for dedup checking from scratch. Add per-clip fingerprint cache alongside `.ko.json` (keyed on path + mtime + size). Skip unchanged clips on re-run. Biggest win for large character folders (56+ clips). Prerequisite: design cache key format and invalidation rule.

---

**5. Preprocess: top-level menu, all cacheable work**

Preprocess is buried in a submenu. Move it to the top-level menu. When selected, run ALL cacheable work: KO scanning + fingerprinting (item 4). Intended for "going AFK" use. Show overall progress bar across all characters. Text on menu item: "Preprocess all (warm cache)".

---

**6. Timestamps format**

Current format `0:34 - 0:40 = Quad Kill` is described as "a bit weird for a YT desc". Standard YouTube chapter format is `0:34 Quad Kill`. Needs a decision: are timestamps for the description body or a pinned comment? Once decided, update `description_writer._timestamps` to match. Also check whether the `Format: ...` header line is needed in the .txt file or can be dropped.

---

**7. Description: Marvel voicelines / character phrases**

Current description prompt asks for a generic one-liner. Goal: character-specific Marvel comic quotes and in-game voicelines woven in. Two paths: (a) manually curate a voiceline list per character in a config JSON (low-tech, good enough for now), or (b) use YouTube API Phase 4 to fetch descriptions from OldCompilations so the prompt can learn from past examples. Path (a) can be done immediately; path (b) ties into OldCompilations work below. Implement (a) first.

---

**8. Code duplication analysis**

Scan codebase for: duplicate/similar logic, files over 300 lines, modularity improvements. Do in a dedicated session after items 2-5 are done and the codebase has stabilised. Highest-impact files are likely `pipeline.py` (540 lines) and `description_writer.py`.

---

## Lower priority / future

**L1. YouTube API - Phase 2 pipeline integration** *(OAuth confirmed working 2026-04-04)*

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

**L2. Automated tests for KO detection**

pytest tests for `scan_clip` and OCR logic. Want KO detection solid before running big scans (OldCompilations, Best-of). Test clip strategy to resolve: commit a very short clip (~5s) as a fixture, or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation. Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier correctly from known crops, cache hit/miss behaviour.

---

**L3. KO scanner large-file efficiency** *(prerequisite for OldCompilations Phase 2)*

Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale.
- Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each
- Improvement: after detecting a kill event, skip ahead confidently (banner is ~2s, mandatory 2s cooldown). Also investigate ffmpeg seek-based extraction vs piping all frames for sparse scanning of long videos.
- Must solve before running OldCompilations Phase 2 on stream VODs.

---

**L4. OldCompilations - retrospective Best-of**

Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.
Location: `C:\Users\David\Videos\MarvelRivals\OldCompilations\`
Playlist: `https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W`

Phase 1 (download) complete - see `docs/HISTORY.md`. 27 videos downloaded (20 compilations, 7 gameplay streams).

**Phase 2 - KO scan** (prerequisite: L3 large-file efficiency solved first, and L2 KO tests passing).

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

**L5. Best-of compilation from Archive**

Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`. 13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but build the feature ready.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

---

**L6. Test FFmpeg auto-download on a clean machine**

Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts correctly. ~70MB download. Only needed before shipping to a new machine.

---

**L7. Animated ticker spacing**

Ticker visually appears to alternate between " .." and "..." - looks uneven. Root cause unknown (may be rendering/timing, not the string values). Investigate before fixing.

---

**L8. Compilation length tolerance when clips are deleted**

When KO/NONE clips are deleted during preprocessing, the remaining batch may fall below `min_batch_seconds`. Current behaviour: pipeline aborts. Decided: acceptable to publish a shorter video. Consider lowering `min_batch_seconds` or adding a `--allow-short` flag.

---

Settled design decisions and parked ideas are in `docs/HISTORY.md`.

---

## See also
- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/HISTORY.md` - completed features, settled design decisions, parked ideas
