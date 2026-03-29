# Ideas & Future Work

This is the single source of truth for all pending work. CLAUDE.md "Next steps" has been removed in favour of this file.

## Pending - ordered by priority

1. **Clip transition trimming** - each clip ends with ~5s "hammer icon + black screen" (game-appended ending). In a compilation these stack up and hurt watch time. Trim the tail of each clip before concatenation, but keep a short gap (don't remove entirely). Requires frame analysis to find the transition start reliably.
2. **YouTube API / upload automation** - automate the stages involving YouTube upload. See `docs/YOUTUBE_API.md` for existing API research. Covers: upload compiled video, set title/description/tags from the AI-generated prompt, confirm upload in state.json.
3. **Rename clips at KO scan stage** (not compile stage) - currently clips are renamed with KO tier when moved to `Output\clips\`. Move the rename earlier: do it at KO scan time so names are available for description writing and archiving. Clip archiving must use already-renamed clips (add from cache, never re-scan). Archiving should never need to run KO detection.
4. **Test end-to-end with Thor** - 31 clips ready (all KO-cached as of 2026-03-28). Compile THOR, verify full sort -> scan -> compile -> describe -> move clips flow. Do transition trimming (item 1) first.
5. **Best-of compilation from Archive** - Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`. 13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but build the feature ready.

   **Archive clip lifecycle (decided):**
   - Archive clips are NEVER deleted - permanent record of best kills.
   - After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/` so they are not re-compiled into future Best-of videos.
   - `ClipArchive/THOR/` (root) = pending clips, not yet in any Best-of video.
   - `ClipArchive/THOR/compiled/` = clips already used in a Best-of, kept forever but excluded from future compiles.
   - The compiled Best-of video itself goes through the normal Output + cleanup flow (published to YT, then video deleted, clips stay in compiled/).
   - Archive display table should show pending vs compiled counts separately.
3. **Fix multi-batch slug numbering** - `_BATCH1` suffix is unnecessary when always compiling one batch at a time. Only add suffix if a previous output folder for that character/date already exists.
4. **Dry-run mode** - `--dry-run` flag for the full pipeline (preview without moving files).

## Design decisions (settled)

**One batch at a time** - the pipeline always compiles the first batch only. Re-run for subsequent batches. Clips not in the first batch stay in Highlights until the next run. Rationale: clips no longer build up to 30-min backlogs now that the process is automated. Previously they built up because the manual workflow was slow. Multi-batch prompt removed 2026-03-28.

**State-driven pipeline** - parked indefinitely. The current system's implicit state (clips in Highlights = uncompiled, output folder exists = compiled) is sufficient. The one genuine benefit (multi-batch flow) is solved by the one-at-a-time approach above.

---

## Architecture: state-driven pipeline (major redesign)

### State-driven pipeline with clear stages
Replace the current linear run-once pipeline with a stage-aware model where the program
tracks which stage each clip/batch is in and only progresses clips forward when the user
confirms. Stages:

```
intake → KO detection → (batch) selection → compilation → cleanup
```

On startup, the program scans all three video folders and displays a clear status table
showing every character group and what state their clips are in — how many are uncompiled,
what batches are pending, what Output folders exist and whether they've been confirmed on
YouTube. The user then selects which stage to advance, rather than the program running the
whole pipeline automatically.

**Safety and idempotency requirements:**
- Safe to re-run without duplicating work or re-processing already-handled clips.
- Dry-run mode for all destructive actions (any deletion or move that can't be undone).
- Explicit user confirmation required before any deletion or file move — list every file
  that will be affected before proceeding.
- Partial failure resilience: if the program is interrupted mid-stage (e.g. encode crashes),
  re-running must pick up from the last safe checkpoint, not restart from scratch.

### ~~State log (JSON) - folder-level~~ ✅ DONE (partial)
`src/state.py` + `data/state.json` (gitignored, machine-local).
Tracks `youtube_confirmed` per output folder. Used by OUTPUT FOLDER display (YT? column,
Next Action column) and gates --cleanup (asks "Is this live on YouTube?" on first run,
saves answer). Load/save/mark/query functions fully tested.

Still needed: clip-level state (which clips belong to which batch, KO tier per clip).
This will be part of the full state-driven pipeline below.

### ~~Caching layer (persistent, keyed, invalidation-aware)~~ ✅ DONE
Cache results stored in `data/cache/<char>/<YYYY-MM>/<stem>.ko.json` keyed by
`(filename, file_mtime)`. On re-run, stale entries (mtime mismatch) are re-scanned.
Null = "scanned, no kill found" — valid result, not a missing entry.

### ~~Startup state display~~ ✅ DONE
`_print_multizone_status()` in `pipeline.py` shows all three folders (Highlights,
Output, Archive) in separate tables on launch.

### ~~Output folder cleanup workflow~~ ✅ DONE (skeleton)
`src/cleanup.py` — interactive cleanup with dry_run=True support. Lists clips with KO
tiers, proposes Quad+ → ClipArchive moves and remaining clip deletion, asks per-action
confirmation. Not yet wired into the main menu.

### ~~Clip KO-tier rename at compilation stage~~ ✅ DONE
`_move_clips()` in `pipeline.py` renames clips on move:
`THOR_2026-03-16_22-18-00.mp4 → THOR_2026-03-16_22-18-00_QUAD.mp4`.
Legacy vid1/vid2 clips still need a one-off migration pass (see Deferred section).

## High-priority / structural

### ~~Protect 5 most-recent clips from batching/moving~~ ✅ DONE
Both `sort_clips()` and `scan_folder()` accept `protect_recent=N`. The N most recently
saved clips (last N alphabetically = chronological for timestamp filenames) are skipped
by the sort step and never moved out of `Highlights\`. Default N=5, matches the game's
buffer size. Log line says "X moved. (N kept unsorted - protected)".
Config key: `protect_recent_clips`. Integration test in `tests/test_integration.py`.



### ~~Consolidate docs/ folder~~ ✅ DONE
`docs/` is now 4 files: `MULTIKILL_DETECTION.md`, `YOUTUBE_API.md`, `YOUTUBE_TITLE_AND_DESC.md`, `IDEAS.md`.

### ~~Reorganise repo structure~~ ✅ DONE
C++ removed, Python pipeline in `src/`, `tests/`, `scripts/`, `config/`, `.gitkeep` in `tools/`, clean `.gitignore`. `tools/` kept as-is rather than renamed to `dependencies/`.

### ~~Rewrite pipeline in Python~~ ✅ DONE
All pipeline stages (encoder, batcher, clip list, description writer) are in Python
alongside `ko_detect.py` in `src/`. C++ removed entirely.

### ~~Pre-process mode: KO scan all clips upfront~~ ✅ DONE
New `src/preprocess.py` module + `[P]` option in the main menu. Scans all clips
across all character folders, writes cache entries, and reports progress. Does
not batch, encode, or move any files.

### Run KO detection at clip-ingest stage
Currently detection runs at batch time. Running it earlier (when clips first land) allows
all clips to be processed in parallel, and results are ready before batching begins.
Encode KO info into the clip filename (see below) at this stage.

### ~~Encode KO tier in clip filename~~ → see Architecture section above
Detailed design moved to "Clip KO-tier rename at compilation stage" in the Architecture
section. Key decision: rename happens when clips move to `Output\clips\`, not in Highlights.

### ~~Skip-if-exists for encoding~~ ✅ DONE
`encode()` in `src/encoder.py` checks if the output `.mp4` exists before running FFmpeg.
If it does, logs WARNING and returns the existing path. Pass `force_encode=True` to
re-encode. Pipeline menu mentions `--force` option.

### Dry-run mode
A `--dry-run` flag that prints everything the pipeline *would* do without
moving any files or running FFmpeg. Useful for:
- Previewing which clips will go into each batch before committing.
- Checking that KO detection results are sensible before encoding.
- Safe to run in any state — no files are touched.

### ~~Cleanup command (post-YouTube workflow)~~ ✅ DONE (skeleton)
`src/cleanup.py` — see Architecture section above.

### Session history in startup display
In the Output table, add a "Days since encoded" column derived from the folder's
modification time. Lets you see at a glance which output folders are old and
ready to be cleaned up vs recently created.

### Startup clip availability check + video recommendations
On launch, scan the highlights folder, group clips by character, tally total duration per group,
and recommend compilations that can be made (e.g. "15-min Thor vid: 30 clips available").
If no character has enough clips for a full video, say so explicitly.
User selects a recommendation (or dismisses if nothing is ready).
This replaces the current manual "pick a batch folder" step.

### Full automation: generate video + title + description from clips
The ideal end state for this program: point it at a folder of clips and it outputs a ready-to-paste
YouTube upload — compiled video, title, description, and timestamps — with zero manual work.
Currently the description and title are written by hand after running the script.
Reference format: `docs/YOUTUBE_TITLE_AND_DESC.md`.

### ~~AI prompt generation for title & description~~ ✅ DONE
`src/ai_prompt.py` — writes `data/output/<slug>/<slug>_ai_prompts.md` after each
pipeline run. Includes character/clip count/date range/kill tier context and pre-filled
prompts (title, one-liner, and combined) following the canonical format in
`docs/YOUTUBE_TITLE_AND_DESC.md`. Wired into `pipeline.py` after description writing.

### ~~Show KO tier in HIGHLIGHTS list~~ ✅ DONE
`write_description()` now accepts `clip_tiers` and annotates each clip line:
`6. THOR_2026-02-21_20-47-21.mp4 [HEXA]`

### ~~Document full pipeline end-to-end~~ ✅ DONE
CLAUDE.md documents the complete workflow: clip ingest → sort → KO detection →
batching → encode → description. `docs/MANUAL_TESTING.md` covers end-to-end
testing steps.

### Test on a different character
Run the full pipeline on a fresh batch of clips for a non-Thor character (e.g. Squirrel Girl)
to confirm detection works character-agnostically — different banner colour, different UI skin.
Good regression check before expanding beyond Thor.

### Automated tests for KO detection
Add a `tests/` folder with pytest tests covering `scan_clip` and OCR logic. Key questions to resolve:
- **Test clip strategy:** do we commit a very short clip (~5s) to the repo as a fixture?
  Pros: fully self-contained, CI-friendly. Cons: binary in git, repo size.
  Alternative: a tiny synthetic test image of the banner crop (just a PNG, ~50KB) to test
  OCR in isolation without needing a real video file.
- Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier
  correctly from known crop images, cache hit/miss behaviour, range format output.

---

## Lower priority / future

### Decompile folder (4th folder) - retrospective Best-of
A fourth folder alongside Highlights/Output/Archive. Workflow:
- Use yt-dlp to download previously uploaded compilation videos (max quality, 720p/1080p).
- Scan downloaded video for Quad+ kills and extract those segments as clips.
- Feed extracted clips into the normal Archive -> Best-of pipeline.
Goal: produce "Best of 2024" / "Best of 2025" retrospective videos from already-uploaded content.
Split into parts if over 15 min. Lower priority than producing normal clips from new recordings.

### Best-of compilation
A "Best of 2025/2026" video pulling only Penta and Hexa clips.
Made trivial once clips are named with their KO tier (see above).

### ~~Review `full_vid_scan_test.txt`~~ ✅ DONE
All 7 Quad kills in vid1 confirmed accurate. Timestamp range format confirmed
(`<streak start> - <max tier time> = Quad Kill`). Detection is solid.

### ~~Speed up ko_detect.py batch scans~~ ✅ DONE
`_collect_highlights` in `pipeline.py` now scans clips in parallel using
`ThreadPoolExecutor` (N_WORKERS=4). Each clip writes to its own cache file so
there are no write conflicts. Cache hits are printed as `[cached]`. Per-clip
timing is logged.

### Rename repo/project to reflect Marvel Rivals focus
The program is Marvel Rivals-specific but the repo is named `CompilationVidMaker` (generic).
Should be renamed to something like `MarvelRivalsCompiler` or `MarvelRivalsVidMaker`.

### ~~Two-level arrow-key menu (replaces all number entry)~~ ✅ DONE

**Design (agreed 2026-03-28):**

All interaction goes through run.bat - no separate script flags needed by the user.
The `--cleanup` flag is being phased into the menu; everything accessible from one entry point.

Level 1 - pick a folder to work on:
```
Which folder do you want to work on?
> Highlights   (THOR ready: 2 batches, 3 characters too short)
  Output       (thor_vid1: cleanup needed / thor_vid2: confirm YT first)
  Archive      (47 clips)
```

Level 2 - pick an action within that folder (context-specific):
- Highlights selected: arrow-select a character to compile (or pre-process)
- Output selected: arrow-select a folder, then arrow-select an action (cleanup / mark YT confirmed / dry-run)
- Archive selected: view contents (read-only for now)

**Why two levels:** showing actions for all 3 folders at once creates too many menu items.
Folder-first narrows to only the relevant actions.

**Library:** `simple-term-menu` or `inquirer` (pip install). Avoid `curses` - Windows support is poor.

### Pipeline improvements (lower priority backlog)
- Description format overhaul
- Group clips by output video in UI
- **Time estimation** — before starting a batch, show the user a rough estimate of how long
  the full run will take, broken into stages:
  - *KO scanning* — ~3–9s per uncached clip (cached = instant); estimate from clip count and cache hits
  - *Encoding* — rough heuristic from total batch duration (e.g. ~1× realtime for NVENC GPU)
  - *Total* — sum of above, formatted as "~4 min" or "~12 min"
  Shown after the menu selection and before processing begins, so the user knows whether to
  wait or walk away.

---

## Deferred / future (no near-term action needed)

### Auto-download FFmpeg if missing
On startup, check whether `ffmpeg.exe` / `ffprobe.exe` exist at the configured path.
If not, automatically download and extract the latest FFmpeg Windows build (same pattern
as `C:\Users\David\GitHubRepos\SBS_Download`). No manual setup required for new machines.

### Legacy KO-tier rename migration
`thor_vid1\` and `thor_vid2\vid2_clips\` were compiled before this program was fully set up.
Their clips need a one-off KO-tier rename pass so they follow the convention
(Quad+ can then be identified and moved to ClipArchive).

Script: `scripts/migrate_ko_tiers.py` - dry-run by default, `--execute` to apply.
Run from repo root: `python scripts/migrate_ko_tiers.py`
