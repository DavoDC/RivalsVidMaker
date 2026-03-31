# RivalsVidMaker — Project Context for Claude

## What this project does
Python pipeline that batches short Marvel Rivals gameplay clips into ~15-min YouTube
compilations using FFmpeg. Detects multi-kill banners via OCR (Tesseract) and generates
timestamped YouTube descriptions automatically.

## Repo structure
```
src/
  main.py               — entry point (run from repo root); supports --force flag
  config.py             — load config/config.json
  pipeline.py           — main orchestrator: sort → scan → batch → detect → encode → describe
  clip_sorter.py        — auto-sort unsorted clips from Highlights/ root into character subfolders
  clip_scanner.py       — scan folder for clips, probe durations in parallel
  batcher.py            — group clips into ~15-min batches
  encoder.py            — FFmpeg concat encode (NVENC GPU / libx264 CPU fallback); skip-if-exists
  description_writer.py — write YouTube description .txt files
  ko_detect.py          — KO banner detection (OCR via Tesseract) — standalone + imported
  ai_prompt.py          — generate pre-filled AI prompts markdown file after each pipeline run
  cleanup.py            — interactive post-YouTube cleanup (move Quad+ to archive, delete rest)
  preprocess.py         — pre-process mode: warm KO cache for all clips without encoding
scripts/
  run.bat               — double-click launcher (opens Git Bash terminal)
  run.sh                — runs python src/main.py from repo root
tests/
  test_batcher.py
  test_clip_scanner.py
  test_clip_sorter.py
  test_encoder.py
  test_description_writer.py
  test_ko_cache.py
  test_ai_prompt.py
  test_cleanup.py
data/
  cache/                — *.ko.json per-clip KO scan cache (tracked)
  logs/                 — runtime logs (gitignored)
  output/               — description.txt files per batch
  examples/             — ground_truth/ labelled frames, ko_frames/ reference screenshots
docs/                   MULTIKILL_DETECTION.md, YOUTUBE_API.md, IDEAS.md
dependencies/
  ffmpeg/               ffmpeg.exe + ffprobe.exe + ffplay.exe (gitignored, user provides)
  yt-dlp.exe            used by scripts/download_playlist.py (gitignored)
config/
  config.json           — your local config (gitignored)
  config.example.json   — template (tracked)
pytest.ini              — test config (testpaths=tests, pythonpath=src)
```

## How to run

**Primary entry point: double-click `scripts/run.bat`**
All normal workflow goes through this. No need to run scripts with different args.
The interactive menu handles everything: compile, pre-process, cleanup, etc.

```
# Developer/debug only (not normal usage):
python src/main.py --force               # re-encode even if output already exists
python src/main.py --cleanup --dry-run   # preview cleanup without moving files

# KO detection standalone:
python src/ko_detect.py                  # ground truth test
python src/ko_detect.py <clip_path>      # single clip debug

# Tests:
pytest
```

Note: `--cleanup` as a standalone flag is being phased into the interactive menu.
Eventually all actions will be accessible from within run.bat with no extra flags needed.

## Development principles
- **Single language rule** — Python only. No mixed languages.
- **TDD** — write tests first for every feature.
- **One clip first** — get a single clip working perfectly before scaling to batch.

## Logging architecture
- **FileHandler (DEBUG)** — full timestamped log of everything, including internal details
  (per-clip probe results, ffmpeg commands, ffmpeg stderr, KO scan details per clip).
- **StreamHandler (INFO)** — terminal shows the same user-facing messages, plain format
  (no timestamps, no level prefix for INFO; `[WARNING]`/`[ERROR]` prefix for those).
- Rule: **everything shown in the terminal also appears in the log; the log has more.**
- Log files are created lazily (`delay=True`) — if the user exits before any work starts,
  no empty log file is left behind.
- Log location: `data/logs/run_YYYYMMDD_HHMMSS.log`

## Clip filename convention
Marvel Rivals clips follow: `{CHARACTER NAME}_{YYYY}-{MM}-{DD}_{HH}-{MM}-{SS}.mp4`

Character names may contain letters, digits, spaces, or underscores.
Spaces are normalised to underscores for the folder name.

Examples:
```
THOR_2026-02-06_22-38-56.mp4           →  Highlights/THOR/
SQUIRREL GIRL_2026-03-13_21-51-02.mp4  →  Highlights/SQUIRREL_GIRL/
BLACK WIDOW_2026-01-15_08-00-00.mp4   →  Highlights/BLACK_WIDOW/
```

