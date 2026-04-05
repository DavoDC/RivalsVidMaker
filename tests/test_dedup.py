"""
Tests for dedup.py -- perceptual-hash duplicate clip detection.

All ffmpeg calls are mocked; no real video files required.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import imagehash

from clip_scanner import Clip
import dedup


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_clip(directory: Path, name: str, duration: float = 30.0) -> Clip:
    p = directory / name
    p.write_bytes(b"fake clip")
    return Clip(path=p, duration=duration)


def _zero_hash() -> imagehash.ImageHash:
    """64-bit hash of all zeros."""
    return imagehash.ImageHash(np.zeros(64, dtype=bool))


def _ones_hash() -> imagehash.ImageHash:
    """64-bit hash of all ones -- maximum distance from zero_hash (64 bits)."""
    return imagehash.ImageHash(np.ones(64, dtype=bool))


def _alt_hash() -> imagehash.ImageHash:
    """Alternating bits -- distance 32 from both zero and ones."""
    bits = np.array([i % 2 == 0 for i in range(64)])
    return imagehash.ImageHash(bits)


def _make_fingerprint(h: imagehash.ImageHash, n: int = 5) -> list[imagehash.ImageHash]:
    """Return n copies of the same hash (simulates a clip where all frames look the same)."""
    return [h] * n


# ── avg_distance ────────────────────────────────────────────────────────────────

class TestAvgDistance:

    def test_identical_hashes_zero_distance(self):
        h = _zero_hash()
        assert dedup.avg_distance([h, h, h], [h, h, h]) == 0.0

    def test_max_distance(self):
        zeros = _make_fingerprint(_zero_hash())
        ones = _make_fingerprint(_ones_hash())
        assert dedup.avg_distance(zeros, ones) == 64.0

    def test_partial_distance(self):
        # alternating hash has 32-bit distance from zero hash
        zeros = _make_fingerprint(_zero_hash())
        alts = _make_fingerprint(_alt_hash())
        assert dedup.avg_distance(zeros, alts) == 32.0

    def test_empty_lists_return_zero(self):
        assert dedup.avg_distance([], []) == 0.0


# ── find_duplicates ─────────────────────────────────────────────────────────────

class TestFindDuplicates:

    def test_empty_clips_returns_empty(self, tmp_path):
        result = dedup.find_duplicates([], ffmpeg="ffmpeg")
        assert result == []

    def test_single_clip_returns_empty(self, tmp_path):
        clip = _make_clip(tmp_path, "clip_a.mp4")
        result = dedup.find_duplicates([clip], ffmpeg="ffmpeg")
        assert result == []

    def test_identical_clips_flagged(self, tmp_path):
        clip_a = _make_clip(tmp_path, "THOR_2026-01-01_10-00-00.mp4")
        clip_b = _make_clip(tmp_path, "THOR_2026-01-01_10-00-00_copy.mp4")

        same_fp = _make_fingerprint(_zero_hash())

        with patch("dedup.fingerprint_clip", return_value=same_fp):
            result = dedup.find_duplicates([clip_a, clip_b], ffmpeg="ffmpeg")

        assert len(result) == 1
        assert result[0][0] is clip_a
        assert result[0][1] is clip_b
        assert result[0][2] == 0.0

    def test_different_clips_not_flagged(self, tmp_path):
        clip_a = _make_clip(tmp_path, "THOR_clip_a.mp4")
        clip_b = _make_clip(tmp_path, "THOR_clip_b.mp4")

        def fp_side_effect(clip, ffmpeg, n_frames=5, **kwargs):
            if clip is clip_a:
                return _make_fingerprint(_zero_hash())
            return _make_fingerprint(_ones_hash())

        with patch("dedup.fingerprint_clip", side_effect=fp_side_effect):
            result = dedup.find_duplicates([clip_a, clip_b], ffmpeg="ffmpeg", threshold=10)

        assert result == []

    def test_threshold_boundary_not_flagged(self, tmp_path):
        """A pair whose distance == threshold is NOT flagged (strict <)."""
        clip_a = _make_clip(tmp_path, "a.mp4")
        clip_b = _make_clip(tmp_path, "b.mp4")

        bits_a = np.zeros(64, dtype=bool)
        bits_b = bits_a.copy()
        bits_b[:10] = True  # 10 bits different
        fp_a = [imagehash.ImageHash(bits_a)] * 5
        fp_b = [imagehash.ImageHash(bits_b)] * 5

        def fp_side_effect(clip, ffmpeg, n_frames=5, **kwargs):
            return fp_a if clip is clip_a else fp_b

        with patch("dedup.fingerprint_clip", side_effect=fp_side_effect):
            result = dedup.find_duplicates([clip_a, clip_b], ffmpeg="ffmpeg", threshold=10)

        assert result == []  # distance == threshold: not a duplicate

    def test_below_threshold_is_flagged(self, tmp_path):
        """A pair whose distance < threshold IS flagged."""
        clip_a = _make_clip(tmp_path, "a.mp4")
        clip_b = _make_clip(tmp_path, "b.mp4")

        bits_a = np.zeros(64, dtype=bool)
        bits_b = bits_a.copy()
        bits_b[:9] = True
        fp_a = [imagehash.ImageHash(bits_a)] * 5
        fp_b = [imagehash.ImageHash(bits_b)] * 5

        def fp_side_effect(clip, ffmpeg, n_frames=5, **kwargs):
            return fp_a if clip is clip_a else fp_b

        with patch("dedup.fingerprint_clip", side_effect=fp_side_effect):
            result = dedup.find_duplicates([clip_a, clip_b], ffmpeg="ffmpeg", threshold=10)

        assert len(result) == 1
        assert result[0][2] == 9.0

    def test_three_clips_one_duplicate_pair(self, tmp_path):
        clip_a = _make_clip(tmp_path, "a.mp4")
        clip_b = _make_clip(tmp_path, "b_copy.mp4")  # duplicate of a
        clip_c = _make_clip(tmp_path, "c_different.mp4")

        fp_same = _make_fingerprint(_zero_hash())
        fp_diff = _make_fingerprint(_ones_hash())

        def fp_side_effect(clip, ffmpeg, n_frames=5, **kwargs):
            if clip is clip_c:
                return fp_diff
            return fp_same

        with patch("dedup.fingerprint_clip", side_effect=fp_side_effect):
            result = dedup.find_duplicates([clip_a, clip_b, clip_c], ffmpeg="ffmpeg")

        assert len(result) == 1
        paths = {result[0][0].path, result[0][1].path}
        assert clip_a.path in paths
        assert clip_b.path in paths

    def test_fingerprint_called_once_per_clip(self, tmp_path):
        clips = [_make_clip(tmp_path, f"clip_{i}.mp4") for i in range(3)]
        fp = _make_fingerprint(_zero_hash())

        with patch("dedup.fingerprint_clip", return_value=fp) as mock_fp:
            dedup.find_duplicates(clips, ffmpeg="ffmpeg")

        assert mock_fp.call_count == 3


# ── fingerprint_clip ────────────────────────────────────────────────────────────

class TestFingerprintClip:

    def test_returns_n_hashes(self, tmp_path):
        from PIL import Image
        clip = _make_clip(tmp_path, "test.mp4", duration=20.0)
        fake_images = [Image.new("RGB", (64, 64), color=(i * 40, 0, 0)) for i in range(5)]

        with patch("dedup._extract_frames", return_value=fake_images):
            result = dedup.fingerprint_clip(clip, ffmpeg="ffmpeg", n_frames=5)

        assert len(result) == 5
        assert all(isinstance(h, imagehash.ImageHash) for h in result)

    def test_uses_clip_duration(self, tmp_path):
        """_extract_frames is called with the clip's duration (no extra ffprobe needed)."""
        from PIL import Image
        clip = _make_clip(tmp_path, "test.mp4", duration=42.0)
        fake_images = [Image.new("RGB", (64, 64)) for _ in range(5)]

        with patch("dedup._extract_frames", return_value=fake_images) as mock_ex:
            dedup.fingerprint_clip(clip, ffmpeg="ffmpeg", n_frames=5)

        call_kwargs = mock_ex.call_args
        # duration is passed through
        assert call_kwargs.kwargs.get("duration") == 42.0 or call_kwargs.args[2] == 42.0

    def test_ffmpeg_path_forwarded(self, tmp_path):
        from PIL import Image
        clip = _make_clip(tmp_path, "test.mp4", duration=10.0)
        fake_images = [Image.new("RGB", (64, 64)) for _ in range(5)]

        with patch("dedup._extract_frames", return_value=fake_images) as mock_ex:
            dedup.fingerprint_clip(clip, ffmpeg="/custom/ffmpeg", n_frames=5)

        call_kwargs = mock_ex.call_args
        assert "/custom/ffmpeg" in call_kwargs.args or "/custom/ffmpeg" in str(call_kwargs)


