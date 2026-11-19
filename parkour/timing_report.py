"""Numbers and series for the docs pages on timestamps, from one subject's videos.

Pure calculation: no file access and no HTML. It measures how late the
stamps are (`lag.py`), applies the rule that chooses clips (`timing.py`),
and compares the two. It changes nothing about which clips are chosen.

A frame is called *removed* if no allowed clip can contain it, and *kept*
otherwise.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import chart, lag, summary, timing
from .chart import Axis
from .dataset import Video

LATE_SECONDS = 0.2          # "clearly late", for the headline share
SESSION_BINS = 200          # columns in the whole-session chart
STRETCH_FLOOR = 0.03        # a late stretch lasts while the lag stays above this
STRETCH_PAD = 20            # frames shown either side of the stretch
STRETCH_MAX = 240           # most frames shown
LAG_BANDS = [(0, 25), (25, 50), (50, 75), (75, 100), (100, 200), (200, 400), (400, None)]
MOST_AFFECTED = 8           # rows in the table of videos that lose most


@dataclass
class Frame:
    """One frame of the stretch shown in close-up."""

    number: int
    step_ms: float | None   # from the previous frame's stamp; None for frame 0
    lag_ms: float
    repeat: bool
    pause: bool
    removed: bool


@dataclass
class Stretch:
    title: str              # which video it is from
    frames: list[Frame]
    removed_runs: list[tuple[int, int]]     # first and last frame number
    frame_axis: Axis
    lag_axis: Axis
    step_axis: Axis


@dataclass
class Column:
    """Worst lag in one slice of the session."""

    left: float             # percent along the session
    width: float
    lag_ms: float
    clock: str


@dataclass
class Band:
    label: str
    count: int
    share: float


@dataclass
class VideoLoss:
    label: str
    clock: str
    seconds: float
    removed_seconds: float
    worst_lag_ms: float


@dataclass
class Report:
    n_frames: int
    n_repeats: int
    n_pauses: int
    longest_step: float             # seconds
    share_late: float               # frames at least LATE_SECONDS late
    worst_lag: float                # seconds
    missing_seconds: float          # session length by the stamps, minus frames at the nominal rate
    missing_between: float          # of that, at the changes from one video file to the next
    missing_within: float           # of that, inside videos
    missing_worst: VideoLoss | None # the video with the most; its removed_seconds holds the amount
    steps: list[Band]

    stretch: Stretch | None
    columns: list[Column]
    column_axis: Axis
    removed_spans: list[tuple[float, float]]    # left and width, percent
    timeline: list[summary.Span]
    ticks: list[tuple[str, float]]

    n_kept: int                     # frames
    n_removed: int
    kept_worst_lag: float           # seconds
    kept_bands: list[Band]
    removed_bands: list[Band]
    late_caught: tuple[int, int]    # frames over max_step late: removed, all

    clips_possible: int
    clips_allowed: int
    task_clips_possible: int
    task_clips_allowed: int
    n_tasks: int
    lost_tasks: list[str]
    removed_seconds: float
    losses: list[VideoLoss]

    clip_seconds: float             # what a clip is meant to cover
    n_long_clips: int               # allowed clips whose stamps span more than that
    longest_clip: float             # seconds from first to last stamp, the longest allowed clip

    @property
    def share_long_clips(self) -> float:
        return self.n_long_clips / self.clips_allowed if self.clips_allowed else 0.0

    @property
    def share_kept(self) -> float:
        return self.clips_allowed / self.clips_possible if self.clips_possible else 0.0

    @property
    def task_share_kept(self) -> float:
        possible = self.task_clips_possible
        return self.task_clips_allowed / possible if possible else 0.0


@dataclass
class _Measured:
    """One video with its lags and the rule applied."""

    video: Video
    lags: list[float]
    steps: list[float]      # seconds; steps[i] is from frame i to frame i + 1
    removed: list[bool]
    allowed: int            # clip starts the rule allows
    possible: int
    spans: list[float]      # seconds from first to last stamp, for each allowed clip


def build(videos: list[Video], study: dict) -> Report | None:
    """The report, or None if no video is long enough to hold a clip."""
    seconds = study["sampling"]["window_seconds"]
    max_step = study["timing"]["max_step_seconds"]
    zone = timezone(timedelta(hours=study["source"]["utc_offset_hours"]))
    usable = [v for v in videos if v.times]
    measured = [m for v in usable if (m := _measure(v, seconds, max_step))]
    if not measured:
        return None

    all_lags = [x for m in measured for x in m.lags]
    all_steps = [s for m in measured for s in m.steps]
    kept = [x for m in measured for x, gone in zip(m.lags, m.removed) if not gone]
    removed = [x for m in measured for x, gone in zip(m.lags, m.removed) if gone]
    origin = usable[0].times[0]
    span = (max(v.times[-1] for v in usable) - origin) or 1
    start, end = _local(origin, zone), _local(origin + span, zone)
    columns = _columns(measured, origin, span, zone)
    tasks = {v.task_number for v in usable if v.is_task}
    alive = {m.video.task_number for m in measured if m.video.is_task and m.allowed}
    names = {v.task_number: summary.task_title(v) for v in usable if v.is_task}

    return Report(
        n_frames=len(all_lags),
        n_repeats=sum(s <= 0 for s in all_steps),
        n_pauses=sum(s > max_step for s in all_steps),
        longest_step=max(all_steps),
        share_late=sum(x >= LATE_SECONDS for x in all_lags) / len(all_lags),
        worst_lag=max(all_lags),
        missing_seconds=_missing(usable, span),
        missing_between=_missing(usable, span) - sum(_excess(v) for v in usable),
        missing_within=sum(_excess(v) for v in usable),
        missing_worst=_most_missing(usable, zone),
        steps=_bands([s * 1000 for s in all_steps], _step_bands(max_step)),
        stretch=_stretch(max(measured, key=lambda m: max(m.lags)), max_step),
        columns=columns,
        column_axis=chart.axis(0, max(c.lag_ms for c in columns), about=4),
        removed_spans=_removed_spans(measured, origin, span),
        timeline=summary.timeline(usable),
        ticks=summary.ticks(start, end),
        n_kept=len(kept),
        n_removed=len(removed),
        kept_worst_lag=max(kept, default=0.0),
        kept_bands=_lag_bands(kept),
        removed_bands=_lag_bands(removed),
        late_caught=(sum(x > max_step for x in removed),
                     sum(x > max_step for x in all_lags)),
        clips_possible=sum(m.possible for m in measured),
        clips_allowed=sum(m.allowed for m in measured),
        task_clips_possible=sum(m.possible for m in measured if m.video.is_task),
        task_clips_allowed=sum(m.allowed for m in measured if m.video.is_task),
        n_tasks=len(tasks),
        lost_tasks=[names[n] for n in sorted(tasks - alive)],
        removed_seconds=sum(sum(m.removed) / m.video.frame_rate for m in measured),
        losses=_losses(measured, zone),
        clip_seconds=seconds,
        n_long_clips=sum(s > seconds for m in measured for s in m.spans),
        longest_clip=max((s for m in measured for s in m.spans), default=0.0),
    )


def _measure(video: Video, clip_seconds: float, max_step: float) -> _Measured | None:
    """Lags and the rule for one video; None if it is too short for a clip."""
    frames = timing.frames_per_window(video, clip_seconds)
    times = video.times
    if frames < 2 or len(times) < frames:
        return None
    starts = timing.clean_starts(video, frames, max_step)
    return _Measured(
        video=video,
        lags=lag.lags(times, video.frame_rate),
        steps=[(b - a) / 1e6 for a, b in zip(times, times[1:])],
        removed=timing.removed_frames(len(times), starts, frames),
        allowed=len(starts),
        possible=len(times) - frames + 1,
        spans=[(times[first + frames - 1] - times[first]) / 1e6 for first in starts],
    )


def _missing(usable: list[Video], span: int) -> float:
    """Session length by the stamps, minus the length the frames account for."""
    filmed = sum(len(v.times) / v.frame_rate for v in usable if v.frame_rate)
    return span / 1e6 - filmed


def _excess(video: Video) -> float:
    """Seconds by which a video is longer, by its stamps, than its frames
    account for at the nominal rate. Frames that are missing make it positive."""
    if not video.frame_rate:
        return 0.0
    return summary.duration(video) - (len(video.times) - 1) / video.frame_rate


def _most_missing(usable: list[Video], zone: timezone) -> VideoLoss | None:
    """The video whose stamps run furthest ahead of its frame count."""
    worst = max(usable, key=_excess, default=None)
    if worst is None or _excess(worst) <= 0:
        return None
    return VideoLoss(
        label=_label(worst),
        clock=_local(worst.times[0], zone).strftime("%H:%M:%S"),
        seconds=summary.duration(worst),
        removed_seconds=_excess(worst),
        worst_lag_ms=0.0,
    )


def _bands(values: list[float], bands: list[tuple]) -> list[Band]:
    """Count values into labelled bands: (label, lowest, highest or None)."""
    total = len(values) or 1
    found = []
    for label, low, high in bands:
        count = sum(
            (low is None or v >= low) and (high is None or v < high) for v in values
        )
        found.append(Band(label, count, count / total))
    return found


def _step_bands(max_step: float) -> list[tuple]:
    """Bands for the steps between stamps; the last starts at the rule's limit."""
    limit = max_step * 1000
    return [                # label, lowest (ms, inclusive), highest (ms, exclusive)
        ("Exactly 0 (repeated timestamp)", None, 0.0005),
        ("Up to 20 ms", 0.0005, 20),
        ("20 to 45 ms (normal)", 20, 45),
        (f"45 to {limit:g} ms", 45, limit),
        (f"Over {limit:g} ms (gap)", limit, None),
    ]


