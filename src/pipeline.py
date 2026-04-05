"""
pipeline.py - Main orchestrator: sort → scan → batch → detect → encode → describe.
"""

import logging
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import ko_detect
from batcher import make_batches
from dedup import find_duplicates, print_dup_table
from clip_scanner import VIDEO_EXTS, scan_folder, summarize_folder
from clip_sorter import sort_clips
from config import Config
from description_writer import fmt_ts, write_description
from encoder import encode
from progress import AnimatedTicker
from menu import pick_action
from preprocess import preprocess_all
from state import is_youtube_confirmed, load as load_state


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


def _collect_highlights(
    batch, config: Config
) -> tuple[list[tuple[float, float, str, str]], dict[str, str]]:
    """
    Scan each clip for KO events in parallel.

    Returns:
      highlights  - Quad+ kills with compilation timestamps, for the description.
      clip_tiers  - {clip.name: tier} for every clip where any kill was detected.
    """
    ko_detect.configure(
        ffmpeg=str(config.ffmpeg),
        tesseract=str(config.tesseract),
        cache_dir=str(config.cache_dir / batch.clips[0].path.parent.name),
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

    # Rename clips in-place now that tiers are known (e.g. THOR_..._QUAD.mp4).
    # This embeds the tier in the filename before description/archiving use it.
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
            logging.info("Renamed: %s -> %s", old_path.name, new_path.name)
        except OSError as e:
            logging.warning("Could not rename %s: %s", old_path.name, e)

    # Build ordered highlights + clip_tiers using original clip order
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


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


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


def _estimate_seconds(clips: list, cache_dir: Path) -> float:
    """Rough pipeline estimate: KO scan (model-based for uncached, ~0.5s cached) + encode (~0.4x duration).

    KO scan model (68 clips, R2=0.90): scan_time = 0.977 * clip_duration - 4.118
    clips: list[Clip] for the batch being compiled (not all clips for the character).
    """
    if not clips:
        return 0.0
    total_dur = sum(c.duration for c in clips)
    avg_dur = total_dur / len(clips)
    char_cache = cache_dir / clips[0].path.parent.name

    ko_est = 0.0
    for c in clips:
        if _cache_exists(c.path, char_cache):
            ko_est += 0.5
        else:
            ko_est += max(1.0, 0.977 * avg_dur - 4.118)
    encode_est = total_dur * 0.4
    return ko_est + encode_est


def _cache_exists(clip: Path, char_cache: Path) -> bool:
    """Check whether a .ko.json cache entry exists for a clip.

    Mirrors ko_detect.cache_path(): clips with a parseable date use a
    YYYY-MM month subfolder; others fall back to the char_cache root.
    """
    m = re.search(r"(\d{4}-\d{2})-\d{2}", clip.stem)
    if m:
        return (char_cache / m.group(1) / (clip.stem + ".ko.json")).exists()
    return (char_cache / (clip.stem + ".ko.json")).exists()


def _fmt_estimate(seconds: float) -> str:
    s = int(seconds)
    m, sec = divmod(s, 60)
    return f"~{m}m {sec:02d}s" if m else f"~{sec}s"


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
    logging.debug("Manifest written: %s (%d clips)", manifest_path.name, len(batch.clips))


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
                lambda f: summarize_folder(f, config.ffprobe), char_folders
            ))
        h_rows = []
        for folder, (count, dur) in zip(char_folders, summaries):
            cached = sum(
                1 for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS
                and _cache_exists(p, config.cache_dir / folder.name)
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
            lambda f: summarize_folder(f, config.ffprobe), char_folders
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
            preprocess_all(config)
            # Refresh summaries and loop back to menu
            with ThreadPoolExecutor() as pool:
                summaries = list(pool.map(
                    lambda f: summarize_folder(f, config.ffprobe), char_folders
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

    # --- Step 6: process selected character ---
    char_name = char_path.name
    logging.info("=" * 50)
    logging.info("Character: %s", char_name)
    logging.info("=" * 50)
    logging.info("")

    # Scan and batch before showing the estimate so it reflects batch 1 only
    clips = scan_folder(char_path, config.ffprobe, protect_recent=0)
    if not clips:
        logging.info("No clips found - nothing to process.")
        return

    batches = make_batches(clips, config.target_batch_seconds)

    # Compile-time low-value guard: warn before encoding if KO/UNKNOWN clips slipped through
    low_tier = _find_ko_none_clips(batches[0].clips)
    if low_tier:
        logging.info("⚠️  %d low-value clip(s) detected - review each:", len(low_tier))
        to_remove = []
        to_archive = []
        to_delete = []
        for clip in low_tier:
            logging.info("")
            logging.info("  📹 %s", clip.name)
            logging.info("  Path: %s", clip.path)
            raw = input("  [y] include  [a] archive to ClipArchive  [d] delete: ").strip().lower()
            if raw in ("y", "yes"):
                logging.info("  -> Included in compilation.")
            elif raw in ("a", "archive"):
                to_archive.append(clip)
                to_remove.append(clip)
                logging.info("  -> Will be archived to ClipArchive.")
            else:
                to_delete.append(clip)
                to_remove.append(clip)
                logging.info("  -> Will be deleted.")
        logging.info("")
        if to_archive:
            _archive_clips(to_archive, char_name, config)
        if to_delete:
            for clip in to_delete:
                clip.path.unlink(missing_ok=True)
                logging.info("Deleted: %s", clip.name)
        if to_remove:
            keep = [c for c in batches[0].clips if c not in to_remove]
            batches[0].clips = keep
            if not batches[0].clips:
                logging.info("No clips remaining after reviewing low-value clips. Nothing to compile.")
                return
        logging.info("Batch now has %d clip(s).", len(batches[0].clips))

    # Batch length adjustment loop - user can keep adding leftover clips one at a time
    leftover = [c for b in batches[1:] for c in b.clips]
    while True:
        logging.info("")
        logging.info("Video:    %d clip(s), %s", len(batches[0].clips), batches[0].duration_str)
        if leftover:
            leftover_dur = sum(c.duration for c in leftover)
            logging.info("Leftover: %d clip(s), %s", len(leftover), _fmt_duration(leftover_dur))
        logging.info("")
        raw = input("Happy with this video length? [Y/n]: ").strip().lower()
        if raw not in ("n", "no"):
            break
        if not leftover:
            logging.info("No more clips to add.")
            break
        clip = leftover.pop(0)
        batches[0].clips.append(clip)
        logging.info("  Added: %s", clip.name)

    est_str = _fmt_estimate(_estimate_seconds(batches[0].clips, config.cache_dir))
    raw = input(f"Make this video? Estimated processing time: {est_str}. [y/N]: ").strip().lower()
    if raw not in ("y", "yes"):
        logging.info("Cancelled.")
        return

    # Always compile one batch at a time. Re-run the program for subsequent batches.
    # (Remaining clips stay in Highlights until next run.)
    batches_to_run = [batches[0]]

    total_batches = 0

    for batch in batches_to_run:
        logging.info("")
        logging.info("--- %s  (%s) ---", char_name, batch.duration_str)

        # --- Duplicate detection ---
        logging.info("")
        logging.info("--- Checking for duplicates ---")
        dup_pairs = find_duplicates(batch.clips, str(config.ffmpeg), tmp_dir=config.cache_dir.parent / "dedup_tmp")
        if dup_pairs:
            print_dup_table(dup_pairs)
            raw = input("Suspected duplicates found. Continue anyway? [y/N]: ").strip().lower()
            if raw not in ("y", "yes"):
                logging.info("Cancelled -- remove duplicates and re-run.")
                return
        else:
            logging.info("No duplicates found.")

        logging.info("")
        logging.info("--- Scanning for KO events ---")
        t_ko = time.perf_counter()
        highlights, clip_tiers = _collect_highlights(batch, config)
        logging.debug("KO scan took %.1fs", time.perf_counter() - t_ko)

        slug = _batch_slug(char_name, batch)
        out_dir = config.output_path / slug

        logging.info("")
        logging.info("--- Encoding ---")
        if dry_run:
            logging.info("[DRY RUN] Would encode %d clips (%s) -> %s.mp4",
                         len(batch.clips), batch.duration_str, out_dir / slug)
        else:
            t_enc = time.perf_counter()
            encode(batch, char_name, out_dir, config.ffmpeg, out_stem=slug, force=force_encode)
            logging.debug("Encode took %.1fs", time.perf_counter() - t_enc)

        logging.info("")
        logging.info("--- Metadata ---")
        ko_tier_counts: dict[str, int] = {}
        for tier in clip_tiers.values():
            ko_tier_counts[tier] = ko_tier_counts.get(tier, 0) + 1
        if dry_run:
            logging.info("[DRY RUN] Would write %s_description.txt", out_dir / slug)
        else:
            desc_path = write_description(
                batch, char_name, highlights, out_dir, out_stem=slug,
                clip_tiers=clip_tiers,
                date_range=_date_range(char_path),
                ko_tiers=ko_tier_counts,
                clip_count=len(batch.clips),
            )

        logging.info("")
        logging.info("--- Cleanup ---")
        if dry_run:
            logging.info("[DRY RUN] Would move %d clips -> %s/clips/", len(batch.clips), out_dir)
        else:
            _move_clips(batch, out_dir / "clips")
            _write_manifest(out_dir, slug, char_name, batch, clip_tiers)

        total_batches += 1

    elapsed = time.perf_counter() - t0
    elapsed_mins = int(elapsed) // 60
    elapsed_secs = int(elapsed) % 60
    elapsed_fmt = f"{elapsed_mins}m {elapsed_secs:02d}s" if elapsed_mins else f"{elapsed_secs}s"
    logging.info("")
    logging.info("=" * 50)
    logging.info("Video processed in %s (estimated: %s)", elapsed_fmt, est_str)
    logging.info("=" * 50)
    print("\a", end="", flush=True)

    # Next steps - shown in both real runs and dry runs
    last_batch = batches_to_run[-1]
    last_slug = _batch_slug(char_name, last_batch)
    last_out_dir = config.output_path / last_slug

    if not dry_run and last_out_dir.exists():
        import os as _os
        _os.startfile(str(last_out_dir))

    logging.info("")
    logging.info(">>> NEXT STEPS <<<")
    logging.info("")
    logging.info("1. Open folder:")
    logging.info("   %s", last_out_dir)
    logging.info("")
    logging.info("2. Upload video to YouTube using temporary title:")
    logging.info("   %s.mp4", last_slug)
    logging.info("")
    logging.info("3. Paste in description from text file there.")
    logging.info("")
