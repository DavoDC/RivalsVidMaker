# Compilation Vid Maker (CVM)

Automates building ~15-minute YouTube compilation videos from short Marvel Rivals gameplay clips.

## What it does

1. **Scans** a character's clip folder and batches clips into ~15-minute groups by duration
2. **Detects** multi-kill events (Quad / Penta / Hexa) in each clip via OCR (Tesseract)
3. **Encodes** each batch into a single MP4 using FFmpeg (NVENC GPU acceleration, CPU fallback)
4. **Generates** a YouTube description `.txt` per batch with clickable multi-kill timestamps

## Quick start

```bash
# Install Python dependencies
pip install pytesseract Pillow

# Install Tesseract OCR
winget install UB-Mannheim.TesseractOCR

# Place ffmpeg.exe + ffprobe.exe in tools/

# Edit config.json with your paths, then run:
scripts/run.bat         # Windows — opens Git Bash terminal
# or:
python src/main.py
```

## Configuration

Copy the example config and fill in your paths:

```bash
cp config/config.example.json config/config.json
```

Then edit `config/config.json`:

```json
{
  "clips_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Highlights",
  "output_path": "C:\\Users\\You\\Videos\\MarvelRivals\\Output",
  "ffmpeg_path": "tools",
  "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
  "cache_dir": "data\\cache",
  "min_batch_seconds": 600,
  "target_batch_seconds": 900
}
```

`clips_path` should contain one subfolder per character (e.g. `THOR\`, `SQUIRREL_GIRL\`).
The pipeline presents a menu to pick which character to process.

## KO detection standalone

```bash
python src/ko_detect.py                  # ground truth test
python src/ko_detect.py <clip_path>      # single clip (debug output)
python src/ko_detect.py --batch vid1     # batch scan → writes timestamps .txt
```

## Repo structure

```
src/
  main.py               entry point
  pipeline.py           main orchestrator
  clip_scanner.py       scan folder, probe durations in parallel
  batcher.py            group clips into ~15-min batches
  encoder.py            FFmpeg concat encode (NVENC / libx264 fallback)
  description_writer.py write YouTube description .txt
  ko_detect.py          KO banner detection (OCR) — standalone + imported by pipeline
scripts/
  run.bat               double-click launcher (Windows Terminal / Git Bash)
  run.sh                runs python src/main.py from repo root
tests/                  pytest test suite (run with: pytest)
data/
  cache/                per-clip KO scan results (*.ko.json)
  output/               generated description files
  examples/             reference screenshots and ground truth frames
docs/
  IDEAS.md              future work
  MULTIKILL_DETECTION.md
tools/                  ffmpeg.exe + ffprobe.exe (not tracked — provide your own)
config/
  config.json           your local config (gitignored)
  config.example.json   template — copy to config.json and edit
```

## Requirements

- Windows
- Python 3.10+
- `pip install pytesseract Pillow`
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (`winget install UB-Mannheim.TesseractOCR`)
- FFmpeg — place `ffmpeg.exe` + `ffprobe.exe` in `tools/`
- NVIDIA GPU recommended (NVENC) — falls back to CPU (libx264) automatically
