"""
ko_detect.py - Multi-kill tier detection for Marvel Rivals clips.

Uses FFmpeg + Tesseract OCR to read the kill banner on the right side of the screen.

Default mode: pass 1 only (2fps). Clips where pass 1 finds nothing or only a single
KO are considered low-value and surfaced to the user for deletion.

Pass 2 (8fps, full-clip, no early exit) is kept in code but disabled by default.
Enable via use_pass2=True in scan_clip() -- used by rescan_and_report.py for data
collection runs where every result is recorded regardless of tier value.

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

import logging
import subprocess, os, sys, tempfile, shutil, glob, re, json, time, math, threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter
import pytesseract
import clip_cache
import winproc

try:
    import ko_ncc          # needs numpy + opencv-python; scan_video falls back to OCR without them
except ImportError as _ncc_err:
    ko_ncc = None
    _NCC_IMPORT_ERROR = str(_ncc_err)

_log = logging.getLogger("ko_detect")

# ── Config ────────────────────────────────────────────────────────────────────

FFMPEG       = r"C:\Users\David\GitHubRepos\RivalsVidMaker\dependencies\ffmpeg\ffmpeg.exe"
FFPROBE      = r"C:\Users\David\GitHubRepos\RivalsVidMaker\dependencies\ffmpeg\ffprobe.exe"
TESSERACT    = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
CLIPS_BASE   = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR"
CACHE_DIR    = r"C:\Users\David\GitHubRepos\RivalsVidMaker\data\cache\THOR"
OUTPUT_DIR   = r"C:\Users\David\GitHubRepos\RivalsVidMaker\data"
GROUND_TRUTH = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR\vid1_uploaded\THOR_2026-02-06_22-38-56.mp4"

pytesseract.pytesseract.tesseract_cmd = TESSERACT


def configure(
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
    tesseract: str | None = None,
    cache_dir: str | None = None,
) -> None:
    """
    Override module-level paths at runtime.

    Called by pipeline.py so the full pipeline can use config.txt paths
    rather than the hardcoded defaults above. Standalone usage (running
    ko_detect.py directly) is unaffected - defaults still apply.
    """
    global FFMPEG, FFPROBE, TESSERACT, CACHE_DIR
    if ffmpeg:
        FFMPEG = ffmpeg
    if ffprobe:
        FFPROBE = ffprobe
    if tesseract:
        TESSERACT = tesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract
    if cache_dir:
        CACHE_DIR = cache_dir


# ── Detection parameters ───────────────────────────────────────────────────────

# Constants derived from statistical analysis of 64 clips (2026-03-31).
# Source: data/analysis/ko_analysis_report_20260331.md (local analysis report, not in the repo)
SCAN_FPS_FAST        = 2     # pass 1: quick sweep (most multi-kills caught here)
SCAN_FPS_FULL        = 8     # pass 2: thorough retry; 0.125s resolution makes brief banners infallible
SKIP_SECS            = 6     # skip first N seconds; data: earliest KO = 7.0s, -1s safety margin
RISE_MIN_GAP_SECS    = 0.5   # peak-stamped chains are about 1.3 s apart; a closer higher peak is a split banner
SHORT_DECODE_FRAMES  = 2     # a decode may come up this many frames short of round(length * fps) before it is truncated
COOLDOWN_SECS        = 2.0   # min gap between distinct kill events (keep low -- p10 inter-kill = 2s)
SCAN_STOP_SECS       = 22    # pass 1 early exit if no KO found; data: p90 start_ts = 18.5s + 3.5s buffer
POST_KO_SILENCE_SECS = 16    # exit after N seconds silence post-sequence; data: p90 sequence duration = 16s

# Banner region: right 25% of frame width, vertically 40 to 62%
CROP_X  = 0.75
CROP_Y1 = 0.40
CROP_Y2 = 0.62

TIERS              = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
TIER_RANK          = {t: i for i, t in enumerate(TIERS)}
NULL_RESULT_SUFFIX = "UNKNOWN"  # appended to clips that were scanned but tier could not be determined

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
    return _tier_from_crop(crop_banner(img))


def _tier_from_crop(crop: Image.Image) -> str | None:
    """OCR an already-cropped banner region (shared by ocr_tier and scan_video)."""
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

def extract_frames(clip_path: str, tmpdir: str, fps: int = SCAN_FPS_FAST) -> list[tuple[float, str]]:
    pat = os.path.join(tmpdir, "f_%05d.png")
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "quiet",
         "-ss", str(SKIP_SECS), "-i", clip_path,
         "-vf", f"fps={fps}", "-q:v", "2", pat],
        check=True,
        creationflags=winproc.NO_WINDOW,
    )
    frames = sorted(glob.glob(os.path.join(tmpdir, "f_*.png")))
    return [(SKIP_SECS + i / fps, p) for i, p in enumerate(frames)]


def get_duration(clip_path: str) -> float:
    r = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", clip_path],
        capture_output=True, text=True,
        creationflags=winproc.NO_WINDOW,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0

# ── Cache ─────────────────────────────────────────────────────────────────────

def cache_path(clip_path: str) -> str:
    """Return the .clip.json path for a clip (delegates to clip_cache)."""
    return clip_cache.cache_path(clip_path, CACHE_DIR)


def cache_exists(clip_path: str) -> bool:
    """Return True only if a valid, up-to-date KO cache entry exists for this clip."""
    hit, entry = clip_cache.cache_load(clip_path, CACHE_DIR)
    if not hit or entry is None:
        return False
    return "ko_result" in entry


def cache_load(clip_path: str) -> tuple[bool, dict | None]:
    """
    Returns (hit, result).
      hit=False -> not in cache, stale, or KO scan not yet run for this clip
      hit=True, result=None  -> cached "no kill detected"
      hit=True, result=dict  -> cached kill data

    Uses clip_cache for storage. Reads ko_result field from .clip.json.
    """
    hit, entry = clip_cache.cache_load(clip_path, CACHE_DIR)
    if not hit or entry is None:
        return False, None
    if "ko_result" not in entry:
        # Clip is cached (duration etc.) but KO scan not yet run
        return False, None
    return True, entry["ko_result"]  # ko_result may be None (scanned, no kill found)


def cache_save(
    clip_path: str,
    result: dict | None,
    *,
    clip_duration: float | None = None,
    scan_time: float | None = None,
    scan_pass: int | None = None,
):
    """Write KO result to the .clip.json cache entry.

    Partial update: only updates ko_result (and optional timing fields).
    Existing fields (duration, fingerprint, etc.) are preserved.

    scan_pass (1 or 2) records which pass detected the kill -- useful for tuning.
    """
    fields: dict = {"ko_result": result}
    if clip_duration is not None:
        fields["duration"] = round(clip_duration, 2)
    if scan_time is not None:
        fields["scan_time"] = round(scan_time, 2)
    if scan_pass is not None:
        fields["scan_pass"] = scan_pass
    clip_cache.cache_save(clip_path, CACHE_DIR, **fields)

# ── Core scan ─────────────────────────────────────────────────────────────────

def _scan_frames(frames: list[tuple[float, str]], debug: bool, stop_early: bool = True) -> dict | None:
    """Run OCR over a list of (timestamp, image_path) frames. Returns a result dict or None.

    stop_early=True  (pass 1): exits at SCAN_STOP_SECS if no KO found yet.
    stop_early=False (pass 2): scans the full clip regardless -- no early exit.
    """
    events       = []
    prev_tier    = None
    cooldown_end = 0.0
    last_active  = None

    for ts, path in frames:
        # Early exit: no KO yet and past the likely-KO window
        if stop_early and not events and ts > SCAN_STOP_SECS:
            if debug:
                print(f"  [early exit: no KO by {SCAN_STOP_SECS}s]")
            break
        # Early exit: kill sequence is done -- enough silence has elapsed
        if events and last_active and (ts - last_active) > POST_KO_SILENCE_SECS:
            if debug:
                print(f"  [early exit: {ts - last_active:.1f}s silence after last kill]")
            break

        tier = ocr_tier(path)

        if debug:
            label = f"-> {tier}" if tier else "(none)"
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
        return None

    max_event = max(events, key=lambda e: TIER_RANK.get(e["tier"], 0))
    return {
        "tier":     max_event["tier"],
        "start_ts": events[0]["ts"],
        "max_ts":   max_event["ts"],
        "end_ts":   (last_active or events[-1]["ts"]) + 1.0,
        "events":   events,
    }


def scan_clip(
    clip_path: str,
    debug: bool = False,
    use_cache: bool = True,
    use_pass2: bool = False,
) -> dict | None:
    """
    KO detection. Pass 1 (2fps) runs always. Pass 2 (8fps, full clip) is optional.

    use_pass2=False (default): pass 1 only. Clips that return null or KO-tier are
        low-value; the caller decides what to do with them (preprocess prompts deletion).
    use_pass2=True: if pass 1 returns null, retry at SCAN_FPS_FULL with no early exit.
        Used by rescan_and_report.py for full data collection.

    Returns:
        {
            "tier":      "QUAD",   # highest tier achieved
            "start_ts":  6.0,      # when FIRST banner appeared (streak start)
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

    t_scan_start = time.perf_counter()
    clip_dur = get_duration(clip_path)
    tmpdir = tempfile.mkdtemp(prefix="ko_")
    try:
        # Pass 1: fast sweep
        frames = extract_frames(clip_path, tmpdir, fps=SCAN_FPS_FAST)
        result = _scan_frames(frames, debug)
        scan_pass = 1

        if result is None and use_pass2:
            # Pass 2: thorough retry at higher FPS, no early exit
            # stop_early=False ensures SCAN_STOP_SECS doesn't suppress kills near/after that window
            if debug:
                print(f"  [pass 1 null - retrying at {SCAN_FPS_FULL}fps, full clip, no early exit]")
            for f in glob.glob(os.path.join(tmpdir, "f_*.png")):
                try:
                    os.remove(f)
                except OSError:
                    pass
            frames = extract_frames(clip_path, tmpdir, fps=SCAN_FPS_FULL)
            result = _scan_frames(frames, debug, stop_early=False)
            scan_pass = 2

        elapsed = time.perf_counter() - t_scan_start
        cache_save(clip_path, result, clip_duration=clip_dur, scan_time=elapsed, scan_pass=scan_pass)
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

# ── Long-video scan ───────────────────────────────────────────────────────────
# scan_clip stays the short-clip path. scan_video is for compilations and VODs: one ffmpeg
# per 600 s chunk crops the banner ROI in ffmpeg and pipes gray rawvideo (no PNG files), an
# OCR thread pool reads the frames, and each finished chunk is checkpointed atomically so a
# killed run resumes with byte-identical chunk files. No early exit, no 22 s cap.

SCANNER_VERSION     = "long-scan-4"   # 3: NCC default (ko_ncc), OCR is detector="ocr"; 4: fast NCC profile (10 fps, auto chunks, NVDEC lane)
DEFAULT_DETECTOR    = "ncc"           # scan_video(detector=None) uses this; "ocr" is the Tesseract path
LONG_CHUNK_SECS     = 600
LONG_OVERLAP_SECS   = 5     # extra decoded tail per chunk; covers seek/fps edge frames
LONG_FPS            = 4     # Quad+ banners stay 2-4 s, so at least 8 samples each
RESCAN_FPS          = 8     # a TRIPLE re-reads the next RESCAN_SECS at this rate; Quad banners can flash < 0.5 s
RESCAN_SECS         = 12
SCENE_KEEP_MIN      = 5.0   # scdet scores below this are noise and not stored
_SCENE_RE           = re.compile(r"lavfi\.scd\.score:\s*([0-9.]+),\s*lavfi\.scd\.time:\s*([0-9.]+)")


def roi_geometry(width: int, height: int) -> tuple[int, int, int, int]:
    """(crop_w, crop_h, x, y) of the banner ROI, identical to what crop_banner cuts."""
    x, y = int(width * CROP_X), int(height * CROP_Y1)
    return width - x, int(height * CROP_Y2) - y, x, y


def get_size(clip_path: str) -> tuple[int, int]:
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", clip_path],
        capture_output=True, text=True, creationflags=winproc.NO_WINDOW,
    )
    try:
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        raise RuntimeError(f"cannot read video size of {clip_path}: {r.stderr.strip()[:200]}")


