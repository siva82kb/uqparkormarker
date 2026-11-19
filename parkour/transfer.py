"""Run an upload or a download of clips in the background, and report progress.

One transfer runs at a time. The pages show its progress the same way as for
reading videos and cutting clips.
"""

import threading
from dataclasses import asdict, dataclass
from typing import Callable

from . import share


@dataclass
class Progress:
    kind: str = ""           # "upload" or "download"
    subject: str = ""
    state: str = "idle"      # idle, running, done or failed
    done: int = 0
    total: int = 0
    unit: str = ""           # what done and total count: "MB" or "clips"
    message: str = ""
    error: str = ""
    differences: tuple = ()  # settings that differ, if that is why it failed


_progress = Progress()
_lock = threading.Lock()


def snapshot(kind: str, subject: str) -> dict:
    """Progress of the transfer of this kind for this subject; idle if there
    is none, or if the last one was another kind or another subject."""
    with _lock:
        if _progress.kind == kind and _progress.subject == subject:
            return asdict(_progress)
    return asdict(Progress(kind=kind, subject=subject))


def start(kind: str, subject: str, work: Callable[[share.Progress], None]) -> None:
    """Begin a transfer, unless one is already running. `work` does the
    copying and is given a function to report progress with."""
    with _lock:
        if _progress.state == "running":
            return
        _set(kind=kind, subject=subject, state="running", done=0, total=0,
             unit="MB" if kind == "download" else "clips",
             message="Starting…", error="", differences=())
    threading.Thread(target=_run, args=(work,), daemon=True).start()


def _set(**changes) -> None:
    for name, value in changes.items():
        setattr(_progress, name, value)


def _run(work: Callable[[share.Progress], None]) -> None:
    def report(done: int, total: int, message: str) -> None:
        with _lock:
            _set(message=message)
            if total:                   # 0 of 0 means: only the message changed
                _set(done=done, total=total)

    try:
        work(report)
        with _lock:
            _set(state="done")
    except share.Mismatch as problem:
        with _lock:
            _set(state="failed", error=str(problem), message="Stopped.",
                 differences=tuple(problem.differences))
    except share.Unreachable:
        with _lock:
            _set(state="failed", message="Stopped.",
                 error="The study folder on the RDM cannot be reached. Check the VPN "
                       "and the drive, then try again.")
    except Exception as problem:        # shown on the page; trying again is safe
        with _lock:
            _set(state="failed", error=str(problem), message="Stopped.")