def _lag_bands(lags_seconds: list[float]) -> list[Band]:
    bands = [
        (f"{low} to {high} ms" if high else f"Over {low} ms", low, high)
        for low, high in LAG_BANDS
    ]
    return _bands([x * 1000 for x in lags_seconds], bands)


def _stretch(m: _Measured, max_step: float) -> Stretch:
    """The frames around the largest lag in a video, for the close-up."""
    peak = max(range(len(m.lags)), key=m.lags.__getitem__)
    first = last = peak
    while first > 0 and m.lags[first - 1] > STRETCH_FLOOR:
        first -= 1
    while last < len(m.lags) - 1 and m.lags[last + 1] > STRETCH_FLOOR:
        last += 1
    first = max(0, first - STRETCH_PAD)
    last = min(len(m.lags) - 1, last + STRETCH_PAD, first + STRETCH_MAX - 1)

    frames = [
        Frame(
            number=i,
            step_ms=m.steps[i - 1] * 1000 if i else None,
            lag_ms=m.lags[i] * 1000,
            repeat=i > 0 and m.steps[i - 1] <= 0,
            pause=i > 0 and m.steps[i - 1] > max_step,
            removed=m.removed[i],
        )
        for i in range(first, last + 1)
    ]
    runs = chart.runs([f.removed for f in frames])
    return Stretch(
        title=_label(m.video),
        frames=frames,
        removed_runs=[(first + a, first + b) for a, b in runs],
        frame_axis=Axis(first, last, _frame_ticks(first, last)),
        lag_axis=chart.axis(0, max(f.lag_ms for f in frames), about=4),
        step_axis=chart.axis(0, max(f.step_ms or 0 for f in frames), about=3),
    )


