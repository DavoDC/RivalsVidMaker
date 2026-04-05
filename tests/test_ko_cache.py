"""
Tests for ko_detect.py cache functions (now backed by clip_cache / .clip.json).

Does NOT test OCR or FFmpeg - only the cache read/write/invalidation logic.
KO results are stored under the ko_result field in .clip.json.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import ko_detect


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_clip(directory: Path, name: str = "THOR_2026-02-06_22-38-56.mp4") -> Path:
    p = directory / name
    p.write_bytes(b"fake clip data")
    return p


def _override_cache_dir(tmp_path: Path):
    """Patch ko_detect.CACHE_DIR to use tmp_path for isolation."""
    return patch.object(ko_detect, "CACHE_DIR", str(tmp_path / "cache"))


# ── cache_path ────────────────────────────────────────────────────────────────

class TestCachePath:

    def test_dated_clip_uses_month_subfolder(self, tmp_path):
        clip = str(tmp_path / "THOR_2026-02-06_22-38-56.mp4")
        with _override_cache_dir(tmp_path):
            p = ko_detect.cache_path(clip)
        assert "2026-02" in p
        assert p.endswith(".clip.json")

    def test_undated_clip_has_no_month_subfolder(self, tmp_path):
        clip = str(tmp_path / "random_clip.mp4")
        with _override_cache_dir(tmp_path):
            p = ko_detect.cache_path(clip)
        assert "2026" not in p
        assert p.endswith(".clip.json")

    def test_clip_json_extension_not_ko_json(self, tmp_path):
        clip = str(tmp_path / "THOR_2026-02-06_22-38-56.mp4")
        with _override_cache_dir(tmp_path):
            p = ko_detect.cache_path(clip)
        assert ".ko.json" not in p
        assert p.endswith(".clip.json")


# ── cache_save / cache_load round-trip ───────────────────────────────────────

class TestCacheRoundTrip:

    def test_save_and_load_kill_result(self, tmp_path):
        clip = _make_clip(tmp_path)
        result = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), result)
            hit, loaded = ko_detect.cache_load(str(clip))

        assert hit is True
        assert loaded is not None
        assert loaded["tier"] == "QUAD"
        assert loaded["start_ts"] == 6.0

    def test_save_and_load_null_result(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            hit, loaded = ko_detect.cache_load(str(clip))

        assert hit is True
        assert loaded is None  # null = "no kill detected"

    def test_null_result_stored_under_ko_result_key(self, tmp_path):
        """Null results must be stored as ko_result: null inside a dict (not bare JSON null)."""
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert isinstance(raw, dict)
        assert "ko_result" in raw
        assert raw["ko_result"] is None

    def test_kill_result_stored_under_ko_result_key(self, tmp_path):
        """Kill results stored as ko_result dict, not flat in root."""
        clip = _make_clip(tmp_path)
        result = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), result)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert isinstance(raw, dict)
        assert "ko_result" in raw
        assert raw["ko_result"]["tier"] == "QUAD"
        # tier must NOT be at root level
        assert "tier" not in raw


# ── cache_exists ──────────────────────────────────────────────────────────────

class TestCacheExists:

    def test_miss_when_no_file(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            assert ko_detect.cache_exists(str(clip)) is False

    def test_hit_when_ko_result_present(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), {"tier": "QUAD", "start_ts": 1.0,
                                              "max_ts": 5.0, "end_ts": 6.0, "events": []})
            assert ko_detect.cache_exists(str(clip)) is True

    def test_hit_when_null_ko_result(self, tmp_path):
        """A null result (scanned, no kill) is still a valid cache hit."""
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            assert ko_detect.cache_exists(str(clip)) is True

    def test_miss_when_only_duration_cached(self, tmp_path):
        """Duration cached but KO not yet scanned - cache_exists should return False."""
        import clip_cache
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
            assert ko_detect.cache_exists(str(clip)) is False

    def test_miss_when_clip_mtime_changes(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            new_mtime = os.path.getmtime(str(clip)) + 10.0
            os.utime(str(clip), (new_mtime, new_mtime))
            assert ko_detect.cache_exists(str(clip)) is False


# ── Stale-cache invalidation ──────────────────────────────────────────────────

class TestStaleCacheInvalidation:

    def test_stale_entry_is_not_returned(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), {"tier": "QUAD", "start_ts": 1.0,
                                              "max_ts": 5.0, "end_ts": 6.0, "events": []})
            new_mtime = os.path.getmtime(str(clip)) + 10.0
            os.utime(str(clip), (new_mtime, new_mtime))
            hit, result = ko_detect.cache_load(str(clip))

        assert hit is False
        assert result is None


# ── Timing fields ─────────────────────────────────────────────────────────────

class TestTimingFields:

    def test_kill_entry_saves_timing_fields(self, tmp_path):
        clip = _make_clip(tmp_path)
        result = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), result, clip_duration=45.2, scan_time=12.3)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        # duration and scan_time stored at root level (not nested under ko_result)
        assert raw["duration"] == 45.2
        assert raw["scan_time"] == 12.3

    def test_null_entry_saves_timing_fields(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None, clip_duration=30.0, scan_time=8.5)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert raw["ko_result"] is None
        assert raw["duration"] == 30.0
        assert raw["scan_time"] == 8.5

    def test_timing_fields_are_optional(self, tmp_path):
        clip = _make_clip(tmp_path)
        result = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), result)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert "duration" not in raw
        assert "scan_time" not in raw
