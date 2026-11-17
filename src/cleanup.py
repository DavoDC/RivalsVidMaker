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
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from send2trash import send2trash

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


def locate_video_and_description(output_folder: Path) -> tuple[Path, Path]:
    """Locate .mp4 and _description.txt files in output folder.

    Returns (mp4_path, description_path) tuple.
    Raises FileNotFoundError if either file is missing.
    """
    mp4_files = list(output_folder.glob("*.mp4"))
    if not mp4_files:
        raise FileNotFoundError(f"No .mp4 video found in {output_folder}")

    if len(mp4_files) > 1:
        logging.warning(f"Multiple .mp4 files found; using the first: {mp4_files[0].name}")

    mp4_path = mp4_files[0]

    desc_files = list(output_folder.glob("*_description.txt"))
    if not desc_files:
        raise FileNotFoundError(f"No _description.txt found in {output_folder}")

    if len(desc_files) > 1:
        logging.warning(f"Multiple description files found; using the first: {desc_files[0].name}")

    desc_path = desc_files[0]

    return mp4_path, desc_path


@dataclass
class RetryResult:
    """Outcome of retry_upload. needs_sign_in means the token was kept and the user must sign in again."""
    uploaded: bool = False
    needs_sign_in: bool = False
    cancelled: bool = False
    error: str | None = None


def retry_upload(output_folder: Path, config, confirm: bool = True) -> RetryResult:
    """Retry uploading a compiled video to YouTube. The single retry path.

    Finds the .mp4 and _description.txt in the output folder, authenticates,
    validates the channel against config.youtube_channel_id, and uploads.

    Parameters
    ----------
    output_folder : path to the output folder (e.g. Output/THOR_FEB-MAR_2026/)
    config        : Config (needs youtube_channel_id and state_path)
    confirm       : True asks "Upload this video?" first; False never prompts (GUI, pipeline)

    An auth or channel-check ValueError returns needs_sign_in=True and leaves
    the token file in place; it is never deleted here.
    """
    import uploader

    print(f"\n📤 Retry YouTube Upload: {output_folder.name}")
    print("=" * 56)

    if not output_folder.exists():
        logging.error("Output folder not found: %s", output_folder)
        print("Output folder not found.")
        return RetryResult(error="Output folder not found")

    try:
        mp4_path, desc_path = locate_video_and_description(output_folder)
    except FileNotFoundError as e:
        logging.error("Cannot retry upload: %s", e)
        print(f"Error: {e}")
        return RetryResult(error=str(e))

    print(f"Video file: {mp4_path.name}")
    print(f"Description: {desc_path.name}")
    print()

    try:
        title, description = uploader.parse_description_file(desc_path)
        print(f"Title: {title[:50]}..." if len(title) > 50 else f"Title: {title}")
        print()
    except Exception as e:
        logging.error("Failed to parse description file: %s", e)
        print(f"Error parsing description: {e}")
        return RetryResult(error=f"Error parsing description: {e}")

    if confirm and not _confirm("Upload this video to YouTube?", dry_run=False):
        print("Upload cancelled.")
        return RetryResult(cancelled=True)

    try:
        youtube = uploader.get_authenticated_service(expected_channel_id=config.youtube_channel_id)
        uploader.validate_channel_id(youtube, config.youtube_channel_id)
    except FileNotFoundError as e:
        logging.warning("YouTube credentials not set up: %s", e)
        print(f"YouTube credentials not set up: {e}")
        return RetryResult(error=str(e))
    except ValueError as e:
        # Auth or channel mismatch: keep the token, let the user sign in again deliberately.
        logging.warning("YouTube sign-in or channel check failed: %s", e)
        logging.warning("Token kept. Sign in again with the correct account, or verify youtube_channel_id in config.json.")
        print(f"YouTube sign-in or channel check failed: {e}")
        return RetryResult(needs_sign_in=True, error=str(e))
    except Exception as e:
        logging.error("YouTube sign-in failed: %s", e)
        print(f"YouTube sign-in failed: {e}")
        return RetryResult(error=str(e))

    try:
        uploader.upload_and_save_state(
            youtube,
            mp4_path,
            title,
            description,
            output_folder.name,
            config.state_path,
        )
    except Exception as e:
        logging.error("Upload failed: %s", e)
        print(f"Upload failed: {e}")
        return RetryResult(error=str(e))

    print()
    print("✅ Upload complete! Video is now on YouTube (private).")
    print()
    return RetryResult(uploaded=True)


