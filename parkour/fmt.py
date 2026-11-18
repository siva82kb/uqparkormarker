"""Format values for display. Used as template filters."""


def duration(seconds: float) -> str:
    """Seconds as a short readable length: '8.4 s', '2 min 05 s', '1 h 01 min'."""
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"
