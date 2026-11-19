"""Which windows of a video have trustworthy timestamps.

The recorder sometimes stamps frames late (see "Parked problems" in
CLAUDE.md). A late stretch shows up as a pause in the stamps followed by
frames that repeat a stamp. So a window is used only if it is clean:

  - no frame in it repeats the previous frame's stamp, and
  - no step between two of its frames is longer than `max_step_seconds`.

Windows that fail are never sampled. Nothing is corrected.
"""

from itertools import accumulate

from .dataset import Video


def frames_per_window(video: Video, window_seconds: float) -> int:
    """How many frames a window holds in this video; 0 if the rate is unknown."""
    return round(window_seconds * video.frame_rate) if video.frame_rate else 0


def clean_starts(video: Video, frames: int, max_step_seconds: float) -> list[int]:
    """Frame numbers at which a clean window of `frames` frames can start."""
    times = video.times
    if not times or frames < 2 or len(times) < frames:
        return []
    limit = max_step_seconds * 1_000_000
    # bad[i] is 1 if the step from frame i to frame i + 1 is a repeat or a pause.
    bad = [int(b - a <= 0 or b - a > limit) for a, b in zip(times, times[1:])]
    upto = [0, *accumulate(bad)]            # upto[i] = bad steps before frame i
    return [
        first for first in range(len(times) - frames + 1)
        if upto[first + frames - 1] == upto[first]
    ]


def count_fitting(starts: list[int], frames: int) -> int:
    """How many windows fit without overlapping, given the allowed starts."""
    count, free_from = 0, 0
    for first in starts:                    # starts are in increasing order
        if first >= free_from:
            count, free_from = count + 1, first + frames
    return count


def removed_frames(n_frames: int, starts: list[int], frames: int) -> list[bool]:
    """For each frame of a video, True if no allowed window can contain it."""
    removed = [True] * n_frames
    done = 0                                # frames below this are already marked
    for first in starts:                    # starts are in increasing order
        for i in range(max(first, done), first + frames):
            removed[i] = False
        done = first + frames
    return removed
