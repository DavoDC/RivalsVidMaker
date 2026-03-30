# Manual Testing Checklist

Comprehensive end-to-end verification for RivalsVidMaker.
Run through this checklist after any significant change, or before a new batch.

---

## 0. Environment Setup Verification

Run these checks before anything else.

- [ ] Python 3.10+ installed: `python --version`
- [ ] pytesseract and Pillow installed: `pip show pytesseract Pillow`
- [ ] Tesseract OCR binary exists at the path in `config/config.json`
  - Default: `C:\Program Files\Tesseract-OCR\tesseract.exe`
  - Quick test: `"C:\Program Files\Tesseract-OCR\tesseract.exe" --version`
- [ ] `dependencies/ffmpeg/ffmpeg.exe` and `dependencies/ffmpeg/ffprobe.exe` exist (or the configured path)
  - Quick test: `dependencies/ffmpeg/ffmpeg.exe -version`
- [ ] `config/config.json` exists and has required fields:
  - `clips_path` — path to `Highlights\` folder
  - `output_path` — path to `Output\` folder
  - `ffmpeg_path` — folder containing `ffmpeg.exe` and `ffprobe.exe`
  - See `config/config.example.json` for the template
- [ ] `Highlights\` folder exists at the configured path
- [ ] At least one character subfolder with `.mp4` clips exists
- [ ] Unit tests pass: `pytest` from repo root → should show all green

---

## 1. Startup & Folder Status Display

**Run:** `python src/main.py` (or double-click `scripts/run.bat`)

**Expected terminal output:**
```
==================================================
             RivalsVidMaker
==================================================
Log: data/logs/run_YYYYMMDD_HHMMSS.log
========================================================
            MarvelRivals — Folder Status
========================================================

