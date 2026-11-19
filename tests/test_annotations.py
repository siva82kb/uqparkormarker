"""Labels and clip order, written to a temporary folder (no participant data)."""

import csv
import tempfile
import unittest
from pathlib import Path

from parkour import annotations, config
from parkour.sampling import Segment


def segments(n):
    return [Segment(f"seg_{i:04d}", "v.avi", i * 30, i * 30 + 29, "", "", "") for i in range(1, n + 1)]


class CleanName(unittest.TestCase):
    def test_makes_a_file_safe_name(self):
        self.assertEqual(annotations.clean_name("  Ann Lee "), "ann_lee")
        self.assertEqual(annotations.clean_name("Dr. Ann-Marie O'Neil"), "dr_ann-marie_o_neil")
        self.assertEqual(annotations.clean_name("../../etc"), "etc")

    def test_nothing_usable_gives_empty(self):
        self.assertEqual(annotations.clean_name(" ?! "), "")


class Order(unittest.TestCase):
    def test_same_rater_same_order_and_all_clips_present(self):
        clips = segments(40)
        first = annotations.order(clips, "ann")
        self.assertEqual(first, annotations.order(clips, "ann"))
        self.assertEqual(sorted(s.segment_id for s in first), [s.segment_id for s in clips])
        self.assertNotEqual(first, clips)                       # shuffled

    def test_raters_differ(self):
        clips = segments(40)
        self.assertNotEqual(annotations.order(clips, "ann"), annotations.order(clips, "bob"))


class Labels(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.saved_root, config.CLIPS_ROOT = config.CLIPS_ROOT, Path(self.folder.name)
        self.addCleanup(setattr, config, "CLIPS_ROOT", self.saved_root)
        (config.CLIPS_ROOT / "Pxx").mkdir()

    def test_nothing_labelled_yet(self):
        self.assertEqual(annotations.read("Pxx", "ann"), {})
        self.assertEqual(annotations.next_position(segments(3), {}), 0)

    def test_append_and_read_back(self):
        annotations.append("Pxx", "ann", "seg_0002", "Non-functional")
        self.assertEqual(annotations.read("Pxx", "ann"), {"seg_0002": "Non-functional"})
        with annotations.path("Pxx", "ann").open(newline="", encoding="utf-8") as fh:
            (row,) = csv.DictReader(fh)
        self.assertEqual(row["rater"], "ann")
        self.assertRegex(row["annotated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

    def test_latest_label_wins_and_every_row_is_kept(self):
        annotations.append("Pxx", "ann", "seg_0001", "Non-functional")
        annotations.append("Pxx", "ann", "seg_0001", "No activity/movement")
        self.assertEqual(annotations.read("Pxx", "ann")["seg_0001"], "No activity/movement")
        self.assertEqual(len(annotations.path("Pxx", "ann").read_text().splitlines()), 3)

    def test_raters_have_separate_files(self):
        annotations.append("Pxx", "ann", "seg_0001", "Non-functional")
        self.assertEqual(annotations.read("Pxx", "bob"), {})

    def test_next_position_skips_labelled_clips(self):
        clips = segments(3)
        labels = {"seg_0001": "x", "seg_0002": "x"}
        self.assertEqual(annotations.next_position(clips, labels), 2)
        self.assertIsNone(annotations.next_position(clips, {**labels, "seg_0003": "x"}))

    def test_counts_follow_the_label_order(self):
        labels = {"seg_0001": "B", "seg_0002": "B", "seg_0003": "A", "seg_0099": "A"}
        tally = annotations.counts(segments(3), labels, ["A", "B", "C"])
        self.assertEqual(list(tally.items()), [("A", 1), ("B", 2), ("C", 0)])


class SetLocal(unittest.TestCase):
    def test_adds_then_replaces_one_line_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as folder:
            saved, config.LOCAL_FILE = config.LOCAL_FILE, Path(folder) / "local.toml"
            self.addCleanup(setattr, config, "LOCAL_FILE", saved)
            config.LOCAL_FILE.write_text('# a note\nsubject = "Pxx"\nclip_limit = 25\n', encoding="utf-8")
            config.set_local("rater", "ann")
            config.set_local("rater", "bob")
            text = config.LOCAL_FILE.read_text(encoding="utf-8")
            self.assertIn("# a note", text)
            self.assertEqual(config.load_local(), {"subject": "Pxx", "clip_limit": 25, "rater": "bob"})


if __name__ == "__main__":
    unittest.main()
