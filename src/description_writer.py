"""
description_writer.py - Write a YouTube-ready description file for a batch.

Replaces C++: DescriptionWriter.cpp
Uses the canonical format documented in CLAUDE.md.
"""

import logging
from pathlib import Path

from batcher import Batch

# (video_start_ts, video_max_ts, tier, clip_name)
Highlight = tuple[float, float, str, str]


def fmt_ts(secs: float) -> str:
    """Format seconds as M:SS (e.g. 96 -> '1:36')."""
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"


def _ko_summary(ko_tiers: dict[str, int]) -> str:
    """Human-readable kill-tier summary. E.g. '2x QUAD, 1x PENTA'."""
    if not ko_tiers:
        return "(no Quad+ kills detected)"
    tier_order = ["HEXA", "PENTA", "QUAD", "TRIPLE", "DOUBLE", "KO"]
    parts = []
    for t in tier_order:
        if t in ko_tiers:
            parts.append(f"{ko_tiers[t]}x {t}")
    for t, n in ko_tiers.items():
        if t not in tier_order:
            parts.append(f"{n}x {t}")
    return ", ".join(parts) if parts else "(no kills detected)"


def write_description(
    batch: Batch,
    char_name: str,
    highlights: list[Highlight],
    output_dir: Path,
    out_stem: str | None = None,
    clip_tiers: dict[str, str] | None = None,
    date_range: str | None = None,
    ko_tiers: dict[str, int] | None = None,
    clip_count: int | None = None,
) -> Path:
    """
    Write a description .txt to output_dir named {out_stem}_description.txt.

    When date_range, ko_tiers and clip_count are provided, the file includes
    AI prompts for title and description at the top (merged format).

    highlights:  list of (video_start_ts, video_max_ts, tier, clip_name)
                 for Quad+ kills only, in video order.
    clip_tiers:  optional {clip.name: tier} for ALL detected kills.

    Returns the path to the written file.
    Running twice with the same inputs produces identical output (idempotent).
    """
    if out_stem is None:
        out_stem = f"{char_name}_batch{batch.number}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{out_stem}_description.txt"

    tiers = clip_tiers or {}
    lines: list[str] = []

    ai_params_provided = date_range is not None and ko_tiers is not None and clip_count is not None

    if ai_params_provided:
        kill_summary = _ko_summary(ko_tiers)

        # Title prompt
        lines.append("=== TITLE PROMPT ===\n")
        lines.append(
            f"Write a punchy, hype YouTube title for a Marvel Rivals {char_name} "
            f"multikill highlights compilation.\n"
            f"\n"
            f"Context:\n"
            f"- Character: {char_name}\n"
            f"- Date range: {date_range}\n"
            f"\n"
            f"Format: <CHARACTER> <CAPS TAGLINE> <subtitle> (<date range>)\n"
            f"Examples:\n"
            f"  THOR OVERLOAD Back-to-Back Multikills (Feb-Mar 2026)\n"
            f"  THOR AWAKENS Multikill Highlights (Feb 2026)\n"
            f"\n"
            f"Return 3 title options. Keep each under 80 characters.\n"
        )
        lines.append("\n\n")

        # Description section - AI prompt followed by timestamps and clip list
        lines.append("=== DESCRIPTION ===\n")
        lines.append(
            f"I'm uploading a Marvel Rivals {char_name} multikill highlights compilation "
            f"to YouTube. Write a punchy one-liner description that weaves in a real "
            f"{char_name} quote - either a Marvel comic line or an in-game voiceline.\n"
            f"\n"
            f"Video details:\n"
            f"- Character: {char_name}\n"
            f"- Date range: {date_range}\n"
            f"- Highlights: {kill_summary}\n"
            f"\n"
            f"Format: one punchy sentence with the quote woven in naturally, hype tone, "
            f"emojis, ends referencing Marvel Rivals. Use a real {char_name} line - "
            f"not generic hype words.\n"
            f"\n"
            f"Return:\n"
            f"  Description: ...\n"
        )
        lines.append("\n")
        lines.append("--- Replace description prompt above with AI output before uploading ---\n")
        lines.append("\n")

    else:
        lines.append("=== TITLE ===\n")
        lines.append(f"Marvel Rivals {char_name} Highlights Part {batch.number}\n")
        lines.append("\n")

        lines.append("=== DESCRIPTION ===\n")
        lines.append(
            f"Marvel Rivals {char_name} highlights compilation - "
            f"Part {batch.number} ({batch.duration_str})\n"
        )
        lines.append("\n")

    if highlights:
        lines.append("=== TIMESTAMPS ===\n")
        for start_ts, max_ts, tier, _ in highlights:
            lines.append(f"{fmt_ts(start_ts)} - {fmt_ts(max_ts)} = {tier.capitalize()} Kill\n")
        lines.append("\n")

    lines.append("=== HIGHLIGHTS ===\n")
    for i, clip in enumerate(batch.clips, 1):
        lines.append(f"{i}. {clip.name}\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    logging.info("Description -> %s", out_path.name)
    return out_path
