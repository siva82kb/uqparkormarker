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


class TaskShare(unittest.TestCase):
    """A set share of the clips comes from task video, the rest from unlabelled."""

    def draw(self, share, n=20):
        study = {**STUDY, "sampling": {**STUDY["sampling"], "n_segments": n, "task_share": share}}
        segments = sampling.draw(videos(), study)
        return sum(bool(s.task) for s in segments), sum(not s.task for s in segments)

    def test_quotas(self):
        self.assertEqual(sampling.quotas({"n_segments": 500, "task_share": 0.7}),
                         {"task": 350, "unlabelled": 150})
        self.assertEqual(sampling.quotas({"n_segments": 25, "task_share": 0.7}),
                         {"task": 18, "unlabelled": 7})
        self.assertIsNone(sampling.quotas({"n_segments": 500}))

    def test_each_kind_supplies_its_number(self):
        self.assertEqual(self.draw(0.1), (2, 18))
        self.assertEqual(self.draw(0.2, n=10), (2, 8))

    def test_all_or_none_from_task_video(self):
        self.assertEqual(self.draw(0.0, n=10), (0, 10))
        self.assertEqual(self.draw(1.0, n=3), (3, 0))

    def test_a_shortfall_is_not_made_up_by_the_other_kind(self):
        task, unlabelled = self.draw(0.9)           # 18 wanted from 5.5 s of task video
        self.assertLessEqual(task, 5)
        self.assertEqual(unlabelled, 2)

    def test_no_share_set_draws_from_everything_together(self):
        segments = sampling.draw(videos(), STUDY)
        self.assertEqual(len(segments), 20)


class CuttingProgress(unittest.TestCase):
    """What the generate page is told about clips from task video."""

    def test_counts_task_clips_among_those_that_exist(self):
        import tempfile
        from pathlib import Path
        from parkour import config, extract
        from parkour.sampling import Segment

        with tempfile.TemporaryDirectory() as folder:
            saved = config.CLIPS_ROOT, config.LOCAL_FILE
            config.CLIPS_ROOT, config.LOCAL_FILE = Path(folder), Path(folder) / "none.toml"
            self.addCleanup(lambda: setattr(config, "CLIPS_ROOT", saved[0]))
            self.addCleanup(lambda: setattr(config, "LOCAL_FILE", saved[1]))
            config.STUDY_FILE.exists() or self.skipTest("no study.toml")
            rows = [Segment(f"seg_{i:04d}", "v.avi", 0, 29, "", "", "Jump" if i <= 3 else "")
                    for i in range(1, 6)]                   # 3 task clips, 2 unlabelled
            clipset.write_plan("Pxx", rows)
            for cut in ("seg_0001", "seg_0002", "seg_0004"):    # 2 task, 1 unlabelled cut
                clipset.clip_path("Pxx", cut).write_bytes(b"")
            seen = extract.snapshot("Pxx")
            self.assertEqual((seen["done"], seen["total"]), (3, 5))
            self.assertEqual((seen["task_done"], seen["task_total"]), (2, 3))


class SignsOfLife(unittest.TestCase):
    """The seconds a page shows ticking beside the status text."""

    def test_seconds_count_only_while_a_step_is_running(self):
        import time
        from parkour import extract

        running = extract.Progress(state="running", step_started=time.monotonic() - 12.4)
        self.assertEqual(running.report()["step_seconds"], 12)
        self.assertNotIn("step_started", running.report())      # internal, not for pages
        for state in ("idle", "done", "failed"):
            stopped = extract.Progress(state=state, step_started=time.monotonic() - 12.4)
            self.assertEqual(stopped.report()["step_seconds"], 0)
        self.assertEqual(extract.Progress(state="running").report()["step_seconds"], 0)