## Clip auto-sorter (src/clip_sorter.py)
On every run the pipeline first calls `sort_clips(clips_path)` to move any video files
sitting directly in the `Highlights/` root into per-character subfolders.

**Safety guarantees:**
- Uses `shutil.move()` — atomic rename on the same filesystem, no copy+delete risk.
- Only touches files **directly in** `clips_path/` root. Existing subfolders are never entered.
- Skips any file whose character name cannot be parsed (logged as WARNING).
- Skips if the destination already exists — never overwrites (logged as WARNING).

**Character folder convention — Highlights subfolders contain ONLY raw `.mp4` clips.**
No further subfolders. Once a clip is compiled into a video it moves to
`Output\CHARACTER_DATE\clips\` — it does NOT stay in Highlights.
Highlights is a pure intake zone: new clips arrive → get sorted → stay until compiled.

## Video folder structure
Root: `C:\Users\David\Videos\MarvelRivals\`

## End-to-end clip lifecycle (game -> pipeline -> YouTube)

Understanding this flow is essential for designing pipeline features.

### Stage 1: In-game auto-capture
- Marvel Rivals automatically captures highlights during gameplay - no user action needed.
- The game maintains an internal buffer of the **5 most recent highlights** only.
- These 5 clips are shown in-game under `Career > Favorites > Highlights` in the **"RECENT HIGHLIGHTS 5/5"** panel.
- These are NOT yet files on disk - they live in the game's internal buffer.
- If the game captures a 6th clip, the oldest of the 5 is discarded and lost forever.

### Stage 2: Manual save to disk (in-game UI)
- David reviews the "RECENT HIGHLIGHTS 5/5" panel in-game.
- Each clip has a **SAVE** button. He presses SAVE on clips worth keeping.
- Pressing SAVE writes the `.mp4` file to `C:\Users\David\Videos\MarvelRivals\Highlights\` on disk.
- Saved clips show a **"SAVED" badge** on the thumbnail; clips being written show **"SAVING"**.
- Clips David does NOT save are lost when new clips push them out of the buffer.
- Reference screenshot: `data/examples/Marvel_Rivals_Highlights_UI.png`

### Stage 3: Clips on disk (RVM intake zone)
- The **"HIGHLIGHTS SAVED"** panel in-game shows clips already on disk (with SHARE buttons).
- The top 5 most recently created clips on the filesystem correspond to what the game shows as "SAVED" in its UI.
- These are the raw `.mp4` files in `Highlights\` - this is where RVM takes over.
- RVM auto-sorts them from the root into per-character subfolders on each run.

### Stage 4: RVM pipeline
- Clips stay in `Highlights\CHARACTER\` until compiled.
- RVM batches them into ~15-min groups (one batch per run - re-run for subsequent batches).
- At KO scan stage, clips are renamed in-place with tier suffix (e.g. `THOR_..._QUAD.mp4`).
- After compilation, clips move to `Output\CHARACTER_DATE\clips\` (already renamed from scan).

### Stage 5: Cleanup (post-YouTube)
- After confirming the YouTube upload, cleanup runs: Quad+ -> ClipArchive, rest deleted.

---

### Design implication: protect recent clips from processing
The 5 most recently created clips on the filesystem match what the game shows as "SAVED" in the Recent Highlights UI. If RVM moves or processes those clips, the game's UI loses track of them - the "SAVED" badge disappears and it becomes confusing which clips were saved.

**Scope: ROOT folder only.** Protection applies ONLY to `Highlights\` root (the in-game save destination). It does NOT apply to character subfolders (`Highlights\THOR\`, `Highlights\SQUIRREL_GIRL\`, etc.) - clips there have already been sorted and are safe to process without restriction.

**Planned feature:** protect the N most recently created clips in `Highlights\` ROOT from being batched/moved (default N=5). These clips are skipped until newer clips are saved on top of them. The protection guard must NOT be applied inside character subfolders.

---

### Highlights\
Default save path for Marvel Rivals (set in-game). New clips land here after David presses SAVE in-game.

- Structure: `Highlights\CHARACTER\*.mp4` - **no further subfolders**.
- Unsorted clips in the root are auto-sorted into character subfolders on each run.
- Character folders contain only raw uncompiled clips. Once compiled, clips move out to Output.
### Output\
All compiled videos live here. One subfolder per published video.

**Naming convention:** `CHARACTER_MMM-MMM_YYYY` (e.g. `THOR_FEB-MAR_2026`)
- Single month: `THOR_FEB_2026`
- Multi-month: `THOR_FEB-MAR_2026`

**Each output folder contains exactly:**
1. `CHARACTER_DATE.mp4` — the compiled video
2. `CHARACTER_DATE_description.txt` — YouTube title, description, and timestamps
3. `clips\` — the source clip files used in this video (tier already in filename from scan stage)

When the user confirms the YouTube video is in good shape, the cleanup process:
- Moves Quad+ clips from `clips\` → `ClipArchive\` (preserved for future Best-of)
- Deletes the remaining clips from `clips\` (after explicit user confirmation listing each file)
- The compiled `.mp4` may also be deleted to save disk space (user confirms)

**Legacy folders (pre-convention, before program was fully set up):**
- `thor_vid1\` — 31 clips in root, published ✅, 7 Quad kills verified — clips not yet renamed with KO tier
- `thor_vid2\vid2_clips\` — 33 clips, published ✅, 6 kills verified (incl. Hexa) — clips not yet renamed
  - Title: "THOR OVERLOAD ⚡ Back-to-Back Multikills (Feb–Mar 2026)"
  These need KO-tier renaming done as a one-off migration (see IDEAS.md).

### ClipArchive\
Long-term archive for Quad+ clips. Never deleted automatically.
- Purpose: source material for a future "Best of 202X" compilation.
- Clips land here during Output cleanup (after YouTube confirmation).
- No subfolders required — flat structure is fine.

## KO detection (src/ko_detect.py)
Detects multi-kill banners (KO → DOUBLE → TRIPLE → QUAD → PENTA → HEXA) via OCR.
Full technical reference: `docs/MULTIKILL_DETECTION.md`.

- 2fps frame extraction, banner crop: right 25%, y 40–62%, 2s cooldown between events
- **Threshold:** Quad+ only in YouTube description output; Triple and below detected internally
- **Cache:** `data/cache/<char>/<YYYY-MM>/<clip_stem>.ko.json` - re-runs are instant; null = no kill (valid); also stores `clip_duration` + `scan_time` for future time estimation
- **Cache keying:** each entry stores `file_mtime`; if the clip file changes, the cache is automatically invalidated and the clip is re-scanned
- **Not all highlight clips are multi-kills:** game DVR saves single-KO + assist sequences too. DOUBLE+ minimum for compilations (pending - see IDEAS.md)
- **`ko_detect.configure(ffmpeg, tesseract, cache_dir)`** — injects runtime paths from config.json so the pipeline isn't hardcoded to THOR. Standalone usage is unaffected.

## YouTube description format
Full format reference, title/description examples: `docs/YOUTUBE_TITLE_AND_DESC.md`.

## YouTube description timestamp workflow
1. Run `python src/ko_detect.py --batch <vid>` (or use full pipeline via `run.bat`)
2. Output written to `data/output/<vid>/<vid>_timestamps.txt`
3. Build full description using canonical format (see `docs/YOUTUBE_TITLE_AND_DESC.md`)
4. Paste into YouTube description
5. Click each timestamp to verify it lands at the right moment in the video
6. Adjust manually if any are wrong

### Verified vid1 timestamps (complete — all 7 Quad kills confirmed ✅):
```
1:36 - 1:45 = Quad Kill
2:30 - 2:37 = Quad Kill
3:52 - 4:06 = Quad Kill
5:23 - 5:37 = Quad Kill
5:54 - 6:16 = Quad Kill
8:32 - 8:42 = Quad Kill
12:58 - 13:07 = Quad Kill
```
All detections verified accurate by manual playback.

## Detection status
Validated clips and known limitations: `docs/MULTIKILL_DETECTION.md`.

## Pending work

See `docs/IDEAS.md` for all pending ideas and next actions, ordered by priority.

**Keep IDEAS.md clean:** when a feature is implemented or a task is done, move its entry from `docs/IDEAS.md` to `docs/HISTORY.md`. Never leave completed items in IDEAS.md. Look for items marked DONE, with checkmarks, or fully implemented before ending a session.

## Dependencies
- Python 3.10+
- `pip install pytesseract Pillow`
- Tesseract OCR binary: `winget install UB-Mannheim.TesseractOCR`
  → installs to `C:\Program Files\Tesseract-OCR\tesseract.exe` (matches config.json default)
- FFmpeg: place `ffmpeg.exe` + `ffprobe.exe` in `dependencies/ffmpeg/`
