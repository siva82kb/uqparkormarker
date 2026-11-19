"""Read a subject's videos once, in the background, and remember the result.

Reading from the network drive can take half a minute, so pages do not wait
for it: they start the read, show its progress, and use the result when it is
ready. The result is kept in memory until the app stops.
"""

import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import dataset
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
    """The subject's recording if it has been read, else None."""
    return _cache.get(Path(subject_dir))


def fetch(
    subject_dir: Path,
    utc_offset_hours: float,
    on_progress: Callable[[int, int], None] | None = None,
) -> Recording:
    """The subject's recording, reading it now if it has not been read."""
    subject_dir = Path(subject_dir)
    if subject_dir not in _cache:
        _cache[subject_dir] = dataset.load(subject_dir, utc_offset_hours, on_progress)
    return _cache[subject_dir]


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
