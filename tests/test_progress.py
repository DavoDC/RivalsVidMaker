"""Tests for progress.py - AnimatedTicker animation frames."""

from progress import _DOTS


class TestDots:
    def test_sequence_starts_with_single_dot(self):
        assert _DOTS[0] == "."

    def test_sequence_progresses_smoothly(self):
        for i in range(len(_DOTS) - 1):
            assert len(_DOTS[i]) < len(_DOTS[i + 1])

    def test_no_blank_frame(self):
        for frame in _DOTS:
            assert frame.strip() != ""
