"""
Integration tests for multi-step pipeline interactions.

These tests run multiple pipeline functions in sequence on the same filesystem
state, catching bugs that unit tests miss because they test functions in isolation.

Golden rule: if a feature spans multiple pipeline steps, there must be an
integration test that runs those steps in order and verifies the end result.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

from clip_scanner import scan_folder, Clip
from clip_sorter import sort_clips
from batcher import Batch
from pipeline import _collect_highlights
from config import Config


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


class TestCollectHighlightsWithRenamedClips:
    """
    Test that _collect_highlights correctly handles clip renaming.

    Clips are renamed after KO scan (e.g., THOR_..._QUAD.mp4), but the offsets
    dict was built with original filenames. This test verifies that offsets is
    correctly updated so lookups don't fail with KeyError.

    Regression test for: KeyError on renamed clips after KO scan (TIER 0 bug).
    """

    def test_collect_highlights_with_renamed_clips(self, tmp_path):
        """Clips renamed with tier suffix should still resolve in offsets dict."""
        # Create clip files
        clip1_path = tmp_path / "THOR_2026-02-06_22-38-56.mp4"
        clip2_path = tmp_path / "THOR_2026-02-07_18-00-00.mp4"
        _make_clip(tmp_path, clip1_path.name)
        _make_clip(tmp_path, clip2_path.name)

        # Create batch
        clips = [
            Clip(path=clip1_path, duration=30.0),
            Clip(path=clip2_path, duration=40.0),
        ]
        batch = Batch(number=1, clips=clips)

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.ffmpeg = Path("ffmpeg")
        mock_config.tesseract = Path("tesseract")
        mock_config.cache_dir = tmp_path / "cache"

        # Mock ko_detect functions to simulate KO detection with tier results
        def mock_scan_one(clip_path: str, clip_name: str):
            # Simulate KO results: first clip is QUAD, second is DOUBLE
            if "2026-02-06" in clip_name:
                return (clip_name, {"tier": "QUAD", "start_ts": 5.0, "max_ts": 8.0}, 1.0, False)
            else:
                return (clip_name, {"tier": "DOUBLE", "start_ts": 10.0, "max_ts": 13.0}, 1.0, False)

        with patch("pipeline._ko_scan_one", side_effect=mock_scan_one):
            with patch("pipeline.ko_detect.configure"):
                with patch("pipeline.ko_detect.N_WORKERS", 2):
                    with patch("pipeline.ko_detect.TIERS", ["DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]):
                        with patch("pipeline.ko_detect.TIER_RANK", {"DOUBLE": 1, "TRIPLE": 2, "QUAD": 3, "PENTA": 4, "HEXA": 5}):
                            with patch("pipeline.ko_detect.REPORT_MIN_TIER", "QUAD"):
                                with patch("pipeline.ko_detect.NULL_RESULT_SUFFIX", "UNKNOWN"):
                                    # Call _collect_highlights - should NOT raise KeyError
                                    highlights, clip_tiers = _collect_highlights(batch, mock_config)

        # Verify results
        # clip_tiers should have NEW filenames (with tier suffixes)
        expected_clip1_name = "THOR_2026-02-06_22-38-56_QUAD.mp4"
        expected_clip2_name = "THOR_2026-02-07_18-00-00_DOUBLE.mp4"
        assert expected_clip1_name in clip_tiers, "Renamed clip1 must be in clip_tiers"
        assert expected_clip2_name in clip_tiers, "Renamed clip2 must be in clip_tiers"
        assert clip_tiers[expected_clip1_name] == "QUAD"
        assert clip_tiers[expected_clip2_name] == "DOUBLE"

        # Verify highlights (only QUAD+ tiers reported)
        assert len(highlights) == 1, "Only QUAD clips should be in highlights"
        video_start, video_max, tier, clip_name = highlights[0]
        assert clip_name == expected_clip1_name
        assert tier == "QUAD"
        # QUAD clip: offset=0, start_ts=5 -> video_start=5; offset=0, max_ts=8 -> video_max=8
        assert video_start == 5.0
        assert video_max == 8.0

        # Verify files were actually renamed on disk
        assert not clip1_path.exists(), "Original clip1 path should not exist after rename"
        assert not clip2_path.exists(), "Original clip2 path should not exist after rename"
        assert (tmp_path / expected_clip1_name).exists(), "Renamed clip1 should exist"
        assert (tmp_path / expected_clip2_name).exists(), "Renamed clip2 should exist"
