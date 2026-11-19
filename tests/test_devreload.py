"""Developer mode: the stamp changes when a watched file changes."""

import os
import tempfile
import unittest
from pathlib import Path

from parkour import devreload


class Stamp(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "templates" / "docs").mkdir(parents=True)
        (self.root / "static").mkdir()
        self.page = self.root / "templates" / "docs" / "page.html"
        self.page.write_text("a", encoding="utf-8")
        (self.root / "static" / "notes.txt").write_text("not watched", encoding="utf-8")

    def test_same_files_same_stamp(self):
        self.assertEqual(devreload.stamp(self.root), devreload.stamp(self.root))

    def test_saving_a_watched_file_changes_the_stamp(self):
        before = devreload.stamp(self.root)
        later = self.page.stat().st_mtime_ns + 1_000_000_000
        os.utime(self.page, ns=(later, later))
        self.assertNotEqual(devreload.stamp(self.root), before)

    def test_adding_a_watched_file_changes_the_stamp(self):
        before = devreload.stamp(self.root)
        (self.root / "static" / "style.css").write_text("b", encoding="utf-8")
        self.assertNotEqual(devreload.stamp(self.root), before)

    def test_other_files_do_not_count(self):
        before = devreload.stamp(self.root)
        (self.root / "static" / "more.txt").write_text("c", encoding="utf-8")
        self.assertEqual(devreload.stamp(self.root), before)


if __name__ == "__main__":
    unittest.main()
