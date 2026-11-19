# KO Detection: Ground Truth Reference

## Source Clip
`THOR_2026-02-06_22-38-56.mp4`
- Duration: ~30s (29.83s)
- FPS: 60fps (r_frame_rate=120/1 is container rate; actual avg ~60fps, confirmed 1801 frames / 29.83s)
- Total frames extracted: 1801 (at native fps)
- Tier classification: **QUAD KILL** (KO → Double → Triple → Quad)
- Frames live at: `data/examples/ko_frames/THOR_2026-02-06_22-38-56/`
  - Bulk unlabelled frames: `frame_000001.png` … `frame_001801.png`
  - **Labelled frames** (ground truth): files with text suffix after frame number

## Labelled Frames

> **Important:** These labels mark frames where the banner was **clearly visible**,
> NOT the exact frame where the banner first appeared. The banner may have appeared
> 1 to 5 frames earlier. Use these as approximate reference points, not precise onset times.


| Filename | Frame # | Timestamp | Label |
|---|---|---|---|
| `frame_000304_KO_prompt_starting.png` | 304 | 0:05 | Game action begins, banner not yet visible |
| `frame_000347_KO.png` | 347 | 0:06 | **KO** banner fully visible on right |
| `frame_000412_double.png` | 412 | 0:07 | **DOUBLE!** banner visible |
| `frame_000700_triple.png` | 700 | 0:12 | **TRIPLE!** banner visible |
| `frame_000748_triple_still.png` | 748 | 0:12 | TRIPLE! banner still on screen |
| `frame_001192_quadra_early.png` | 1192 | 0:20 | **QUAD!** banner first appears |
| `frame_001248_quadra_still.png` | 1248 | 0:21 | QUAD! banner still showing |
| `frame_001298_quadra_still.png` | 1298 | 0:22 | QUAD! banner still showing |
| `frame_001358_multikill_finished.png` | 1358 | 0:45 | Banner gone, sequence complete |

**Multi-kill window within this clip: 0:10 → 0:45**

## Banner Visual Properties (from labelled frames)

- **Position**: right ~20-25% of screen width, vertically ~40-60% of screen height
- **Appearance**: slides in from the right edge; stays 2-4 seconds per tier
- **Style**: cyan/blue circular icon (Thor hammer) + white text on dark translucent panel
- **Text values**: `KO` → `DOUBLE!` → `TRIPLE!` → `QUAD!` → `PENTA!` → `HEXA!`
- **Colour is character-dependent**, not reliable for detection:
  | Character     | Banner colour                              |
  |---------------|--------------------------------------------|
  | Thor          | Vivid electric blue/cyan (~R=0, G=160, B=240) |
  | Squirrel Girl | Vivid gold/yellow (~R=220, G=180, B=0)     |
- Banner text is **white** on a dark background regardless of character
- Saturation heuristic (character-agnostic): `max(R,G,B) > 180 AND max(R,G,B) - min(R,G,B) > 100`

## Crop Region for Detection

To isolate the banner, crop to:
- X: 75 to 100% of frame width (right 25%)
- Y: 40 to 62% of frame height

FFmpeg filter: `crop=iw*0.25:ih*0.22:iw*0.75:ih*0.40`

The labelled frames confirm this crop captures the banner cleanly without other HUD elements (kill feed is top-right, health bar is bottom-centre).

## Detection Approach: OCR (Recommended)

**Why OCR beats pixel/saturation heuristics:**
- Saturation heuristic fires on any vivid region (maps with neon lighting, energy effects, etc.) → false positives
- OCR reads the actual text → zero ambiguity
- Banner text is large, high-contrast (white on dark) → easy for OCR

**Why OCR beats template matching:**
- Template matching requires a reference image per tier (3+ PNG files to maintain)
- Fails if game patches the UI visuals or resolution/UI scale changes
- OCR handles font variations and will pick up new kill tiers automatically
- Template matching is faster (~3 to 8ms/frame vs ~50 to 150ms) but 2fps scanning means speed is not a concern, accuracy matters more

**Recommended stack:** Python + `pytesseract` + `Pillow`

