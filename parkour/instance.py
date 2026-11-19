"""What this running copy of the app says about itself.

`run.bat` asks before it starts anything: is the app's port already in use,
and if so, by which copy? A second double-click on the same copy should only
open the browser. A copy in a different folder is another matter: the person
is told where it runs from and asked whether to close it.
"""

import os

from . import config, extract, loader, shared_ratings, transfer

NAME = "uq-parkour-annotator"       # how run.bat knows it is this app at all


def busy() -> str:
    """Slow work this copy is in the middle of, in words, or "" if none.
    Closing the copy cuts this work off; it carries on at the next start."""
    doing = []
    if loader._progress.state == "running":
        doing.append("reading the videos")
    if extract._progress.state == "running":
        doing.append("generating clips")
    if transfer._progress.state == "running":
        doing.append("uploading clips" if transfer._progress.kind == "upload"
                     else "downloading clips")
    if shared_ratings._running:
        doing.append("uploading labels")
    return " and ".join(doing)


def describe() -> dict:
    """The app's name, the folder this copy runs from, its process number
    (so that it can be closed) and what it is busy with."""
    return {"app": NAME, "folder": str(config.ROOT), "pid": os.getpid(), "busy": busy()}
