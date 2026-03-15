# Compilation Vid Maker (CVM)

A C++ console program that automates building ~15-minute YouTube compilation videos from short gameplay clips.

## What it does

1. **Scans** a `Clips/` folder for video files
2. **Batches** clips into ~15-minute groups based on duration
3. **Encodes** each batch into a single MP4 using FFmpeg with GPU acceleration (NVENC on NVIDIA, CPU fallback)
4. **Generates** a YouTube description `.txt` per batch with:
   - List of original clip filenames
   - Timestamps for any multi-kill events detected in filenames (Quadra / Penta / Hexa Kill)

## Setup

1. Download [FFmpeg](https://github.com/GyanD/codexffmpeg/releases) and place `ffmpeg.exe` + `ffprobe.exe` in the `FFMPEG/` folder
2. Drop your clips into the `Clips/` folder
3. Open `Project/CompilationVidMaker.sln` in Visual Studio and build (Release x64)
4. Run the executable — encoded videos and descriptions appear in `Output/`

## Folder structure

```
CompilationVidMaker/
├── Code/        Source files
├── Project/     Visual Studio solution and project
├── FFMPEG/      Place ffmpeg.exe and ffprobe.exe here
├── Clips/       Drop input clips here
└── Output/      Encoded MP4s and description .txt files go here
```

## Requirements

- Windows
- Visual Studio 2022 (v143 toolset, C++20)
- FFmpeg (ffmpeg.exe + ffprobe.exe) — place in `tools/`
- NVIDIA GPU recommended (NVENC) — falls back to CPU automatically

### KO detection script (`scripts/ko_detect.py`)

Additional requirements for the Python OCR-based kill detection:

- Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — install via:
  ```
  winget install UB-Mannheim.TesseractOCR
  ```
  Installs to `C:\Program Files\Tesseract-OCR\` (expected path, no config needed)
- Python packages: `pip install pytesseract Pillow`

## Kill detection

Clip filenames are scanned for multi-kill keywords (case-insensitive):
- `quadra` / `quad` → **Quadra Kill**
- `penta` → **Penta Kill**
- `hexa` → **Hexa Kill**

Detected kills are added as timestamps to the YouTube description.

## Architecture

Modelled after [CoverVidMaker](https://github.com/DavoDC/CoverVidMaker). Core classes:

| Class | Role |
|---|---|
| `Command` | Wraps Windows `CreateProcessA` to run FFmpeg/FFprobe |
| `Clip` | Single video clip with path and duration |
| `ClipList` | Scans `Clips/` folder, queries durations via FFprobe |
| `Batcher` | Groups clips into ~15-min batches |
| `KillDetector` | Scans filenames for kill tier keywords, records timestamps |
| `Encoder` | FFmpeg NVENC encode per batch (concat demuxer) |
| `DescriptionWriter` | Writes YouTube description `.txt` per batch |
| `Processor` | Orchestrates the full pipeline |
