# Ideas & Future Work

## High-priority / structural

### Consolidate docs/ folder (no data loss)
The `docs/` folder has too many files with significant duplication. Target: 3 files.

**Files to delete (fully superseded):**
- `PRIORITIES.md` — entirely covered by CLAUDE.md's "Current focus" section
- `compilationvidmaker.md` — old project overview + old bugs; ~90% superseded by CLAUDE.md.
  One unique item (YouTube API lower-priority list) is already captured in IDEAS.md.

**Files to relocate (wrong folder):**
- `vid1_timestamps.txt` → `data/` (it's generated output, not a doc)
- `full_vid_scan_test.txt` → `data/logs/` or delete (raw terminal output log)

**Files to merge then delete:**
- `NOTES.md` — KO banner position, colour table, reference screenshot index, scan params.
  Unique content should be merged into `GROUND_TRUTH.md`, then `NOTES.md` deleted.

**Files to keep (each has unique content):**
- `GROUND_TRUTH.md` — ground truth reference for KO detection (absorbs NOTES.md)
- `CompilationVidMaker-Research.md` — YouTube API deep-dive research, not duplicated anywhere
- `IDEAS.md` — this file

### Reorganise repo structure (matches SBS_Download layout)
The repo is messy — inconsistent folder names, C++ VS project folders mixed in, `tools/`
instead of `dependencies/`, no `.gitkeep` sentinels, etc. Decide on a clean structure
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

### Review `full_vid_scan_test.txt`
Output from a full-video scan test is in `docs/full_vid_scan_test.txt`.
Review findings and incorporate any useful tuning into `ko_detect.py`.
