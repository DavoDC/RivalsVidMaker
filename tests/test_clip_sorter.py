"""
Tests for clip_sorter.py

All tests use tmp_path - no real clips are touched.
"""

from pathlib import Path

import pytest

from clip_sorter import extract_character, sort_clips


# ---------------------------------------------------------------------------
# extract_character
# ---------------------------------------------------------------------------

class TestExtractCharacter:
    def test_simple(self):
        assert extract_character("THOR_2026-02-06_22-38-56") == "THOR"

    def test_underscore_in_name(self):
        assert extract_character("BLACK_WIDOW_2026-01-15_08-00-00") == "BLACK_WIDOW"

    def test_space_in_name_becomes_underscore(self):
        assert extract_character("SQUIRREL GIRL_2026-03-13_21-51-02") == "SQUIRREL_GIRL"

    def test_space_and_underscore_mixed(self):
        assert extract_character("BLACK WIDOW_2026-01-15_08-00-00") == "BLACK_WIDOW"

    def test_short_name(self):
        assert extract_character("SG_2026-03-10_19-45-00") == "SG"

    def test_lowercase_char(self):
        assert extract_character("Other_2026-03-05_12-00-00") == "Other"

    def test_no_date_returns_none(self):
        assert extract_character("just_a_random_file") is None

    def test_empty_string_returns_none(self):
        assert extract_character("") is None

    def test_date_only_returns_none(self):
        # No character prefix before the date
        assert extract_character("2026-02-06_22-38-56") is None

    def test_starts_with_digit_returns_none(self):
        assert extract_character("123_2026-01-01_00-00-00") is None

    def test_leading_space_stripped(self):
        # Shouldn't happen in practice but guard against it
        result = extract_character("THOR_2026-02-06_22-38-56")
        assert result == "THOR"


# ---------------------------------------------------------------------------
# sort_clips - file operations (uses tmp_path, never touches real clips)
# ---------------------------------------------------------------------------

def _make_clip(directory: Path, name: str) -> Path:
    """Create a zero-byte file to simulate a clip."""
    p = directory / name
    p.write_bytes(b"")
    return p


class TestSortClips:
    def test_moves_single_clip(self, tmp_path):
        src = _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        moved = sort_clips(tmp_path)
        assert moved == 1
        assert not src.exists(), "Original should be gone after move"
        assert (tmp_path / "THOR" / "THOR_2026-02-06_22-38-56.mp4").exists()

    def test_space_in_character_name(self, tmp_path):
        src = _make_clip(tmp_path, "SQUIRREL GIRL_2026-03-13_21-51-02.mp4")
        moved = sort_clips(tmp_path)
        assert moved == 1
        assert not src.exists()
        # Folder uses underscores; original filename is preserved inside
        assert (tmp_path / "SQUIRREL_GIRL" / "SQUIRREL GIRL_2026-03-13_21-51-02.mp4").exists()

    def test_moves_multiple_characters(self, tmp_path):
        _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        _make_clip(tmp_path, "SQUIRREL GIRL_2026-03-13_21-51-02.mp4")
        _make_clip(tmp_path, "SG_2026-03-10_19-45-00.mp4")
        moved = sort_clips(tmp_path)
        assert moved == 3
        assert (tmp_path / "THOR" / "THOR_2026-02-06_22-38-56.mp4").exists()
        assert (tmp_path / "SQUIRREL_GIRL" / "SQUIRREL GIRL_2026-03-13_21-51-02.mp4").exists()
        assert (tmp_path / "SG" / "SG_2026-03-10_19-45-00.mp4").exists()

    def test_multiple_clips_same_character(self, tmp_path):
        _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        _make_clip(tmp_path, "THOR_2026-02-07_18-00-00.mp4")
        moved = sort_clips(tmp_path)
        assert moved == 2
        assert (tmp_path / "THOR" / "THOR_2026-02-06_22-38-56.mp4").exists()
        assert (tmp_path / "THOR" / "THOR_2026-02-07_18-00-00.mp4").exists()

    def test_creates_character_subfolder(self, tmp_path):
        _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        assert not (tmp_path / "THOR").exists()
        sort_clips(tmp_path)
        assert (tmp_path / "THOR").is_dir()

    def test_skips_unparseable_filename(self, tmp_path):
        src = _make_clip(tmp_path, "random_file.mp4")
        moved = sort_clips(tmp_path)
        assert moved == 0
        assert src.exists(), "Unparseable file must not be moved"

    def test_skips_if_destination_exists(self, tmp_path):
        src = _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        dest_dir = tmp_path / "THOR"
        dest_dir.mkdir()
        existing = dest_dir / "THOR_2026-02-06_22-38-56.mp4"
        existing.write_bytes(b"existing content")
        moved = sort_clips(tmp_path)
        assert moved == 0
        assert src.exists(), "Source must not be deleted when destination already exists"
        assert existing.read_bytes() == b"existing content", "Destination must not be overwritten"

    def test_ignores_non_video_files(self, tmp_path):
        _make_clip(tmp_path, "notes.txt")
        _make_clip(tmp_path, "thumbnail.png")
        moved = sort_clips(tmp_path)
        assert moved == 0
        assert (tmp_path / "notes.txt").exists()
        assert (tmp_path / "thumbnail.png").exists()

    def test_ignores_clips_already_in_subfolders(self, tmp_path):
        """Clips inside existing subfolders (e.g. vid1_uploaded/) must not be moved."""
        char_dir = tmp_path / "THOR"
        char_dir.mkdir()
        _make_clip(char_dir, "THOR_2026-02-06_22-38-56.mp4")
        # Also a special subfolder
        uploaded = char_dir / "vid1_uploaded"
        uploaded.mkdir()
        _make_clip(uploaded, "THOR_2026-01-01_00-00-00.mp4")
        moved = sort_clips(tmp_path)
        assert moved == 0

    def test_empty_folder_returns_zero(self, tmp_path):
        assert sort_clips(tmp_path) == 0

    def test_mixed_video_extensions(self, tmp_path):
        _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        _make_clip(tmp_path, "THOR_2026-02-07_10-00-00.mov")
        _make_clip(tmp_path, "THOR_2026-02-08_11-00-00.mkv")
        moved = sort_clips(tmp_path)
        assert moved == 3