class _FfmpegDecode:
    """Iterable of gray ROI frames (bytes) from one ffmpeg run; .scenes fills as it streams."""

    def __init__(self, video, start, length, geom, fps):
        cw, ch, x, y = geom
        self.scenes: list[tuple[float, float]] = []
        self._size = cw * ch * 3   # rgb24: gray from the YUV plane differs from PNG->PIL luma and OCRs worse
        graph = (f"[0:v]split=2[a][b];"
                 f"[a]fps={fps},crop={cw}:{ch}:{x}:{y},format=rgb24[roi];"
                 f"[b]scale=320:-2,scdet=threshold=0[sc]")
        cmd = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "info", "-nostdin",
               "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", video, "-an", "-sn",
               "-filter_complex", graph,
               "-map", "[roi]", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
               "-map", "[sc]", "-f", "null", "-"]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      creationflags=winproc.NO_WINDOW)
        self._err_tail: deque = deque(maxlen=20)
        self._reader = threading.Thread(target=self._drain_stderr, daemon=True)
        self._reader.start()

    def _drain_stderr(self):
        for raw in self._proc.stderr:
            line = raw.decode("utf-8", "replace")
            m = _SCENE_RE.search(line)
            if m:
                self.scenes.append((float(m.group(2)), float(m.group(1))))
            else:
                self._err_tail.append(line.rstrip())

    def __iter__(self):
        try:
            while True:
                data = self._proc.stdout.read(self._size)
                if len(data) < self._size:
                    break
                yield data
            self._proc.wait()
            self._reader.join(timeout=10)
            if self._proc.returncode != 0:
                raise RuntimeError(f"ffmpeg failed ({self._proc.returncode}): " + " | ".join(self._err_tail))
        finally:
            if self._proc.poll() is None:
                self._proc.kill()
                self._proc.wait()


