"""
ko_detect.py — Multi-kill tier detection for Marvel Rivals clips.

Uses FFmpeg (2fps extraction) + Tesseract OCR to read the kill banner
on the right side of the screen.

Usage:
    python scripts/ko_detect.py                         # test ground truth clip
    python scripts/ko_detect.py <clip_path>             # single clip
    python scripts/ko_detect.py --batch vid1            # full batch

Output (single clip):
    QUAD KILL  |  0:12 → 0:45  (within clip)

Output (batch):
    [3:20] QUAD KILL  (compiled video timestamp)
"""

import subprocess, os, sys, tempfile, shutil, glob, re
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter
import pytesseract

# ── Config ────────────────────────────────────────────────────────────────────

FFMPEG       = r"C:\Users\David\GitHubRepos\CompilationVidMaker\tools\ffmpeg.exe"
TESSERACT    = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
CLIPS_BASE   = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR"
GROUND_TRUTH = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR\vid1_uploaded\THOR_2026-02-06_22-38-56.mp4"

pytesseract.pytesseract.tesseract_cmd = TESSERACT

# ── Detection parameters ───────────────────────────────────────────────────────

SCAN_FPS      = 2      # frames/sec to extract (banner lasts 2-4s, so 2fps is sufficient)
SKIP_SECS     = 2      # skip first N seconds (banner never appears this early)
COOLDOWN_SECS = 2.0    # min gap between distinct events (prevents double-counting same banner)

# Banner region: right 25% of frame width, vertically 40–62%
# Calibrated from ground truth frames — see examples/ground_truth/GROUND_TRUTH.md
CROP_X = 0.75
CROP_Y1 = 0.40
CROP_Y2 = 0.62

TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

# ── Image processing ──────────────────────────────────────────────────────────

def crop_banner(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.crop((int(w * CROP_X), int(h * CROP_Y1), w, int(h * CROP_Y2)))


def preprocess(crop: Image.Image) -> Image.Image:
    grey = crop.convert("L")
    # Scale up 3x — Tesseract performs better on larger images
    grey = grey.resize((grey.width * 3, grey.height * 3), Image.LANCZOS)
    # Banner text is white on dark → invert so Tesseract sees dark text on white
    grey = ImageOps.invert(grey)
    grey = grey.filter(ImageFilter.SHARPEN)
    return grey


def ocr_tier(img_path: str) -> str | None:
    """Return highest tier detected in this frame, or None."""
    img   = Image.open(img_path)
    crop  = crop_banner(img)
    proc  = preprocess(crop)

    # PSM 8 = single word; try PSM 7 (single line) as fallback
    for psm in (8, 7, 6):
        cfg  = f"--psm {psm} --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ!"
        text = pytesseract.image_to_string(proc, config=cfg)
        clean = re.sub(r"[^A-Z]", "", text.upper())
        # Check highest tier first (HEXA > PENTA > ... > KO)
        for tier in reversed(TIERS):
            if tier in clean:
                return tier
    return None

# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frames(clip_path: str, tmpdir: str) -> list[tuple[float, str]]:
    """Extract frames to tmpdir at SCAN_FPS. Returns [(timestamp_secs, path), ...]."""
    pat = os.path.join(tmpdir, "f_%05d.png")
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "quiet",
         "-ss", str(SKIP_SECS), "-i", clip_path,
         "-vf", f"fps={SCAN_FPS}", "-q:v", "2", pat],
        check=True
    )
    frames = sorted(glob.glob(os.path.join(tmpdir, "f_*.png")))
    return [(SKIP_SECS + i / SCAN_FPS, p) for i, p in enumerate(frames)]

# ── Core scan ─────────────────────────────────────────────────────────────────

