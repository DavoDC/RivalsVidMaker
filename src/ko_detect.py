"""
ko_detect.py — Multi-kill tier detection for Marvel Rivals clips.

Uses FFmpeg (2fps extraction) + Tesseract OCR to read the kill banner
on the right side of the screen.

Output format (YouTube description timestamps):
    <streak start> - <max tier time> = Quad Kill
    e.g. 1:36 - 1:45 = Quad Kill

Streak start = when FIRST KO banner appears (gives viewers the build-up).
Max tier time = when the Quad/Penta/Hexa banner first appears.

Usage:
    python src/ko_detect.py                         # test ground truth clip
    python src/ko_detect.py <clip_path>             # single clip (debug)
    python src/ko_detect.py --batch vid1            # full batch → writes output txt
    python src/ko_detect.py --batch vid2            # full batch → writes output txt
"""

import subprocess, os, sys, tempfile, shutil, glob, re, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter
import pytesseract

# ── Config ────────────────────────────────────────────────────────────────────

FFMPEG       = r"C:\Users\David\GitHubRepos\RivalsVidMaker\tools\ffmpeg.exe"
TESSERACT    = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
CLIPS_BASE   = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR"
CACHE_DIR    = r"C:\Users\David\GitHubRepos\RivalsVidMaker\data\cache\THOR"
OUTPUT_DIR   = r"C:\Users\David\GitHubRepos\RivalsVidMaker\data"
GROUND_TRUTH = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR\vid1_uploaded\THOR_2026-02-06_22-38-56.mp4"

pytesseract.pytesseract.tesseract_cmd = TESSERACT


def configure(
    ffmpeg: str | None = None,
    tesseract: str | None = None,
    cache_dir: str | None = None,
) -> None:
    """
    Override module-level paths at runtime.

    Called by pipeline.py so the full pipeline can use config.txt paths
    rather than the hardcoded defaults above.  Standalone usage (running
    ko_detect.py directly) is unaffected — defaults still apply.
    """
    global FFMPEG, TESSERACT, CACHE_DIR
    if ffmpeg:
        FFMPEG = ffmpeg
    if tesseract:
        TESSERACT = tesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract
    if cache_dir:
        CACHE_DIR = cache_dir


# ── Detection parameters ───────────────────────────────────────────────────────

SCAN_FPS      = 2      # frames/sec to extract
SKIP_SECS     = 2      # skip first N seconds
COOLDOWN_SECS = 2.0    # min gap between distinct events

# Banner region: right 25% of frame width, vertically 40–62%
CROP_X  = 0.75
CROP_Y1 = 0.40
CROP_Y2 = 0.62

TIERS     = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

# Only tiers at this rank or above appear in the YouTube description output
REPORT_MIN_TIER = "QUAD"

# Parallel workers for batch scanning (FFmpeg + Tesseract are external processes,
# so threads give real parallelism here)
N_WORKERS = 4

# ── Image processing ──────────────────────────────────────────────────────────

def crop_banner(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img.crop((int(w * CROP_X), int(h * CROP_Y1), w, int(h * CROP_Y2)))


def preprocess(crop: Image.Image) -> Image.Image:
    grey = crop.convert("L")
    grey = grey.resize((grey.width * 3, grey.height * 3), Image.LANCZOS)
    grey = ImageOps.invert(grey)
    grey = grey.filter(ImageFilter.SHARPEN)
    return grey


def ocr_tier(img_path: str) -> str | None:
    img   = Image.open(img_path)
    crop  = crop_banner(img)
    proc  = preprocess(crop)
    for psm in (8, 7, 6):
        cfg   = f"--psm {psm} --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ!"
        text  = pytesseract.image_to_string(proc, config=cfg)
        clean = re.sub(r"[^A-Z]", "", text.upper())
        for tier in reversed(TIERS):
            if tier in clean:
                return tier
    return None

# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frames(clip_path: str, tmpdir: str) -> list[tuple[float, str]]:
    pat = os.path.join(tmpdir, "f_%05d.png")
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "quiet",
         "-ss", str(SKIP_SECS), "-i", clip_path,
         "-vf", f"fps={SCAN_FPS}", "-q:v", "2", pat],
        check=True
    )
    frames = sorted(glob.glob(os.path.join(tmpdir, "f_*.png")))
    return [(SKIP_SECS + i / SCAN_FPS, p) for i, p in enumerate(frames)]


