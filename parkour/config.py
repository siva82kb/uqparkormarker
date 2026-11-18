"""Load the two settings files.

study.toml  the study design; committed, the same for every rater.
local.toml  this machine's setup; written by the app, ignored by git.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUDY_FILE = ROOT / "study.toml"
LOCAL_FILE = ROOT / "local.toml"
CLIPS_ROOT = ROOT / "data4annotation"


def _load(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_study() -> dict:
    """The study design. Missing or malformed is an error."""
    return _load(STUDY_FILE)


def load_local() -> dict | None:
    """This machine's setup, or None if setup has not been done yet."""
    return _load(LOCAL_FILE) if LOCAL_FILE.exists() else None
