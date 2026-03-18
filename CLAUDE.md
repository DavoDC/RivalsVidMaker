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
  pipeline.py           — main orchestrator: scan → batch → detect → encode → describe
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

## Clips location
`C:\Users\David\Videos\MarvelRivals\Highlights\THOR\`
- `vid1_uploaded/`    — 31 clips, compiled video published on YouTube ✅ (all verified)
- `vid2_uploaded/`    — 33 clips, compiled video published on YouTube ✅ (all verified)
- `batch3_unused/`    — 5 clips (Mar 5–7 2026), not yet in a video

## Compiled videos
Output folder: `C:\Users\David\Videos\MarvelRivals\Output\`
- `thor_vid1/THOR_batch1.mp4`  (~15m 3s, 31 clips) — published ✅, 7 Quad kills verified
- `thor_vid2/THOR_batch2.mp4`  (~15m 5s, 33 clips) — published ✅, 6 kills verified (incl. Hexa)
  - Title: "THOR OVERLOAD ⚡ Back-to-Back Multikills (Feb–Mar 2026)"

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
5. **Test and refine the new Python pipeline end-to-end** — run against THOR/batch3_unused (5 clips, small smoke test), verify scan → batch → detect → encode → describe all work, fix any bugs, iterate until clean
6. Test on a new batch (different character) — see IDEAS.md

## Dependencies
- Python 3.10+
- `pip install pytesseract Pillow`
- Tesseract OCR binary: `winget install UB-Mannheim.TesseractOCR`
  → installs to `C:\Program Files\Tesseract-OCR\tesseract.exe` (matches config.json default)
- FFmpeg: place `ffmpeg.exe` + `ffprobe.exe` in `tools/`
