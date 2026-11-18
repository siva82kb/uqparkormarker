"""vidt decoding, checked against a hand-built record (no participant data)."""

import unittest
from datetime import datetime

from parkour import vidt


def encode(t: datetime) -> bytes:
    """Pack a datetime the way the recorder does: temporenc DTS, microseconds."""
    date = (t.year << 9) | ((t.month - 1) << 5) | (t.day - 1)
    time = (t.hour << 12) | (t.minute << 6) | t.second
    value = (0b0101 << 60) | (date << 39) | (time << 22) | (t.microsecond << 2)
    return value.to_bytes(8, "big")


class DecodeTimestamp(unittest.TestCase):
    def test_round_trip(self):
        for t in (
            datetime(2022, 11, 25, 14, 38, 49, 173274),
            datetime(2000, 1, 1, 0, 0, 0, 0),
            datetime(2031, 12, 31, 23, 59, 59, 999999),
        ):
            self.assertEqual(vidt.decode_timestamp(encode(t)), t)

    def test_rejects_other_temporenc_types(self):
        with self.assertRaises(ValueError):
            vidt.decode_timestamp(bytes(8))

    def test_rejects_wrong_length(self):
        with self.assertRaises(ValueError):
            vidt.decode_timestamp(bytes(7))


if __name__ == "__main__":
    unittest.main()
