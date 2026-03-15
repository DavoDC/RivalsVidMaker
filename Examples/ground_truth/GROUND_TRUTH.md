# KO Detection — Ground Truth Reference

## Source Clip
`THOR_2026-02-06_22-38-56.mp4`
- Duration: ~60s
- FPS: 29.83 (effectively 30fps)
- Total frames extracted: 1801
- Tier classification: **QUAD KILL** (KO → Double → Triple → Quad)
- Frames live at: `Examples/frame_by_frame_example_THOR_2026-02-06_22-38-56/frames/`
  - Bulk unlabelled frames: `frame_000001.png` … `frame_001801.png`
  - **Labelled frames** (ground truth): files with text suffix after frame number

## Labelled Frames

> **Important:** These labels mark frames where the banner was **clearly visible**,
> NOT the exact frame where the banner first appeared. The banner may have appeared
> 1–5 frames earlier. Use these as approximate reference points, not precise onset times.



| Filename | Frame # | Timestamp | Label |
|---|---|---|---|
| `frame_000304_KO_prompt_starting.png` | 304 | 0:10 | Game action begins — banner not yet visible |
| `frame_000347_KO.png` | 347 | 0:12 | **KO** banner fully visible on right |
| `frame_000412_double.png` | 412 | 0:14 | **DOUBLE!** banner visible |
| `frame_000700_triple.png` | 700 | 0:23 | **TRIPLE!** banner visible |
| `frame_000748_triple_still.png` | 748 | 0:25 | TRIPLE! banner still on screen |
| `frame_001192_quadra_early.png` | 1192 | 0:40 | **QUAD!** banner first appears |
| `frame_001248_quadra_still.png` | 1248 | 0:42 | QUAD! banner still showing |
| `frame_001298_quadra_still.png` | 1298 | 0:44 | QUAD! banner still showing |
| `frame_001358_multikill_finished.png` | 1358 | 0:45 | Banner gone — sequence complete |

**Multi-kill window within this clip: 0:10 → 0:45**

## Banner Visual Properties (from labelled frames)

- **Position**: right ~20-25% of screen width, vertically ~40-60% of screen height
- **Appearance**: slides in from the right edge; stays 2-4 seconds per tier
- **Style**: cyan/blue circular icon (Thor hammer) + white text on dark translucent panel
- **Text values**: `KO` → `DOUBLE!` → `TRIPLE!` → `QUAD!` → `PENTA!` → `HEXA!`
- **Colour is character-dependent** — not reliable for detection:
  - Thor: electric cyan/blue
  - Squirrel Girl: gold/yellow
- Banner text is **white** on a dark background regardless of character

## Crop Region for Detection

To isolate the banner, crop to:
- X: 75–100% of frame width (right 25%)
- Y: 40–62% of frame height

FFmpeg filter: `crop=iw*0.25:ih*0.22:iw*0.75:ih*0.40`

The labelled frames confirm this crop captures the banner cleanly without
other HUD elements (kill feed is top-right, health bar is bottom-centre).

## Detection Approach: OCR (Recommended)

**Why OCR beats pixel/saturation heuristics:**
- Saturation heuristic fires on any vivid region (maps with neon lighting,
  energy effects, etc.) → false positives
- OCR reads the actual text → zero ambiguity
- Banner text is large, high-contrast (white on dark) → easy for OCR

**Recommended stack:** Python + `pytesseract` + `Pillow`

**Steps per clip:**
1. Use FFmpeg to extract frames at 2fps (sufficient; banners last 2-4s each)
2. Crop each frame to the banner region (right 25%, y 40-62%)
3. Pre-process crop: convert to greyscale, threshold to high-contrast B&W
4. Run `pytesseract.image_to_string()` on the crop
5. Check if result contains any of: `KO`, `DOUBLE`, `TRIPLE`, `QUAD`, `PENTA`, `HEXA`
6. Apply 2s cooldown between distinct events (prevents double-counting same banner)
7. Record event tier + timestamp

## YouTube Description Timestamp Goal

**The user wants start + end timestamps relative to the COMPILED VIDEO, not the clip.**

For each clip, the compiled video timestamp = `running_video_offset + clip_event_timestamp`.

Example:
- Clip starts at 3:20 in the compiled video (running offset)
- Quad kill banner appears at 0:40 within the clip
- YouTube description entry: `3:20 → 4:05  QUAD KILL`

**What to put in the description:**
```
Multi-Kills:
3:20  Quad Kill
7:45  Triple Kill  (only if Quad+ threshold lowered in future)
```

Only **QUAD and above** are surfaced in the YouTube description (per design decision).
Lower tiers (KO, Double, Triple) are detected internally to track the streak
but are not shown to the viewer.

**Window format:** For the description, we want the timestamp of when the QUAD+
banner **first appears** in the compiled video. A viewer jumping to that timestamp
will land right on the Quad kill moment.

If a wider window is preferred (to show the buildup):
- Start = timestamp of first KO in the streak
- End = timestamp when the Quad+ banner disappears
- Format: `3:20 – 4:05  Quad Kill`

## This Clip's Output (When Working Correctly)

Given this clip is part of batch1 (vid1), and its position in the batch needs
to be computed from cumulative durations of preceding clips, the exact compiled
video timestamp is TBD. But within the clip itself:

- **Quad kill at: 0:40** (frame 1192)
- **Sequence window: 0:10 – 0:45**

## Notes / Gotchas

- The gap between Triple (0:23) and Quad (0:40) is ~17 seconds — kills can be
  spaced far apart. Don't assume kills are clustered.
- Frame 304 (0:10) shows no banner yet — the "starting" label marks when
  game action leading to the kill streak begins, not when the banner appears.
- The same banner tier stays on screen for multiple seconds — use rising-edge
  detection (inactive → active transition) to count distinct events.
- A 2s cooldown after each detected event prevents counting the same
  banner frame twice.
