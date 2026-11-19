"""Tests for clip_names: tier_from_name, and standard_clip_name with its round trip through the parsers."""

import re
from datetime import datetime

import pytest

import clip_names

# Real names from the ClipArchive folder, used as fixtures. The folder itself is never read here.
REAL_ARCHIVE_NAMES = [
    "THOR_2026-02-06_21-25-38_QUAD.mp4",
    "THOR_2026-02-06_22-38-56_QUAD.mp4",
    "THOR_2026-02-21_20-31-53_HEXA.mp4",
    "THOR_2026-04-05_22-32-09_QUAD.mp4",
]

_NAME_RE = re.compile(r"^(?P<char>.+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})(?:_(?P<tier>[A-Z]+))?\.mp4$")


def _split_real_name(name):
    """Split a real archive name into (character, datetime, tier) with a plain regex, independent of the code under test."""
    m = _NAME_RE.match(name)
    dt = datetime.strptime(m.group("date") + " " + m.group("time"), "%Y-%m-%d %H-%M-%S")
    return m.group("char"), dt, m.group("tier")


def test_tier_from_name_reads_the_upper_case_suffix():
    assert clip_names.tier_from_name("X_QUAD.mp4") == "QUAD"


def test_tier_from_name_reads_a_lower_case_suffix_and_returns_upper_case():
    assert clip_names.tier_from_name("x_quad.mp4") == "QUAD"


def test_tier_from_name_is_none_without_a_tier_suffix():
    assert clip_names.tier_from_name("X.mp4") is None


def test_standard_name_matches_the_archive_for_thor_quad():
    name = clip_names.standard_clip_name("THOR", datetime(2026, 2, 6, 22, 38, 56), "QUAD")
    assert name == "THOR_2026-02-06_22-38-56_QUAD.mp4"


def test_standard_name_matches_the_archive_for_thor_hexa():
    name = clip_names.standard_clip_name("THOR", datetime(2026, 2, 21, 20, 31, 53), "HEXA")
    assert name == "THOR_2026-02-21_20-31-53_HEXA.mp4"


def test_standard_name_without_tier_is_the_raw_game_name():
    name = clip_names.standard_clip_name("THOR", datetime(2026, 2, 6, 22, 38, 56), None)
    assert name == "THOR_2026-02-06_22-38-56.mp4"


def test_standard_name_keeps_the_game_spacing_for_squirrel_girl():
    name = clip_names.standard_clip_name("SQUIRREL GIRL", datetime(2026, 3, 13, 21, 51, 2), None)
    assert name == "SQUIRREL GIRL_2026-03-13_21-51-02.mp4"


def test_standard_name_upper_cases_the_tier():
    name = clip_names.standard_clip_name("THOR", datetime(2026, 2, 6, 22, 38, 56), "penta")
    assert name == "THOR_2026-02-06_22-38-56_PENTA.mp4"


@pytest.mark.parametrize("name", REAL_ARCHIVE_NAMES)
def test_real_archive_names_round_trip_through_the_parsers(name):
    character, dt, tier = _split_real_name(name)
    rebuilt = clip_names.standard_clip_name(character, dt, tier)
    assert rebuilt == name
    stem = name[: -len(".mp4")]
    assert clip_names.extract_character(stem) == character
    assert clip_names.tier_from_name(name) == tier


def test_squirrel_girl_round_trips_to_the_folder_name_and_back():
    name = clip_names.standard_clip_name("SQUIRREL GIRL", datetime(2026, 3, 13, 21, 51, 2), "QUAD")
    assert clip_names.extract_character(name[: -len(".mp4")]) == "SQUIRREL_GIRL"
    assert clip_names.tier_from_name(name) == "QUAD"


def test_standard_name_rejects_a_character_the_parser_cannot_read():
    with pytest.raises(ValueError):
        clip_names.standard_clip_name("1THOR", datetime(2026, 2, 6, 22, 38, 56), None)


def test_standard_name_rejects_an_unknown_tier():
    with pytest.raises(ValueError):
        clip_names.standard_clip_name("THOR", datetime(2026, 2, 6, 22, 38, 56), "MEGA")
