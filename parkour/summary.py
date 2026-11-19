"""Build the data summary for one subject from its list of videos.

Pure calculation: no file access and no HTML. Durations are in seconds.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median

from . import sampling, timing
from .dataset import Video

GAP_SECONDS = 1.0          # report silences between files longer than this
NAME_DRIFT_SECONDS = 1.0   # file-name time vs first frame: tolerated difference


@dataclass
class Span:
    """A stretch of the timeline strip, as percentages of the whole recording."""

    kind: str       # "task", "unlabelled" or "gap"
    label: str
    seconds: float
    left: float
    width: float


@dataclass
class TaskRow:
    number: int
    name: str
    seconds: float
    repeats: int


@dataclass
class Summary:
    n_task: int
    n_unlabelled: int
    task_seconds: float
    unlabelled_seconds: float
    start: datetime | None
    end: datetime | None
    fps_median: float | None
    fps_min: float | None
    fps_max: float | None
    gaps: list[Span]
    problems: list[str]
    tasks: list[TaskRow]
    timeline: list[Span]
    ticks: list[tuple[str, float]]   # clock label and position (%) along the strip
    n_windows: int                   # clips that fit: n_windows_task + the rest
    n_windows_task: int
    quotas: dict[str, int] | None    # clips wanted from task and unlabelled video

    @property
    def n_windows_unlabelled(self) -> int:
        return self.n_windows - self.n_windows_task

    @property
    def n_videos(self) -> int:
        return self.n_task + self.n_unlabelled

    @property
    def total_seconds(self) -> float:
        return self.task_seconds + self.unlabelled_seconds

    @property
    def span_seconds(self) -> float:
        return (self.end - self.start).total_seconds() if self.start else 0.0


def duration(video: Video) -> float:
    """Recorded seconds in a video: first frame to last frame."""
    if not video.times:
        return 0.0
    return (video.times[-1] - video.times[0]) / 1e6


def build(videos: list[Video], study: dict, missing: list[str] = ()) -> Summary:
    """`missing` names videos the experiment record lists but the folder lacks."""
    usable = [v for v in videos if v.times]   # timed videos, in recording order
    zone = timezone(timedelta(hours=study["source"]["utc_offset_hours"]))
    windows = _windows(usable, study)
    rates = [(len(v.times) - 1) / duration(v) for v in usable if duration(v) > 0]
    spans = timeline(usable)
    start = _local(usable[0].times[0], zone) if usable else None
    end = _local(max(v.times[-1] for v in usable), zone) if usable else None

    return Summary(
        n_task=sum(v.is_task for v in videos),
        n_unlabelled=sum(not v.is_task for v in videos),
        task_seconds=sum(duration(v) for v in usable if v.is_task),
        unlabelled_seconds=sum(duration(v) for v in usable if not v.is_task),
        start=start,
        end=end,
        fps_median=median(rates) if rates else None,
        fps_min=min(rates) if rates else None,
        fps_max=max(rates) if rates else None,
        gaps=[s for s in spans if s.kind == "gap"],
        problems=_missing_note(missing) + _problems(videos) + windows.notes,
        tasks=_task_table(usable),
        timeline=spans,
        ticks=ticks(start, end) if usable else [],
        n_windows=windows.fitting,
        n_windows_task=windows.fitting_task,
        quotas=sampling.quotas(study["sampling"]),
    )


@dataclass
class _Windows:
    fitting: int            # non-overlapping windows with trustworthy timestamps
    fitting_task: int       # those of them that lie in task video
    notes: list[str]        # what the timestamp rule leaves out, and any shortfall


def _windows(usable: list[Video], study: dict) -> _Windows:
    """Count the windows that can be sampled, and say what the rule excludes."""
    seconds = study["sampling"]["window_seconds"]
    max_step = study["timing"]["max_step_seconds"]
    fitting = fitting_task = possible = allowed = 0
    per_task: dict[int, int] = defaultdict(int)
    for v in usable:
        frames = timing.frames_per_window(v, seconds)
        starts = timing.clean_starts(v, frames, max_step)
        fits = timing.count_fitting(starts, frames)
        fitting += fits
        fitting_task += fits if v.is_task else 0
        allowed += len(starts)
        possible += max(0, len(v.times) - frames + 1) if frames >= 2 else 0
        if v.is_task:
            per_task[v.task_number] += fits

    notes = []
    if possible > allowed:
        empty = sum(n == 0 for n in per_task.values())
        note = (
            f"{1 - allowed / possible:.1%} of possible {seconds:g} s windows are left "
            "out of sampling because they contain a repeated timestamp or a pause "
            f"longer than {max_step:g} s, which mark frames that were stamped late."
        )
        if empty:
            verb = "has" if empty == 1 else "have"
            note += f" {empty} of the {len(per_task)} tasks {verb} no usable window."
        notes.append(note)

    # Is there room for the number of clips wanted from each kind of video?
    wanted = sampling.quotas(study["sampling"]) or {}
    room = {"task": fitting_task, "unlabelled": fitting - fitting_task}
    for kind, number in wanted.items():
        if number > room[kind]:
            notes.append(
                f"{number} clips are wanted from {kind} video, but it has room for "
                f"only {room[kind]}. Fewer clips will be made; the other kind of "
                "video does not make up the difference."
            )
    return _Windows(fitting, fitting_task, notes)


def _local(microseconds: int, zone: timezone) -> datetime:
    return datetime.fromtimestamp(microseconds / 1e6, zone)


def ticks(start: datetime, end: datetime) -> list[tuple[str, float]]:
    """Clock marks along the strip, on round minutes, about six at most."""
    total = (end - start).total_seconds()
    if total <= 0:
        return []
    step = next((m for m in (1, 2, 5, 10, 15, 30, 60) if total / (m * 60) <= 6), 120)
    tick = start.replace(second=0, microsecond=0)
    tick += timedelta(minutes=step - tick.minute % step)   # next round mark
    ticks = []
    while tick < end:
        ticks.append((tick.strftime("%H:%M"), 100 * (tick - start).total_seconds() / total))
        tick += timedelta(minutes=step)
    return ticks


def timeline(usable: list[Video]) -> list[Span]:
    """Videos and the gaps between them, placed along the whole recording."""
    if not usable:
        return []
    origin = usable[0].times[0]
    total = (max(v.times[-1] for v in usable) - origin) or 1

    def span(kind: str, label: str, begin: int, end: int) -> Span:
        return Span(
            kind=kind,
            label=label,
            seconds=(end - begin) / 1e6,
            left=100 * (begin - origin) / total,
            width=100 * (end - begin) / total,
        )

    spans, previous_end = [], origin
    for v in usable:
        begin, end = v.times[0], v.times[-1]
        if (begin - previous_end) / 1e6 > GAP_SECONDS:
            spans.append(span("gap", "No video", previous_end, begin))
        kind = "task" if v.is_task else "unlabelled"
        spans.append(span(kind, v.task_name or "Unlabelled", begin, end))
        previous_end = max(previous_end, end)
    return spans


def _task_table(usable: list[Video]) -> list[TaskRow]:
    """One row per task number: total time and how often it was recorded."""
    seconds, repeats, names = defaultdict(float), defaultdict(int), {}
    for v in usable:
        if v.is_task:
            seconds[v.task_number] += duration(v)
            repeats[v.task_number] += 1
            names[v.task_number] = task_title(v)
    return [TaskRow(n, names[n], seconds[n], repeats[n]) for n in sorted(seconds)]


def task_title(video: Video) -> str:
    """'03:Tie shoelaces' -> 'Tie shoelaces'; the number has its own column."""
    name = video.task_name or ""
    return name.split(":", 1)[-1].strip() or "(no name)"


def _missing_note(missing: list[str]) -> list[str]:
    """One line for all the listed-but-absent videos, split by kind."""
    if not missing:
        return []
    tasks = sum(name.startswith("task_") for name in missing)
    return [
        f"{len(missing)} videos listed in experiment_details.json are not in the "
        f"videos folder ({tasks} task, {len(missing) - tasks} unlabelled)."
    ]


def _problems(videos: list[Video]) -> list[str]:
    """Plain-language notes on anything wrong with the files."""
    found = []
    for v in videos:
        if v.times is None:
            found.append(f"{v.name}: no .vidt timestamp file, so it cannot be sampled.")
            continue
        if not v.times:
            found.append(f"{v.name}: the .vidt timestamp file is empty.")
            continue
        if v.frame_count is None:
            found.append(f"{v.name}: could not read the frame count from the video.")
        elif v.frame_count != len(v.times):
            found.append(
                f"{v.name}: {v.frame_count} frames but {len(v.times)} timestamps."
            )
        steps = [b - a for a, b in zip(v.times, v.times[1:])]
        backward = sum(s < 0 for s in steps)
        if backward:
            found.append(f"{v.name}: timestamps go backwards in {backward} places.")
        drift = abs(v.times[0] - v.filename_time) / 1e6
        if drift > NAME_DRIFT_SECONDS:
            found.append(
                f"{v.name}: first frame is {drift:.1f} s away from the time in the file name."
            )
    return found
