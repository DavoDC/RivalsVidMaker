"""
pipeline.py — Main orchestrator: sort → scan → batch → detect → encode → describe.
"""

import logging
import math
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import ko_detect
from ai_prompt import write_ai_prompts
from batcher import make_batches
from clip_scanner import VIDEO_EXTS, scan_folder, summarize_folder
from clip_sorter import sort_clips
from config import Config
from description_writer import fmt_ts, write_description
from encoder import encode
from preprocess import preprocess_all


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
                logging.info("%s @ %s–%s", tier_found, fmt_ts(video_start), fmt_ts(video_max))

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
    """Rough pipeline estimate: KO scan (~6s uncached, ~0.5s cached) + encode (~0.4× duration)."""
    char_cache = cache_dir / folder.name
    ko_est = 0.0
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            cached = (char_cache / (p.stem + ".ko.json")).exists()
            ko_est += 0.5 if cached else 6.0
    encode_est = total_dur * 0.4
    return ko_est + encode_est


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

def _move_clips(batch, clip_tiers: dict[str, str], clips_dir: Path) -> None:
    """Move source clips into clips_dir, appending _TIER suffix where detected."""
    clips_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for clip in batch.clips:
        tier = clip_tiers.get(clip.name)
        stem = clip.path.stem + (f"_{tier}" if tier else "")
        dest = clips_dir / (stem + clip.path.suffix)
        if dest.exists():
            logging.warning("Clip destination already exists, skipping: %s", dest.name)
            continue
        try:
            shutil.move(str(clip.path), str(dest))
            logging.debug("Moved clip → %s", dest.name)
            moved += 1
        except OSError as e:
            logging.error("Failed to move %s → %s: %s", clip.name, dest.name, e)
    logging.info("Clips → %s  (%d moved)", clips_dir, moved)


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
        })
    return rows


def _scan_archive_folder(archive_path: Path) -> tuple[int, dict[str, int]]:
    """
    Scan ClipArchive directory.

    Returns (total_clip_count, {char_name: clip_count}).
    Clips are attributed to a character by parsing the filename convention.
    """
    if not archive_path.exists():
        return 0, {}
    from clip_sorter import extract_character
    char_counts: dict[str, int] = {}
    total = 0
    for p in archive_path.iterdir():
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            total += 1
            char = extract_character(p.stem)
            if char:
                char_counts[char] = char_counts.get(char, 0) + 1
            else:
                char_counts["unknown"] = char_counts.get("unknown", 0) + 1
    return total, char_counts


def _print_multizone_status(config: Config) -> None:
    """Print Output and Archive status before the character menu."""
    # OUTPUT
    print("\n-- OUTPUT --")
    output_rows = _scan_output_folder(config.output_path)
    if output_rows:
        o_rows = [
            (
                r["name"],
                "OK" if r["has_video"] else "-",
                "OK" if r["has_desc"] else "-",
                "OK" if r["has_clips"] else "-",
            )
            for r in output_rows
        ]
        _print_table(
            o_rows,
            col_headers=("Folder", "Video", "Desc", "Clips"),
            col_aligns=("l", "l", "l", "l"),
        )
    else:
        print("(no output folders found)")

    # ARCHIVE
    total_archived, char_counts = _scan_archive_folder(config.archive_path)
    if total_archived:
        breakdown = ", ".join(
            f"{char} ({n})" for char, n in sorted(char_counts.items())
        )
        print(f"\n-- ARCHIVE -- {total_archived} clip(s): {breakdown}")
    else:
        print("\n-- ARCHIVE -- (empty)")

    print()


# ── Input helpers ─────────────────────────────────────────────────────────────

