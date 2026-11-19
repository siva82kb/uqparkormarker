"""Resetting a subject's folder, in a temporary folder (no participant data)."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from parkour import config, reset

NOW = datetime(2026, 11, 19, 12, 0, 0)


class Reset(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        local = self.root / "local.toml"
        local.write_text('subject = "P99"\nrater = "ann"\nclip_limit = 5\n', encoding="utf-8")
        for name, value in (("CLIPS_ROOT", self.root / "out"), ("LOCAL_FILE", local)):
            patched = mock.patch.object(config, name, value)
            patched.start()
            self.addCleanup(patched.stop)

        self.folder = self.root / "out" / "P99"
        (self.folder / "clips").mkdir(parents=True)
        for name in ("clips/seg_0001.mp4", "clips/seg_0002.mp4", "segments.csv",
                     "design.toml", "recording.json.gz", "P99_ann_annotations.csv"):
            (self.folder / name).write_text("x", encoding="utf-8")

    def names(self):
        return sorted(p.name for p in self.folder.iterdir())

    def test_plan_changes_nothing(self):
        found = reset.plan("P99", now=NOW)
        self.assertEqual(found.n_clips, 2)
        self.assertEqual(len(self.names()), 5)
        self.assertTrue(any("2 clips" in line for line in found.lines()))

    def test_clips_go_labels_are_kept_aside_and_the_read_stays(self):
        reset.apply(reset.plan("P99", now=NOW))
        self.assertEqual(self.names(), ["recording.json.gz"])
        kept = self.root / "out" / "_archive" / "P99_20261119-120000" / "P99_ann_annotations.csv"
        self.assertTrue(kept.exists())
        self.assertEqual(config.load_local()["rater"], "ann")

    def test_recording_and_rater_go_only_when_asked(self):
        reset.apply(reset.plan("P99", recording=True, rater=True, now=NOW))
        self.assertEqual(self.names(), [])
        self.assertEqual(config.load_local(), {"subject": "P99", "clip_limit": 5})

    def test_nothing_to_do_for_an_unknown_subject(self):
        self.assertTrue(reset.plan("P00", now=NOW).empty)


if __name__ == "__main__":
    unittest.main()
