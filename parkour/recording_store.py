"""Keep what was read from a subject's videos on disk, so it is read once.

    data4annotation/<subject>/recording.json.gz

Reading a subject from the network drive takes a minute or two. The source
videos do not change, so the result is saved here and used on every later
start. The file records when the videos were read and from which folder.
It is replaced only when the user asks for the videos to be read again.
"""

import gzip
import json
import os
from datetime import datetime
from pathlib import Path

from . import config, dataset
from .dataset import Recording, Video

FILE = "recording.json.gz"
VERSION = 1                 # raise when the saved layout changes


def path(subject_dir: Path) -> Path:
    return config.CLIPS_ROOT / Path(subject_dir).name / FILE


def save(subject_dir: Path, recording: Recording) -> None:
    """Write the recording under a temporary name, then rename it, so a file
    with the final name is always complete."""
    content = {
        "version": VERSION,
        "source": str(Path(subject_dir)),
        "read_at": recording.read_at.isoformat() if recording.read_at else None,
        "missing": recording.missing,
        "videos": [
            {
                "file": v.path.name,
                "task_number": v.task_number,
                "task_name": v.task_name,
                "filename_time": v.filename_time,
                "frame_count": v.frame_count,
                "frame_rate": v.frame_rate,
                "times": v.times,
            }
            for v in recording.videos
        ],
    }
    file = path(subject_dir)
    file.parent.mkdir(parents=True, exist_ok=True)
    partial = file.with_name(file.name + ".part")
    with gzip.open(partial, "wt", encoding="utf-8") as fh:
        json.dump(content, fh, separators=(",", ":"))
    os.replace(partial, file)


def load(subject_dir: Path) -> Recording | None:
    """The saved recording, or None if there is none that can be used: no
    file, a damaged file, an older layout, or one read from another folder."""
    file = path(subject_dir)
    if not file.exists():
        return None
    try:
        with gzip.open(file, "rt", encoding="utf-8") as fh:
            content = json.load(fh)
        if content["version"] != VERSION or content["source"] != str(Path(subject_dir)):
            return None
        folder = Path(content["source"])
        return Recording(
            videos=[
                Video(
                    path=dataset.video_path(folder, v["file"]),
                    task_number=v["task_number"],
                    task_name=v["task_name"],
                    filename_time=v["filename_time"],
                    frame_count=v["frame_count"],
                    frame_rate=v["frame_rate"],
                    times=v["times"],
                )
                for v in content["videos"]
            ],
            missing=content["missing"],
            read_at=datetime.fromisoformat(content["read_at"]) if content["read_at"] else None,
        )
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        return None


def forget(subject_dir: Path) -> None:
    """Remove the saved recording, so the videos are read again."""
    path(subject_dir).unlink(missing_ok=True)
