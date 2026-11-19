"""Clear a subject's generated files so that work can start afresh.

Used only by `reset.py`, which a person runs by hand. The app itself never
deletes clips or labels.

What a reset does to data4annotation/<subject>/:

  - clips/, segments.csv, design.toml and generation_time.json are deleted.
    They can be made again.
  - Annotation files are never deleted. They are moved to
    data4annotation/_archive/<subject>_<date>-<time>/, because labels are a
    person's work and cannot be made again.
  - recording.json.gz (what was read from the source videos) is kept, unless
    asked for, since reading the videos again takes a minute or two and
    gives the same result.

The rater's name in local.toml is kept unless asked for.
"""

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import clipset, config, recording_store, shared_ratings

ARCHIVE_DIR = "_archive"
ANNOTATIONS = "*_annotations.csv"


@dataclass
class Plan:
    """What a reset would do. Nothing is touched until `apply`."""

    subject: str
    delete: list[Path] = field(default_factory=list)
    archive: list[Path] = field(default_factory=list)     # annotation files
    archive_to: Path | None = None
    n_clips: int = 0
    forget_rater: bool = False

    @property
    def empty(self) -> bool:
        return not (self.delete or self.archive or self.forget_rater)

    def lines(self) -> list[str]:
        """The plan in plain words, one line per action."""
        said = []
        for path in self.delete:
            note = f" ({self.n_clips} clips)" if path.name == clipset.CLIP_DIR else ""
            said.append(f"delete   {path}{note}")
        for path in self.archive:
            said.append(f"move     {path}\n         to {self.archive_to}")
        if self.forget_rater:
            said.append(f"remove   the rater's name from {config.LOCAL_FILE}")
        return said


def plan(subject: str, recording: bool = False, rater: bool = False,
         now: datetime | None = None) -> Plan:
    """Work out what a reset of `subject` would do."""
    folder = clipset.folder(subject)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    found = Plan(subject, archive_to=config.CLIPS_ROOT / ARCHIVE_DIR / f"{subject}_{stamp}")

    clips = folder / clipset.CLIP_DIR
    if clips.is_dir():
        found.n_clips = sum(1 for _ in clips.glob("*.mp4"))
    names = [clipset.CLIP_DIR, clipset.SEGMENTS_FILE, clipset.DESIGN_FILE,
             clipset.SPENT_FILE,        # the time spent goes with the clips
             shared_ratings.NOTE_FILE]  # ... and so does the note of what was uploaded
    if recording:
        names.append(recording_store.FILE)
    found.delete = [folder / name for name in names if (folder / name).exists()]
    found.archive = sorted(folder.glob(ANNOTATIONS)) if folder.is_dir() else []
    found.forget_rater = rater and bool((config.load_local() or {}).get("rater"))
    return found


def apply(found: Plan) -> None:
    """Carry the plan out. Annotation files are moved first, so that nothing
    is deleted if they cannot be kept."""
    if found.archive:
        found.archive_to.mkdir(parents=True, exist_ok=False)
        for path in found.archive:
            shutil.move(str(path), found.archive_to / path.name)
    for path in found.delete:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    if found.forget_rater:
        config.remove_local("rater")
        config.remove_local("uploaded_as")      # the upload name belongs to that rater
