# Compilation Vid Maker (CVM)

Automates building ~15-minute YouTube compilation videos from short Marvel Rivals gameplay clips.

## What it does

1. **Scans** a character's clip folder and batches clips into ~15-minute groups by duration
2. **Detects** multi-kill events (Quad / Penta / Hexa) in each clip via OCR (Tesseract)
3. **Encodes** each batch into a single MP4 using FFmpeg (NVENC GPU, CPU fallback)
4. **Generates** a YouTube description `.txt` per batch with clickable multi-kill timestamps

## Setup

```bash
pip install pytesseract Pillow
winget install UB-Mannheim.TesseractOCR
```

Place `ffmpeg.exe` + `ffprobe.exe` in `tools/`.

Edit `config/config.json` (copy from `config/config.example.json`):

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

## Usage

```bash
scripts/run.bat              # Windows launcher (Git Bash terminal)
python src/main.py           # or run directly

pytest                       # run tests
```

## Requirements

- Windows, Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- FFmpeg in `tools/`
- NVIDIA GPU recommended (NVENC) — falls back to CPU automatically