def _ffmpeg_runner(video, start, length, geom, fps):
    return _FfmpegDecode(video, start, length, geom, fps)


def _roi_to_gray(data: bytes, width: int, height: int) -> Image.Image:
    return Image.frombytes("RGB", (width, height), data).convert("L")


def _ocr_roi_bytes(data: bytes, width: int, height: int) -> str | None:
    return _tier_from_crop(Image.frombytes("RGB", (width, height), data))


def _rescan_triples(video, events, duration, geom, runner, ocr_fn, workers) -> list[tuple[float, str | None]]:
    """Extra high-fps samples for the RESCAN_SECS after every TRIPLE not already followed by a Quad+."""
    cw, ch = geom[0], geom[1]
    extra: list[tuple[float, str | None]] = []
    quad = TIER_RANK["QUAD"]
    for ev in events:
        if ev["tier"] != "TRIPLE":
            continue
        end = ev["ts"] + RESCAN_SECS
        if any(e["ts"] > ev["ts"] and e["ts"] <= end and TIER_RANK[e["tier"]] >= quad for e in events):
            continue
        start = max(0.0, ev["ts"])
        length = min(RESCAN_SECS, duration - start)
        if length <= 0:
            continue
        decode = runner(video, start, length, geom, RESCAN_FPS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(ocr_fn, d, cw, ch) for d in decode]
            extra += [(start + k / RESCAN_FPS, f.result()) for k, f in enumerate(futs)]
    return extra


