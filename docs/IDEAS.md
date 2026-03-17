# Ideas & Future Work

## High-priority / structural

### ~~Consolidate docs/ folder~~ ✅ DONE
`docs/` is now 3 files: `GROUND_TRUTH.md`, `CompilationVidMaker-Research.md`, `IDEAS.md`.

### Reorganise repo structure (matches SBS_Download layout)
The repo is messy — inconsistent folder names, C++ VS project folders mixed in, `tools/`
instead of `dependencies/`, no `.gitkeep` sentinels (DEFINITELY ADD), etc. Decide on a clean structure
before the Python rewrite lands so the rewrite drops files in the right places.

**Target layout (mirroring SBS_Download):**
```
dependencies/       ffmpeg/ (ffmpeg.exe, ffprobe.exe — gitignored), README.md
data/               cache/     — *.ko.json scan cache (tracked)
                    logs/      — runtime logs (.gitkeep tracked, logs gitignored)
src/                Python source modules (ko_detect.py + future pipeline modules)
tests/              pytest tests
scripts/            run.bat / run.sh entry-point launchers
docs/               PRIORITIES.md, TTD.md, IDEAS.md, research docs
examples/           ground_truth/, ko_frames/, descriptions/, issues/
CLAUDE.md           (root)
README.md           (root)
.gitignore          (root)
config.txt          (root, or move to data/)
```

**What to remove / archive:**
- `Project/` — VS 2022 solution + vcxproj (archive or delete once C++ is retired)
- `config/` — fold config.txt up to root (or `data/`)
- `tools/` — rename to `dependencies/` (add README.md like SBS_Download)

**`.gitkeep` pattern:** empty-but-tracked folders (e.g. `data/logs/`) get a `.gitkeep`
so git doesn't lose the folder, matching SBS_Download convention.

### Rewrite pipeline in Python
Replace the C++ pipeline entirely with Python (matching the SBS Downloader repo structure).
Encoder, batcher, clip list, description writer — all in Python alongside `ko_detect.py` (in 'src' folder).
Simpler to maintain, easier to iterate on.

### Run KO detection at clip-ingest stage
Currently detection runs at batch time. Running it earlier (when clips first land) allows
all clips to be processed in parallel, and results are ready before batching begins.
Encode KO info into the clip filename (see below) at this stage.

### Encode KO tier in clip filename
After detection, rename clips to embed their max KO classification:

    THOR_2026-03-16_22-18-00.mp4  →  THOR_2026-03-16_22-18-00_QUAD.mp4

Benefits:
- Instantly reviewable — open clip, filename tells you what to expect
- Description generation can read tier from filename (no re-scan needed)
- Enables future "Best of" compilations: filter by `_PENTA` or `_HEXA` without
  re-processing anything

### Document full pipeline end-to-end
Write a reference doc (or update CLAUDE.md) describing the complete workflow:
clip ingest → KO detection → batching → encode → description → YouTube upload.
Useful for onboarding Claude in future sessions.

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
