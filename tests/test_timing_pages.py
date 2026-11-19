"""Lateness measure, the made-up recorder and the timing report (no participant data)."""

import unittest

from parkour import chart, lag, timing, timing_report, timing_sketch
from tests.test_summary import SECOND, STUDY, video

STEP = SECOND // 10                                 # test videos run at 10 fps


class Lags(unittest.TestCase):
    def test_steady_stamps_are_not_late(self):
        self.assertEqual(set(lag.lags(video("a", 0, 50).times, 10.0)), {0.0})

    def test_frames_saved_after_a_hold_up_are_late_by_the_wait(self):
        # Frames 20 to 24 all waited and were stamped together, 0.5 s on.
        v = video("a", 0, 50)
        for i in range(20, 25):
            v.times[i] = v.times[25]
        found = lag.lags(v.times, 10.0)
        self.assertAlmostEqual(found[20], 0.5)      # waited longest
        self.assertAlmostEqual(found[24], 0.1)
        self.assertEqual(found[19], 0.0)
        self.assertEqual(found[25], 0.0)

    def test_look_ahead_limits_how_far_later_frames_count(self):
        v = video("a", 0, 50)
        v.times[0] += 4 * STEP                      # frame 0 stamped 0.4 s late
        self.assertAlmostEqual(lag.lags(v.times, 10.0)[0], 0.4)
        self.assertEqual(lag.lags(v.times, 10.0, look_ahead_seconds=0)[0], 0.4)

    def test_empty_or_unrated_video(self):
        self.assertEqual(lag.lags([], 30.0), [])
        self.assertEqual(lag.lags([1, 2], None), [])


class Sketch(unittest.TestCase):
    def setUp(self):
        self.sketch = timing_sketch.record(n_frames=40, busy_at=8, busy_frames=6)

    def test_stamps_are_right_before_the_hold_up_and_after_the_catch_up(self):
        late = self.sketch.late
        self.assertEqual(set(late[:8]), {0})
        self.assertEqual(late[8], 6)                # waited the whole hold-up
        self.assertEqual(set(late[self.sketch.caught_up_at:]), {0})

    def test_a_stamp_is_never_early_and_never_goes_back(self):
        stamps = self.sketch.stamps
        self.assertTrue(all(x >= 0 for x in self.sketch.late))
        self.assertEqual(stamps, sorted(stamps))

    def test_catch_up_repeats_every_third_stamp(self):
        repeats = self.sketch.repeats
        self.assertEqual([i for i in range(8, 18) if repeats[i]], [9, 12, 15])

    def test_measured_lag_matches_the_made_up_lateness(self):
        measured = lag.lags(self.sketch.times, self.sketch.frame_rate)
        for found, late in zip(measured, self.sketch.late):
            self.assertAlmostEqual(found, late / self.sketch.frame_rate, places=4)

    def test_rule_example_keeps_and_removes_as_labelled(self):
        example = timing_sketch.rule_example(1.0, 0.1)
        self.assertEqual([c.kept for c in example.clips], [True, False, False, True])
        (run,) = example.removed_runs
        self.assertEqual(run[0], example.sketch.busy_at)


class RemovedFrames(unittest.TestCase):
    def test_frames_outside_every_allowed_window_are_removed(self):
        removed = timing.removed_frames(12, [0, 1, 8], 4)
        self.assertEqual([i for i, gone in enumerate(removed) if gone], [5, 6, 7])


class Chart(unittest.TestCase):
    def test_axis_has_round_ticks_and_places_values(self):
        axis = chart.axis(0, 547, about=4)
        self.assertEqual(axis.ticks, [0, 200, 400, 600])
        self.assertEqual(axis.at(300, 0, 100), 50)

    def test_runs(self):
        self.assertEqual(chart.runs([True, False, True, True]), [(0, 0), (2, 3)])


class Report(unittest.TestCase):
    def setUp(self):
        clean = video("unlabelled_x_1", 0, 100)
        held_up = video("task_000_2", 20, 60, task=0)
        for i in range(30, 60):
            held_up.times[i] += 2 * SECOND          # a 2.1 s gap before frame 30
        held_up.times[31] = held_up.times[30]       # then one repeated stamp
        short = video("task_001_3", 40, 5, task=1)  # too short for a clip
        self.report = timing_report.build([clean, held_up, short], STUDY)

    def test_counts(self):
        r = self.report
        self.assertEqual((r.n_frames, r.n_repeats, r.n_pauses), (160, 1, 1))
        self.assertAlmostEqual(r.longest_step, 2.1)
        self.assertAlmostEqual(r.worst_lag, 0.1)    # frame 30 shares frame 31's stamp

    def test_kept_and_removed_frames(self):
        r = self.report
        self.assertEqual(r.n_kept + r.n_removed, r.n_frames)
        self.assertEqual(r.n_removed, 1)            # frame 30 sits between the gap and the repeat
        self.assertLess(r.clips_allowed, r.clips_possible)
        self.assertEqual(r.clips_possible, 91 + 51)

    def test_tasks(self):
        self.assertEqual(self.report.n_tasks, 2)
        self.assertEqual(self.report.lost_tasks, ["Task 1"])   # too short for any clip

    def test_nothing_to_report_without_a_long_enough_video(self):
        self.assertIsNone(timing_report.build([video("a", 0, 5)], STUDY))


if __name__ == "__main__":
    unittest.main()
