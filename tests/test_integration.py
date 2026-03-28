"""
Integration tests for multi-step pipeline interactions.

These tests run multiple pipeline functions in sequence on the same filesystem
state, catching bugs that unit tests miss because they test functions in isolation.

Golden rule: if a feature spans multiple pipeline steps, there must be an
integration test that runs those steps in order and verifies the end result.
"""

from pathlib import Path
from unittest.mock import patch

from clip_scanner import scan_folder
from clip_sorter import sort_clips


def _make_clip(directory: Path, name: str) -> Path:
    p = directory / name
    p.write_bytes(b"")
    return p


class TestProtectRecentClipsEndToEnd:
    """
    Golden path: sort_clips runs first, scan_folder runs second.
    Protected clips must survive both steps untouched.

    This test class exists to catch the bug where protection was only
    in scan_folder (step 2), so sort_clips (step 1) moved protected
    files before protection ever ran.
    """

    def test_protected_clips_not_moved_by_sort_and_not_scanned(self, tmp_path):
        """Full pipeline: 7 clips in root, protect 2 newest. Only 5 get sorted and scanned."""
        clips = [f"THOR_2026-01-0{i}_00-00-00.mp4" for i in range(1, 8)]
        for name in clips:
            _make_clip(tmp_path, name)

        # Step 1: sort (pipeline step 1)
        moved = sort_clips(tmp_path, protect_recent=2)

        # 5 oldest moved to THOR/, 2 newest still in root
        assert moved == 5
        assert (tmp_path / "THOR_2026-01-06_00-00-00.mp4").exists(), "6th clip must stay in root"
        assert (tmp_path / "THOR_2026-01-07_00-00-00.mp4").exists(), "7th clip must stay in root"
        for name in clips[:5]:
            assert (tmp_path / "THOR" / name).exists(), f"{name} should be in THOR/"

        # Step 2: scan character subfolder (pipeline step 4)
        with patch("clip_scanner.probe_duration", return_value=30.0):
            scanned = scan_folder(tmp_path / "THOR", Path("ffprobe"))

        # Only the 5 sorted clips are visible to the scanner
        assert len(scanned) == 5
        scanned_names = {c.name for c in scanned}
        assert "THOR_2026-01-06_00-00-00.mp4" not in scanned_names
        assert "THOR_2026-01-07_00-00-00.mp4" not in scanned_names

    def test_zero_protection_sorts_and_scans_everything(self, tmp_path):
        """With protect_recent=0, all clips are sorted and all are available to scan."""
        clips = [f"THOR_2026-01-0{i}_00-00-00.mp4" for i in range(1, 6)]
        for name in clips:
            _make_clip(tmp_path, name)

        moved = sort_clips(tmp_path, protect_recent=0)
        assert moved == 5

        with patch("clip_scanner.probe_duration", return_value=30.0):
            scanned = scan_folder(tmp_path / "THOR", Path("ffprobe"))

        assert len(scanned) == 5

    def test_protect_all_clips_nothing_sorted_nothing_scanned(self, tmp_path):
        """Protect count >= total clips: nothing moves, character folder never created."""
        clips = [f"THOR_2026-01-0{i}_00-00-00.mp4" for i in range(1, 4)]
        for name in clips:
            _make_clip(tmp_path, name)

        moved = sort_clips(tmp_path, protect_recent=5)
        assert moved == 0
        assert not (tmp_path / "THOR").exists(), "Character folder must not be created"
        for name in clips:
            assert (tmp_path / name).exists(), f"{name} must still be in root"

    def test_protected_clips_are_the_newest_not_the_oldest(self, tmp_path):
        """Confirm it is the NEWEST clips protected, not oldest."""
        oldest = "THOR_2026-01-01_00-00-00.mp4"
        newest = "THOR_2026-12-31_00-00-00.mp4"
        _make_clip(tmp_path, oldest)
        _make_clip(tmp_path, newest)

        sort_clips(tmp_path, protect_recent=1)

        assert (tmp_path / "THOR" / oldest).exists(), "Oldest must be sorted"
        assert (tmp_path / newest).exists(), "Newest must stay in root"
