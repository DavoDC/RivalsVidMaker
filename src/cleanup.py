"""
cleanup.py - Interactive post-YouTube cleanup for a compiled output folder.

Workflow (called after user confirms a video is live on YouTube):
1. List every clip in Output/<slug>/clips/ with its detected KO tier.
2. Identify Quad+ clips → propose moving them to ClipArchive/.
3. Identify remaining clips → propose deletion (shows each file).
4. Show compiled .mp4 size → ask whether to delete to save disk space.
5. Nothing happens until the user confirms each action.

Usage (from main menu or pipeline):
    from cleanup import run_cleanup
    run_cleanup(output_folder, archive_path)

    output_folder - e.g. Path("C:/Videos/MarvelRivals/Output/THOR_Feb-Mar_2026")
    archive_path  - e.g. Path("C:/Videos/MarvelRivals/ClipArchive")
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
        confirmed = _confirm("Is this video live on YouTube?", dry_run=False)
        if not confirmed:
            print("Cleanup aborted - confirm on YouTube first.")
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
        print("clips/ folder is empty or missing - nothing to clean up here.")

    # ── Step 2: archive Quad+ clips ───────────────────────────────────────────
    quad_plus = [p for p in clip_files if _tier_from_name(p.name) in ARCHIVE_MIN_TIERS]
    if quad_plus:
        char_name = quad_plus[0].stem.split("_")[0]
        char_archive = archive_path / char_name
        print(f"\n{len(quad_plus)} Quad+ clip(s) to archive -> {archive_path.name}/{char_name}/:")
        for p in quad_plus:
            print(f"  {p.name}")
        if _confirm("\nMove these to ClipArchive?", dry_run=dry_run):
            char_archive.mkdir(parents=True, exist_ok=True)

            before_archive = set(p.name for p in char_archive.iterdir() if p.is_file())
            before_clips = set(p.name for p in clips_dir.iterdir() if p.is_file())

            moved = 0
            for p in quad_plus:
                dest = char_archive / p.name
                if dest.exists():
                    logging.warning("Archive destination already exists, skipping: %s", p.name)
                    print(f"  [skipped] {p.name} - already in archive")
                    continue
                try:
                    shutil.move(str(p), str(dest))
                    logging.debug("Archived: %s -> %s", p.name, char_archive)
                    moved += 1
                except OSError as e:
                    logging.error("Failed to archive %s: %s", p.name, e)
                    print(f"  [error] {p.name}: {e}")

            # Verify: expected files added to archive, removed from clips
            after_archive = set(p.name for p in char_archive.iterdir() if p.is_file())
            after_clips = set(p.name for p in clips_dir.iterdir() if p.is_file())
            unexpected_remaining = set(p.name for p in quad_plus) & after_clips
            unexpected_missing = (before_archive - after_archive)
            if unexpected_remaining:
                logging.warning("Archive verify: these files still in clips/ after move: %s", unexpected_remaining)
            if unexpected_missing:
                logging.warning("Archive verify: these files disappeared from archive: %s", unexpected_missing)
            logging.debug("Archive verify: %d added, clips/ went from %d to %d files",
                          len(after_archive - before_archive), len(before_clips), len(after_clips))

            print(f"{moved}/{len(quad_plus)} clip(s) archived.")
            # Refresh clip_files - quad_plus clips have moved
            clip_files = sorted(
                p for p in clips_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".mp4"
            )
        else:
            print("Skipped archiving.")
    else:
        print("\n(no Quad+ clips to archive)")

    # ── Step 3: delete remaining clips ───────────────────────────────────────
    remaining = [p for p in clip_files if p.exists()]
    if remaining:
        print(f"\n{len(remaining)} remaining clip(s) to delete:")
        for p in remaining:
            print(f"  {p.name}")
        if _confirm("\nDelete these clips permanently?", dry_run=dry_run):
            deleted = 0
            for p in remaining:
                try:
                    p.unlink()
                    logging.debug("Deleted clip: %s", p.name)
                    deleted += 1
                except OSError as e:
                    logging.error("Failed to delete %s: %s", p.name, e)
                    print(f"  [error] deleting {p.name}: {e}")
            print(f"{deleted}/{len(remaining)} clip(s) deleted.")
            try:
                clips_dir.rmdir()
                logging.debug("Removed empty clips/ directory")
            except OSError:
                pass
        else:
            print("Skipped clip deletion.")
    else:
        print("\n(no remaining clips to delete)")

    # ── Step 4: delete compiled .mp4 ─────────────────────────────────────────
    mp4s = list(output_folder.glob("*.mp4"))
    if mp4s:
        for mp4 in mp4s:
            size_str = _fmt_size(mp4)
            print(f"\nCompiled video: {mp4.name}  ({size_str})")
            if _confirm("Delete this file to free disk space?", dry_run=dry_run):
                try:
                    mp4.unlink()
                    logging.debug("Deleted compiled video: %s", mp4.name)
                    print(f"Deleted: {mp4.name}")
                except OSError as e:
                    logging.error("Failed to delete %s: %s", mp4.name, e)
                    print(f"[error] deleting {mp4.name}: {e}")
            else:
                print("Kept compiled video.")
    else:
        print("\n(no compiled .mp4 found in output folder)")

    # Remove description .txt files (no longer needed once video is gone)
    for txt in output_folder.glob("*_description.txt"):
        try:
            txt.unlink()
            logging.info("Deleted description file: %s", txt.name)
        except OSError:
            pass

    # Remove the output folder itself if now empty
    try:
        output_folder.rmdir()
        logging.info("Removed empty output folder: %s", output_folder.name)
    except OSError:
        pass  # Not empty - leave it

    print()
    print("  Cleanup complete.")
    print()


def run_uncompile(
    output_folder: Path,
    clips_path: Path,
    state_path: Path | None = None,
) -> None:
    """
    Reverse a compile: move all clips from output_folder/clips/ back to
    Highlights/<char>/, then delete the output folder (compiled video,
    description file, clips subdir, and the folder itself).

    Use case: a batch was compiled incorrectly (e.g. KO/NONE clips included)
    and needs to be re-done from scratch.

    Parameters
    ----------
    output_folder : path to the compiled output folder (e.g. Output/THOR_Mar_2026_BATCH1)
    clips_path    : path to the Highlights root (clips go back here under their char subfolder)
    state_path    : path to state.json; if provided, clears YouTube-confirmed status for this folder
    """
    from clip_sorter import extract_character

    if not output_folder.exists():
        logging.error("Output folder not found: %s", output_folder)
        return

    clips_dir = output_folder / "clips"
    clip_files = sorted(
        p for p in clips_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".mp4"
    ) if clips_dir.exists() else []

    if not clip_files:
        print(f"\nNo clips found in {output_folder.name}/clips/ - nothing to restore.")
        return

    # Infer character from clip filenames
    char_name = extract_character(clip_files[0].stem)
    if not char_name:
        # Fallback: everything before the date stamp
        char_name = clip_files[0].stem.split("_")[0]
    highlights_char = clips_path / char_name

    print(f"\nUncompile: {output_folder.name}")
    print("=" * 56)
    print(f"Restoring {len(clip_files)} clip(s) -> Highlights/{char_name}/")
    for p in clip_files:
        print(f"  {p.name}")

    mp4s = list(output_folder.glob("*.mp4"))
    if mp4s:
        sizes = ", ".join(_fmt_size(p) for p in mp4s)
        print(f"\nCompiled video will be deleted: {', '.join(p.name for p in mp4s)}  ({sizes})")

    raw = input("\nRestore clips and delete this output folder? [y/N]: ").strip().lower()
    if raw not in ("y", "yes"):
        print("Uncompile cancelled.")
        return

    # Move clips back to Highlights/<char>/
    highlights_char.mkdir(parents=True, exist_ok=True)
    restored = 0
    for p in clip_files:
        dest = highlights_char / p.name
        if dest.exists():
            logging.warning("Destination already exists, skipping: %s", p.name)
            print(f"  [skipped] {p.name} - already in Highlights/{char_name}/")
            continue
        try:
            import shutil as _shutil
            _shutil.move(str(p), str(dest))
            logging.debug("Restored: %s -> Highlights/%s/", p.name, char_name)
            restored += 1
        except OSError as e:
            logging.error("Failed to restore %s: %s", p.name, e)
            print(f"  [error] {p.name}: {e}")

    print(f"{restored}/{len(clip_files)} clip(s) restored to Highlights/{char_name}/.")

    # Delete compiled video(s)
    for mp4 in mp4s:
        try:
            mp4.unlink()
            logging.debug("Deleted compiled video: %s", mp4.name)
        except OSError as e:
            logging.error("Failed to delete compiled video %s: %s", mp4.name, e)

    # Delete description file(s)
    for txt in output_folder.glob("*_description.txt"):
        try:
            txt.unlink()
            logging.debug("Deleted description: %s", txt.name)
        except OSError as e:
            logging.error("Failed to delete description %s: %s", txt.name, e)

    # Remove now-empty clips/ dir and output folder
    try:
        clips_dir.rmdir()
    except OSError:
        pass
    try:
        output_folder.rmdir()
        logging.info("Removed output folder: %s", output_folder.name)
    except OSError:
        logging.warning("Output folder not empty after uncompile - manual check needed: %s", output_folder)

    # Clear YouTube-confirmed state if present
    if state_path:
        state = load_state(state_path)
        folder_name = output_folder.name
        if is_youtube_confirmed(state, folder_name):
            state.get("youtube_confirmed", {}).pop(folder_name, None)
            save_state(state, state_path)
            logging.info("Cleared YouTube-confirmed status for '%s'.", folder_name)

    print("\n  Uncompile complete.")
    print()
