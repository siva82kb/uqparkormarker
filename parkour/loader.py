"""Read a subject's videos once, in the background, and remember the result.

Reading from the network drive can take a minute or two, so pages do not wait
for it: they start the read, show its progress, and use the result when it is
ready. The result is kept in memory, and on disk (`recording_store.py`), so
the videos are read once per subject and not on every start of the app. They
are read again only when the user asks (`forget`).
"""

import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import dataset, recording_store
from .dataset import Recording


@dataclass
class Progress:
    state: str = "idle"      # idle, running, done or failed
    done: int = 0            # videos read
    total: int = 0
    message: str = ""
    error: str = ""


_cache: dict[Path, Recording] = {}
_progress = Progress()
_lock = threading.Lock()


def cached(subject_dir: Path) -> Recording | None:
    """The subject's recording if it has been read, now or on an earlier
    start of the app, else None."""
    subject_dir = Path(subject_dir)
    if subject_dir not in _cache:
        saved = recording_store.load(subject_dir)
        if saved is None:
            return None
        _cache[subject_dir] = saved
    return _cache[subject_dir]


def fetch(
    subject_dir: Path,
    utc_offset_hours: float,
    on_progress: Callable[[int, int], None] | None = None,
) -> Recording:
    """The subject's recording, reading it now if it has not been read."""
    subject_dir = Path(subject_dir)
    recording = cached(subject_dir)
    if recording is None:
        recording = dataset.load(subject_dir, utc_offset_hours, on_progress)
        recording_store.save(subject_dir, recording)
        _cache[subject_dir] = recording
    return recording


def forget(subject_dir: Path) -> bool:
    """Drop what was read for a subject, in memory and on disk, so the next
    page reads the videos again. False if a read is running; nothing is
    dropped then."""
    with _lock:
        if _progress.state == "running":
            return False
        _cache.pop(Path(subject_dir), None)
        recording_store.forget(subject_dir)
        _set(state="idle", done=0, total=0, message="", error="")
    return True


def start(subject_dir: Path, utc_offset_hours: float) -> None:
    """Begin reading in the background, unless a read is already running."""
    with _lock:
        if _progress.state == "running":
            return
        _set(state="running", done=0, total=0, error="",
             message="Listing the video folder…")
    threading.Thread(
        target=_run, args=(Path(subject_dir), utc_offset_hours), daemon=True
    ).start()


def snapshot() -> dict:
    with _lock:
        return asdict(_progress)


def _set(**changes) -> None:
    for name, value in changes.items():
        setattr(_progress, name, value)


def _run(subject_dir: Path, utc_offset_hours: float) -> None:
    def report(done: int, total: int) -> None:
        with _lock:
            _set(done=done, total=total,
                 message=f"Reading video {done} of {total} from {subject_dir}")

    try:
        recording = fetch(subject_dir, utc_offset_hours, report)
        count = len(recording.videos)
        with _lock:
            _set(state="done", done=count, total=count,
                 message=f"Read {count} videos.")
    except Exception as problem:     # shown on the page; reloading tries again
        with _lock:
            _set(state="failed", error=str(problem), message="Stopped.")
