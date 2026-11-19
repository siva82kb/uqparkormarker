"""Saving what was read from a subject's videos, and using it again (no participant data)."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from parkour import config, loader, recording_store
from parkour.dataset import Recording
from tests.test_summary import video

SOURCE = Path("X:/source/P99")


class Store(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patched = mock.patch.object(config, "CLIPS_ROOT", Path(folder.name))
        patched.start()
        self.addCleanup(patched.stop)
        loader._cache.clear()
        self.addCleanup(loader._cache.clear)
        self.recording = Recording(
            videos=[video("unlabelled_x_1", 0, 30), video("task_000_2", 10, 20, task=0),
                    video("task_001_3", 20, 5, task=1, times=None)],
            missing=["task_002_4"],
            read_at=datetime(2026, 11, 19, 11, 40, tzinfo=timezone.utc),
        )

    def test_nothing_saved_yet(self):
        self.assertIsNone(recording_store.load(SOURCE))

    def test_what_is_saved_comes_back_the_same(self):
        recording_store.save(SOURCE, self.recording)
        back = recording_store.load(SOURCE)
        self.assertEqual(back.read_at, self.recording.read_at)
        self.assertEqual(back.missing, ["task_002_4"])
        for saved, original in zip(back.videos, self.recording.videos, strict=True):
            self.assertEqual(saved.name, original.name)
            self.assertEqual(saved.times, original.times)
            self.assertEqual((saved.task_number, saved.task_name, saved.frame_rate),
                             (original.task_number, original.task_name, original.frame_rate))

    def test_a_save_from_another_folder_is_not_used(self):
        recording_store.save(SOURCE, self.recording)
        self.assertIsNone(recording_store.load(Path("Y:/elsewhere/P99")))

    def test_a_damaged_file_is_not_used(self):
        recording_store.save(SOURCE, self.recording)
        recording_store.path(SOURCE).write_bytes(b"not a gzip file")
        self.assertIsNone(recording_store.load(SOURCE))

    def test_loader_uses_the_saved_recording_without_reading_the_videos(self):
        recording_store.save(SOURCE, self.recording)
        with mock.patch("parkour.dataset.load", side_effect=AssertionError("read again")):
            self.assertEqual(len(loader.fetch(SOURCE, 10).videos), 3)

    def test_forget_makes_the_next_fetch_read_and_save_again(self):
        recording_store.save(SOURCE, self.recording)
        loader.cached(SOURCE)
        self.assertTrue(loader.forget(SOURCE))
        self.assertIsNone(loader.cached(SOURCE))
        with mock.patch("parkour.dataset.load", return_value=self.recording) as read:
            loader.fetch(SOURCE, 10)
        read.assert_called_once()
        self.assertIsNotNone(recording_store.load(SOURCE))


if __name__ == "__main__":
    unittest.main()
