"""
Tests for ko_detect.py — cache functions (mtime keying).

Does NOT test OCR or FFmpeg — only the JSON cache read/write/invalidation logic.
"""

import json
import os
import time
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
        assert p.endswith(".ko.json")

    def test_undated_clip_has_no_month_subfolder(self, tmp_path):
        clip = str(tmp_path / "random_clip.mp4")
        with _override_cache_dir(tmp_path):
            p = ko_detect.cache_path(clip)
        # Should NOT have a YYYY-MM subfolder
        assert "2026" not in p
        assert p.endswith(".ko.json")


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
        # Internal file_mtime key must not be exposed to callers
        assert "file_mtime" not in loaded

    def test_save_and_load_null_result(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            hit, loaded = ko_detect.cache_load(str(clip))

        assert hit is True
        assert loaded is None  # null = "no kill detected"

    def test_null_result_stored_as_dict_not_json_null(self, tmp_path):
        """Null results must NOT be stored as bare JSON null — they need mtime keying."""
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert isinstance(raw, dict), "Null result must be stored as a dict, not JSON null"
        assert raw.get("_null_result") is True
        assert "file_mtime" in raw


# ── cache_exists ─────────────────────────────────────────────────────────────

class TestCacheExists:

    def test_miss_when_no_file(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            assert ko_detect.cache_exists(str(clip)) is False

    def test_hit_when_fresh_entry_exists(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), {"tier": "QUAD", "start_ts": 1.0,
                                              "max_ts": 5.0, "end_ts": 6.0, "events": []})
            assert ko_detect.cache_exists(str(clip)) is True

    def test_miss_when_clip_mtime_changes(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None)
            # Simulate the clip being replaced (touch with a different mtime)
            new_mtime = os.path.getmtime(str(clip)) + 10.0
            os.utime(str(clip), (new_mtime, new_mtime))
            assert ko_detect.cache_exists(str(clip)) is False

    def test_legacy_entry_without_mtime_is_accepted(self, tmp_path):
        """Entries written before mtime keying was added must still be accepted."""
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            # Write a legacy-style entry (no file_mtime key)
            cache_file = ko_detect.cache_path(str(clip))
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            legacy = {"tier": "QUAD", "start_ts": 1.0, "max_ts": 5.0, "end_ts": 6.0, "events": []}
            Path(cache_file).write_text(json.dumps(legacy))

            hit, result = ko_detect.cache_load(str(clip))
            assert hit is True
            assert result is not None
            assert result["tier"] == "QUAD"


# ── Stale-cache invalidation (integration-ish) ───────────────────────────────

class TestStaleCacheInvalidation:

    def test_stale_entry_is_not_returned(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), {"tier": "QUAD", "start_ts": 1.0,
                                              "max_ts": 5.0, "end_ts": 6.0, "events": []})
            # Modify the clip file to change its mtime
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

        assert raw["clip_duration"] == 45.2
        assert raw["scan_time"] == 12.3

    def test_null_entry_saves_timing_fields(self, tmp_path):
        clip = _make_clip(tmp_path)
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), None, clip_duration=30.0, scan_time=8.5)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert raw["_null_result"] is True
        assert raw["clip_duration"] == 30.0
        assert raw["scan_time"] == 8.5

    def test_timing_fields_are_optional(self, tmp_path):
        clip = _make_clip(tmp_path)
        result = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        with _override_cache_dir(tmp_path):
            ko_detect.cache_save(str(clip), result)
            cache_file = ko_detect.cache_path(str(clip))
            raw = json.loads(Path(cache_file).read_text())

        assert "clip_duration" not in raw
        assert "scan_time" not in raw
