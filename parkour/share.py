"""The shared folder on the RDM: where clips are put for every rater to use.

    <study folder>/<share folder>/
        clips/<subject>/<subject>_clips.zip        everything a rater needs
        clips/<subject>/<subject>_clips_id.txt     the set id (see clipset.set_id)
        ratings/                                   see shared_ratings.py

The name of the share folder is `folder` under `[share]` in study.toml.

The zip holds the clips, segments.csv, design.toml and the saved reading of
the videos. It never holds a label file. A zip is written under a temporary
name and renamed when complete, on the RDM and on this computer, so a
half-copied zip is never taken for a whole one.

The RDM is slow and may be out of reach (VPN off). Functions here raise
`Unreachable` for that; callers say so to the person and try again later.
"""

import csv
import os
import re
import shutil
import threading
import tomllib
import zipfile
from pathlib import Path
from typing import Callable

from . import clipset, recording_store

CLIPS = "clips"
RATINGS = "ratings"
PART = ".part"
CHUNK = 4 * 1024 * 1024                 # bytes copied at a time
_CLIP_MEMBER = re.compile(rf"^{clipset.CLIP_DIR}/seg_\d+\.mp4$")
_PLAIN_MEMBERS = (clipset.SEGMENTS_FILE, clipset.DESIGN_FILE, recording_store.FILE)

Progress = Callable[[int, int, str], None]      # done, total, what is happening


class Unreachable(Exception):
    """The study folder on the RDM cannot be reached just now."""


class Mismatch(Exception):
    """The shared clips were made with settings other than this app's."""

    def __init__(self, differences: list[str]):
        super().__init__("The shared clips were made with different settings.")
        self.differences = differences


def root(local: dict, study: dict) -> Path:
    """The share folder, inside the study folder named in local.toml."""
    return Path(local["source_dir"]) / study["share"]["folder"]


def zip_path(share: Path, subject: str) -> Path:
    return share / CLIPS / subject / f"{subject}_clips.zip"


def id_path(share: Path, subject: str) -> Path:
    return share / CLIPS / subject / f"{subject}_clips_id.txt"


def within(seconds: float, action: Callable, *arguments):
    """Run `action`, giving up after `seconds`. A drive that is out of reach
    can make a simple check hang for a long time; this turns that, and any
    error from the drive, into `Unreachable`."""
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["value"] = action(*arguments)
        except OSError as problem:
            outcome["error"] = problem

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive() or "error" in outcome:
        raise Unreachable(str(outcome.get("error", "no answer from the drive")))
    return outcome["value"]


def reachable(folder: Path, seconds: float = 8) -> bool:
    """Can this folder be seen right now?"""
    try:
        return bool(within(seconds, Path(folder).is_dir))
    except Unreachable:
        return False


def need_study_folder(share: Path) -> None:
    """Fail, as an error from the drive, if the study folder cannot be seen.
    A missing file on a drive that is out of reach looks just like a file
    that is not there, so the folder itself is checked first. (The share
    folder may not exist yet; the study folder it sits in must.)"""
    if not share.parent.is_dir():
        raise OSError(f"cannot open {share.parent}")


def shared_subjects(share: Path) -> list[str]:
    """Participants that have a zip of clips in the share folder."""
    def look() -> list[str]:
        need_study_folder(share)
        folder = share / CLIPS
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if zip_path(share, p.name).is_file())
    return within(20, look)


def shared_id(share: Path, subject: str) -> str | None:
    """The set id of the participant's shared clips, or None if no clips are
    shared. Raises Unreachable if the RDM cannot be asked."""
    def look() -> str | None:
        need_study_folder(share)
        if not zip_path(share, subject).is_file():
            return None
        note = id_path(share, subject)
        if note.is_file():
            return note.read_text(encoding="utf-8").strip()
        with zipfile.ZipFile(zip_path(share, subject)) as archive:     # no note: work it out
            return clipset.content_id(archive.read(clipset.SEGMENTS_FILE),
                                      archive.read(clipset.DESIGN_FILE))
    return within(30, look)


def shared_differences(share: Path, subject: str, study: dict) -> list[str]:
    """Settings that differ between the shared clips and this app's study.toml."""
    def look() -> list[str]:
        with zipfile.ZipFile(zip_path(share, subject)) as archive:
            design = tomllib.loads(archive.read(clipset.DESIGN_FILE).decode("utf-8"))
        return clipset.differences(design, study)
    return within(60, look)


def standing(share: Path, subject: str, limited: bool = False) -> str:
    """How this computer's finished clips stand against the RDM:

    upload       the RDM has no clips for the participant; these can be uploaded
    limited      as above, but the clip_limit test setting is on, so they must not be
    shared       the RDM has these very clips
    other        the RDM has a different set of clips for the participant
    unreachable  the RDM cannot be asked just now
    """
    try:
        on_rdm = shared_id(share, subject)
    except Unreachable:
        return "unreachable"
    if on_rdm is None:
        return "limited" if limited else "upload"
    return "shared" if on_rdm == clipset.set_id(subject) else "other"