**Steps per clip:**
1. Use FFmpeg to extract frames at 2fps (sufficient; banners last 2-4s each)
2. Crop each frame to the banner region (right 25%, y 40-62%)
3. Pre-process crop: scale 3x, invert (white text → dark for Tesseract), sharpen
4. Run `pytesseract.image_to_string()` with PSM 8 → PSM 7 → PSM 6 fallback
5. Check if result contains any of: `KO`, `DOUBLE`, `TRIPLE`, `QUAD`, `PENTA`, `HEXA`
6. Apply 2s cooldown between distinct events (prevents double-counting same banner)
7. Record event tier + timestamp

**Performance at 2fps (30s clips):** ~60 frames extracted per clip. OCR at ~50 to 150ms/frame = ~3 to 9 seconds per clip. Acceptable; cache means re-runs are instant.

For context on a full 15-min compiled video at native fps (not used, we scan clips individually):
- 15 min @ 60fps = 54,000 frames; template matching ~3min, OCR ~45 to 135min (impractical)
- Sampling every 10 frames at 2fps = 180 frames; OCR ~9 to 27 seconds total, fast enough

## Long videos: NCC template detector (`scan_video`)

`ko_detect.scan_video` (compilations and VODs) no longer OCRs every frame. `src/ko_ncc.py` decodes only the small tier-word box with ffmpeg at 15 fps (`-threads 1` per decode, 8 chunks decoded in parallel: `ko_ncc.FFMPEG_THREADS`, `ko_ncc.WORKERS`), turns each frame into a Sobel edge map and scores it by normalised cross-correlation against a bank of tier-word crops in `assets/ko_templates/` (`templates.json` plus the PNGs under `templates/`, cut from 1080p footage; DOUBLE, TRIPLE, QUAD, PENTA and HEXA). Runs of hit frames (score at least 0.5, two or more hits, one missed frame bridged) become events, the tier is the one with the largest summed score over the run, and the timeline and events keep the shape `ko_streaks` expects (same rank and cooldown rules). OCR remains as `scan_video(..., detector="ocr")` and runs only as a per-event tiebreak when the top two tier scores of a run differ by less than 10 percent.

Measured on the AWAKENS compilation (15 minutes at 1080p): all 9 verified Quad banners found, no Quad or higher event outside the truth windows, about 6.3 seconds per video minute against about 44.6 for the OCR scan. Other 16:9 sizes rescale the templates; a frame that is not 16:9 or is under 360 px high, a missing bank, or a missing opencv falls back to OCR with a log line. Chunk checkpoints are 60 s of scores and are keyed on the bank hash, so a changed bank rescans. `scan_clip` (short clips) is unchanged and still uses OCR.

## YouTube Description Timestamp Goal

Timestamps in the description are **relative to the compiled video, not the clip.**

```
compiled video timestamp = running_video_offset + clip_event_timestamp
```

Example: clip starts at 3:20 in the compiled video, Quad kill at 0:40 within the clip → description entry at 4:00.

Timestamp range format and threshold (Quad+ only): see `docs/YOUTUBE_TITLE_AND_DESC.md`.

## This Clip's Output (When Working Correctly)

This clip is the first clip in vid1 (batch1). Within the clip itself:

- **Quad kill at: 0:20** (frame 1192, at 2fps scan)
- **Sequence window: 0:06 to 0:22** (KO banner first appears at ~0:06, Quad banner at ~0:20)

In the compiled video, this clip is clip 1 with no preceding offset. Verified timestamp: `0:06 - 0:22 = Quad Kill` (confirmed accurate by manual playback, see CLAUDE.md).

## Validated Test Clips

Clips verified correct by watching the actual video after running `ko_detect.py`:

| Clip | Expected | Script output | Window | Verified |
|---|---|---|---|---|
| `THOR_2026-02-06_22-38-56.mp4` | QUAD | QUAD | 0:06 → 0:22 | ✅ |
| `THOR_2026-02-17_23-25-25.mp4` | TRIPLE | TRIPLE | 0:06 → 0:14 | ✅ |

**Known false negatives (manual review 2026-03-31):**

