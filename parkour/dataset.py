"""Find subjects and their videos. The only module that knows the folder layout.

    <source>/<subject>/experiment_details.json
    <source>/<subject>/videos/task_NNN_<unix-us>.avi        a recorded task
    <source>/<subject>/videos/unlabelled_x_<unix-us>.avi    between tasks
    <source>/<subject>/videos/<same name>.vidt              frame times

All times handed out by this module are whole microseconds since the Unix
epoch, so they compare directly with the time in the file name.
"""

import json
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import vidt

VIDEO_DIR = "videos"
DETAILS_FILE = "experiment_details.json"
_NAME = re.compile(r"^(?:task_(\d+)|unlabelled_x)_(\d+)$")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)


@dataclass
class Video:
    """One video file and its frame times."""

    path: Path
    task_number: int | None      # None for unlabelled video
    task_name: str | None        # e.g. "03:Tie shoelaces"
    filename_time: int           # unix microseconds, from the file name
    frame_count: int | None      # from the .avi header; None if unreadable
    times: list[int] | None = field(repr=False)  # per frame; None if no .vidt

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def is_task(self) -> bool:
        return self.task_number is not None


def list_subjects(source: Path) -> list[str]:
    """Names of the subject folders in `source`: those with a videos folder."""
    return sorted(
        p.name for p in Path(source).iterdir() if (p / VIDEO_DIR).is_dir()
    )


def load_videos(subject_dir: Path, utc_offset_hours: float) -> list[Video]:
    """Every video of a subject, in recording order."""
    subject_dir = Path(subject_dir)
    task_names = _task_names(subject_dir)
    zone = timezone(timedelta(hours=utc_offset_hours))

    videos = []
    for avi in (subject_dir / VIDEO_DIR).glob("*.avi"):
        match = _NAME.match(avi.stem)
        if not match:
            continue  # not a study recording
        number, stamp = match.groups()
        videos.append(
            Video(
                path=avi,
                task_number=int(number) if number else None,
                task_name=task_names.get(avi.stem) or None,
                filename_time=int(stamp),
                frame_count=avi_frame_count(avi),
                times=_frame_times(avi.with_suffix(".vidt"), zone),
            )
        )
    return sorted(videos, key=lambda v: v.filename_time)


def missing_videos(subject_dir: Path) -> list[str]:
    """Videos named in experiment_details.json that are not in the folder."""
    subject_dir = Path(subject_dir)
    present = {p.stem for p in (subject_dir / VIDEO_DIR).glob("*.avi")}
    return sorted(set(_task_names(subject_dir)) - present)


def avi_frame_count(path: Path) -> int | None:
    """Frame count from the AVI main header, without decoding the video."""
    with Path(path).open("rb") as fh:
        head = fh.read(512)
    at = head.find(b"avih")
    if not head.startswith(b"RIFF") or at < 0:
        return None
    # 'avih', chunk size, then four 32-bit fields before dwTotalFrames.
    return struct.unpack_from("<I", head, at + 8 + 16)[0]


def _frame_times(vidt_file: Path, zone: timezone) -> list[int] | None:
    """Frame times as unix microseconds, or None if the .vidt is missing."""
    if not vidt_file.exists():
        return None
    return [
        (t.replace(tzinfo=zone) - _EPOCH) // _MICROSECOND
        for t in vidt.read_times(vidt_file)
    ]


def _task_names(subject_dir: Path) -> dict[str, str]:
    """Map video file stem to task name, from experiment_details.json."""
    details = subject_dir / DETAILS_FILE
    if not details.exists():
        return {}
    with details.open(encoding="utf-8") as fh:
        datafiles = json.load(fh).get("datafiles", [])
    # Paths were written on Windows; keep only the last component.
    return {path.replace("\\", "/").rsplit("/", 1)[-1]: name for path, name in datafiles}
