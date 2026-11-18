"""Choose the windows to annotate.

Each strategy is a module in this package with one function:

    sample(videos, n, frames, seed) -> list[Window]

The strategy named in study.toml is loaded by name, so adding one means
adding a file here and nothing else.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module

from ..dataset import Video


@dataclass
class Window:
    """A stretch of one video, as chosen by a strategy."""

    video: Video
    start_frame: int     # first frame of the window
    end_frame: int       # last frame of the window (inclusive)
    start_time: int      # timestamp of the first frame, unix microseconds
    end_time: int        # timestamp of the last frame


@dataclass
class Segment:
    """One row of segments.csv: a window with its clip identifier."""

    segment_id: str      # e.g. "seg_0001"
    video_file: str      # e.g. "task_003_1669351394954942.avi"
    start_frame: int
    end_frame: int
    start_time: str      # timestamp of the first frame: ISO 8601, local time
    end_time: str        # timestamp of the last frame
    task: str            # e.g. "03:Tie shoelaces"; empty for unlabelled video

    FIELDS = (
        "segment_id", "video_file", "start_frame", "end_frame",
        "start_time", "end_time", "task",
    )


def draw(videos: list[Video], study: dict) -> list[Segment]:
    """Sample windows with the strategy in study.toml; number them in time order."""
    settings = study["sampling"]
    strategy = import_module(f"{__name__}.{settings['strategy']}")
    windows = strategy.sample(
        videos, settings["n_segments"], settings["frames_per_clip"], settings["seed"]
    )
    zone = timezone(timedelta(hours=study["source"]["utc_offset_hours"]))
    windows.sort(key=lambda w: w.start_time)
    return [
        Segment(
            segment_id=f"seg_{i:04d}",
            video_file=w.video.path.name,
            start_frame=w.start_frame,
            end_frame=w.end_frame,
            start_time=_iso(w.start_time, zone),
            end_time=_iso(w.end_time, zone),
            task=w.video.task_name or "",
        )
        for i, w in enumerate(windows, start=1)
    ]


def _iso(microseconds: int, zone: timezone) -> str:
    whole = datetime.fromtimestamp(microseconds // 1_000_000, zone)
    return whole.replace(microsecond=microseconds % 1_000_000).isoformat()
