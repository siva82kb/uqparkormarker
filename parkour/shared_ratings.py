"""Ratings in the shared folder on the RDM: names in use, and uploading.

    <share folder>/ratings/<subject>_<name>_annotations_<YYYYMMDD-HHMMSS>.csv

A rater's label file is copied here when they have labelled every clip. An
upload never replaces an earlier one; the most recent file for a rater is the
one that counts.

Names. Two raters must not share a name. The sign-in page warns while a name
is being typed (`taken_names`). The first upload from a computer checks
again; on a clash it adds a random three-digit number. The name used is then
remembered in local.toml as `uploaded_as`, and later uploads from the same
computer use it without checking. So a rater must stay on one computer.

On this computer, a small note beside the label file records what was last
uploaded, so the same labels are not uploaded twice:

    data4annotation/<subject>/ratings_uploaded.json
"""

import csv
import hashlib
import io
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import annotations, clipset, config, share
from .share import Unreachable

NOTE_FILE = "ratings_uploaded.json"
STAMP = "%Y%m%d-%H%M%S"
_FILE = re.compile(r"^(?P<subject>.+?)_(?P<name>.+)_annotations_(?P<stamp>\d{8}-\d{6})\.csv$")


@dataclass
class Shared:
    """One ratings file on the RDM."""

    name: str               # the rater, as uploaded
    at: datetime
    path: Path


@dataclass
class Outcome:
    """What happened when the app tried to upload a rater's labels."""

    status: str             # uploaded, unchanged, unreachable, no_clips or other_clips
    name: str = ""          # the name the ratings are (or were last) uploaded under
    renamed: bool = False   # True if a number was added to the name just now
    at: datetime | None = None          # when this upload, or the last one, was made
    previous: datetime | None = None    # an earlier upload that this one supersedes


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
                                    datetime.strptime(match["stamp"], STAMP), path))
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


def upload(share_folder: Path, subject: str, rater: str, now: datetime | None = None) -> Outcome:
    """Copy the rater's labels to the RDM, if there is anything new to copy.

    Call this when every clip has a label. It never raises for an RDM that is
    out of reach: it reports `unreachable`, and the next call tries again.
    """
    local_file = annotations.path(subject, rater)
    content = local_file.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    note = _read_note(subject)
    if note.get("digest") == digest:
        return Outcome("unchanged", note["name"], at=datetime.fromisoformat(note["at"]))

    try:
        on_rdm = share.shared_id(share_folder, subject)
        if on_rdm is None:
            return Outcome("no_clips")          # the clips must be shared first
        if on_rdm != clipset.set_id(subject):
            return Outcome("other_clips")       # these labels are for different clips

        remembered = (config.load_local() or {}).get("uploaded_as")
        earlier = shared(share_folder, subject)
        name = remembered or free_name(rater, {s.name for s in earlier})
        mine = [s for s in earlier if s.name == name] if remembered else []
        now = now or datetime.now()
        target = (share_folder / share.RATINGS /
                  f"{subject}_{name}_annotations_{now.strftime(STAMP)}.csv")
        share.within(60, _write, target, _renamed(content, name))
    except Unreachable:
        return Outcome("unreachable")

    if not remembered:
        config.set_local("uploaded_as", name)
    _write_note(subject, {"digest": digest, "name": name, "file": target.name,
                          "at": now.isoformat(timespec="seconds")})
    return Outcome("uploaded", name, renamed=name != rater, at=now,
                   previous=mine[-1].at if mine else None)


def _renamed(content: bytes, name: str) -> bytes:
    """The label file with `name` in the rater column of every row, so that
    the file's name and its rows agree."""
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8"), newline="")))
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=annotations.FIELDS)
    writer.writeheader()
    writer.writerows({**row, "rater": name} for row in rows)
    return out.getvalue().encode("utf-8")


def _write(target: Path, content: bytes) -> None:
    """Write under a temporary name, then rename: never a half-written file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + share.PART)
    partial.write_bytes(content)
    os.replace(partial, target)


def _read_note(subject: str) -> dict:
    path = clipset.folder(subject) / NOTE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_note(subject: str, note: dict) -> None:
    (clipset.folder(subject) / NOTE_FILE).write_text(json.dumps(note), encoding="utf-8")
