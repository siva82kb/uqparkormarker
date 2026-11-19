"""The whole journey through the pages, with a folder standing in for the RDM.

One computer generates clips and uploads them. A second computer is set up
from nothing, fetches the clips, signs in, labels them and has its ratings
uploaded. No participant data is used; clips are small stand-in files.
"""

import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from parkour import annotations, clipset, config, share, shared_ratings, transfer
from parkour.sampling import Segment

STUDY = config.load_study()
SUBJECT = "P99"


class Journey(unittest.TestCase):
    def setUp(self):
        base = tempfile.TemporaryDirectory()
        self.addCleanup(base.cleanup)
        self.base = Path(base.name)
        self.source = self.base / "study folder"
        (self.source / SUBJECT / "Video").mkdir(parents=True)
        (self.source / SUBJECT / "Video" / "task_000_1.avi").write_bytes(b"")
        (self.source / "Consent Forms").mkdir()
        self.share = self.source / STUDY["share"]["folder"]
        self._patches = []
        self.addCleanup(lambda: [p.stop() for p in self._patches])
        from app import app
        self.client = app.test_client()

    def on(self, computer):
        """Carry on as the named computer. A new one has no local.toml at all."""
        for patch in self._patches:
            patch.stop()
        home = self.base / computer
        home.mkdir(exist_ok=True)
        self._patches = [mock.patch.object(config, "CLIPS_ROOT", home / "clips"),
                         mock.patch.object(config, "LOCAL_FILE", home / "local.toml")]
        for patch in self._patches:
            patch.start()
        transfer._set(state="idle", kind="", subject="")       # a different computer: no job running

    def get(self, address):
        response = self.client.get(address)
        text = response.get_data(as_text=True)
        response.close()
        return response, text

    def finished(self):
        """Open the finished page, which appears at once, then wait for the
        outcome of the upload that it starts in the background. Returns the
        text of both."""
        _, page = self.get("/done")
        self.assertIn("Uploading your labels to the RDM", page)     # shown without waiting
        for _ in range(200):
            response = self.client.get("/done/outcome")
            if response.status_code == 200:
                return page + response.get_data(as_text=True)
            time.sleep(0.05)
        self.fail("the upload of the labels did not finish")

    def goes_to(self, response):
        return response.headers.get("Location", "")

    def wait_for_transfer(self, kind):
        for _ in range(200):
            progress = transfer.snapshot(kind, SUBJECT)
            if progress["state"] != "running":
                return progress
            time.sleep(0.05)
        self.fail("the transfer did not finish")

    def stand_in_clips(self, n=4):
        rows = [Segment(f"seg_{i:04d}", "task_000_1.avi", 100 * i, 100 * i + 29,
                        f"2026-01-01T10:00:{i:02d}+10:00", f"2026-01-01T10:00:{i:02d}+10:00",
                        "Jump" if i % 2 else "") for i in range(1, n + 1)]
        clipset.write_plan(SUBJECT, rows)
        for row in rows:
            clipset.clip_path(SUBJECT, row.segment_id).write_bytes(b"clip " + row.segment_id.encode())

    def label_everything(self):
        for _ in range(50):
            response, page = self.get("/annotate")
            if response.status_code == 302:
                return
            clip = re.search(r'data-segment="(seg_\d+)"', page).group(1)
            self.client.post("/annotate/confirm", data={"segment_id": clip, "right": "3", "left": "4"})
        self.fail("labelling did not finish")

    def test_generate_upload_then_fetch_label_and_share_ratings(self):
        # ---- First computer: set up, generate, upload ----
        self.on("generator")
        response, _ = self.get("/")
        self.assertTrue(self.goes_to(response).endswith("/setup"))
        _, page = self.get("/setup")
        self.assertIn("Where is the study folder?", page)

        response = self.client.post("/setup", data={"folder": str(self.base / "nowhere")})
        self.assertIn("cannot be opened", response.get_data(as_text=True))
        self.assertIsNone(config.load_local())

        response = self.client.post("/setup", data={"folder": str(self.source)})
        page = response.get_data(as_text=True)
        self.assertIn("No clips have been shared yet", page)        # so: who will you generate for?
        self.assertIn(f'value="{SUBJECT}"', page)
        self.assertNotIn("Consent", page)                           # not a participant folder
        response = self.client.post("/setup", data={"folder": str(self.source), "subject": SUBJECT})
        self.assertEqual(config.load_local(), {"source_dir": str(self.source), "subject": SUBJECT})

        response, _ = self.get("/")                 # no clips here, none shared: the usual flow
        self.assertTrue(self.goes_to(response).endswith("/summary"))

        self.stand_in_clips()                       # generation itself is tested elsewhere
        _, page = self.get("/generate")
        self.assertIn("Upload to RDM", page)
        self.assertIn("only on this computer", page)

        self.client.post("/upload")
        self.assertEqual(self.wait_for_transfer("upload")["state"], "done")
        self.assertTrue(share.zip_path(self.share, SUBJECT).is_file())
        _, page = self.get("/upload")
        self.assertIn("Clips shared", page)
        _, page = self.get("/generate")
        self.assertNotIn("Upload to RDM", page)                     # the button is gone
        self.assertIn("the ones shared on the RDM", page)
        self.client.post("/upload")                                 # pressing an old button changes nothing
        self.assertEqual(len(list(share.zip_path(self.share, SUBJECT).parent.glob("*.zip"))), 1)

        # ---- Second computer: a rater who has never run the app ----
        self.on("rater")
        response = self.client.post("/setup", data={"folder": str(self.source)})
        self.assertTrue(self.goes_to(response).endswith("/"))        # one shared participant: taken as is
        self.assertEqual(config.load_local()["subject"], SUBJECT)

        response, _ = self.get("/")
        self.assertTrue(self.goes_to(response).endswith("/fetch"))   # clips are on the RDM: get them
        _, page = self.get("/fetch")
        self.assertIn("Getting the clips", page)
        self.assertEqual(self.wait_for_transfer("download")["state"], "done")
        self.assertEqual(clipset.state(SUBJECT), "complete")

        response, _ = self.get("/")
        self.assertTrue(self.goes_to(response).endswith("/signin"))  # straight to the annotator
        self.assertEqual(self.client.get("/signin/check?name=Ann Lee").get_json(),
                         {"verdict": "free", "name": "ann_lee"})
        self.assertEqual(self.client.get("/signin/check?name= ?! ").get_json()["verdict"], "empty")
        self.client.post("/signin", data={"name": "Ann Lee"})
        self.assertEqual(config.load_local()["rater"], "ann_lee")

        self.label_everything()
        page = self.finished()
        self.assertIn("Your labels have been uploaded to the RDM", page)
        files = shared_ratings.shared(self.share, SUBJECT)
        self.assertEqual([f.name for f in files], ["ann_lee"])
        self.assertRegex(files[0].path.name, rf"^{SUBJECT}_ann_lee_annotations_\d{{8}}-\d{{6}}\.csv$")

        page = self.finished()                                 # nothing new: not uploaded twice
        self.assertIn("Nothing has changed since", page)
        self.assertEqual(len(shared_ratings.shared(self.share, SUBJECT)), 1)

        # ---- A third computer: someone who wants the same name ----
        self.on("another rater")
        self.client.post("/setup", data={"folder": str(self.source)})
        self.get("/fetch")
        self.wait_for_transfer("download")
        self.assertEqual(self.client.get("/signin/check?name=ann lee").get_json()["verdict"], "taken")
        response = self.client.post("/signin", data={"name": "ann lee"})
        self.assertIn("already in use", response.get_data(as_text=True))
        self.assertNotIn("rater", config.load_local())

    def test_next_saves_both_labels_as_one_row(self):
        self.on("rater")
        config.set_local("source_dir", str(self.source))
        config.set_local("subject", SUBJECT)
        config.set_local("rater", "ann")
        self.stand_in_clips(n=3)
        _, page = self.get("/annotate")
        first = re.search(r'data-segment="(seg_\d+)"', page).group(1)
        file = annotations.path(SUBJECT, "ann")

        # One arm only, or a key that is not a label: nothing is saved.
        for incomplete in ({"right": "3"}, {"right": "3", "left": ""}, {"right": "3", "left": "9"}):
            response = self.client.post("/annotate/confirm", data={"segment_id": first, **incomplete})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(file.exists())

        response = self.client.post("/annotate/confirm", data={"segment_id": first, "right": "3", "left": "1"})
        self.assertTrue(self.goes_to(response).endswith("/annotate/1"))         # on to the next clip
        self.assertEqual(annotations.read(SUBJECT, "ann")[first],
                         {"right": "Non-functional", "left": "Task-related functional"})
        self.assertEqual(len(file.read_text(encoding="utf-8").splitlines()), 2)  # header and one row

        # Looking back shows what was saved; Next without a change writes nothing.
        _, page = self.get("/annotate/0")
        self.assertEqual(len(re.findall(r'class="label label-chosen"', page)), 2)
        self.client.post("/annotate/confirm", data={"segment_id": first, "right": "3", "left": "1"})
        self.assertEqual(len(file.read_text(encoding="utf-8").splitlines()), 2)

        # A changed label rewrites the clip's row: still one row for the clip.
        self.client.post("/annotate/confirm", data={"segment_id": first, "right": "4", "left": "1"})
        self.assertEqual(len(file.read_text(encoding="utf-8").splitlines()), 2)
        self.assertEqual(annotations.read(SUBJECT, "ann")[first]["right"], "No activity/movement")

        # The last clip goes to the finished page.
        self.label_everything()
        last = annotations.order(clipset.read_segments(SUBJECT), "ann")[-1].segment_id
        response = self.client.post("/annotate/confirm", data={"segment_id": last, "right": "2", "left": "2"})
        self.assertTrue(self.goes_to(response).endswith("/done"))

    def test_file_names_through_finish_edit_and_finish_again(self):
        self.on("rater")
        config.set_local("source_dir", str(self.source))
        config.set_local("subject", SUBJECT)
        self.stand_in_clips(n=3)
        share.pack(self.share, SUBJECT)
        config.set_local("rater", "ann")
        local = lambda: sorted(p.name for p in clipset.folder(SUBJECT).glob("*_annotations*.csv"))
        on_rdm = lambda: sorted(p.name for p in (self.share / share.RATINGS).glob("*.csv"))
        dated = rf"^{SUBJECT}_ann_annotations_\d{{8}}-\d{{6}}\.csv$"

        self.label_everything()
        self.assertEqual(local(), [f"{SUBJECT}_ann_annotations.csv"])      # in progress: no date yet
        page = self.finished()
        (first,) = local()                                                  # finishing saved it under a date
        self.assertRegex(first, dated)
        self.assertEqual(on_rdm(), [first])                                 # the same name on the RDM
        self.assertIn(first, page)                                          # and the page names the file
        _, summary = self.get("/annotations")
        self.assertIn(first, summary)
        self.assertIn("same name on this", summary)

        # Looking back shows the saved labels; changing one starts an undated file.
        clip = annotations.order(clipset.read_segments(SUBJECT), "ann")[0].segment_id
        _, page = self.get("/annotate/0")
        self.assertEqual(len(re.findall(r'class="label label-chosen"', page)), 2)
        self.client.post("/annotate/confirm", data={"segment_id": clip, "right": "1", "left": "1"})
        self.assertEqual(local(), [f"{SUBJECT}_ann_annotations.csv", first])
        _, summary = self.get("/annotations")
        self.assertIn("changes that are not saved yet", summary)
        self.assertEqual(on_rdm(), [first])

        time.sleep(1.1)                                                     # a later second, so a new name
        self.finished()
        second = [name for name in local() if name != first]
        self.assertEqual(len(second), 1)
        self.assertRegex(second[0], dated)
        self.assertEqual(on_rdm(), sorted([first, second[0]]))
        rows = annotations.rows(clipset.folder(SUBJECT) / second[0])
        self.assertEqual(len(rows), 3)                                      # one row per clip, all of them
        self.assertEqual(annotations.read(SUBJECT, "ann")[clip]["right"], "Task-related functional")

    def test_study_folder_out_of_reach_is_said_plainly(self):
        self.on("rater")
        config.set_local("source_dir", str(self.base / "not connected"))
        config.set_local("subject", SUBJECT)
        _, page = self.get("/")
        self.assertIn("The study folder cannot be reached", page)
        self.assertEqual(self.client.get("/signin/check?name=ann").get_json()["verdict"], "unchecked")

    def test_labels_wait_when_the_rdm_is_out_of_reach(self):
        self.on("generator")
        config.set_local("source_dir", str(self.source))
        config.set_local("subject", SUBJECT)
        self.stand_in_clips()
        share.pack(self.share, SUBJECT)
        config.set_local("rater", "ann")
        self.label_everything()
        config.set_local("source_dir", str(self.base / "not connected"))    # the VPN drops
        page = self.finished()
        self.assertIn("could not be uploaded, because the RDM cannot be reached", page)
        config.set_local("source_dir", str(self.source))                    # and comes back
        page = self.finished()
        self.assertIn("Your labels have been uploaded to the RDM", page)


if __name__ == "__main__":
    unittest.main()
