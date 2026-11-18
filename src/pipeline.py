"""
pipeline.py - Main orchestrator: sort → scan → batch → detect → encode → describe.

A compile is split in two:
  plan_compile  - reads the folder, scans KO tiers and duplicates. No renames, no moves.
  apply_compile - carries out a plan from a decisions dict. Never prompts.
run() is the terminal wrapper: it asks the questions and builds the decisions.
"""

import logging
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import ko_detect
from send2trash import send2trash
from batcher import Batch, make_batches
from dedup import find_duplicates, print_dup_table
import clip_cache
from clip_scanner import VIDEO_EXTS, Clip, scan_folder, summarize_folder
from clip_sorter import sort_clips
from config import Config
from description_writer import fmt_ts, write_description
from encoder import encode
from progress import AnimatedTicker
from menu import pick_action
from preprocess import preprocess_all
from state import is_youtube_confirmed, load as load_state
import uploader


# ── KO scan helpers ──────────────────────────────────────────────────────────

def _ko_scan_one(clip_path: str, clip_name: str) -> tuple[str, dict | None, float, bool]:
    """Thread worker for a single clip KO scan.

    Returns (clip_name, result, elapsed_secs, was_cached).
    was_cached is checked *before* calling scan_clip so the flag is accurate
    even when multiple threads are scanning simultaneously.
    """
    was_cached = ko_detect.cache_exists(clip_path)
    t0 = time.perf_counter()
    result = ko_detect.scan_clip(clip_path, use_cache=True)
    elapsed = time.perf_counter() - t0
    return clip_name, result, elapsed, was_cached


