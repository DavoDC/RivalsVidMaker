"""
menu.py - Two-level arrow-key action picker using questionary.

Level 1: pick a folder (Highlights / Output / Archive / Quit)
Level 2: pick a context-specific action within that folder
"""

from pathlib import Path

import questionary


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def _char_label(name: str, clip_count: int, duration_str: str, batch_count: int, status: str) -> str:
    """Build a Level-2 label for a character folder."""
    return name


def _folder1_label(folder_name: str, summary: str = "") -> str:
    """Build a Level-1 label for a top-level folder."""
    if summary:
        return f"{folder_name}   {summary}"
    return folder_name


def _output_label(row: dict, yt_confirmed: bool) -> str:
    """Build a Level-2 label for an output folder row."""
    name = row["name"]
    age = row.get("age", "?")
    if not yt_confirmed:
        return f"{name}  ({age})  - check it's live on YT before selecting (will delete compiled video)"
    if row.get("has_clips"):
        return f"{name}  ({age})  - cleanup ready (archive Quad+, delete rest)"
    return f"{name}  ({age})"


# ---------------------------------------------------------------------------
# pick_action
# ---------------------------------------------------------------------------

def pick_action(
    char_folders: list,
    summaries: list,
    output_rows: list,
    state: dict,
    target_batch_seconds: int,
    output_path: Path | None = None,
    archive_path: Path | None = None,
) -> dict:
    """
    Two-level interactive menu. Returns a dict with a 'type' key:
      {'type': 'quit'}
      {'type': 'compile', 'folder': Path}
      {'type': 'preprocess'}
      {'type': 'cleanup', 'folder': Path}
    """
    from state import is_youtube_confirmed

    while True:
        # --- Level 1: pick folder ---
        level1_choices = _build_level1_choices(char_folders, summaries, output_rows, state,
                                               target_batch_seconds)
        answer = questionary.select(
            "What would you like to do?",
            choices=level1_choices,
        ).ask()

        if answer is None or answer == "quit":
            return {"type": "quit"}

        # --- Level 2: pick action ---
        if answer == "highlights":
            result = _highlights_submenu(char_folders, summaries, target_batch_seconds)
            if result is not None:
                return result
            # None = back, loop to Level 1

        elif answer == "output":
            result = _output_submenu(output_rows, state, output_path)
            if result is not None:
                return result

        elif answer == "archive":
            _archive_view(archive_path)
        # "back" - loop back


def _build_level1_choices(char_folders, summaries, output_rows, state, target_batch_seconds):
    from state import is_youtube_confirmed

    # Highlights summary
    ready = []
    too_short = []
    for folder, (count, dur) in zip(char_folders, summaries):
        if dur >= target_batch_seconds:
            ready.append(folder.name)
        elif dur > 0:
            too_short.append(folder.name)

    if ready:
        h_detail = f"{', '.join(ready)} ready"
    elif too_short:
        h_detail = "no characters ready yet"
    else:
        h_detail = "no clips"

    # Output summary
    o_detail = f"{len(output_rows)} folder(s) waiting" if output_rows else "nothing to clean up"

    return [
        questionary.Choice(f"Compile a new highlights video  ({h_detail})", value="highlights"),
        questionary.Choice(f"Clean up a completed output folder  ({o_detail})", value="output"),
        questionary.Choice("Browse the archive", value="archive"),
        questionary.Choice("Quit", value="quit"),
    ]


def _highlights_submenu(char_folders, summaries, target_batch_seconds):
    """Returns action dict or None (back)."""
    choices = []
    for folder, (count, dur) in zip(char_folders, summaries):
        from pipeline import _fmt_duration, _menu_status
        dur_str = _fmt_duration(dur) if count else "-"
        batches = max(1, int(dur / target_batch_seconds)) if dur >= target_batch_seconds else 0
        status = _menu_status(dur, target_batch_seconds)
        label = _char_label(folder.name, count, dur_str, batches, status)
        choices.append(questionary.Choice(label, value=str(folder)))

    choices.append(questionary.Choice("Pre-process all clips (warm KO cache)", value="preprocess"))
    choices.append(questionary.Choice("Back", value="back"))

    answer = questionary.select(
        "Which character do you want to compile?",
        choices=choices,
    ).ask()

    if answer is None or answer == "back":
        return None
    if answer == "preprocess":
        return {"type": "preprocess"}
    return {"type": "compile", "folder": Path(answer)}


def _archive_view(archive_path: Path | None) -> None:
    """Show archive contents (read-only) then return to menu."""
    if not archive_path or not archive_path.exists():
        print("\n  Archive folder is empty (or path not configured).")
    else:
        from clip_scanner import VIDEO_EXTS
        clips = [p for p in archive_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
        if clips:
            print(f"\n  Archive: {len(clips)} clip(s)")
            for p in sorted(clips):
                print(f"    {p.name}")
        else:
            print("\n  Archive folder is empty.")
    input("  Press Enter to go back...")


def _output_submenu(output_rows, state, output_path):
    """Returns action dict or None (back)."""
    from state import is_youtube_confirmed

    if not output_rows:
        return None

    choices = []
    for row in output_rows:
        yt_confirmed = is_youtube_confirmed(state, row["name"])
        label = _output_label(row, yt_confirmed)
        choices.append(questionary.Choice(label, value=row["name"]))

    choices.append(questionary.Choice("Back", value="back"))

    answer = questionary.select(
        "Which output folder?",
        choices=choices,
    ).ask()

    if answer is None or answer == "back":
        return None

    folder = (output_path / answer) if output_path else Path(answer)

    # Second submenu: choose action for this output folder
    action_answer = questionary.select(
        f"Action for {answer}?",
        choices=[
            questionary.Choice("Clean up (archive Quad+, delete rest)", value="cleanup"),
            questionary.Choice("Uncompile (restore clips to Highlights, discard output)", value="uncompile"),
            questionary.Choice("Back", value="back"),
        ],
    ).ask()

    if action_answer is None or action_answer == "back":
        return None

    return {"type": action_answer, "folder": folder}