FATE_ARCHIVE = "archive"
FATE_RECYCLE = "recycle"
FATE_RECYCLE_VIDEO = "recycle_video"
FATE_REMOVE_EMPTY_FOLDER = "remove_empty_folder"

GROUP_ARCHIVE = "archive"
GROUP_CLIPS = "clips"
GROUP_VIDEO = "video"
GROUP_METADATA = "metadata"
GROUP_FOLDER = "folder"


class PlanChanged(RuntimeError):
    """The output folder changed between plan_cleanup and apply_cleanup. Nothing was touched."""


class FolderNotConfirmed(RuntimeError):
    """apply_cleanup refused: the folder is not marked live on YouTube in state."""


@dataclass(frozen=True)
class PlannedAction:
    """One file or folder operation with its fate. dest is set only for archive moves."""
    fate: str
    path: Path
    group: str
    dest: Path | None = None


@dataclass(frozen=True)
class CleanupPlan:
    """What cleanup would do to one output folder. Building it changes nothing."""
    folder_name: str
    output_folder: Path
    archive_path: Path
    include_video: bool
    actions: tuple[PlannedAction, ...]
    skipped: tuple[str, ...]
    snapshot: frozenset[str]


@dataclass
class ApplyResult:
    done: list[PlannedAction] = field(default_factory=list)
    errors: list[tuple[PlannedAction, str]] = field(default_factory=list)


