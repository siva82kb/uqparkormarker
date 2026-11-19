"""Sharing clips and ratings through a folder that stands in for the RDM.

Two temporary clip folders play two computers; a third temporary folder plays
the study folder on the RDM. No participant data is used.
"""

import csv
import random
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from parkour import (annotations, clipset, config, recording_store, share,
                     shared_ratings)
from parkour.sampling import Segment

STUDY = config.load_study()
SUBJECT = "Pxx"


def rows(first_frame=0, n=4):
    return [Segment(f"seg_{i:04d}", "v.avi", first_frame + 100 * i, first_frame + 100 * i + 29,
                    "2026-01-01T10:00:00+10:00", "2026-01-01T10:00:01+10:00", "")
            for i in range(1, n + 1)]


class TwoComputers(unittest.TestCase):
    """Base: a study folder, and two computers that can be switched between."""

    def setUp(self):
        base = tempfile.TemporaryDirectory()
        self.addCleanup(base.cleanup)
        self.base = Path(base.name)
        self.source = self.base / "study folder"
        self.source.mkdir()
        self.share = self.source / STUDY["share"]["folder"]
        self.on("first")

    def on(self, computer):
        """Carry on as the named computer: its own clips and its own local.toml."""
        for patch in getattr(self, "_patches", []):
            patch.stop()
        home = self.base / computer
        home.mkdir(exist_ok=True)
        local = home / "local.toml"
        if not local.exists():
            local.write_text(f'source_dir = "{self.source.as_posix()}"\nsubject = "{SUBJECT}"\n',
                             encoding="utf-8")
        self._patches = [mock.patch.object(config, "CLIPS_ROOT", home / "clips"),
                         mock.patch.object(config, "LOCAL_FILE", local)]
        for patch in self._patches:
            patch.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def generate(self, first_frame=0, with_reading=True):
        """Stand in for generating clips on the current computer."""
        clipset.write_plan(SUBJECT, rows(first_frame))
        for row in rows(first_frame):
            clipset.clip_path(SUBJECT, row.segment_id).write_bytes(f"clip {row.start_frame}".encode())
        if with_reading:
            from parkour.dataset import Recording
            recording_store.save(Path("Z:/elsewhere") / SUBJECT, Recording(videos=[], missing=[]))

    def label_all(self, rater="ann", label="Non-functional"):
        for row in clipset.read_segments(SUBJECT):
            annotations.save(SUBJECT, rater, row.segment_id, {"right": label, "left": label})


class Design(unittest.TestCase):
    def test_share_folder_name_is_not_part_of_the_design(self):
        other = {**STUDY, "share": {"folder": "Another name"}}
        self.assertEqual(clipset.differences(STUDY, other), [])

    def test_a_real_design_change_is_still_seen(self):
        other = {**STUDY, "sampling": {**STUDY["sampling"], "seed": 1}}
        self.assertEqual(len(clipset.differences(STUDY, other)), 1)

    def test_set_id_ignores_line_endings(self):
        self.assertEqual(clipset.content_id(b"a\r\nb\r\n", b"x\r\n"), clipset.content_id(b"a\nb\n", b"x\n"))
        self.assertNotEqual(clipset.content_id(b"a\n", b"x\n"), clipset.content_id(b"b\n", b"x\n"))


