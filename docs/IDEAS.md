# Ideas & Future Work

Single source of truth for all pending work.

**Do not move to next tier until current tier is verified on real data.**

---

## TIER 0 (BLOCKING)

Work that blocks core functionality. Program cannot ship without these.

---

**YouTube API Phase 2 pipeline integration**

OAuth confirmed working (2026-04-04). This automates the core workflow (upload clips to YouTube).

What works (confirmed):
- OAuth flow via `davo29rhino@gmail.com`, `youtube.upload` scope
- Working test script: `scripts/once_off/yt_upload_test.py`
- Credentials: `config/client_secret_*.json` (gitignored), token: `config/token.json` (gitignored)
- Set `OAUTHLIB_RELAX_TOKEN_SCOPE=1` - required when user grants narrower scope than requested
- `youtube.upload` scope alone is sufficient for video upload

Phase 2 implementation plan:
- Add `src/uploader.py` - reuse auth logic from `scripts/once_off/yt_upload_test.py`
- Channel ID check: call `channels.list?part=id&mine=true`, compare against `"youtube_channel_id"` in config.json (target: `UC4xPDj5h-MRmTaa8-xIBfaA` / `@dave369_`). Abort if mismatch.
- Parse title + description from the `_description.txt` file written by `description_writer.py`
- After successful upload, write video ID + URL to state.json so cleanup can link to it
- Hook into `pipeline.py` after encode + describe steps

Reference: See `docs/YOUTUBE_API.md` for full API reference and auth setup notes.

---

**Automated tests for KO detection**

pytest tests for `scan_clip` and OCR logic. Needed BEFORE large-scale KO work (OldCompilations, etc.).

Test clip strategy to resolve: commit a very short clip (~5s) as a fixture, or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation.

Tests to write:
- Ground truth clip detects QUAD at correct timestamp
- OCR reads each tier correctly from known crops
- Cache hit/miss behaviour

---

## TIER 1 (MVP)

Features that improve core workflow. High user impact, ready to start.

---

**Preprocess: top-level menu + run all cacheable work**

Preprocess is buried in a submenu. Move it to the top-level menu. When selected, run ALL cacheable work: KO scanning + fingerprinting. Intended for "going AFK" use. Show overall progress bar across all characters. Text on menu item: "Preprocess all (warm cache)".

Status: Medium complexity. Depends on KO detection tests being solid.

---

## TIER 2 (QUALITY)

Refactoring, perf, and polish on core workflow.

---

**Animated ticker spacing**

Ticker visually appears to alternate between " .." and "..." - looks uneven. Root cause unknown (may be rendering/timing, not the string values). Investigate before fixing.

---

## TIER 3 (POLISH)

Cosmetic improvements, documentation, nice-to-haves.

---

**Code duplication analysis**

Scan codebase for: duplicate/similar logic, files over 300 lines, modularity improvements. Do in a dedicated session after the main items above are done and the codebase has stabilised.

Highest-impact files are likely `pipeline.py` (540 lines) and `description_writer.py`.

---

**FFmpeg auto-download test on clean machine**

Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts correctly. ~70MB download. Only needed before shipping to a new machine.

---

## TIER 4 (FUTURE)

Extra functionality, nice-to-have, lower priority. Do not start until TIER 0-2 are solid.

---

**Best-of compilation from Archive**

Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`.

13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but feature is ready to build.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

---

**KO scanner large-file efficiency**

Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale.

Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each.

Improvement: after detecting a kill event, skip ahead confidently (banner is ~2s, mandatory 2s cooldown). Also investigate ffmpeg seek-based extraction vs piping all frames for sparse scanning of long videos.

Note: This is ONLY needed for OldCompilations Phase 2 (scanning 4hr+ VODs). Not required for current highlight workflow.

---

**OldCompilations - retrospective Best-of**

Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.

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