def candidates(source: Path, share: Path) -> tuple[str, list[str]]:
    """The participants a new user can be set up with, and where they come
    from: ("shared", names) if the RDM has shared clips for any participant,
    else ("source", names) for the participant folders in the study folder."""
    from . import dataset           # here, to keep this module free of video reading

    ready = shared_subjects(share)
    if ready:
        return "shared", ready
    return "source", within(30, dataset.subject_names, source)


def pack(share: Path, subject: str, report: Progress = lambda *_: None) -> Path:
    """Put this computer's clips for a participant on the RDM as one zip.

    Never replaces a zip that is already there. Clips are stored as they are
    (video does not compress), so packing costs little more than copying.
    """
    target = zip_path(share, subject)
    try:
        need_study_folder(share)
    except OSError as problem:
        raise Unreachable(str(problem)) from problem
    if target.exists():
        raise FileExistsError(f"Clips for {subject} are already on the RDM.")
    folder = clipset.folder(subject)
    clips = sorted((folder / clipset.CLIP_DIR).glob("seg_*.mp4"))
    plain = [folder / name for name in _PLAIN_MEMBERS if (folder / name).exists()]

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + PART)
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as archive:
            for path in plain:
                archive.write(path, path.name)
            for done, clip in enumerate(clips):
                report(done, len(clips), f"Uploading clip {done + 1} of {len(clips)}")
                archive.write(clip, f"{clipset.CLIP_DIR}/{clip.name}")
        if target.exists():             # someone else finished first
            raise FileExistsError(f"Clips for {subject} are already on the RDM.")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    id_path(share, subject).write_text(clipset.set_id(subject) + "\n", encoding="utf-8")
    report(len(clips), len(clips), "The clips are on the RDM.")
    return target


def unpack(share: Path, subject: str, subject_dir: Path, study: dict,
           report: Progress = lambda *_: None) -> None:
    """Fetch a participant's shared clips and put them where this computer's
    clips live. Nothing is put in place unless everything arrived.

    Raises Mismatch, before downloading, if the clips were made with settings
    other than this app's.
    """
    differing = shared_differences(share, subject, study)
    if differing:
        raise Mismatch(differing)

    folder = clipset.folder(subject)
    if (folder / clipset.SEGMENTS_FILE).exists():
        raise FileExistsError(f"There are already clips for {subject} on this computer.")
    folder.mkdir(parents=True, exist_ok=True)
    local_zip = folder / f"{subject}_clips.zip{PART}"
    incoming = folder / "incoming"
    try:
        _copy(zip_path(share, subject), local_zip, report)
        report(0, 0, "Unpacking the clips…")        # 0 of 0: keep the bar where it is
        shutil.rmtree(incoming, ignore_errors=True)
        with zipfile.ZipFile(local_zip) as archive:
            wanted = [name for name in archive.namelist()
                      if name in _PLAIN_MEMBERS or _CLIP_MEMBER.match(name)]
            archive.extractall(incoming, wanted)        # label files are never taken
        _install(incoming, folder, subject, subject_dir)
    finally:
        local_zip.unlink(missing_ok=True)
        shutil.rmtree(incoming, ignore_errors=True)
    report(0, 0, "The clips are ready.")


def _copy(source: Path, target: Path, report: Progress) -> None:
    """Copy a large file in pieces, reporting megabytes as it goes."""
    total = source.stat().st_size
    megabytes = lambda size: max(1, round(size / 1_000_000))
    copied = 0
    with source.open("rb") as origin, target.open("wb") as copy:
        while piece := origin.read(CHUNK):
            copy.write(piece)
            copied += len(piece)
            report(megabytes(copied), megabytes(total), "Downloading the clips from the RDM…")
    if copied != total:
        raise OSError("The download was cut short.")


def _install(incoming: Path, folder: Path, subject: str, subject_dir: Path) -> None:
    """Check what was unpacked, then move it into the participant's folder."""
    for name in (clipset.SEGMENTS_FILE, clipset.DESIGN_FILE):
        if not (incoming / name).is_file():
            raise OSError(f"The shared zip has no {name}.")
    with (incoming / clipset.SEGMENTS_FILE).open(newline="", encoding="utf-8") as fh:
        listed = [row["segment_id"] for row in csv.DictReader(fh)]
    absent = [name for name in listed
              if not (incoming / clipset.CLIP_DIR / f"{name}.mp4").is_file()]
    if not listed or absent:
        raise OSError(f"The shared zip is missing {len(absent)} of {len(listed)} clips.")

    clips = folder / clipset.CLIP_DIR
    if clips.is_dir() and not any(clips.iterdir()):
        clips.rmdir()                               # an empty folder left by a reset
    shutil.move(str(incoming / clipset.CLIP_DIR), clips)
    shutil.move(str(incoming / clipset.DESIGN_FILE), folder / clipset.DESIGN_FILE)
    # The list of clips goes in last: its presence is what says "clips exist".
    shutil.move(str(incoming / clipset.SEGMENTS_FILE), folder / clipset.SEGMENTS_FILE)

    reading = incoming / recording_store.FILE
    if reading.is_file() and not (folder / recording_store.FILE).exists():
        shutil.move(str(reading), folder / recording_store.FILE)
        recording_store.adopt(subject_dir)          # read on another computer's drive
