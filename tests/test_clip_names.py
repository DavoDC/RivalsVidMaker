"""Tests for clip_names.tier_from_name: the KO tier embedded at the end of a clip file name."""

import clip_names


def test_tier_from_name_reads_the_upper_case_suffix():
    assert clip_names.tier_from_name("X_QUAD.mp4") == "QUAD"


def test_tier_from_name_reads_a_lower_case_suffix_and_returns_upper_case():
    assert clip_names.tier_from_name("x_quad.mp4") == "QUAD"


def test_tier_from_name_is_none_without_a_tier_suffix():
    assert clip_names.tier_from_name("X.mp4") is None
