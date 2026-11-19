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


def set_local(key: str, text: str) -> None:
    """Set one text value in local.toml, leaving the rest of the file as it is."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    line = f'{key} = "{escaped}"'
    lines = LOCAL_FILE.read_text(encoding="utf-8").splitlines() if LOCAL_FILE.exists() else []
    for i, existing in enumerate(lines):
        if existing.split("=")[0].strip() == key:
            lines[i] = line
            break
    else:
        lines.append(line)
    LOCAL_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remove_local(key: str) -> None:
    """Take one value out of local.toml, leaving the rest of the file as it is."""
    if not LOCAL_FILE.exists():
        return
    lines = LOCAL_FILE.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.split("=")[0].strip() != key]
    LOCAL_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