def _prompt_choice(max_choice: int) -> int:
    while True:
        try:
            raw = input("Enter choice: ").strip()
            choice = int(raw)
            if 1 <= choice <= max_choice:
                return choice
        except (ValueError, EOFError):
            pass
        print(f"  Invalid — enter a number between 1 and {max_choice}.")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(config: Config, force_encode: bool = False) -> None:
    t0 = time.perf_counter()

    config.output_path.mkdir(parents=True, exist_ok=True)

    if not config.clips_path.exists():
        raise FileNotFoundError(f"Clips path not found: {config.clips_path}")

    # --- Step 1: sort any unsorted clips into character subfolders ---
    sort_clips(config.clips_path, protect_recent=config.protect_recent_clips)

    # --- Step 2: show full folder status (Highlights + Output + Archive) ---
    _print_multizone_status(config)

    # --- Step 3: discover character subfolders ---
    char_folders = sorted(e for e in config.clips_path.iterdir() if e.is_dir())
    if not char_folders:
        char_folders = [config.clips_path]

    # --- Step 4: scan Highlights folders for the character selection menu ---
    with ThreadPoolExecutor() as pool:
        summaries = list(pool.map(
            lambda f: summarize_folder(f, config.ffprobe), char_folders
        ))
    for folder, (count, dur) in zip(char_folders, summaries):
        logging.debug("  %s: %d clips, %s", folder.name, count, _fmt_duration(dur))

    # --- Step 5: character selection menu ---
    rows = []
    estimates = []
    for i, (folder, (count, dur)) in enumerate(zip(char_folders, summaries), 1):
        batches_n = math.ceil(dur / config.target_batch_seconds) if dur > 0 else 0
        est = _estimate_seconds(folder, config.cache_dir, dur)
        estimates.append(est)
        rows.append((
            str(i),
            folder.name,
            str(count) if count else "0",
            _fmt_duration(dur) if count else "—",
            f"~{batches_n}" if batches_n else "—",
            _menu_status(dur, config.target_batch_seconds),
            _date_range(folder),
        ))
        logging.debug("Menu item %d: %s — %d clips, %s, est %s",
                      i, folder.name, count, _fmt_duration(dur), _fmt_estimate(est))

    col_headers = ("#", "Character", "Clips", "Duration", "Batches", "Status", "Date Range")
    col_aligns  = ("r",  "l",         "r",     "r",         "r",       "l",     "l")
    col_widths  = [max(len(col_headers[c]), max(len(r[c]) for r in rows)) for c in range(len(col_headers))]

    def _print_char_table(highlight_row=None):
        print(_tbl_line(col_widths, "┌", "┬", "┐"))
        print(_tbl_row(col_headers, col_widths, col_aligns))
        for row in (rows if highlight_row is None else [rows[highlight_row]]):
            print(_tbl_line(col_widths, "├", "┼", "┤"))
            print(_tbl_row(row, col_widths, col_aligns))
        print(_tbl_line(col_widths, "└", "┴", "┘"))

    _print_char_table()
    print(f"  [P] Pre-process all clips (warm KO cache)")
    if force_encode:
        print("  [--force mode: existing output files will be re-encoded]")
    else:
        print("  (existing output files are skipped — use --force to re-encode)")
    print()

    # --- Step 6: main menu loop (character number or P for pre-process) ---
    while True:
        raw = input(f"Enter choice (1-{len(char_folders)} or P): ").strip().lower()

        if raw in ("p", "pre", "preprocess"):
            logging.info("Pre-processing all clips...")
            preprocess_all(config)
            # Refresh the display and re-show the menu after pre-processing
            _print_char_table()
            print(f"  [P] Pre-process all clips (warm KO cache)")
            print()
            continue

        try:
            choice = int(raw)
            if 1 <= choice <= len(char_folders):
                break
        except ValueError:
            pass
        print(f"  Invalid — enter a number between 1 and {len(char_folders)}, or P.")

    char_path = char_folders[choice - 1]
    est_str = _fmt_estimate(estimates[choice - 1])
    _print_char_table(highlight_row=choice - 1)
    raw = input(f"Make this video? Estimated processing time: {est_str}. [y/N]: ").strip().lower()
    if raw not in ("y", "yes"):
        logging.info("Cancelled.")
        return

    logging.info("Selected: %s", char_path.name)

    # --- Step 7: process selected character ---
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

    if len(batches) > 1:
        print(f"Generate all {len(batches)} batches, or just one?")
        print("  [A] All batches")
        for b in batches:
            print(f"  [{b.number}] Batch {b.number} only  ({b.duration_str})")
        while True:
            raw = input(f"Enter choice [A/1-{len(batches)}]: ").strip().lower()
            if raw in ("a", "all", ""):
                batches_to_run = batches
                break
            try:
                n = int(raw)
                if 1 <= n <= len(batches):
                    batches_to_run = [batches[n - 1]]
                    break
            except ValueError:
                pass
            print(f"  Invalid — enter A or a number between 1 and {len(batches)}.")
    else:
        batches_to_run = batches

    total_batches = 0

    for batch in batches_to_run:
        logging.info("")
        logging.info("--- %s  Batch %d/%d  (%s) ---",
                     char_name, batch.number, len(batches), batch.duration_str)

        logging.info("Scanning for KO events...")
        t_ko = time.perf_counter()
        highlights, clip_tiers = _collect_highlights(batch, config)
        logging.debug("KO scan took %.1fs", time.perf_counter() - t_ko)
        if not highlights:
            logging.info("(no Quad+ kills detected)")
        else:
            logging.info("%d Quad+ kill(s) found.", len(highlights))

        slug = _batch_slug(char_name, batch, len(batches))
        out_dir = config.output_path / slug
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

        _move_clips(batch, clip_tiers, out_dir / "clips")

        total_batches += 1

    elapsed = time.perf_counter() - t0
    est_total = estimates[char_folders.index(char_path)]
    logging.info("")
    logging.info("=" * 50)
    logging.info("Done.  %d batch(es) encoded in %.1fs  (estimated %.1fs)", total_batches, elapsed, est_total)
    logging.info("Output: %s", config.output_path)

    print("\a", end="", flush=True)
    logging.info(">>> Encoding complete! Please check the output video. <<<")
