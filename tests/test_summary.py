"""Summary calculations on hand-built videos (no participant data)."""

import unittest
from pathlib import Path

from parkour import summary
from parkour.dataset import Video

SECOND = 1_000_000

STUDY = {
    "source": {"utc_offset_hours": 10},
    "timing": {"max_step_seconds": 0.3},
    "sampling": {"strategy": "uniform", "n_segments": 20, "window_seconds": 1.0, "seed": 7},
}


def video(name, start_s, n_frames, task=None, step=SECOND // 10, **changes):
    """A video of n_frames at 10 fps starting start_s seconds after the epoch."""
    times = [start_s * SECOND + i * step for i in range(n_frames)]
    fields = dict(
        path=Path(f"{name}.avi"),
        task_number=task,
        task_name=f"{task:02d}:Task {task}" if task is not None else None,
        filename_time=times[0] if times else start_s * SECOND,
        frame_count=n_frames,
        frame_rate=1_000_000 / step,
        times=times,
    )
    return Video(**{**fields, **changes})


class Build(unittest.TestCase):
    def setUp(self):
        self.videos = [
            video("unlabelled_x_1", 0, 101),            # 0 to 10 s
            video("task_000_2", 10, 51, task=0),        # 10 to 15 s, no gap
            video("task_000_3", 20, 26, task=0),        # 20 to 22.5 s, 5 s gap
        ]
        self.summary = summary.build(self.videos, STUDY)

    def test_counts_and_durations(self):
        s = self.summary
        self.assertEqual((s.n_videos, s.n_task, s.n_unlabelled), (3, 2, 1))
        self.assertAlmostEqual(s.unlabelled_seconds, 10.0)
        self.assertAlmostEqual(s.task_seconds, 7.5)
        self.assertAlmostEqual(s.span_seconds, 22.5)
        self.assertAlmostEqual(s.fps_median, 10.0)

    def test_gaps(self):
        self.assertEqual(len(self.summary.gaps), 1)
        self.assertAlmostEqual(self.summary.gaps[0].seconds, 5.0)

    def test_windows_stay_inside_one_video(self):
        # 101, 51 and 26 frames hold 10, 5 and 2 windows of 10 frames.
        self.assertEqual(self.summary.n_windows, 10 + 5 + 2)

    def test_task_table_merges_repeats(self):
        (row,) = self.summary.tasks
        self.assertEqual((row.number, row.name, row.repeats), (0, "Task 0", 2))
        self.assertAlmostEqual(row.seconds, 7.5)

    def test_timeline_covers_the_whole_span(self):
        spans = self.summary.timeline
        self.assertEqual([s.kind for s in spans], ["unlabelled", "task", "gap", "task"])
        self.assertAlmostEqual(spans[-1].left + spans[-1].width, 100.0)

    def test_clean_data_has_no_problems(self):
        self.assertEqual(self.summary.problems, [])


class Problems(unittest.TestCase):
    def problems(self, *videos):
        return summary.build(list(videos), STUDY).problems

    def test_missing_vidt(self):
        (note,) = self.problems(video("a", 0, 10, times=None))
        self.assertIn("no .vidt", note)

    def test_frame_count_mismatch(self):
        (note,) = self.problems(video("a", 0, 10, frame_count=12))
        self.assertIn("12 frames but 10 timestamps", note)

    def test_backward_timestamps(self):
        v = video("a", 0, 5)
        v.times[4] = v.times[3] - 1
        self.assertIn("backwards in 1 places", " ".join(self.problems(v)))

    def test_windows_left_out_for_late_stamps(self):
        clean = video("task_000_1", 0, 30, task=0)
        late = video("task_001_2", 10, 30, task=1)
        late.times[15] = late.times[14]             # a repeated stamp mid-video
        s = summary.build([clean, late], STUDY)
        (note,) = s.problems
        self.assertIn("left out of sampling", note)
        self.assertIn("pause longer than 0.3 s", note)
        self.assertNotIn("no usable window", note)
        self.assertEqual(s.n_windows, 3 + 2)        # the late video loses one

    def test_task_with_no_usable_window(self):
        late = video("task_001_2", 10, 12, task=1)
        late.times[6] = late.times[5]
        (note,) = self.problems(video("task_000_1", 0, 30, task=0), late)
        self.assertIn("1 of the 2 tasks has no usable window", note)

    def test_too_little_task_video_for_the_share_wanted(self):
        study = {**STUDY, "sampling": {**STUDY["sampling"], "task_share": 0.5}}
        clips = [video("task_000_1", 0, 30, task=0), video("unlabelled_x_2", 10, 300)]
        s = summary.build(clips, study)
        self.assertEqual((s.n_windows_task, s.n_windows_unlabelled), (3, 30))
        self.assertEqual(s.quotas, {"task": 10, "unlabelled": 10})
        (note,) = s.problems
        self.assertIn("10 clips are wanted from task video, but it has room for only 3", note)

    def test_listed_but_absent_videos(self):
        s = summary.build([video("a", 0, 10)], STUDY, ["task_001_5", "unlabelled_x_6"])
        self.assertIn("2 videos listed", s.problems[0])
        self.assertIn("(1 task, 1 unlabelled)", s.problems[0])

    def test_file_name_time_disagrees(self):
        (note,) = self.problems(video("a", 0, 10, filename_time=5 * SECOND))
        self.assertIn("5.0 s away", note)


if __name__ == "__main__":
    unittest.main()
