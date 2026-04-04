"""
Tests for menu.py - two-level action picker.

Questionary calls are mocked so tests run non-interactively.
"""

import math
from pathlib import Path
from unittest.mock import patch

import pytest

from menu import _char_label, _folder1_label, _output_label, pick_action


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

class TestCharLabel:
    def test_ready(self):
        label = _char_label("THOR", 31, "16m 34s", 2, "Ready")
        assert "THOR" in label

    def test_too_short(self):
        label = _char_label("SQUIRREL_GIRL", 14, "6m 11s", 1, "Too short")
        assert "SQUIRREL_GIRL" in label

    def test_zero_clips(self):
        label = _char_label("DOCTOR_STRANGE", 0, "-", 0, "Too short")
        assert "DOCTOR_STRANGE" in label


class TestFolder1Label:
    def test_highlights_with_ready(self):
        label = _folder1_label("Highlights", summary="THOR ready, 3 too short")
        assert "Highlights" in label
        assert "THOR ready" in label

    def test_output_with_info(self):
        label = _folder1_label("Output", summary="2 folders")
        assert "Output" in label

    def test_archive_empty(self):
        label = _folder1_label("Archive", summary="empty")
        assert "Archive" in label
        assert "empty" in label


class TestOutputLabel:
    def test_not_confirmed(self):
        row = {"name": "thor_vid1", "age": "1w", "has_clips": True}
        label = _output_label(row, yt_confirmed=False)
        assert "thor_vid1" in label
        assert "yt" in label.lower()

    def test_confirmed_with_clips(self):
        row = {"name": "thor_vid1", "age": "1w", "has_clips": True}
        label = _output_label(row, yt_confirmed=True)
        assert "thor_vid1" in label
        assert "cleanup" in label.lower()

    def test_confirmed_no_clips(self):
        row = {"name": "thor_vid1", "age": "1w", "has_clips": False}
        label = _output_label(row, yt_confirmed=True)
        assert "thor_vid1" in label


# ---------------------------------------------------------------------------
# pick_action - mock questionary to simulate user choices
# ---------------------------------------------------------------------------

def _make_char_folders(tmp_path):
    folders = []
    for name in ["THOR", "SQUIRREL_GIRL"]:
        d = tmp_path / name
        d.mkdir()
        folders.append(d)
    return folders


class TestPickAction:
    def test_quit_returns_quit(self, tmp_path):
        char_folders = _make_char_folders(tmp_path)
        summaries = [(31, 900.0), (14, 371.0)]
        output_rows = []

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = "quit"
            result = pick_action(char_folders, summaries, output_rows, {}, target_batch_seconds=900)

        assert result["type"] == "quit"

    def test_highlights_then_character_returns_compile(self, tmp_path):
        char_folders = _make_char_folders(tmp_path)
        summaries = [(31, 900.0), (14, 371.0)]
        output_rows = []

        with patch("menu.questionary.select") as mock_select:
            # Level 1: pick Highlights; Level 2: pick THOR
            mock_select.return_value.ask.side_effect = ["highlights", str(char_folders[0])]
            result = pick_action(char_folders, summaries, output_rows, {}, target_batch_seconds=900)

        assert result["type"] == "compile"
        assert result["folder"] == char_folders[0]

    def test_highlights_then_preprocess_returns_preprocess(self, tmp_path):
        char_folders = _make_char_folders(tmp_path)
        summaries = [(31, 900.0), (14, 371.0)]

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.side_effect = ["highlights", "preprocess"]
            result = pick_action(char_folders, summaries, [], {}, target_batch_seconds=900)

        assert result["type"] == "preprocess"

    def test_highlights_then_back_loops_to_level1(self, tmp_path):
        char_folders = _make_char_folders(tmp_path)
        summaries = [(31, 900.0), (14, 371.0)]

        with patch("menu.questionary.select") as mock_select:
            # Back from highlights, then quit
            mock_select.return_value.ask.side_effect = ["highlights", "back", "quit"]
            result = pick_action(char_folders, summaries, [], {}, target_batch_seconds=900)

        assert result["type"] == "quit"

    def test_output_then_folder_returns_cleanup(self, tmp_path):
        char_folders = []
        output_rows = [{"name": "thor_vid1", "age": "1w", "has_clips": True}]
        output_path = tmp_path / "Output"
        output_path.mkdir()

        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.side_effect = ["output", "thor_vid1"]
            result = pick_action(char_folders, [], output_rows, {}, target_batch_seconds=900,
                                 output_path=output_path)

        assert result["type"] == "cleanup"
        assert result["folder"].name == "thor_vid1"

    def test_ctrl_c_returns_quit(self, tmp_path):
        char_folders = _make_char_folders(tmp_path)
        with patch("menu.questionary.select") as mock_select:
            mock_select.return_value.ask.return_value = None  # questionary returns None on Ctrl+C
            result = pick_action(char_folders, [(31, 900.0), (14, 371.0)], [], {}, target_batch_seconds=900)

        assert result["type"] == "quit"
