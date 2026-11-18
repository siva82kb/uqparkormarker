"""Decode .vidt files: one timestamp per video frame.

Each timestamp is 8 bytes in temporenc "DTS" form with microsecond precision
(https://temporenc.org). Read as one big-endian 64-bit number, the bits are:

    01  01  yyyyyyyyyyyy mmmm ddddd  hhhhh mmmmmm ssssss  (20 bits of us)  00
    tag precision  date (21 bits)       time (17 bits)     microseconds   pad

Month and day are stored counting from zero. The times carry no time zone;
they are local wall-clock time.
"""

from datetime import datetime
from pathlib import Path

RECORD_BYTES = 8
_TAG_DTS_MICROSECONDS = 0b0101  # tag 01 (DTS) followed by precision 01 (us)


def decode_timestamp(record: bytes) -> datetime:
    """Decode one 8-byte record into a naive local datetime."""
    if len(record) != RECORD_BYTES:
        raise ValueError(f"expected {RECORD_BYTES} bytes, got {len(record)}")
    value = int.from_bytes(record, "big")
    if value >> 60 != _TAG_DTS_MICROSECONDS:
        raise ValueError("not a temporenc DTS timestamp with microseconds")

    date = (value >> 39) & 0x1FFFFF
    time = (value >> 22) & 0x1FFFF
    microsecond = (value >> 2) & 0xFFFFF
    return datetime(
        year=date >> 9,
        month=((date >> 5) & 0xF) + 1,
        day=(date & 0x1F) + 1,
        hour=time >> 12,
        minute=(time >> 6) & 0x3F,
        second=time & 0x3F,
        microsecond=microsecond,
    )


def read_times(path: Path) -> list[datetime]:
    """All frame times in a .vidt file, in file order."""
    data = Path(path).read_bytes()
    if len(data) % RECORD_BYTES:
        raise ValueError(f"{path}: size is not a multiple of {RECORD_BYTES} bytes")
    return [
        decode_timestamp(data[i : i + RECORD_BYTES])
        for i in range(0, len(data), RECORD_BYTES)
    ]