── HIGHLIGHTS ──
┌──────────┬───────┬──────────┬───────────┬────────────┐
│ Character │ Clips │ Duration │ KO cached │ Date range │
...
```

- [ ] Header prints correctly
- [ ] Log file path is shown (file should NOT exist yet if nothing has run)
- [ ] HIGHLIGHTS table shows correct character names and clip counts
- [ ] Duration column shows non-zero values (requires ffprobe to work)
- [ ] KO cached column shows `n/m` fractions correctly
- [ ] Date range column shows clip date ranges (e.g. `6 Feb '26 → 15 Mar '26`)
- [ ] OUTPUT table shows any existing output folders
- [ ] ARCHIVE table shows archived clip count (or "(archive is empty...)")
- [ ] Character selection menu appears after the tables

**Failure modes:**
- `FileNotFoundError: Clips path not found` → check `clips_path` in config.json
- `ffprobe` shows duration as `—` for all clips → ffprobe binary not found or wrong path
- Table shows `0` clips → character subfolders exist but contain no `.mp4` files

---

## 2. Clip Auto-Sort (sort_clips)

**Setup:** Place one or more unsorted `.mp4` clips directly in the `Highlights\` root.
Clip names must follow the convention: `THOR_2026-03-01_22-38-56.mp4`

**Expected:**
- Clips moved to `Highlights\THOR\` automatically on startup
- Terminal shows: `Sorting clips... 1 file(s) moved.`
- Log file shows `DEBUG Moving: THOR_2026-03-01_22-38-56.mp4 → THOR/`

**Check:**
- [ ] Clip no longer exists in `Highlights\` root
- [ ] Clip exists in `Highlights\THOR\THOR_2026-03-01_22-38-56.mp4`
- [ ] HIGHLIGHTS table now includes the clip in the THOR row

**Edge cases to verify:**
- [ ] Clips with spaces in character name: `SQUIRREL GIRL_2026-03-01_22-38-56.mp4` → `Highlights\SQUIRREL_GIRL\`
- [ ] Clips with unrecognised filenames are NOT moved (no date pattern → WARNING in log)
- [ ] If destination already exists: source clip stays, WARNING logged, no overwrite

---

## 3. Pre-process Mode (KO cache warming)

**Setup:** Have at least one uncached clip in a character folder.
Delete cache for a clip: remove `data/cache/THOR/YYYY-MM/<stem>.ko.json`

**Run:** At the character menu, press `P` (then Enter)

**Expected:**
```
Pre-processing 9 clip(s) across 1 character folder(s)...
[1/9] Scanning THOR_2026-02-06_22-38-56.mp4...
[1/9] Done (4.2s) — QUAD
[2/9] [cached] THOR_2026-02-17_23-25-25.mp4
...
Pre-processing complete — 9 clip(s) in 42.3s
```

- [ ] Each uncached clip is scanned (shows timing)
- [ ] Each cached clip is skipped (shows `[cached]`)
- [ ] Cache files created: `data/cache/CHAR/YYYY-MM/<stem>.ko.json`
- [ ] After pre-process, menu re-displays and `[P]` option is shown again
- [ ] KO cached column in HIGHLIGHTS table now shows all cached

**Failure modes:**
- OCR errors / blank tier results → check Tesseract path in config
- `FileNotFoundError` for ffmpeg → check ffmpeg path in config
- Very slow (>10s per clip) → normal if Tesseract is cold; subsequent runs will use cache

---

## 4. Character Selection & Batch Confirmation

**Run:** At the character menu, enter the number for a character with clips.

**Expected:**
```
┌───┬───────────┬───────┬──────────┬─────────┬──────────┬─────────────┐
│ # │ Character │ Clips │ Duration │ Batches │ Status   │ Date Range  │
├───┼───────────┼───────┼──────────┼─────────┼──────────┼─────────────┤
│ 1 │ THOR      │ 9     │ 12m 34s  │ ~1      │ ✓ Ready  │ ...         │
└───┴───────────┴───────┴──────────┴─────────┴──────────┴─────────────┘
Make this video? Estimated processing time: ~3m 00s. [y/N]:
```

- [ ] Selected row is highlighted (re-shown alone)
- [ ] Estimated processing time is shown (non-zero)
- [ ] Entering `N` cancels cleanly: `Cancelled.` and returns to prompt
- [ ] Entering `Y` proceeds to KO scanning

**Status column checks:**
- `✓ Ready` — enough clips for a full batch (≥15 min)
- `~ Almost` — 75–99% of target duration
- `✗ Too short` — less than 75% of target
- `— No clips` — folder exists but no clips found

---

## 5. KO Detection (during pipeline run)

After confirming `Y`, KO scanning begins.

**Expected:**
```
Scanning for KO events...
KO scan [1/9]: [cached] THOR_2026-02-06_22-38-56.mp4 -> Done (0.0s) — QUAD
KO scan [2/9]: THOR_2026-02-17_23-25-25.mp4 -> Done (4.2s) — TRIPLE
KO scan [3/9]: THOR_2026-03-01_22-38-56.mp4 -> Done (3.8s)
...
3 Quad+ kill(s) found.
```

- [ ] Each clip is listed as scanned or cached
- [ ] Cached clips are instant (0.0s)
- [ ] Tier is shown after the dash (QUAD, TRIPLE, etc.) where detected
- [ ] Count of Quad+ kills is reported
- [ ] If no Quad+ kills: `(no Quad+ kills detected)` appears

**Failure modes:**
- Hangs on a clip → ffmpeg or Tesseract is stuck; Ctrl+C to abort
- All results show no tier → OCR misconfigured; run `python src/ko_detect.py <clip>` to debug
- Missing cache after pre-process → check `cache_dir` in config.json points to the right place

---

## 6. Encoding

**Expected output:**
```
Encoding THOR_Feb-Mar_2026 (12m 34s)...
Encoded → C:\...\Output\THOR_Feb-Mar_2026\THOR_Feb-Mar_2026.mp4
```

- [ ] Output `.mp4` file exists in the expected output folder
- [ ] File size is non-trivial (not 0 bytes)
- [ ] Log contains the FFmpeg command at DEBUG level
- [ ] If GPU (NVENC) is used: log shows `Encoder: NVENC (GPU)`
- [ ] If CPU fallback: log shows `Encoder: libx264 (CPU)`

**Failure modes:**
- `FFmpeg failed (exit 1)` → check log file for full ffmpeg stderr output
- Output file is tiny (<1 MB) → ffmpeg ran but produced corrupt output; check clip paths
- `check_nvenc` takes a long time → normal on first run

---

## 7. Description File

**Expected:**
- File created: `Output\THOR_Feb-Mar_2026\THOR_Feb-Mar_2026_description.txt`
- Terminal: `Description → <path>`

**Check the description file content:**
- [ ] `=== TITLE ===` section with character name and batch number
- [ ] `=== DESCRIPTION ===` section with duration
- [ ] `=== TIMESTAMPS ===` section present **only if** Quad+ kills were detected
  - Format: `1:36 - 1:45 = Quad Kill`
  - Timestamps use M:SS format
- [ ] `=== HIGHLIGHTS ===` section lists all clips, numbered
  - Clips with detected kills show `[QUAD]` / `[TRIPLE]` / etc. suffix
- [ ] Clip count in HIGHLIGHTS matches the batch size

---

## 8. Clip Move (Output/clips/)

**Expected:**
- Terminal: `Clips → <path>/clips  (N moved)`
- Each clip moved from `Highlights\THOR\` to `Output\THOR_Feb-Mar_2026\clips\`
- Clips with detected tiers renamed: `THOR_2026-02-06_22-38-56_QUAD.mp4`
- Clips without detected tiers: original name preserved

**Check:**
- [ ] `Highlights\THOR\` is now empty (all clips moved)
- [ ] `Output\THOR_Feb-Mar_2026\clips\` contains all clips
- [ ] KO-tier clips have the correct `_TIER` suffix
- [ ] No clips were silently dropped (count should match)

**Failure modes:**
- `Failed to move <clip>` in log → permissions issue or clips folder locked
- Clip destination already exists warning → a previous run may have partially moved clips

---

## 9. KO Detection — Standalone Testing

Use this to debug detection issues without running the full pipeline.

**Ground truth test (THOR vid1 clip):**
```
python src/ko_detect.py
```
Expected:
```
RESULT:  QUAD KILL
Tier:   PASS  (got QUAD, want QUAD)
Start:  PASS  (got 0:06, want ~0:06)
```

**Single clip debug:**
```
python src/ko_detect.py "C:\path\to\clip.mp4"
```
- [ ] Prints per-frame tier detections
- [ ] Shows final result: tier, streak start/end, all events

**Batch scan (legacy vid1/vid2):**
```
python src/ko_detect.py --batch vid1
```
- [ ] Scans all clips in `vid1_uploaded`
- [ ] Writes `data/output/vid1/vid1_timestamps.txt`
- [ ] Quad+ timestamps match verified list in CLAUDE.md

---

## 10. End-to-End Log Verification

After a full run, open `data/logs/run_YYYYMMDD_HHMMSS.log`:

- [ ] Log file exists and is non-empty
- [ ] All INFO messages from terminal appear in the log
- [ ] DEBUG messages appear in the log (ffmpeg commands, per-clip details)
- [ ] No unexpected `[ERROR]` or `[WARNING]` entries
- [ ] Final line: `>>> Encoding complete! Please check the output video. <<<`

---

---

## 11. Skip-if-Exists (Encode)

**Setup:** Run the pipeline once to produce an output `.mp4`. Then run again without `--force`.

**Expected:**
```
[WARNING] Output already exists: <path>. Use --force to re-encode.
```

- [ ] Second run skips FFmpeg — no `Encoding ...` message
- [ ] Output file is unchanged (same size, same mtime)
- [ ] Log contains the warning at WARNING level

**Test --force:**

Run `python src/main.py --force` after an existing output exists.

- [ ] `[--force mode: existing output files will be re-encoded]` shown in menu
- [ ] FFmpeg runs and produces a new output file (mtime changes)

---

## 12. Cache Mtime Invalidation

**Setup:** Run the pipeline on a clip to populate its cache entry.
Then replace the clip file (copy a different clip to the same filename, or `touch` the file
to update its mtime).

**Expected on next run:**
- [ ] Log shows `Cache stale (mtime mismatch), re-scanning: <clip_name>` at DEBUG level
- [ ] The clip is re-scanned (not `[cached]` in the terminal output)
- [ ] New cache entry is written with updated mtime

**Verify:**
- [ ] The `.ko.json` cache file has been updated (new mtime on the cache file itself)
- [ ] The new KO result reflects the new clip content

---

## 13. AI Prompt Output

After a full pipeline run:

- [ ] File created: `Output\<slug>\<slug>_ai_prompts.md`
- [ ] Terminal shows: `AI prompts → <path>`
- [ ] File contains three prompt sections (Prompt 1, Prompt 2, Prompt 3)
- [ ] Character name appears in the prompts
- [ ] Detected KO tier summary appears (or "(no Quad+ kills detected)" if none found)
- [ ] Date range appears in the prompts

**Check the file manually:**
Open the file and verify you could paste Prompt 3 directly into Claude/ChatGPT
and get a useful YouTube title + description back.

---

## 14. Cleanup Dry Run

From a Python shell or test:

```python
from pathlib import Path
from cleanup import run_cleanup

