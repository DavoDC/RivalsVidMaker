# Ideas & Future Work

Single source of truth for all pending work.

## See also
- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/MANUAL_TESTING.md` - end-to-end testing steps
- `docs/DONE.md` - completed features (moved here to keep this file clean)

---

## Pending - ordered by priority

### Quick wins (do first)

1. **Rename clips at KO scan stage** - currently clips are renamed with KO tier when moved to `Output\clips\`. Move the rename earlier: at KO scan time (including pre-process mode - if pre-process runs, use cache to rename clips in Highlights immediately). Names then available for description writing and archiving. Clip archiving must use already-renamed clips (read from cache, never re-scan). Archiving should never need to run KO detection.

2. **Test on a different character** - check Squirrel Girl clips after item 1: verify KO tiers look correct on the renamed filenames. Fairly confident detection already works character-agnostically (different banner colour/UI skin) but this confirms it cheaply.

3. **Auto-download FFmpeg if missing** - on startup, check whether `ffmpeg.exe` / `ffprobe.exe` exist at the configured path. If not, download and extract the latest FFmpeg Windows build automatically (same pattern as `SBS_Downloader`). No manual setup for new machines.

### Main work

4. **Dry-run mode** - `--dry-run` flag for the full pipeline. Prints everything the pipeline would do without moving files or running FFmpeg. Useful for previewing batches and checking KO detection results before committing.

5. **Clip transition trimming** - each clip ends with ~5s "hammer icon + black screen" (game-appended ending). In a compilation these stack up and hurt watch time. Trim the tail of each clip before concatenation, but keep a short gap (don't remove entirely). Requires frame analysis to find the transition start reliably.

6. **YouTube API / upload automation** - automate the full YouTube upload. See `docs/YOUTUBE_API.md` for existing API research. Scope: compile video, then upload directly to YouTube as **private** (user reviews and makes public manually), with title/description/tags set from the AI-generated prompt file. Confirm upload written to state.json. Goal: zero manual steps from clips to a private YouTube draft ready to publish.

7. **Test end-to-end with Thor** - 31 clips ready, all KO-cached as of 2026-03-28. Full pipeline test covering all of the above: sort -> scan -> clip rename -> transition trim -> compile -> describe -> YouTube upload (private). This is the integration test for items 1-6.

---

## Lower priority / future

### Best-of compilation from Archive
Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`. 13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but build the feature ready.

**Archive clip lifecycle (decided):**
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/` so they are not re-compiled into future Best-of videos.
- `ClipArchive/THOR/` (root) = pending clips, not yet in any Best-of video.
- `ClipArchive/THOR/compiled/` = clips already used in a Best-of, kept forever but excluded from future compiles.
- The compiled Best-of video itself goes through the normal Output + cleanup flow (published to YT, then video deleted, clips stay in compiled/).
- Archive display table should show pending vs compiled counts separately.

### Automated tests for KO detection
pytest tests for `scan_clip` and OCR logic. Test clip strategy to resolve: commit a very short clip (~5s) as a fixture (CI-friendly but binary in git), or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation. Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier correctly from known crops, cache hit/miss behaviour.

### Decompile folder (4th folder) - retrospective Best-of
A fourth folder alongside Highlights/Output/Archive. Use yt-dlp to download previously uploaded compilation videos (max quality, 720p/1080p), scan for Quad+ kills, extract those segments as clips, then feed into the Archive -> Best-of pipeline. Goal: "Best of 2024" / "Best of 2025" retrospective videos. Split into parts if over 15 min.

### Time estimation before encode
Before starting a batch, show a rough estimate broken into stages: KO scanning (~3-9s per uncached clip, instant if cached), encoding (~1x realtime for NVENC). Shown after menu selection, before processing begins.

---

## Design decisions (settled)

**Slug always includes batch number** - output folders always use `_BATCH1`, `_BATCH2` etc. even when compiling one at a time. Safer to always have a unique, predictable name than to special-case the first batch.

**One batch at a time** - the pipeline always compiles the first batch only. Re-run for subsequent batches. Rationale: clips no longer build up to 30-min backlogs now that the process is automated. Multi-batch prompt removed 2026-03-28.

**State-driven pipeline** - parked indefinitely. The current system's implicit state (clips in Highlights = uncompiled, output folder exists = compiled) is sufficient. The one genuine benefit (multi-batch flow) is solved by the one-at-a-time approach above.

---

## Parked: state-driven pipeline (major redesign)

Full redesign spec kept here for reference. Not being pursued - parked indefinitely (see design decision above).

### Concept
Replace the current linear pipeline with a stage-aware model where the program tracks which stage each clip/batch is in and only progresses clips forward when the user confirms. Stages:

```
intake -> KO detection -> (batch) selection -> compilation -> cleanup
```

On startup, the program scans all three video folders and displays a status table showing every character group and what state their clips are in. The user selects which stage to advance, rather than the program running the whole pipeline automatically.

**Safety and idempotency requirements:**
- Safe to re-run without duplicating work or re-processing already-handled clips.
- Dry-run mode for all destructive actions.
- Explicit user confirmation required before any deletion or file move.
- Partial failure resilience: if interrupted mid-stage, re-running must pick up from the last safe checkpoint.

**Partially implemented:**
- `src/state.py` + `data/state.json` - tracks `youtube_confirmed` per output folder. Load/save/mark/query fully tested.
- `data/cache/` - caching layer complete (see `docs/DONE.md`).
- `_print_multizone_status()` - startup display complete.
- `src/cleanup.py` - cleanup workflow skeleton complete.

**Still needed if ever resumed:** clip-level state (which clips belong to which batch, KO tier per clip).