class SlowClip(unittest.TestCase):
    """The status line stays quiet unless the clip being cut is unusually slow."""

    def slow(self, seconds_on_clip, per_clip, state="running", total=10):
        import time
        from parkour import extract
        progress = extract.Progress(state=state, done=4 if total else 0, total=total,
                                    per_clip=per_clip,
                                    step_started=time.monotonic() - seconds_on_clip)
        return progress.report()["slow"]

    def test_ordinary_clip_is_not_slow(self):
        self.assertFalse(self.slow(12, per_clip=10))
        self.assertFalse(self.slow(45, per_clip=10))        # 4.5 times, but under a minute

    def test_long_but_usual_clip_is_not_slow(self):
        self.assertFalse(self.slow(100, per_clip=40))       # over a minute, but only 2.5 times

    def test_much_longer_than_usual_is_slow(self):
        self.assertTrue(self.slow(65, per_clip=10))
        self.assertTrue(self.slow(130, per_clip=40))

    def test_first_clip_is_slow_only_after_two_minutes(self):
        self.assertFalse(self.slow(90, per_clip=None))
        self.assertTrue(self.slow(125, per_clip=None))

    def test_reading_videos_is_never_called_slow(self):
        self.assertFalse(self.slow(300, per_clip=None, total=0))

    def test_nothing_is_slow_once_the_job_has_stopped(self):
        self.assertFalse(self.slow(300, per_clip=10, state="done"))
        self.assertFalse(self.slow(300, per_clip=10, state="failed"))


