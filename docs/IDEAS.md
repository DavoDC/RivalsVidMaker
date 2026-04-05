# Ideas & Future Work

Single source of truth for all pending work.

---

## Pending - ordered by priority (quick wins first)

**1. Fix dry run: preprocess renames/deletes not gated** *(bug, 1-2 lines)*

`pipeline.py:567` calls `preprocess_all(config)` with no `dry_run` arg. Inside `preprocess_all`, `_rename_clip()` and `_prompt_delete()` run fully even in `--dry-run` mode - renaming video files and prompting to delete them. Fix: pass `dry_run` through to `preprocess_all`, gate both operations behind it.

---

**2. Fix dry run: low-value clip prompts not gated** *(bug, 1-2 lines)*

`pipeline.py:607-640` - the compile path low-value clip guard prompts to delete/archive clips and actually does it, even in `--dry-run` mode. Fix: wrap the delete/archive actions in `if not dry_run:`. In dry run, log what would happen but skip the actual file ops.

---

**3. Remove timestamps Format: header** *(trivial, 1 line)*

Decision made: remove the `Format: <streak start> - <max kill time> = Kill tier` header line from the description .txt (`description_writer.py:128-129`). The format is intuitive enough for viewers without explaining it.

---

**4. Description: Marvel voicelines / character phrases** *(trivial, update prompt only)*

Current description prompt asks for a generic one-liner. Goal: character-specific Marvel comic quotes and in-game voicelines woven in. Approach: update the AI prompt to instruct it to find and use character-appropriate voicelines (AI can web search etc). No manual config JSON needed - that was over-engineering. Once prompt is updated, this item is done.

---

**5. Estimate: swap NVENC encode multiplier** *(small)*

Current estimate uses `total_dur * 0.4` (CPU encode). NVENC (GPU) is ~0.10-0.15x real-time. Read `encoder.py`, detect whether NVENC is being used, and use the correct multiplier. Prerequisite for item 7 (composite estimate).

---

**6. Estimate: add per-stage timing logs** *(small)*

Add timing instrumentation around each pipeline stage: KO scanning, fingerprinting, encoding. Log each stage's actual elapsed time so real data accumulates over runs. Used to validate and refine the composite estimate (item 7).

---

**7. Estimate: composite estimate (KO + fingerprint + encode)** *(medium)*

Replace the single encode-only estimate with a composite: KO scan estimate + fingerprint estimate + encode estimate = overall. Each stage modelled separately. Depends on items 5 and 6 being done first to have correct per-stage models.

---

**8. Fingerprint/duration caching** *(medium - design decision pending)*

Every run re-fingerprints all clips for dedup checking from scratch. Add per-clip caching. Cache key: path + mtime + size. Skip unchanged clips on re-run. Biggest win for large character folders (56+ clips).

Design options:
- (a) Separate `.fp.json` per clip alongside `.ko.json`. Simple, isolated, no migration. But two files per clip, and future cache fields need another new file type.
- (b) Single generic `.clip.json` per clip containing everything: KO result, fingerprint hashes, duration, anything added later. One file per clip, easy to extend. Requires migrating existing `.ko.json` files and updating `ko_detect.py` to read/write the new format.

**Recommendation: (b) long-term.** If we plan to cache 3+ things (KO, fingerprint, duration, maybe more), a single file is cleaner. The migration is a one-off. Worth discussing before implementing.

---

**9. Preprocess: top-level menu + run all cacheable work** *(medium, depends on item 8)*

Preprocess is buried in a submenu. Move it to the top-level menu. When selected, run ALL cacheable work: KO scanning + fingerprinting (item 8). Intended for "going AFK" use. Show overall progress bar across all characters. Text on menu item: "Preprocess all (warm cache)".

---

## Lower priority / future

*(ordered by size - smaller first)*

**Test FFmpeg auto-download on a clean machine**

Delete `dependencies/ffmpeg/` and run `python src/main.py` to verify `ffmpeg_setup.py` downloads and extracts correctly. ~70MB download. Only needed before shipping to a new machine.

---

**Animated ticker spacing**