def _atomic_write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _chunk_meta(video, idx, chunk_secs, overlap_secs, fps, geom) -> dict:
    try:
        nbytes = os.path.getsize(video)
    except OSError:
        nbytes = None
    return {"scanner_version": SCANNER_VERSION, "chunk": idx, "chunk_secs": chunk_secs,
            "overlap_secs": overlap_secs, "fps": fps, "geom": list(geom),
            "source": os.path.basename(video), "source_bytes": nbytes}


def _load_chunk(path: str, meta: dict) -> dict | None:
    """The checkpoint at path if it is finished and matches meta, else None."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in meta.items()):
        return None
    return data


def _scan_chunk(video, start, length, geom, fps, runner, ocr_fn, pool, limit) -> tuple[list, list]:
    """Decode one chunk and OCR its frames in order. Returns (tiers, scenes) for the chunk."""
    cw, ch = geom[0], geom[1]
    decode = runner(video, start, length, geom, fps)
    pending: deque = deque()
    tiers: list = []
    try:
        for data in decode:
            pending.append(pool.submit(ocr_fn, data, cw, ch))
            while len(pending) > limit:
                tiers.append(pending.popleft().result())
        while pending:
            tiers.append(pending.popleft().result())
    except BaseException:
        for fut in pending:
            fut.cancel()
        raise
    expected = int(length * fps)
    if len(tiers) < expected - 1:
        raise RuntimeError(f"chunk at {start}s produced {len(tiers)} frames, expected about {expected}")
    return tiers, [(round(start + t, 3), round(s, 3)) for t, s in decode.scenes if s >= SCENE_KEEP_MIN]


def _events_from_samples(samples: list[tuple[float, str | None]], rise_ignores_cooldown: bool = False) -> list[dict]:
    """
    The _scan_frames event rules (rank rise, cooldown, prev-tier reset) with no early exit.
    rise_ignores_cooldown: for peak-stamped samples (one per run) a higher tier is always its own event, because
    consecutive peaks of a QUAD -> PENTA -> HEXA chain can sit closer together than COOLDOWN_SECS. A rising peak
    under RISE_MIN_GAP_SECS after the previous peak is a split banner misread, not a chain, and stays suppressed.
    """
    events, prev_tier, cooldown_end, last_active = [], None, 0.0, None
    for ts, tier in samples:
        rank, prev_rank = TIER_RANK.get(tier, -1), TIER_RANK.get(prev_tier, -1) if prev_tier else -1
        rising = (bool(tier) and rise_ignores_cooldown and prev_tier is not None and rank > prev_rank
                  and last_active is not None and ts - last_active >= RISE_MIN_GAP_SECS)
        if tier and (ts >= cooldown_end or rising):
            if prev_tier is None or rank > prev_rank:
                events.append({"tier": tier, "ts": ts})
                cooldown_end, prev_tier = ts + COOLDOWN_SECS, tier
            elif tier == prev_tier:
                cooldown_end = ts + COOLDOWN_SECS
        if tier:
            last_active = ts
        elif last_active is not None and (ts - last_active) > COOLDOWN_SECS * 2:
            prev_tier = None
    return events


def _ocr_ambiguous_runs(video_path, runs, geom, runner, ocr_fn, fps) -> None:
    """Re-read the peak frame of every run whose top two tier scores are within ko_ncc.AMBIG_MARGIN.
    A recognised tier replaces the run's tier; any OCR failure or unreadable frame keeps the NCC answer."""
    cw, ch = geom[0], geom[1]
    for r in runs:
        if r["margin"] >= ko_ncc.AMBIG_MARGIN:
            continue
        try:
            for data in runner(video_path, max(0.0, r["peak"] / fps), 0.5, geom, 4):
                tier = ocr_fn(data, cw, ch)
                if tier in TIER_RANK:
                    _log.info("scan_video: OCR settled ambiguous run at %.2fs: %s -> %s", r["peak"] / fps, r["tier"], tier)
                    r["tier"] = tier
                break
        except Exception as e:                  # OCR is a best-effort tiebreak, never fatal
            _log.warning("scan_video: OCR tiebreak failed at %.2fs (%s); keeping %s", r["peak"] / fps, e, r["tier"])


