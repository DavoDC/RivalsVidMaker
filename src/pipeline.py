"""
pipeline.py — Main orchestrator: scan → batch → detect → encode → describe.

Replaces C++: Processor.cpp
"""

import time
from pathlib import Path

import ko_detect
from batcher import make_batches
from clip_scanner import scan_folder
from config import Config
from description_writer import fmt_ts, write_description
from encoder import encode


def _collect_highlights(batch, config: Config) -> list[tuple[float, float, str, str]]:
    """
    Scan each clip in the batch for KO events via ko_detect.scan_clip.

    Accumulates running video time to convert per-clip timestamps into
    compilation-level timestamps (same logic as ko_detect.run_batch).

    Returns a list of (video_start_ts, video_max_ts, tier, clip_name)
    for Quad+ kills only, in video order.
    """
    ko_detect.configure(
        ffmpeg=str(config.ffmpeg),
        tesseract=str(config.tesseract),
        cache_dir=str(config.cache_dir / batch.clips[0].path.parent.name),
    )

    highlights = []
    running = 0.0

    for clip in batch.clips:
        result = ko_detect.scan_clip(str(clip.path), use_cache=True)
        if result:
            tier = result["tier"]
            if ko_detect.TIER_RANK.get(tier, 0) >= ko_detect.TIER_RANK[ko_detect.REPORT_MIN_TIER]:
                video_start = running + result["start_ts"]
                video_max = running + result["max_ts"]
                highlights.append((video_start, video_max, tier, clip.name))
                print(f"    {tier} @ {fmt_ts(video_start)}–{fmt_ts(video_max)}")
        running += clip.duration

    return highlights


def _prompt_choice(max_choice: int) -> int:
    while True:
        try:
            raw = input("\nEnter choice: ").strip()
            choice = int(raw)
            if 0 <= choice <= max_choice:
                return choice
        except (ValueError, EOFError):
            pass
        print("  Invalid choice, try again.")


def run(config: Config) -> None:
    t0 = time.perf_counter()

    config.output_path.mkdir(parents=True, exist_ok=True)

    if not config.clips_path.exists():
        raise FileNotFoundError(f"Clips path not found: {config.clips_path}")

    # Discover character subfolders (one level deep)
    char_folders = sorted(e for e in config.clips_path.iterdir() if e.is_dir())
    if not char_folders:
        # No subfolders — treat clipsPath itself as the single character folder
        char_folders = [config.clips_path]

    # Character selection menu
    print("\nAvailable characters:")
    for i, folder in enumerate(char_folders, 1):
        print(f"  [{i}] {folder.name}")
    print("  [0] All characters")

    choice = _prompt_choice(len(char_folders))
    to_process = char_folders if choice == 0 else [char_folders[choice - 1]]

    total_batches = 0

    for char_path in to_process:
        char_name = char_path.name
        print(f"\n{'=' * 50}")
        print(f"Character: {char_name}")
        print("=" * 50)

        clips = scan_folder(char_path, config.ffprobe)
        if not clips:
            print("  No clips found, skipping.")
            continue

        batches = make_batches(clips, config.target_batch_seconds)
        print(f"\nBatching: {len(batches)} batch(es)")
        for b in batches:
            print(f"  Batch {b.number}: {len(b.clips)} clip(s), {b.duration_str}")

        for batch in batches:
            print(
                f"\n--- {char_name}  Batch {batch.number}/{len(batches)}"
                f"  ({batch.duration_str}) ---"
            )

            if batch.total_duration < config.min_batch_seconds:
                min_m = config.min_batch_seconds // 60
                print(
                    f"  SKIP — too short ({batch.duration_str}), "
                    f"minimum is {min_m}m. Not worth uploading."
                )
                continue

            print("  Scanning for KO events...")
            highlights = _collect_highlights(batch, config)
            if not highlights:
                print("  (no Quad+ kills detected)")

            out_dir = config.output_path / char_name / f"batch{batch.number}"
            encode(batch, char_name, out_dir, config.ffmpeg)
            write_description(batch, char_name, highlights, out_dir)

            total_batches += 1

    elapsed = time.perf_counter() - t0
    print(f"\n{'=' * 50}")
    print(f"Done.  {total_batches} batch(es) encoded in {elapsed:.1f}s")
    print(f"Output: {config.output_path}")

    # Terminal bell — encoding complete
    print("\a", end="", flush=True)
    print("\n>>> Encoding complete! Please check the output video. <<<")
