"""The clip folder of one subject, on disk.

    data4annotation/<subject>/
        segments.csv            the sampled windows
        design.toml             copy of study.toml as it was when they were drawn
        clips/seg_0001.mp4 ...  one clip per window
        generation_time.json    time spent generating so far, over every run

A clip with its final name is always complete: clips are written under a
temporary name and renamed when finished (see extract.py).
"""

import csv
import hashlib
import json
import shutil
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from . import config
from .sampling import Segment

SEGMENTS_FILE = "segments.csv"
DESIGN_FILE = "design.toml"
CLIP_DIR = "clips"
SPENT_FILE = "generation_time.json"     # time spent generating, over every run


def folder(subject: str) -> Path:
    return config.CLIPS_ROOT / subject


def clip_path(subject: str, segment_id: str) -> Path:
    return folder(subject) / CLIP_DIR / f"{segment_id}.mp4"


@dataclass
class Spent:
    """Time spent generating a subject's clips so far, over every run."""

    seconds: float = 0.0        # everything: reading videos, choosing, cutting
    cut_seconds: float = 0.0    # the cutting alone
    clips: int = 0              # clips cut in that time

    @property
    def per_clip(self) -> float | None:
        """Average seconds to cut one clip, once at least one has been cut."""
        return self.cut_seconds / self.clips if self.clips else None


def read_spent(subject: str) -> Spent:
    path = folder(subject) / SPENT_FILE
    if not path.exists():
        return Spent()
    try:
        return Spent(**json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError):     # unreadable: start counting again
        return Spent()


def add_spent(subject: str, seconds: float, clips: int = 0) -> Spent:
    """Add time to the running total and save it at once, so the total
    survives the app being stopped. `clips` says how many clips were cut in
    that time; with none, the time counts as preparation."""
    spent = read_spent(subject)
    spent.seconds += seconds
    if clips:
        spent.cut_seconds += seconds
        spent.clips += clips
    folder(subject).mkdir(parents=True, exist_ok=True)
    (folder(subject) / SPENT_FILE).write_text(json.dumps(asdict(spent)), encoding="utf-8")
    return spent


def set_code(subject: str) -> str:
    """A short code that identifies this generated set of clips.

    It goes into the address of every clip, so that a browser can never show
    a clip from an earlier set under the same clip number. It is made from
    the list of clips, the settings they were made with, and the moment the
    list was written, so it changes every time clips are generated again.
    Empty if no clips have been chosen yet.
    """
    plan = folder(subject) / SEGMENTS_FILE
    if not plan.exists():
        return ""
    design = folder(subject) / DESIGN_FILE
    stamp = hashlib.sha256(plan.read_bytes())
    stamp.update(design.read_bytes() if design.exists() else b"")
    stamp.update(str(plan.stat().st_mtime_ns).encode())
    return stamp.hexdigest()[:10]


def write_plan(subject: str, segments: list[Segment]) -> None:
    """Record the windows and the settings they were drawn with."""
    (folder(subject) / CLIP_DIR).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config.STUDY_FILE, folder(subject) / DESIGN_FILE)
    with (folder(subject) / SEGMENTS_FILE).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=Segment.FIELDS)
        writer.writeheader()
        writer.writerows(asdict(s) for s in segments)


def read_segments(subject: str) -> list[Segment]:
    """The clips to work with; empty if none have been chosen yet.

    Normally every row of segments.csv. While testing, `clip_limit` in
    local.toml cuts this to the first few, so the rest of the app (cutting,
    progress, annotation) behaves as if those were all there is.
    """
    path = folder(subject) / SEGMENTS_FILE
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        segments = [
            Segment(**{**row, "start_frame": int(row["start_frame"]),
                       "end_frame": int(row["end_frame"])})
            for row in csv.DictReader(fh)
        ]
    limit = (config.load_local() or {}).get("clip_limit")
    return segments[:limit] if limit else segments


def missing(subject: str, segments: list[Segment]) -> list[Segment]:
    """Windows whose clip has not been cut yet."""
    clips = folder(subject) / CLIP_DIR
    have = {p.stem for p in clips.glob("*.mp4")} if clips.is_dir() else set()
    return [s for s in segments if s.segment_id not in have]


@dataclass
class Spacing:
    """How close the clips come to one another, as a check that none overlap."""

    shared: int                     # pairs of clips that share a frame; should be 0
    closest: int | None             # fewest frames between two clips of one video
    pair: tuple[str, str] | None    # the two clips that are that close
    closest_starts: float | None    # least time between two start times, in seconds


def spacing(segments: list[Segment]) -> Spacing:
    """Compare each clip with the next one from the same video, by frame
    number. Clips from different videos cannot overlap."""
    by_video: dict[str, list[Segment]] = {}
    for segment in segments:
        by_video.setdefault(segment.video_file, []).append(segment)

    shared, closest, pair = 0, None, None
    for clips in by_video.values():
        clips.sort(key=lambda s: s.start_frame)
        for earlier, later in zip(clips, clips[1:]):
            between = later.start_frame - earlier.end_frame - 1
            shared += between < 0
            if closest is None or between < closest:
                closest, pair = between, (earlier.segment_id, later.segment_id)

    # Start times of all clips, whatever their video, taken in time order.
    starts = sorted(datetime.fromisoformat(s.start_time) for s in segments if s.start_time)
    gaps = [(b - a).total_seconds() for a, b in zip(starts, starts[1:])]
    return Spacing(shared, closest, pair, min(gaps) if gaps else None)


def state(subject: str) -> str:
    """'none', 'partial' or 'complete'."""
    segments = read_segments(subject)
    if not segments:
        return "none"
    return "partial" if missing(subject, segments) else "complete"


def design_differences(subject: str, study: dict) -> list[str]:
    """Settings that differ between the clips' design.toml and study.toml.

    Empty when they match, or when no clips have been planned yet.
    """
    path = folder(subject) / DESIGN_FILE
    if not path.exists():
        return []
    with path.open("rb") as fh:
        then, now = _flatten(tomllib.load(fh)), _flatten(study)
    return [
        f"{key}: clips were made with {then.get(key, 'nothing')!r}, "
        f"study.toml now has {now.get(key, 'nothing')!r}"
        for key in sorted(then.keys() | now.keys())
        if then.get(key) != now.get(key)
    ]


def _flatten(value, prefix: str = "") -> dict:
    """{'a': {'b': 1}, 'c': [2]} -> {'a.b': 1, 'c.1': 2}; lists count from 1."""
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = ((str(i), v) for i, v in enumerate(value, start=1))
    else:
        return {prefix: value}
    flat = {}
    for key, inner in items:
        flat.update(_flatten(inner, f"{prefix}.{key}" if prefix else key))
    return flat