def _ncc_lanes(with_scenes: bool, workers, nvdec, crop, size) -> dict:
    """
    Pick the NCC scan profile. with_scenes=True or an explicit worker count keeps the legacy decode (60 s chunks,
    15 fps, scdet, CPU only). Otherwise the fast profile: NVDEC lane when allowed, detected and the ROI is
    cuvid-croppable (4 CPU + 3 NVDEC workers), else the same fast decode on 8 CPU workers. Never raises.
    """
    if with_scenes:
        return {"profile": "legacy", "fps": ko_ncc.FPS, "chunk_secs": ko_ncc.CHUNK_SECS,
                "cpu": workers or ko_ncc.WORKERS, "nvdec": 0}
    p = ko_ncc.FAST
    use_nv = (nvdec is not False and not workers and ko_ncc.nvdec_available(FFMPEG)
              and ko_ncc.nvdec_crop_ok(crop, size))
    cpu = workers or (p["cpu_workers"] if use_nv else ko_ncc.ALL_CPU_WORKERS)
    return {"profile": "fast", "fps": p["fps"], "chunk_secs": p["chunk_secs"], "cpu": cpu,
            "nvdec": p["nvdec_workers"] if use_nv else 0}


def _scan_video_ncc(video_path, plan, duration, geom, checkpoint_dir, progress, runner, ocr_fn, workers, resume, t0,
                    with_scenes=False, nvdec=None, size=None) -> dict:
    """
    The detector="ncc" body of scan_video: chunks of scores, checkpointed, merged, then runs and events.

    Default is the fast profile (ko_ncc.FAST, bench candidate ncc_hybrid_4c3n): balanced auto chunks (one per
    worker), 10 fps, noref + no loop filter, 4 CPU + 3 NVDEC workers (all-CPU on 8 workers without NVIDIA).
    Design decisions, so a later reader need not rediscover them:
    - Checkpoints stay per chunk, but a chunk is now about duration / 7 long (minutes, not 60 s), so a killed
      scan resumes at that coarser grain. The chunk length is a pure function of duration and the lane layout,
      and chunk_secs / fps / profile are in the chunk meta, so resume stays correct and a different layout
      rescans instead of mixing grids. Lane (CPU or NVDEC) is deliberately NOT in the meta: both give valid scores.
    - The fast lanes decode the ROI only, so "scenes" is [] on them. with_scenes=True selects the legacy
      profile (60 s chunks, 15 fps, scdet, CPU only) for callers that need scene peaks.
    - An NVDEC chunk that fails to decode is redone on the CPU lane (silent, debug log); a failed CPU decode raises.
    decode / decode_fast / decode_nvdec are looked up on ko_ncc at call time so tests can swap them.
    """
    import numpy as np
    bank, crop = plan["bank"], plan["crop"]
    vsize = size or get_size(video_path)
    lay = _ncc_lanes(with_scenes, workers, nvdec, crop, vsize)
    fps = lay["fps"]
    n_workers = lay["cpu"] + lay["nvdec"]
    chunk_secs = ko_ncc.chunk_len(duration, n_workers, lay["chunk_secs"])
    n_chunks = math.ceil(duration / chunk_secs)
    total = int(duration * fps)
    lanes = ko_ncc.split_lanes(n_chunks, lay["cpu"], lay["nvdec"])
    sig = ko_ncc.bank_signature()

    def one(i: int):
        start = i * chunk_secs
        length = min(chunk_secs, duration - start)
        meta = {"scanner_version": SCANNER_VERSION, "detector": "ncc", "chunk": i, "chunk_secs": chunk_secs,
                "fps": fps, "crop": list(crop), "bank": sig, "profile": lay["profile"],
                "source": os.path.basename(video_path), "source_bytes": _file_size(video_path)}
        path = os.path.join(checkpoint_dir, f"chunk_{i:04d}.json")
        tc = time.perf_counter()
        expected = round(length * fps)
        data = _load_chunk(path, meta) if resume else None
        if data is not None and len(data.get("scores") or []) < expected - SHORT_DECODE_FRAMES:
            data = None                                      # a checkpoint holding too few frames is rescanned, never merged
        was_reused = data is not None
        if data is None:
            def need_full(fr, lane):
                if len(fr) < expected - SHORT_DECODE_FRAMES:
                    raise RuntimeError(f"short decode on {lane} lane at {start:.1f}s: {len(fr)} of {expected} frames")
                return fr

            if lay["profile"] == "legacy":
                frames, scenes = ko_ncc.decode(FFMPEG, video_path, start, length, fps, crop)
                need_full(frames, "legacy")
            else:
                frames, scenes = None, []
                if lanes[i] == "nvdec":
                    try:
                        frames = need_full(ko_ncc.decode_nvdec(FFMPEG, video_path, start, length, fps, crop, vsize), "nvdec")
                    except Exception as e:                  # per-chunk fallback: the CPU lane redoes this chunk
                        _log.debug("scan_video: NVDEC chunk %d failed (%s); decoding on the CPU", i, e)
                if frames is None:
                    frames = need_full(ko_ncc.decode_fast(FFMPEG, video_path, start, length, fps, crop), "cpu")
            frames = frames[:expected]
            scores = ko_ncc.frame_scores(frames, bank)
            data = {**meta, "first_idx": round(start * fps), "scores": np.round(scores, 3).tolist(),
                    "scenes": [[round(start + t, 3), round(s, 3)] for t, s in scenes]}
            _atomic_write_json(path, data)
        return i, data, was_reused, time.perf_counter() - tc

    owned: list[tuple[int, dict]] = []
    reused = 0
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = [pool.submit(one, i) for i in range(n_chunks)]
        try:
            for done, fut in enumerate(as_completed(futs), 1):
                i, data, was_reused, secs = fut.result()
                reused += was_reused
                owned.append((i, data))
                if progress:
                    progress(done, n_chunks, {"chunk": i, "reused": was_reused, "secs": secs})
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    parts = [(d["first_idx"], np.asarray(d["scores"], np.float32).reshape(-1, len(bank["tiers"])))
             for _, d in sorted(owned)]
    scores = ko_ncc.merge_scores(parts, total)
    runs = ko_ncc.runs_from_scores(scores, bank["tiers"], fps)
    _ocr_ambiguous_runs(video_path, runs, geom, runner or _ffmpeg_runner, ocr_fn or _ocr_roi_bytes, fps)
    timeline = ko_ncc.timeline_from_runs(runs, total, fps)
    scenes = sorted((t, s) for _, d in owned for t, s in d["scenes"])
    return {
        "video": video_path, "duration": duration, "fps": fps, "scanner_version": SCANNER_VERSION,
        "detector": "ncc", "chunks": n_chunks, "chunks_reused": reused, "timeline": timeline,
        # events are stamped at each run's peak frame (not its first), so a chained TRIPLE -> QUAD run gives the QUAD time;
        # "timeline" keeps the per-frame run labels
        "events": _events_from_samples(ko_ncc.peak_timeline(runs, total, fps), rise_ignores_cooldown=True),
        "scenes": scenes,
        "scan_time": time.perf_counter() - t0,
    }