Ticker visually appears to alternate between " .." and "..." - looks uneven. Root cause unknown (may be rendering/timing, not the string values). Investigate before fixing.

---

**Code duplication analysis**

Scan codebase for: duplicate/similar logic, files over 300 lines, modularity improvements. Do in a dedicated session after the main items above are done and the codebase has stabilised. Highest-impact files are likely `pipeline.py` (540 lines) and `description_writer.py`.

---

**Automated tests for KO detection**

pytest tests for `scan_clip` and OCR logic. Want KO detection solid before running big scans (OldCompilations, Best-of). Test clip strategy to resolve: commit a very short clip (~5s) as a fixture, or a synthetic test image of the banner crop (~50KB PNG) to test OCR in isolation. Tests to write: ground truth clip detects QUAD at correct timestamp, OCR reads each tier correctly from known crops, cache hit/miss behaviour.

---

**KO scanner large-file efficiency** *(prerequisite for OldCompilations Phase 2)*

Gameplay streams can be 4hr / 7GB+. Current 2fps sampling is fine for 15-min clips but becomes expensive at that scale.
- Current approach: extract every frame at 2fps via ffmpeg pipe, run OCR on each
- Improvement: after detecting a kill event, skip ahead confidently (banner is ~2s, mandatory 2s cooldown). Also investigate ffmpeg seek-based extraction vs piping all frames for sparse scanning of long videos.
- Must solve before running OldCompilations Phase 2 on stream VODs.

---

**Best-of compilation from Archive**

Archive submenu should offer "Compile Best-of" per character, running the same KO scan + encode pipeline as Highlights. Output slug e.g. `THOR_BEST_OF_2026`. 13 THOR Quad+ clips currently in archive (6m 11s) - too short yet, but build the feature ready.

Archive clip lifecycle (decided):
- Archive clips are NEVER deleted - permanent record of best kills.
- After a Best-of compilation, compiled clips move from `ClipArchive/THOR/` to `ClipArchive/THOR/compiled/`.
- `ClipArchive/THOR/` (root) = pending, not yet in any Best-of.
- `ClipArchive/THOR/compiled/` = already used, excluded from future compiles.
- Archive display table should show pending vs compiled counts separately.

---

**YouTube API - Phase 2 pipeline integration** *(OAuth confirmed working 2026-04-04)*

See `docs/YOUTUBE_API.md` for full API reference and auth setup notes.

What works (confirmed):
- OAuth flow via `davo29rhino@gmail.com`, `youtube.upload` scope
- Working test script: `scripts/once_off/yt_upload_test.py`
- Credentials: `config/client_secret_*.json` (gitignored), token: `config/token.json` (gitignored)
- Set `OAUTHLIB_RELAX_TOKEN_SCOPE=1` - required when user grants narrower scope than requested in the consent screen
- `youtube.upload` scope alone is sufficient for video upload; full `youtube` scope needed for thumbnails/playlists

Phase 2 implementation plan:
- Add `src/uploader.py` - reuse auth logic from `scripts/once_off/yt_upload_test.py`
- Channel ID check: call `channels.list?part=id&mine=true`, compare against `"youtube_channel_id"` in config.json (target: `UC4xPDj5h-MRmTaa8-xIBfaA` / `@dave369_`). Abort if mismatch.
- Parse title + description from the `_description.txt` file written by `description_writer.py`
- After successful upload, write video ID + URL to state.json so cleanup can link to it
- Hook into `pipeline.py` after encode + describe steps

---

**OldCompilations - retrospective Best-of**

Previously uploaded videos re-downloaded for KO scanning + segment extraction into ClipArchive.
Location: `C:\Users\David\Videos\MarvelRivals\OldCompilations\`
Playlist: `https://youtube.com/playlist?list=PLMGEiDlepOBXeW6gsniLnAcg1OaCZmy_W`

Phase 1 (download) complete - see `docs/HISTORY.md`. 27 videos downloaded (20 compilations, 7 gameplay streams).

**Phase 2 - KO scan** (prerequisite: large-file efficiency solved first, and KO detection tests passing).

