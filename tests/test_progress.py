"""Tests for progress.py - AnimatedTicker animation frames and listeners."""

import logging

import progress
from progress import _DOTS, AnimatedTicker, add_listener, remove_listener


class TestListeners:
    def setup_method(self):
        progress._listeners.clear()

    def teardown_method(self):
        progress._listeners.clear()

    def test_listener_receives_done_total_label_on_increment(self):
        calls = []
        add_listener(lambda done, total, label: calls.append((done, total, label)))
        with AnimatedTicker("Scanning", total=3) as ticker:
            ticker.increment()
            ticker.increment()
        assert calls == [(1, 3, "Scanning"), (2, 3, "Scanning")]

    def test_remove_listener_stops_calls(self):
        calls = []

        def fn(done, total, label):
            calls.append(done)

        add_listener(fn)
        with AnimatedTicker("Scanning", total=3) as ticker:
            ticker.increment()
            remove_listener(fn)
            ticker.increment()
        assert calls == [1]

    def test_raising_listener_is_logged_and_ignored(self, caplog):
        calls = []

        def bad(done, total, label):
            raise RuntimeError("boom")

        add_listener(bad)
        add_listener(lambda done, total, label: calls.append(done))
        with caplog.at_level(logging.WARNING, logger="progress"):
            with AnimatedTicker("Scanning", total=2) as ticker:
                ticker.increment()
        assert calls == [1]
        assert any("boom" in r.getMessage() or "boom" in str(r.exc_info) for r in caplog.records)

    def test_stdout_identical_with_and_without_listener(self, capsys):
        def run():
            # interval=10 keeps the background thread from printing frames,
            # so the captured stdout is deterministic.
            with AnimatedTicker("Scanning", total=2, interval=10) as ticker:
                ticker.increment()
                ticker.increment()
            return capsys.readouterr().out

        without = run()
        add_listener(lambda done, total, label: None)
        with_listener = run()
        assert with_listener == without
        assert without.endswith("Scanning 2/2   \n")


class TestDots:
    def test_sequence_starts_with_single_dot(self):
        assert _DOTS[0] == "."

    def test_sequence_progresses_smoothly(self):
        for i in range(len(_DOTS) - 1):
            assert len(_DOTS[i]) < len(_DOTS[i + 1])

    def test_no_blank_frame(self):
        for frame in _DOTS:
            assert frame.strip() != ""
