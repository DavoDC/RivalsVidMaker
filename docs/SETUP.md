# Setting up RivalsVidMaker

One-time setup takes about ten minutes. You need Windows and Python 3.10 or newer; an NVIDIA GPU helps but is not required (it falls back to the CPU automatically).

## 1. Install the dependencies

```bash
# Python packages
pip install pytesseract Pillow imagehash questionary google-auth-oauthlib send2trash nicegui

# Tesseract OCR (reads the multi-kill banners)
winget install UB-Mannheim.TesseractOCR
```

FFmpeg downloads itself on first run (official builds, extracted to `dependencies/ffmpeg/`). Nothing to install by hand.

## 2. Point it at your clips

Copy `config/config.example.json` to `config/config.json` (gitignored) and set your folders:

- `clips_path`: where Marvel Rivals saves highlights (the game's `Highlights` folder).
- `output_path`: where finished videos and their descriptions go.
- `archive_path`: where Quad+ clips are kept for future best-of videos.
- `tesseract_path`: usually `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- `youtube_channel_id`: your channel, so uploads can never go to the wrong one.
- `target_batch_seconds`: video length, 900 for 15 minutes.

## 3. Connect YouTube (optional)

The first time you upload, RivalsVidMaker opens a Google sign-in in your browser. The token is saved to `config/token.json` (gitignored) for later uploads. Background detail: [YOUTUBE_API.md](YOUTUBE_API.md).

## 4. Run it

- **GUI:** double-click `scripts/gui.bat`. It runs on your own machine at 127.0.0.1 only and opens in your browser.
- **Terminal menu:** double-click `scripts/run.bat` for the arrow-key menu (compile, pre-process, manage outputs, browse the archive). It still covers every action while the GUI catches up.

## Command line

```bash
PYTHONPATH=src python -m gui --launch   # start the GUI and open the browser
PYTHONPATH=src python -m gui --stop     # stop it
python src/main.py                      # terminal menu, uses config/config.json
python src/main.py --force              # re-encode even if the output already exists
python src/ko_detect.py                 # try multi-kill detection on its own
pytest                                  # run the tests
```

Every run writes a timestamped log under `data/logs/`.

## How the pieces fit

```
Highlights/CHAR/     raw clips, saved in game
   -> sort, scan, batch, merge, describe, upload
Output/CHAR_DATE/    finished MP4, description, source clips
   -> clean up: Quad+ to the archive, the rest to the recycle bin
ClipArchive/CHAR/    your best kills, never deleted automatically
```

- **Multi-kill detection:** FFmpeg samples each clip at 2 fps, the kill banner is cropped and cleaned up, Tesseract reads the tier, and a short cooldown stops one banner counting twice. Results are cached per clip, so a re-run is instant. Full method: [MULTIKILL_DETECTION.md](MULTIKILL_DETECTION.md).
- **Fast merging:** Marvel Rivals clips share one format (H.264, 1920x1080, AAC), so they are joined by stream copy with no re-encoding, which takes seconds instead of minutes.
- **Descriptions:** each video gets a description with a clickable timestamp for every Quad, Penta and Hexa. Title and wording guide: [YOUTUBE_TITLE_AND_DESC.md](YOUTUBE_TITLE_AND_DESC.md).

## Built with

Python, [FFmpeg](https://ffmpeg.org/), [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki), imagehash and Pillow for duplicate checks, NiceGUI for the GUI, questionary for the terminal menu, and the YouTube Data API through google-auth-oauthlib.
