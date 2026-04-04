"""
pipeline.py — Main orchestrator: sort → scan → batch → detect → encode → describe.
"""

import logging
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import ko_detect
from ai_prompt import write_ai_prompts
from batcher import make_batches
from dedup import find_duplicates, print_dup_table
from clip_scanner import VIDEO_EXTS, scan_folder, summarize_folder
from clip_sorter import sort_clips
from config import Config
from description_writer import fmt_ts, write_description
from encoder import encode
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
      highlights  — Quad+ kills with compilation timestamps, for the description.
      clip_tiers  — {clip.name: tier} for every clip where any kill was detected.
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

    # Scan all clips in parallel — FFmpeg + Tesseract are external processes,
    # so threads give real concurrency. Each clip writes to its own cache file.
    scan_results: dict[str, tuple[dict | None, float, bool]] = {}
    done = 0

    with ThreadPoolExecutor(max_workers=ko_detect.N_WORKERS) as pool:
        future_to_clip = {
            pool.submit(_ko_scan_one, str(clip.path), clip.name): clip
            for clip in batch.clips
        }
        for future in as_completed(future_to_clip):
            done += 1
            clip = future_to_clip[future]
            clip_name, result, elapsed, was_cached = future.result()
            scan_results[clip_name] = (result, elapsed, was_cached)

            elapsed_str = (
                f"{int(elapsed) // 60}m{int(elapsed) % 60:02d}s"
                if elapsed >= 60
                else f"{elapsed:.1f}s"
            )
            tier_found = result["tier"] if result else None
            cache_tag = "[cached] " if was_cached else ""
            suffix = f" — {tier_found}" if tier_found else ""
            print(f"KO scan [{done}/{total}]: {cache_tag}{clip_name} -> Done ({elapsed_str}){suffix}")
            logging.debug(
                "KO scan: %s — %.1fs%s", clip_name, elapsed,
                f" {tier_found}" if tier_found else "",
            )
            if tier_found and ko_detect.TIER_RANK.get(tier_found, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
                video_start = offsets[clip_name] + result["start_ts"]
                video_max = offsets[clip_name] + result["max_ts"]
                logging.debug("%s @ %s–%s", tier_found, fmt_ts(video_start), fmt_ts(video_max))

    # Rename clips in-place now that tiers are known (e.g. THOR_..._QUAD.mp4).
    # This embeds the tier in the filename before description/archiving use it.
    _tier_set = set(ko_detect.TIERS)
    for clip in batch.clips:
        result, _e, _c = scan_results.get(clip.name, (None, 0.0, False))
        if not result:
            continue
        tier = result["tier"]
        stem = clip.path.stem
        if any(stem.endswith(f"_{t}") for t in _tier_set):
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
        return "—"
    lo, hi = min(dates), max(dates)

    def _d(d: datetime) -> str:
        return f"{d.day} {_MONTH[d.month - 1]} '{d.year % 100:02d}"

    return _d(lo) if lo.date() == hi.date() else f"{_d(lo)} → {_d(hi)}"


def _menu_status(dur: float, target: int) -> str:
    if dur >= target:        return "✓ Ready"
    if dur >= target * 0.75: return "~ Almost"   # 11m15s+ at default 15m target
    if dur > 0:              return "✗ Too short"
    return "— No clips"


def _estimate_seconds(folder: Path, cache_dir: Path, total_dur: float) -> float:
    """Rough pipeline estimate: KO scan (model-based for uncached, ~0.5s cached) + encode (~0.4x duration).

    KO scan model (68 clips, R2=0.90): scan_time = 0.977 * clip_duration - 4.118
    Uses average clip duration as proxy to avoid extra ffprobe calls here.
    """
    char_cache = cache_dir / folder.name
    clips = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    n_clips = len(clips)
    avg_dur = total_dur / n_clips if n_clips else 0.0

    ko_est = 0.0
    for p in clips:
        if _cache_exists(p, char_cache):
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


def _batch_slug(char_name: str, batch, total_batches: int) -> str:
    """Build the output folder/file stem: CHAR_MMM[-MMM]_YYYY[_BATCH{n}]."""
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
    slug = f"{char_name}_{date_part}"
    if total_batches > 1:
        slug += f"_BATCH{batch.number}"
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
    logging.info("Clips -> %s  (%d moved)", clips_dir, moved)


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

    # Estimate for selected character
    try:
        char_idx = char_folders.index(char_path)
        _, char_dur = summaries[char_idx]
        est_str = _fmt_estimate(_estimate_seconds(char_path, config.cache_dir, char_dur))
    except (ValueError, IndexError):
        est_str = "unknown"

    raw = input(f"Make this video? Estimated processing time: {est_str}. [y/N]: ").strip().lower()
    if raw not in ("y", "yes"):
        logging.info("Cancelled.")
        return

    logging.info("Selected: %s", char_path.name)

    # --- Step 6: process selected character ---
    char_name = char_path.name
    logging.info("")
    logging.info("=" * 50)
    logging.info("Character: %s", char_name)
    logging.info("=" * 50)

    clips = scan_folder(char_path, config.ffprobe, protect_recent=config.protect_recent_clips)
    if not clips:
        logging.info("No clips found - nothing to process.")
        return

    batches = make_batches(clips, config.target_batch_seconds)
    logging.info("Batching: %d batch(es)", len(batches))
    for b in batches:
        logging.info("Batch %d: %d clip(s), %s", b.number, len(b.clips), b.duration_str)

    # Always compile one batch at a time. Re-run the program for subsequent batches.
    # (Remaining clips stay in Highlights until next run.)
    batches_to_run = [batches[0]]
    if len(batches) > 1:
        logging.info("Note: %d batch(es) worth of clips available. Compiling batch 1 now - re-run for the rest.", len(batches))

    total_batches = 0

    for batch in batches_to_run:
        logging.info("")
        logging.info("--- %s  Batch %d/%d  (%s) ---",
                     char_name, batch.number, len(batches), batch.duration_str)

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
        if not highlights:
            logging.info("(no Quad+ kills detected)")
        else:
            logging.info("%d Quad+ kill(s) found.", len(highlights))

        slug = _batch_slug(char_name, batch, len(batches))
        out_dir = config.output_path / slug

        logging.info("")
        logging.info("--- Encoding ---")
        if dry_run:
            print(f"[DRY RUN] Would encode {len(batch.clips)} clips ({batch.duration_str}) -> {out_dir / slug}.mp4")
            print(f"[DRY RUN] Would write description -> {out_dir / slug}_description.txt")
            print(f"[DRY RUN] Would write AI prompts  -> {out_dir / slug}_ai_prompts.txt")
            print(f"[DRY RUN] Would move {len(batch.clips)} clips -> {out_dir / 'clips'}/")
        else:
            t_enc = time.perf_counter()
            encode(batch, char_name, out_dir, config.ffmpeg, out_stem=slug, force=force_encode)
            logging.debug("Encode took %.1fs", time.perf_counter() - t_enc)
            desc_path = write_description(batch, char_name, highlights, out_dir, out_stem=slug,
                                          clip_tiers=clip_tiers)

            # Tally detected KO tiers for the AI prompts context block
            ko_tier_counts: dict[str, int] = {}
            for tier in clip_tiers.values():
                ko_tier_counts[tier] = ko_tier_counts.get(tier, 0) + 1
            prompts_path = write_ai_prompts(
                out_dir=out_dir,
                char_name=char_name,
                clip_count=len(batch.clips),
                date_range=_date_range(char_path),
                ko_tiers=ko_tier_counts,
                description_path=desc_path,
                out_stem=slug,
            )
            print(f"AI prompts \u2192 {prompts_path}")

            _move_clips(batch, out_dir / "clips")

        total_batches += 1

    elapsed = time.perf_counter() - t0
    logging.info("")
    logging.info("=" * 50)
    logging.info("Done.  %d batch(es) encoded in %.1fs", total_batches, elapsed)
    logging.info("=" * 50)

    print("\a", end="", flush=True)

    if not dry_run:
        # Print next-steps for the last batch processed
        last_batch = batches_to_run[-1]
        last_slug = _batch_slug(char_name, last_batch, len(batches))
        last_out_dir = config.output_path / last_slug
        video_path = last_out_dir / f"{last_slug}.mp4"
        prompts_path = last_out_dir / f"{last_slug}_ai_prompts.txt"

        logging.info("")
        logging.info(">>> NEXT STEPS <<<")
        logging.info("")
        logging.info("  1. Review video:   %s", video_path)
        logging.info("  2. Upload to YouTube (drag & drop the .mp4 above)")
        logging.info("  3. Check timestamps in the video description:")
        logging.info("        %s", last_out_dir / f"{last_slug}_description.txt")
        logging.info("  4. Get title and description from AI prompts:")
        logging.info("        %s", prompts_path)
        logging.info("")
    else:
        logging.info("")
        logging.info("  Output would be: %s", config.output_path)
