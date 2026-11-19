"""A rater's labels for a subject's clips: the order of clips and the CSV files.

Every clip gets two labels: one for the participant's right arm and one for
their left arm. Right and left always mean the participant's own right and
left, whichever way they are facing. A file has exactly one row per clip.

File names say where things stand:

    <subject>_<rater>_annotations.csv
        no date: work in progress. It holds changes that have not been saved
        yet, and is what the app shows.

    <subject>_<name>_annotations_<YYYYMMDD-HHMMSS>.csv
        saved. Made when every clip is labelled and the rater reaches the
        finished page (see shared_ratings.py); the same name is used on the
        RDM. If only dated files exist, the newest is what the app shows.

A row is written when the rater confirms a clip by moving on from it. If the
rater later changes a clip's labels, its row is rewritten, never added to.
The first change after a save starts a new undated file, as a full copy of
the newest dated file with that one row changed; the dated files are not
touched, so they are the record of what was saved before.
"""

import csv
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from random import Random

from . import clipset
from .sampling import Segment

ARMS = ("right", "left")        # in the order they are shown, left to right, on the page
# Keys that choose an arm on the labelling page. The first of each pair is
# within reach of the hand that rests on 1 to 5; the second is the initial.
ARM_KEYS = {"right": ("a", "r"), "left": ("f", "l")}
FIELDS = ("segment_id", "right_label", "left_label", "rater", "annotated_at")
STAMP = "%Y%m%d-%H%M%S"         # the date and time in the name of a saved file
_COLUMN = {arm: f"{arm}_label" for arm in ARMS}     # the column that holds each arm's label

Labels = dict[str, dict[str, str]]      # clip -> arm -> label


def clean_name(text: str) -> str:
    """A rater's name made safe for a file name: 'Dr. Ann-Marie O'Neil' ->
    'dr_ann-marie_o_neil'. Empty if nothing usable is left."""
    return re.sub(r"[^a-z0-9-]+", "_", text.strip().lower()).strip("_")


# ---- The files ----

def path(subject: str, rater: str) -> Path:
    """The undated file: work in progress."""
    return clipset.folder(subject) / f"{subject}_{rater}_annotations.csv"


def dated_path(subject: str, name: str, at: datetime) -> Path:
    """A saved file, for the rater name it is saved under and the moment of saving."""
    return clipset.folder(subject) / f"{subject}_{name}_annotations_{at.strftime(STAMP)}.csv"


def parse_dated(subject: str, file_name: str) -> tuple[str, datetime] | None:
    """(rater name, when saved) if this is the name of a saved file for the
    subject, else None."""
    match = re.match(rf"^{re.escape(subject)}_(.+)_annotations_(\d{{8}}-\d{{6}})\.csv$", file_name)
    return (match[1], datetime.strptime(match[2], STAMP)) if match else None


def saved_files(subject: str) -> list[Path]:
    """The saved (dated) files on this computer, oldest first. One rater uses
    a computer, so they are all that rater's."""
    folder = clipset.folder(subject)
    found = [p for p in folder.glob(f"{subject}_*_annotations_*.csv")
             if parse_dated(subject, p.name)] if folder.is_dir() else []
    return sorted(found, key=lambda p: parse_dated(subject, p.name)[1])


def current_path(subject: str, rater: str) -> Path | None:
    """The file that holds the most recent labels: the undated one if there
    is one, else the newest dated one, else None."""
    working = path(subject, rater)
    if working.exists():
        return working
    saved = saved_files(subject)
    return saved[-1] if saved else None


def in_progress(subject: str, rater: str) -> bool:
    """Are there labels that have not been saved under a dated name yet?"""
    return path(subject, rater).exists()


# ---- Reading and writing ----

def order(segments: list[Segment], rater: str) -> list[Segment]:
    """The clips in the order this rater sees them: shuffled, the same way
    every time for the same rater, differently for different raters."""
    seed = int.from_bytes(hashlib.sha256(rater.encode("utf-8")).digest()[:8], "big")
    shuffled = list(segments)
    Random(seed).shuffle(shuffled)
    return shuffled


