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


def test_short_same_day_is_the_clock_alone():
    now = datetime(2026, 11, 18, 9, 0)
    assert timefmt.short(datetime(2026, 11, 18, 0, 50), now=now) == "12:50am"


def test_short_other_day_same_year_has_day_month_and_clock():
    now = datetime(2026, 11, 18, 9, 0)
    assert timefmt.short(datetime(2026, 11, 17, 23, 52), now=now) == "17 Nov 11:52pm"


def test_short_single_digit_day_has_no_leading_zero():
    now = datetime(2026, 11, 18, 9, 0)
    assert timefmt.short(datetime(2026, 11, 5, 9, 3), now=now) == "5 Nov 9:03am"


def test_short_other_year_is_day_month_and_year_with_no_clock():
    now = datetime(2026, 11, 18, 9, 0)
    assert timefmt.short(datetime(2025, 11, 17, 23, 52), now=now) == "17 Nov 2025"


def test_short_accepts_iso_text_like_stamp():
    assert timefmt.short("2026-11-17T14:14:00", now=datetime(2026, 11, 17, 20, 0)) == "2:14pm"


def test_short_none_is_a_dash_and_bad_text_comes_back_unchanged():
    assert timefmt.short(None) == "-"
    assert timefmt.short("not a time") == "not a time"


def test_short_defaults_now_to_the_current_local_time():
    assert re.fullmatch(r"\d{1,2}:\d{2}(am|pm)", timefmt.short(datetime.now()))
