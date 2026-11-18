"""Uniform sampling over recorded time, with free start times.

A window may start at any instant of any video (3.21 s, say), as long as it
lies wholly inside that video. There is no fixed grid. The window begins at
the first frame at or after that instant and holds a fixed number of frames
(10 frames is 1 s at 10 fps), so every clip is the same length.

Windows are drawn one at a time. Each start is chosen uniformly from every
instant at which a window could start, across all videos, so longer videos
contribute proportionally more. A draw that would share a frame with a window
already chosen is discarded and drawn again, so no two windows overlap.

If the footage is too short to hold n windows, the draw stops after a fixed
number of attempts and returns as many as it found.
"""

from bisect import bisect_left, insort
from random import Random

from ..dataset import Video
from . import Window

ATTEMPTS_PER_WINDOW = 200   # give up after this many draws per window wanted


def sample(videos: list[Video], n: int, frames: int, seed: int) -> list[Window]:
    rng = Random(seed)

    # For each usable video, the span of instants at which a window may start:
    # from its first frame to the last frame that still has `frames` after it.
    usable = [v for v in videos if v.times and len(v.times) >= frames]
    room = [v.times[len(v.times) - frames] - v.times[0] + 1 for v in usable]
    total = sum(room)

    chosen: list[Window] = []
    taken: list[list[int]] = [[] for _ in usable]   # sorted first frames, per video
    for _ in range(ATTEMPTS_PER_WINDOW * n if total else 0):
        if len(chosen) == n:
            break
        index, instant = _locate(rng.randrange(total), usable, room)
        video = usable[index]
        first = bisect_left(video.times, instant)    # first frame at or after it
        if _overlaps(taken[index], first, frames):
            continue
        last = first + frames - 1
        chosen.append(Window(video, first, last, video.times[first], video.times[last]))
        insort(taken[index], first)
    return chosen


def _locate(position: int, usable: list[Video], room: list[int]) -> tuple[int, int]:
    """Turn a position along all the start spans laid end to end into
    (which video, instant in unix microseconds)."""
    for index, size in enumerate(room):
        if position < size:
            return index, usable[index].times[0] + position
        position -= size
    raise ValueError("position lies beyond the last video")


def _overlaps(taken: list[int], first: int, frames: int) -> bool:
    """Would a window starting at frame `first` share a frame with one
    already chosen in this video?"""
    at = bisect_left(taken, first)
    before = at > 0 and first - taken[at - 1] < frames
    after = at < len(taken) and taken[at] - first < frames
    return before or after