def rows(file: Path | None) -> list[dict]:
    """The rows of a label file, one per clip. A file with an older layout
    has other columns; its rows cannot be used and are passed over. Older
    files could hold several rows for a clip; the last one is kept."""
    if file is None or not file.exists():
        return []
    by_clip: dict[str, dict] = {}
    with file.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if all(row.get(column) for column in _COLUMN.values()):
                by_clip[row["segment_id"]] = {field: row.get(field, "") for field in FIELDS}
    return list(by_clip.values())


def store(file: Path, content: list[dict]) -> None:
    """Write a whole label file. It is written under a temporary name and
    then swapped in, so the file is never left half-written."""
    partial = file.with_name(file.name + ".part")
    with partial.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(partial, file)


def read(subject: str, rater: str) -> Labels:
    """The labels of both arms of each clip confirmed so far, from the file
    that holds the most recent labels."""
    return {row["segment_id"]: {arm: row[_COLUMN[arm]] for arm in ARMS}
            for row in rows(current_path(subject, rater))}


def save(subject: str, rater: str, segment_id: str, both: dict[str, str]) -> None:
    """Record a clip's two labels, {"right": ..., "left": ...}.

    The clip's row is rewritten if it has one, else added, so the file keeps
    one row per clip. The row goes into the undated file. If there is none
    (everything so far has been saved under a dated name), one is started as
    a full copy of the newest dated file.
    """
    if set(both) != set(ARMS) or not all(both.values()):
        raise ValueError(f"a label is needed for each arm, got {both!r}")
    working = path(subject, rater)
    _set_aside_if_older_layout(working)
    content = rows(current_path(subject, rater))
    new = {
        "segment_id": segment_id,
        **{_COLUMN[arm]: both[arm] for arm in ARMS},
        "rater": rater,
        "annotated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    for row in content:
        row["rater"] = rater        # a dated file may carry the name used on the RDM
    for position, row in enumerate(content):
        if row["segment_id"] == segment_id:
            content[position] = new
            break
    else:
        content.append(new)
    store(working, content)


def _set_aside_if_older_layout(file: Path) -> None:
    """A label file made with an earlier layout has other columns. New rows
    must not be mixed into it, so it is renamed (never deleted) and a fresh
    file is started."""
    if not file.exists():
        return
    with file.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh), [])
    if tuple(header) != FIELDS:
        stamp = datetime.now().strftime(STAMP)
        file.rename(file.with_name(f"{file.stem}_older_layout_{stamp}.csv"))


# ---- What the labels add up to ----

def complete(labels: Labels, segment_id: str) -> bool:
    """Has this clip been confirmed, with a label for each arm?"""
    return all(arm in labels.get(segment_id, {}) for arm in ARMS)


def n_complete(ordered: list[Segment], labels: Labels) -> int:
    """How many of the rater's clips have been labelled and confirmed."""
    return sum(complete(labels, segment.segment_id) for segment in ordered)


def next_position(ordered: list[Segment], labels: Labels) -> int | None:
    """Position in the rater's order of the first clip not yet labelled and
    confirmed, or None when every clip has been."""
    for position, segment in enumerate(ordered):
        if not complete(labels, segment.segment_id):
            return position
    return None


def counts(ordered: list[Segment], labels: Labels, names: list[str]) -> dict[str, dict[str, int]]:
    """For each label, in the order of `names`, how many of the rater's clips
    carry it on each arm: {label: {"right": n, "left": n}}."""
    tally = {name: dict.fromkeys(ARMS, 0) for name in names}
    for segment in ordered:
        for arm, label in labels.get(segment.segment_id, {}).items():
            tally.setdefault(label, dict.fromkeys(ARMS, 0))[arm] += 1
    return tally
