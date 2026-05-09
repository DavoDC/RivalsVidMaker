# Ideas & Future Work

Single source of truth for all pending work.

**Do not move to next tier until current tier is verified on real data.**

---

## TIER 0 (BLOCKING)

Work that blocks core functionality. Program cannot ship without these.

---

**BUG: Pipeline YouTube upload failure has no retry loop**

When YouTube upload fails (auth, network, etc), pipeline falls back to manual upload instructions, forcing user to recompile (30+ min wasted). Should instead:
1. Catch upload error
2. Ask "Delete token and re-authenticate? [y/N]"
3. Delete token.json if yes → triggers OAuth flow on next auth attempt
4. Automatically retry upload
5. Proceed to cleanup on success

"Retry YouTube upload" menu option exists for cleanup menu, but NOT in pipeline. This is the critical path users hit first.

**BUG: token.json corruption during write**

token.json sometimes becomes truncated/invalid JSON (JSONDecodeError on read). Likely cause: concurrent writes or failed file operations during token save. Fix: write to temp file first, atomic rename on success.

---

## TIER 1 (MVP)

Features that improve core workflow. Valuable for scaling and workflow quality, ready to start.

*(All current TIER 1 items have been completed.)*

---

## TIER 2 (QUALITY)

Polish on core workflow. Nice-to-have visual fixes.

---

**Animated ticker spacing**

Nice-to-have visual polish. Ticker visually appears to alternate between " .." and "..." - looks uneven. Root cause unknown (may be rendering/timing, not the string values). Investigate before fixing.

---

## TIER 3 (POLISH)

Cosmetic improvements, documentation, nice-to-haves.

---

**Code duplication analysis**

Scan codebase for: duplicate/similar logic, files over 300 lines, modularity improvements. Do in a dedicated session after the main items above are done and the codebase has stabilised.

Highest-impact files are likely `pipeline.py` (540 lines) and `description_writer.py`.

---

**FFmpeg auto-download test on clean machine**

Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts correctly. ~70MB download. Only needed before shipping to a new machine.

---

**Clip review: add [v]iew in VLC option**

During low-value clip review (preprocess and compile), user sees:
```
[y] include  [a] archive to ClipArchive  [d] delete:
```

Add [v] option to launch the clip in VLC without deciding. Lets user visually inspect the clip before deciding to keep/archive/delete.

Implementation: detect VLC at `C:\Program Files\VideoLAN\VLC\vlc.exe`, use `subprocess.Popen()` to open the clip, loop back to the same prompt so user can decide after viewing.

Config: `vlc_path` optional (default None). If not found, skip the option silently.

---

**Error message: literal \n instead of newline**

Config validation error shows literal `\n` in output: `'config.json is missing required field(s): youtube_channel_id\n  See config/config.example.json...`

The `\n` should be rendered as an actual newline. Grep the codebase for all occurrences of `\\n` in error strings and string literals to find similar issues. Fix all at once: ensure error strings use proper newline handling instead of literal escape sequences.

---

## TIER 4 (FUTURE)

Extra functionality, lower priority. Do not start until TIER 0-2 are solid. These are improvements beyond core highlight workflow.

---

**Best-of compilation from Archive**

Extra feature for archive management. Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`.

13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but feature is ready to build.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

---

**Automated tests for KO detection**

pytest tests for `scan_clip` and OCR logic. Prerequisite for confident scaling in OldCompilations Phase 2 (large-file scanning).

Test clip strategy to resolve: commit a very short clip (~5s) as a fixture, or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation.

Tests to write:
- Ground truth clip detects QUAD at correct timestamp
- OCR reads each tier correctly from known crops
- Cache hit/miss behaviour

---

**KO scanner large-file efficiency**

Performance optimization for TIER 4 OldCompilations Phase 2 only. Not needed for current highlight workflow.

Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale.

Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each.

Improvement: after detecting a kill event, skip ahead confidently (banner is ~2s, mandatory 2s cooldown). Also investigate ffmpeg seek-based extraction vs piping all frames for sparse scanning of long videos.

---

**OldCompilations - retrospective Best-of**

Lower priority extra feature. Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.

Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.

Location: `C:\Users\David\Videos\MarvelRivals\OldCompilations\`
Playlist: `https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W`

Phase 1 (download) complete - see `docs/HISTORY.md`. 27 videos downloaded (20 compilations, 7 gameplay streams).

**Phase 2 - KO scan** (prerequisite: KO scanner large-file efficiency solved first).

Scan order: compilation videos first (clean, no kill-cam false positives), stream VODs last (up to 4hr/7GB, kill-cam risk - treat results as needing manual verification).

**Phase 3 - Segment extraction:** FFmpeg-cut each Quad+ segment (with padding) into individual clips, output to `ClipArchive/`.

**Phase 4 - Description fetch via YouTube API (low priority):** Fetch each OldCompilations video's YouTube description (manually-entered timestamps + original clip filenames). Save as `<video_stem>_description.txt`. Uses: timestamp validation against KO scanner output, clip reconstruction via transition-counting. Auth reuses `config/token.json`.

---

## See also

- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/HISTORY.md` - completed features, settled design decisions, parked ideas
