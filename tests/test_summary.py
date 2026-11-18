"""Summary calculations on hand-built videos (no participant data)."""

import unittest
from pathlib import Path

from parkour import summary
from parkour.dataset import Video

SECOND = 1_000_000


def video(name, start_s, n_frames, task=None, step=SECOND // 10, **changes):
    """A video of n_frames at 10 fps starting start_s seconds after the epoch."""
    times = [start_s * SECOND + i * step for i in range(n_frames)]
    fields = dict(
        path=Path(f"{name}.avi"),
        task_number=task,
        task_name=f"{task:02d}:Task {task}" if task is not None else None,
        filename_time=times[0] if times else start_s * SECOND,
        frame_count=n_frames,
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
        self.summary = summary.build(self.videos, 1.0, 10)

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
        return summary.build(list(videos), 1.0, 10).problems

    def test_missing_vidt(self):
        (note,) = self.problems(video("a", 0, 10, times=None))
        self.assertIn("no .vidt", note)

    def test_frame_count_mismatch(self):
        (note,) = self.problems(video("a", 0, 10, frame_count=12))
        self.assertIn("12 frames but 10 timestamps", note)

    def test_repeated_and_backward_timestamps(self):
        v = video("a", 0, 5)
        v.times[2] = v.times[1]            # repeat
        v.times[4] = v.times[3] - 1        # backwards
        notes = " ".join(self.problems(v))
        self.assertIn("backwards in 1 places", notes)
        self.assertIn("1 frames repeat", notes)

    def test_listed_but_absent_videos(self):
        s = summary.build([video("a", 0, 10)], 1.0, 10, ["task_001_5", "unlabelled_x_6"])
        self.assertIn("2 videos listed", s.problems[0])
        self.assertIn("(1 task, 1 unlabelled)", s.problems[0])

    def test_file_name_time_disagrees(self):
        (note,) = self.problems(video("a", 0, 10, filename_time=5 * SECOND))
        self.assertIn("5.0 s away", note)


if __name__ == "__main__":
    unittest.main()
