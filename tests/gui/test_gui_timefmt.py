import re
from datetime import datetime

from gui import timefmt


def test_stamp_formats_day_month_year_and_12_hour_clock():
    assert timefmt.stamp(datetime(2026, 11, 17, 14, 14)) == "17/11/2026 2:14pm"


def test_stamp_uses_am_and_no_leading_zero_on_the_hour():
    assert timefmt.stamp(datetime(2026, 1, 5, 0, 7)) == "05/01/2026 12:07am"


def test_stamp_accepts_iso_text():
    assert timefmt.stamp("2026-11-17T14:14:00") == "17/11/2026 2:14pm"


def test_stamp_none_is_a_dash_and_bad_text_comes_back_unchanged():
    assert timefmt.stamp(None) == "-"
    assert timefmt.stamp("not a time") == "not a time"


def test_duration_is_minutes_and_seconds_under_an_hour_without_zero_padded_minutes():
    assert timefmt.duration(905) == "15:05"
    assert timefmt.duration(0) == "0:00"
    assert timefmt.duration(300) == "5:00"
    assert timefmt.duration(425) == "7:05"


def test_duration_adds_hours_from_one_hour_up():
    assert timefmt.duration(3725) == "1:02:05"
    assert timefmt.duration(3600) == "1:00:00"


def test_duration_none_is_a_dash_and_negative_clamps_to_zero():
    assert timefmt.duration(None) == "-"
    assert timefmt.duration(-5) == "0:00"


def test_ago_seconds_minutes_hours_days():
    assert timefmt.ago(1) == "1s ago"
    assert timefmt.ago(200) == "3m ago"
    assert timefmt.ago(7200) == "2h ago"
    assert timefmt.ago(90000) == "1d ago"


def test_ago_negative_clamps_to_zero_seconds():
    assert timefmt.ago(-5) == "0s ago"
    assert re.fullmatch(r"\d+s ago", timefmt.ago(0))
