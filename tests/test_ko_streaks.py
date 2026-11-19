"""Tests for ko_streaks.py: pure streak builder and boundary picker over synthetic timelines."""

import ko_streaks


def ev(t, tier):
    return {"ts": t, "tier": tier}


def test_empty_timeline_has_no_streaks():
    assert ko_streaks.build_streaks([]) == []


def test_single_ko_is_one_streak():
    streaks = ko_streaks.build_streaks([ev(10.0, "KO")])
    assert len(streaks) == 1
    assert streaks[0]["tier"] == "KO"
    assert streaks[0]["start_ts"] == 10.0
    assert streaks[0]["max_ts"] == 10.0


def test_rising_tiers_form_one_streak_with_start_and_max_time():
    events = [ev(6.0, "KO"), ev(7.0, "DOUBLE"), ev(12.0, "TRIPLE"), ev(20.0, "QUAD")]
    streaks = ko_streaks.build_streaks(events)
    assert len(streaks) == 1
    s = streaks[0]
    assert s["tier"] == "QUAD"
    assert s["start_ts"] == 6.0
    assert s["max_ts"] == 20.0
    assert s["end_ts"] == 20.0
    assert [e["tier"] for e in s["events"]] == ["KO", "DOUBLE", "TRIPLE", "QUAD"]


def test_seventeen_second_gap_between_triple_and_quad_stays_one_streak():
    events = [ev(0.0, "KO"), ev(6.0, "DOUBLE"), ev(23.0, "TRIPLE"), ev(40.0, "QUAD")]
    streaks = ko_streaks.build_streaks(events)
    assert len(streaks) == 1
    assert streaks[0]["tier"] == "QUAD"
    assert streaks[0]["start_ts"] == 0.0


def test_gap_longer_than_max_gap_splits_the_streak():
    events = [ev(0.0, "KO"), ev(30.0, "DOUBLE")]
    streaks = ko_streaks.build_streaks(events, max_gap=25.0)
    assert len(streaks) == 2
    assert streaks[1]["start_ts"] == 30.0
    assert streaks[1]["tier"] == "DOUBLE"


def test_ko_after_quad_starts_a_new_streak():
    events = [ev(0.0, "KO"), ev(5.0, "DOUBLE"), ev(9.0, "TRIPLE"), ev(14.0, "QUAD"), ev(20.0, "KO")]
    streaks = ko_streaks.build_streaks(events)
    assert [s["tier"] for s in streaks] == ["QUAD", "KO"]
    assert streaks[1]["start_ts"] == 20.0


def test_equal_tier_repeat_starts_a_new_streak():
    streaks = ko_streaks.build_streaks([ev(0.0, "DOUBLE"), ev(8.0, "DOUBLE")])
    assert len(streaks) == 2


def test_skipped_intermediate_tiers_are_allowed():
    streaks = ko_streaks.build_streaks([ev(0.0, "KO"), ev(10.0, "QUAD")])
    assert len(streaks) == 1
    assert streaks[0]["tier"] == "QUAD"


def test_events_may_be_tuples_and_unsorted():
    streaks = ko_streaks.build_streaks([(20.0, "QUAD"), (6.0, "KO"), (12.0, "TRIPLE")])
    assert len(streaks) == 1
    assert streaks[0]["start_ts"] == 6.0
    assert streaks[0]["tier"] == "QUAD"


def test_input_is_not_mutated():
    events = [ev(20.0, "QUAD"), ev(6.0, "KO")]
    snapshot = [dict(e) for e in events]
    ko_streaks.build_streaks(events)
    assert events == snapshot


# -- boundaries ---------------------------------------------------------------

def _streak(start, end):
    return {"tier": "QUAD", "start_ts": start, "max_ts": end, "end_ts": end, "events": []}


def test_picks_top_n_minus_one_peaks_sorted_by_time():
    peaks = [(100.0, 50.0), (50.0, 90.0), (200.0, 70.0), (150.0, 10.0)]
    boundaries, conf = ko_streaks.pick_boundaries(peaks, 3, [])
    assert boundaries == [50.0, 200.0]
    assert conf == 70.0 / 50.0


def test_min_spacing_drops_a_close_weaker_peak():
    peaks = [(50.0, 90.0), (54.0, 80.0), (100.0, 40.0)]
    boundaries, _ = ko_streaks.pick_boundaries(peaks, 3, [], min_spacing=8.0)
    assert boundaries == [50.0, 100.0]


def test_boundary_never_splits_a_streak():
    peaks = [(15.0, 99.0), (60.0, 50.0), (120.0, 40.0)]
    boundaries, _ = ko_streaks.pick_boundaries(peaks, 3, [_streak(10.0, 20.0)])
    assert 15.0 not in boundaries
    assert boundaries == [60.0, 120.0]


def test_boundary_at_streak_start_or_after_its_last_event_is_allowed():
    peaks = [(10.0, 99.0), (20.5, 98.0), (20.0, 97.0)]
    boundaries, _ = ko_streaks.pick_boundaries(peaks, 3, [_streak(10.0, 20.0)])
    assert boundaries == [10.0, 20.5]


def test_pad_extends_the_protected_span():
    peaks = [(22.0, 99.0), (60.0, 50.0)]
    boundaries, _ = ko_streaks.pick_boundaries(peaks, 2, [_streak(10.0, 20.0)], pad=3.0)
    assert boundaries == [60.0]


def test_too_few_peaks_reports_zero_confidence():
    boundaries, conf = ko_streaks.pick_boundaries([(50.0, 90.0)], 4, [])
    assert boundaries == [50.0]
    assert conf == 0.0


def test_single_segment_needs_no_boundaries():
    boundaries, conf = ko_streaks.pick_boundaries([(50.0, 90.0)], 1, [])
    assert boundaries == []
    assert conf is None


def test_confidence_is_none_when_no_runner_up_exists():
    boundaries, conf = ko_streaks.pick_boundaries([(50.0, 90.0), (100.0, 80.0)], 3, [])
    assert boundaries == [50.0, 100.0]
    assert conf is None
