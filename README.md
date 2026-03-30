# Rivals Vid Maker

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)



Automates building ~15-minute YouTube compilation videos from short [Marvel Rivals](https://www.marvelrivals.com/) gameplay clips.

## What it does

1. **Scans** a character's clip folder and batches clips into ~15-minute groups by total duration
2. **Detects** multi-kill events (Quad / Penta / Hexa kills) in each clip via OCR (Tesseract)
3. **Encodes** each batch into a single MP4 using FFmpeg (NVENC GPU-accelerated, CPU fallback)
4. **Generates** a YouTube description `.txt` per batch with clickable multi-kill timestamps

## Project Structure

```
RivalsVidMaker/
├── config/
│   ├── config.example.json  # Template - copy to config.json and fill in your paths
│   └── config.json          # Your paths and batch settings (gitignored)
├── src/
│   ├── main.py              # CLI entrypoint
│   ├── batcher.py           # Clip scanning and duration-based batching
│   ├── ocr.py               # Tesseract OCR multi-kill detection
│   ├── encoder.py           # FFmpeg encoding (NVENC / CPU fallback)
│   └── description.py       # YouTube description + timestamp generation
├── scripts/
│   └── run.bat              # Windows launcher
├── tests/                   # Pytest test suite
├── dependencies/
│   ├── ffmpeg/              # FFmpeg binaries (gitignored)
│   └── yt-dlp.exe           # YouTube downloader (gitignored)
└── data/                    # Runtime cache (gitignored)
```

## Setup

```bash
pip install pytesseract Pillow
winget install UB-Mannheim.TesseractOCR
```

Place `ffmpeg.exe` + `ffprobe.exe` in `dependencies/ffmpeg/`.

Copy and edit the config:

```json
{
  "clips_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Highlights",
  "output_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Output",
  "ffmpeg_path": "dependencies\\ffmpeg",
  "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
  "cache_dir": "data\\cache",
  "min_batch_seconds": 600,
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

**Developed:** March 2026 · **Status:** Actively developed
