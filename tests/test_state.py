"""Tests for state.py - output folder state log (YouTube confirmed, etc.)."""

import json
from pathlib import Path

import pytest

from state import is_youtube_confirmed, load, mark_youtube_confirmed, save


class TestLoad:
    def test_missing_file_returns_empty_state(self, tmp_path):
        state = load(tmp_path / "state.json")
        assert state == {"output_folders": {}}

    def test_loads_existing_file(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps({"output_folders": {"thor_vid1": {"youtube_confirmed": True}}}))
        state = load(p)
        assert state["output_folders"]["thor_vid1"]["youtube_confirmed"] is True

    def test_corrupt_file_returns_empty_state(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("not valid json")
        state = load(p)
        assert state == {"output_folders": {}}


class TestSave:
    def test_writes_json_file(self, tmp_path):
        p = tmp_path / "state.json"
        save({"output_folders": {}}, p)
        assert p.exists()

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "state.json"
        original = {"output_folders": {"thor_vid1": {"youtube_confirmed": True, "confirmed_at": "2026-03-28T00:00:00"}}}
        save(original, p)
        assert load(p) == original

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "state.json"
        save({"output_folders": {}}, p)
        assert p.exists()


class TestIsYoutubeConfirmed:
    def test_returns_false_for_unknown_folder(self):
        state = {"output_folders": {}}
        assert is_youtube_confirmed(state, "thor_vid1") is False

    def test_returns_true_when_confirmed(self):
        state = {"output_folders": {"thor_vid1": {"youtube_confirmed": True}}}
        assert is_youtube_confirmed(state, "thor_vid1") is True

    def test_returns_false_when_explicitly_false(self):
        state = {"output_folders": {"thor_vid1": {"youtube_confirmed": False}}}
        assert is_youtube_confirmed(state, "thor_vid1") is False


class TestMarkYoutubeConfirmed:
    def test_sets_confirmed_flag(self):
        state = {"output_folders": {}}
        state = mark_youtube_confirmed(state, "thor_vid1")
        assert state["output_folders"]["thor_vid1"]["youtube_confirmed"] is True

    def test_sets_confirmed_at_timestamp(self):
        state = {"output_folders": {}}
        state = mark_youtube_confirmed(state, "thor_vid1")
        assert "confirmed_at" in state["output_folders"]["thor_vid1"]
        assert state["output_folders"]["thor_vid1"]["confirmed_at"] is not None

    def test_does_not_affect_other_folders(self):
        state = {"output_folders": {"thor_vid2": {"youtube_confirmed": False}}}
        state = mark_youtube_confirmed(state, "thor_vid1")
        assert is_youtube_confirmed(state, "thor_vid2") is False

    def test_overwrites_existing_entry(self):
        state = {"output_folders": {"thor_vid1": {"youtube_confirmed": False, "confirmed_at": None}}}
        state = mark_youtube_confirmed(state, "thor_vid1")
        assert is_youtube_confirmed(state, "thor_vid1") is True

    def test_works_on_empty_state(self):
        state = {}
        state = mark_youtube_confirmed(state, "thor_vid1")
        assert is_youtube_confirmed(state, "thor_vid1") is True
