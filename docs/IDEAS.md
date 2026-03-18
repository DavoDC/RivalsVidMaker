# Ideas & Future Work

## High-priority / structural

### ~~Consolidate docs/ folder~~ ✅ DONE
`docs/` is now 3 files: `GROUND_TRUTH.md`, `YOUTUBE_API.md`, `IDEAS.md`.

### ~~Reorganise repo structure~~ ✅ DONE
C++ removed, Python pipeline in `src/`, `tests/`, `scripts/`, `config/`, `.gitkeep` in `tools/`, clean `.gitignore`. `tools/` kept as-is rather than renamed to `dependencies/`.

### Rewrite pipeline in Python
Replace the C++ pipeline entirely with Python (matching the SBS Downloader repo structure).
Encoder, batcher, clip list, description writer — all in Python alongside `ko_detect.py` (in 'src' folder).
Simpler to maintain, easier to iterate on.

### Run KO detection at clip-ingest stage
Currently detection runs at batch time. Running it earlier (when clips first land) allows
all clips to be processed in parallel, and results are ready before batching begins.
Encode KO info into the clip filename (see below) at this stage.

### Encode KO tier in clip filename (actual file rename at runtime)
During program execution, physically rename the source clip files in the highlights folder
to embed their max KO classification:

    THOR_2026-03-16_22-18-00.mp4  →  THOR_2026-03-16_22-18-00_QUAD.mp4

This is a real `os.rename()` on disk — not just a label in the description output.
The HIGHLIGHTS section of the description then naturally reflects the renamed files.

Benefits:
- Instantly reviewable on disk — filename tells you what to expect before opening
- Description generation reads tier from filename (no re-scan needed)
- Enables future "Best of" compilations: filter by `_PENTA` or `_HEXA` without
  re-processing anything

### Auto-download FFmpeg if missing
On startup, check whether `ffmpeg.exe` / `ffprobe.exe` exist at the configured path.
If not, automatically download and extract the latest FFmpeg Windows build (same pattern
as `C:\Users\David\GitHubRepos\SBS_Download`). No manual setup required for new machines.

### Startup clip availability check + video recommendations
On launch, scan the highlights folder, group clips by character, tally total duration per group,
and recommend compilations that can be made (e.g. "15-min Thor vid: 30 clips available").
If no character has enough clips for a full video, say so explicitly.
User selects a recommendation (or dismisses if nothing is ready).
This replaces the current manual "pick a batch folder" step.

### Full automation: generate video + title + description from clips
The ideal end state for this program: point it at a folder of clips and it outputs a ready-to-paste
YouTube upload — compiled video, title, description, and timestamps — with zero manual work.
Currently the description and title are written by hand after running the script.
Reference format: `docs/YOUTUBE_TITLE_AND_DESC.md`.

### AI prompt generation for title & description
At the end of the pipeline (after timestamps are written), generate a markdown file containing
pre-filled AI prompts the user can paste into Claude/ChatGPT to produce the YouTube title and description.
Prompts include: character name, clip count, date range, detected KO tiers, and canonical format reference.
Terminal output at the end of the run points the user at the file:

    ✅ Done! AI prompts saved → data/output/vid3/vid3_ai_prompts.md

Faster than writing prompts from scratch each upload.

### Show KO tier in HIGHLIGHTS list
In the generated description, append the detected tier to each clip filename:
```
HIGHLIGHTS:
6. THOR_2026-02-21_20-47-21.mp4 [HEXA]
```
Makes it easy to spot which clip is which without watching the video.

### Document full pipeline end-to-end
Write a reference doc (or update CLAUDE.md) describing the complete workflow:
clip ingest → KO detection → batching → encode → description → YouTube upload.
Useful for onboarding Claude in future sessions.

### Test on a different character
Run the full pipeline on a fresh batch of clips for a non-Thor character (e.g. Squirrel Girl)
to confirm detection works character-agnostically — different banner colour, different UI skin.
Good regression check before expanding beyond Thor.

### Automated tests for KO detection
Add a `tests/` folder with pytest tests covering `scan_clip` and OCR logic. Key questions to resolve:
- **Test clip strategy:** do we commit a very short clip (~5s) to the repo as a fixture?
  Pros: fully self-contained, CI-friendly. Cons: binary in git, repo size.
  Alternative: a tiny synthetic test image of the banner crop (just a PNG, ~50KB) to test
  OCR in isolation without needing a real video file.
- Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier
  correctly from known crop images, cache hit/miss behaviour, range format output.

---

## Lower priority / future

### Best-of compilation
A "Best of 2025/2026" video pulling only Penta and Hexa clips.
Made trivial once clips are named with their KO tier (see above).

### ~~Review `full_vid_scan_test.txt`~~ ✅ DONE
All 7 Quad kills in vid1 confirmed accurate. Timestamp range format confirmed
(`<streak start> - <max tier time> = Quad Kill`). Detection is solid.

### Speed up ko_detect.py batch scans
Batch scans take a long time (~3–9s per clip × 33 clips = up to 5 min). Ideas:
- **Parallel clip scanning** — `concurrent.futures.ProcessPoolExecutor` (or `ThreadPoolExecutor`).
  Each clip is independent so embarrassingly parallel. Could cut total time by `N_WORKERS`x.
- **Per-clip timing logs** — print elapsed time per clip and total batch time so we can see
  where time is going (FFmpeg extract vs OCR vs I/O). Use `time.perf_counter()`.
- Note: cache hits are already instant — this only matters for first-run / uncached clips.

### Rename repo/project to reflect Marvel Rivals focus
The program is Marvel Rivals-specific but the repo is named `CompilationVidMaker` (generic).
Should be renamed to something like `MarvelRivalsCompiler` or `MarvelRivalsVidMaker`.

### Pipeline improvements (lower priority backlog)
- Description format overhaul
- Group clips by output video in UI
- Skip-if-exists logic (don't re-encode already-built batches)
- Time estimation (how long will this batch take?)
