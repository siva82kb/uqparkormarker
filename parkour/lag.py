"""Measure how late each frame's timestamp is. A measurement only.

Nothing here is used to choose clips or to correct any time. It exists so
the docs pages on timestamps can show the size of the problem and check the rule in
`timing.py` against it.

The idea, for one video:

  - A frame was filmed no later than its own stamp (a stamp is never early).
  - The camera films at a steady rate. So a frame was also filmed at least
    k frame-times before the frame k places after it, and so no later than
    that later frame's stamp minus k frame-times.

The earliest of these limits, over the frames that follow within
`look_ahead_seconds`, is the latest moment the frame can have been filmed.
The stamp minus that moment is the frame's lag. It is a lower limit: the
true lag can be larger (by the fixed camera delay, at least), never smaller.
"""

from collections import deque

LOOK_AHEAD_SECONDS = 60.0


def lags(times: list[int], frame_rate: float,
         look_ahead_seconds: float = LOOK_AHEAD_SECONDS) -> list[float]:
    """Seconds by which each stamp is late, at least. `times` in microseconds."""
    if not times or not frame_rate:
        return []
    period = 1_000_000 / frame_rate
    reach = max(1, round(look_ahead_seconds * frame_rate))
    # level[j] is frame j's stamp moved back by j frame-times. Frame i's limit
    # is the lowest level among frames i .. i + reach, moved forward again.
    level = [t - j * period for j, t in enumerate(times)]
    lowest = [0.0] * len(times)
    queue: deque[int] = deque()             # indexes whose levels increase
    for i in range(len(times) - 1, -1, -1):
        while queue and level[queue[-1]] >= level[i]:
            queue.pop()
        queue.append(i)
        if queue[0] > i + reach:
            queue.popleft()
        lowest[i] = level[queue[0]]
    return [(level[i] - lowest[i]) / 1_000_000 for i in range(len(times))]
