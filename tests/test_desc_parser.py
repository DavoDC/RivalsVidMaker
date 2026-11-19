"""Tests for src/desc_parser.py: parse old-compilation YouTube descriptions."""
from datetime import datetime
from pathlib import Path

from desc_parser import parse_description

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_video_list_fixture_has_19_clips():
    r = parse_description(_load("desc_iViRKtsnKu0_video_list.txt"))
    assert r["format"] == "video_list"
    assert len(r["clips"]) == 19


def test_video_list_first_clip_fields():
    r = parse_description(_load("desc_iViRKtsnKu0_video_list.txt"))
    c = r["clips"][0]
    assert c["index"] == 1
    assert c["raw_name"] == "Vid1_8-2-25_THOR_PENTA2_2025-02-08_17-59-27.mp4"
    assert c["character"] == "THOR"
    assert c["tier"] == "PENTA"
    assert c["capture_dt"] == datetime(2025, 2, 8, 17, 59, 27)
    assert c["timestamp_s"] is None


def test_video_list_clip_without_character_or_tier():
    r = parse_description(_load("desc_iViRKtsnKu0_video_list.txt"))
    c = r["clips"][15]
    assert c["index"] == 16
    assert c["raw_name"] == "Vid16_04_2025-05-08_23-11-35.mp4"
    assert c["character"] is None
    assert c["tier"] is None
    assert c["capture_dt"] == datetime(2025, 5, 8, 23, 11, 35)


def test_awakens_has_7_timestamps():
    r = parse_description(_load("desc_tm_udR3WUZE_timestamps.txt"))
    assert r["format"] == "timestamps"
    assert len(r["timestamps"]) == 7


def test_awakens_first_timestamp_range_and_label():
    r = parse_description(_load("desc_tm_udR3WUZE_timestamps.txt"))
    t = r["timestamps"][0]
    assert t["timestamp_s"] == 96
    assert t["end_s"] == 105
    assert t["label"] == "Quad Kill"


def test_awakens_highlight_list_keeps_capture_dt():
    r = parse_description(_load("desc_tm_udR3WUZE_timestamps.txt"))
    assert len(r["clips"]) == 31
    c = r["clips"][0]
    assert c["raw_name"] == "THOR_2026-02-01_23-06-24.mp4"
    assert c["character"] == "THOR"
    assert c["tier"] is None
    assert c["capture_dt"] == datetime(2026, 2, 1, 23, 6, 24)


def test_vod_without_list_gives_empty_clips():
    r = parse_description(_load("desc_7p35LSKonZ0_vod_none.txt"))
    assert r["format"] == "none"
    assert r["clips"] == []
    assert r["timestamps"] == []


def test_empty_text_is_none_format():
    r = parse_description("")
    assert r == {"clips": [], "timestamps": [], "format": "none", "unknown": []}


def test_pipeline_tier_suffix_after_datetime():
    text = "HIGHLIGHTS:\n1. THOR_2026-03-05_19-26-24_DOUBLE.mp4\n"
    c = parse_description(text)["clips"][0]
    assert c["character"] == "THOR"
    assert c["tier"] == "DOUBLE"
    assert c["capture_dt"] == datetime(2026, 3, 5, 19, 26, 24)


def test_two_word_character_is_kept_whole():
    text = "VIDS/DATES:\nSQUIRREL GIRL_2026-03-13_21-51-02.mp4\n"
    c = parse_description(text)["clips"][0]
    assert c["character"] == "SQUIRREL GIRL"
    assert c["raw_name"] == "SQUIRREL GIRL_2026-03-13_21-51-02.mp4"


def test_timestamp_forms_start_only_and_range():
    text = "TIMESTAMPS:\n1:43 - Quadra!\n1:36 - 1:45 = Quad Kill\n1:02:03 - Outro\n"
    ts = parse_description(text)["timestamps"]
    assert ts[0] == {"timestamp_s": 103, "end_s": None, "label": "Quadra!", "raw": "1:43 - Quadra!"}
    assert ts[1]["timestamp_s"] == 96 and ts[1]["end_s"] == 105 and ts[1]["label"] == "Quad Kill"
    assert ts[2]["timestamp_s"] == 3723


def test_unknown_lines_are_kept_not_dropped():
    text = "Video file: DOOM EVENT Fortnite 2024.10.06 - 01.59.39.01.mp4\nhello there\n"
    r = parse_description(text)
    assert r["clips"] == []
    assert "Video file: DOOM EVENT Fortnite 2024.10.06 - 01.59.39.01.mp4" in r["unknown"]
    assert "hello there" in r["unknown"]
