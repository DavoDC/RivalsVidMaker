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
    _estimate_seconds,
    _find_ko_none_clips,
    _fmt_duration,
    _fmt_estimate,
    _menu_status,
    _move_clips,
    _scan_archive_folder,
    _scan_output_folder,
)


# ── _estimate_seconds ────────────────────────────────────────────────────────

def _make_mp4(directory: Path, name: str) -> Path:
    p = directory / name
    p.write_bytes(b"")
    return p


def _make_cache(cache_dir: Path, clip: Path) -> None:
    """Create a .ko.json cache entry for a clip (mirrors _cache_exists logic)."""
    import re
    m = re.search(r"(\d{4}-\d{2})-\d{2}", clip.stem)
    if m:
        entry = cache_dir / m.group(1) / (clip.stem + ".ko.json")
    else:
        entry = cache_dir / (clip.stem + ".ko.json")
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("{}")


class TestEstimateSeconds:

    def test_empty_clips_returns_zero(self, tmp_path):
        result = _estimate_seconds([], tmp_path / "cache")
        assert result == 0.0

    def test_all_cached_clips(self, tmp_path):
        folder = tmp_path / "THOR"
        folder.mkdir()
        cache_root = tmp_path / "cache"
        char_cache = cache_root / "THOR"
        clip_path = _make_mp4(folder, "THOR_2026-02-06_22-38-56.mp4")
        _make_cache(char_cache, clip_path)
        clips = [Clip(path=clip_path, duration=30.0)]

        result = _estimate_seconds(clips, cache_root)
        # 1 cached clip: 0.5s + encode: 30 * 0.4 = 12.0
        assert result == pytest.approx(0.5 + 12.0)

    def test_uncached_clip_uses_formula(self, tmp_path):
        folder = tmp_path / "THOR"
        folder.mkdir()
        clip_path = _make_mp4(folder, "THOR_2026-02-06_22-38-56.mp4")
        clips = [Clip(path=clip_path, duration=30.0)]
        # avg=30s, formula: 0.977*30 - 4.118 = 25.192
        result = _estimate_seconds(clips, tmp_path / "cache")
        expected_ko = 0.977 * 30 - 4.118
        expected = expected_ko + 30.0 * 0.4
        assert result == pytest.approx(expected, rel=1e-3)

    def test_short_clip_formula_clamped_to_one(self, tmp_path):
        # Formula for a 4s clip: 0.977*4 - 4.118 = -0.21 -> clamped to 1.0
        folder = tmp_path / "THOR"
        folder.mkdir()
        clip_path = _make_mp4(folder, "THOR_2026-02-06_22-38-56.mp4")
        clips = [Clip(path=clip_path, duration=4.0)]
        result = _estimate_seconds(clips, tmp_path / "cache")
        expected = 1.0 + 4.0 * 0.4
        assert result == pytest.approx(expected)

    def test_mix_cached_and_uncached(self, tmp_path):
        folder = tmp_path / "THOR"
        folder.mkdir()
        cache_root = tmp_path / "cache"
        char_cache = cache_root / "THOR"
        cached_path = _make_mp4(folder, "THOR_2026-02-06_22-38-56.mp4")
        _make_cache(char_cache, cached_path)
        uncached_path = _make_mp4(folder, "THOR_2026-02-07_18-00-00.mp4")
        clips = [Clip(path=cached_path, duration=30.0), Clip(path=uncached_path, duration=30.0)]

        result = _estimate_seconds(clips, cache_root)
        ko_cached = 0.5
        ko_uncached = 0.977 * 30 - 4.118  # avg=30s
        expected = ko_cached + ko_uncached + 60.0 * 0.4
        assert result == pytest.approx(expected, rel=1e-3)


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
        # Fractional part is discarded - only whole seconds counted
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
        assert _menu_status(0.0, 900) == "- No clips"


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
        assert _date_range(tmp_path) == "-"

    def test_non_video_files_ignored(self, tmp_path):
        _make_clip_file(tmp_path, "notes.txt")
        assert _date_range(tmp_path) == "-"

    def test_unparseable_filenames_ignored(self, tmp_path):
        _make_clip_file(tmp_path, "random_clip.mp4")
        assert _date_range(tmp_path) == "-"


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
        slug = _batch_slug("THOR", batch)
        assert slug == "THOR_Feb_2026_BATCH1"

    def test_multi_month(self):
        batch = make_batch_with_names([
            "THOR_2026-02-06_22-38-56.mp4",
            "THOR_2026-03-15_18-00-00.mp4",
        ])
        slug = _batch_slug("THOR", batch)
        assert slug == "THOR_Feb-Mar_2026_BATCH1"

    def test_batch_number_in_slug(self):
        batch = make_batch_with_names(["THOR_2026-02-06_22-38-56.mp4"], number=2)
        slug = _batch_slug("THOR", batch)
        assert slug.endswith("_BATCH2")

    def test_single_batch_always_gets_suffix(self):
        batch = make_batch_with_names(["THOR_2026-02-06_22-38-56.mp4"], number=1)
        slug = _batch_slug("THOR", batch)
        assert slug.endswith("_BATCH1")

    def test_unknown_date_when_no_parseable_names(self):
        batch = make_batch_with_names(["random.mp4"])
        slug = _batch_slug("THOR", batch)
        assert "UNKNOWN" in slug

    def test_char_name_in_slug(self):
        batch = make_batch_with_names(["SQUIRREL_GIRL_2026-03-01_10-00-00.mp4"])
        slug = _batch_slug("SQUIRREL_GIRL", batch)
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
        row = rows[0]
        assert row["name"] == "THOR_Feb_2026"
        assert row["has_video"] is True
        assert row["has_desc"] is True
        assert row["has_clips"] is True
        assert "age" in row

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
        assert counts["THOR"][0] == 2

    def test_multiple_characters(self, tmp_path):
        (tmp_path / "THOR_2026-02-06_22-38-56_QUAD.mp4").write_bytes(b"")
        (tmp_path / "STORM_2026-03-01_10-00-00_QUAD.mp4").write_bytes(b"")
        total, counts = _scan_archive_folder(tmp_path)
        assert total == 2
        assert counts["THOR"][0] == 1
        assert counts["STORM"][0] == 1

    def test_non_video_files_ignored(self, tmp_path):
        (tmp_path / "notes.txt").write_text("x")
        total, _ = _scan_archive_folder(tmp_path)
        assert total == 0

    def test_unparseable_filenames_counted_as_unknown(self, tmp_path):
        (tmp_path / "random.mp4").write_bytes(b"")
        total, counts = _scan_archive_folder(tmp_path)
        assert total == 1
        assert counts["unknown"][0] == 1


