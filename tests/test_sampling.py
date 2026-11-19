"""Timing rule, sampling and the clip folder, on hand-built videos (no participant data)."""

import unittest

from parkour import clipset, sampling, timing
from parkour.sampling import uniform
from tests.test_summary import STUDY, video


def videos():
    return [
        video("unlabelled_x_1", 0, 305),            # 30.4 s
        video("task_000_2", 40, 56, task=0),        # 5.5 s
        video("task_001_3", 50, 8, task=1),         # 0.7 s: too short for a window
        video("unlabelled_x_4", 60, 100, times=None),
    ]


class CleanStarts(unittest.TestCase):
    def test_every_start_allowed_in_a_clean_video(self):
        self.assertEqual(timing.clean_starts(video("a", 0, 25), 10, 0.3), list(range(16)))

    def test_too_short_or_untimed_video_offers_nothing(self):
        self.assertEqual(timing.clean_starts(video("a", 0, 8), 10, 0.3), [])
        self.assertEqual(timing.clean_starts(video("a", 0, 30, times=None), 10, 0.3), [])

    def test_repeated_stamp_blocks_the_windows_that_contain_it(self):
        v = video("a", 0, 40)
        v.times[20] = v.times[19]                   # frame 20 repeats frame 19
        starts = timing.clean_starts(v, 10, 0.3)
        # A window is blocked if it holds both frame 19 and frame 20.
        self.assertEqual(starts, [*range(0, 11), *range(20, 31)])

    def test_pause_blocks_the_windows_that_span_it(self):
        v = video("a", 0, 40)
        for i in range(20, 40):
            v.times[i] += 2_000_000                 # a 2.1 s step before frame 20
        self.assertEqual(timing.clean_starts(v, 10, 0.3), [*range(0, 11), *range(20, 31)])

    def test_count_fitting(self):
        self.assertEqual(timing.count_fitting(list(range(16)), 10), 2)
        self.assertEqual(timing.count_fitting([*range(0, 11), *range(20, 31)], 10), 2 + 2)
        self.assertEqual(timing.count_fitting([], 10), 0)


class Uniform(unittest.TestCase):
    def sample(self, n, seed=7, clips=None):
        return uniform.sample(sampling.pools(clips or videos(), STUDY), n, seed)

    def setUp(self):
        self.windows = self.sample(20)

    def test_draws_the_number_asked_for(self):
        self.assertEqual(len(self.windows), 20)

    def test_never_more_than_fit(self):
        crowded = self.sample(500)
        self.assertLessEqual(len(crowded), 30 + 5)      # 30.4 s and 5.5 s of video
        self.assertGreaterEqual(len(crowded), 20)
        self.assert_no_overlap(crowded)

    def test_starts_are_not_on_a_grid(self):
        offsets = {w.start_frame % 10 for w in self.windows}
        self.assertGreater(len(offsets), 5)             # e.g. frame 32, not only 30, 40

    def test_same_seed_same_windows(self):
        key = lambda w: (w.video.name, w.start_frame, w.end_frame)
        self.assertEqual([key(w) for w in self.windows], [key(w) for w in self.sample(20)])
        self.assertNotEqual([key(w) for w in self.windows],
                            [key(w) for w in self.sample(20, seed=8)])

    def test_every_window_is_ten_frames_inside_one_video(self):
        for w in self.windows:
            self.assertEqual(w.end_frame - w.start_frame + 1, 10)
            self.assertGreaterEqual(w.start_frame, 0)
            self.assertLess(w.end_frame, len(w.video.times))

    def test_windows_do_not_overlap(self):
        self.assert_no_overlap(self.windows)

    def test_no_window_contains_a_late_stamp(self):
        clips = videos()
        long = clips[0]
        long.times[100] = long.times[99]                # a repeat
        for i in range(200, len(long.times)):
            long.times[i] += 3_000_000                  # and a 3.1 s pause
        for w in self.sample(500, clips=clips):
            steps = [b - a for a, b in zip(w.video.times[w.start_frame:w.end_frame],
                                           w.video.times[w.start_frame + 1:w.end_frame + 1])]
            self.assertTrue(all(0 < s <= 300_000 for s in steps))

    def assert_no_overlap(self, windows):
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
