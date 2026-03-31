# Project History

Completed features, settled design decisions, and parked ideas.
Active work stays in `docs/IDEAS.md`.

---

## Completed Features

### Pipeline & architecture

**Rewrite pipeline in Python**
All pipeline stages (encoder, batcher, clip list, description writer) are in Python alongside `ko_detect.py` in `src/`. C++ removed entirely.

**Reorganise repo structure**
C++ removed, Python pipeline in `src/`, `tests/`, `scripts/`, `config/`, clean `.gitignore`.

**Pre-process mode: KO scan all clips upfront**
`src/preprocess.py` + menu option. Scans all clips across all character folders, writes cache entries, reports progress. Does not batch, encode, or move files.

**Caching layer (persistent, keyed, invalidation-aware)**
Cache results stored in `data/cache/<char>/<YYYY-MM>/<stem>.ko.json` keyed by `(filename, file_mtime)`. Stale entries (mtime mismatch) are re-scanned. Null = "scanned, no kill found" - valid result.

**Speed up KO detection batch scans**
`_collect_highlights` in `pipeline.py` scans clips in parallel using `ThreadPoolExecutor` (N_WORKERS=4). Each clip writes to its own cache file (no write conflicts). Cache hits printed as `[cached]`. Per-clip timing logged.

**Skip-if-exists for encoding**
`encode()` in `src/encoder.py` checks if output `.mp4` exists before running FFmpeg. Logs WARNING and returns existing path if so. Pass `force_encode=True` to re-encode.

**Clip KO-tier rename at scan stage**
Clips are renamed in-place immediately after scanning: `THOR_2026-03-16_22-18-00.mp4` -> `THOR_2026-03-16_22-18-00_QUAD.mp4`. Cache file renamed too. `_move_clips()` simplified - tier already embedded.


**Protect 5 most-recent clips from batching/moving**
`sort_clips()` and `scan_folder()` accept `protect_recent=N`. The N most recently saved clips in `Highlights\` ROOT are skipped by sort and never moved. Default N=5, matches the game's buffer size. Config key: `protect_recent_clips`. Only applies to the root folder - character subfolders are never protected. Bug fix (2026-03-31): `preprocess_all()` was incorrectly applying this guard to character subfolders too, zeroing the clip list when folder size <= N.

**Timing fields in KO cache entries**
`cache_save()` accepts optional `clip_duration` and `scan_time` kwargs. `scan_clip()` measures its own elapsed time and calls `get_duration()` before scanning, storing both in the `.ko.json` entry. Accumulates training data for the future time-estimation model. Fields absent on cache hits.

**Two-pass KO scan (fix single-KO miss bug)**
Root cause: 2fps sampling had a 0.5s miss window - KO banners that appeared and disappeared between frames were missed. Fix: pass 1 sweeps at `SCAN_FPS_FAST=2` (fast), pass 2 re-scans any null-result clips at `SCAN_FPS_FULL=4` (0.25s miss window). Confirmed fix: 3 Thor clips (`_22-20-29`, `_23-19-10`, `_23-23-58`) previously null now correctly detected as `_KO`. Also fixed ffprobe path (`FFPROBE` var passed explicitly through `configure()` instead of string-replace hack).

**NULL_RESULT_SUFFIX for processed-but-no-KO clips**
Clips with no KO detected after full scan now renamed with `_NONE` suffix. Cache entry uses `_null_result: true` flag (no `tier` field). Allows distinguishing "processed, confirmed no KO" from "not yet scanned". `preprocess` force-rescans clips without any suffix (unprocessed).

**Full rescan run (2026-03-31)**
Renamed `cache/` to `cache_bak/` and ran full preprocess on all 64 clips to collect `scan_time` and `clip_duration` on every entry. Analysis script `scripts/once_off/analyse_ko_data.py` written to extract statistical insights from the dataset.

**Auto-download FFmpeg on first run**
`src/ffmpeg_setup.py` - `ensure_ffmpeg(ffmpeg_dir)` checks for `ffmpeg.exe`/`ffprobe.exe` at startup. If missing, downloads latest FFmpeg Windows GPL build from BtbN/FFmpeg-Builds and extracts binaries automatically.

---

### UI / display

**Two-level arrow-key menu**
All interaction through `run.bat`. Uses `inquirer` (pip install). `curses` avoided - poor Windows support.

**Startup state display**
`_print_multizone_status()` in `pipeline.py` shows all three folders (Highlights, Output, Archive) in separate tables on launch.

**Show KO tier in HIGHLIGHTS list**
Clip list annotates each entry: `6. THOR_2026-02-21_20-47-21.mp4 [HEXA]`

---

### Description & metadata

**AI prompt generation for title & description**
`src/ai_prompt.py` writes `data/output/<slug>/<slug>_ai_prompts.md` after each pipeline run. Includes character/clip count/date range/kill tier context and pre-filled prompts.

---

### State & cleanup

**State log (JSON) - folder-level**
`src/state.py` + `data/state.json` (gitignored, machine-local). Tracks `youtube_confirmed` per output folder.

**Output folder cleanup workflow**
`src/cleanup.py` - interactive cleanup with dry_run=True support. Lists clips with KO tiers, proposes Quad+ -> ClipArchive moves and remaining clip deletion, asks per-action confirmation. Wired into Output menu.

---

### OldCompilations

**Phase 1 - Download all previously-uploaded videos**
`scripts/download_playlist.py` downloads all 27 videos from the YouTube playlist idempotently (skips already-downloaded). All 27 videos confirmed at 1080p.
- 20 compilation videos (various characters/dates)
- 7 full gameplay stream recordings (39min to ~4hr)
- Two 2026-03-17 videos already processed (clips saved).

---

### Misc

**Review `full_vid_scan_test.txt`**
All 7 Quad kills in vid1 confirmed accurate. Timestamp range format confirmed (`<streak start> - <max tier time> = Quad Kill`). Detection is solid.

**Rename repo**
Renamed from `CompilationVidMaker` to `RivalsVidMaker`.

---

## Design Decisions (settled)

**Slug always includes batch number**
Output folders always use `_BATCH1`, `_BATCH2` etc. even when compiling one at a time. Safer to always have a unique, predictable name than to special-case the first batch.

**One batch at a time**
The pipeline always compiles the first batch only. Re-run for subsequent batches. Rationale: clips no longer build up to 30-min backlogs now that the process is automated. Multi-batch prompt removed 2026-03-28.

**State-driven pipeline - not being pursued**
The current system's implicit state (clips in Highlights = uncompiled, output folder exists = compiled) is sufficient. The one genuine benefit (multi-batch flow) is solved by the one-at-a-time approach above. Full spec preserved in the Parked section below.

---

## Parked

### State-driven pipeline (major redesign)

Full redesign spec kept for reference. Not being pursued - parked indefinitely.

#### Concept
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
- `data/cache/` - caching layer complete.
- `_print_multizone_status()` - startup display complete.
- `src/cleanup.py` - cleanup workflow skeleton complete.

**Still needed if ever resumed:** clip-level state (which clips belong to which batch, KO tier per clip).
