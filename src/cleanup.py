"""
cleanup.py — Interactive post-YouTube cleanup for a compiled output folder.

Workflow (called after user confirms a video is live on YouTube):
1. List every clip in Output/<slug>/clips/ with its detected KO tier.
2. Identify Quad+ clips → propose moving them to ClipArchive/.
3. Identify remaining clips → propose deletion (shows each file).
4. Show compiled .mp4 size → ask whether to delete to save disk space.
5. Nothing happens until the user confirms each action.

Usage (from main menu or pipeline):
    from cleanup import run_cleanup
    run_cleanup(output_folder, archive_path)

    output_folder — e.g. Path("C:/Videos/MarvelRivals/Output/THOR_Feb-Mar_2026")
    archive_path  — e.g. Path("C:/Videos/MarvelRivals/ClipArchive")
"""

import logging
import re
import shutil
from pathlib import Path

from state import is_youtube_confirmed, load as load_state, mark_youtube_confirmed, save as save_state

# Tiers considered worth archiving (Quad and above)
ARCHIVE_MIN_TIERS = {"QUAD", "PENTA", "HEXA"}

# Regex that matches the _TIER suffix embedded in a clip filename
_TIER_SUFFIX_RE = re.compile(r"_(QUAD|PENTA|HEXA|TRIPLE|DOUBLE|KO)(?=\.mp4$)", re.IGNORECASE)


def _tier_from_name(name: str) -> str | None:
    """Extract the embedded KO tier from a clip filename, e.g. '_QUAD' → 'QUAD'."""
    m = _TIER_SUFFIX_RE.search(name)
    return m.group(1).upper() if m else None


def _fmt_size(path: Path) -> str:
    """Format a file size as a human-readable string (MB)."""
    try:
        mb = path.stat().st_size / (1024 * 1024)
        return f"{mb:.1f} MB"
    except OSError:
        return "unknown size"