run_cleanup(
    output_folder=Path("C:/Videos/MarvelRivals/Output/THOR_Feb-Mar_2026"),
    archive_path=Path("C:/Videos/MarvelRivals/ClipArchive"),
    dry_run=True,
)
```

**Expected:**
- [ ] `[DRY RUN] No files will be moved or deleted.` printed first
- [ ] All clips listed with their KO tier
- [ ] Quad+ clips listed as "to archive"
- [ ] Remaining clips listed as "to delete"
- [ ] Compiled .mp4 size shown
- [ ] Nothing actually moved or deleted (verify files still exist)
- [ ] No prompts shown (dry_run bypasses all user confirmation)

---

## Common Failure Patterns

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Duration columns all `—` | ffprobe not found | Check `ffmpeg_path` in config.json |
| KO scan hangs | Tesseract not found or wrong path | Check `tesseract_path`; run `tesseract --version` |
| All clips show no tier | OCR misconfigured | Run standalone: `python src/ko_detect.py <clip>` |
| `FileNotFoundError: Clips path not found` | Wrong `clips_path` in config | Verify the path exists |
| `KeyError: clips_path` | Missing field in config.json | Copy from `config/config.example.json` |
| `FFmpeg failed (exit 1)` | Bad clips or codec issue | Check log for full ffmpeg stderr |
| Clip not moved after encode | Permissions or path issue | Check log for `Failed to move` entries |
| Cache files not created | Wrong `cache_dir` or permissions | Verify `data/cache/` is writable |
