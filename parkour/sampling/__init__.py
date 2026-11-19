"""Choose the windows to annotate.

`draw` works out, for every video, how long a window is in frames and at
which frames a window with trustworthy timestamps may start (timing.py). It
hands those pools to the strategy named in study.toml, which picks from them.

Each strategy is a module in this package with one function:

    sample(pools, n, seed) -> list[Window]

so adding a strategy means adding a file here and nothing else.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import import_module

from .. import timing
from ..dataset import Video


@dataclass
class Pool:
    """What one video offers for sampling."""

    video: Video
    frames: int          # length of a window in this video
    starts: list[int]    # frames at which a window may start, in increasing order


@dataclass
class Window:
    """A stretch of one video, as chosen by a strategy."""

    video: Video
    start_frame: int     # first frame of the window
    end_frame: int       # last frame of the window (inclusive)


@dataclass
class Segment:
    """One row of segments.csv: a window with its clip identifier."""

    segment_id: str      # e.g. "seg_0001"
    video_file: str      # e.g. "task_003_1669351394954942.avi"
    start_frame: int
    end_frame: int
    start_time: str      # timestamp of the first frame: ISO 8601, local time
    end_time: str        # timestamp of the last frame
    task: str            # e.g. "Tie shoelaces"; empty for unlabelled video

    FIELDS = (
        "segment_id", "video_file", "start_frame", "end_frame",
        "start_time", "end_time", "task",
    )


def pools(videos: list[Video], study: dict) -> list[Pool]:
    """For each video, the window length and the allowed window starts."""
    seconds = study["sampling"]["window_seconds"]
    max_step = study["timing"]["max_step_seconds"]
    result = []
    for video in videos:
        frames = timing.frames_per_window(video, seconds)
        result.append(Pool(video, frames, timing.clean_starts(video, frames, max_step)))
    return result


def quotas(settings: dict) -> dict[str, int] | None:
    """How many clips are wanted from task video and from unlabelled video.

    `task_share` in study.toml is the share to take from task video; the rest
    come from unlabelled video. None if no share is set, in which case clips
    are drawn from all videos together.
    """
    share = settings.get("task_share")
    if share is None:
        return None
    task = round(settings["n_segments"] * share)
    return {"task": task, "unlabelled": settings["n_segments"] - task}


def draw(videos: list[Video], study: dict) -> list[Segment]:
    """Sample windows with the strategy in study.toml; number them in time order.

    With a `task_share`, task video and unlabelled video are sampled
    separately, each for its own number of clips. If one kind cannot supply
    its number, the total falls short; the other kind does not make it up.
    """
    settings = study["sampling"]
    strategy = import_module(f"{__name__}.{settings['strategy']}")
    offered, wanted, seed = pools(videos, study), quotas(settings), settings["seed"]
    if wanted is None:
        windows = strategy.sample(offered, settings["n_segments"], seed)
    else:
        task = [p for p in offered if p.video.is_task]
        unlabelled = [p for p in offered if not p.video.is_task]
        windows = (strategy.sample(task, wanted["task"], seed)
                   + strategy.sample(unlabelled, wanted["unlabelled"], seed + 1))

    zone = timezone(timedelta(hours=study["source"]["utc_offset_hours"]))
    windows.sort(key=lambda w: w.video.times[w.start_frame])
    return [
        Segment(
            segment_id=f"seg_{i:04d}",
            video_file=w.video.path.name,
            start_frame=w.start_frame,
            end_frame=w.end_frame,
            start_time=_iso(w.video.times[w.start_frame], zone),
            end_time=_iso(w.video.times[w.end_frame], zone),
            task=w.video.task_name or "",
        )
        for i, w in enumerate(windows, start=1)
    ]


def _iso(microseconds: int, zone: timezone) -> str:
    whole = datetime.fromtimestamp(microseconds // 1_000_000, zone)
    return whole.replace(microsecond=microseconds % 1_000_000).isoformat()
