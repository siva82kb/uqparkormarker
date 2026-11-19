"""Small helpers for drawing charts as plain SVG in the templates.

An Axis knows its range of values and its round tick marks. A template asks
it where a value falls between two pixel positions. No drawing happens here.
"""

from dataclasses import dataclass
from math import ceil, floor, log10


@dataclass
class Axis:
    low: float
    high: float
    ticks: list[float]

    def at(self, value: float, start: float, end: float) -> float:
        """Pixel position of `value` when the axis runs from `start` to `end`."""
        span = (self.high - self.low) or 1.0
        return round(start + (value - self.low) / span * (end - start), 2)


def axis(low: float, high: float, about: int = 5) -> Axis:
    """An axis covering low..high, widened to round ticks, about `about` of them."""
    if high <= low:
        high = low + 1.0
    step = _round_step((high - low) / about)
    first, last = floor(low / step), ceil(high / step)
    ticks = [round(k * step, 10) for k in range(first, last + 1)]
    return Axis(ticks[0], ticks[-1], ticks)


def _round_step(rough: float) -> float:
    """The nearest of 1, 2, 5 times a power of ten at or above `rough`."""
    power = 10 ** floor(log10(rough))
    return next(m * power for m in (1, 2, 5, 10) if m * power >= rough * 0.999)


def runs(flags: list[bool]) -> list[tuple[int, int]]:
    """(first, last) index of every unbroken run of True values."""
    found, start = [], None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            found.append((start, i - 1))
            start = None
    if start is not None:
        found.append((start, len(flags) - 1))
    return found
