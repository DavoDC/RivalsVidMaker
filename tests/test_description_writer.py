"""
Tests for description_writer.py — YouTube description file generation.
"""

from pathlib import Path

import pytest

from batcher import Batch
from clip_scanner import Clip
from description_writer import fmt_ts, write_description


def make_batch(n_clips: int = 3, number: int = 1) -> Batch:
    clips = [
        Clip(path=Path(f"/videos/THOR_clip_{i}.mp4"), duration=30.0)
        for i in range(n_clips)
    ]
    return Batch(number=number, clips=clips)


class TestFmtTs:

    def test_minutes_and_seconds(self):
        assert fmt_ts(96.0) == "1:36"

    def test_zero(self):
        assert fmt_ts(0.0) == "0:00"

    def test_whole_minute(self):
        assert fmt_ts(120.0) == "2:00"

    def test_single_digit_seconds_padded(self):
        assert fmt_ts(65.0) == "1:05"

    def test_large_value(self):
        assert fmt_ts(754.0) == "12:34"


class TestWriteDescription:

    # ── Golden path ───────────────────────────────────────────────────────────

    def test_file_is_created(self, tmp_path):
        out = write_description(make_batch(), "THOR", [], tmp_path)
        assert out.exists()

    def test_contains_char_name(self, tmp_path):
        out = write_description(make_batch(), "THOR", [], tmp_path)
        assert "THOR" in out.read_text()

    def test_timestamps_present_when_highlights_given(self, tmp_path):
        highlights = [(96.0, 105.0, "QUAD", "THOR_clip_0.mp4")]
        out = write_description(make_batch(), "THOR", highlights, tmp_path)
        content = out.read_text()
        assert "TIMESTAMPS" in content
        assert "1:36" in content   # fmt_ts(96)
        assert "1:45" in content   # fmt_ts(105)
        assert "Quad Kill" in content

    def test_highlight_tier_is_title_cased(self, tmp_path):
        highlights = [(60.0, 75.0, "HEXA", "clip.mp4")]
        content = write_description(make_batch(), "THOR", highlights, tmp_path).read_text()
        assert "Hexa Kill" in content

    def test_clip_list_numbered_correctly(self, tmp_path):
        content = write_description(make_batch(3), "THOR", [], tmp_path).read_text()
        assert "1. THOR_clip_0.mp4" in content
        assert "2. THOR_clip_1.mp4" in content
        assert "3. THOR_clip_2.mp4" in content

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_no_timestamps_section_when_no_highlights(self, tmp_path):
        content = write_description(make_batch(), "THOR", [], tmp_path).read_text()
        assert "TIMESTAMPS" not in content

    def test_highlights_section_always_present(self, tmp_path):
        content = write_description(make_batch(), "THOR", [], tmp_path).read_text()
        assert "HIGHLIGHTS" in content

    def test_output_dir_created_if_missing(self, tmp_path):
        nested = tmp_path / "char" / "batch1"
        write_description(make_batch(), "THOR", [], nested)
        assert nested.exists()

    def test_multiple_highlights_all_written(self, tmp_path):
        highlights = [
            (60.0, 75.0, "QUAD", "a.mp4"),
            (300.0, 315.0, "PENTA", "b.mp4"),
        ]
        content = write_description(make_batch(), "THOR", highlights, tmp_path).read_text()
        assert "Quad Kill" in content
        assert "Penta Kill" in content

    # ── Idempotency ───────────────────────────────────────────────────────────

    def test_idempotent(self, tmp_path):
        highlights = [(60.0, 75.0, "QUAD", "clip.mp4")]
        batch = make_batch()
        out1 = write_description(batch, "THOR", highlights, tmp_path)
        out2 = write_description(batch, "THOR", highlights, tmp_path)
        assert out1 == out2
        assert out1.read_text() == out2.read_text()


class TestWriteDescriptionClipTiers:
    """Tests for the clip_tiers annotation feature in the HIGHLIGHTS list."""

    def _batch_with_known_names(self) -> Batch:
        clips = [
            Clip(path=Path(f"/videos/THOR_clip_{i}.mp4"), duration=30.0)
            for i in range(3)
        ]
        return Batch(number=1, clips=clips)

    def test_clip_tier_annotated_in_highlights(self, tmp_path):
        batch = self._batch_with_known_names()
        tiers = {"THOR_clip_0.mp4": "QUAD"}
        content = write_description(batch, "THOR", [], tmp_path, clip_tiers=tiers).read_text()
        assert "THOR_clip_0.mp4 [QUAD]" in content

    def test_clip_without_tier_has_no_annotation(self, tmp_path):
        batch = self._batch_with_known_names()
        tiers = {"THOR_clip_0.mp4": "QUAD"}  # only clip_0 has a tier
        content = write_description(batch, "THOR", [], tmp_path, clip_tiers=tiers).read_text()
        # clip_1 and clip_2 have no tier — no bracket suffix
        assert "THOR_clip_1.mp4 [" not in content
        assert "THOR_clip_2.mp4 [" not in content

    def test_all_clips_annotated(self, tmp_path):
        batch = self._batch_with_known_names()
        tiers = {
            "THOR_clip_0.mp4": "QUAD",
            "THOR_clip_1.mp4": "TRIPLE",
            "THOR_clip_2.mp4": "HEXA",
        }
        content = write_description(batch, "THOR", [], tmp_path, clip_tiers=tiers).read_text()
        assert "THOR_clip_0.mp4 [QUAD]" in content
        assert "THOR_clip_1.mp4 [TRIPLE]" in content
        assert "THOR_clip_2.mp4 [HEXA]" in content

    def test_no_clip_tiers_produces_no_annotation(self, tmp_path):
        batch = self._batch_with_known_names()
        content = write_description(batch, "THOR", [], tmp_path).read_text()
        assert "[" not in content

    def test_empty_clip_tiers_dict_produces_no_annotation(self, tmp_path):
        batch = self._batch_with_known_names()
        content = write_description(batch, "THOR", [], tmp_path, clip_tiers={}).read_text()
        assert "[" not in content

    def test_clip_tiers_idempotent(self, tmp_path):
        batch = self._batch_with_known_names()
        tiers = {"THOR_clip_0.mp4": "QUAD"}
        out1 = write_description(batch, "THOR", [], tmp_path, clip_tiers=tiers)
        out2 = write_description(batch, "THOR", [], tmp_path, clip_tiers=tiers)
        assert out1.read_text() == out2.read_text()


class TestWriteDescriptionOutStem:
    """Tests for the out_stem override parameter."""

    def test_default_stem_uses_char_and_batch_number(self, tmp_path):
        batch = make_batch(number=2)
        out = write_description(batch, "THOR", [], tmp_path)
        assert out.name == "THOR_batch2_description.txt"

    def test_custom_stem_used_in_filename(self, tmp_path):
        batch = make_batch()
        out = write_description(batch, "THOR", [], tmp_path, out_stem="THOR_Feb_2026")
        assert out.name == "THOR_Feb_2026_description.txt"

    def test_custom_stem_does_not_affect_content_char_name(self, tmp_path):
        batch = make_batch()
        out = write_description(batch, "STORM", [], tmp_path, out_stem="STORM_Mar_2026")
        assert "STORM" in out.read_text()
