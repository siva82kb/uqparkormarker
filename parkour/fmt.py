"""Format values for display. Used as template filters."""

from datetime import datetime


def duration(seconds: float) -> str:
    """Seconds as a short readable length: '8.4 s', '2 min 05 s', '1 h 01 min'."""
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def clock(iso_time: str) -> str:
    """The time of day from an ISO timestamp, to the millisecond:
    '2026-06-29T10:44:36.186283+10:00' -> '10:44:36.186'."""
    moment = datetime.fromisoformat(iso_time)
    return f"{moment:%H:%M:%S}.{moment.microsecond // 1000:03d}"


def clip_number(segment_id: str) -> int:
    """'seg_0042' -> 42."""
    return int(segment_id.rsplit("_", 1)[-1])


def share(fraction: float) -> str:
    """A fraction as a percentage that keeps small values visible: '97.5%', '0.03%'."""
    if fraction <= 0:
        return "0%"
    if fraction < 0.0001:
        return "under 0.01%"
    return f"{fraction:.2%}" if fraction < 0.01 else f"{fraction:.1%}"