def _frame_ticks(first: int, last: int) -> list[float]:
    step = next(s for s in (10, 15, 30, 60, 90) if (last - first) / s <= 9)
    return [n for n in range(first, last + 1) if n % step == 0]


def _columns(measured: list[_Measured], origin: int, span: int,
             zone: timezone) -> list[Column]:
    """The worst lag in each of SESSION_BINS equal slices of the session."""
    worst = [0.0] * SESSION_BINS
    for m in measured:
        for t, x in zip(m.video.times, m.lags):
            slot = min(SESSION_BINS - 1, (t - origin) * SESSION_BINS // span)
            if x > worst[slot]:
                worst[slot] = x
    width = 100 / SESSION_BINS
    return [
        Column(
            left=k * width,
            width=width,
            lag_ms=x * 1000,
            clock=_local(origin + k * span // SESSION_BINS, zone).strftime("%H:%M:%S"),
        )
        for k, x in enumerate(worst)
    ]


def _removed_spans(measured: list[_Measured], origin: int, span: int) -> list[tuple[float, float]]:
    """Where the removed frames fall along the session, as left and width (%)."""
    spans = []
    for m in measured:
        times = m.video.times
        for a, b in chart.runs(m.removed):
            spans.append((100 * (times[a] - origin) / span,
                          100 * (times[b] - times[a]) / span))
    return spans


def _losses(measured: list[_Measured], zone: timezone) -> list[VideoLoss]:
    """The videos that lose the most footage to the rule."""
    rows = [
        VideoLoss(
            label=_label(m.video),
            clock=_local(m.video.times[0], zone).strftime("%H:%M:%S"),
            seconds=summary.duration(m.video),
            removed_seconds=sum(m.removed) / m.video.frame_rate,
            worst_lag_ms=max(m.lags) * 1000,
        )
        for m in measured if any(m.removed)
    ]
    return sorted(rows, key=lambda r: -r.removed_seconds)[:MOST_AFFECTED]


def _label(video: Video) -> str:
    return summary.task_title(video) if video.is_task else "Unlabelled video"


def _local(microseconds: int, zone: timezone) -> datetime:
    return datetime.fromtimestamp(microseconds / 1e6, zone)
