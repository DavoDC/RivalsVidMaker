# Rivals Vid Maker

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)



Automates building ~15-minute YouTube compilation videos from short [Marvel Rivals](https://www.marvelrivals.com/) gameplay clips.

## What it does

1. **Scans** a character's clip folder and batches clips into ~15-minute groups by total duration
2. **Detects** multi-kill events (Quad / Penta / Hexa kills) in each clip via OCR (Tesseract)
3. **Encodes** each batch into a single MP4 using FFmpeg (NVENC GPU-accelerated, CPU fallback)
4. **Generates** a YouTube description `.txt` per batch with clickable multi-kill timestamps

## Clip pipeline

Video clips move through three folders as they are processed:

```
Highlights/THOR/          <- raw clips from gameplay, sorted by character
Output/THOR_Mar_2026/     <- compiled video, description, AI prompts, source clips
ClipArchive/THOR/         <- permanent archive of Quad+ clips
```

**Full flow:**

1. Drop new clips into `Highlights/`
2. Run the tool - it sorts clips into character subfolders, scans for kill events, batches by duration, and encodes
3. Upload the compiled MP4 to YouTube
4. Run cleanup - Quad+ source clips are archived to `ClipArchive/`, the rest deleted

`ClipArchive` clips are never deleted. They feed future Best-of compilations.

## How kill detection works

The tool scans each clip for multi-kill events using OCR, without needing game API access or video labels:

1. **Frame extraction** - FFmpeg extracts frames at a low framerate (fast pass by default)
2. **Region crop** - only the banner region (right side of frame, mid-height) is kept, where the kill tier banner appears
3. **Image preprocessing** - crop is converted to grayscale, upscaled, inverted, and sharpened for better OCR accuracy
4. **OCR** - Tesseract reads the tier text from the crop (KO, Double, Triple, Quad, Penta, Hexa)
5. **Event logic** - a cooldown between events prevents double-counting the same kill; early exit if no kill is found within the likely window
6. **Caching** - results are cached per clip; re-running the pipeline on cached clips is instant

Only **Quad kills and above** appear as clickable timestamps in the YouTube description.

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

```bash
pip install pytesseract Pillow inquirer
winget install UB-Mannheim.TesseractOCR
```

FFmpeg is downloaded automatically on first run. No manual installation needed.

Copy and edit the config:

```json
{
  "clips_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Highlights",
  "output_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Output",
  "archive_path": "C:\\Users\\You\\Videos\\MarvelRivals\\ClipArchive",
  "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
  "cache_dir": "data\\cache",
  "target_batch_seconds": 900
}
```

## Usage

```bash
scripts/run.bat     # Windows launcher
python src/main.py  # or run directly

pytest              # run tests
```

## Tech

- **Language:** Python 3.10+
- **Video encoding:** [FFmpeg](https://ffmpeg.org/) with NVENC GPU acceleration (NVIDIA) - auto-falls back to CPU
- **OCR:** [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) via pytesseract for kill-event detection
- **Testing:** Pytest test suite

## Requirements

- Windows, Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- FFmpeg in `dependencies/ffmpeg/`
- NVIDIA GPU recommended (NVENC) - falls back to CPU automatically

## Development

**Developed:** March 2026