# ── _move_clips ───────────────────────────────────────────────────────────────

def make_batch_from_files(paths: list[Path]) -> Batch:
    return Batch(number=1, clips=[Clip(path=p, duration=30.0) for p in paths])


class TestMoveClips:

    def test_moves_clip_to_clips_dir(self, tmp_path):
        src = tmp_path / "THOR_2026-02-06_22-38-56.mp4"
        src.write_bytes(b"clip data")
        clips_dir = tmp_path / "output" / "clips"
        batch = make_batch_from_files([src])
        _move_clips(batch, clips_dir)
        assert not src.exists()
        assert (clips_dir / "THOR_2026-02-06_22-38-56.mp4").exists()

    def test_tier_already_in_filename_preserved(self, tmp_path):
        # Tier embedded at scan stage - _move_clips just moves without renaming
        src = tmp_path / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        src.write_bytes(b"clip data")
        clips_dir = tmp_path / "output" / "clips"
        batch = make_batch_from_files([src])
        _move_clips(batch, clips_dir)
        assert (clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4").exists()

    def test_no_tier_filename_unchanged(self, tmp_path):
        src = tmp_path / "THOR_2026-02-06_22-38-56.mp4"
        src.write_bytes(b"clip data")
        clips_dir = tmp_path / "output" / "clips"
        batch = make_batch_from_files([src])
        _move_clips(batch, clips_dir)
        assert (clips_dir / "THOR_2026-02-06_22-38-56.mp4").exists()

    def test_creates_clips_dir_if_missing(self, tmp_path):
        src = tmp_path / "THOR_2026-02-06_22-38-56.mp4"
        src.write_bytes(b"x")
        clips_dir = tmp_path / "does_not_exist" / "clips"
        assert not clips_dir.exists()
        batch = make_batch_from_files([src])
        _move_clips(batch, clips_dir)
        assert clips_dir.is_dir()

    def test_skips_existing_destination(self, tmp_path):
        src = tmp_path / "THOR_2026-02-06_22-38-56.mp4"
        src.write_bytes(b"source")
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        existing = clips_dir / "THOR_2026-02-06_22-38-56.mp4"
        existing.write_bytes(b"existing")
        batch = make_batch_from_files([src])
        _move_clips(batch, clips_dir)
        # Source stays, destination is not overwritten
        assert src.exists()
        assert existing.read_bytes() == b"existing"

    def test_moves_multiple_clips(self, tmp_path):
        clips_dir = tmp_path / "clips"
        srcs = []
        for name in ["THOR_2026-02-06_22-38-56_QUAD.mp4", "THOR_2026-02-07_18-00-00.mp4"]:
            p = tmp_path / name
            p.write_bytes(b"x")
            srcs.append(p)
        batch = make_batch_from_files(srcs)
        _move_clips(batch, clips_dir)
        assert (clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4").exists()
        assert (clips_dir / "THOR_2026-02-07_18-00-00.mp4").exists()


# ── _find_ko_none_clips ───────────────────────────────────────────────────────

def _make_clip(name: str) -> "Clip":
    return Clip(path=Path(name), duration=30.0)


class TestFindKoNoneClips:

    def test_empty_list_returns_empty(self):
        assert _find_ko_none_clips([]) == []

    def test_ko_suffix_detected(self):
        clips = [_make_clip("THOR_2026-03-22_23-19-10_KO.mp4")]
        result = _find_ko_none_clips(clips)
        assert len(result) == 1

    def test_none_suffix_detected(self):
        clips = [_make_clip("THOR_2026-03-28_23-22-42_UNKNOWN.mp4")]
        result = _find_ko_none_clips(clips)
        assert len(result) == 1

    def test_none_ko_compound_suffix_detected(self):
        # Legacy clips may have _NONE_KO - stem ends with _KO, so caught
        clips = [_make_clip("THOR_2026-03-17_22-20-29_NONE_KO.mp4")]
        result = _find_ko_none_clips(clips)
        assert len(result) == 1

    def test_quad_clip_not_filtered(self):
        clips = [_make_clip("THOR_2026-02-06_22-38-56_QUAD.mp4")]
        assert _find_ko_none_clips(clips) == []

    def test_double_clip_not_filtered(self):
        clips = [_make_clip("THOR_2026-03-01_20-00-00_DOUBLE.mp4")]
        assert _find_ko_none_clips(clips) == []

    def test_unsuffixed_clip_not_filtered(self):
        clips = [_make_clip("THOR_2026-02-06_22-38-56.mp4")]
        assert _find_ko_none_clips(clips) == []

    def test_mixed_batch_returns_only_low_tier(self):
        clips = [
            _make_clip("THOR_2026-02-06_22-38-56_QUAD.mp4"),
            _make_clip("THOR_2026-03-22_23-19-10_KO.mp4"),
            _make_clip("THOR_2026-03-28_23-22-42_UNKNOWN.mp4"),
            _make_clip("THOR_2026-03-01_20-00-00_TRIPLE.mp4"),
        ]
        result = _find_ko_none_clips(clips)
        assert len(result) == 2
        names = {c.name for c in result}
        assert "THOR_2026-03-22_23-19-10_KO.mp4" in names
        assert "THOR_2026-03-28_23-22-42_UNKNOWN.mp4" in names