class TimeSpent(unittest.TestCase):
    """The running total of time spent generating, kept across runs."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from parkour import config

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(config, "CLIPS_ROOT", Path(folder.name))
        patch.start()
        self.addCleanup(patch.stop)

    def test_nothing_spent_yet(self):
        spent = clipset.read_spent("Pxx")
        self.assertEqual((spent.seconds, spent.clips, spent.per_clip), (0.0, 0, None))

    def test_total_adds_up_and_is_read_back_from_disk(self):
        clipset.add_spent("Pxx", 40.0)                  # reading videos, choosing clips
        clipset.add_spent("Pxx", 10.0, clips=1)
        clipset.add_spent("Pxx", 20.0, clips=1)
        spent = clipset.read_spent("Pxx")               # as a restarted app would see it
        self.assertAlmostEqual(spent.seconds, 70.0)
        self.assertEqual(spent.clips, 2)
        self.assertAlmostEqual(spent.per_clip, 15.0)    # preparation is not counted here

    def test_unreadable_file_starts_again_from_zero(self):
        clipset.add_spent("Pxx", 5.0)
        (clipset.folder("Pxx") / clipset.SPENT_FILE).write_text("not json", encoding="utf-8")
        self.assertEqual(clipset.read_spent("Pxx").seconds, 0.0)

    def test_page_is_told_total_and_time_left(self):
        import time
        from parkour import extract

        cutting = extract.Progress(state="running", done=4, total=10, spent=100.0,
                                   per_clip=20.0, step_started=time.monotonic() - 5.2)
        told = cutting.report()
        self.assertEqual(told["elapsed_seconds"], 105)          # saved total plus this clip
        self.assertEqual(told["left_seconds"], 114)     # six clips at 20 s, less 5.2 s on this one
        for hidden in ("spent", "per_clip", "step_started"):
            self.assertNotIn(hidden, told)

    def test_no_guess_of_time_left_without_a_clip_to_judge_by(self):
        from parkour import extract
        self.assertIsNone(extract.Progress(state="running", done=0, total=10).report()["left_seconds"])

    def test_finished_job_reports_the_total_and_nothing_left(self):
        from parkour import extract
        told = extract.Progress(state="done", done=10, total=10, spent=312.7, per_clip=30.0).report()
        self.assertEqual((told["elapsed_seconds"], told["left_seconds"]), (312, None))

    def test_stopped_job_still_reports_what_was_spent(self):
        from parkour import extract
        told = extract.Progress(state="idle", done=4, total=10, spent=100.0, per_clip=20.0).report()
        self.assertEqual((told["elapsed_seconds"], told["left_seconds"]), (100, 120))


class ClipLimit(unittest.TestCase):
    """The `clip_limit` test setting must hold on a first run as well as later."""

    def test_limit_applies_when_the_list_is_first_made(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest import mock
        from parkour import config, extract

        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / "local.toml"
            local.write_text('subject = "Pxx"\nclip_limit = 5\n', encoding="utf-8")
            study = {**STUDY, "sampling": {**STUDY["sampling"], "n_segments": 20}}
            with mock.patch.object(config, "CLIPS_ROOT", Path(folder)), \
                 mock.patch.object(config, "LOCAL_FILE", local), \
                 mock.patch.object(extract.loader, "fetch",
                                   return_value=SimpleNamespace(videos=videos())):
                first = extract._clips_to_cut("Pxx", Path(folder), study)     # makes the list
                again = extract._clips_to_cut("Pxx", Path(folder), study)     # reads it back
                saved = (Path(folder) / "Pxx" / "segments.csv").read_text().splitlines()
            self.assertEqual(len(first), 5)                 # this was 20 before the fix
            self.assertEqual([s.segment_id for s in first], [s.segment_id for s in again])
            self.assertEqual(len(saved) - 1, 20)            # the full list is still saved


class Spacing(unittest.TestCase):
    """The check shown on the generate page that no two clips overlap."""

    def clip(self, number, video, first):
        from parkour.sampling import Segment
        return Segment(f"seg_{number:04d}", video, first, first + 29, "", "", "")

    def test_closest_pair_within_one_video(self):
        found = clipset.spacing([
            self.clip(1, "a.avi", 0), self.clip(2, "a.avi", 34),     # 4 frames between
            self.clip(3, "a.avi", 200), self.clip(4, "b.avi", 10),   # other video: not compared
        ])
        self.assertEqual((found.shared, found.closest, found.pair), (0, 4, ("seg_0001", "seg_0002")))

    def test_back_to_back_clips_do_not_share_a_frame(self):
        found = clipset.spacing([self.clip(1, "a.avi", 0), self.clip(2, "a.avi", 30)])
        self.assertEqual((found.shared, found.closest), (0, 0))

    def test_overlap_is_reported(self):
        found = clipset.spacing([self.clip(1, "a.avi", 0), self.clip(2, "a.avi", 29)])
        self.assertEqual(found.shared, 1)

    def test_drawn_clips_never_overlap(self):
        from parkour import fmt
        segments = sampling.draw(videos(), STUDY)
        self.assertEqual(clipset.spacing(segments).shared, 0)
        self.assertRegex(fmt.clock(segments[0].start_time), r"^\d\d:\d\d:\d\d\.\d{3}$")
        self.assertEqual(fmt.clip_number("seg_0042"), 42)

    def test_one_clip_per_video_has_nothing_to_compare(self):
        found = clipset.spacing([self.clip(1, "a.avi", 0), self.clip(2, "b.avi", 0)])
        self.assertEqual((found.shared, found.closest, found.pair), (0, None, None))

    def test_closest_start_times(self):
        from parkour.sampling import Segment
        at = lambda n, t: Segment(f"seg_{n:04d}", f"{n}.avi", 0, 29, f"2026-06-29T10:00:{t}+10:00", "", "")
        found = clipset.spacing([at(1, "00.000000"), at(2, "01.250000"), at(3, "09.000000")])
        self.assertAlmostEqual(found.closest_starts, 1.25)


class DesignDifferences(unittest.TestCase):
    def test_flatten_names_nested_settings(self):
        flat = clipset._flatten({"a": {"b": 1}, "labels": [{"key": "1"}]})
        self.assertEqual(flat, {"a.b": 1, "labels.1.key": "1"})


if __name__ == "__main__":
    unittest.main()
