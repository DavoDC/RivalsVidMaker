# Ideas & Future Work

Single source of truth for all pending work.

**Do not ship until SHIPPING BLOCKERS are resolved.**

---

## SHIPPING BLOCKERS

Work that makes the program unusable or unpresentable. Cannot ship without these.

**OAuth prompt shows channel ID instead of channel name**

During OAuth flow, user is asked to "Select the account that owns: UC4xPDj5h-MRmTaa8-xIBfaA". The channel ID is not human-readable. Currently shows the expected channel ID for context (Session 242), but needs human-readable channel name fetched from YouTube API during get_authenticated_service(). Display format: "Select the account that owns: [Channel Name] (UC4xPDj5h-MRmTaa8-xIBfaA)" for clarity. Prevents accidental upload to wrong channel on multi-account systems.

---


## CORE WORKFLOW

Features needed for smooth operation but with workarounds.

---

**Output batch folders don't persist clip metadata**

When a batch is compiled (e.g., THOR_Mar-Apr_2026_BATCH1), the muxed video + description file are created, but the UI dashboard shows "-" for the Clips column because it can't see the individual clips that went into the batch. The description file DOES contain the clip list (as timestamped segments), but the UI doesn't parse it.

**Solution:** Either (a) create `batch-metadata.json` in output folder with clip list when batch compiles, or (b) update UI to parse description file's clip section and extract clip count. Table must show accurate/correct counts.

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

**Best-of compilation from Archive** (tied to OldCompilations workflow)

Extra feature for archive management. Archive submenu offers "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

Status: 13 THOR Quad+ clips currently in archive (6m 11s) - accumulating, ready to build when OldCompilations Phase 2 is underway.

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
