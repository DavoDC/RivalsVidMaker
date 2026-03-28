"""
state.py - Persistent state log for output folders.

Tracks per-folder state (YouTube confirmed, etc.) in data/state.json.
This is local-only state - not committed to git.

Schema:
{
  "output_folders": {
    "thor_vid1": {
      "youtube_confirmed": true,
      "confirmed_at": "2026-03-28T20:00:00+00:00"
    }
  }
}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


def _empty() -> dict:
    return {"output_folders": {}}


def load(state_path: Path) -> dict:
    """Load state from disk. Returns empty state if file is missing or corrupt."""
    if not state_path.exists():
        return _empty()
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logging.warning("Could not read state file %s: %s", state_path, e)
        return _empty()


def save(state: dict, state_path: Path) -> None:
    """Write state to disk, creating parent directories if needed."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_youtube_confirmed(state: dict, folder_name: str) -> bool:
    """Return True if the output folder has been marked as live on YouTube."""
    return state.get("output_folders", {}).get(folder_name, {}).get("youtube_confirmed", False)


def mark_youtube_confirmed(state: dict, folder_name: str) -> dict:
    """Mark an output folder as confirmed live on YouTube. Returns updated state."""
    if "output_folders" not in state:
        state["output_folders"] = {}
    state["output_folders"][folder_name] = {
        "youtube_confirmed": True,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    return state
