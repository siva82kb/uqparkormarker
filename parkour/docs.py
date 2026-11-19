"""The docs pages: which exist, in what order, and what each one needs.

This list is the single place that decides the contents page, the order of
"previous" and "next", and the address of every docs page (/docs/<slug>).
"""

from dataclasses import dataclass

from . import sampling, timing_sketch


@dataclass(frozen=True)
class Page:
    slug: str                   # the address is /docs/<slug>
    title: str
    about: str                  # one line for the contents page
    needs_videos: bool = False  # shows measurements from the subject's videos

    @property
    def template(self) -> str:
        return f"docs/{self.slug.replace('-', '_')}.html"


@dataclass(frozen=True)
class Group:
    title: str
    about: str
    pages: tuple[Page, ...]


GROUPS = (
    Group(
        "How the app works",
        "What happens between a participant's videos and the clips a rater sees.",
        (
            Page("clips", "From videos to clips",
                 "The four steps, how the clips are picked, and what is saved for each clip and each label."),
        ),
    ),
    Group(
        "The timestamp problem",
        "Some frame timestamps are late. Read these four pages in order.",
        (
            Page("timing-problem", "Some timestamps are late",
                 "How the recording program stamps frames, and what a late stretch looks like."),
            Page("timing-evidence", "What this participant's timestamps show",
                 "The problem measured in the participant's own timestamp files.",
                 needs_videos=True),
            Page("timing-rule", "The rule the app uses",
                 "The rule, a check of it, what it costs, points for and against, and the other ways considered.",
                 needs_videos=True),
            Page("timing-open", "What the rule does not settle",
                 "Lining clips up with the sensors, and the questions still open."),
        ),
    ),
    Group(
        "Using the results",
        "For anyone who will interpret the labels.",
        (
            Page("interpreting", "What to keep in mind",
                 "What the clips are a sample of, how exact their times are, and what is not settled."),
        ),
    ),
)

PAGES = tuple(page for group in GROUPS for page in group.pages)


def find(slug: str) -> tuple[Page, Page | None, Page | None] | None:
    """(the page, the one before it, the one after it), or None if unknown."""
    for at, page in enumerate(PAGES):
        if page.slug == slug:
            before = PAGES[at - 1] if at else None
            after = PAGES[at + 1] if at + 1 < len(PAGES) else None
            return page, before, after
    return None


def group_of(page: Page) -> Group:
    return next(group for group in GROUPS if page in group.pages)


CAMERA_RATE = 30            # frames per second in the study recordings


def settings(study: dict) -> dict:
    """The study.toml values that the docs pages quote, ready to print.

    Pages must take these from here and never write the numbers out, so a
    change to study.toml shows on every page.
    """
    seconds = study["sampling"]["window_seconds"]
    wanted = sampling.quotas(study["sampling"])
    return {
        "n_clips": study["sampling"]["n_segments"],
        # Clips wanted from each kind of video; None if no share is set.
        "n_task_clips": wanted and wanted["task"],
        "n_unlabelled_clips": wanted and wanted["unlabelled"],
        "task_percent": wanted and f"{100 * study['sampling']['task_share']:g}",
        "clip_seconds": f"{seconds:g}",
        "clip_frames": round(seconds * CAMERA_RATE),
        "max_step": f"{study['timing']['max_step_seconds']:g}",
        "n_labels": len(study["labels"]),
    }


def figures(study: dict) -> dict:
    """The made-up recordings that the diagrams are drawn from."""
    return {
        "sketch": timing_sketch.record(n_frames=40, busy_at=8, busy_frames=6),
        "example": timing_sketch.rule_example(
            study["sampling"]["window_seconds"], study["timing"]["max_step_seconds"]
        ),
    }
