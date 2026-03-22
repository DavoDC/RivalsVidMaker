"""
Tests for pipeline.py helper functions.

All helpers are pure or use only the filesystem (tmp_path).
No FFmpeg / Tesseract / real clips needed.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from batcher import Batch
from clip_scanner import Clip
from pipeline import (
    _batch_slug,
    _date_range,
    _fmt_duration,
    _fmt_estimate,
    _menu_status,
    _scan_archive_folder,
    _scan_output_folder,
)


# ── _fmt_duration ─────────────────────────────────────────────────────────────

class TestFmtDuration:

    def test_minutes_and_seconds(self):
        assert _fmt_duration(90.0) == "1m 30s"

    def test_zero(self):
        assert _fmt_duration(0.0) == "0m 0s"

    def test_exactly_one_hour(self):
        assert _fmt_duration(3600.0) == "1h 0m"

    def test_one_hour_thirty_minutes(self):
        assert _fmt_duration(5400.0) == "1h 30m"

    def test_seconds_only(self):
        assert _fmt_duration(45.0) == "0m 45s"

    def test_fractional_seconds_truncated(self):
        # Fractional part is discarded — only whole seconds counted
        assert _fmt_duration(90.9) == "1m 30s"


# ── _fmt_estimate ─────────────────────────────────────────────────────────────

class TestFmtEstimate:

    def test_under_one_minute(self):
        assert _fmt_estimate(45.0) == "~45s"

    def test_exactly_one_minute(self):
        assert _fmt_estimate(60.0) == "~1m 00s"

    def test_minutes_and_seconds(self):
        assert _fmt_estimate(125.0) == "~2m 05s"

    def test_zero(self):
        assert _fmt_estimate(0.0) == "~0s"


# ── _menu_status ──────────────────────────────────────────────────────────────

class TestMenuStatus:

    def test_ready_when_at_target(self):
        assert _menu_status(900.0, 900) == "✓ Ready"

    def test_ready_when_above_target(self):
        assert _menu_status(1200.0, 900) == "✓ Ready"

    def test_almost_when_75_percent(self):
        # 75% of 900 = 675s
        assert _menu_status(675.0, 900) == "~ Almost"

    def test_almost_just_below_target(self):
        assert _menu_status(899.0, 900) == "~ Almost"

    def test_too_short_when_under_75_percent(self):
        assert _menu_status(500.0, 900) == "✗ Too short"

    def test_no_clips_when_zero(self):
        assert _menu_status(0.0, 900) == "— No clips"


# ── _date_range ───────────────────────────────────────────────────────────────

def _make_clip_file(directory: Path, name: str) -> Path:
    p = directory / name
    p.write_bytes(b"")
    return p


class TestDateRange:

    def test_single_clip_returns_single_date(self, tmp_path):
        _make_clip_file(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        result = _date_range(tmp_path)
        assert "6 Feb '26" in result
        assert "→" not in result  # single date, no range

    def test_two_clips_same_date(self, tmp_path):
        _make_clip_file(tmp_path, "THOR_2026-02-06_10-00-00.mp4")
        _make_clip_file(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        result = _date_range(tmp_path)
        assert "→" not in result

    def test_two_clips_different_dates_shows_range(self, tmp_path):
        _make_clip_file(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        _make_clip_file(tmp_path, "THOR_2026-03-15_14-00-00.mp4")
        result = _date_range(tmp_path)
        assert "→" in result
        assert "Feb" in result
        assert "Mar" in result

    def test_empty_folder_returns_dash(self, tmp_path):
        assert _date_range(tmp_path) == "—"

    def test_non_video_files_ignored(self, tmp_path):
        _make_clip_file(tmp_path, "notes.txt")
        assert _date_range(tmp_path) == "—"

    def test_unparseable_filenames_ignored(self, tmp_path):
        _make_clip_file(tmp_path, "random_clip.mp4")
        assert _date_range(tmp_path) == "—"


# ── _batch_slug ───────────────────────────────────────────────────────────────

def make_batch_with_names(names: list[str], number: int = 1) -> Batch:
    clips = [Clip(path=Path(n), duration=30.0) for n in names]
    return Batch(number=number, clips=clips)


class TestBatchSlug:

    def test_single_month(self):
        batch = make_batch_with_names([
            "THOR_2026-02-06_22-38-56.mp4",
            "THOR_2026-02-20_18-00-00.mp4",
        ])
        slug = _batch_slug("THOR", batch, total_batches=1)
        assert slug == "THOR_Feb_2026"

    def test_multi_month(self):
        batch = make_batch_with_names([
            "THOR_2026-02-06_22-38-56.mp4",
            "THOR_2026-03-15_18-00-00.mp4",
        ])
        slug = _batch_slug("THOR", batch, total_batches=1)
        assert slug == "THOR_Feb-Mar_2026"

    def test_batch_suffix_when_multiple_batches(self):
        batch = make_batch_with_names(["THOR_2026-02-06_22-38-56.mp4"], number=2)
        slug = _batch_slug("THOR", batch, total_batches=3)
        assert slug.endswith("_BATCH2")

    def test_no_batch_suffix_when_single_batch(self):
        batch = make_batch_with_names(["THOR_2026-02-06_22-38-56.mp4"], number=1)
        slug = _batch_slug("THOR", batch, total_batches=1)
        assert "_BATCH" not in slug

    def test_unknown_date_when_no_parseable_names(self):
        batch = make_batch_with_names(["random.mp4"])
        slug = _batch_slug("THOR", batch, total_batches=1)
        assert "UNKNOWN" in slug

    def test_char_name_in_slug(self):
        batch = make_batch_with_names(["SQUIRREL_GIRL_2026-03-01_10-00-00.mp4"])
        slug = _batch_slug("SQUIRREL_GIRL", batch, total_batches=1)
        assert slug.startswith("SQUIRREL_GIRL_")


# ── _scan_output_folder ───────────────────────────────────────────────────────

class TestScanOutputFolder:

    def test_empty_output_returns_empty(self, tmp_path):
        assert _scan_output_folder(tmp_path) == []

    def test_nonexistent_path_returns_empty(self, tmp_path):
        assert _scan_output_folder(tmp_path / "missing") == []

    def test_detects_video_file(self, tmp_path):
        folder = tmp_path / "THOR_Feb_2026"
        folder.mkdir()
        (folder / "THOR_Feb_2026.mp4").write_bytes(b"")
        rows = _scan_output_folder(tmp_path)
        assert len(rows) == 1
        assert rows[0]["has_video"] is True
        assert rows[0]["has_desc"] is False
        assert rows[0]["has_clips"] is False

    def test_detects_description_file(self, tmp_path):
        folder = tmp_path / "THOR_Feb_2026"
        folder.mkdir()
        (folder / "THOR_Feb_2026_description.txt").write_text("desc")
        rows = _scan_output_folder(tmp_path)
        assert rows[0]["has_desc"] is True

    def test_detects_clips_subfolder(self, tmp_path):
        folder = tmp_path / "THOR_Feb_2026"
        folder.mkdir()
        clips_dir = folder / "clips"
        clips_dir.mkdir()
        rows = _scan_output_folder(tmp_path)
        assert rows[0]["has_clips"] is True

    def test_folder_with_all_three(self, tmp_path):
        folder = tmp_path / "THOR_Feb_2026"
        folder.mkdir()
        (folder / "THOR_Feb_2026.mp4").write_bytes(b"")
        (folder / "THOR_Feb_2026_description.txt").write_text("desc")
        (folder / "clips").mkdir()
        rows = _scan_output_folder(tmp_path)
        assert rows[0] == {
            "name": "THOR_Feb_2026",
            "has_video": True,
            "has_desc": True,
            "has_clips": True,
        }

    def test_multiple_folders_returned_sorted(self, tmp_path):
        for name in ["STORM_Mar_2026", "THOR_Feb_2026", "THOR_Mar_2026"]:
            (tmp_path / name).mkdir()
        rows = _scan_output_folder(tmp_path)
        assert [r["name"] for r in rows] == ["STORM_Mar_2026", "THOR_Feb_2026", "THOR_Mar_2026"]

    def test_skips_files_at_root(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        rows = _scan_output_folder(tmp_path)
        assert rows == []


# ── _scan_archive_folder ──────────────────────────────────────────────────────

class TestScanArchiveFolder:

    def test_nonexistent_path_returns_empty(self, tmp_path):
        total, counts = _scan_archive_folder(tmp_path / "missing")
        assert total == 0
        assert counts == {}

    def test_empty_folder_returns_zero(self, tmp_path):
        total, counts = _scan_archive_folder(tmp_path)
        assert total == 0
        assert counts == {}

    def test_counts_clips(self, tmp_path):
        (tmp_path / "THOR_2026-02-06_22-38-56_QUAD.mp4").write_bytes(b"")
        (tmp_path / "THOR_2026-02-07_18-00-00_PENTA.mp4").write_bytes(b"")
        total, counts = _scan_archive_folder(tmp_path)
        assert total == 2
        assert counts.get("THOR") == 2

    def test_multiple_characters(self, tmp_path):
        (tmp_path / "THOR_2026-02-06_22-38-56_QUAD.mp4").write_bytes(b"")
        (tmp_path / "STORM_2026-03-01_10-00-00_QUAD.mp4").write_bytes(b"")
        total, counts = _scan_archive_folder(tmp_path)
        assert total == 2
        assert counts["THOR"] == 1
        assert counts["STORM"] == 1

    def test_non_video_files_ignored(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        total, _ = _scan_archive_folder(tmp_path)
        assert total == 0

    def test_unparseable_filenames_counted_as_unknown(self, tmp_path):
        (tmp_path / "random.mp4").write_bytes(b"")
        total, counts = _scan_archive_folder(tmp_path)
        assert total == 1
        assert counts.get("unknown") == 1