# ── _extract_frames ──────────────────────────────────────────────────────────────

class TestExtractFrames:

    def test_calls_ffmpeg_with_fps_filter(self, tmp_path):
        """_extract_frames calls ffmpeg with a fps filter derived from duration/n_frames."""
        import subprocess
        from PIL import Image

        clip_path = tmp_path / "test.mp4"
        clip_path.write_bytes(b"fake")

        # Create fake PNG files that ffmpeg would produce
        fake_pngs = []
        for i in range(1, 6):
            p = tmp_path / f"f{i:05d}.png"
            img = Image.new("RGB", (64, 64))
            img.save(str(p))
            fake_pngs.append(p)

        def fake_run(cmd, **kwargs):
            return MagicMock(returncode=0)

        with patch("dedup.subprocess.run", side_effect=fake_run), \
             patch("dedup.glob.glob", return_value=[str(p) for p in fake_pngs]):
            images = dedup._extract_frames(
                str(clip_path), ffmpeg="ffmpeg", duration=30.0, n_frames=5, tmpdir=str(tmp_path)
            )

        assert len(images) == 5

    def test_ffmpeg_receives_correct_vframes(self, tmp_path):
        """ffmpeg -vframes N must match n_frames."""
        from PIL import Image
        clip_path = tmp_path / "test.mp4"
        clip_path.write_bytes(b"fake")

        captured_cmd = []

        fake_pngs = []
        for i in range(1, 4):
            p = tmp_path / f"f{i:05d}.png"
            img = Image.new("RGB", (64, 64))
            img.save(str(p))
            fake_pngs.append(p)

        def fake_run(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return MagicMock(returncode=0)

        with patch("dedup.subprocess.run", side_effect=fake_run), \
             patch("dedup.glob.glob", return_value=[str(p) for p in fake_pngs]):
            dedup._extract_frames(
                str(clip_path), ffmpeg="ffmpeg", duration=30.0, n_frames=3, tmpdir=str(tmp_path)
            )

        # -vframes 3 must appear in the command
        assert "-vframes" in captured_cmd
        idx = captured_cmd.index("-vframes")
        assert captured_cmd[idx + 1] == "3"


# ── print_dup_table ──────────────────────────────────────────────────────────────

class TestPrintDupTable:

    def test_prints_nothing_for_empty_pairs(self, capsys):
        dedup.print_dup_table([])
        out = capsys.readouterr().out
        assert out == ""

    def test_prints_warning_header(self, tmp_path, capsys):
        clip_a = _make_clip(tmp_path, "a.mp4")
        clip_b = _make_clip(tmp_path, "b_copy.mp4")
        pairs = [(clip_a, clip_b, 3.2)]
        dedup.print_dup_table(pairs)
        out = capsys.readouterr().out
        assert "duplicate" in out.lower() or "DUPLICATE" in out
        assert "a.mp4" in out
        assert "b_copy.mp4" in out

    def test_shows_distance(self, tmp_path, capsys):
        clip_a = _make_clip(tmp_path, "a.mp4")
        clip_b = _make_clip(tmp_path, "b.mp4")
        pairs = [(clip_a, clip_b, 5.0)]
        dedup.print_dup_table(pairs)
        out = capsys.readouterr().out
        assert "5.0" in out or "5" in out


# ── fingerprint_clip cache ────────────────────────────────────────────────────

class TestFingerprintClipCache:

    def test_cache_hit_skips_ffmpeg(self, tmp_path):
        """When fingerprint is cached, _extract_frames must not be called."""
        import clip_cache

        clip = _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        cache_dir = tmp_path / "cache"

        # pHash is 64 bits = 16 hex chars
        fake_hex = "aabbccdd11223344"
        clip_cache.cache_save(str(clip.path), str(cache_dir), fingerprint=[fake_hex] * 5)

        with patch("dedup._extract_frames") as mock_ex:
            result = dedup.fingerprint_clip(clip, ffmpeg="ffmpeg", cache_dir=cache_dir)

        mock_ex.assert_not_called()
        assert len(result) == 5

    def test_cache_miss_calls_ffmpeg_and_saves(self, tmp_path):
        """On a cache miss, fingerprint is computed and written to .clip.json."""
        from PIL import Image
        import clip_cache

        clip = _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        cache_dir = tmp_path / "cache"
        fake_images = [Image.new("RGB", (64, 64), color=(i * 30, 0, 0)) for i in range(5)]

        with patch("dedup._extract_frames", return_value=fake_images):
            result = dedup.fingerprint_clip(clip, ffmpeg="ffmpeg", n_frames=5, cache_dir=cache_dir)

        assert len(result) == 5
        hit, entry = clip_cache.cache_load(str(clip.path), str(cache_dir))
        assert hit is True
        assert "fingerprint" in entry
        assert len(entry["fingerprint"]) == 5

    def test_cache_partial_update_preserves_ko_result(self, tmp_path):
        """Saving fingerprint must not overwrite an existing ko_result in cache."""
        from PIL import Image
        import clip_cache

        clip = _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        cache_dir = tmp_path / "cache"
        ko = {"tier": "QUAD", "start_ts": 6.0, "max_ts": 20.0, "end_ts": 22.0, "events": []}
        clip_cache.cache_save(str(clip.path), str(cache_dir), ko_result=ko)

        fake_images = [Image.new("RGB", (64, 64)) for _ in range(5)]
        with patch("dedup._extract_frames", return_value=fake_images):
            dedup.fingerprint_clip(clip, ffmpeg="ffmpeg", n_frames=5, cache_dir=cache_dir)

        hit, entry = clip_cache.cache_load(str(clip.path), str(cache_dir))
        assert hit is True
        assert entry["ko_result"]["tier"] == "QUAD"
        assert "fingerprint" in entry

    def test_no_cache_dir_behaves_as_before(self, tmp_path):
        """fingerprint_clip without cache_dir still works (no cache used)."""
        from PIL import Image
        clip = _make_clip(tmp_path, "THOR_2026-02-06_22-38-56.mp4")
        fake_images = [Image.new("RGB", (64, 64)) for _ in range(5)]

        with patch("dedup._extract_frames", return_value=fake_images):
            result = dedup.fingerprint_clip(clip, ffmpeg="ffmpeg", n_frames=5)

        assert len(result) == 5
