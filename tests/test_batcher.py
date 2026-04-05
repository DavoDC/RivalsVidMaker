"""
Tests for batcher.py - clip grouping logic.
"""

from pathlib import Path

import pytest

from batcher import Batch, make_batches
from clip_scanner import Clip


def make_clips(durations: list[float]) -> list[Clip]:
    return [Clip(path=Path(f"clip_{i}.mp4"), duration=d) for i, d in enumerate(durations)]


class TestMakeBatches:

    # ── Golden path ───────────────────────────────────────────────────────────

    def test_single_batch_when_all_clips_fit(self):
        clips = make_clips([30.0] * 30)      # 900s total, exactly at target
        batches = make_batches(clips, target=900)
        assert len(batches) == 1
        assert len(batches[0].clips) == 30

    def test_splits_to_second_batch_on_overflow(self):
        # 30 clips × 30s = 900s fits; 31st clip pushes total to 930s → spills
        clips = make_clips([30.0] * 31)
        batches = make_batches(clips, target=900)
        assert len(batches) == 2
        assert len(batches[0].clips) == 30
        assert len(batches[1].clips) == 1

    def test_batch_numbers_are_sequential(self):
        clips = make_clips([500.0, 500.0, 500.0])
        batches = make_batches(clips, target=900)
        assert [b.number for b in batches] == [1, 2, 3]

    def test_total_duration_is_sum_of_clips(self):
        clips = make_clips([10.0, 20.0, 30.0])
        batches = make_batches(clips, target=900)
        assert batches[0].total_duration == pytest.approx(60.0)

    def test_duration_str_format(self):
        clips = make_clips([90.0])   # 1m 30s
        batches = make_batches(clips, target=900)
        assert batches[0].duration_str == "1m 30s"

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_empty_list_returns_empty(self):
        assert make_batches([]) == []

    def test_single_clip(self):
        clips = make_clips([60.0])
        batches = make_batches(clips, target=900)
        assert len(batches) == 1
        assert batches[0].clips[0].duration == 60.0

    def test_clip_longer_than_target_goes_in_its_own_batch(self):
        # A single oversized clip must still be included
        clips = make_clips([1200.0])
        batches = make_batches(clips, target=900)
        assert len(batches) == 1

    def test_all_clips_longer_than_target(self):
        clips = make_clips([1000.0, 1000.0, 1000.0])
        batches = make_batches(clips, target=900)
        assert len(batches) == 3

    # ── Idempotency ───────────────────────────────────────────────────────────

    def test_idempotent(self):
        clips = make_clips([30.0] * 10)
        b1 = make_batches(clips, target=900)
        b2 = make_batches(clips, target=900)
        assert len(b1) == len(b2)
        assert [len(b.clips) for b in b1] == [len(b.clips) for b in b2]
