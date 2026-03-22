# Ideas & Future Work

## Architecture: state-driven pipeline (major redesign)

### State-driven pipeline with clear stages
Replace the current linear run-once pipeline with a stage-aware model where the program
tracks which stage each clip/batch is in and only progresses clips forward when the user
confirms. Stages:

```
intake → KO detection → (batch) selection → compilation → cleanup
```

On startup, the program scans all three video folders and displays a clear status table
showing every character group and what state their clips are in — how many are uncompiled,
what batches are pending, what Output folders exist and whether they've been confirmed on
YouTube. The user then selects which stage to advance, rather than the program running the
whole pipeline automatically.

**Safety and idempotency requirements:**
- Safe to re-run without duplicating work or re-processing already-handled clips.
- Dry-run mode for all destructive actions (any deletion or move that can't be undone).
- Explicit user confirmation required before any deletion or file move — list every file
  that will be affected before proceeding.
- Partial failure resilience: if the program is interrupted mid-stage (e.g. encode crashes),
  re-running must pick up from the last safe checkpoint, not restart from scratch.

### State log (JSON)
A simple per-session or persistent JSON file tracking which clips have been processed,
which stage they're in, and what their KO detection results are. Used to:
- Skip re-processing clips that have already been through KO detection.
- Know which clips belong to which output batch.
- Track whether an Output folder has been YouTube-confirmed.

Keyed by clip filename + modified time (or file hash) so it survives renames gracefully.
Stored alongside the cache (e.g. `data/state.json`).

### Caching layer (persistent, keyed, invalidation-aware)
KO detection is expensive (~3–9s per clip). Cache results in a persistent JSON store keyed
by `(filename, file_modified_time)` or file hash. On re-run, skip any clip whose key matches
— use the cached result directly.

Cache invalidation: if a file is modified or replaced, its key changes and it gets
re-processed. The cache must never silently serve stale results.

Null in cache = "scanned, no kill found" — a valid result, not a missing entry.
Cache must integrate with the state log so the two never contradict each other.
Already partially implemented (`data/cache/<char>/<clip_stem>.ko.json`) — this idea
upgrades it to be keyed on file identity rather than just filename.

### Startup state display
On launch, show the state of ALL folders under `C:\Users\David\Videos\MarvelRivals\` —
not just Highlights — with a separate titled table for each:

**Highlights** — clips waiting to be compiled:
```
Character    Clips    Total duration    KO scanned?
THOR         9        12m 34s           ✅ all cached
STORM        4        5m 12s            — not scanned
```

**Output** — compiled videos and their status:
```
Folder               Video              YouTube confirmed
THOR_FEB-MAR_2026    THOR_FEB-MAR_...   ✅
STORM_MAR_2026       STORM_MAR_...      — pending
```

**ClipArchive** — archived Quad+ clips:
```
Clips    Characters
12       THOR (7), STORM (5)
```

User picks what to do next. Nothing runs automatically without selection.

### Output folder cleanup workflow
After the user confirms a YouTube video is live and looks good:
1. Program lists every clip in `Output\CHARACTER_DATE\clips\` with its KO tier.
2. Identifies Quad+ clips — proposes moving them to `ClipArchive\`.
3. Identifies remaining clips — proposes deletion.
4. Shows compiled `.mp4` size — asks whether to delete to save disk space.
5. User confirms each action (or confirms all at once via dry-run preview).
6. Only then are files moved/deleted. No silent cleanup.

### Clip KO-tier rename at compilation stage
When clips are moved into `Output\CHARACTER_DATE\clips\` at compile time, physically rename
each file to embed its max detected KO tier:

    THOR_2026-03-16_22-18-00.mp4  →  THOR_2026-03-16_22-18-00_QUAD.mp4
    THOR_2026-02-21_20-47-21.mp4  →  THOR_2026-02-21_20-47-21_HEXA.mp4
    THOR_2026-03-01_19-05-00.mp4  →  THOR_2026-03-01_19-05-00_NONE.mp4  (or no suffix)

This is a real `os.rename()` on the clips in the Output clips folder — not a label.
The HIGHLIGHTS section of the description naturally reflects the renamed files.
Makes it trivial to identify Quad+ clips for archiving without re-scanning.

**Legacy migration needed:** `thor_vid1\` and `thor_vid2\vid2_clips\` were compiled before
this program was fully set up. Their clips need a one-off KO-tier rename pass so they follow
the same convention (Quad+ can then be identified and moved to ClipArchive).

## High-priority / structural

### ~~Consolidate docs/ folder~~ ✅ DONE
`docs/` is now 3 files: `GROUND_TRUTH.md`, `YOUTUBE_API.md`, `IDEAS.md`.

### ~~Reorganise repo structure~~ ✅ DONE
C++ removed, Python pipeline in `src/`, `tests/`, `scripts/`, `config/`, `.gitkeep` in `tools/`, clean `.gitignore`. `tools/` kept as-is rather than renamed to `dependencies/`.

### Rewrite pipeline in Python
Replace the C++ pipeline entirely with Python (matching the SBS Downloader repo structure).
Encoder, batcher, clip list, description writer — all in Python alongside `ko_detect.py` (in 'src' folder).
Simpler to maintain, easier to iterate on.

### ~~Pre-process mode: KO scan all clips upfront~~ ✅ DONE
New `src/preprocess.py` module + `[P]` option in the main menu. Scans all clips
across all character folders, writes cache entries, and reports progress. Does
not batch, encode, or move any files.

### Run KO detection at clip-ingest stage
Currently detection runs at batch time. Running it earlier (when clips first land) allows
all clips to be processed in parallel, and results are ready before batching begins.
Encode KO info into the clip filename (see below) at this stage.

### ~~Encode KO tier in clip filename~~ → see Architecture section above
Detailed design moved to "Clip KO-tier rename at compilation stage" in the Architecture
section. Key decision: rename happens when clips move to `Output\clips\`, not in Highlights.

### Skip-if-exists for encoding
Before encoding a batch, check whether the output `.mp4` already exists. If it
does, print a notice and skip (rather than silently overwriting with the `-y`
flag). Re-encode can be forced with a `--force` flag or CLI option.
This prevents accidentally re-encoding a video that took minutes to produce.

### Dry-run mode
A `--dry-run` flag that prints everything the pipeline *would* do without
moving any files or running FFmpeg. Useful for:
- Previewing which clips will go into each batch before committing.
- Checking that KO detection results are sensible before encoding.
- Safe to run in any state — no files are touched.

### Cleanup command (post-YouTube workflow)
An interactive cleanup subcommand for after a video is confirmed live on YouTube:
1. List every clip in `Output\CHARACTER_DATE\clips\` with its KO tier.
2. Identify Quad+ clips — confirm moving them to `ClipArchive\`.
3. Identify remaining clips — confirm deletion with a per-file list.
4. Show compiled `.mp4` size — ask whether to delete.
5. Nothing happens until the user types `yes`.
This maps directly to the "Output folder cleanup workflow" in the Architecture
section and closes the loop on the full pipeline.

### Session history in startup display
In the Output table, add a "Days since encoded" column derived from the folder's
modification time. Lets you see at a glance which output folders are old and
ready to be cleaned up vs recently created.

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

### ~~Show KO tier in HIGHLIGHTS list~~ ✅ DONE
`write_description()` now accepts `clip_tiers` and annotates each clip line:
`6. THOR_2026-02-21_20-47-21.mp4 [HEXA]`

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

### ~~Speed up ko_detect.py batch scans~~ ✅ DONE
`_collect_highlights` in `pipeline.py` now scans clips in parallel using
`ThreadPoolExecutor` (N_WORKERS=4). Each clip writes to its own cache file so
there are no write conflicts. Cache hits are printed as `[cached]`. Per-clip
timing is logged.

### Rename repo/project to reflect Marvel Rivals focus
The program is Marvel Rivals-specific but the repo is named `CompilationVidMaker` (generic).
Should be renamed to something like `MarvelRivalsCompiler` or `MarvelRivalsVidMaker`.

### Arrow-key menu navigation
Replace number-typed menu selection with arrow-key navigation (highlight + Enter to confirm).
Cleaner UX — no mismatch errors, no need to read option numbers. Use `curses` or a library
like `simple-term-menu` / `inquirer` for the interactive prompt.

### Pipeline improvements (lower priority backlog)
- Description format overhaul
- Group clips by output video in UI
- Skip-if-exists logic (don't re-encode already-built batches)
- **Time estimation** — before starting a batch, show the user a rough estimate of how long
  the full run will take, broken into stages:
  - *KO scanning* — ~3–9s per uncached clip (cached = instant); estimate from clip count and cache hits
  - *Encoding* — rough heuristic from total batch duration (e.g. ~1× realtime for NVENC GPU)
  - *Total* — sum of above, formatted as "~4 min" or "~12 min"
  Shown after the menu selection and before processing begins, so the user knows whether to
  wait or walk away.
