"""
Tests for clip_cache.py - unified per-clip cache (.clip.json).

Cache key: file mtime + size. Fields: ko_result, fingerprint, duration, width, height.
All fields are optional - only written when available.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import clip_cache


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_clip(directory: Path, name: str = "THOR_2026-02-06_22-38-56.mp4") -> Path:
    p = directory / name
    p.write_bytes(b"fake clip data")
    return p


# ── cache_path ────────────────────────────────────────────────────────────────

class TestCachePath:

    def test_dated_clip_uses_month_subfolder(self, tmp_path):
        clip = str(tmp_path / "THOR_2026-02-06_22-38-56.mp4")
        p = clip_cache.cache_path(clip, str(tmp_path / "cache"))
        assert "2026-02" in p
        assert p.endswith(".clip.json")

    def test_undated_clip_has_no_month_subfolder(self, tmp_path):
        clip = str(tmp_path / "random_clip.mp4")
        p = clip_cache.cache_path(clip, str(tmp_path / "cache"))
        assert "2026" not in p
        assert p.endswith(".clip.json")

    def test_clip_json_extension_not_ko_json(self, tmp_path):
        clip = str(tmp_path / "THOR_2026-02-06_22-38-56.mp4")
        p = clip_cache.cache_path(clip, str(tmp_path / "cache"))
        assert ".ko.json" not in p
        assert p.endswith(".clip.json")


# ── cache_load / cache_save round-trip ────────────────────────────────────────

class TestCacheRoundTrip:

    def test_save_and_load_ko_result(self, tmp_path):
        clip = _make_clip(tmp_path)
        ko = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), ko_result=ko)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert entry["ko_result"]["tier"] == "QUAD"

    def test_save_null_ko_result(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), ko_result=None)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert "ko_result" in entry
        assert entry["ko_result"] is None

    def test_save_and_load_fingerprint(self, tmp_path):
        clip = _make_clip(tmp_path)
        fp = ["aabbccdd", "11223344"]
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), fingerprint=fp)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert entry["fingerprint"] == fp

    def test_save_and_load_duration(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=45.2)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert entry["duration"] == pytest.approx(45.2)

    def test_save_and_load_resolution(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), width=1920, height=1080)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert entry["width"] == 1920
        assert entry["height"] == 1080

    def test_partial_update_preserves_other_fields(self, tmp_path):
        """Saving fingerprint must not overwrite an existing ko_result."""
        clip = _make_clip(tmp_path)
        ko = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), ko_result=ko)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), fingerprint=["hash1"])
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert entry["ko_result"]["tier"] == "QUAD"
        assert entry["fingerprint"] == ["hash1"]

    def test_internal_keys_present_in_raw_file(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
        raw_path = clip_cache.cache_path(str(clip), str(tmp_path / "cache"))
        raw = json.loads(Path(raw_path).read_text())
        assert "file_mtime" in raw
        assert "file_size" in raw


# ── Cache key validation ───────────────────────────────────────────────────────

class TestCacheKeyValidation:

    def test_miss_when_no_file(self, tmp_path):
        clip = _make_clip(tmp_path)
        hit, _ = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is False

    def test_hit_when_fresh(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
        hit, _ = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True

    def test_miss_when_mtime_changes(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
        new_mtime = os.path.getmtime(str(clip)) + 10.0
        os.utime(str(clip), (new_mtime, new_mtime))
        hit, _ = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is False

    def test_miss_when_size_changes(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
        # Append bytes to change size without touching mtime via os.utime
        clip.write_bytes(b"fake clip data EXTRA")
        hit, _ = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is False

    def test_miss_when_file_absent(self, tmp_path):
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
        clip.unlink()
        hit, _ = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is False

    def test_miss_when_corrupt_json(self, tmp_path):
        clip = _make_clip(tmp_path)
        raw_path = clip_cache.cache_path(str(clip), str(tmp_path / "cache"))
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        Path(raw_path).write_text("{bad json")
        hit, _ = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is False


# ── Field presence semantics ──────────────────────────────────────────────────

class TestFieldPresence:

    def test_unscanned_clip_has_no_ko_result_key(self, tmp_path):
        """A clip with only duration cached has no ko_result key - not scanned yet."""
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), duration=30.0)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert "ko_result" not in entry

    def test_scanned_no_kill_has_null_ko_result(self, tmp_path):
        """Scanned but no kill found: ko_result key is present but value is None."""
        clip = _make_clip(tmp_path)
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), ko_result=None)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert "ko_result" in entry
        assert entry["ko_result"] is None

    def test_unfingerprinted_clip_has_no_fingerprint_key(self, tmp_path):
        """A clip with only ko_result has no fingerprint key."""
        clip = _make_clip(tmp_path)
        ko = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        clip_cache.cache_save(str(clip), str(tmp_path / "cache"), ko_result=ko)
        hit, entry = clip_cache.cache_load(str(clip), str(tmp_path / "cache"))
        assert hit is True
        assert "fingerprint" not in entry
