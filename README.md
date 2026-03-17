# Compilation Vid Maker (CVM)

Automates building ~15-minute YouTube compilation videos from short Marvel Rivals gameplay clips.

## What it does

1. **Scans** clips, **batches** them into ~15-minute groups by duration
2. **Encodes** each batch into a single MP4 using FFmpeg (NVENC GPU acceleration, CPU fallback)
3. **Detects** multi-kill events (Quad / Penta / Hexa) in each clip via OCR
4. **Generates** a YouTube description `.txt` per batch with clickable multi-kill timestamps

## Current state

- **KO detection** (`scripts/ko_detect.py`) — active focus, Python + pytesseract OCR
- **Encoder / batcher** (`src/CppProject/`) — C++ (VS 2022), lower priority, planned Python rewrite

## Setup

### KO detection (Python)

```
pip install pytesseract Pillow
winget install UB-Mannheim.TesseractOCR
```

Place `ffmpeg.exe` + `ffprobe.exe` in `tools/`.

### Encoder (C++)

1. Open `src/CppProject/CompilationVidMaker.sln` in Visual Studio 2022
2. Build Release x64
3. Edit `src/CppProject/config.txt` with your paths

## Usage

```bash
# Detect multi-kill events in a batch of clips
python scripts/ko_detect.py --batch vid1

# Output: data/output/vid1/description.txt
```

## Repo structure

```
data/
  cache/          per-clip KO scan cache (*.ko.json)
  output/         generated description files
  examples/       reference screenshots and ground truth frames
docs/
  MULTIKILL_DETECTION.md   KO detection reference + ground truth
  YOUTUBE_API.md           YouTube API research + upload architecture
  IDEAS.md                 future work
scripts/
  ko_detect.py    KO detection script (active focus)
src/CppProject/   C++ encoder/batcher (lower priority)
tools/            ffmpeg.exe + ffprobe.exe (not tracked — provide your own)
```

## Requirements

- Windows
- Python 3.10+ with `pytesseract`, `Pillow`
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- FFmpeg (`ffmpeg.exe` + `ffprobe.exe`) in `tools/`
- Visual Studio 2022 (C++ encoder only)
- NVIDIA GPU recommended (NVENC) — falls back to CPU
