"""Sampling and the clip folder, on hand-built videos (no participant data)."""

import unittest

from parkour import clipset, sampling
from parkour.sampling import uniform
from tests.test_summary import SECOND, video

STUDY = {
    "source": {"utc_offset_hours": 10},
    "sampling": {"strategy": "uniform", "n_segments": 20, "window_seconds": 1.0,
                 "frames_per_clip": 10, "seed": 7},
}


def videos():
    return [
        video("unlabelled_x_1", 0, 305),            # 30.4 s
        video("task_000_2", 40, 56, task=0),        # 5.5 s
        video("task_001_3", 50, 8, task=1),         # 0.7 s: too short for a window
        video("unlabelled_x_4", 60, 100, times=None),
    ]


class Uniform(unittest.TestCase):
    def setUp(self):
        self.windows = uniform.sample(videos(), 20, 10, seed=7)

    def test_draws_the_number_asked_for(self):
        self.assertEqual(len(self.windows), 20)

    def test_never_more_than_fit(self):
        crowded = uniform.sample(videos(), 500, 10, seed=7)
        self.assertLessEqual(len(crowded), 30 + 5)      # 30.4 s and 5.5 s of video
        self.assertGreaterEqual(len(crowded), 20)
        self.assert_no_overlap(crowded)

    def test_starts_are_not_on_a_grid(self):
        offsets = {w.start_frame % 10 for w in self.windows}
        self.assertGreater(len(offsets), 5)             # e.g. frame 32, not only 30, 40

    def test_same_seed_same_windows(self):
        again = uniform.sample(videos(), 20, 10, seed=7)
        key = lambda w: (w.video.name, w.start_frame, w.end_frame)
        self.assertEqual([key(w) for w in self.windows], [key(w) for w in again])
        other = uniform.sample(videos(), 20, 10, seed=8)
        self.assertNotEqual([key(w) for w in self.windows], [key(w) for w in other])

    def test_every_window_is_ten_frames_inside_one_video(self):
        for w in self.windows:
            times = w.video.times
            self.assertEqual(w.end_frame - w.start_frame + 1, 10)
            self.assertGreaterEqual(w.start_frame, 0)
            self.assertLess(w.end_frame, len(times))
            self.assertEqual((w.start_time, w.end_time),
                             (times[w.start_frame], times[w.end_frame]))

    def test_windows_do_not_overlap(self):
        self.assert_no_overlap(self.windows)

    def assert_no_overlap(self, windows):
        spans = sorted((w.start_time, w.end_time) for w in windows)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLess(end, start)
        frames = [(w.video.name, f) for w in windows
                  for f in range(w.start_frame, w.end_frame + 1)]
        self.assertEqual(len(frames), len(set(frames)))     # no frame used twice


class Draw(unittest.TestCase):
    def test_segments_are_numbered_in_time_order(self):
        segments = sampling.draw(videos(), STUDY)
        self.assertEqual(segments[0].segment_id, "seg_0001")
        self.assertEqual(segments[-1].segment_id, "seg_0020")
        starts = [s.start_time for s in segments]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(starts[0].endswith("+10:00"))
        self.assertEqual({s.task for s in segments}, {"", "00:Task 0"})


class DesignDifferences(unittest.TestCase):
    def test_flatten_names_nested_settings(self):
        flat = clipset._flatten({"a": {"b": 1}, "labels": [{"key": "1"}]})
        self.assertEqual(flat, {"a.b": 1, "labels.1.key": "1"})


if __name__ == "__main__":
    unittest.main()
