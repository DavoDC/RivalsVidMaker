# Completed Features

Moved here from IDEAS.md to keep the active ideas list clean. Each entry describes what was built and where it lives.

---

## Pipeline & architecture

### Rewrite pipeline in Python
All pipeline stages (encoder, batcher, clip list, description writer) are in Python alongside `ko_detect.py` in `src/`. C++ removed entirely.

### Reorganise repo structure
C++ removed, Python pipeline in `src/`, `tests/`, `scripts/`, `config/`, `.gitkeep` in `tools/`, clean `.gitignore`.

### Pre-process mode: KO scan all clips upfront
`src/preprocess.py` + menu option. Scans all clips across all character folders, writes cache entries, reports progress. Does not batch, encode, or move files.

### Caching layer (persistent, keyed, invalidation-aware)
Cache results stored in `data/cache/<char>/<YYYY-MM>/<stem>.ko.json` keyed by `(filename, file_mtime)`. Stale entries (mtime mismatch) are re-scanned. Null = "scanned, no kill found" - valid result.

### Speed up KO detection batch scans
`_collect_highlights` in `pipeline.py` scans clips in parallel using `ThreadPoolExecutor` (N_WORKERS=4). Each clip writes to its own cache file (no write conflicts). Cache hits printed as `[cached]`. Per-clip timing logged.

### Skip-if-exists for encoding
`encode()` in `src/encoder.py` checks if output `.mp4` exists before running FFmpeg. Logs WARNING and returns existing path if so. Pass `force_encode=True` to re-encode.

### Clip KO-tier rename at compilation stage
`_move_clips()` in `pipeline.py` renames clips on move to Output:
`THOR_2026-03-16_22-18-00.mp4 -> THOR_2026-03-16_22-18-00_QUAD.mp4`.

### Legacy KO-tier rename migration
`thor_vid1\` and `thor_vid2\vid2_clips\` clips renamed with KO tier via `scripts/migrate_ko_tiers.py`. Completed.

### Protect 5 most-recent clips from batching/moving
`sort_clips()` and `scan_folder()` accept `protect_recent=N`. The N most recently saved clips are skipped by sort and never moved out of `Highlights\`. Default N=5, matches the game's buffer size. Config key: `protect_recent_clips`. Integration test in `tests/test_integration.py`.

---

## UI / display

### Two-level arrow-key menu
All interaction through `run.bat`. Level 1 picks a folder (Highlights/Output/Archive). Level 2 picks a character or action within that folder. Uses `inquirer` (pip install). `curses` avoided - poor Windows support.

### Startup state display
`_print_multizone_status()` in `pipeline.py` shows all three folders (Highlights, Output, Archive) in separate tables on launch.

### Show KO tier in HIGHLIGHTS list
`write_description()` annotates each clip line: `6. THOR_2026-02-21_20-47-21.mp4 [HEXA]`

---

## Description & metadata

### AI prompt generation for title & description
`src/ai_prompt.py` writes `data/output/<slug>/<slug>_ai_prompts.md` after each pipeline run. Includes character/clip count/date range/kill tier context and pre-filled prompts following the format in `docs/YOUTUBE_TITLE_AND_DESC.md`.

### Document full pipeline end-to-end
CLAUDE.md documents the complete workflow. `docs/MANUAL_TESTING.md` covers end-to-end testing steps.

---

## State & cleanup

### State log (JSON) - folder-level
`src/state.py` + `data/state.json` (gitignored, machine-local). Tracks `youtube_confirmed` per output folder. Gates `--cleanup` (asks "Is this live on YouTube?" on first run, saves answer).

### Output folder cleanup workflow (skeleton)
`src/cleanup.py` - interactive cleanup with dry_run=True support. Lists clips with KO tiers, proposes Quad+ -> ClipArchive moves and remaining clip deletion, asks per-action confirmation. Wired into Output menu.

---

## Docs & repo

### Rename repo to reflect Marvel Rivals focus
Renamed from `CompilationVidMaker` to `RivalsVidMaker`. Happy with the name.

### Consolidate docs/ folder
`docs/` now contains: `MULTIKILL_DETECTION.md`, `YOUTUBE_API.md`, `YOUTUBE_TITLE_AND_DESC.md`, `IDEAS.md`, `MANUAL_TESTING.md`, `DONE.md`.

### Review `full_vid_scan_test.txt`
All 7 Quad kills in vid1 confirmed accurate. Timestamp range format confirmed (`<streak start> - <max tier time> = Quad Kill`). Detection is solid.

---

## OldCompilations

### Phase 1 - Download all previously-uploaded videos
`scripts/download_playlist.py` downloads all 27 videos from the YouTube playlist idempotently (skips already-downloaded). All 27 videos confirmed at 1080p, good quality.
- 20 compilation videos (various characters/dates)
- 7 full gameplay stream recordings (39min to ~4hr)
- Two 2026-03-17 videos already processed through the pipeline (clips saved).

---

## Setup & tooling

### Auto-download FFmpeg on first run
`src/ffmpeg_setup.py` - `ensure_ffmpeg(ffmpeg_dir)` checks for `ffmpeg.exe`/`ffprobe.exe` at startup. If missing, downloads latest FFmpeg Windows GPL build from BtbN/FFmpeg-Builds and extracts binaries automatically. Called from `main.py` before any processing.

### Rename clips at KO scan stage
`_collect_highlights()` in `pipeline.py` renames clips in-place immediately after scanning (e.g. `THOR_2026-02-06_22-38-56.mp4` -> `THOR_2026-02-06_22-38-56_QUAD.mp4`). Cache file renamed too (keeps future scans fast). `_move_clips()` simplified - tier already embedded. `preprocess_all()` in `preprocess.py` also renames after scanning or cache hit.
