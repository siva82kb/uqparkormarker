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
            clip = re.search(r'name="segment_id" value="(seg_\d+)"', page).group(1)
            self.client.post("/annotate", data={"segment_id": clip, "key": "3"})
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
        _, page = self.get("/done")
        self.assertIn("Your labels have been uploaded to the RDM", page)
        files = shared_ratings.shared(self.share, SUBJECT)
        self.assertEqual([f.name for f in files], ["ann_lee"])
        self.assertRegex(files[0].path.name, rf"^{SUBJECT}_ann_lee_annotations_\d{{8}}-\d{{6}}\.csv$")

        _, page = self.get("/done")                                 # nothing new: not uploaded twice
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
        _, page = self.get("/done")
        self.assertIn("could not be uploaded, because the RDM cannot be reached", page)
        config.set_local("source_dir", str(self.source))                    # and comes back
        _, page = self.get("/done")
        self.assertIn("Your labels have been uploaded to the RDM", page)


if __name__ == "__main__":
    unittest.main()
