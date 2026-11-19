"""Saving a rater's finished labels under a dated name, and putting them on
the RDM under that same name.

    on this computer   data4annotation/<subject>/<subject>_<name>_annotations_<YYYYMMDD-HHMMSS>.csv
    on the RDM         <share folder>/ratings/<the same file name>

When a rater has labelled every clip and reaches the finished page, the
undated work-in-progress file (see annotations.py) is given its dated name:
that is the save. The dated file is then copied to the RDM. The date and time
are the moment of saving, so the names match even if the RDM could not be
reached at once and the copy is made later. A dated file is never changed or
replaced, here or on the RDM; the most recent one for a rater is the one that
counts.

Names. Two raters must not share a name. The sign-in page warns while a name
is being typed (`taken_names`). The first upload from a computer checks
again; on a clash it adds a random three-digit number, and the files saved so
far on this computer are renamed to match. The name is then remembered in
local.toml as `uploaded_as`, and later saves and uploads from the same
computer use it without checking. So a rater must stay on one computer.

On this computer, a small note beside the label files lists the dated files
that have reached the RDM, so that each is uploaded once:

    data4annotation/<subject>/ratings_uploaded.json
"""

import json
import os
import random
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import annotations, clipset, config, share
from .share import Unreachable

NOTE_FILE = "ratings_uploaded.json"
_FILE = re.compile(r"^(?P<subject>.+?)_(?P<name>.+)_annotations_(?P<stamp>\d{8}-\d{6})\.csv$")


@dataclass
class Shared:
    """One ratings file on the RDM."""

    name: str               # the rater, as uploaded
    at: datetime
    path: Path


@dataclass
class Outcome:
    """What happened when the app tried to upload a rater's saved labels."""

    status: str             # uploaded, unchanged, unreachable, no_clips or other_clips
    name: str = ""          # the name the labels are saved and uploaded under
    file: str = ""          # the newest saved file: its name here and on the RDM
    renamed: bool = False   # True if a number was added to the name just now
    at: datetime | None = None          # when that file was saved
    previous: datetime | None = None    # an earlier upload that this one supersedes


@dataclass
class Standing:
    """Where a rater's labels are, read from this computer alone (the RDM is
    not asked, so pages can show this at once)."""

    current: Path | None    # the file that holds the most recent labels
    in_progress: bool       # True if there are changes not yet saved under a dated name
    saved: str = ""         # the newest saved file's name, if any
    saved_at: datetime | None = None
    saved_as: str = ""      # the rater name in that file's name
    uploaded: bool = False  # has that file reached the RDM?


def shared(share_folder: Path, subject: str) -> list[Shared]:
    """Every ratings file for a participant on the RDM, oldest first."""
    def look() -> list[Shared]:
        share.need_study_folder(share_folder)
        folder = share_folder / share.RATINGS
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            match = _FILE.match(path.name)
            if match and match["subject"] == subject:
                found.append(Shared(match["name"],
                                    datetime.strptime(match["stamp"], annotations.STAMP), path))
        return sorted(found, key=lambda s: s.at)
    return share.within(20, look)


def taken_names(share_folder: Path, subject: str) -> set[str]:
    """Rater names that already have ratings for this participant."""
    return {s.name for s in shared(share_folder, subject)}


def free_name(wanted: str, taken: set[str], rng: random.Random | None = None) -> str:
    """`wanted` if nobody has it, else `wanted` with a random three-digit
    number that nobody has either."""
    rng = rng or random.Random()
    name = wanted
    while name in taken:
        name = f"{wanted}_{rng.randrange(100, 1000)}"
    return name


def standing(subject: str, rater: str) -> Standing:
    saved = annotations.saved_files(subject)
    found = Standing(annotations.current_path(subject, rater),
                     annotations.in_progress(subject, rater))
    if saved:
        found.saved = saved[-1].name
        found.saved_as, found.saved_at = annotations.parse_dated(subject, saved[-1].name)
        found.uploaded = saved[-1].name in _uploaded(subject)
    return found


def save_finished(subject: str, rater: str, now: datetime | None = None) -> Path | None:
    """Give the work-in-progress file its dated name. This is the save.

    Call it only when every clip has a label. Returns the new file, or None
    if there was nothing in progress. Inside the file, the rater column
    carries the name in the file's name. Needs no RDM.
    """
    working = annotations.path(subject, rater)
    if not working.exists():
        return None
    name = (config.load_local() or {}).get("uploaded_as") or rater
    target = annotations.dated_path(subject, name, now or datetime.now())
    annotations.store(target, [{**row, "rater": name} for row in annotations.rows(working)])
    working.unlink()
    return target