def _file_size(path: str):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def scan_video(
    video_path: str,
    *,
    checkpoint_dir: str,
    progress=None,
    runner=None,
    ocr_fn=None,
    duration: float | None = None,
    size: tuple[int, int] | None = None,
    chunk_secs: int = LONG_CHUNK_SECS,
    overlap_secs: int = LONG_OVERLAP_SECS,
    fps: int = LONG_FPS,
    workers: int | None = None,
    resume: bool = True,
    detector: str | None = None,
    with_scenes: bool = False,
    nvdec: bool | None = None,
) -> dict:
    """
    Scan a long video (compilation or VOD) end to end for kill banners.

    detector "ncc" (the default, DEFAULT_DETECTOR) matches the tier word against the template
    bank in ko_ncc: about 8x faster than OCR, own chunk checkpoints, OCR only for runs whose
    top two tier scores are close. It falls back to OCR with a log line when the frame size, the
    bank or opencv is unusable. NCC runs the fast profile by default (ko_ncc.FAST: auto chunks, 10 fps,
    optional NVDEC lane with silent CPU fallback; no scenes). with_scenes=True selects the legacy
    60 s / 15 fps / scdet CPU profile so "scenes" is filled; nvdec=False disables the NVDEC lane. detector "ocr" is the original Tesseract path described below
    (chunk_secs, overlap_secs and fps apply to it only). Both return the same shape plus "detector".

    OCR path: chunks of chunk_secs (plus overlap_secs of tail) are decoded one at a time; each is
    checkpointed to checkpoint_dir/chunk_NNNN.json. With resume=True a chunk whose file
    matches the current scanner version and parameters is reused, not rescanned.

    progress(done_chunks, total_chunks, info) is called after every chunk
    (info = {"chunk", "reused", "secs"}). runner(video, start, length, geom, fps) returns
    an iterable of gray ROI frames with a .scenes list; ocr_fn(data, w, h) returns a tier
    or None. Both are injectable for tests. The caller owns checkpoint_dir (the OldCompilations
    run passes it through oldcomp_guard.assert_outside_oldcomp first).

    Returns {"video", "duration", "fps", "scanner_version", "chunks", "chunks_reused",
    "timeline": [(t, tier_or_None)] one per sample, "events": [{"tier","ts"}] with the
    scan_clip rank/cooldown rules, "scenes": [(t, score)] with score >= SCENE_KEEP_MIN,
    "scan_time"}.
    """
    t0 = time.perf_counter()
    runner = runner or _ffmpeg_runner
    ocr_fn = ocr_fn or _ocr_roi_bytes
    duration = get_duration(video_path) if duration is None else duration
    if duration <= 0:
        raise RuntimeError(f"cannot read duration of {video_path}")
    detector = detector or DEFAULT_DETECTOR
    if detector not in ("ncc", "ocr"):
        raise ValueError(f"unknown detector {detector!r}, expected 'ncc' or 'ocr'")
    size = size or get_size(video_path)
    geom = roi_geometry(*size)
    os.makedirs(checkpoint_dir, exist_ok=True)
    if detector == "ncc":
        plan, why = None, None
        if ko_ncc is None:
            why = f"ko_ncc unavailable ({_NCC_IMPORT_ERROR})"
        else:
            try:
                plan = ko_ncc.plan(*size)
            except (ValueError, OSError, KeyError) as e:      # UnsupportedSize is a ValueError
                why = str(e)
        if plan is not None:
            return _scan_video_ncc(video_path, plan, duration, geom, checkpoint_dir, progress, runner, ocr_fn,
                                   workers, resume, t0, with_scenes=with_scenes, nvdec=nvdec, size=size)
        _log.warning("scan_video: NCC detector not usable for %s (%s); falling back to OCR", video_path, why)
        detector = "ocr"
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")   # one tesseract thread per worker, no oversubscription
    n_chunks = math.ceil(duration / chunk_secs)
    own_len = chunk_secs * fps                         # grid samples owned per chunk
    frame_tier: dict[int, str | None] = {}
    scenes: list[tuple[float, float]] = []
    owned: list[dict] = []
    reused = 0

    n_workers = workers or min(12, os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:   # in-flight frames bounded at 4x workers
        try:
            for i in range(n_chunks):
                start = i * chunk_secs
                length = min(chunk_secs + overlap_secs, duration - start)
                path = os.path.join(checkpoint_dir, f"chunk_{i:04d}.json")
                meta = _chunk_meta(video_path, i, chunk_secs, overlap_secs, fps, geom)
                tc = time.perf_counter()
                data = _load_chunk(path, meta) if resume else None
                was_reused = data is not None
                if data is None:
                    tiers, sc = _scan_chunk(video_path, start, length, geom, fps, runner, ocr_fn, pool, n_workers * 4)
                    data = {**meta, "first_idx": round(start * fps), "tiers": tiers,
                            "scenes": [list(s) for s in sc]}
                    _atomic_write_json(path, data)
                reused += was_reused
                owned.append(data)
                if progress:
                    progress(i + 1, n_chunks, {"chunk": i, "reused": was_reused, "secs": time.perf_counter() - tc})
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise

    # Merge: overlap samples first, then each chunk's owned samples win (dedup by grid index).
    for i, data in enumerate(owned):
        lo, hi = i * own_len, (i + 1) * own_len if i < n_chunks - 1 else float("inf")
        for k, tier in enumerate(data["tiers"]):
            idx = data["first_idx"] + k
            if not (lo <= idx < hi):
                frame_tier.setdefault(idx, tier)
        for t, s in data["scenes"]:
            if lo <= round(t * fps) < hi:
                scenes.append((t, s))
    for i, data in enumerate(owned):
        lo, hi = i * own_len, (i + 1) * own_len if i < n_chunks - 1 else float("inf")
        for k, tier in enumerate(data["tiers"]):
            idx = data["first_idx"] + k
            if lo <= idx < hi:
                frame_tier[idx] = tier

    timeline = [(idx / fps, frame_tier[idx]) for idx in sorted(frame_tier)]
    extra = _rescan_triples(video_path, _events_from_samples(timeline), duration, geom, runner, ocr_fn, n_workers)
    if extra:
        timeline = sorted(timeline + extra, key=lambda p: p[0])
    return {
        "video": video_path, "duration": duration, "fps": fps, "scanner_version": SCANNER_VERSION,
        "detector": "ocr", "chunks": n_chunks, "chunks_reused": reused, "timeline": timeline,
        "events": _events_from_samples(timeline), "scenes": sorted(scenes),
        "scan_time": time.perf_counter() - t0,
    }

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
        tier_str = result["tier"] if result else "-"
        tag      = "[cached] " if was_cached else f"[{elapsed:.1f}s]  "

        if result:
            video_start_ts = running + result["start_ts"]
            video_max_ts   = running + result["max_ts"]
            print(f"  [{i+1:2d}/{len(clips)}] {tag}{name}  ->  {tier_str}  ({fmt(video_start_ts)}-{fmt(video_max_ts)} in video)")
            if TIER_RANK.get(result["tier"], 0) >= TIER_RANK[REPORT_MIN_TIER]:
                highlights.append((video_start_ts, video_max_ts, result["tier"], name))
        else:
            print(f"  [{i+1:2d}/{len(clips)}] {tag}{name}  ->  {tier_str}")

        running += dur

    # ── Write output file ──────────────────────────────────────────────────────
    out_dir  = os.path.join(OUTPUT_DIR, "output", batch_name)
    out_path = os.path.join(out_dir, f"{batch_name}_timestamps.txt")
    lines = [f"Multi-kill timestamps - {batch_name}\n"]
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
        print(f"Streak:  {fmt(result['start_ts'])} -> {fmt(result['end_ts'])}")
        print(f"Events:  {', '.join(e['tier'] + '@' + fmt(e['ts']) for e in result['events'])}")
        ok_tier  = result["tier"] == "QUAD"
        ok_start = abs(result["start_ts"] - 6) <= 3
        print(f"\n  Tier:   {'PASS' if ok_tier  else 'FAIL'}  (got {result['tier']}, want QUAD)")
        print(f"  Start:  {'PASS' if ok_start else 'FAIL'}  (got {fmt(result['start_ts'])}, want ~0:06)")
    else:
        print("FAIL - no multi-kill detected")


def run_single(clip_path: str):
    print(f"Scanning: {Path(clip_path).name}")
    result = scan_clip(clip_path, debug=True, use_cache=False)
    print()
    if result:
        print(f"RESULT:  {result['tier']} KILL")
        print(f"Streak:  {fmt(result['start_ts'])} -> {fmt(result['end_ts'])}")
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
