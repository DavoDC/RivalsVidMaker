# CompilationVidMaker — Project Context for Claude

## What this project does
C++ console app (VS 2022, C++20, Windows) that batches short Marvel Rivals gameplay clips
into ~15-min YouTube compilations using FFmpeg. A Python script handles KO detection.

## Repo structure
```
data/           cache/          — *.ko.json per-clip KO scan cache (tracked)
                logs/           — runtime logs (gitignored)
                output/vid1/    — description.txt + full_vid_scan_test.txt for vid1
                examples/       — ground_truth/ labelled frames, ko_frames/ reference screenshots
docs/           MULTIKILL_DETECTION.md, YOUTUBE_API.md, IDEAS.md
scripts/        ko_detect.py    — KO detection (Python, THIS IS THE ACTIVE FOCUS)
src/CppProject/ C++ source + config.txt (VS 2022, lower priority)
tools/          ffmpeg.exe + ffprobe.exe (gitignored, user provides)
```

## Development principles
- **Single language rule** — if a feature requires Python, rewrite the entire app in Python. No mixed languages.
- **TDD** — write automated tests first for every feature.
- **One clip first** — get a single clip working perfectly before scaling to batch processing.

## Current focus: KO detection (scripts/ko_detect.py)
Get detection perfect before touching anything else.

### What we're detecting
The multi-kill banner that appears on the RIGHT side of the screen in Marvel Rivals
when the player gets consecutive kills: KO → DOUBLE! → TRIPLE! → QUAD! → PENTA! → HEXA!

### Approach: OCR via pytesseract + Tesseract
- FFmpeg extracts frames at 2fps, skipping first 2s
- Each frame is cropped to the banner region (right 25%, y 40–62%)
- Crop is scaled 3x, inverted (white text → dark for Tesseract), sharpened
- pytesseract reads the tier text (PSM 8/7/6 fallback)
- Events tracked with 2s cooldown to avoid double-counting

### Key parameter: timestamps = STREAK START
YouTube description timestamps = when the FIRST KO banner appears (streak start),
NOT when the Quad/Penta appears. This lets viewers watch the full build-up.

### Threshold: Quad+ only in YouTube description output
Triple and below are detected internally but not shown in the output .txt.

### Cache
Results saved to `data/cache/<clip_stem>.ko.json`. Re-runs are instant.
Null stored in cache = "no kill detected for this clip" (valid result, not an error).

## Clips location
`C:\Users\David\Videos\MarvelRivals\Highlights\THOR\`
- `vid1_uploaded/`    — 31 clips, compiled video already on YouTube (private while testing)
- `vid2_uploaded/`    — 33 clips, compiled video already on YouTube (private while testing)
- `batch3_unused/`    — 5 clips (Mar 5–7 2026), not yet in a video

## Compiled videos
Output folder: `C:\Users\David\Videos\MarvelRivals\Output\`
- `thor_vid1/THOR_batch1.mp4` + description.txt  (~15m 3s, 31 clips)
- `thor_vid2/THOR_batch2.mp4` + description.txt  (~15m 5s, 33 clips)

## YouTube description timestamp workflow
1. Run `python scripts/ko_detect.py --batch vid1`
2. Output written to `data/output/vid1/description.txt`
3. Paste into YouTube description
4. Click each timestamp to verify it lands at the right moment in the video
5. Adjust manually if any are wrong

### User's manual timestamps (vid1, partial — more exist):
```
1:46 - Quad Kill
2:37 - Quad Kill
4:06 - Quad Kill
5:37 - Quad Kill
(more multikills exist after 5:37 — script should find them all)
```
These are approximate — that's fine, viewers just need to be in the right area.

## Detection status
| Clip | Expected | Detected | Verified |
|---|---|---|---|
| THOR_2026-02-06_22-38-56.mp4 | QUAD | QUAD, streak 0:06–0:22 | ✅ |
| THOR_2026-02-17_23-25-25.mp4 | TRIPLE | TRIPLE, streak 0:06–0:14 | ✅ |

Known limitations:
- Short banners (<1s) may be missed at 2fps — mostly affects KO/DOUBLE, not Quad+
- "KO" (2 chars) is harder for OCR than longer tier names

## Next steps
1. Run `python scripts/ko_detect.py --batch vid1` — get full timestamp list
2. Paste into YouTube vid1 description, click to verify each one
3. Fix any wrong timestamps manually
4. Repeat for vid2 (`--batch vid2` — add BATCH2 list to script first)
5. Eventually rewrite entire pipeline in Python (C++ is lower priority)

## Dependencies
- Python 3.10+
- `pip install pytesseract Pillow`
- Tesseract OCR binary: `winget install UB-Mannheim.TesseractOCR`
  → installs to `C:\Program Files\Tesseract-OCR\tesseract.exe` (expected path, no config)
- FFmpeg: place `ffmpeg.exe` + `ffprobe.exe` in `tools/`
