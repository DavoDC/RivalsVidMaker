"""
Tests for cleanup.py - interactive post-YouTube output folder cleanup.

All tests use tmp_path; no real filesystem paths are required.
User prompts are patched out so tests are fully non-interactive.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from cleanup import _tier_from_name, _fmt_size, run_cleanup


# ── _tier_from_name ───────────────────────────────────────────────────────────

class TestTierFromName:

    def test_quad(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_QUAD.mp4") == "QUAD"

    def test_penta(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_PENTA.mp4") == "PENTA"

    def test_hexa(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_HEXA.mp4") == "HEXA"

    def test_triple(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_TRIPLE.mp4") == "TRIPLE"

    def test_no_tier(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56.mp4") is None

    def test_case_insensitive(self):
        # The regex is case-insensitive; result is always upper
        assert _tier_from_name("THOR_2026-02-06_quad.mp4") == "QUAD"


# ── _fmt_size ─────────────────────────────────────────────────────────────────

class TestFmtSize:

    def test_returns_mb_string(self, tmp_path):
        f = tmp_path / "video.mp4"
        f.write_bytes(b"x" * 1024 * 1024)  # exactly 1 MB
        result = _fmt_size(f)
        assert "MB" in result
        assert "1.0" in result

    def test_missing_file_returns_unknown(self, tmp_path):
        assert _fmt_size(tmp_path / "missing.mp4") == "unknown size"


# ── run_cleanup ───────────────────────────────────────────────────────────────

def _make_output_folder(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a standard output folder structure and return key paths."""
    out = tmp_path / "THOR_Feb-Mar_2026"
    out.mkdir()
    clips_dir = out / "clips"
    clips_dir.mkdir()
    mp4 = out / "THOR_Feb-Mar_2026.mp4"
    mp4.write_bytes(b"compiled video")
    return out, clips_dir, mp4, tmp_path / "ClipArchive"


class TestRunCleanupMissingFolder:

    def test_nonexistent_folder_logs_error(self, tmp_path, caplog):
        import logging
        archive = tmp_path / "ClipArchive"
        with caplog.at_level(logging.ERROR):
            run_cleanup(tmp_path / "MISSING", archive)
        assert any("not found" in r.message.lower() for r in caplog.records)


class TestRunCleanupArchiving:

    def test_quad_clip_moved_to_archive_when_confirmed(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad_clip = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad_clip.write_bytes(b"quad data")

        # Confirm YT, confirm archive, decline delete, decline video delete
        with patch("builtins.input", side_effect=["y", "y", "n", "n"]):
            run_cleanup(out, archive)

        assert (archive / "THOR" / quad_clip.name).exists()
        assert not quad_clip.exists()

    def test_quad_clip_stays_when_archiving_declined(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad_clip = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad_clip.write_bytes(b"quad data")

        # Confirm YT, decline archive, decline delete, decline video delete
        with patch("builtins.input", side_effect=["y", "n", "n", "n"]):
            run_cleanup(out, archive)

        assert quad_clip.exists()
        assert not archive.exists()

    def test_archive_skips_existing_destination(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad_clip = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad_clip.write_bytes(b"source")
        archive.mkdir()
        existing = archive / quad_clip.name
        existing.write_bytes(b"already archived")

        with patch("builtins.input", side_effect=["y", "y", "n", "n"]):
            run_cleanup(out, archive)

        # Existing archive file is not overwritten
        assert existing.read_bytes() == b"already archived"


class TestRunCleanupDeletion:

    def test_remaining_clips_deleted_when_confirmed(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        clip = clips_dir / "THOR_2026-02-06_22-38-56.mp4"
        clip.write_bytes(b"no tier")

        # Confirm YT, no quad+ to archive, confirm delete, decline video delete
        with patch("builtins.input", side_effect=["y", "y", "n"]):
            run_cleanup(out, archive)

        assert not clip.exists()

    def test_remaining_clips_kept_when_deletion_declined(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        clip = clips_dir / "THOR_2026-02-06_22-38-56.mp4"
        clip.write_bytes(b"no tier")

        with patch("builtins.input", side_effect=["y", "n", "n"]):
            run_cleanup(out, archive)

        assert clip.exists()

    def test_quad_plus_not_in_remaining_after_archive(self, tmp_path):
        """After archiving, Quad+ clips must not appear in the deletion list."""
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad.write_bytes(b"quad")
        plain = clips_dir / "THOR_2026-02-07_18-00-00.mp4"
        plain.write_bytes(b"plain")

        # Confirm YT, confirm archive, confirm delete remaining, decline video delete
        with patch("builtins.input", side_effect=["y", "y", "y", "n"]):
            run_cleanup(out, archive)

        assert (archive / "THOR" / quad.name).exists()
        assert not plain.exists()


class TestRunCleanupVideoFile:

    def test_compiled_mp4_deleted_when_confirmed(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)

        # Confirm YT, no clips: skip archive, skip deletion, confirm video delete
        with patch("builtins.input", side_effect=["y", "y"]):
            run_cleanup(out, archive)

        assert not mp4.exists()

    def test_compiled_mp4_kept_when_declined(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)

        with patch("builtins.input", side_effect=["y", "n"]):
            run_cleanup(out, archive)

        assert mp4.exists()

    def test_no_mp4_section_when_no_video(self, tmp_path):
        """If no compiled .mp4 exists, cleanup completes without prompting for it."""
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        mp4.unlink()

        # YT confirmation fires, then nothing else (no clips, no video)
        with patch("builtins.input", side_effect=["y"]) as mock_input:
            run_cleanup(out, archive)
        assert mock_input.call_count == 1
