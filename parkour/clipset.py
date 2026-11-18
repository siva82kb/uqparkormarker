"""The clip folder of one subject, on disk.

    data4annotation/<subject>/
        segments.csv            the sampled windows
        design.toml             copy of study.toml as it was when they were drawn
        clips/seg_0001.mp4 ...  one clip per window

A clip with its final name is always complete: clips are written under a
temporary name and renamed when finished (see extract.py).
"""

import csv
import shutil
import tomllib
from dataclasses import asdict
from pathlib import Path

from . import config
from .sampling import Segment

SEGMENTS_FILE = "segments.csv"
DESIGN_FILE = "design.toml"
CLIP_DIR = "clips"


def folder(subject: str) -> Path:
    return config.CLIPS_ROOT / subject


def clip_path(subject: str, segment_id: str) -> Path:
    return folder(subject) / CLIP_DIR / f"{segment_id}.mp4"


def write_plan(subject: str, segments: list[Segment]) -> None:
    """Record the windows and the settings they were drawn with."""
    (folder(subject) / CLIP_DIR).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config.STUDY_FILE, folder(subject) / DESIGN_FILE)
    with (folder(subject) / SEGMENTS_FILE).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=Segment.FIELDS)
        writer.writeheader()
        writer.writerows(asdict(s) for s in segments)


def read_segments(subject: str) -> list[Segment]:
    """The recorded windows; empty if none have been drawn yet."""
    path = folder(subject) / SEGMENTS_FILE
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            Segment(**{**row, "start_frame": int(row["start_frame"]),
                       "end_frame": int(row["end_frame"])})
            for row in csv.DictReader(fh)
        ]


def missing(subject: str, segments: list[Segment]) -> list[Segment]:
    """Windows whose clip has not been cut yet."""
    clips = folder(subject) / CLIP_DIR
    have = {p.stem for p in clips.glob("*.mp4")} if clips.is_dir() else set()
    return [s for s in segments if s.segment_id not in have]


def state(subject: str) -> str:
    """'none', 'partial' or 'complete'."""
    segments = read_segments(subject)
    if not segments:
        return "none"
    return "partial" if missing(subject, segments) else "complete"


def design_differences(subject: str, study: dict) -> list[str]:
    """Settings that differ between the clips' design.toml and study.toml.

    Empty when they match, or when no clips have been planned yet.
    """
    path = folder(subject) / DESIGN_FILE
    if not path.exists():
        return []
    with path.open("rb") as fh:
        then, now = _flatten(tomllib.load(fh)), _flatten(study)
    return [
        f"{key}: clips were made with {then.get(key, 'nothing')!r}, "
        f"study.toml now has {now.get(key, 'nothing')!r}"
        for key in sorted(then.keys() | now.keys())
        if then.get(key) != now.get(key)
    ]


def _flatten(value, prefix: str = "") -> dict:
    """{'a': {'b': 1}, 'c': [2]} -> {'a.b': 1, 'c.1': 2}; lists count from 1."""
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = ((str(i), v) for i, v in enumerate(value, start=1))
    else:
        return {prefix: value}
    flat = {}
    for key, inner in items:
        flat.update(_flatten(inner, f"{prefix}.{key}" if prefix else key))
    return flat