def scan_clip(clip_path: str, debug: bool = False) -> dict | None:
    """
    Scan a clip for multi-kill events.

    Returns:
        {
            "tier":     "QUAD",        # highest tier achieved
            "start_ts": 12.0,          # first banner appearance (secs within clip)
            "end_ts":   46.0,          # last banner disappearance + 1s buffer
            "events":   [              # all individual events detected
                {"tier": "KO",     "ts": 12.0},
                {"tier": "DOUBLE", "ts": 14.0},
                {"tier": "TRIPLE", "ts": 23.0},
                {"tier": "QUAD",   "ts": 40.0},
            ]
        }
        or None if no kill banner detected.
    """
    tmpdir = tempfile.mkdtemp(prefix="ko_")
    try:
        frames = extract_frames(clip_path, tmpdir)
        events        = []
        prev_tier     = None
        cooldown_end  = 0.0
        last_active   = None

        for ts, path in frames:
            tier = ocr_tier(path)

            if debug:
                label = f"→ {tier}" if tier else "(none)"
                print(f"  t={ts:5.1f}s  {label}")

            if tier and ts >= cooldown_end:
                rank     = TIER_RANK.get(tier, -1)
                prev_rank = TIER_RANK.get(prev_tier, -1) if prev_tier else -1

                # New event: either first detection, tier went up, or cooldown elapsed after a gap
                if prev_tier is None or rank > prev_rank:
                    events.append({"tier": tier, "ts": ts})
                    cooldown_end = ts + COOLDOWN_SECS
                    prev_tier    = tier
                    if debug:
                        print(f"    *** EVENT: {tier} at {ts:.1f}s ***")
                elif tier == prev_tier:
                    # Same tier still showing — update cooldown, don't add new event
                    cooldown_end = ts + COOLDOWN_SECS

            if tier:
                last_active = ts
            elif last_active and (ts - last_active) > COOLDOWN_SECS * 2:
                # Banner has been gone long enough — streak could reset
                prev_tier = None

        if not events:
            return None

        max_tier = max(events, key=lambda e: TIER_RANK.get(e["tier"], 0))["tier"]
        return {
            "tier":     max_tier,
            "start_ts": events[0]["ts"],
            "end_ts":   (last_active or events[-1]["ts"]) + 1.0,
            "events":   events,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

# ── Batch processing ──────────────────────────────────────────────────────────

BATCH1 = [
    "THOR_2026-02-01_23-06-24.mp4","THOR_2026-02-05_23-34-58.mp4","THOR_2026-02-05_23-35-47.mp4",
    "THOR_2026-02-06_21-25-38.mp4","THOR_2026-02-06_21-26-23.mp4","THOR_2026-02-06_21-27-07.mp4",
    "THOR_2026-02-06_21-38-51.mp4","THOR_2026-02-06_21-39-43.mp4","THOR_2026-02-06_22-38-56.mp4",
    "THOR_2026-02-06_22-39-48.mp4","THOR_2026-02-06_22-42-30.mp4","THOR_2026-02-15_22-39-21.mp4",
    "THOR_2026-02-15_23-00-22.mp4","THOR_2026-02-15_23-09-55.mp4","THOR_2026-02-15_23-21-47.mp4",
    "THOR_2026-02-15_23-36-49.mp4","THOR_2026-02-16_00-12-08.mp4","THOR_2026-02-17_23-24-35.mp4",
    "THOR_2026-02-17_23-25-25.mp4","THOR_2026-02-18_23-19-12.mp4","THOR_2026-02-18_23-20-39.mp4",
    "THOR_2026-02-20_01-02-03.mp4","THOR_2026-02-20_01-10-58.mp4","THOR_2026-02-20_01-15-20.mp4",
    "THOR_2026-02-20_01-18-26.mp4","THOR_2026-02-20_01-19-11.mp4","THOR_2026-02-20_01-20-03.mp4",
    "THOR_2026-02-20_23-50-11.mp4","THOR_2026-02-20_23-50-59.mp4","THOR_2026-02-20_23-52-42.mp4",
    "THOR_2026-02-21_00-09-43.mp4",
]


def get_duration(clip_path: str) -> float:
    r = subprocess.run(
        [FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error",
         "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
         clip_path],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except:
        return 0.0


def fmt(secs: float) -> str:
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"

# ── Entry point ───────────────────────────────────────────────────────────────

def run_ground_truth():
    """Test on the known ground truth clip. Expected: QUAD, window ~0:12 → 0:45."""
    print("=" * 60)
    print(f"GROUND TRUTH TEST: {Path(GROUND_TRUTH).name}")
    print("Expected: QUAD KILL  |  ~0:06 → ~0:22")
    print("=" * 60)
    result = scan_clip(GROUND_TRUTH, debug=True)
    print()
    if result:
        print(f"RESULT:  {result['tier']} KILL")
        print(f"Window:  {fmt(result['start_ts'])} → {fmt(result['end_ts'])}")
        print("Events:")
        for ev in result["events"]:
            print(f"  {fmt(ev['ts'])}  {ev['tier']}")
        # Pass/fail check
        ok_tier   = result["tier"] == "QUAD"
        ok_start  = abs(result["start_ts"] - 6) <= 3
        ok_end    = abs(result["end_ts"]   - 22) <= 4
        print()
        print(f"  Tier correct?   {'PASS' if ok_tier  else 'FAIL'} (got {result['tier']}, want QUAD)")
        print(f"  Start correct?  {'PASS' if ok_start else 'FAIL'} (got {fmt(result['start_ts'])}, want ~0:06)")
        print(f"  End correct?    {'PASS' if ok_end   else 'FAIL'} (got {fmt(result['end_ts'])},  want ~0:22)")
    else:
        print("FAIL — no multi-kill detected")


def run_single(clip_path: str):
    print(f"Scanning: {Path(clip_path).name}")
    result = scan_clip(clip_path, debug=True)
    print()
    if result:
        print(f"RESULT:  {result['tier']} KILL")
        print(f"Window:  {fmt(result['start_ts'])} → {fmt(result['end_ts'])}")
    else:
        print("No multi-kill detected.")


def run_batch(batch_name: str, clips: list[str], clips_dir: str):
    print(f"\n{'=' * 60}")
    print(f"BATCH: {batch_name}")
    print("=" * 60)
    running = 0.0
    quad_plus = []
    for name in clips:
        path = os.path.join(clips_dir, name)
        if not os.path.exists(path):
            print(f"  MISSING: {name}")
            continue
        dur = get_duration(path)
        result = scan_clip(path)
        tier_str = result["tier"] if result else "—"
        if result:
            video_ts = running + result["start_ts"]
            video_end = running + result["end_ts"]
            print(f"  {name}  →  {tier_str}  [{fmt(video_ts)} – {fmt(video_end)}]")
            if TIER_RANK.get(result["tier"], 0) >= TIER_RANK["QUAD"]:
                quad_plus.append((video_ts, result["tier"], name))
        else:
            print(f"  {name}  →  {tier_str}")
        running += dur

    print(f"\nQuad+ timestamps for YouTube description ({batch_name}):")
    if quad_plus:
        for ts, tier, clip in quad_plus:
            print(f"  {fmt(ts)}  {tier}")
    else:
        print("  (none detected)")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        run_ground_truth()
    elif args[0] == "--batch" and len(args) > 1 and args[1] == "vid1":
        clips_dir = os.path.join(CLIPS_BASE, "vid1_uploaded")
        run_batch("vid1", BATCH1, clips_dir)
    else:
        run_single(args[0])
