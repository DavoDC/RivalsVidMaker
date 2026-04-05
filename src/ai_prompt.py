"""
ai_prompt.py - Generate a Markdown file of pre-filled AI prompts for the YouTube
title and description, based on the pipeline's detected output for a batch.

The generated file is placed alongside the description.txt so the user can find
it instantly after a run:

    data/output/<slug>/<slug>_ai_prompts.md

Usage (from pipeline.py):
    from ai_prompt import write_ai_prompts
    write_ai_prompts(
        out_dir=out_dir,
        char_name=char_name,
        clip_count=len(batch.clips),
        date_range=_date_range(char_path),
        ko_tiers=ko_tier_counts,       # {tier: count} e.g. {"QUAD": 3, "PENTA": 1}
        description_path=desc_path,    # Path to the written description.txt
        out_stem=slug,
    )
"""

import logging
from pathlib import Path


def _ko_summary(ko_tiers: dict[str, int]) -> str:
    """Human-readable kill-tier summary. E.g. '2x QUAD, 1x PENTA'."""
    if not ko_tiers:
        return "(no Quad+ kills detected)"
    tier_order = ["HEXA", "PENTA", "QUAD", "TRIPLE", "DOUBLE", "KO"]
    parts = []
    for t in tier_order:
        if t in ko_tiers:
            parts.append(f"{ko_tiers[t]}x {t}")
    # Any unexpected tiers not in the ordered list
    for t, n in ko_tiers.items():
        if t not in tier_order:
            parts.append(f"{n}x {t}")
    return ", ".join(parts) if parts else "(no kills detected)"


def write_ai_prompts(
    out_dir: Path,
    char_name: str,
    clip_count: int,
    date_range: str,
    ko_tiers: dict[str, int],
    description_path: Path,
    out_stem: str,
) -> Path:
    """
    Write a Markdown file with pre-filled AI prompts for title + description.

    Parameters
    ----------
    out_dir          : output folder (e.g. Output/THOR_Feb-Mar_2026/)
    char_name        : e.g. "THOR"
    clip_count       : number of clips in the batch
    date_range       : human-readable date range, e.g. "Feb–Mar 2026"
    ko_tiers         : {tier: count} for kills detected in this batch
    description_path : Path to the written *_description.txt (for reference)
    out_stem         : slug used for the output filename, e.g. "THOR_Feb-Mar_2026"

    Returns the path to the written file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_stem}_ai_prompts.md"

    kill_summary = _ko_summary(ko_tiers)
    desc_filename = description_path.name if description_path else f"{out_stem}_description.txt"

    lines: list[str] = []
    lines.append(f"# AI Prompts - {out_stem}\n\n")
    lines.append(
        f"> **PASTE INTO FREE AI (ChatGPT / Grok) AND REPLACE TITLE + DESCRIPTION IN "
        f"`{desc_filename}`**\n\n"
    )
    lines.append(
        "Use Prompt 3 (combined). Copy the block, paste into ChatGPT or Grok, "
        "then copy the Title and Description lines back into your description file.\n\n"
    )
    lines.append("---\n\n")

    # ── Context block ────────────────────────────────────────────────────────
    lines.append("## Video context\n\n")
    lines.append(f"- **Character:** {char_name}\n")
    lines.append(f"- **Clips:** {clip_count}\n")
    lines.append(f"- **Date range:** {date_range}\n")
    lines.append(f"- **Kills detected:** {kill_summary}\n\n")
    lines.append("---\n\n")

    # ── Prompt 1: title ──────────────────────────────────────────────────────
    lines.append("## Prompt 1 - YouTube title\n\n")
    lines.append("```\n")
    lines.append(
        f"Write a punchy, hype YouTube title for a Marvel Rivals {char_name} "
        f"multikill highlights compilation.\n"
        f"\n"
        f"Context:\n"
        f"- Character: {char_name}\n"
        f"- Date range: {date_range}\n"
        f"- Kill highlights: {kill_summary}\n"
        f"- Total clips: {clip_count}\n"
        f"\n"
        f"Format: <CHARACTER> <CAPS TAGLINE> ⚡ <subtitle> (<date range>)\n"
        f"Examples:\n"
        f"  THOR OVERLOAD ⚡ Back-to-Back Multikills (Feb–Mar 2026)\n"
        f"  THOR AWAKENS ⚡ Multikill Highlights (Feb 2026)\n"
        f"\n"
        f"Return 3 title options. Keep each under 80 characters.\n"
    )
    lines.append("```\n\n")

    # ── Prompt 2: one-liner description ─────────────────────────────────────
    lines.append("## Prompt 2 - One-liner description\n\n")
    lines.append("```\n")
    lines.append(
        f"Write a punchy one-liner YouTube description for a Marvel Rivals "
        f"{char_name} highlights video.\n"
        f"\n"
        f"Context:\n"
        f"- Character: {char_name}\n"
        f"- Date range: {date_range}\n"
        f"- Kill highlights: {kill_summary}\n"
        f"- Tone: hype, fast-paced, uses emojis\n"
        f"\n"
        f"Format: starts with a hype phrase, ends with 'in Marvel Rivals' "
        f"or a reference to the game. Include emojis throughout.\n"
        f"Example: ⚡ The storm answers only to the worthy - Mjolnir unleashed, "
        f"lightning combos, and relentless Thor multikills across Feb–Mar 2026 "
        f"in Marvel Rivals 🔥⚡\n"
        f"\n"
        f"Return 3 options.\n"
    )
    lines.append("```\n\n")

    # ── Prompt 3: combined (title + description in one go) ───────────────────
    lines.append("## Prompt 3 - Combined (title + description together)\n\n")
    lines.append("```\n")
    lines.append(
        f"I'm uploading a Marvel Rivals {char_name} multikill highlights compilation "
        f"to YouTube. Give me a title and one-liner description.\n"
        f"\n"
        f"Video details:\n"
        f"- Character: {char_name}\n"
        f"- Date range: {date_range}\n"
        f"- Highlights: {kill_summary}\n"
        f"- Clip count: {clip_count}\n"
        f"\n"
        f"Title format: <CHARACTER> <CAPS TAGLINE> ⚡ <subtitle> (<date range>)\n"
        f"Description: one punchy sentence, hype tone, emojis, ends referencing Marvel Rivals.\n"
        f"\n"
        f"Return:\n"
        f"  Title: ...\n"
        f"  Description: ...\n"
    )
    lines.append("```\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    logging.info("AI prompts → %s", out_path)
    return out_path