def _confirm(prompt: str, dry_run: bool = False) -> bool:
    """Prompt the user for yes/no.  Returns True only for 'y' or 'yes'.

    In dry_run mode, always returns False without prompting.
    """
    if dry_run:
        return False
    try:
        raw = input(f"{prompt} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return raw in ("y", "yes")


def run_cleanup(
    output_folder: Path,
    archive_path: Path,
    state_path: Path | None = None,
    dry_run: bool = False,
) -> None:
    """
    Interactive post-YouTube cleanup for one output folder.

    Parameters
    ----------
    output_folder : path to a compiled output folder (e.g. Output/THOR_FEB-MAR_2026/)
    archive_path  : path to the ClipArchive folder
    state_path    : path to state.json; if provided, saves YouTube-confirmed status
    dry_run       : if True, print the plan without moving or deleting anything

    Steps:
    0. Confirm the video is live on YouTube (gates the whole cleanup).
    1. List all clips in output_folder/clips/ with their KO tier (from filename suffix).
    2. Identify Quad+ clips -> propose moving to archive_path.
    3. Identify remaining clips -> propose deletion (shows each file).
    4. Show compiled .mp4 size -> ask whether to delete.
    5. Nothing happens until the user types 'yes' for each action.
       With dry_run=True, only the plan is printed.
    """
    if dry_run:
        print("[DRY RUN] No files will be moved or deleted.\n")

    if not output_folder.exists():
        logging.error("Output folder not found: %s", output_folder)
        return

    # Step 0: confirm video is live on YouTube before proceeding
    folder_name = output_folder.name
    state = load_state(state_path) if state_path else {}
    already_confirmed = is_youtube_confirmed(state, folder_name)

    if not already_confirmed:
        print(f"\nBefore cleaning up '{folder_name}':")
        confirmed = _confirm("  Is this video live on YouTube?", dry_run=False)
        if not confirmed:
            print("  Cleanup aborted - confirm on YouTube first.")
            return
        if state_path:
            state = mark_youtube_confirmed(state, folder_name)
            save_state(state, state_path)
            logging.info("Marked '%s' as YouTube-confirmed in state log.", folder_name)

    clips_dir = output_folder / "clips"

    print()
    print(f"Cleanup: {output_folder.name}")
    print("=" * 56)

    # ── Step 1: list clips ────────────────────────────────────────────────────
    if clips_dir.exists():
        clip_files = sorted(
            p for p in clips_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".mp4"
        )
    else:
        clip_files = []

    if not clip_files:
        print("  clips/ folder is empty or missing — nothing to clean up here.")
    else:
        print(f"\n  {len(clip_files)} clip(s) in {clips_dir.name}/:\n")
        for p in clip_files:
            tier = _tier_from_name(p.name)
            tier_label = f"  [{tier}]" if tier else ""
            print(f"    {p.name}{tier_label}")

    # ── Step 2: archive Quad+ clips ───────────────────────────────────────────
    quad_plus = [p for p in clip_files if _tier_from_name(p.name) in ARCHIVE_MIN_TIERS]
    if quad_plus:
        print(f"\n  {len(quad_plus)} Quad+ clip(s) to archive → {archive_path.name}/:")
        for p in quad_plus:
            print(f"    {p.name}")
        if _confirm("\n  Move these to ClipArchive?", dry_run=dry_run):
            archive_path.mkdir(parents=True, exist_ok=True)
            moved = 0
            for p in quad_plus:
                dest = archive_path / p.name
                if dest.exists():
                    logging.warning("Archive destination already exists, skipping: %s", p.name)
                    print(f"    [skipped] {p.name} — already in archive")
                    continue
                try:
                    shutil.move(str(p), str(dest))
                    logging.info("Archived: %s → %s", p.name, archive_path)
                    print(f"    Archived: {p.name}")
                    moved += 1
                except OSError as e:
                    logging.error("Failed to archive %s: %s", p.name, e)
                    print(f"    [error] {p.name}: {e}")
            print(f"  {moved}/{len(quad_plus)} clip(s) archived.")
            # Refresh clip_files — quad_plus clips have moved
            clip_files = sorted(
                p for p in clips_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".mp4"
            )
        else:
            print("  Skipped archiving.")
    else:
        print("\n  (no Quad+ clips to archive)")

    # ── Step 3: delete remaining clips ───────────────────────────────────────
    remaining = [p for p in clip_files if p.exists()]
    if remaining:
        print(f"\n  {len(remaining)} remaining clip(s) to delete:")
        for p in remaining:
            print(f"    {p.name}")
        if _confirm("\n  Delete these clips permanently?", dry_run=dry_run):
            deleted = 0
            for p in remaining:
                try:
                    p.unlink()
                    logging.info("Deleted clip: %s", p.name)
                    deleted += 1
                except OSError as e:
                    logging.error("Failed to delete %s: %s", p.name, e)
                    print(f"    [error] deleting {p.name}: {e}")
            print(f"  {deleted}/{len(remaining)} clip(s) deleted.")
            # Remove the now-empty clips/ dir if nothing's left
            try:
                clips_dir.rmdir()
                logging.debug("Removed empty clips/ directory")
            except OSError:
                pass  # Not empty (e.g. an error left a file behind) — leave it
        else:
            print("  Skipped clip deletion.")
    else:
        print("\n  (no remaining clips to delete)")

    # ── Step 4: delete compiled .mp4 ─────────────────────────────────────────
    mp4s = list(output_folder.glob("*.mp4"))
    if mp4s:
        for mp4 in mp4s:
            size_str = _fmt_size(mp4)
            print(f"\n  Compiled video: {mp4.name}  ({size_str})")
            if _confirm("  Delete this file to free disk space?", dry_run=dry_run):
                try:
                    mp4.unlink()
                    logging.info("Deleted compiled video: %s", mp4.name)
                    print(f"  Deleted: {mp4.name}")
                except OSError as e:
                    logging.error("Failed to delete %s: %s", mp4.name, e)
                    print(f"  [error] deleting {mp4.name}: {e}")
            else:
                print("  Kept compiled video.")
    else:
        print("\n  (no compiled .mp4 found in output folder)")

    print()
    print("  Cleanup complete.")
    print()
