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

### Key parameter: timestamps = STREAK RANGE
YouTube description timestamps must show a **range**: `<streak start> - <when MAX KO banner appeared>`.
- Streak start = when the FIRST KO banner appears in the streak
- Range end = when the highest-tier banner (Quad/Penta/etc.) first appears
- Format: `1:36 - 1:45 = Quad Kill`

This gives viewers both the context build-up AND the exact moment of the big kill.

### Threshold: Quad+ only in YouTube description output
Triple and below are detected internally but not shown in the output .txt.

### Cache
Results saved to `data/cache/<clip_stem>.ko.json`. Re-runs are instant.
Null stored in cache = "no kill detected for this clip" (valid result, not an error).

## Clips location
`C:\Users\David\Videos\MarvelRivals\Highlights\THOR\`
- `vid1_uploaded/`    — 31 clips, compiled video published on YouTube (old timestamp format — needs update)
- `vid2_uploaded/`    — 33 clips, compiled video published on YouTube ✅ (new range format, all verified)
- `batch3_unused/`    — 5 clips (Mar 5–7 2026), not yet in a video

## Compiled videos
Output folder: `C:\Users\David\Videos\MarvelRivals\Output\`
- `thor_vid1/THOR_batch1.mp4`  (~15m 3s, 31 clips) — published, old timestamp format
- `thor_vid2/THOR_batch2.mp4`  (~15m 5s, 33 clips) — published ✅, new range format, all 6 kills verified perfect
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
1. Run `python src/ko_detect.py --batch <vid>`
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
All detections verified accurate by manual playback. Script output matched every kill.
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
1. ~~Run `python src/ko_detect.py --batch vid1` — get full timestamp list~~ ✅ DONE
2. ~~Verify vid1 timestamps~~ ✅ DONE — all 7 Quad kills confirmed accurate
3. ~~Update script output format to range: `<streak start> - <max tier time> = Quad Kill`~~ ✅ DONE
4. ~~Run `python src/ko_detect.py --batch vid2`~~ ✅ DONE
5. ~~Verify vid2 timestamps~~ ✅ DONE — all 6 kills perfect (including Hexa)
6. ~~Publish vid2 with new range-format timestamps~~ ✅ DONE
7. Re-run `python src/ko_detect.py --batch vid1` → update vid1 YouTube description to new range format
8. Eventually rewrite entire pipeline in Python (C++ is lower priority)

> **Script location:** `src/ko_detect.py` (not `scripts/`)

## Dependencies
- Python 3.10+
- `pip install pytesseract Pillow`
- Tesseract OCR binary: `winget install UB-Mannheim.TesseractOCR`
  → installs to `C:\Program Files\Tesseract-OCR\tesseract.exe` (expected path, no config)
- FFmpeg: place `ffmpeg.exe` + `ffprobe.exe` in `tools/`