def upload(share_folder: Path, subject: str, rater: str, now: datetime | None = None) -> Outcome:
    """Save the rater's labels if any are in progress, then copy to the RDM
    every saved file that is not there yet.

    Call this when every clip has a label. It never raises for an RDM that is
    out of reach: it reports `unreachable`, and the next call tries again.
    The local save happens whatever the RDM does.
    """
    save_finished(subject, rater, now)
    saved = annotations.saved_files(subject)
    if not saved:
        return Outcome("unchanged")
    pending = [file for file in saved if file.name not in _uploaded(subject)]

    def about(status: str, **more) -> Outcome:      # described by the newest saved file
        name, at = annotations.parse_dated(subject, annotations.saved_files(subject)[-1].name)
        return Outcome(status, name, annotations.saved_files(subject)[-1].name, at=at, **more)

    if not pending:
        return about("unchanged")
    try:
        on_rdm = share.shared_id(share_folder, subject)
        if on_rdm is None:
            return about("no_clips")            # the clips must be shared first
        if on_rdm != clipset.set_id(subject):
            return about("other_clips")         # these labels are for different clips

        remembered = (config.load_local() or {}).get("uploaded_as")
        earlier = shared(share_folder, subject)
        name = remembered or free_name(rater, {s.name for s in earlier})
        if name != rater and not remembered:    # a clash, found only now: rename what was saved
            pending = [_under_name(subject, file, name) for file in pending]
        mine = [s for s in earlier if s.name == name] if remembered else []
        for file in pending:
            share.within(60, _copy, file, share_folder / share.RATINGS / file.name)
            _note_uploaded(subject, file.name)
    except Unreachable:
        return about("unreachable")

    if not remembered:
        config.set_local("uploaded_as", name)
    return about("uploaded", renamed=name != rater, previous=mine[-1].at if mine else None)


def _under_name(subject: str, file: Path, name: str) -> Path:
    """Rename a saved file so that it carries `name`, in its file name and in
    its rater column. Used only before a file has ever been uploaded."""
    _, at = annotations.parse_dated(subject, file.name)
    target = annotations.dated_path(subject, name, at)
    annotations.store(target, [{**row, "rater": name} for row in annotations.rows(file)])
    file.unlink()
    return target


def _copy(source: Path, target: Path) -> None:
    """Copy a saved file to the RDM under a temporary name, then rename it:
    never a half-written file there, and never one replaced."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    partial = target.with_name(target.name + share.PART)
    partial.write_bytes(source.read_bytes())
    os.replace(partial, target)


def _uploaded(subject: str) -> set[str]:
    """Names of the saved files that have reached the RDM."""
    path = clipset.folder(subject) / NOTE_FILE
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("uploaded", []))
    except (OSError, ValueError, AttributeError):
        return set()


def _note_uploaded(subject: str, file_name: str) -> None:
    names = sorted(_uploaded(subject) | {file_name})
    (clipset.folder(subject) / NOTE_FILE).write_text(
        json.dumps({"uploaded": names}), encoding="utf-8")


# ---- Uploading in the background ----
#
# The RDM is slow, so a page must not wait for an upload. The finished page
# starts one here, shows itself at once, and asks for the outcome until it
# is there.

_lock = threading.Lock()
_running = False
_outcome: tuple[str, str, Outcome] | None = None     # subject, rater, what happened


def start(share_folder: Path, subject: str, rater: str) -> None:
    """Begin uploading the rater's saved labels, unless an upload is already
    under way. The outcome is picked up later with `outcome`."""
    global _running, _outcome
    with _lock:
        if _running:
            return
        _running, _outcome = True, None

    def work() -> None:
        global _running, _outcome
        try:
            result = upload(share_folder, subject, rater)
        except Exception:                   # anything unexpected: try again next time
            result = Outcome("unreachable")
        with _lock:
            _running, _outcome = False, (subject, rater, result)

    threading.Thread(target=work, daemon=True).start()


def outcome(subject: str, rater: str) -> Outcome | None:
    """What the last upload for this rater came to, or None while it is
    still under way (or if none has been started)."""
    with _lock:
        if _running or _outcome is None or _outcome[:2] != (subject, rater):
            return None
        return _outcome[2]
