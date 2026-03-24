"""
Tests for ai_prompt.py — AI prompt Markdown generator.
"""

from pathlib import Path

import pytest

from ai_prompt import _ko_summary, write_ai_prompts


# ── _ko_summary ───────────────────────────────────────────────────────────────

class TestKoSummary:

    def test_empty_returns_no_kills(self):
        assert _ko_summary({}) == "(no Quad+ kills detected)"

    def test_single_tier(self):
        result = _ko_summary({"QUAD": 2})
        assert "2x QUAD" in result

    def test_multiple_tiers_ordered_hexa_first(self):
        result = _ko_summary({"QUAD": 3, "HEXA": 1, "PENTA": 2})
        hexa_pos = result.index("HEXA")
        penta_pos = result.index("PENTA")
        quad_pos = result.index("QUAD")
        assert hexa_pos < penta_pos < quad_pos

    def test_unknown_tier_appended(self):
        result = _ko_summary({"UNKNOWN_TIER": 1})
        assert "UNKNOWN_TIER" in result


# ── write_ai_prompts ──────────────────────────────────────────────────────────

def _call_write(tmp_path: Path, ko_tiers: dict | None = None) -> Path:
    desc = tmp_path / "THOR_Feb_2026_description.txt"
    desc.write_text("stub")
    effective_tiers = {"QUAD": 3} if ko_tiers is None else ko_tiers
    return write_ai_prompts(
        out_dir=tmp_path,
        char_name="THOR",
        clip_count=9,
        date_range="Feb–Mar 2026",
        ko_tiers=effective_tiers,
        description_path=desc,
        out_stem="THOR_Feb-Mar_2026",
    )


class TestWriteAiPrompts:

    def test_returns_path_in_out_dir(self, tmp_path):
        path = _call_write(tmp_path)
        assert path.parent == tmp_path

    def test_filename_ends_with_ai_prompts(self, tmp_path):
        path = _call_write(tmp_path)
        assert path.name.endswith("_ai_prompts.md")

    def test_file_is_written(self, tmp_path):
        path = _call_write(tmp_path)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_contains_character_name(self, tmp_path):
        path = _call_write(tmp_path)
        content = path.read_text()
        assert "THOR" in content

    def test_contains_date_range(self, tmp_path):
        path = _call_write(tmp_path)
        content = path.read_text()
        assert "Feb" in content

    def test_contains_kill_summary(self, tmp_path):
        path = _call_write(tmp_path, ko_tiers={"QUAD": 3, "PENTA": 1})
        content = path.read_text()
        assert "QUAD" in content
        assert "PENTA" in content

    def test_no_kills_message_when_empty(self, tmp_path):
        path = _call_write(tmp_path, ko_tiers={})
        content = path.read_text().lower()
        assert "no quad+" in content or "no kills" in content

    def test_contains_three_prompts(self, tmp_path):
        path = _call_write(tmp_path)
        content = path.read_text()
        # All three prompt headings must be present
        assert "Prompt 1" in content
        assert "Prompt 2" in content
        assert "Prompt 3" in content

    def test_creates_out_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "nested" / "dir"
        desc = tmp_path / "desc.txt"
        desc.write_text("stub")
        write_ai_prompts(
            out_dir=new_dir,
            char_name="STORM",
            clip_count=5,
            date_range="Mar 2026",
            ko_tiers={"QUAD": 1},
            description_path=desc,
            out_stem="STORM_Mar_2026",
        )
        assert new_dir.is_dir()

    def test_idempotent_second_call_overwrites(self, tmp_path):
        """Calling write_ai_prompts twice with the same inputs produces the same output."""
        path1 = _call_write(tmp_path)
        content1 = path1.read_text()
        path2 = _call_write(tmp_path)
        content2 = path2.read_text()
        assert path1 == path2
        assert content1 == content2
