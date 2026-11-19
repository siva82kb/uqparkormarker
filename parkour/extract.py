"""Cut the clips with ffmpeg, in a background thread, and report progress.

One job runs at a time. It cuts only the clips that are missing, so starting
it again after an interruption resumes where it stopped.
"""

import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import imageio_ffmpeg

from . import clipset, dataset, loader, sampling
from .sampling import Segment


@dataclass
class Progress:
    subject: str = ""
    state: str = "idle"      # idle, running, done or failed
    done: int = 0            # clips that exist
    total: int = 0
    message: str = ""        # what is happening right now
    error: str = ""


_progress = Progress()
_lock = threading.Lock()


def snapshot(subject: str) -> dict:
    """Progress for a subject: the live job if it is theirs, else what is on disk."""
    with _lock:
        if _progress.subject == subject and _progress.state != "idle":
            return asdict(_progress)
    segments = clipset.read_segments(subject)
    done = len(segments) - len(clipset.missing(subject, segments))
    finished = bool(segments) and done == len(segments)
    return asdict(Progress(
        subject=subject,
        state="done" if finished else "idle",
        done=done,
        total=len(segments),
        message=f"All {done} clips are ready." if finished else "",
    ))


def ensure_running(subject: str, subject_dir: Path, study: dict) -> None:
    """Draw the windows if that has not been done, then cut any missing clips."""
    with _lock:
        if _progress.state == "running":
            return
        _set(subject=subject, state="running", done=0, total=0, error="",
             message="Reading the videos…")
    threading.Thread(
        target=_run, args=(subject, Path(subject_dir), study), daemon=True
    ).start()


def _set(**changes) -> None:
    for name, value in changes.items():
        setattr(_progress, name, value)


def _run(subject: str, subject_dir: Path, study: dict) -> None:
    try:
        segments = clipset.read_segments(subject)
        if not segments:        # first run: the plan is written before any cutting
            recording = loader.fetch(
                subject_dir, study["source"]["utc_offset_hours"], _report_reading
            )
            with _lock:
                _set(message="Choosing the windows…")
            segments = sampling.draw(recording.videos, study)
            clipset.write_plan(subject, segments)

        todo = clipset.missing(subject, segments)
        total, already = len(segments), len(segments) - len(todo)
        ffmpeg, crf = imageio_ffmpeg.get_ffmpeg_exe(), study["clips"]["crf"]
        rates: dict[str, float] = {}
        started = time.monotonic()

        for i, segment in enumerate(todo):
            with _lock:
                _set(done=already + i, total=total, message=(
                    f"Cutting clip {already + i + 1} of {total} from "
                    f"{segment.video_file}{_time_left(started, i, len(todo))}"
                ))
            source = dataset.video_path(subject_dir, segment.video_file)
            if segment.video_file not in rates:
                rates[segment.video_file] = dataset.avi_header(source)[1]
            cut(ffmpeg, source, clipset.clip_path(subject, segment.segment_id),
                segment, rates[segment.video_file], crf)

        with _lock:
            _set(state="done", done=total, total=total,
                 message=f"All {total} clips are ready.")
    except Exception as problem:    # shown on the page; the next start resumes
        with _lock:
            _set(state="failed", error=str(problem), message="Stopped.")


def _report_reading(done: int, total: int) -> None:
    with _lock:
        _set(message=f"Reading video {done} of {total} before choosing windows…")


def _time_left(started: float, cut_so_far: int, to_cut: int) -> str:
    """' · about 2 min left', once there is enough to judge by."""
    if cut_so_far < 5:
        return ""
    seconds = (time.monotonic() - started) / cut_so_far * (to_cut - cut_so_far)
    if seconds < 60:
        return " · less than a minute left"
    return f" · about {round(seconds / 60)} min left"


def cut(ffmpeg: str, source: Path, target: Path, segment: Segment,
        frame_rate: float | None, crf: int) -> None:
    """Cut frames start_frame..end_frame of `source` into an H.264 MP4, no audio.

    Seeking to half a frame before the first wanted frame makes ffmpeg start
    exactly on it without decoding the video from the beginning.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source video not found: {source}")
    if not frame_rate:
        raise ValueError(f"Could not read the frame rate of {source.name}")

    part = target.with_suffix(".part")      # renamed only when complete
    command = [
        ffmpeg, "-v", "error", "-y",
        "-ss", f"{max(0.0, (segment.start_frame - 0.5) / frame_rate):.6f}",
        "-i", str(source),
        "-frames:v", str(segment.end_frame - segment.start_frame + 1),
        "-an",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast",
        "-pix_fmt", "yuv420p",              # the format every browser plays
        "-movflags", "+faststart",
        "-f", "mp4", str(part),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0 or not part.exists():
        part.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed on {segment.segment_id}: {result.stderr.strip()[-400:]}")
    os.replace(part, target)
