"""
batcher.py - Group clips into ~N-minute batches.

Replaces C++: Batcher.cpp
"""

from dataclasses import dataclass, field

from clip_scanner import Clip

TARGET_SECONDS = 15 * 60  # 15 minutes


@dataclass
class Batch:
    number: int
    clips: list[Clip] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.clips)

    @property
    def duration_str(self) -> str:
        s = int(self.total_duration)
        return f"{s // 60}m {s % 60:02d}s"


def make_batches(clips: list[Clip], target: int = TARGET_SECONDS) -> list[Batch]:
    """
    Greedily pack clips into batches up to `target` seconds each.

    A clip is always added to the current batch before checking overflow -
    this matches the C++ behaviour where a clip is only sealed off when the
    *next* clip would exceed the limit, not the current one.
    """
    if not clips:
        return []

    batches: list[Batch] = []
    current = Batch(number=1)

    for clip in clips:
        # Seal the current batch if adding this clip would exceed the target
        # (but only if the batch already has at least one clip).
        if current.clips and (current.total_duration + clip.duration) > target:
            batches.append(current)
            current = Batch(number=len(batches) + 1)
        current.clips.append(clip)

    if current.clips:
        batches.append(current)

    return batches