class Clips(TwoComputers):
    def test_nothing_shared_yet(self):
        self.assertIsNone(share.shared_id(self.share, SUBJECT))
        self.assertEqual(share.shared_subjects(self.share), [])
        self.generate()
        self.assertEqual(share.standing(self.share, SUBJECT), "upload")
        self.assertEqual(share.standing(self.share, SUBJECT, limited=True), "limited")

    def test_upload_makes_one_zip_without_any_label_file(self):
        self.generate()
        self.label_all()
        seen = []
        share.pack(self.share, SUBJECT, lambda done, total, message: seen.append((done, total)))
        target = share.zip_path(self.share, SUBJECT)
        with zipfile.ZipFile(target) as archive:
            names = sorted(archive.namelist())
        self.assertEqual(names, ["clips/seg_0001.mp4", "clips/seg_0002.mp4", "clips/seg_0003.mp4",
                                 "clips/seg_0004.mp4", "design.toml", "recording.json.gz", "segments.csv"])
        self.assertEqual(seen[-1], (4, 4))
        self.assertEqual(list(target.parent.glob("*.part")), [])
        self.assertEqual(share.shared_id(self.share, SUBJECT), clipset.set_id(SUBJECT))
        self.assertEqual(share.standing(self.share, SUBJECT), "shared")
        self.assertEqual(share.shared_subjects(self.share), [SUBJECT])

    def test_existing_zip_is_never_replaced(self):
        self.generate()
        share.pack(self.share, SUBJECT)
        before = share.zip_path(self.share, SUBJECT).read_bytes()
        self.on("second")
        self.generate(first_frame=5000)                 # a different set
        self.assertEqual(share.standing(self.share, SUBJECT), "other")
        with self.assertRaises(FileExistsError):
            share.pack(self.share, SUBJECT)
        self.assertEqual(share.zip_path(self.share, SUBJECT).read_bytes(), before)

    def test_download_gives_the_second_computer_the_very_same_set(self):
        self.generate()
        mine = clipset.set_id(SUBJECT)
        share.pack(self.share, SUBJECT)

        self.on("second")
        self.assertEqual(clipset.state(SUBJECT), "none")
        subject_dir = self.source / SUBJECT
        share.unpack(self.share, SUBJECT, subject_dir, STUDY)
        self.assertEqual(clipset.state(SUBJECT), "complete")
        self.assertEqual(clipset.set_id(SUBJECT), mine)
        self.assertEqual(clipset.clip_path(SUBJECT, "seg_0002").read_bytes(), b"clip 200")
        self.assertEqual(share.standing(self.share, SUBJECT), "shared")
        leftovers = [p.name for p in clipset.folder(SUBJECT).iterdir()
                     if p.name.endswith(".part") or p.name == "incoming"]
        self.assertEqual(leftovers, [])
        # The saved reading came from another drive; here it is usable all the same.
        self.assertIsNotNone(recording_store.load(subject_dir))

    def test_download_refuses_clips_made_with_other_settings(self):
        self.generate()
        share.pack(self.share, SUBJECT)
        self.on("second")
        other = {**STUDY, "sampling": {**STUDY["sampling"], "seed": 1}}
        with self.assertRaises(share.Mismatch) as caught:
            share.unpack(self.share, SUBJECT, self.source / SUBJECT, other)
        self.assertIn("sampling.seed", caught.exception.differences[0])
        self.assertEqual(clipset.state(SUBJECT), "none")           # nothing was put in place

    def test_incomplete_zip_is_not_installed(self):
        self.generate()
        share.pack(self.share, SUBJECT)
        target = share.zip_path(self.share, SUBJECT)
        with zipfile.ZipFile(target) as archive:
            kept = {n: archive.read(n) for n in archive.namelist() if n != "clips/seg_0003.mp4"}
        with zipfile.ZipFile(target, "w") as archive:
            for name, content in kept.items():
                archive.writestr(name, content)
        self.on("second")
        with self.assertRaises(OSError):
            share.unpack(self.share, SUBJECT, self.source / SUBJECT, STUDY)
        self.assertEqual(clipset.state(SUBJECT), "none")

    def test_study_folder_out_of_reach(self):
        gone = self.base / "not connected" / STUDY["share"]["folder"]
        self.assertFalse(share.reachable(gone.parent))
        with self.assertRaises(share.Unreachable):
            share.shared_id(gone, SUBJECT)
        self.generate()
        self.assertEqual(share.standing(gone, SUBJECT), "unreachable")
        with self.assertRaises(share.Unreachable):
            share.pack(gone, SUBJECT)

    def test_new_user_is_offered_shared_participants_first(self):
        (self.source / "P07").mkdir()
        (self.source / "Notes").mkdir()
        self.assertEqual(share.candidates(self.source, self.share), ("source", ["P07"]))
        self.generate()
        share.pack(self.share, SUBJECT)
        self.assertEqual(share.candidates(self.source, self.share), ("shared", [SUBJECT]))


