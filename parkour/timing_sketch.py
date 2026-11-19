"""A made-up recording that shows how late timestamps arise.

Used only for the diagrams on the timing pages. It follows the recorder as
it is understood (see "Parked problems" in CLAUDE.md):

  - The camera films one frame per frame-time and notes the time of its
    latest frame in one shared place.
  - The writer saves frames in order. With each frame it saves whatever
    time is in the shared place at that moment.
  - Saving a frame takes two thirds of a frame-time, so the writer normally
    keeps up. If it is held up for a while, frames wait. It then saves them
    quickly, and they get the time of the moment they were saved.
"""

from dataclasses import dataclass
from pathlib import Path

from . import chart, timing
from .dataset import Video

THIRDS = 3          # time is counted in thirds of a frame-time, to stay exact
WRITE_COST = 2      # thirds of a frame-time needed to save one frame


@dataclass
class Sketch:
    frame_rate: float
    busy_at: int            # the frame at which the writer is held up
    busy_frames: int        # for how many frame-times
    times: list[int]        # the stamp saved with each frame, in microseconds
    late: list[int]         # how late each stamp is, in whole frame-times

    @property
    def stamps(self) -> list[int]:
        """Each stamp as a whole number of frame-times from the start."""
        return [number + late for number, late in enumerate(self.late)]

    @property
    def repeats(self) -> list[bool]:
        """True where a frame has the same stamp as the frame before it."""
        stamps = self.stamps
        return [False] + [b == a for a, b in zip(stamps, stamps[1:])]

    @property
    def caught_up_at(self) -> int:
        """The first frame after the hold-up whose stamp is right again."""
        return next(
            (i for i in range(self.busy_at, len(self.late)) if self.late[i] == 0),
            len(self.late),
        )


def record(n_frames: int, busy_at: int, busy_frames: int,
           frame_rate: float = 30.0) -> Sketch:
    """Film `n_frames`, holding the writer up once."""
    period = 1_000_000 / frame_rate
    free = 0                                    # when the writer is next free
    stamps = []
    for number in range(n_frames):
        begin = max(number * THIRDS, free)      # a frame cannot be saved before it is filmed
        if number == busy_at:
            begin = max(begin, (number + busy_frames) * THIRDS)
        free = begin + WRITE_COST
        stamps.append(begin // THIRDS)          # time of the camera's latest frame
    return Sketch(
        frame_rate=frame_rate,
        busy_at=busy_at,
        busy_frames=busy_frames,
        times=[round(s * period) for s in stamps],
        late=[s - number for number, s in enumerate(stamps)],
    )


@dataclass
class ExampleClip:
    first: int              # frame numbers
    last: int
    kept: bool
    reason: str


@dataclass
class RuleExample:
    """The rule in `timing.py` applied to a made-up recording."""

    sketch: Sketch
    removed_runs: list[tuple[int, int]]     # frames no allowed clip can contain
    clips: list[ExampleClip]


def rule_example(clip_seconds: float, max_step_seconds: float) -> RuleExample:
    """Four seconds of video with one hold-up, and four clips tried on it."""
    sketch = record(n_frames=120, busy_at=36, busy_frames=9)
    video = Video(Path("sketch.avi"), None, None, 0, len(sketch.times),
                  sketch.frame_rate, sketch.times)
    frames = timing.frames_per_window(video, clip_seconds)
    starts = set(allowed := timing.clean_starts(video, frames, max_step_seconds))
    removed = timing.removed_frames(len(sketch.times), allowed, frames)
    tried = [
        (3, "no gap and no repeat"),
        (22, "contains the gap"),
        (52, "contains repeated timestamps"),
        (len(sketch.times) - frames - 4, "no gap and no repeat"),
    ]
    return RuleExample(
        sketch=sketch,
        removed_runs=chart.runs(removed),
        clips=[ExampleClip(first, first + frames - 1, first in starts, reason)
               for first, reason in tried],
    )