| Clip | Manually observed | Script output | Status |
|---|---|---|---|
| `THOR_2026-03-17_22-20-29.mp4` | KO at ~8s, then assists | null | Bug - missed |
| `THOR_2026-03-22_23-19-10.mp4` | KO at ~8s, then assists | null | Bug - missed |
| `THOR_2026-03-27_22-23-58.mp4` | KO at ~8s, clip ends | null | Bug - missed |
| `THOR_2026-03-28_23-22-42.mp4` | KO at ~8s, nothing else (18.5s clip) | null | Bug - missed |
| `THOR_2026-03-26_22-37-28.mp4` | KO at 18.5s (single-frame flash), DOUBLE at 25.9s (39s clip) | null | Pass 1 misses the KO (single-frame) and early-exits before 25.9s. Pass 2 fixed this, but pass 2 is being removed (B1). Clip will be flagged for deletion. |

**Notes on misses:** DOUBLE was missed in the TRIPLE clip (banner visible ~1s, fell between 2fps sample points). Acceptable - intermediate tiers don't affect final classification as long as the highest tier is caught.

**Known limitations:**
- Short banners (<1s) may be missed at 2fps - mostly affects KO/DOUBLE, not Quad+
- `KO` (2 chars) is harder for Tesseract than longer tier names like `TRIPLE` or `QUAD`
- **Single-KO false negatives (confirmed bug):** 4 clips with visible KO banners at ~8s returned null (THOR_2026-03-17_22-20-29, THOR_2026-03-22_23-19-10, THOR_2026-03-27_22-23-58, THOR_2026-03-28_23-22-42). Crop region confirmed correct (same position as multi-kill banners). Root cause: 2fps has a 0.5s miss window - KO banner can appear and disappear between samples. Fix: raise `SCAN_FPS` to 4 (planned).
- **Single-frame KO banners (~0.125s):** confirmed in THOR_2026-03-26_22-37-28 -- KO banner at 18.5s lasted ~0.125s, always missed by pass 1 at 2fps. Previously fixed by pass 2; pass 2 is being removed (B1 design). These clips will be flagged for deletion -- accepted tradeoff.
- **Not all highlight clips are multi-kills:** The game's DVR saves single-KO + assist sequences too. These scan as null or KO-tier. Pass 1 only is the intended scanner; clips where pass 1 finds nothing or only a single KO are prompted for deletion. Only DOUBLE+ from pass 1 go into compilations.
- **Kill-cam false positives (stream VODs only):** When the player dies in a stream VOD (raw game recording), the game shows the killer's POV during the respawn wait. The killer can chain multi-kills in this window, and their KO banners appear in the same region as the player's own banners. Does NOT affect saved highlight clips - those are always the player's own kills captured by the in-game DVR. Only relevant for OldCompilations stream VODs.

## Notes / Gotchas

- The gap between Triple (0:23) and Quad (0:40) is ~17 seconds, and kills can be spaced far apart. Don't assume kills are clustered.
- Frame 304 (0:10) shows no banner yet: the "starting" label marks when game action leading to the kill streak begins, not when the banner appears.
- The same banner tier stays on screen for multiple seconds, so use rising-edge detection (inactive → active transition) to count distinct events.
- A 2s cooldown after each detected event prevents counting the same banner frame twice.

## Reference Screenshots (`data/examples/ko_frames/`)

| File | Character | Tier | Map / notes |
|---|---|---|---|
| `thor_ko.png` | Thor | KO | t=00:05 |
| `thor_double.png` | Thor | DOUBLE! | t=00:09 |
| `thor_triple.png` | Thor | TRIPLE! | t=00:14 |
| `quad_example1.png` | Thor | QUAD! | Stone ruins map |
| `quad_example2.png` | Thor | QUAD! | Asgard-style map (blue/purple ambient, watch for false positives) |
| `quad_example3.png` | Squirrel Girl | TRIPLE! | Gold/orange colour, neon space map, confirms colour-agnostic heuristic works |
| `example_a.png` | Thor | TRIPLE! | Circular arena map |
| `example_b.png` | Thor | KO | Circular arena map |
| `example_c.png` | Thor | KO | Circular arena map (different frame) |
| `example_d.png` | Thor | DOUBLE! | Stone castle / Japanese map |
| `example_e.png` | Thor | QUAD! | JIKAWA MALL |
