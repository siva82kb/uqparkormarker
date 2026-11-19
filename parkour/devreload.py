"""Developer mode: tell an open page when the app's files have changed.

Started with `uv run python app.py --dev`. Raters never use it.

In developer mode Flask restarts the server when a Python file changes and
reads templates afresh on every request. This module adds the missing part:
the page in the browser asks for `stamp()` once a second and reloads itself
when the answer changes (see app.js).
"""

from pathlib import Path

from . import config

WATCHED = (                 # folder or file, and the kinds of file that count
    ("templates", (".html",)),
    ("static", (".css", ".js")),
    ("parkour", (".py",)),
    ("app.py", ()),
    ("study.toml", ()),
)


def stamp(root: Path = config.ROOT) -> str:
    """A value that changes whenever a watched file is saved, added or removed."""
    newest, count = 0, 0
    for name, kinds in WATCHED:
        path = root / name
        files = [path] if path.is_file() else [
            f for f in path.rglob("*") if f.suffix in kinds
        ] if path.is_dir() else []
        for file in files:
            newest = max(newest, file.stat().st_mtime_ns)
            count += 1
    return f"{newest}-{count}"
