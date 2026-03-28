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

### ~~Caching layer (persistent, keyed, invalidation-aware)~~ ✅ DONE
Cache results stored in `data/cache/<char>/<YYYY-MM>/<stem>.ko.json` keyed by
`(filename, file_mtime)`. On re-run, stale entries (mtime mismatch) are re-scanned.
Null = "scanned, no kill found" — valid result, not a missing entry.

### ~~Startup state display~~ ✅ DONE
`_print_multizone_status()` in `pipeline.py` shows all three folders (Highlights,
Output, Archive) in separate tables on launch.

### ~~Output folder cleanup workflow~~ ✅ DONE (skeleton)
`src/cleanup.py` — interactive cleanup with dry_run=True support. Lists clips with KO
tiers, proposes Quad+ → ClipArchive moves and remaining clip deletion, asks per-action
confirmation. Not yet wired into the main menu.

### ~~Clip KO-tier rename at compilation stage~~ ✅ DONE
`_move_clips()` in `pipeline.py` renames clips on move:
`THOR_2026-03-16_22-18-00.mp4 → THOR_2026-03-16_22-18-00_QUAD.mp4`.
Legacy vid1/vid2 clips still need a one-off migration pass (see Deferred section).

## High-priority / structural

### Protect 5 most-recent clips from batching/moving

**Context:** Marvel Rivals only shows the 5 most recently saved highlights in-game (Career > Favorites > Highlights > "RECENT HIGHLIGHTS 5/5"). David manually presses SAVE to write clips to disk. The 5 most recently created files in `Highlights\` on disk correspond exactly to what the game shows as "SAVED" in its UI. If RVM moves those clips, the game loses track of them - the "SAVED" status disappears from the thumbnail and it gets confusing.

**Requirement:** when scanning clips for a batch, always skip the N most recently created (by ctime/mtime) clips across the Highlights folder (default N=5). These clips stay untouched until newer clips are saved on top of them.

**Implementation sketch:**
- In `clip_scanner.py` or `pipeline.py`, after collecting all clips, sort by creation time descending.
- Exclude the first `N` from the candidate list before passing to the batcher.
- Make N configurable in `config.json` (key: `"protect_recent_clips": 5`).
- Show in startup display: "X clips available, Y protected (most recent - still live in game UI)".
- The protected clips are skipped silently; no error or warning needed.



### ~~Consolidate docs/ folder~~ ✅ DONE
`docs/` is now 4 files: `MULTIKILL_DETECTION.md`, `YOUTUBE_API.md`, `YOUTUBE_TITLE_AND_DESC.md`, `IDEAS.md`.

### ~~Reorganise repo structure~~ ✅ DONE
C++ removed, Python pipeline in `src/`, `tests/`, `scripts/`, `config/`, `.gitkeep` in `tools/`, clean `.gitignore`. `tools/` kept as-is rather than renamed to `dependencies/`.

### ~~Rewrite pipeline in Python~~ ✅ DONE
All pipeline stages (encoder, batcher, clip list, description writer) are in Python
alongside `ko_detect.py` in `src/`. C++ removed entirely.

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

### ~~Skip-if-exists for encoding~~ ✅ DONE
`encode()` in `src/encoder.py` checks if the output `.mp4` exists before running FFmpeg.
If it does, logs WARNING and returns the existing path. Pass `force_encode=True` to
re-encode. Pipeline menu mentions `--force` option.

### Dry-run mode
A `--dry-run` flag that prints everything the pipeline *would* do without
moving any files or running FFmpeg. Useful for:
- Previewing which clips will go into each batch before committing.
- Checking that KO detection results are sensible before encoding.
- Safe to run in any state — no files are touched.

### ~~Cleanup command (post-YouTube workflow)~~ ✅ DONE (skeleton)
`src/cleanup.py` — see Architecture section above.

### Session history in startup display
In the Output table, add a "Days since encoded" column derived from the folder's
modification time. Lets you see at a glance which output folders are old and
ready to be cleaned up vs recently created.

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

### ~~AI prompt generation for title & description~~ ✅ DONE
`src/ai_prompt.py` — writes `data/output/<slug>/<slug>_ai_prompts.md` after each
pipeline run. Includes character/clip count/date range/kill tier context and pre-filled
prompts (title, one-liner, and combined) following the canonical format in
`docs/YOUTUBE_TITLE_AND_DESC.md`. Wired into `pipeline.py` after description writing.

### ~~Show KO tier in HIGHLIGHTS list~~ ✅ DONE
`write_description()` now accepts `clip_tiers` and annotates each clip line:
`6. THOR_2026-02-21_20-47-21.mp4 [HEXA]`

### ~~Document full pipeline end-to-end~~ ✅ DONE
CLAUDE.md documents the complete workflow: clip ingest → sort → KO detection →
batching → encode → description. `docs/MANUAL_TESTING.md` covers end-to-end
testing steps.

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
- **Time estimation** — before starting a batch, show the user a rough estimate of how long
  the full run will take, broken into stages:
  - *KO scanning* — ~3–9s per uncached clip (cached = instant); estimate from clip count and cache hits
  - *Encoding* — rough heuristic from total batch duration (e.g. ~1× realtime for NVENC GPU)
  - *Total* — sum of above, formatted as "~4 min" or "~12 min"
  Shown after the menu selection and before processing begins, so the user knows whether to
  wait or walk away.

---

## Deferred / future (no near-term action needed)

### Auto-download FFmpeg if missing
On startup, check whether `ffmpeg.exe` / `ffprobe.exe` exist at the configured path.
If not, automatically download and extract the latest FFmpeg Windows build (same pattern
as `C:\Users\David\GitHubRepos\SBS_Download`). No manual setup required for new machines.

### Legacy KO-tier rename migration
`thor_vid1\` and `thor_vid2\vid2_clips\` were compiled before this program was fully set up.
Their clips need a one-off KO-tier rename pass so they follow the convention
(Quad+ can then be identified and moved to ClipArchive).
Low urgency — these videos are already published; just useful for archiving.
