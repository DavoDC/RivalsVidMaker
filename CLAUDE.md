# RivalsVidMaker — Project Context for Claude

## What this project does
Python pipeline that batches short Marvel Rivals gameplay clips into ~15-min YouTube
compilations using FFmpeg. Detects multi-kill banners via OCR (Tesseract) and generates
timestamped YouTube descriptions automatically.

## Repo structure
```
src/
  main.py               — entry point (run from repo root)
  config.py             — load config/config.json
  pipeline.py           — main orchestrator: sort → scan → batch → detect → encode → describe
  clip_sorter.py        — auto-sort unsorted clips from Highlights/ root into character subfolders
  clip_scanner.py       — scan folder for clips, probe durations in parallel
  batcher.py            — group clips into ~15-min batches
  encoder.py            — FFmpeg concat encode (NVENC GPU / libx264 CPU fallback)
  description_writer.py — write YouTube description .txt files
  ko_detect.py          — KO banner detection (OCR via Tesseract) — standalone + imported
scripts/
  run.bat               — double-click launcher (opens Git Bash terminal)
  run.sh                — runs python src/main.py from repo root
tests/
  test_batcher.py
  test_clip_scanner.py
  test_clip_sorter.py
  test_encoder.py
  test_description_writer.py
data/
  cache/                — *.ko.json per-clip KO scan cache (tracked)
  logs/                 — runtime logs (gitignored)
  output/               — description.txt files per batch
  examples/             — ground_truth/ labelled frames, ko_frames/ reference screenshots
docs/                   MULTIKILL_DETECTION.md, YOUTUBE_API.md, IDEAS.md
tools/                  ffmpeg.exe + ffprobe.exe (gitignored, user provides)
config/
  config.json           — your local config (gitignored)
  config.example.json   — template (tracked)
pytest.ini              — test config (testpaths=tests, pythonpath=src)
```

## How to run
```
# Double-click (opens Git Bash terminal):
scripts/run.bat

# Or directly:
python src/main.py
python src/main.py path/to/config.json   # explicit config

# KO detection standalone (still works):
python src/ko_detect.py                  # ground truth test
python src/ko_detect.py <clip_path>      # single clip debug
python src/ko_detect.py --batch vid1     # batch → writes timestamps .txt

# Tests:
pytest
```

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

### Highlights\
Default save path for Marvel Rivals (set in-game). New clips land here automatically.

- Structure: `Highlights\CHARACTER\*.mp4` — **no further subfolders**.
- Unsorted clips in the root are auto-sorted into character subfolders on each run.
- Character folders contain only raw uncompiled clips. Once compiled, clips move out to Output.
- Current state:
  - `THOR\` — 9 uncompiled clips (ready for next batch)

### Output\
All compiled videos live here. One subfolder per published video.

**Naming convention:** `CHARACTER_MMM-MMM_YYYY` (e.g. `THOR_FEB-MAR_2026`)
- Single month: `THOR_FEB_2026`
- Multi-month: `THOR_FEB-MAR_2026`

**Each output folder contains exactly:**
1. `CHARACTER_DATE.mp4` — the compiled video
2. `CHARACTER_DATE_description.txt` — YouTube title, description, and timestamps
3. `clips\` — the source clip files used in this video (renamed with KO tier suffix)

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
The multi-kill banner that appears on the RIGHT side of the screen in Marvel Rivals
when the player gets consecutive kills: KO → DOUBLE! → TRIPLE! → QUAD! → PENTA! → HEXA!

### Approach: OCR via pytesseract + Tesseract
- FFmpeg extracts frames at 2fps, skipping first 2s
- Each frame is cropped to the banner region (right 25%, y 40–62%)
- Crop is scaled 3x, inverted (white text → dark for Tesseract), sharpened
- pytesseract reads the tier text (PSM 8/7/6 fallback)
- Events tracked with 2s cooldown to avoid double-counting

### Key parameter: timestamps = STREAK RANGE
YouTube description timestamps must show a **range**: `<streak start> - <when MAX KO banner appeared>`.
- Streak start = when the FIRST KO banner appears in the streak
- Range end = when the highest-tier banner (Quad/Penta/etc.) first appears
- Format: `1:36 - 1:45 = Quad Kill`

### Threshold: Quad+ only in YouTube description output
Triple and below are detected internally but not shown in the output .txt.

### Cache
Results saved to `data/cache/<char>/<clip_stem>.ko.json`. Re-runs are instant.
Null stored in cache = "no kill detected for this clip" (valid result, not an error).

### configure() for pipeline integration
`ko_detect.configure(ffmpeg, tesseract, cache_dir)` injects runtime paths from config.json
so the pipeline isn't hardcoded to THOR. Standalone usage is unaffected.

## YouTube description format (canonical — see `data/examples/descriptions/vid2_canonical_example.txt`)

```
TITLE:
<CHARACTER> <tagline> ⚡ <subtitle> (<date range>)

DESCRIPTION:
<one punchy line with emojis, ends with "in Marvel Rivals">

TIMESTAMPS:
<streak start> - <max kill time> = <Tier> Kill
(Quad+ only)

HIGHLIGHTS:
1. CLIP_FILENAME.mp4
...
```

## YouTube description timestamp workflow
1. Run `python src/ko_detect.py --batch <vid>` (or use full pipeline via `run.bat`)
2. Output written to `data/output/<vid>/<vid>_timestamps.txt`
3. Build full description using canonical format above
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
| Clip | Expected | Detected | Verified |
|---|---|---|---|
| THOR_2026-02-06_22-38-56.mp4 | QUAD | QUAD, streak 0:06–0:22 | ✅ |
| THOR_2026-02-17_23-25-25.mp4 | TRIPLE | TRIPLE, streak 0:06–0:14 | ✅ |

Known limitations:
- Short banners (<1s) may be missed at 2fps — mostly affects KO/DOUBLE, not Quad+
- "KO" (2 chars) is harder for OCR than longer tier names

## Next steps
1. ~~KO detection + range format timestamps~~ ✅ DONE
2. ~~vid1 published with verified timestamps~~ ✅ DONE
3. ~~vid2 published with verified timestamps~~ ✅ DONE
4. ~~Rewrite entire pipeline in Python~~ ✅ DONE
5. **Test and refine the new Python pipeline end-to-end** — run against THOR clips
   (batch3_unused has 5 clips, good smoke test), verify sort → scan → batch → detect →
   encode → describe all work, fix any bugs, iterate until clean
6. Test on a new batch (different character) — see IDEAS.md

## Dependencies
- Python 3.10+
- `pip install pytesseract Pillow`
- Tesseract OCR binary: `winget install UB-Mannheim.TesseractOCR`
  → installs to `C:\Program Files\Tesseract-OCR\tesseract.exe` (matches config.json default)
- FFmpeg: place `ffmpeg.exe` + `ffprobe.exe` in `tools/`