def get_duration(clip_path: str) -> float:
    r = subprocess.run(
        [FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", clip_path],
        capture_output=True, text=True
    )
    try:
        return float(r.stdout.strip())
    except:
        return 0.0

# ── Cache ─────────────────────────────────────────────────────────────────────

def _month_from_stem(stem: str) -> str | None:
    """Extract YYYY-MM from a clip stem like THOR_2026-02-01_23-06-24.
    Returns None if the filename doesn't contain a parseable date."""
    m = re.search(r"(\d{4}-\d{2})-\d{2}", stem)
    return m.group(1) if m else None


def cache_path(clip_path: str) -> str:
    """Return the cache file path, nested under a YYYY-MM month subfolder.

    Structure: <CACHE_DIR>/<YYYY-MM>/<stem>.ko.json
    Falls back to <CACHE_DIR>/<stem>.ko.json for filenames without a date.
    """
    stem = Path(clip_path).stem
    month = _month_from_stem(stem)
    if month:
        return os.path.join(CACHE_DIR, month, f"{stem}.ko.json")
    return os.path.join(CACHE_DIR, f"{stem}.ko.json")


def cache_exists(clip_path: str) -> bool:
    return os.path.exists(cache_path(clip_path))


def cache_load(clip_path: str) -> tuple[bool, dict | None]:
    """
    Returns (hit, result).
      hit=False → not in cache, needs scanning
      hit=True, result=None  → cached "no kill detected"
      hit=True, result=dict  → cached kill data
    """
    p = cache_path(clip_path)
    if not os.path.exists(p):
        return False, None
    with open(p) as f:
        return True, json.load(f)


def cache_save(clip_path: str, result: dict | None):
    os.makedirs(os.path.dirname(cache_path(clip_path)), exist_ok=True)
    with open(cache_path(clip_path), "w") as f:
        json.dump(result, f)

# ── Core scan ─────────────────────────────────────────────────────────────────

def scan_clip(clip_path: str, debug: bool = False, use_cache: bool = True) -> dict | None:
    """
    Returns:
        {
            "tier":      "QUAD",   # highest tier achieved
            "start_ts":  6.0,      # when FIRST banner appeared (streak start — use for YT timestamp)
            "max_ts":    20.0,     # when the MAX tier banner appeared
            "end_ts":    22.0,     # when last banner disappeared + 1s
            "events":    [{"tier": "KO", "ts": 6.0}, ...]
        }
        or None if no kill banner detected.
    """
    if use_cache:
        hit, cached = cache_load(clip_path)
        if hit:
            if debug:
                print("  [cache hit]")
            return cached

    tmpdir = tempfile.mkdtemp(prefix="ko_")
    try:
        frames       = extract_frames(clip_path, tmpdir)
        events       = []
        prev_tier    = None
        cooldown_end = 0.0
        last_active  = None

        for ts, path in frames:
            tier = ocr_tier(path)

            if debug:
                label = f"→ {tier}" if tier else "(none)"
                print(f"  t={ts:5.1f}s  {label}")

            if tier and ts >= cooldown_end:
                rank      = TIER_RANK.get(tier, -1)
                prev_rank = TIER_RANK.get(prev_tier, -1) if prev_tier else -1
                if prev_tier is None or rank > prev_rank:
                    events.append({"tier": tier, "ts": ts})
                    cooldown_end = ts + COOLDOWN_SECS
                    prev_tier    = tier
                    if debug:
                        print(f"    *** EVENT: {tier} at {ts:.1f}s ***")
                elif tier == prev_tier:
                    cooldown_end = ts + COOLDOWN_SECS

            if tier:
                last_active = ts
            elif last_active and (ts - last_active) > COOLDOWN_SECS * 2:
                prev_tier = None

        if not events:
            cache_save(clip_path, None)
            return None

        max_event = max(events, key=lambda e: TIER_RANK.get(e["tier"], 0))
        result = {
            "tier":     max_event["tier"],
            "start_ts": events[0]["ts"],        # streak start → use for YT timestamp
            "max_ts":   max_event["ts"],        # when highest tier appeared
            "end_ts":   (last_active or events[-1]["ts"]) + 1.0,
            "events":   events,
        }
        cache_save(clip_path, result)
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

# ── Formatting ────────────────────────────────────────────────────────────────

def fmt(secs: float) -> str:
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"

# ── Batch ─────────────────────────────────────────────────────────────────────

BATCH_DIRS = {
    "vid1": "vid1_uploaded",
    "vid2": "vid2_uploaded",
}


def get_clips(clips_dir: str) -> list[str]:
    """Return sorted list of .mp4 filenames in a directory (alphabetical = chronological)."""
    paths = sorted(glob.glob(os.path.join(clips_dir, "*.mp4")))
    return [os.path.basename(p) for p in paths]


def _scan_worker(clip_path: str) -> tuple[str, dict | None, float, bool]:
    """Thread worker. Returns (clip_path, result, elapsed_secs, was_cached)."""
    was_cached = cache_exists(clip_path)
    t0 = time.perf_counter()
    result = scan_clip(clip_path, debug=False, use_cache=True)
    elapsed = time.perf_counter() - t0
    return clip_path, result, elapsed, was_cached


def run_batch(batch_name: str, clips: list[str], clips_dir: str):
    t_batch = time.perf_counter()

    print(f"\n{'=' * 60}")
    print(f"BATCH: {batch_name}  ({len(clips)} clips)  [{N_WORKERS} workers]")
    print("=" * 60)

    # ── Phase 1: resolve paths and collect durations (fast, sequential) ────────
    clip_paths = {}
    durations  = {}
    for name in clips:
        path = os.path.join(clips_dir, name)
        clip_paths[name] = path
        if os.path.exists(path):
            durations[name] = get_duration(path)

    # ── Phase 2: scan all clips in parallel ────────────────────────────────────
    scan_results = {}  # name → (result, elapsed, was_cached)
    valid_clips  = [name for name in clips if os.path.exists(clip_paths[name])]

    with ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
        future_to_name = {
            executor.submit(_scan_worker, clip_paths[name]): name
            for name in valid_clips
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            _, result, elapsed, was_cached = future.result()
            scan_results[name] = (result, elapsed, was_cached)

    # ── Phase 3: output in order + compute running timestamps ─────────────────
    running    = 0.0
    highlights = []

    for i, name in enumerate(clips):
        path = clip_paths.get(name)
        if not path or not os.path.exists(path):
            print(f"  [{i+1:2d}/{len(clips)}] MISSING: {name}")
            continue

        result, elapsed, was_cached = scan_results[name]
        dur      = durations.get(name, 0.0)
        tier_str = result["tier"] if result else "—"
        tag      = "[cached] " if was_cached else f"[{elapsed:.1f}s]  "

        if result:
            video_start_ts = running + result["start_ts"]
            video_max_ts   = running + result["max_ts"]
            print(f"  [{i+1:2d}/{len(clips)}] {tag}{name}  →  {tier_str}  ({fmt(video_start_ts)}–{fmt(video_max_ts)} in video)")
            if TIER_RANK.get(result["tier"], 0) >= TIER_RANK[REPORT_MIN_TIER]:
                highlights.append((video_start_ts, video_max_ts, result["tier"], name))
        else:
            print(f"  [{i+1:2d}/{len(clips)}] {tag}{name}  →  {tier_str}")

        running += dur

    # ── Write output file ──────────────────────────────────────────────────────
    out_dir  = os.path.join(OUTPUT_DIR, "output", batch_name)
    out_path = os.path.join(out_dir, f"{batch_name}_timestamps.txt")
    lines = [f"Multi-kill timestamps — {batch_name}\n"]
    lines.append("Format: <streak start> - <max kill time> = Kill tier\n\n")
    if highlights:
        for start_ts, max_ts, tier, clip in highlights:
            lines.append(f"{fmt(start_ts)} - {fmt(max_ts)} = {tier.capitalize()} Kill\n")
    else:
        lines.append("(no Quad+ kills detected)\n")

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.writelines(lines)

    total = time.perf_counter() - t_batch
    print(f"\n{'─' * 60}")
    print(f"Quad+ highlights ({batch_name}):")
    for start_ts, max_ts, tier, clip in highlights:
        print(f"  {fmt(start_ts)} - {fmt(max_ts)} = {tier.capitalize()} Kill")
    print(f"\nCompleted in {total:.1f}s  |  Saved to: {out_path}")

# ── Entry points ──────────────────────────────────────────────────────────────

def run_ground_truth():
    print("=" * 60)
    print(f"GROUND TRUTH TEST: {Path(GROUND_TRUTH).name}")
    print("Expected: QUAD KILL  |  streak start ~0:06")
    print("=" * 60)
    result = scan_clip(GROUND_TRUTH, debug=True, use_cache=False)
    print()
    if result:
        print(f"RESULT:  {result['tier']} KILL")
        print(f"Streak:  {fmt(result['start_ts'])} → {fmt(result['end_ts'])}")
        print(f"Events:  {', '.join(e['tier'] + '@' + fmt(e['ts']) for e in result['events'])}")
        ok_tier  = result["tier"] == "QUAD"
        ok_start = abs(result["start_ts"] - 6) <= 3
        print(f"\n  Tier:   {'PASS' if ok_tier  else 'FAIL'}  (got {result['tier']}, want QUAD)")
        print(f"  Start:  {'PASS' if ok_start else 'FAIL'}  (got {fmt(result['start_ts'])}, want ~0:06)")
    else:
        print("FAIL — no multi-kill detected")


def run_single(clip_path: str):
    print(f"Scanning: {Path(clip_path).name}")
    result = scan_clip(clip_path, debug=True, use_cache=False)
    print()
    if result:
        print(f"RESULT:  {result['tier']} KILL")
        print(f"Streak:  {fmt(result['start_ts'])} → {fmt(result['end_ts'])}")
        print(f"Events:  {', '.join(e['tier'] + '@' + fmt(e['ts']) for e in result['events'])}")
    else:
        print("No multi-kill detected.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        run_ground_truth()
    elif args[0] == "--batch" and len(args) > 1:
        batch = args[1]
        if batch not in BATCH_DIRS:
            print(f"Unknown batch: {batch}. Known batches: {list(BATCH_DIRS)}")
            sys.exit(1)
        clips_dir = os.path.join(CLIPS_BASE, BATCH_DIRS[batch])
        run_batch(batch, get_clips(clips_dir), clips_dir)
    else:
        run_single(args[0])
