"""Find subjects and their videos. The only module that knows the folder layout.

    <source>/Pxx/Video/experiment_details.json
    <source>/Pxx/Video/task_NNN_<unix-us>.avi        a recorded task
    <source>/Pxx/Video/unlabelled_x_<unix-us>.avi    between tasks
    <source>/Pxx/Video/<same name>.vidt              frame times

A subject is a folder named P plus digits. For now only subjects whose videos
sit directly in Video/ are offered; those whose Video/ folder is split into
session subfolders are left out.

The source is usually a network drive, where opening any file takes a second
or two. So a folder is listed once, and files are read many at a time.

All times handed out by this module are whole microseconds since the Unix
epoch, so they compare directly with the time in the file name.
"""

import json
import os
import re
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import vidt

VIDEO_DIR = "Video"
DETAILS_FILE = "experiment_details.json"
SUBJECT = re.compile(r"^P\d+$")
READERS = 32               # files read at the same time
_NAME = re.compile(r"^(?:task_(\d+)|unlabelled_x)_(\d+)$")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)


@dataclass
class Video:
    """One video file and its frame times."""

    path: Path
    task_number: int | None      # None for unlabelled video
    task_name: str | None        # e.g. "Tie shoelaces"
    filename_time: int           # unix microseconds, from the file name
    frame_count: int | None      # from the .avi header; None if unreadable
    frame_rate: float | None     # nominal, from the .avi header (see avi_header)
    times: list[int] | None = field(repr=False)  # per frame; None if no .vidt

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def is_task(self) -> bool:
        return self.task_number is not None


@dataclass
class Recording:
    """Everything read from one subject's Video folder."""

    videos: list[Video]          # in recording order
    missing: list[str]           # named in experiment_details.json but absent
    read_at: datetime | None = None   # when the files were read from the source


def list_subjects(source: Path) -> list[str]:
    """Subject folders in `source` that can be used: named P plus digits, with
    videos directly in their Video folder and no subfolders there."""
    return sorted(
        p.name for p in Path(source).iterdir()
        if SUBJECT.match(p.name) and _has_flat_videos(p / VIDEO_DIR)
    )


def _has_flat_videos(video_dir: Path) -> bool:
    """True if the folder holds .avi files and no subfolders."""
    if not video_dir.is_dir():
        return False
    has_video = False
    with os.scandir(video_dir) as entries:
        for entry in entries:
            if entry.is_dir():
                return False
            has_video = has_video or entry.name.lower().endswith(".avi")
    return has_video


def load(
    subject_dir: Path,
    utc_offset_hours: float,
    on_progress: Callable[[int, int], None] | None = None,
) -> Recording:
    """Read every video of a subject. `on_progress(done, total)` is called as
    each video's files are read."""
    folder = Path(subject_dir) / VIDEO_DIR
    present = set(os.listdir(folder))                 # the only folder listing
    zone = timezone(timedelta(hours=utc_offset_hours))
    task_names = _task_names(folder) if DETAILS_FILE in present else {}

    wanted = [n for n in present if n.endswith(".avi") and _NAME.match(n[:-4])]
    videos = []
    with ThreadPoolExecutor(READERS) as pool:
        jobs = [
            pool.submit(_read_video, folder / name, name[:-4] + ".vidt" in present,
                        task_names.get(name[:-4]) or None, zone)
            for name in wanted
        ]
        for done, job in enumerate(as_completed(jobs), start=1):
            videos.append(job.result())
            if on_progress:
                on_progress(done, len(jobs))

    stems = {name[:-4] for name in present if name.endswith(".avi")}
    return Recording(
        videos=sorted(videos, key=lambda v: v.filename_time),
        missing=sorted(set(task_names) - stems),
        read_at=datetime.now().astimezone().replace(microsecond=0),
    )


def _read_video(avi: Path, has_vidt: bool, task_name: str | None, zone: timezone) -> Video:
    number, stamp = _NAME.match(avi.stem).groups()
    frame_count, frame_rate = avi_header(avi)
    times = None
    if has_vidt:
        times = [
            (t.replace(tzinfo=zone) - _EPOCH) // _MICROSECOND
            for t in vidt.read_times(avi.with_suffix(".vidt"))
        ]
    return Video(
        path=avi,
        task_number=int(number) if number else None,
        task_name=task_name,
        filename_time=int(stamp),
        frame_count=frame_count,
        frame_rate=frame_rate,
        times=times,
    )


def avi_header(path: Path) -> tuple[int | None, float | None]:
    """(frame count, nominal frames per second) from the start of an AVI file,
    without decoding the video. Either is None if it cannot be read.

    The nominal rate is the one the container plays at (frame n sits at
    n / rate), which is what seeking needs. The true capture times are in
    the .vidt file.
    """
    with Path(path).open("rb") as fh:
        head = fh.read(1024)
    if not head.startswith(b"RIFF"):
        return None, None

    count = rate = None
    at = head.find(b"avih")
    if at >= 0:     # 'avih', chunk size, then four 32-bit fields, then dwTotalFrames
        count = struct.unpack_from("<I", head, at + 8 + 16)[0]
    at = head.find(b"strh")
    if at >= 0 and head[at + 8 : at + 12] == b"vids":
        # 'strh', chunk size, then 20 bytes of fields, then dwScale and dwRate
        scale, per = struct.unpack_from("<II", head, at + 8 + 20)
        rate = per / scale if scale else None
    return count, rate


def video_path(subject_dir: Path, video_file: str) -> Path:
    """Where a video named in segments.csv lives."""
    return Path(subject_dir) / VIDEO_DIR / video_file


def _task_names(folder: Path) -> dict[str, str]:
    """Map video file stem to task name, from experiment_details.json."""
    with (folder / DETAILS_FILE).open(encoding="utf-8") as fh:
        datafiles = json.load(fh).get("datafiles", [])
    # Paths were written on Windows; keep only the last component.
    return {path.replace("\\", "/").rsplit("/", 1)[-1]: name for path, name in datafiles}
