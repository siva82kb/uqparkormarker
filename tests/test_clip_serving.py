"""Clips must never be shown from an earlier set: address code and no storing."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from parkour import clipset, config
from parkour.sampling import Segment


def rows(first_frame):
    return [Segment(f"seg_{i:04d}", "v.avi", first_frame + 100 * i, first_frame + 100 * i + 29,
                    "2026-01-01T10:00:00+10:00", "2026-01-01T10:00:01+10:00", "")
            for i in range(1, 4)]


class ClipServing(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        local = root / "local.toml"
        local.write_text('subject = "Pxx"\nsource_dir = "X:/nowhere"\nrater = "ann"\n', encoding="utf-8")
        for name, value in (("CLIPS_ROOT", root / "clips"), ("LOCAL_FILE", local)):
            patch = mock.patch.object(config, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        from app import app
        self.client = app.test_client()

    def get(self, address, **options):
        """Fetch an address, read it fully and close it (Windows keeps a file
        locked while a response to it is still open)."""
        response = self.client.get(address, **options)
        response.get_data()
        response.close()
        return response

    def generate(self, first_frame, content):
        """Stand in for generating a set: write the list and the clip files."""
        clipset.write_plan("Pxx", rows(first_frame))
        plan = clipset.folder("Pxx") / clipset.SEGMENTS_FILE
        os.utime(plan, ns=(first_frame * 10**9, first_frame * 10**9))   # a new moment each time
        for row in rows(first_frame):
            clipset.clip_path("Pxx", row.segment_id).write_bytes(content)
        return clipset.set_code("Pxx")

    def test_code_is_short_and_empty_before_any_clips(self):
        self.assertEqual(clipset.set_code("Pxx"), "")
        self.assertRegex(self.generate(1, b"one"), r"^[0-9a-f]{10}$")

    def test_generating_again_changes_every_clip_address(self):
        first = self.generate(1, b"first set")
        second = self.generate(2, b"second set")
        self.assertNotEqual(first, second)
        old = self.get(f"/clips/{first}/seg_0001.mp4")
        new = self.get(f"/clips/{second}/seg_0001.mp4")
        self.assertEqual(old.status_code, 404)              # the old address is dead
        self.assertEqual(new.data, b"second set")

    def test_same_settings_generated_again_still_get_a_new_code(self):
        first = self.generate(1, b"a")
        clipset.write_plan("Pxx", rows(1))               # the very same list, written later
        self.assertNotEqual(first, clipset.set_code("Pxx"))

    def test_browser_is_told_to_store_nothing(self):
        code = self.generate(1, b"clip")
        response = self.get(f"/clips/{code}/seg_0001.mp4")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for header in ("ETag", "Last-Modified", "Expires"):
            self.assertNotIn(header, response.headers)

    def test_part_of_a_clip_can_be_asked_for(self):
        code = self.generate(1, b"0123456789")
        part = self.get(f"/clips/{code}/seg_0001.mp4", headers={"Range": "bytes=2-5"})
        self.assertEqual((part.status_code, part.data), (206, b"2345"))
        self.assertEqual(part.headers["Cache-Control"], "no-store")

    def test_annotation_page_uses_the_coded_address(self):
        code = self.generate(1, b"clip")
        page = self.client.get("/annotate").get_data(as_text=True)
        self.assertIn(f'src="/clips/{code}/seg_', page)
        self.assertNotIn("prefetch", page)


if __name__ == "__main__":
    unittest.main()
