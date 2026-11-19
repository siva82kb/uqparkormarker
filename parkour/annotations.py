"""A rater's labels for a subject's clips: the order of clips and the CSV file.

    data4annotation/<subject>/<subject>_<rater>_annotations.csv

One row is added each time a clip is labelled, and written to disk at once.
If a clip is labelled again, a new row is added; the latest row for a clip is
the one that counts. Nothing is ever rewritten or deleted.
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

FIELDS = ("segment_id", "label", "rater", "annotated_at")


def clean_name(text: str) -> str:
    """A rater's name made safe for a file name: 'Dr. Ann-Marie O'Neil' ->
    'dr_ann-marie_o_neil'. Empty if nothing usable is left."""
    return re.sub(r"[^a-z0-9-]+", "_", text.strip().lower()).strip("_")


def path(subject: str, rater: str) -> Path:
    return clipset.folder(subject) / f"{subject}_{rater}_annotations.csv"


def order(segments: list[Segment], rater: str) -> list[Segment]:
    """The clips in the order this rater sees them: shuffled, the same way
    every time for the same rater, differently for different raters."""
    seed = int.from_bytes(hashlib.sha256(rater.encode("utf-8")).digest()[:8], "big")
    shuffled = list(segments)
    Random(seed).shuffle(shuffled)
    return shuffled


def read(subject: str, rater: str) -> dict[str, str]:
    """Label of each clip labelled so far. The latest row for a clip wins."""
    file = path(subject, rater)
    if not file.exists():
        return {}
    with file.open(newline="", encoding="utf-8") as fh:
        return {row["segment_id"]: row["label"] for row in csv.DictReader(fh)}


def append(subject: str, rater: str, segment_id: str, label: str) -> None:
    """Add one label and make sure it has reached the disk."""
    file = path(subject, rater)
    is_new = not file.exists()
    with file.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "segment_id": segment_id,
            "label": label,
            "rater": rater,
            "annotated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        fh.flush()
        os.fsync(fh.fileno())


def next_position(ordered: list[Segment], labels: dict[str, str]) -> int | None:
    """Position in the rater's order of the first clip without a label, or
    None when every clip has one."""
    for position, segment in enumerate(ordered):
        if segment.segment_id not in labels:
            return position
    return None


def counts(ordered: list[Segment], labels: dict[str, str], names: list[str]) -> dict[str, int]:
    """How many of the rater's clips carry each label, in the order of `names`."""
    tally = {name: 0 for name in names}
    for segment in ordered:
        label = labels.get(segment.segment_id)
        if label is not None:
            tally[label] = tally.get(label, 0) + 1
    return tally