Scan order: compilation videos first (clean, no kill-cam false positives), stream VODs last (up to 4hr/7GB, kill-cam risk - treat results as needing manual verification).

**Content inventory (27 videos):**

Compilation videos (20):
- `2025-05-18` THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]
- `2025-08-03` THOR HIGHLIGHTS, MULTIKILLS [JUL+AUG 2025]
- `2025-08-16` THOR HIGHLIGHTS, MULTIKILLS [AUG 2025][Part 1]
- `2025-08-30` THOR HIGHLIGHTS, MULTIKILLS [AUG 2025][Part 2]
- `2025-09-13` THOR HIGHLIGHTS, MULTIKILLS [SEP 2025][Part 1]
- `2025-09-13` THOR HIGHLIGHTS, MULTIKILLS [SEP 2025][Part 2]
- `2025-09-27` THOR HIGHLIGHTS, MULTIKILLS [SEP 2025][Part 3]
- `2025-10-01` THOR UNLEASHED - Relentless Multikills (Sep 2025) Part 4
- `2025-10-13` SQUIRREL GIRL HIGHLIGHTS [AUG-OCT 2025]
- `2025-10-13` THOR HIGHLIGHTS, MULTIKILLS [OCT 2025][Part 1]
- `2025-11-01` THOR HIGHLIGHTS, MULTIKILLS [OCT 2025][Part 2]
- `2025-11-03` SQUIRREL GIRL HIGHLIGHTS [OCT 2025]
- `2025-11-22` THOR HIGHLIGHTS, MULTIKILLS [NOV 2025][Part 1]
- `2025-12-07` SQUIRREL GIRL HIGHLIGHTS [NOV-DEC 2025]
- `2025-12-07` UNSTOPPABLE THOR - Multikill Highlights Nov-Dec 2025
- `2026-01-31` THOR AT PEAK POWER - Multikill Highlights (Jan 2026)
- `2026-01-31` THOR IN FULL CONTROL - Multikill Highlights (Dec 2025)
- `2026-02-14` SQUIRREL GIRL MULTIKILL MONTAGE (Dec 25 - Feb 26)
- `2026-03-17` THOR AWAKENS - Multikill Highlights (Feb 2026) **[already processed - clips saved]**
- `2026-03-17` THOR OVERLOAD - Back-to-Back Multikills (Feb-Mar 2026) **[already processed - clips saved]**

Gameplay stream videos (7, 39min+, up to ~4hr/7GB):
- `2025-08-12` THOR RIVALS GAMEPLAY (13th Aug 2025)
- `2025-09-09` THOR RIVALS GAMEPLAY (9th Sep 2025)
- `2025-09-11` THOR RIVALS GAMEPLAY (11th Sep 2025)
- `2025-09-12` THOR RIVALS GAMEPLAY (12th Sep 2025)
- `2025-09-23` THOR RIVALS GAMEPLAY (23rd Sep 2025)
- `2025-09-27` THOR RIVALS GAMEPLAY (27th Sep 2025)
- `2025-11-09` MARVEL RIVALS Gameplay (1st Nov 2025)

Already-processed: the two 2026-03-17 videos are done (clips saved). Keep as regression tests.

**Phase 3 - Segment extraction:** FFmpeg-cut each Quad+ segment (with padding) into individual clips, output to `ClipArchive/`.

**Phase 4 - Description fetch via YouTube API (low priority):** Fetch each OldCompilations video's YouTube description (manually-entered timestamps + original clip filenames). Save as `<video_stem>_description.txt`. Uses: timestamp validation against KO scanner output, clip reconstruction via transition-counting. Auth reuses `config/token.json`.

---

Settled design decisions and parked ideas are in `docs/HISTORY.md`.

---

## See also
- `docs/YOUTUBE_API.md` - YouTube Data API v3 research, auth flow, upload endpoint
- `docs/MULTIKILL_DETECTION.md` - KO detection algorithm, OCR, frame sampling
- `docs/YOUTUBE_TITLE_AND_DESC.md` - canonical format for titles and descriptions
- `docs/HISTORY.md` - completed features, settled design decisions, parked ideas
