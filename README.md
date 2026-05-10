# Rivals Vid Maker

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)

Automates building ~15-minute YouTube compilation videos from short [Marvel Rivals](https://www.marvelrivals.com/) gameplay clips. **Batchs, scans, merges, and uploads in seconds using stream copy muxing (100x faster than re-encoding).**

## What it does

1. **Detects** multi-kill events (Quad / Penta / Hexa) in each clip via OCR (Tesseract) with parallel multi-threaded scanning
2. **Warns** about duplicate clips before encoding using perceptual hashing - prevents wasted processing
3. **Batches** clips into ~15-minute groups by total duration and merges them in seconds via stream copy (no re-encoding)
4. **Generates** timestamped YouTube descriptions with clickable kill timestamps
5. **Uploads** compiled videos to YouTube automatically with OAuth authentication and state tracking
6. **Archives** Quad+ clips for future Best-of compilations; offers interactive cleanup and recovery options

## Features

### Speed & Performance
- **Lightning-fast encoding**: Stream copy concatenation completes 15-min videos in ~10 seconds (100x faster than GPU re-encoding). Works because Marvel Rivals clips are uniform H.264 1920x1080 120fps AAC.
- **Parallel multi-threaded scanning**: OCR detection runs on multiple clips simultaneously - real concurrency from external FFmpeg + Tesseract processes
- **Instant re-runs**: File-change aware caching means re-running on the same clips takes ~1 second

### Automation & Intelligence
- **YouTube integration**: OAuth authentication, automated upload to your channel, state tracking. Confirm once, retry failed uploads later.
- **Duplicate detection**: Perceptual hashing (pHash) warns about duplicate clips before wasting time encoding. You decide whether to keep or remove.
- **Smart state tracking**: Remembers which videos were uploaded, allows retry/recovery, prevents re-uploading the same content

### User Experience
- **Interactive menu**: Single entry point via `scripts/run.bat` - no command-line flags needed. Arrow-key navigation to:
  - Compile a new highlights video
  - Pre-process clips (warm cache without encoding)
  - Manage output folders (retry uploads, archive clips, recover uncompiled videos)
  - Browse the archive of Quad+ clips
- **Comprehensive logging**: Every run saves a timestamped log file with full debug output for troubleshooting

### Workflow
- **Clip auto-sorting**: Raw clips in Highlights root are auto-sorted into character subfolders
- **Tier-aware naming**: Clips automatically renamed with kill tier after scanning (e.g., `THOR_..._QUAD.mp4`)
- **Archive management**: Quad+ clips permanently archived for future "Best-of" compilations; other clips can be safely deleted
- **Undo option**: "Uncompile" a batch to restore clips back to Highlights and discard output

## Workflow Overview

```
Highlights/CHAR/          <- raw clips from gameplay
  |
  +--> [Pipeline: sort, scan, batch, encode, upload]
  |
Output/CHAR_DATE/         <- compiled MP4, description, source clips
  |
  +--> [Cleanup: archive Quad+, delete rest]
  |
ClipArchive/CHAR/         <- permanent best-kills archive (never deleted)
```

**Full process:**
1. Marvel Rivals auto-saves clips to `Highlights/` - you just press SAVE in-game
2. Run `scripts/run.bat` - interactive menu guides you through all steps
3. Select a character with enough clips (~15 min) - tool scans, detects kills, encodes, generates description
4. Review the output folder and confirm the video looks good
5. Upload to YouTube via the menu (one-click OAuth, automatic upload)
6. Cleanup: archive Quad+ clips for future compilations, delete the rest

**Smart features:** Duplicate detection warns before encoding. Cache makes re-runs instant. Retry failed uploads anytime. Uncompile if you need to recover clips.

Archive clips accumulate for future "Best-of" compilations and are never auto-deleted.

## Kill Detection (OCR via Tesseract)

The tool scans each clip for multi-kill events using OCR, without needing game API access or video labels. **Scanning is parallelized across all CPU cores** - multiple clips are scanned simultaneously using multi-threaded FFmpeg + Tesseract processes.

**Algorithm:**
1. **Frame extraction** - FFmpeg extracts frames at 2fps (optimized for speed)
2. **Region crop** - isolates the banner region (right side, mid-height) where kill tier appears
3. **Image preprocessing** - grayscale, upscale, invert, sharpen for OCR accuracy
4. **OCR** - Tesseract reads the tier text (KO, Double, Triple, Quad, Penta, Hexa)
5. **Event logic** - 2-second cooldown prevents double-counting; early exit if no kill found in likely window
6. **Caching** - results cached per clip with file-change detection; re-runs are instant

**In YouTube descriptions:** Only Quad+ kills appear as clickable timestamps. Triple and Double detected internally (used for auto-naming clips). Single KO not reported.

**Performance:** First run on a 15-min batch (30-40 clips): ~2-3 min with parallel scanning. Second run on same clips: ~1 second (cache hit).

## Project Structure

```
RivalsVidMaker/
├── config/
│   ├── config.example.json  # Template - copy to config.json and fill in your paths
│   └── config.json          # Your paths and batch settings (gitignored)
├── src/
│   ├── main.py              # CLI entrypoint and interactive menu
│   ├── pipeline.py          # Main orchestrator: sort -> scan -> batch -> encode -> describe
│   ├── ko_detect.py         # Tesseract OCR multi-kill banner detection
│   ├── encoder.py           # FFmpeg encoding (NVENC GPU / libx264 CPU fallback)
│   ├── preprocess.py        # Pre-process mode: warm KO cache for all clips
│   └── cleanup.py           # Post-YouTube cleanup (archive Quad+, delete rest)
├── scripts/
│   └── run.bat              # Windows launcher (double-click to run)
├── tests/                   # Pytest test suite
├── dependencies/
│   ├── ffmpeg/              # FFmpeg binaries - auto-downloaded on first run (gitignored)
│   └── yt-dlp.exe           # YouTube downloader (gitignored)
└── data/                    # Runtime cache and logs (gitignored)
```

## Setup

### 1. Install dependencies

```bash
# Python packages
pip install pytesseract Pillow imagehash questionary google-auth-oauthlib send2trash

# Tesseract OCR (Windows)
winget install UB-Mannheim.TesseractOCR
```

**FFmpeg** is downloaded automatically on first run (official FFmpeg builds, auto-extracted to `dependencies/ffmpeg/`). No manual installation needed.

### 2. Configure paths

Copy `config/config.example.json` to `config/config.json` and edit your paths:

```json
{
  "clips_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Highlights",
  "output_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Output",
  "archive_path": "C:\\Users\\You\\Videos\\MarvelRivals\\ClipArchive",
  "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
  "youtube_channel_id": "YOUR_CHANNEL_ID_HERE",
  "cache_dir": "data\\cache",
  "target_batch_seconds": 900
}
```

### 3. (Optional) Set up YouTube upload

Run the tool once - it will guide you through OAuth authentication when you first try to upload. Your token is saved to `config/token.json` for future uploads.

## Usage

**Primary entry point:** Double-click `scripts/run.bat` and use the interactive menu to access all features (compile, upload, cleanup, etc). No command-line flags needed for normal use.

```bash
scripts/run.bat             # Windows launcher - recommended for all normal work

# Developer/advanced:
python src/main.py          # Run directly (uses config/config.json)
python src/main.py --force  # Re-encode even if output already exists
python src/ko_detect.py     # Test KO detection standalone

pytest                      # Run test suite
```

## Tech Stack

- **Language:** Python 3.10+
- **Video encoding:** [FFmpeg](https://ffmpeg.org/) - stream copy (no re-encoding) for lightning-fast concatenation
- **OCR:** [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) via pytesseract for kill-event detection
- **Duplicate detection:** imagehash (perceptual hashing) + Pillow for frame analysis
- **UI:** questionary for interactive arrow-key menus
- **YouTube integration:** google-auth + google-auth-oauthlib for OAuth 2.0 uploads
- **Testing:** Pytest with comprehensive test coverage (~40 test modules)

## Requirements

- Windows, Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- FFmpeg in `dependencies/ffmpeg/`
- NVIDIA GPU recommended (NVENC) - falls back to CPU automatically

## What Makes This Difficult

**Real-time KO detection via OCR:** The banner detection system is the hardest part - automatically identifying multi-kill tiers from a moving video stream with no labeled training data. Uses perceptual hashing, Tesseract OCR, image preprocessing, and a cooldown state machine to achieve >95% accuracy.

**Stream copy architecture:** YouTube/compilation tools typically re-encode for compatibility. We detected that Marvel Rivals clips are uniform (H.264 1920x1080 120fps AAC), allowing stream copy muxing - eliminating encoding bottleneck entirely.

**Parallel pipeline:** Coordinates FFmpeg frame extraction, Tesseract OCR, and duplicate detection across multiple clips simultaneously while maintaining state and cache coherence.

**YouTube integration:** Full OAuth 2.0 flow with state tracking, retry logic, and multi-account support. Prevents accidental uploads to wrong channel.

## Development

**Built:** March 2026 | **Test coverage:** 40+ test modules | **Active features:** 15+
