"""Labels and clip order, written to a temporary folder (no participant data)."""

import csv
import tempfile
import unittest
from pathlib import Path

from parkour import annotations, config
from parkour.sampling import Segment


def segments(n):
    return [Segment(f"seg_{i:04d}", "v.avi", i * 30, i * 30 + 29, "", "", "") for i in range(1, n + 1)]


def both(right, left):
    return {"right": right, "left": left}


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

    def rows(self, rater="ann"):
        with annotations.path("Pxx", rater).open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_nothing_labelled_yet(self):
        self.assertEqual(annotations.read("Pxx", "ann"), {})
        self.assertEqual(annotations.next_position(segments(3), {}), 0)

    def test_one_row_holds_both_arms(self):
        annotations.save("Pxx", "ann", "seg_0002", both("Non-functional", "No activity/movement"))
        self.assertEqual(annotations.read("Pxx", "ann"),
                         {"seg_0002": both("Non-functional", "No activity/movement")})
        (row,) = self.rows()
        self.assertEqual(list(row), ["segment_id", "right_label", "left_label", "rater", "annotated_at"])
        self.assertEqual((row["right_label"], row["left_label"], row["rater"]),
                         ("Non-functional", "No activity/movement", "ann"))
        self.assertRegex(row["annotated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

    def test_changing_a_clip_rewrites_its_row(self):
        annotations.save("Pxx", "ann", "seg_0001", both("Non-functional", "Non-functional"))
        annotations.save("Pxx", "ann", "seg_0002", both("Non-functional", "Non-functional"))
        annotations.save("Pxx", "ann", "seg_0001", both("Non-functional", "No activity/movement"))
        self.assertEqual(annotations.read("Pxx", "ann")["seg_0001"]["left"], "No activity/movement")
        self.assertEqual([row["segment_id"] for row in self.rows()], ["seg_0001", "seg_0002"])   # one row each

    def test_dated_file_is_what_is_shown_when_nothing_is_in_progress(self):
        from datetime import datetime
        annotations.save("Pxx", "ann", "seg_0001", both("Non-functional", "Non-functional"))
        working = annotations.path("Pxx", "ann")
        self.assertEqual(annotations.current_path("Pxx", "ann"), working)
        self.assertTrue(annotations.in_progress("Pxx", "ann"))
        older = annotations.dated_path("Pxx", "ann", datetime(2026, 1, 1, 9, 0, 0))
        newer = annotations.dated_path("Pxx", "ann", datetime(2026, 1, 2, 9, 0, 0))
        annotations.store(older, [{**row, "left_label": "old"} for row in annotations.rows(working)])
        working.rename(newer)
        self.assertEqual(newer.name, "Pxx_ann_annotations_20260102-090000.csv")
        self.assertEqual(annotations.saved_files("Pxx"), [older, newer])
        self.assertFalse(annotations.in_progress("Pxx", "ann"))
        self.assertEqual(annotations.current_path("Pxx", "ann"), newer)             # the newest dated file
        self.assertEqual(annotations.read("Pxx", "ann")["seg_0001"]["left"], "Non-functional")

    def test_change_after_a_save_starts_a_new_file_as_a_full_copy(self):
        from datetime import datetime
        for clip in ("seg_0001", "seg_0002", "seg_0003"):
            annotations.save("Pxx", "ann", clip, both("Non-functional", "Non-functional"))
        dated = annotations.dated_path("Pxx", "ann", datetime(2026, 1, 2, 9, 0, 0))
        annotations.path("Pxx", "ann").rename(dated)
        before = dated.read_bytes()

        annotations.save("Pxx", "ann", "seg_0002", both("Task-related functional", "Non-functional"))
        self.assertEqual(dated.read_bytes(), before)                    # the saved file is not touched
        rows = self.rows()                                              # the new undated file
        self.assertEqual([row["segment_id"] for row in rows], ["seg_0001", "seg_0002", "seg_0003"])
        self.assertEqual([row["right_label"] for row in rows],
                         ["Non-functional", "Task-related functional", "Non-functional"])
        self.assertTrue(annotations.in_progress("Pxx", "ann"))
        self.assertEqual(annotations.read("Pxx", "ann")["seg_0002"]["right"], "Task-related functional")

    def test_other_files_are_not_taken_for_saved_ones(self):
        folder = annotations.path("Pxx", "ann").parent
        (folder / "Pxx_ann_annotations_older_layout_20261119-150958.csv").write_text("x", encoding="utf-8")
        (folder / "Qxx_ann_annotations_20261119-150958.csv").write_text("x", encoding="utf-8")
        self.assertEqual(annotations.saved_files("Pxx"), [])
        self.assertEqual(annotations.parse_dated("Pxx", "Pxx_ann_lee_417_annotations_20261119-150958.csv")[0],
                         "ann_lee_417")
    def test_raters_have_separate_files(self):
        annotations.save("Pxx", "ann", "seg_0001", both("Non-functional", "Non-functional"))
        self.assertEqual(annotations.read("Pxx", "bob"), {})

    def test_a_row_needs_a_label_for_each_arm(self):
        for incomplete in ({"right": "Non-functional"}, both("Non-functional", ""),
                           {"right": "x", "left": "y", "both": "z"}):
            with self.assertRaises(ValueError):
                annotations.save("Pxx", "ann", "seg_0001", incomplete)
        self.assertFalse(annotations.path("Pxx", "ann").exists())

    def test_a_clip_is_labelled_once_it_has_a_row(self):
        clips = segments(2)
        labels = {"seg_0001": both("x", "y")}
        self.assertTrue(annotations.complete(labels, "seg_0001"))
        self.assertFalse(annotations.complete(labels, "seg_0002"))
        self.assertEqual((annotations.n_complete(clips, labels), annotations.next_position(clips, labels)), (1, 1))

    def test_files_with_an_older_layout_are_set_aside_not_mixed_or_deleted(self):
        layouts = ("segment_id,label,rater,annotated_at\nseg_0001,Non-functional,ann,x\n",
                   "segment_id,arm,label,rater,annotated_at\nseg_0001,right,Non-functional,ann,x\n")
        for number, content in enumerate(layouts):
            rater = f"ann{number}"
            old = annotations.path("Pxx", rater)
            old.write_text(content, encoding="utf-8")
            self.assertEqual(annotations.read("Pxx", rater), {})        # its rows cannot be used
            annotations.save("Pxx", rater, "seg_0001", both("Non-functional", "Non-functional"))
            self.assertEqual(len(self.rows(rater)), 1)
            (kept,) = old.parent.glob(f"Pxx_{rater}_annotations_older_layout_*.csv")
            self.assertEqual(kept.read_text(encoding="utf-8"), content)

    def test_next_position_skips_labelled_clips(self):
        clips = segments(3)
        labels = {"seg_0001": both("x", "x"), "seg_0002": both("x", "x")}
        self.assertEqual(annotations.next_position(clips, labels), 2)
        self.assertIsNone(annotations.next_position(clips, {**labels, "seg_0003": both("x", "x")}))

    def test_counts_are_per_arm_and_follow_the_label_order(self):
        labels = {"seg_0001": both("B", "A"), "seg_0002": both("B", "B"),
                  "seg_0099": both("A", "A")}                   # 0099 is not one of the clips
        tally = annotations.counts(segments(3), labels, ["A", "B", "C"])
        self.assertEqual(list(tally), ["A", "B", "C"])
        self.assertEqual(tally["A"], {"right": 0, "left": 1})
        self.assertEqual(tally["B"], {"right": 2, "left": 1})
        self.assertEqual(tally["C"], {"right": 0, "left": 0})


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