class Ratings(TwoComputers):
    def shared_set(self):
        """Clips generated on the first computer, shared, and on the second too."""
        self.generate()
        share.pack(self.share, SUBJECT)
        self.on("second")
        share.unpack(self.share, SUBJECT, self.source / SUBJECT, STUDY)
        self.on("first")

    def at(self, hour):
        return datetime(2026, 11, 20, hour, 15, 30)

    def test_name_with_a_number_when_taken(self):
        self.assertEqual(shared_ratings.free_name("ann", {"bob"}), "ann")
        picked = shared_ratings.free_name("ann", {"ann"}, random.Random(1))
        self.assertRegex(picked, r"^ann_\d{3}$")

    def test_held_back_until_the_clips_are_shared(self):
        self.generate()
        self.label_all()
        self.assertEqual(shared_ratings.upload(self.share, SUBJECT, "ann").status, "no_clips")
        self.assertFalse((self.share / share.RATINGS).exists())

    def test_held_back_when_these_are_not_the_shared_clips(self):
        self.shared_set()
        self.on("third")
        self.generate(first_frame=5000)
        self.label_all()
        self.assertEqual(shared_ratings.upload(self.share, SUBJECT, "ann").status, "other_clips")

    def test_upload_names_the_file_with_date_and_time(self):
        self.shared_set()
        self.label_all()
        outcome = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))
        self.assertEqual((outcome.status, outcome.name, outcome.renamed, outcome.previous),
                         ("uploaded", "ann", False, None))
        (file,) = (self.share / share.RATINGS).iterdir()
        self.assertEqual(file.name, "Pxx_ann_annotations_20261120-091530.csv")
        self.assertEqual(config.load_local()["uploaded_as"], "ann")
        self.assertEqual(shared_ratings.taken_names(self.share, SUBJECT), {"ann"})

    def local_names(self):
        return sorted(p.name for p in clipset.folder(SUBJECT).glob("*_annotations*.csv"))

    def rdm_names(self):
        folder = self.share / share.RATINGS
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def test_saving_gives_the_file_its_date_and_the_same_name_on_the_rdm(self):
        self.shared_set()
        self.label_all()
        self.assertEqual(self.local_names(), ["Pxx_ann_annotations.csv"])       # in progress: no date
        before = shared_ratings.standing(SUBJECT, "ann")
        self.assertEqual((before.in_progress, before.saved, before.uploaded), (True, "", False))

        outcome = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))
        name = "Pxx_ann_annotations_20261120-091530.csv"
        self.assertEqual((outcome.status, outcome.file), ("uploaded", name))
        self.assertEqual(self.local_names(), [name])                             # the undated file is gone
        self.assertEqual(self.rdm_names(), [name])
        self.assertEqual((clipset.folder(SUBJECT) / name).read_bytes(),
                         (self.share / share.RATINGS / name).read_bytes())       # identical contents
        after = shared_ratings.standing(SUBJECT, "ann")
        self.assertEqual((after.in_progress, after.saved, after.saved_at, after.uploaded),
                         (False, name, self.at(9), True))
        self.assertEqual(after.current.name, name)

    def test_edit_after_saving_makes_a_second_file_with_one_row_per_clip(self):
        self.shared_set()
        self.label_all()
        shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))
        first = "Pxx_ann_annotations_20261120-091530.csv"
        kept = (clipset.folder(SUBJECT) / first).read_bytes()

        annotations.save(SUBJECT, "ann", "seg_0002", {"right": "Task-related functional", "left": "Non-functional"})
        self.assertEqual(self.local_names(), [first, "Pxx_ann_annotations.csv"][::-1])   # undated again
        self.assertTrue(shared_ratings.standing(SUBJECT, "ann").in_progress)
        self.assertEqual(self.rdm_names(), [first])                              # nothing uploaded yet

        outcome = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(11))
        second = "Pxx_ann_annotations_20261120-111530.csv"
        self.assertEqual((outcome.status, outcome.file, outcome.previous), ("uploaded", second, self.at(9)))
        self.assertEqual(self.local_names(), [first, second])
        self.assertEqual(self.rdm_names(), [first, second])
        self.assertEqual((clipset.folder(SUBJECT) / first).read_bytes(), kept)   # the first save is as it was
        rows = annotations.rows(clipset.folder(SUBJECT) / second)
        self.assertEqual(len(rows), 4)                                           # one row per clip
        self.assertEqual({r["segment_id"]: r["right_label"] for r in rows}["seg_0002"], "Task-related functional")
        self.assertEqual(annotations.read(SUBJECT, "ann")["seg_0002"]["right"], "Task-related functional")

    def test_save_goes_through_without_the_rdm_and_keeps_its_name(self):
        self.shared_set()
        self.label_all()
        gone = self.base / "not connected" / STUDY["share"]["folder"]
        outcome = shared_ratings.upload(gone, SUBJECT, "ann", self.at(9))
        name = "Pxx_ann_annotations_20261120-091530.csv"
        self.assertEqual((outcome.status, outcome.file), ("unreachable", name))
        self.assertEqual(self.local_names(), [name])                             # saved here all the same
        self.assertFalse(shared_ratings.standing(SUBJECT, "ann").uploaded)
        later = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(13))   # the VPN is back
        self.assertEqual((later.status, later.file), ("uploaded", name))         # the date is the save, not the upload
        self.assertEqual(self.rdm_names(), [name])

    def test_name_clash_renames_the_saved_file_too(self):
        self.shared_set()
        self.label_all()
        shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))
        self.on("second")                                                        # another person, same name
        self.label_all(label="No activity/movement")
        outcome = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(10))
        self.assertRegex(outcome.name, r"^ann_\d{3}$")
        name = f"Pxx_{outcome.name}_annotations_20261120-101530.csv"
        self.assertEqual((outcome.file, self.local_names()), (name, [name]))     # same name in both places
        self.assertIn(name, self.rdm_names())
    def test_nothing_new_is_not_uploaded_again(self):
        self.shared_set()
        self.label_all()
        shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))
        again = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(10))
        self.assertEqual((again.status, again.at), ("unchanged", self.at(9)))
        self.assertEqual(len(list((self.share / share.RATINGS).iterdir())), 1)

    def test_changed_label_uploads_a_new_file_and_keeps_the_old(self):
        self.shared_set()
        self.label_all()
        shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))
        annotations.save(SUBJECT, "ann", "seg_0001", {"right": "Non-functional", "left": "No activity/movement"})
        outcome = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(11))
        self.assertEqual((outcome.status, outcome.previous), ("uploaded", self.at(9)))
        files = shared_ratings.shared(self.share, SUBJECT)
        self.assertEqual([f.at for f in files], [self.at(9), self.at(11)])       # oldest first

    def test_clash_with_another_rater_gets_a_number(self):
        self.shared_set()
        self.label_all()
        shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9))

        self.on("second")                               # another person, same name
        self.label_all(label="No activity/movement")
        outcome = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(10))
        self.assertEqual((outcome.status, outcome.renamed, outcome.previous), ("uploaded", True, None))
        self.assertRegex(outcome.name, r"^ann_\d{3}$")
        self.assertEqual(config.load_local()["uploaded_as"], outcome.name)
        # Inside the uploaded file, every row carries the new name.
        uploaded = next(f for f in shared_ratings.shared(self.share, SUBJECT) if f.name == outcome.name)
        with uploaded.path.open(newline="", encoding="utf-8") as fh:
            self.assertEqual({row["rater"] for row in csv.DictReader(fh)}, {outcome.name})
        # The file on this computer is left as it was.
        self.assertEqual(annotations.read(SUBJECT, "ann")["seg_0001"]["left"], "No activity/movement")

        # Later uploads from this computer keep that name, and count as the same rater.
        annotations.save(SUBJECT, "ann", "seg_0002", {"right": "Non-functional", "left": "Non-functional"})
        later = shared_ratings.upload(self.share, SUBJECT, "ann", self.at(12))
        self.assertEqual((later.name, later.renamed, later.previous), (outcome.name, True, self.at(10)))

    def test_rdm_out_of_reach_keeps_the_labels_for_next_time(self):
        self.shared_set()
        self.label_all()
        gone = self.base / "not connected" / STUDY["share"]["folder"]
        self.assertEqual(shared_ratings.upload(gone, SUBJECT, "ann").status, "unreachable")
        self.assertNotIn("uploaded_as", config.load_local())
        self.assertEqual(shared_ratings.upload(self.share, SUBJECT, "ann", self.at(9)).status, "uploaded")


if __name__ == "__main__":
    unittest.main()
