"""
pipeline.py — Main orchestrator: sort → scan → batch → detect → encode → describe.
"""

import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import ko_detect
from batcher import make_batches
from clip_scanner import VIDEO_EXTS, scan_folder, summarize_folder
from clip_sorter import sort_clips
from config import Config
from description_writer import fmt_ts, write_description
from encoder import encode


def _collect_highlights(batch, config: Config) -> list[tuple[float, float, str, str]]:
    """
    Scan each clip for KO events and return Quad+ highlights with compilation timestamps.
    """
    ko_detect.configure(
        ffmpeg=str(config.ffmpeg),
        tesseract=str(config.tesseract),
        cache_dir=str(config.cache_dir / batch.clips[0].path.parent.name),
    )

    highlights = []
    running = 0.0

    for clip in batch.clips:
        logging.debug("  KO scan: %s (offset %.1fs)", clip.name, running)
        result = ko_detect.scan_clip(str(clip.path), use_cache=True)
        if result:
            tier = result["tier"]
            logging.debug("    detected %s  start=%.1f  max=%.1f", tier, result["start_ts"], result["max_ts"])
            if ko_detect.TIER_RANK.get(tier, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
                video_start = running + result["start_ts"]
                video_max = running + result["max_ts"]
                highlights.append((video_start, video_max, tier, clip.name))
                logging.info("    %s @ %s–%s", tier, fmt_ts(video_start), fmt_ts(video_max))
        else:
            logging.debug("    no kill detected")
        running += clip.duration

    return highlights


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


_MONTH = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

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


def _menu_status(dur: float, target: int, minimum: int) -> str:
    if dur >= target:   return "✓ Ready"
    if dur >= minimum:  return "~ Almost"
    if dur > 0:         return "✗ Too short"
    return "— No clips"


def _tbl_row(cells, widths, aligns) -> str:
    parts = [c.rjust(w) if a == "r" else c.ljust(w) for c, w, a in zip(cells, widths, aligns)]
    return "│ " + " │ ".join(parts) + " │"


def _tbl_line(widths, left, mid, right) -> str:
    return left + mid.join("─" * (w + 2) for w in widths) + right


def _prompt_choice(max_choice: int) -> int:
    while True:
        try:
            raw = input("\nEnter choice: ").strip()
            choice = int(raw)
            if 1 <= choice <= max_choice:
                return choice
        except (ValueError, EOFError):
            pass
        print(f"  Invalid — enter a number between 1 and {max_choice}.")


def run(config: Config) -> None:
    t0 = time.perf_counter()

    config.output_path.mkdir(parents=True, exist_ok=True)

    if not config.clips_path.exists():
        raise FileNotFoundError(f"Clips path not found: {config.clips_path}")

    # --- Step 1: sort any unsorted clips into character subfolders ---
    sort_clips(config.clips_path)

    # --- Step 2: discover character subfolders ---
    char_folders = sorted(e for e in config.clips_path.iterdir() if e.is_dir())
    if not char_folders:
        char_folders = [config.clips_path]

    # --- Step 3: scan all folders in parallel for clip counts + durations ---
    logging.info("Scanning clips...")
    with ThreadPoolExecutor() as pool:
        summaries = list(pool.map(
            lambda f: summarize_folder(f, config.ffprobe), char_folders
        ))
    for folder, (count, dur) in zip(char_folders, summaries):
        logging.debug("  %s: %d clips, %s", folder.name, count, _fmt_duration(dur))

    # --- Step 4: character selection menu ---
    rows = []
    for i, (folder, (count, dur)) in enumerate(zip(char_folders, summaries), 1):
        batches_n = math.ceil(dur / config.target_batch_seconds) if dur > 0 else 0
        rows.append((
            str(i),
            folder.name,
            str(count) if count else "0",
            _fmt_duration(dur) if count else "—",
            f"~{batches_n}" if batches_n else "—",
            _menu_status(dur, config.target_batch_seconds, config.min_batch_seconds),
            _date_range(folder),
        ))
        logging.debug("Menu item %d: %s — %d clips, %s", i, folder.name, count, _fmt_duration(dur))

    col_headers = ("#", "Character", "Clips", "Duration", "Batches", "Status",     "Date Range")
    col_aligns  = ("r",  "l",         "r",     "r",         "r",       "l",         "l")
    col_widths  = [max(len(col_headers[c]), max(len(r[c]) for r in rows)) for c in range(len(col_headers))]

    print()
    print(_tbl_line(col_widths, "┌", "┬", "┐"))
    print(_tbl_row(col_headers, col_widths, col_aligns))
    for row in rows:
        print(_tbl_line(col_widths, "├", "┼", "┤"))
        print(_tbl_row(row, col_widths, col_aligns))
    print(_tbl_line(col_widths, "└", "┴", "┘"))

    choice = _prompt_choice(len(char_folders))
    char_path = char_folders[choice - 1]
    logging.info("Selected: %s", char_path.name)

    # --- Step 5: process selected character ---
    char_name = char_path.name
    logging.info("")
    logging.info("=" * 50)
    logging.info("Character: %s", char_name)
    logging.info("=" * 50)

    clips = scan_folder(char_path, config.ffprobe)
    if not clips:
        logging.info("No clips found — nothing to process.")
        return

    batches = make_batches(clips, config.target_batch_seconds)
    logging.info("Batching: %d batch(es)", len(batches))
    for b in batches:
        logging.info("  Batch %d: %d clip(s), %s", b.number, len(b.clips), b.duration_str)

    total_batches = 0

    for batch in batches:
        logging.info("")
        logging.info("--- %s  Batch %d/%d  (%s) ---",
                     char_name, batch.number, len(batches), batch.duration_str)

        if batch.total_duration < config.min_batch_seconds:
            min_m = config.min_batch_seconds // 60
            logging.info(
                "  SKIP — too short (%s), minimum is %dm. Not worth uploading.",
                batch.duration_str, min_m,
            )
            continue

        logging.info("  Scanning for KO events...")
        highlights = _collect_highlights(batch, config)
        if not highlights:
            logging.info("  (no Quad+ kills detected)")
        else:
            logging.info("  %d Quad+ kill(s) found.", len(highlights))

        out_dir = config.output_path / char_name / f"batch{batch.number}"
        encode(batch, char_name, out_dir, config.ffmpeg)
        write_description(batch, char_name, highlights, out_dir)

        total_batches += 1

    elapsed = time.perf_counter() - t0
    logging.info("")
    logging.info("=" * 50)
    logging.info("Done.  %d batch(es) encoded in %.1fs", total_batches, elapsed)
    logging.info("Output: %s", config.output_path)

    print("\a", end="", flush=True)
    logging.info(">>> Encoding complete! Please check the output video. <<<")