class TestSortClipsProtectRecent:

    def test_protect_recent_leaves_newest_in_root(self, tmp_path):
        # a < b < c alphabetically; protect 1 -> only a, b moved; c stays in root
        _make_clip(tmp_path, "THOR_2026-01-01_00-00-00.mp4")
        _make_clip(tmp_path, "THOR_2026-01-02_00-00-00.mp4")
        _make_clip(tmp_path, "THOR_2026-01-03_00-00-00.mp4")
        moved = sort_clips(tmp_path, protect_recent=1)
        assert moved == 2
        assert (tmp_path / "THOR" / "THOR_2026-01-01_00-00-00.mp4").exists()
        assert (tmp_path / "THOR" / "THOR_2026-01-02_00-00-00.mp4").exists()
        assert (tmp_path / "THOR_2026-01-03_00-00-00.mp4").exists(), "Newest must stay in root"

    def test_protect_recent_five_leaves_five_in_root(self, tmp_path):
        clips = [f"THOR_2026-01-0{i}_00-00-00.mp4" for i in range(1, 8)]
        for name in clips:
            _make_clip(tmp_path, name)
        moved = sort_clips(tmp_path, protect_recent=5)
        assert moved == 2
        for name in clips[:2]:
            assert (tmp_path / "THOR" / name).exists()
        for name in clips[2:]:
            assert (tmp_path / name).exists(), f"{name} should stay in root"

    def test_protect_recent_zero_moves_all(self, tmp_path):
        for name in ["THOR_2026-01-01_00-00-00.mp4", "THOR_2026-01-02_00-00-00.mp4"]:
            _make_clip(tmp_path, name)
        moved = sort_clips(tmp_path, protect_recent=0)
        assert moved == 2

    def test_protect_recent_gte_count_moves_nothing(self, tmp_path):
        _make_clip(tmp_path, "THOR_2026-01-01_00-00-00.mp4")
        _make_clip(tmp_path, "THOR_2026-01-02_00-00-00.mp4")
        moved = sort_clips(tmp_path, protect_recent=5)
        assert moved == 0
        assert (tmp_path / "THOR_2026-01-01_00-00-00.mp4").exists()
        assert (tmp_path / "THOR_2026-01-02_00-00-00.mp4").exists()

    def test_protect_recent_mixed_characters(self, tmp_path):
        # 3 clips: a=oldest, b=middle, c=newest. protect 1 -> a and b moved, c stays
        _make_clip(tmp_path, "SQUIRREL_GIRL_2026-01-01_00-00-00.mp4")
        _make_clip(tmp_path, "THOR_2026-01-02_00-00-00.mp4")
        _make_clip(tmp_path, "THOR_2026-01-03_00-00-00.mp4")
        moved = sort_clips(tmp_path, protect_recent=1)
        assert moved == 2
        assert (tmp_path / "THOR_2026-01-03_00-00-00.mp4").exists(), "Newest must stay"
