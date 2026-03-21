"""
pipeline.py — Main orchestrator: sort → scan → batch → detect → encode → describe.
"""

import logging
import math
import re
import shutil
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


def _collect_highlights(batch, config: Config) -> tuple[list[tuple[float, float, str, str]], dict[str, str]]:
    """
    Scan each clip for KO events.

    Returns:
      highlights — Quad+ kills with compilation timestamps, for the description.
      clip_tiers — {clip.name: tier} for every clip where any kill was detected.
    """
    ko_detect.configure(
        ffmpeg=str(config.ffmpeg),
        tesseract=str(config.tesseract),
        cache_dir=str(config.cache_dir / batch.clips[0].path.parent.name),
    )

    highlights = []
    clip_tiers: dict[str, str] = {}
    running = 0.0

    total = len(batch.clips)
    for idx, clip in enumerate(batch.clips, 1):
        print(f"KO scan [{idx}/{total}]: {clip.name}", end="", flush=True)
        logging.debug("KO scan: %s (offset %.1fs)", clip.name, running)
        t_clip = time.perf_counter()
        result = ko_detect.scan_clip(str(clip.path), use_cache=True)
        elapsed = time.perf_counter() - t_clip
        elapsed_str = f"{int(elapsed)//60}m{int(elapsed)%60:02d}s" if elapsed >= 60 else f"{elapsed:.1f}s"

        tier_found = None
        if result:
            tier = result["tier"]
            logging.debug("detected %s  start=%.1f  max=%.1f", tier, result["start_ts"], result["max_ts"])
            tier_found = tier
            clip_tiers[clip.name] = tier
            if ko_detect.TIER_RANK.get(tier, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
                video_start = running + result["start_ts"]
                video_max = running + result["max_ts"]
                highlights.append((video_start, video_max, tier, clip.name))
        else:
            logging.debug("no kill detected")

        suffix = f" — {tier_found}" if tier_found else ""
        print(f" -> Done (took {elapsed_str}){suffix}")
        logging.debug("KO scan [%d/%d]: %s — %.1fs%s", idx, total, clip.name, elapsed, f" {tier_found}" if tier_found else "")
        if tier_found and ko_detect.TIER_RANK.get(tier_found, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
            logging.info("%s @ %s–%s", tier_found, fmt_ts(highlights[-1][0]), fmt_ts(highlights[-1][1]))
        running += clip.duration

    return highlights, clip_tiers


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


def _menu_status(dur: float, target: int) -> str:
    if dur >= target:        return "✓ Ready"
    if dur >= target * 0.75: return "~ Almost"   # 11m15s+ at default 15m target
    if dur > 0:              return "✗ Too short"
    return "— No clips"


def _tbl_row(cells, widths, aligns) -> str:
    parts = [c.rjust(w) if a == "r" else c.ljust(w) for c, w, a in zip(cells, widths, aligns)]
    return "│ " + " │ ".join(parts) + " │"


def _tbl_line(widths, left, mid, right) -> str:
    return left + mid.join("─" * (w + 2) for w in widths) + right


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


def _move_clips(batch, clip_tiers: dict[str, str], clips_dir: Path) -> None:
    """Move source clips into clips_dir, appending _TIER suffix where detected."""
    clips_dir.mkdir(parents=True, exist_ok=True)
    for clip in batch.clips:
        tier = clip_tiers.get(clip.name)
        stem = clip.path.stem + (f"_{tier}" if tier else "")
        dest = clips_dir / (stem + clip.path.suffix)
        shutil.move(str(clip.path), str(dest))
        logging.debug("Moved clip → %s", dest.name)
    logging.info("Clips → %s", clips_dir)


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

    # --- Step 4: character selection menu + confirmation ---
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

    def _print_table(highlight_row=None):
        print(_tbl_line(col_widths, "┌", "┬", "┐"))
        print(_tbl_row(col_headers, col_widths, col_aligns))
        for row in (rows if highlight_row is None else [rows[highlight_row]]):
            print(_tbl_line(col_widths, "├", "┼", "┤"))
            print(_tbl_row(row, col_widths, col_aligns))
        print(_tbl_line(col_widths, "└", "┴", "┘"))

    _print_table()

    while True:
        choice = _prompt_choice(len(char_folders))
        char_path = char_folders[choice - 1]
        _, (count, _dur) = list(zip(char_folders, summaries))[choice - 1]
        est_str = _fmt_estimate(estimates[choice - 1])
        _print_table(highlight_row=choice - 1)
        raw = input(f"Are you sure you want to make this video? Estimated processing time is {est_str}. [y/N]: ").strip().lower()
        if raw in ("y", "yes"):
            break

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
        encode(batch, char_name, out_dir, config.ffmpeg, out_stem=slug)
        logging.debug("Encode took %.1fs", time.perf_counter() - t_enc)
        write_description(batch, char_name, highlights, out_dir, out_stem=slug)
        _move_clips(batch, clip_tiers, out_dir / "clips")

        total_batches += 1

    elapsed = time.perf_counter() - t0
    est_total = sum(estimates[i] for i, f in enumerate(char_folders) if f == char_path)
    logging.info("")
    logging.info("=" * 50)
    logging.info("Done.  %d batch(es) encoded in %.1fs  (estimated %.1fs)", total_batches, elapsed, est_total)
    logging.info("Output: %s", config.output_path)

    print("\a", end="", flush=True)
    logging.info(">>> Encoding complete! Please check the output video. <<<")
