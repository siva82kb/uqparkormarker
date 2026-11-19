"""Uniform sampling: every allowed window is equally likely.

Each video offers the frames at which a window may start (see timing.py for
which are allowed). A window may start at any of them, so there is no fixed
grid: a 1 s window can run from 3.21 s to 4.21 s.

Windows are drawn one at a time. Each draw picks one allowed start, with
every allowed start in every video equally likely, so longer videos
contribute proportionally more. A draw that would share a frame with a window
already chosen is discarded and drawn again, so no two windows overlap.

If the footage is too short to hold n windows, the draw stops after a fixed
number of attempts and returns as many as it found.
"""

from bisect import bisect_left, insort
from random import Random

from . import Pool, Window

ATTEMPTS_PER_WINDOW = 200   # give up after this many draws per window wanted


def sample(pools: list[Pool], n: int, seed: int) -> list[Window]:
    rng = Random(seed)
    pools = [p for p in pools if p.starts]
    total = sum(len(p.starts) for p in pools)

    chosen: list[Window] = []
    taken: list[list[int]] = [[] for _ in pools]    # sorted first frames, per video
    for _ in range(ATTEMPTS_PER_WINDOW * n if total else 0):
        if len(chosen) == n:
            break
        index, first = _locate(rng.randrange(total), pools)
        frames = pools[index].frames
        if _overlaps(taken[index], first, frames):
            continue
        chosen.append(Window(pools[index].video, first, first + frames - 1))
        insort(taken[index], first)
    return chosen


def _locate(position: int, pools: list[Pool]) -> tuple[int, int]:
    """Turn a position along all the allowed starts laid end to end into
    (which video, first frame)."""
    for index, pool in enumerate(pools):
        if position < len(pool.starts):
            return index, pool.starts[position]
        position -= len(pool.starts)
    raise ValueError("position lies beyond the last video")


def _overlaps(taken: list[int], first: int, frames: int) -> bool:
    """Would a window starting at frame `first` share a frame with one
    already chosen in this video?"""
    at = bisect_left(taken, first)
    before = at > 0 and first - taken[at - 1] < frames
    after = at < len(taken) and taken[at] - first < frames
    return before or after
