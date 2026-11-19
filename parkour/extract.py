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


SLOW_SECONDS = 60           # a clip is not called slow before this
SLOW_FACTOR = 3             # ... nor unless it is this many times the average clip
SLOW_FIRST_SECONDS = 120    # the first clip has no average to compare with


@dataclass
class Progress:
    subject: str = ""
    state: str = "idle"      # idle, running, done or failed
    done: int = 0            # clips that exist
    total: int = 0
    task_done: int = 0       # of the clips that exist, those from task video
    task_total: int = 0      # of all the clips, those from task video
    message: str = ""        # what is happening right now
    error: str = ""
    step_started: float = 0.0   # when the current step (one clip, say) began
    spent: float = 0.0          # seconds of generating saved so far, over every run
    per_clip: float | None = None   # average seconds to cut a clip, once known

    def _slow(self, step: float) -> bool:
        """Is the clip now being cut taking much longer than clips usually do?

        It must have taken at least a minute, and more than three times the
        average clip so far. With no clip cut yet there is nothing to compare
        with, so the first clip is only called slow after two minutes.
        Reading the videos and choosing the clips are never called slow.
        """
        if self.state != "running" or not self.total:
            return False
        if self.per_clip is None:
            return step >= SLOW_FIRST_SECONDS
        return step >= SLOW_SECONDS and step > SLOW_FACTOR * self.per_clip

    def report(self) -> dict:
        """What a page is told. In place of the internal figures it gets:

        step_seconds     how long the current step has been going
        slow             True if the clip being cut is taking much longer
                         than usual; the page then says so, with the time
        elapsed_seconds  time spent generating in all, over every run
        left_seconds     a rough guess of the time still needed, or None
        """
        told = asdict(self)
        for internal in ("step_started", "spent", "per_clip"):
            told.pop(internal)
        running = self.state == "running" and self.step_started
        step = time.monotonic() - self.step_started if running else 0.0
        told["step_seconds"] = int(step)
        told["slow"] = self._slow(step)
        told["elapsed_seconds"] = int(self.spent + step)
        waiting = self.total - self.done
        if self.per_clip and waiting > 0 and self.state != "done":
            # `step` is the time already spent on the clip now being cut.
            told["left_seconds"] = int(max(0.0, self.per_clip * waiting - step))
        else:
            told["left_seconds"] = None
        return told


_progress = Progress()
_lock = threading.Lock()


def snapshot(subject: str) -> dict:
    """Progress for a subject: the live job if it is theirs, else what is on disk."""
    with _lock:
        if _progress.subject == subject and _progress.state != "idle":
            return _progress.report()
    segments = clipset.read_segments(subject)
    missing = {s.segment_id for s in clipset.missing(subject, segments)}
    done = len(segments) - len(missing)
    finished = bool(segments) and done == len(segments)
    spent = clipset.read_spent(subject)
    return Progress(
        spent=spent.seconds,
        per_clip=spent.per_clip,
        subject=subject,
        state="done" if finished else "idle",
        done=done,
        total=len(segments),
        task_done=sum(bool(s.task) for s in segments if s.segment_id not in missing),
        task_total=sum(bool(s.task) for s in segments),
        message=f"All {done} clips are ready." if finished else "",
    ).report()


def ensure_running(subject: str, subject_dir: Path, study: dict) -> None:
    """Draw the windows if that has not been done, then cut any missing clips."""
    with _lock:
        if _progress.state == "running":
            return
        _set(subject=subject, state="running", done=0, total=0, task_done=0,
             task_total=0, error="", step_started=time.monotonic(),
             spent=clipset.read_spent(subject).seconds, per_clip=None,
             message="Reading the videos…")
    threading.Thread(
        target=_run, args=(subject, Path(subject_dir), study), daemon=True
    ).start()


def _set(**changes) -> None:
    for name, value in changes.items():
        setattr(_progress, name, value)


def _clips_to_cut(subject: str, subject_dir: Path, study: dict) -> list[Segment]:
    """The clips this run works with, choosing and saving them first if no
    list exists yet.

    The list is always read back from disk, even just after it was saved, so
    that a first run and a resumed run see exactly the same clips. Reading
    back is also what applies the `clip_limit` test setting.
    """
    if not clipset.read_segments(subject):      # first run: plan before cutting
        recording = loader.fetch(
            subject_dir, study["source"]["utc_offset_hours"], _report_reading
        )
        with _lock:
            _set(message="Choosing the windows…")
        clipset.write_plan(subject, sampling.draw(recording.videos, study))
    return clipset.read_segments(subject)


def _run(subject: str, subject_dir: Path, study: dict) -> None:
    try:
        began = time.monotonic()
        segments = _clips_to_cut(subject, subject_dir, study)
        # Time is added to the saved total after every step, so that it
        # carries on from here if the app is stopped and started again.
        spent = clipset.add_spent(subject, time.monotonic() - began)    # preparation
        todo = clipset.missing(subject, segments)
        total, already = len(segments), len(segments) - len(todo)
        task_total = sum(bool(s.task) for s in segments)
        task_done = task_total - sum(bool(s.task) for s in todo)   # already cut
        ffmpeg, crf = imageio_ffmpeg.get_ffmpeg_exe(), study["clips"]["crf"]
        rates: dict[str, float] = {}

        for i, segment in enumerate(todo):
            began = time.monotonic()
            with _lock:
                _set(done=already + i, total=total, task_done=task_done,
                     task_total=task_total, step_started=began,
                     spent=spent.seconds, per_clip=spent.per_clip,
                     message=f"Cutting clip {already + i + 1} of {total} from {segment.video_file}")
            source = dataset.video_path(subject_dir, segment.video_file)
            if segment.video_file not in rates:
                rates[segment.video_file] = dataset.avi_header(source)[1]
            cut(ffmpeg, source, clipset.clip_path(subject, segment.segment_id),
                segment, rates[segment.video_file], crf)
            spent = clipset.add_spent(subject, time.monotonic() - began, clips=1)
            task_done += bool(segment.task)

        with _lock:
            _set(state="done", done=total, total=total, task_done=task_total,
                 task_total=task_total, spent=spent.seconds, per_clip=spent.per_clip,
                 message=f"All {total} clips are ready.")
    except Exception as problem:    # shown on the page; the next start resumes
        with _lock:
            _set(state="failed", error=str(problem), message="Stopped.")


def _report_reading(done: int, total: int) -> None:
    with _lock:
        _set(message=f"Reading video {done} of {total} before choosing windows…")



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
