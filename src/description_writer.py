"""
description_writer.py — Write a YouTube-ready description file for a batch.

Replaces C++: DescriptionWriter.cpp
Uses the canonical format documented in CLAUDE.md.
"""

import logging
from pathlib import Path

from batcher import Batch

# (video_start_ts, video_max_ts, tier, clip_name)
Highlight = tuple[float, float, str, str]


def fmt_ts(secs: float) -> str:
    """Format seconds as M:SS (e.g. 96 → '1:36')."""
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"


def write_description(
    batch: Batch,
    char_name: str,
    highlights: list[Highlight],
    output_dir: Path,
) -> Path:
    """
    Write a description.txt to output_dir.

    highlights: list of (video_start_ts, video_max_ts, tier, clip_name)
                for Quad+ kills only, in video order.

    Returns the path to the written file.
    Running twice with the same inputs produces identical output (idempotent).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "description.txt"

    lines: list[str] = []

    lines.append("=== TITLE ===\n")
    lines.append(f"Marvel Rivals {char_name} Highlights Part {batch.number}\n")
    lines.append("\n")

    lines.append("=== DESCRIPTION ===\n")
    lines.append(
        f"Marvel Rivals {char_name} highlights compilation — "
        f"Part {batch.number} ({batch.duration_str})\n"
    )
    lines.append("\n")

    if highlights:
        lines.append("=== TIMESTAMPS ===\n")
        lines.append("Format: <streak start> - <max kill time> = Kill tier\n")
        for start_ts, max_ts, tier, _ in highlights:
            lines.append(f"{fmt_ts(start_ts)} - {fmt_ts(max_ts)} = {tier.capitalize()} Kill\n")
        lines.append("\n")

    lines.append("=== HIGHLIGHTS ===\n")
    for i, clip in enumerate(batch.clips, 1):
        lines.append(f"{i}. {clip.name}\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    logging.info("  Description → %s", out_path)
    return out_path
