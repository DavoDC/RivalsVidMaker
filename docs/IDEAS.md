# Ideas & Future Work

Single source of truth for all pending work.

## See also
- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/HISTORY.md` - completed features, settled design decisions, parked ideas

---

## Pending - ordered by priority

### Bugs / correctness issues (fix before shipping)

**BUG: protect_recent_clips applied to character subfolders (WRONG)**

`preprocess.py` applies the `protect_recent_clips` guard to every character subfolder (THOR, SQUIRREL_GIRL, etc.). This is wrong - protection should only apply to the `Highlights\` ROOT folder. That's the only folder the in-game save UI writes to; clips in character subfolders have already been sorted and are safe to process without restriction.

Symptom: if SQUIRREL_GIRL has exactly 5 clips, `clips[:-5]` = empty - all 5 are "protected" and nothing gets scanned/renamed. With THOR having more clips, the last 5 are silently skipped.

Fix: remove the `protect_recent_clips` slicing from `preprocess_all()` entirely. Pre-process scans character subfolders only - protection is irrelevant there. (Protection logic, if it is ever needed, belongs in the root-folder clip sorter, not in preprocess.)


---

### Quick wins (do first)

1. **Test on a different character** - run pre-process on Squirrel Girl clips and verify KO tiers look correct on the renamed filenames (e.g. `SQUIRREL_GIRL_..._QUAD.mp4`). Fairly confident detection works character-agnostically but this confirms it cheaply.

### Main work

2. **Dry-run mode** - `--dry-run` flag for the full pipeline. Prints everything the pipeline would do without moving files or running FFmpeg. Useful for previewing batches and checking KO detection results before committing.

3. **Clip transition trimming** - each clip ends with ~5s "hammer icon + black screen" (game-appended ending). In a compilation these stack up and hurt watch time. Trim the tail of each clip before concatenation, but keep a short gap (don't remove entirely). Requires frame analysis to find the transition start reliably.

4. **YouTube API / upload automation** - automate the full YouTube upload. See `docs/YOUTUBE_API.md` for existing API research.

   **Phase 1 (feasibility probe - do first, standalone script):** Write the smallest possible standalone script (`scripts/yt_upload_test.py`) that authenticates via OAuth and uploads a single hardcoded clip as **private** to confirm the API actually works. Small channels may not have upload quota or the right API access tier - verify this before building anything else. Success = a private video appears on the channel.

   **Phase 2 (pipeline integration - only if Phase 1 works):** Compile video -> upload as private (title/description/tags from the AI prompt file) -> record upload URL in state.json. Goal: zero manual steps from clips to a private YouTube draft ready to publish.

5. **Test end-to-end with Thor** - 31 clips ready, all KO-cached as of 2026-03-28. Full pipeline test: sort -> scan -> clip rename -> transition trim -> compile -> describe -> YouTube upload (private). Integration test for items 1-4. Run items 3 (transition trimming) and 4 (YouTube API Phase 1) first - these are prerequisites for a clean end-to-end test.

---

## Lower priority / future

### Quick wins

### README improvements (2 items)
- **OCR/KO scan section** - the OCR multi-kill detection is the most technically interesting part of the project. Add a dedicated README section explaining how it works: frame extraction at 2fps, banner crop region, Tesseract OCR, tier detection, cooldown logic. Technical but concise - not a wall of text.
- **Pipeline and folder structure** - README should explain the full end-to-end flow and what each folder contains (Highlights, Output, ClipArchive). Currently lives only in CLAUDE.md.

### Test FFmpeg auto-download on a clean machine
Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts the binaries correctly. ~70MB download. Only needed before shipping to a new machine.

---

### Time estimation before encode (with data-driven model)

Before starting a batch, show a rough estimate broken into stages: KO scanning (instant if cached, else estimate from clip length), encoding (~1x realtime for NVENC). Shown after menu selection, before processing begins.

**Data-driven approach:** save timing data to each `.ko.json` cache entry: clip duration (seconds) + actual scan time (seconds). Over time this builds a dataset of `(clip_length, scan_time)` pairs. Use a simple linear model from past runs to predict future scan times. Far more accurate than hardcoded constants.

Two separate predictions needed:
1. **KO scan time** - per-clip, based on clip length. Instant if cached.
2. **Encode/compile time** - per-batch, based on total clip duration. Different model (GPU vs CPU).

Add the timing fields to the `.ko.json` schema now so data accumulates from the start, even before the estimation UI is built.

### Automated tests for KO detection
pytest tests for `scan_clip` and OCR logic. Want KO detection solid and well-tested before running big scans (OldCompilations, Best-of). Test clip strategy to resolve: commit a very short clip (~5s) as a fixture (CI-friendly but binary in git), or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation. Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier correctly from known crops, cache hit/miss behaviour.

---

### Best-of compilation from Archive
Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`. 13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but build the feature ready.

> **Related:** OldCompilations (below) feeds directly into this - decompiling old uploaded videos is the main way to fill ClipArchive with pre-2026 kills.