def _scan_batch(
    batch, config: Config
) -> tuple[dict[str, tuple[dict | None, float, bool]], dict[str, float]]:
    """
    Scan each clip for KO events in parallel. Writes KO cache files only, never renames.

    Returns:
      scan_results - {clip.name: (result, elapsed, was_cached)}
      offsets      - {clip.name: start offset in the compiled video, seconds}
    """
    ko_detect.configure(
        ffmpeg=str(config.ffmpeg),
        tesseract=str(config.tesseract),
        cache_dir=str(clip_cache.character_cache_dir(config.cache_dir, batch.clips[0].path.parent.name)),
    )

    total = len(batch.clips)

    # Compute running video offsets upfront (clip order determines timestamps)
    offsets: dict[str, float] = {}
    running = 0.0
    for clip in batch.clips:
        offsets[clip.name] = running
        running += clip.duration

    # Scan all clips in parallel - FFmpeg + Tesseract are external processes,
    # so threads give real concurrency. Each clip writes to its own cache file.
    scan_results: dict[str, tuple[dict | None, float, bool]] = {}

    with AnimatedTicker("Scanning", total=total) as ticker:
        with ThreadPoolExecutor(max_workers=ko_detect.N_WORKERS) as pool:
            future_to_clip = {
                pool.submit(_ko_scan_one, str(clip.path), clip.name): clip
                for clip in batch.clips
            }
            for future in as_completed(future_to_clip):
                clip = future_to_clip[future]
                clip_name, result, elapsed, was_cached = future.result()
                scan_results[clip_name] = (result, elapsed, was_cached)
                ticker.increment()

                tier_found = result["tier"] if result else None
                logging.debug(
                    "KO scan: %s %.1fs%s", clip_name, elapsed,
                    f" {tier_found}" if tier_found else "",
                )
                if tier_found and ko_detect.TIER_RANK.get(tier_found, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
                    video_start = offsets[clip_name] + result["start_ts"]
                    video_max = offsets[clip_name] + result["max_ts"]
                    logging.debug("%s @ %s-%s", tier_found, fmt_ts(video_start), fmt_ts(video_max))

    return scan_results, offsets


def _rename_tiered(batch, scan_results: dict, offsets: dict) -> None:
    """Rename clips in-place to embed their KO tier (e.g. THOR_..._QUAD.mp4). Writes files."""
    _tier_set = set(ko_detect.TIERS)
    for clip in batch.clips:
        result, _e, _c = scan_results.get(clip.name, (None, 0.0, False))
        if not result:
            continue
        tier = result["tier"]
        stem = clip.path.stem
        if any(stem.endswith(f"_{t}") for t in _tier_set) or stem.endswith(f"_{ko_detect.NULL_RESULT_SUFFIX}"):
            continue  # already renamed
        old_path = clip.path
        new_path = old_path.with_stem(f"{stem}_{tier}")
        try:
            old_path.rename(new_path)
            # Move cache file to match new stem so future runs still hit the cache
            old_cache = Path(ko_detect.cache_path(str(old_path)))
            new_cache = Path(ko_detect.cache_path(str(new_path)))
            if old_cache.exists() and not new_cache.exists():
                new_cache.parent.mkdir(parents=True, exist_ok=True)
                old_cache.rename(new_cache)
            scan_results[new_path.name] = scan_results.pop(clip.name)
            clip.path = new_path
            offsets[new_path.name] = offsets.pop(old_path.name)
            logging.info("Renamed: %s -> %s", old_path.name, new_path.name)
        except OSError as e:
            logging.warning("Could not rename %s: %s", old_path.name, e)


def _highlights_from_scan(
    batch, scan_results: dict, offsets: dict
) -> tuple[list[tuple[float, float, str, str]], dict[str, str]]:
    """
    Build ordered highlights and clip_tiers from scan results.

    Returns:
      highlights  - Quad+ kills with compilation timestamps, for the description.
      clip_tiers  - {clip.name: tier} for every clip where any kill was detected.
    """
    highlights: list[tuple[float, float, str, str]] = []
    clip_tiers: dict[str, str] = {}

    for clip in batch.clips:
        result, _, _ = scan_results.get(clip.name, (None, 0.0, False))
        if result:
            tier = result["tier"]
            clip_tiers[clip.name] = tier
            logging.debug("detected %s  start=%.1f  max=%.1f", tier, result["start_ts"], result["max_ts"])
            if ko_detect.TIER_RANK.get(tier, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
                video_start = offsets[clip.name] + result["start_ts"]
                video_max = offsets[clip.name] + result["max_ts"]
                highlights.append((video_start, video_max, tier, clip.name))

    return highlights, clip_tiers


def _collect_highlights(
    batch, config: Config
) -> tuple[list[tuple[float, float, str, str]], dict[str, str]]:
    """Scan, rename clips to embed their tier, and build highlights and clip_tiers."""
    scan_results, offsets = _scan_batch(batch, config)
    _rename_tiered(batch, scan_results, offsets)
    return _highlights_from_scan(batch, scan_results, offsets)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


def _mmss(seconds: float) -> str:
    """Duration in the Batch.duration_str format, e.g. 1m 05s."""
    s = int(seconds)
    return f"{s // 60}m {s % 60:02d}s"


_MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date_range(folder: Path) -> str:
    """Parse clip filenames to find the earliest and latest recording dates."""
    pat = re.compile(r'_(\d{4})-(\d{2})-(\d{2})_')
    dates = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            m = pat.search(p.name)
            if m:
                try:
                    dates.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                except ValueError:
                    pass
    if not dates:
        return "-"
    lo, hi = min(dates), max(dates)

    def _d(d: datetime) -> str:
        return f"{d.day} {_MONTH[d.month - 1]} '{d.year % 100:02d}"

    return _d(lo) if lo.date() == hi.date() else f"{_d(lo)} → {_d(hi)}"


def _menu_status(dur: float, target: int) -> str:
    if dur >= target:        return "✓ Ready"
    if dur >= target * 0.75: return "~ Almost"   # 11m15s+ at default 15m target
    if dur > 0:              return "✗ Too short"
    return "- No clips"


def _cache_exists(clip: Path, char_cache: Path) -> bool:
    """Check whether a .clip.json with ko_result exists for a clip.

    Uses ko_detect.cache_exists() which checks for the ko_result field,
    so duration-only entries (no KO scan yet) correctly return False.
    """
    import ko_detect as _ko
    old_dir = _ko.CACHE_DIR
    _ko.CACHE_DIR = str(char_cache)
    try:
        return _ko.cache_exists(str(clip))
    finally:
        _ko.CACHE_DIR = old_dir


def _find_ko_none_clips(clips: list) -> list:
    """Return clips whose stem ends with _KO or _UNKNOWN (low-value tiers)."""
    return [c for c in clips if c.path.stem.endswith(("_KO", f"_{ko_detect.NULL_RESULT_SUFFIX}"))]


def _archive_clips(clips: list, char_name: str, config) -> None:
    """Move clips (and their .ko.json cache files) to ClipArchive/<char_name>/."""
    dest_dir = config.archive_path / char_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        dest = dest_dir / clip.path.name
        shutil.move(str(clip.path), str(dest))
        logging.info("  Archived: %s -> %s", clip.path.name, dest_dir)
        cache_file = Path(ko_detect.cache_path(str(clip.path)))
        if cache_file.exists():
            shutil.move(str(cache_file), str(dest_dir / cache_file.name))


def _write_manifest(out_dir: Path, slug: str, char_name: str, batch, clip_tiers: dict) -> None:
    """Write clips.json to out_dir - authoritative record of what was compiled.

    Used by run_uncompile() to restore clips even if the clips/ dir is incomplete.
    """
    import json as _json
    from datetime import datetime as _dt

    manifest = {
        "slug": slug,
        "char": char_name,
        "compiled_at": _dt.now().isoformat(timespec="seconds"),
        "clips": [
            {"name": c.name, "tier": clip_tiers.get(c.name)}
            for c in batch.clips
        ],
    }
    manifest_path = out_dir / "clips.json"
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(_json.dumps(manifest, indent=2))
    tmp.replace(manifest_path)


def _retry_youtube_upload(output_folder: Path, config: Config) -> None:
    """Retry YouTube upload for a previously compiled video.

    Used when upload fails (e.g., auth error) but video is already compiled.
    Skips encode and goes straight to YouTube upload attempt.

    Looks for:
    - video.mp4 in output_folder root
    - video_description.txt in output_folder root
    """
    from cleanup import retry_upload

    # Delegates to the single retry path; no prompt, and a sign-in failure keeps the token.
    result = retry_upload(output_folder, config, confirm=False)
    if result.needs_sign_in:
        logging.warning("Token kept. Re-run after signing in with the correct account.")
    elif not result.uploaded and not result.cancelled and result.error:
        logging.warning("YouTube retry did not upload: %s", result.error)


def _batch_slug(char_name: str, batch) -> str:
    """Build the output folder/file stem: CHAR_MMM[-MMM]_YYYY_BATCH{n}."""
    pat = re.compile(r'_(\d{4})-(\d{2})-(\d{2})_')
    dates = []
    for clip in batch.clips:
        m = pat.search(clip.name)
        if m:
            try:
                dates.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except ValueError:
                pass
    if dates:
        lo, hi = min(dates), max(dates)
        lo_str = _MONTH[lo.month - 1]
        if lo.month == hi.month and lo.year == hi.year:
            date_part = f"{lo_str}_{hi.year}"
        else:
            date_part = f"{lo_str}-{_MONTH[hi.month - 1]}_{hi.year}"
    else:
        date_part = "UNKNOWN"
    slug = f"{char_name}_{date_part}_BATCH{batch.number}"
    return slug


# ── File operations ───────────────────────────────────────────────────────────

def _move_clips(batch, clips_dir: Path) -> None:
    """Move source clips into clips_dir (KO tier already embedded in filename from scan stage)."""
    clips_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for clip in batch.clips:
        dest = clips_dir / clip.path.name
        if dest.exists():
            logging.warning("Clip destination already exists, skipping: %s", dest.name)
            continue
        try:
            shutil.move(str(clip.path), str(dest))
            logging.debug("Moved clip -> %s", dest.name)
            moved += 1
        except OSError as e:
            logging.error("Failed to move %s -> %s: %s", clip.name, dest.name, e)
    logging.info("Moved %d clip(s) to %s", moved, clips_dir)


# ── Table drawing ─────────────────────────────────────────────────────────────

def _tbl_row(cells, widths, aligns) -> str:
    parts = [c.rjust(w) if a == "r" else c.ljust(w) for c, w, a in zip(cells, widths, aligns)]
    return "│ " + " │ ".join(parts) + " │"


def _tbl_line(widths, left, mid, right) -> str:
    return left + mid.join("─" * (w + 2) for w in widths) + right


def _print_table(rows, col_headers, col_aligns, highlight_row=None):
    """Print a Unicode box-drawing table. If highlight_row is set, only that row is printed."""
    col_widths = [
        max(len(col_headers[c]), max((len(r[c]) for r in rows), default=0))
        for c in range(len(col_headers))
    ]
    print(_tbl_line(col_widths, "┌", "┬", "┐"))
    print(_tbl_row(col_headers, col_widths, col_aligns))
    display_rows = rows if highlight_row is None else [rows[highlight_row]]
    for row in display_rows:
        print(_tbl_line(col_widths, "├", "┼", "┤"))
        print(_tbl_row(row, col_widths, col_aligns))
    print(_tbl_line(col_widths, "└", "┴", "┘"))


# ── Folder state scanners ─────────────────────────────────────────────────────

def _folder_age(folder: Path) -> str:
    """Human-readable age of a folder based on its modification time."""
    try:
        days = (time.time() - folder.stat().st_mtime) / 86400
        if days < 1:
            return "today"
        if days < 7:
            return f"{int(days)}d"
        if days < 30:
            return f"{int(days / 7)}w"
        return f"{int(days / 30)}mo"
    except OSError:
        return "?"


def _scan_output_folder(output_path: Path) -> list[dict]:
    """Scan Output directory. Returns a list of dicts, one per subfolder."""
    if not output_path.exists():
        return []
    rows = []
    for folder in sorted(output_path.iterdir()):
        if not folder.is_dir():
            continue
        mp4s = list(folder.glob("*.mp4"))
        descs = list(folder.glob("*_description.txt"))
        clips_dir = folder / "clips"
        rows.append({
            "name": folder.name,
            "has_video": bool(mp4s),
            "has_desc": bool(descs),
            "has_clips": clips_dir.is_dir(),
            "age": _folder_age(folder),
        })
    return rows


def _scan_archive_folder(archive_path: Path, ffprobe: Path | None = None) -> tuple[int, dict[str, tuple[int, float]]]:
    """
    Scan ClipArchive directory.

    Returns (total_clip_count, {char_name: (clip_count, total_duration_secs)}).
    Probes duration per character subfolder if ffprobe is provided.
    """
    if not archive_path.exists():
        return 0, {}
    char_data: dict[str, tuple[int, float]] = {}
    total = 0
    # Prefer per-character subfolders; fall back to flat files in root
    subdirs = [p for p in archive_path.iterdir() if p.is_dir()]
    if subdirs:
        for sub in sorted(subdirs):
            if ffprobe:
                count, dur = summarize_folder(sub, ffprobe)
            else:
                count = sum(1 for p in sub.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
                dur = 0.0
            if count:
                char_data[sub.name] = (count, dur)
                total += count
    # Also count any flat files in root (legacy)
    from clip_sorter import extract_character
    for p in archive_path.iterdir():
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            total += 1
            char = extract_character(p.stem) or "unknown"
            c, d = char_data.get(char, (0, 0.0))
            char_data[char] = (c + 1, d)
    return total, char_data


def _next_action(r: dict, yt_confirmed: bool) -> str:
    """Derive the next action for a compiled output folder based on its state."""
    if not yt_confirmed:
        return "Confirm on YouTube, then select Output > this folder"
    if r["has_clips"]:
        return "Select Output > this folder (archive Quad+, delete rest)"
    if r["has_video"]:
        return "Delete compiled video"
    return "Done"


def _print_multizone_status(config: Config) -> None:
    """Print Highlights, Output, and Archive status. Order reflects the clip pipeline."""

    # HIGHLIGHTS FOLDER
    print("\n-- HIGHLIGHTS FOLDER --")
    char_folders = sorted(e for e in config.clips_path.iterdir() if e.is_dir()) \
        if config.clips_path.exists() else []
    if char_folders:
        with ThreadPoolExecutor() as pool:
            summaries = list(pool.map(
                lambda f: summarize_folder(f, config.ffprobe, cache_dir=clip_cache.character_cache_dir(config.cache_dir, f.name)),
                char_folders,
            ))
        h_rows = []
        for folder, (count, dur) in zip(char_folders, summaries):
            cached = sum(
                1 for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS
                and _cache_exists(p, clip_cache.character_cache_dir(config.cache_dir, folder.name))
            )
            h_rows.append((
                folder.name,
                str(count) if count else "0",
                _fmt_duration(dur) if count else "-",
                _menu_status(dur, config.target_batch_seconds),
                f"{cached}/{count}" if count else "-",
                _date_range(folder),
            ))
        h_rows.sort(key=lambda r: (
            0 if r[3] == "✓ Ready" else (1 if r[3] == "~ Almost" else 2),
            -int(r[1]),
            r[0],
        ))
        _print_table(
            h_rows,
            col_headers=("Character", "Clips", "Duration", "Status", "KO cached", "Date range"),
            col_aligns=("l", "r", "r", "l", "r", "l"),
        )
    else:
        print("(no character folders found)")

    # OUTPUT FOLDER
    print("\n-- OUTPUT FOLDER --")
    output_rows = _scan_output_folder(config.output_path)
    if output_rows:
        state = load_state(config.state_path)
        o_rows = [
            (
                r["name"],
                r["age"],
                "OK" if r["has_video"] else "-",
                "OK" if r["has_desc"] else "-",
                "OK" if r["has_clips"] else "-",
                "Yes" if is_youtube_confirmed(state, r["name"]) else "No",
                _next_action(r, is_youtube_confirmed(state, r["name"])),
            )
            for r in output_rows
        ]
        _print_table(
            o_rows,
            col_headers=("Folder", "Age", "Video", "Desc", "Clips", "YT?", "Next Action"),
            col_aligns=("l", "r", "l", "l", "l", "l", "l"),
        )
    else:
        print("(no output folders found)")

    # ARCHIVE FOLDER
    print("\n-- ARCHIVE FOLDER --")
    total_archived, char_data = _scan_archive_folder(config.archive_path, ffprobe=config.ffprobe)
    if total_archived:
        a_rows = [
            (char, str(count), _fmt_duration(dur) if dur else "-",
             _menu_status(dur, config.target_batch_seconds))
            for char, (count, dur) in sorted(char_data.items())
        ]
        _print_table(a_rows, col_headers=("Character", "Clips", "Duration", "Status"),
                     col_aligns=("l", "r", "r", "l"))
    else:
        print("(empty)")

    print()


# ── Compile plan and apply ────────────────────────────────────────────────────

@dataclass
class PlanClip:
    name: str
    path: Path
    duration_s: float
    start_s: float        # offset inside its batch
    tier: str | None      # KO tier from the scan; None when no KO found, or the batch was not scanned
    low_value: bool       # stem ends _KO or _UNKNOWN


@dataclass
class PlanBatch:
    number: int
    duration_s: float
    clips: list[PlanClip]


@dataclass
class PlanDuplicate:
    a: str
    b: str
    score: float  # avg Hamming distance per frame (dedup.py); 0 means identical


@dataclass
class CompilePlan:
    character: str
    folder: Path
    target_s: float
    batches: list[PlanBatch]
    duplicates: list[PlanDuplicate]   # suspected pairs among batch 1 clips
    low_value: list[str]              # batch 1 clip names with a low-value tier
    _clips: dict[str, Clip] = field(default_factory=dict, repr=False)


@dataclass
class CompileResult:
    compiled: bool
    out_dir: Path | None = None
    slug: str = ""
    video_path: Path | None = None
    desc_path: Path | None = None
    title: str = ""
    description: str = ""
    duration_s: float = 0.0
    clip_count: int = 0
    uploaded: bool = False
    upload_speed: float | None = None   # MB/min
    upload_failed: bool = False         # the upload call itself raised; the terminal may retry
    needs_sign_in: bool = False         # auth or channel check failed; the token was kept
    error: str = ""


_CLIP_DECISIONS = ("keep", "archive", "recycle", "drop")


def _resolve_folder(config: Config, character: Path | str) -> Path:
    """character is the Highlights folder itself, or a folder name under clips_path."""
    if isinstance(character, Path):
        return character
    return config.clips_path / character


def _duplicate_pairs(config: Config, char_name: str, clips: list[Clip]) -> list[tuple[Clip, Clip, float]]:
    logging.info("")
    logging.info("--- Checking for duplicates ---")
    t_fp = time.perf_counter()
    pairs = find_duplicates(
        clips, str(config.ffmpeg),
        tmp_dir=config.cache_dir.parent / "dedup_tmp",
        cache_dir=clip_cache.character_cache_dir(config.cache_dir, char_name),
    )
    logging.info("Fingerprint took %.1fs total (%.1fs/clip)",
                 time.perf_counter() - t_fp, (time.perf_counter() - t_fp) / max(len(clips), 1))
    return pairs


def _clone(plan: CompilePlan, name: str) -> Clip:
    """A fresh Clip for apply, so a plan can be applied more than once."""
    src = plan._clips[name]
    return Clip(path=src.path, duration=src.duration)


def plan_compile(config: Config, character: Path | str, target_s: float) -> CompilePlan:
    """
    Plan a compile without renaming, moving, encoding or prompting.

    KO scanning and duplicate fingerprinting still run and fill their caches under
    config.cache_dir, as the old dry run did. Batch 1 gets KO tiers and duplicate
    pairs. Later batches list their clips with tier None.
    """
    folder = _resolve_folder(config, character)
    char_name = folder.name
    clips = scan_folder(folder, config.ffprobe, protect_recent=0,
                        cache_dir=clip_cache.character_cache_dir(config.cache_dir, char_name))
    plan = CompilePlan(character=char_name, folder=folder, target_s=target_s,
                       batches=[], duplicates=[], low_value=[])
    batches = make_batches(clips, target_s)
    if not batches:
        return plan

    first = batches[0]
    scan_results, _offsets = _scan_batch(first, config)
    tiers = {name: (res["tier"] if res else None) for name, (res, _e, _c) in scan_results.items()}
    low_names = {c.name for c in _find_ko_none_clips(first.clips)}

    for batch in batches:
        plan_clips: list[PlanClip] = []
        start = 0.0
        for clip in batch.clips:
            plan._clips[clip.name] = clip
            plan_clips.append(PlanClip(
                name=clip.name,
                path=clip.path,
                duration_s=clip.duration,
                start_s=start,
                tier=tiers.get(clip.name) if batch is first else None,
                low_value=clip.name in low_names if batch is first else False,
            ))
            start += clip.duration
        plan.batches.append(PlanBatch(number=batch.number, duration_s=batch.total_duration, clips=plan_clips))

    plan.low_value = [c.name for c in first.clips if c.name in low_names]
    plan.duplicates = [
        PlanDuplicate(a=a.name, b=b.name, score=score)
        for a, b, score in _duplicate_pairs(config, char_name, first.clips)
    ]
    return plan


def _upload_compiled(config: Config, result: CompileResult) -> None:
    """One non-interactive YouTube upload attempt. Fills the upload fields on result."""
    logging.info("")
    logging.info("--- YouTube Upload ---")
    try:
        youtube = uploader.get_authenticated_service(expected_channel_id=config.youtube_channel_id,
                                                     token_path=config.token_path)
        uploader.validate_channel_id(youtube, config.youtube_channel_id)
        result.title, result.description = uploader.parse_description_file(result.desc_path)
    except FileNotFoundError as e:
        logging.warning("YouTube credentials not set up: %s", e)
        logging.warning("ACTION: Download OAuth credentials from Google Cloud Console and save to config/client_secret_*.json")
        result.error = str(e)
        return
    except ValueError as e:
        # Auth or channel mismatch: keep the token, the user signs in again deliberately.
        logging.warning("YouTube channel validation failed: %s", e)
        logging.warning("Token kept. Sign in again with the correct account, or verify youtube_channel_id in config.json.")
        logging.warning("If the channel ID mismatch persists, verify youtube_channel_id in config.json.")
        result.needs_sign_in = True
        result.error = str(e)
        return
    except Exception as e:
        # Any other auth failure (e.g. a token refresh error) must not abort the compile.
        logging.warning("YouTube sign-in failed: %s", e)
        logging.warning("Token kept. Sign in again to upload this video.")
        result.needs_sign_in = True
        result.error = str(e)
        return
    try:
        result.upload_speed = _attempt_upload(youtube, result.video_path, result.title,
                                              result.description, result.slug, config.state_path,
                                              token_path=config.token_path)
        result.uploaded = True
        logging.info("Video uploaded successfully!")
    except Exception as e:
        logging.warning("YouTube upload failed: %s", e)
        result.upload_failed = True
        result.error = str(e)


def _attempt_upload(youtube, video_path: Path, title: str, description: str, slug: str, state_path: Path,
                    token_path=None) -> float:
    """Upload once. Returns the speed in MB/min. Raises on failure."""
    t0 = time.perf_counter()
    size_mb = video_path.stat().st_size / (1024 * 1024)
    uploader.upload_and_save_state(youtube, video_path, title, description, slug, state_path,
                                   token_path=token_path)
    duration = max(time.perf_counter() - t0, 1e-6)
    return size_mb / (duration / 60)


def apply_compile(
    config: Config,
    plan: CompilePlan,
    decisions: dict,
    force: bool = False,
    on_progress=None,
    upload: bool = True,
) -> CompileResult:
    """
    Carry out a compile plan. Never prompts. upload=False skips the YouTube upload.

    decisions:
      "clips": {clip name: "keep" | "archive" | "recycle" | "drop"}, default "keep".
          archive and recycle apply to low-value clips: ClipArchive or Recycle Bin.
          drop leaves the clip in Highlights and out of this video (one side of a duplicate).
      "extra": how many leftover clips from plan.batches[1:] to append, in plan order.

    Renames the kept clips to embed their KO tier, encodes, writes the description,
    makes one upload attempt, then moves the clips into the output folder.
    """
    if not plan.batches:
        return CompileResult(compiled=False)

    choices = decisions.get("clips", {})
    for name, choice in choices.items():
        if choice not in _CLIP_DECISIONS:
            raise ValueError(f"unknown decision {choice!r} for {name}")

    char_name = plan.character
    first = plan.batches[0]
    kept: list[Clip] = []
    archive: list[Clip] = []
    recycle: list[Clip] = []
    for pc in first.clips:
        choice = choices.get(pc.name, "keep")
        if choice == "archive":
            archive.append(_clone(plan, pc.name))
        elif choice == "recycle":
            recycle.append(_clone(plan, pc.name))
        elif choice == "keep":
            kept.append(_clone(plan, pc.name))

    if archive:
        _archive_clips(archive, char_name, config)
    for clip in recycle:
        send2trash(str(clip.path))
        logging.info("Sent to Recycle Bin: %s", clip.name)

    leftover = [pc for b in plan.batches[1:] for pc in b.clips]
    for pc in leftover[:int(decisions.get("extra", 0))]:
        kept.append(_clone(plan, pc.name))

    if not kept:
        logging.info("No clips remaining after reviewing low-value clips. Nothing to compile.")
        return CompileResult(compiled=False)

    batch = Batch(number=first.number, clips=kept)
    slug = _batch_slug(char_name, batch)
    out_dir = config.output_path / slug

    logging.info("")
    logging.info("--- Scanning for KO events ---")
    t_ko = time.perf_counter()
    highlights, clip_tiers = _collect_highlights(batch, config)
    logging.info("KO scan took %.1fs total (%.1fs/clip)",
                 time.perf_counter() - t_ko, (time.perf_counter() - t_ko) / max(len(batch.clips), 1))

    logging.info("")
    logging.info("--- Encoding ---")
    t_enc = time.perf_counter()
    encode(batch, char_name, out_dir, config.ffmpeg, out_stem=slug, force=force, on_progress=on_progress)
    logging.info("Mux took %.1fs", time.perf_counter() - t_enc)

    logging.info("")
    logging.info("--- Metadata ---")
    ko_tier_counts: dict[str, int] = {}
    for tier in clip_tiers.values():
        ko_tier_counts[tier] = ko_tier_counts.get(tier, 0) + 1
    desc_path = write_description(
        batch, char_name, highlights, out_dir, out_stem=slug,
        title=slug,
        clip_tiers=clip_tiers,
        date_range=_date_range(plan.folder),
        ko_tiers=ko_tier_counts,
        clip_count=len(batch.clips),
    )

    result = CompileResult(
        compiled=True,
        out_dir=out_dir,
        slug=slug,
        video_path=out_dir / f"{slug}.mp4",
        desc_path=desc_path,
        duration_s=batch.total_duration,
        clip_count=len(batch.clips),
    )
    if upload:
        _upload_compiled(config, result)
    else:
        logging.info("Upload skipped.")

    logging.info("")
    logging.info("--- Cleanup ---")
    _move_clips(batch, out_dir / "clips")
    _write_manifest(out_dir, slug, char_name, batch, clip_tiers)
    return result


# ── Terminal prompts ──────────────────────────────────────────────────────────

def _review_low_value(config: Config, low_tier: list[PlanClip]) -> dict[str, str]:
    """Ask about each low-value clip. Returns {name: 'keep' | 'archive' | 'recycle'}."""
    choices: dict[str, str] = {}
    for pc in low_tier:
        logging.info("")
        logging.info("  📹 %s", pc.name)
        logging.info("  Path: %s", pc.path)
        vlc_hint = "  [v] view in VLC" if config.vlc_path else ""
        while True:
            raw = input(f"  [y] include  [a] archive to ClipArchive  [d] delete{vlc_hint}: ").strip().lower()
            if raw == "v" and config.vlc_path:
                subprocess.Popen([str(config.vlc_path), str(pc.path)],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                continue
            break
        if raw in ("y", "yes"):
            choices[pc.name] = "keep"
            logging.info("  -> Included in compilation.")
        elif raw in ("a", "archive"):
            choices[pc.name] = "archive"
            logging.info("  -> Will be archived to ClipArchive.")
        else:
            choices[pc.name] = "recycle"
            logging.info("  -> Will be deleted.")
    logging.info("")
    return choices


def _review_length(kept: list[PlanClip], leftover: list[PlanClip]) -> int:
    """Ask whether the length is right. Each 'n' moves one leftover clip into kept. Returns how many."""
    added = 0
    while True:
        logging.info("")
        logging.info("Video:    %d clip(s), %s", len(kept), _mmss(sum(c.duration_s for c in kept)))
        if leftover:
            leftover_dur = sum(c.duration_s for c in leftover)
            logging.info("Leftover: %d clip(s), %s", len(leftover), _fmt_duration(leftover_dur))
        logging.info("")
        raw = input("Happy with this video length? [Y/n]: ").strip().lower()
        if raw not in ("n", "no"):
            break
        if not leftover:
            logging.info("No more clips to add.")
            break
        clip = leftover.pop(0)
        kept.append(clip)
        added += 1
        logging.info("  Added: %s", clip.name)
    return added


def _review_duplicates(config: Config, plan: CompilePlan, names: list[str], recompute: bool) -> bool:
    """Show suspected duplicates among the kept clips. Returns False if the user cancels.

    recompute is True when clips were added after planning, so the plan's pairs do not cover them.
    """
    if recompute:
        pairs = _duplicate_pairs(config, plan.character, [_clone(plan, n) for n in names])
    else:
        keep = set(names)
        pairs = [
            (plan._clips[d.a], plan._clips[d.b], d.score)
            for d in plan.duplicates if d.a in keep and d.b in keep
        ]
    if pairs:
        print_dup_table(pairs)
        raw = input("Suspected duplicates found. Continue anyway? [y/N]: ").strip().lower()
        if raw not in ("y", "yes"):
            logging.info("Cancelled -- remove duplicates and re-run.")
            return False
    else:
        logging.info("No duplicates found.")
    return True


def _prompt_upload_retry(config: Config, result: CompileResult) -> None:
    """After a failed upload, offer to delete the token and try again. Updates result in place."""
    while True:
        logging.warning("")
        confirm = input("Delete token.json and re-authenticate? [y/N]: ").strip().lower()
        if confirm not in ('y', 'yes'):
            logging.warning("Upload cancelled by user. Falling back to manual upload.")
            return
        # User agreed: delete token to force re-auth on next attempt
        token_path = uploader.resolve_token_path(config.token_path)
        if token_path.exists():
            token_path.unlink()
            logging.info("Token deleted. Re-authenticating...")
        try:
            youtube = uploader.get_authenticated_service(expected_channel_id=config.youtube_channel_id,
                                                         token_path=config.token_path)
            uploader.validate_channel_id(youtube, config.youtube_channel_id)
        except Exception as auth_err:
            logging.warning("Re-authentication failed: %s", auth_err)
            return
        try:
            result.upload_speed = _attempt_upload(youtube, result.video_path, result.title,
                                                  result.description, result.slug, config.state_path,
                                                  token_path=config.token_path)
        except Exception as e:
            logging.warning("YouTube upload failed: %s", e)
            continue
        result.uploaded = True
        result.upload_failed = False
        logging.info("Video uploaded successfully!")
        return


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(config: Config, force_encode: bool = False, dry_run: bool = False) -> None:
    t0 = time.perf_counter()

    if dry_run:
        print("\n*** DRY RUN - no files will be moved or encoded ***\n")

    config.output_path.mkdir(parents=True, exist_ok=True)

    if not config.clips_path.exists():
        raise FileNotFoundError(f"Clips path not found: {config.clips_path}")

    # --- Step 1: sort any unsorted clips into character subfolders ---
    if dry_run:
        print("[DRY RUN] Skipping clip sort")
    else:
        sort_clips(config.clips_path, protect_recent=config.protect_recent_clips)

    # --- Step 2: show full folder status (Highlights + Output + Archive) ---
    _print_multizone_status(config)

    # --- Step 3: discover character subfolders ---
    char_folders = sorted(e for e in config.clips_path.iterdir() if e.is_dir())
    if not char_folders:
        char_folders = [config.clips_path]

    # --- Step 4: scan Highlights folders for the menu ---
    with ThreadPoolExecutor() as pool:
        summaries = list(pool.map(
            lambda f: summarize_folder(f, config.ffprobe, cache_dir=clip_cache.character_cache_dir(config.cache_dir, f.name)),
            char_folders,
        ))
    for folder, (count, dur) in zip(char_folders, summaries):
        logging.debug("  %s: %d clips, %s", folder.name, count, _fmt_duration(dur))

    # Sort by readiness first (ready > almost > too short), then clip count desc, then name
    _pairs = sorted(
        zip(char_folders, summaries),
        key=lambda x: (
            0 if x[1][1] >= config.target_batch_seconds else (
                1 if x[1][1] >= config.target_batch_seconds * 0.75 else 2
            ),
            -x[1][0],
            x[0].name,
        ),
    )
    if _pairs:
        char_folders, summaries = map(list, zip(*_pairs))

    # --- Step 5: two-level arrow-key menu ---
    output_rows = _scan_output_folder(config.output_path)
    state = load_state(config.state_path)

    while True:
        action = pick_action(
            char_folders, summaries, output_rows, state,
            target_batch_seconds=config.target_batch_seconds,
            output_path=config.output_path,
            archive_path=config.archive_path,
        )

        if action["type"] == "quit":
            logging.info("Cancelled.")
            return

        if action["type"] == "preprocess":
            logging.info("Pre-processing all clips...")
            preprocess_all(config, dry_run=dry_run)
            # Refresh summaries and loop back to menu
            with ThreadPoolExecutor() as pool:
                summaries = list(pool.map(
                    lambda f: summarize_folder(f, config.ffprobe, cache_dir=clip_cache.character_cache_dir(config.cache_dir, f.name)),
                    char_folders,
                ))
            continue

        if action["type"] == "compile":
            char_path = action["folder"]
            break

        if action["type"] == "cleanup":
            from cleanup import run_cleanup
            run_cleanup(action["folder"], config.archive_path,
                        state_path=config.state_path, dry_run=False)
            return

        if action["type"] == "uncompile":
            from cleanup import run_uncompile
            run_uncompile(action["folder"], config.clips_path,
                          state_path=config.state_path)
            return

        if action["type"] == "retry_youtube":
            _retry_youtube_upload(action["folder"], config)
            return

    # --- Step 6: plan the selected character, then ask the questions ---
    char_name = char_path.name
    logging.info("=" * 50)
    logging.info("Character: %s", char_name)
    logging.info("=" * 50)
    logging.info("")

    plan = plan_compile(config, char_path, config.target_batch_seconds)
    if not plan.batches:
        logging.info("No clips found - nothing to process.")
        return

    first = plan.batches[0]

    # Compile-time low-value guard: ask about each KO/UNKNOWN clip before encoding
    choices: dict[str, str] = {}
    low_tier = [pc for pc in first.clips if pc.low_value]
    if low_tier:
        logging.info("⚠️  %d low-value clip(s) detected - review each:", len(low_tier))
        if dry_run:
            for pc in low_tier:
                logging.info("  [DRY RUN] Would review: %s", pc.name)
        else:
            choices = _review_low_value(config, low_tier)
            remaining = [pc for pc in first.clips if choices.get(pc.name, "keep") == "keep"]
            if not remaining:
                apply_compile(config, plan, {"clips": choices})
                return
            logging.info("Batch now has %d clip(s).", len(remaining))
    kept = [pc for pc in first.clips if choices.get(pc.name, "keep") == "keep"]

    # Batch length adjustment loop - user can keep adding leftover clips one at a time
    leftover = [pc for b in plan.batches[1:] for pc in b.clips]
    extra = _review_length(kept, leftover)

    raw = input("Make this video? [y/N]: ").strip().lower()
    if raw not in ("y", "yes"):
        logging.info("Cancelled.")
        return

    # Always compile one batch at a time. Re-run the program for subsequent batches.
    # (Remaining clips stay in Highlights until next run.)
    names = [pc.name for pc in kept]
    if not _review_duplicates(config, plan, names, recompute=extra > 0):
        return

    if dry_run:
        batch = Batch(number=first.number, clips=[_clone(plan, n) for n in names])
        slug = _batch_slug(char_name, batch)
        out_dir = config.output_path / slug
        logging.info("")
        logging.info("--- Encoding ---")
        logging.info("[DRY RUN] Would encode %d clips (%s) -> %s.mp4",
                     len(batch.clips), batch.duration_str, out_dir / slug)
        logging.info("")
        logging.info("--- Metadata ---")
        logging.info("[DRY RUN] Would write %s_description.txt", out_dir / slug)
        logging.info("")
        logging.info("--- Cleanup ---")
        logging.info("[DRY RUN] Would move %d clips -> %s/clips/", len(batch.clips), out_dir)
        yt_uploaded = False
        yt_upload_speed = None
        last_out_dir = out_dir
    else:
        result = apply_compile(config, plan, {"clips": choices, "extra": extra}, force=force_encode)
        if not result.compiled:
            return
        if result.upload_failed:
            _prompt_upload_retry(config, result)
        yt_uploaded = result.uploaded
        yt_upload_speed = result.upload_speed
        last_out_dir = result.out_dir

    elapsed = time.perf_counter() - t0
    elapsed_mins = int(elapsed) // 60
    elapsed_secs = int(elapsed) % 60
    elapsed_fmt = f"{elapsed_mins}m {elapsed_secs:02d}s" if elapsed_mins else f"{elapsed_secs}s"
    logging.info("")
    logging.info("=" * 50)
    logging.info("Video processed in %s", elapsed_fmt)
    if yt_uploaded and yt_upload_speed:
        logging.info("Upload speed: %.0f MB/min", yt_upload_speed)
    logging.info("=" * 50)
    print("\a", end="", flush=True)

    # Next steps - shown in both real runs and dry runs
    if not dry_run and last_out_dir.exists():
        import os as _os
        _os.startfile(str(last_out_dir))

    logging.info("")
    if yt_uploaded:
        logging.info("✓ Video uploaded to YouTube (private)")
        logging.info("Check YouTube Studio to review and publish")
    logging.info("")