def _snapshot(folder: Path) -> frozenset[str]:
    """Relative paths of every file under folder. Used to detect changes between plan and apply."""
    if not folder.is_dir():
        return frozenset()
    return frozenset(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def _clip_files(clips_dir: Path) -> list[Path]:
    if not clips_dir.is_dir():
        return []
    return sorted(p for p in clips_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")


def _only_removed(folder: Path, removed: set[Path]) -> bool:
    return all(child in removed for child in folder.iterdir())


def _with_folder_fates(output_folder: Path, actions: list[PlannedAction]) -> list[PlannedAction]:
    """Add remove_empty_folder for clips/ and the output folder when the planned removals empty them."""
    kept = [a for a in actions if a.fate != FATE_REMOVE_EMPTY_FOLDER]
    removed = {a.path for a in kept if a.fate in (FATE_ARCHIVE, FATE_RECYCLE, FATE_RECYCLE_VIDEO)}
    clips_dir = output_folder / "clips"
    if clips_dir.is_dir() and _only_removed(clips_dir, removed):
        kept.append(PlannedAction(FATE_REMOVE_EMPTY_FOLDER, clips_dir, GROUP_FOLDER))
        removed.add(clips_dir)
    if output_folder.is_dir() and _only_removed(output_folder, removed):
        kept.append(PlannedAction(FATE_REMOVE_EMPTY_FOLDER, output_folder, GROUP_FOLDER))
    return kept


def plan_cleanup(output_folder: Path, archive_path: Path, include_video: bool = False) -> CleanupPlan:
    """Work out what cleanup would do with output_folder. Reads the folder; changes nothing.

    Fates:
    - archive: QUAD, PENTA, HEXA clips whose archive destination is free
    - recycle (group clips): every other clip in clips/
    - recycle (group metadata): *_description.txt and clips.json
    - recycle_video: compiled .mp4 files, only when include_video
    - remove_empty_folder: clips/ and the output folder, when the plan empties them
    Quad+ clips whose archive destination already exists are kept and listed in skipped.
    """
    actions: list[PlannedAction] = []
    skipped: list[str] = []

    for p in _clip_files(output_folder / "clips"):
        if _tier_from_name(p.name) in ARCHIVE_MIN_TIERS:
            dest = archive_path / p.stem.split("_")[0] / p.name
            if dest.exists():
                skipped.append(p.name)
            else:
                actions.append(PlannedAction(FATE_ARCHIVE, p, GROUP_ARCHIVE, dest))
        else:
            actions.append(PlannedAction(FATE_RECYCLE, p, GROUP_CLIPS))

    if include_video:
        for mp4 in sorted(output_folder.glob("*.mp4")):
            actions.append(PlannedAction(FATE_RECYCLE_VIDEO, mp4, GROUP_VIDEO))

    for txt in sorted(output_folder.glob("*_description.txt")):
        actions.append(PlannedAction(FATE_RECYCLE, txt, GROUP_METADATA))
    clips_json = output_folder / "clips.json"
    if clips_json.exists():
        actions.append(PlannedAction(FATE_RECYCLE, clips_json, GROUP_METADATA))

    return CleanupPlan(
        folder_name=output_folder.name,
        output_folder=output_folder,
        archive_path=archive_path,
        include_video=include_video,
        actions=tuple(_with_folder_fates(output_folder, actions)),
        skipped=tuple(skipped),
        snapshot=_snapshot(output_folder),
    )


def restrict_plan(plan: CleanupPlan, keep: Callable[[PlannedAction], bool]) -> CleanupPlan:
    """Return a copy of plan with only the actions keep() accepts. Folder fates are recomputed."""
    kept = [a for a in plan.actions if a.fate != FATE_REMOVE_EMPTY_FOLDER and keep(a)]
    return replace(plan, actions=tuple(_with_folder_fates(plan.output_folder, kept)))


def apply_cleanup(plan: CleanupPlan, state_path: Path | None = None) -> ApplyResult:
    """Carry out exactly the actions in plan.

    Refuses with FolderNotConfirmed unless state_path marks the folder live on YouTube.
    Raises PlanChanged, before touching anything, if a file appeared or vanished since
    planning or an archive destination now exists.
    """
    if state_path is None or not is_youtube_confirmed(load_state(state_path), plan.folder_name):
        raise FolderNotConfirmed(f"'{plan.folder_name}' is not marked live on YouTube; nothing was touched.")

    if _snapshot(plan.output_folder) != plan.snapshot:
        raise PlanChanged(f"Files in '{plan.folder_name}' changed since the plan was made; nothing was touched.")
    for a in plan.actions:
        if a.fate == FATE_ARCHIVE and a.dest.exists():
            raise PlanChanged(f"Archive destination appeared since planning: {a.dest.name}; nothing was touched.")

    result = ApplyResult()
    for a in plan.actions:
        if a.fate == FATE_REMOVE_EMPTY_FOLDER:
            try:
                a.path.rmdir()
                result.done.append(a)
                logging.info("Removed empty folder: %s", a.path.name)
            except OSError:
                logging.info("Left %s in place: not empty", a.path.name)
            continue
        try:
            if a.fate == FATE_ARCHIVE:
                a.dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(a.path), str(a.dest))
                logging.debug("Archived: %s -> %s", a.path.name, a.dest.parent)
            elif a.fate in (FATE_RECYCLE, FATE_RECYCLE_VIDEO):
                send2trash(str(a.path))
                logging.debug("Sent to Recycle Bin: %s", a.path.name)
            else:
                raise ValueError(f"unknown fate: {a.fate}")
            result.done.append(a)
        except Exception as e:
            logging.error("Failed to %s %s: %s", a.fate, a.path.name, e)
            result.errors.append((a, str(e)))
    return result


def _describe(a: PlannedAction) -> str:
    if a.fate == FATE_ARCHIVE:
        return f"  [archive] {a.path.name} -> {a.dest.parent.parent.name}/{a.dest.parent.name}/"
    if a.fate == FATE_RECYCLE_VIDEO:
        return f"  [recycle_video] {a.path.name} ({_fmt_size(a.path)})"
    if a.fate == FATE_REMOVE_EMPTY_FOLDER:
        return f"  [remove_empty_folder] {a.path.name}/"
    return f"  [recycle] {a.path.name}"


def run_cleanup(
    output_folder: Path,
    archive_path: Path,
    state_path: Path | None = None,
    dry_run: bool = False,
) -> None:
    """
    Interactive post-YouTube cleanup for one output folder. A terminal wrapper over
    plan_cleanup and apply_cleanup.

    Parameters
    ----------
    output_folder : path to a compiled output folder (e.g. Output/THOR_FEB-MAR_2026/)
    archive_path  : path to the ClipArchive folder
    state_path    : path to state.json; required for a live run (it records the YouTube-confirmed
                    status that apply_cleanup checks)
    dry_run       : if True, print the plan and return. No prompts, no state writes, no file changes.

    Steps (live run):
    0. Confirm the video is live on YouTube and record it in state.
    1. Quad+ clips -> ask before moving them to archive_path.
    2. Other clips -> ask before sending them to the Recycle Bin.
    3. Compiled .mp4 -> ask before sending it to the Recycle Bin.
    Description and clips.json files are part of the plan and are removed with it.
    Nothing moves until every prompt has been answered.
    """
    if not output_folder.exists():
        logging.error("Output folder not found: %s", output_folder)
        return

    folder_name = output_folder.name
    plan = plan_cleanup(output_folder, archive_path, include_video=True)

    if dry_run:
        print("[DRY RUN] No files will be moved or deleted, and no state is written.\n")
        print(f"Cleanup plan: {folder_name}")
        print("=" * 56)
        for a in plan.actions:
            print(_describe(a))
        for name in plan.skipped:
            print(f"  [kept] {name} - already in archive")
        return

    if state_path is None:
        logging.error("Cleanup needs state_path to record the YouTube confirmation; nothing changed.")
        print("Cleanup needs a state file to record the YouTube confirmation. Nothing changed.")
        return

    # Step 0: confirm video is live on YouTube before proceeding
    state = load_state(state_path)
    if not is_youtube_confirmed(state, folder_name):
        print(f"\nBefore cleaning up '{folder_name}':")
        if not _confirm("Is this video live on YouTube?"):
            print("Cleanup aborted - confirm on YouTube first.")
            return
        state = mark_youtube_confirmed(state, folder_name)
        save_state(state, state_path)
        logging.info("Marked '%s' as YouTube-confirmed in state log.", folder_name)

    print()
    print(f"Cleanup: {folder_name}")
    print("=" * 56)

    archive_actions = [a for a in plan.actions if a.fate == FATE_ARCHIVE]
    clip_actions = [a for a in plan.actions if a.fate == FATE_RECYCLE and a.group == GROUP_CLIPS]
    video_actions = [a for a in plan.actions if a.fate == FATE_RECYCLE_VIDEO]

    if not (archive_actions or clip_actions or plan.skipped):
        print("clips/ folder is empty or missing - nothing to clean up here.")

    # ── Step 1: archive Quad+ clips ──────────────────────────────────────────
    approve_archive = False
    if archive_actions:
        print(f"\n{len(archive_actions)} Quad+ clip(s) to archive -> {archive_path.name}/:")
        for a in archive_actions:
            print(f"  {a.path.name}")
        approve_archive = _confirm("\nMove these to ClipArchive?")
        if not approve_archive:
            print("Skipped archiving.")
    else:
        print("\n(no Quad+ clips to archive)")
    for name in plan.skipped:
        print(f"  [kept] {name} - already in archive")

    # ── Step 2: send remaining clips to the Recycle Bin ──────────────────────
    approve_clips = False
    if clip_actions:
        print(f"\n{len(clip_actions)} remaining clip(s) to delete:")
        for a in clip_actions:
            print(f"  {a.path.name}")
        approve_clips = _confirm("\nSend these clips to the Recycle Bin?")
        if not approve_clips:
            print("Skipped clip deletion.")
    else:
        print("\n(no remaining clips to delete)")

    # ── Step 3: compiled .mp4 ────────────────────────────────────────────────
    approved_videos: set[Path] = set()
    if video_actions:
        for a in video_actions:
            print(f"\nCompiled video: {a.path.name}  ({_fmt_size(a.path)})")
            if _confirm("Send this file to Recycle Bin to free disk space?"):
                approved_videos.add(a.path)
            else:
                print("Kept compiled video.")
    else:
        print("\n(no compiled .mp4 found in output folder)")

    # Description and clips.json go only when every clip leaves clips/: the description
    # is what a later upload retry reads, so it stays while any clip stays.
    all_clips_go = (
        (approve_archive or not archive_actions)
        and (approve_clips or not clip_actions)
        and not plan.skipped
    )
    selected = restrict_plan(plan, keep=lambda a: (
        (a.fate == FATE_ARCHIVE and approve_archive)
        or (a.fate == FATE_RECYCLE and a.group == GROUP_CLIPS and approve_clips)
        or (a.fate == FATE_RECYCLE_VIDEO and a.path in approved_videos)
        or (a.group == GROUP_METADATA and all_clips_go)
    ))

    try:
        result = apply_cleanup(selected, state_path)
    except (FolderNotConfirmed, PlanChanged) as e:
        logging.error("Cleanup stopped: %s", e)
        print(f"Cleanup stopped: {e}")
        return

    for a, err in result.errors:
        print(f"  [error] {a.path.name}: {err}")
    if approve_archive:
        n = sum(1 for a in result.done if a.fate == FATE_ARCHIVE)
        print(f"{n}/{len(archive_actions)} clip(s) archived.")
    if approve_clips:
        n = sum(1 for a in result.done if a.fate == FATE_RECYCLE and a.group == GROUP_CLIPS)
        print(f"{n}/{len(clip_actions)} clip(s) sent to Recycle Bin.")
    for a in result.done:
        if a.fate == FATE_RECYCLE_VIDEO:
            print(f"Sent to Recycle Bin: {a.path.name}")

    print()
    print("Cleanup complete.")
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

    print(f"\n🔄 Uncompile: {output_folder.name}")
    print("=" * 56)
    print(f"Restoring {len(clip_files)} clip(s) -> Highlights/{char_name}/")
    for p in clip_files:
        print(f"  {p.name}")

    mp4s = list(output_folder.glob("*.mp4"))
    if mp4s:
        sizes = ", ".join(_fmt_size(p) for p in mp4s)
        print(f"\n🗑️  Compiled video will be deleted: {', '.join(p.name for p in mp4s)}  ({sizes})")

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

    print(f"✅ {restored}/{len(clip_files)} clip(s) restored to Highlights/{char_name}/")

    # Delete compiled video(s)
    for mp4 in mp4s:
        try:
            send2trash(str(mp4))
            logging.debug("Sent compiled video to Recycle Bin: %s", mp4.name)
        except Exception as e:
            logging.error("Failed to send compiled video to Recycle Bin %s: %s", mp4.name, e)

    # Delete description file(s)
    for txt in output_folder.glob("*_description.txt"):
        try:
            send2trash(str(txt))
            logging.debug("Sent description to Recycle Bin: %s", txt.name)
        except Exception as e:
            logging.error("Failed to send description to Recycle Bin %s: %s", txt.name, e)

    # Delete clips.json manifest (written during compile)
    clips_json = output_folder / "clips.json"
    if clips_json.exists():
        try:
            send2trash(str(clips_json))
            logging.debug("Sent clips.json to Recycle Bin: %s", clips_json.name)
        except Exception as e:
            logging.error("Failed to send clips.json to Recycle Bin: %s", e)

    # Remove output folder and all remaining contents (including clips/ dir)
    try:
        shutil.rmtree(str(output_folder))
        logging.info("Removed output folder: %s", output_folder.name)
    except OSError as e:
        logging.error("Failed to remove output folder: %s", e)

    # Clear YouTube-confirmed state if present
    if state_path:
        state = load_state(state_path)
        folder_name = output_folder.name
        if is_youtube_confirmed(state, folder_name):
            state.get("youtube_confirmed", {}).pop(folder_name, None)
            save_state(state, state_path)
            logging.info("Cleared YouTube-confirmed status for '%s'.", folder_name)

    print("\n🎬 Uncompile complete. Re-run to compile a clean batch!")
    print()