**Archive clip lifecycle (decided):**
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/` so they are not re-compiled into future Best-of videos.
- `ClipArchive/THOR/` (root) = pending clips, not yet in any Best-of video.
- `ClipArchive/THOR/compiled/` = clips already used in a Best-of, kept forever but excluded from future compiles.
- The compiled Best-of video itself goes through the normal Output + cleanup flow (published to YT, then video deleted, clips stay in compiled/).
- Archive display table should show pending vs compiled counts separately.

### OldCompilations - retrospective Best-of
Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.
Location: `C:\Users\David\Videos\MarvelRivals\OldCompilations\`
Playlist: `https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W`

> **Related:** This feeds the Best-of compilation above - extracted Quad+ segments land in ClipArchive and become source material for Best-of videos.

Phase 1 (download) complete - see `docs/HISTORY.md`. 27 videos downloaded (20 compilations, 7 gameplay streams).

**Next: Phase 2 - KO scan** (prerequisite: solve large-file efficiency below first, and have solid automated KO detection tests passing).

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

Gameplay stream videos (7, 39min+, up to ~4hr/7GB - full session recordings, not clip compilations):
- `2025-08-12` THOR RIVALS GAMEPLAY (13th Aug 2025)
- `2025-09-09` THOR RIVALS GAMEPLAY (9th Sep 2025)
- `2025-09-11` THOR RIVALS GAMEPLAY (11th Sep 2025)
- `2025-09-12` THOR RIVALS GAMEPLAY (12th Sep 2025)
- `2025-09-23` THOR RIVALS GAMEPLAY (23rd Sep 2025)
- `2025-09-27` THOR RIVALS GAMEPLAY (27th Sep 2025)
- `2025-11-09` MARVEL RIVALS Gameplay (1st Nov 2025)

**Already-processed:** The two 2026-03-17 videos are done (clips saved). Keep in place as regression tests (known KO timestamps to verify scanner against).

**Phase 2 - KO scan:** Run `ko_detect.py` against all OldCompilations videos. Both compilations and gameplay streams should be scanned - gameplay streams will also contain Quad+ kills.

**Kill-cam false positives (stream VODs only):** During Phase 2, stream VODs require extra care. When the player dies, the game shows the killer's POV during respawn - their KO banners appear in the same screen region and will be detected as the player's kills. Compilation videos are not affected (always the player's own clips). For stream VODs, treat scan results as needing manual verification. Potential automated fix: detect "Spectating [name]" UI element in frame and suppress KO detection during that window.

**KO scanner large-file efficiency (must solve before Phase 2):** Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale. The scanner must be efficient enough to handle these without taking hours.
- Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each
- Improvement needed: the banner only appears for ~2s and has a mandatory 2s cooldown - so after detecting a kill event, skip ahead confidently. Also consider: only sample the banner crop region (already done), but investigate whether ffmpeg seek-based extraction (not piping all frames) would be faster for sparse scanning of long videos.
- This is a prerequisite for Phase 2 - don't scan large files until this is solved.

**Phase 3 - Segment extraction:** FFmpeg-cut each Quad+ segment (with padding) into individual clips, output to `ClipArchive/` pending Best-of compilation.

**Phase 4 - Description fetch via YouTube API (low priority):** Each OldCompilations video has a YouTube description containing manually-entered timestamps and a list of the original clip filenames that contributed. Fetch these descriptions via the YouTube Data API and save as `<video_stem>_description.txt` alongside the video file.

Uses:
- **Timestamp validation:** Compare KO scanner output against the manually-entered timestamps in the description. Not a strict test (human timestamps may be wrong or missing) - treat as a rough sanity check. Trust the scanner if it disagrees.
- **Clip reconstruction:** Descriptions list original clip filenames in order. Combined with transition-counting (count the black-screen transitions in the compiled video), you can reconstruct which clip maps to which segment - giving a clip order list that links back to the original filenames. This is difficult because clips vary in length, but transition detection makes it tractable.

Note: YouTube API auth setup (OAuth) overlaps with the higher-priority upload automation (item 4). Auth work done for item 4 can be reused here - no point doing it twice.

**Duplicate clip detection (also relevant to Phase 4):** Gameplay streams are full session recordings and may contain footage that also appears in compilation videos, resulting in duplicate extracted clips. Also relevant to the main pipeline: before compiling, check that no clip is a near-duplicate of another in the same batch.

Approach: perceptual hashing of keyframes gives each clip a fingerprint. Compare fingerprints across clips; high similarity = likely duplicate. Exact match threshold to be determined empirically.

Two use cases:
1. **OldCompilations dedup:** after Phase 3 segment extraction, check extracted clips against each other and against existing ClipArchive clips. Flag duplicates before archiving.
2. **Main pipeline dedup:** before encoding a batch, check for near-duplicate clips within the batch (e.g. same kill captured twice). Warn and let user decide whether to exclude.

Implementation note: `imagehash` library (perceptual hash) or frame-level DCT hash via ffmpeg/Pillow. No heavy ML needed.

---

Settled design decisions and parked ideas are in `docs/HISTORY.md`.
