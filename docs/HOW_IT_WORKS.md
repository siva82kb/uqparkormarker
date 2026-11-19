# How the annotator works, and what to keep in mind when reading the results

This document explains, in plain terms, how the app turns a participant's
videos into the one-second clips that raters label. It is written for anyone
who will interpret the labels, especially when lining them up with sensor
data. It must be kept in step with the code.

## 1. Words used here

- **Video**: one recorded file. A participant has about 180 to 200 of them.
  Each is either a *task* video (one task being performed) or an
  *unlabelled* video (the time between two tasks).
- **Frame**: one picture in a video. The camera takes 30 per second.
- **Timestamp**: the clock time saved with each frame, in the `.vidt` file
  that sits next to each video.
- **Clip**: a one-second piece cut out of a video, 30 frames long. A clip is
  what the rater sees and labels.

## 2. From videos to clips, in four steps

1. **Read.** The app reads every video's timestamps for the chosen
   participant.
2. **Remove.** It works out every one-second piece that could be cut from
   every video, and removes the pieces whose timestamps cannot be trusted
   (section 4).
3. **Pick.** From the pieces that are left, it picks 500 at random, with no
   two sharing a frame (section 5).
4. **Cut.** It cuts each picked piece out of its video and saves it as a
   small MP4 file, with a row in `segments.csv` saying exactly where it came
   from (section 6).

A clip never crosses from one video into the next.

## 3. The timestamp problem

### What goes wrong

Each frame should be saved with the time it was filmed. The recording
program does not quite do that. It saves the time at which it *got round to
writing* the frame.

Most of the time these are the same to within a few hundredths of a second.
But now and then the recording program is busy for a moment, sometimes for
several seconds. The camera keeps filming. The frames wait in a queue. When
the program is free again it writes all the waiting frames quickly, one after
another, and gives each of them the current time, not the time it was filmed.

So those frames get timestamps that are **too late**, by as much as the time
they waited. A timestamp is never too early.

### What it looks like in the timestamps

A late stretch always has the same shape:

1. **A gap.** Two neighbouring frames whose timestamps are far apart, for
   example 3 seconds instead of 1/30 of a second. This is the moment the
   program was busy.
2. **A catch-up.** For some seconds after the gap, the waiting frames are
   written in a rush. Their timestamps are bunched together, and about every
   third frame has exactly the same timestamp as the frame before it.
3. **Back to normal.** Once the queue is empty, timestamps are right again.

The pictures themselves are fine throughout. Only the saved times are wrong.

### How big it is

Measured on the six participants whose videos could be read directly:

- In the least affected participant, 0.03% of frames were stamped more than
  0.2 s late, and the worst was 0.55 s late.
- In the other five, 2 to 3.3% of frames were more than 0.2 s late, and the
  worst were between 2 and 11 s late.

Test recordings from 2022 made at 10 frames per second show almost none of
this. At 30 frames per second the program has a third of the time to handle
each frame, so it falls behind more easily.

### A separate, smaller problem: missing time

In every session there are also a few seconds, in total, for which no frames
exist at all (between 0.6 and 17.7 s per session). So the number of frames
cannot be used to measure long stretches of time: counting frames from the
start of a session would drift by those seconds. The timestamps do not have
this problem, because each one is a fresh reading of the clock.

## 4. Which one-second pieces are removed

A one-second piece is removed if either of these is true:

- two neighbouring frames inside it are more than 0.1 s apart (a gap), or
- any frame inside it has the same timestamp as the frame before it (the
  sign of a catch-up).

Everything else is kept. **Whole videos are never removed**, only the
affected seconds.

### Example

A 60-second video in which the program was busy for 3 seconds:

| Part of the video | Timestamps | One-second pieces |
|---|---|---|
| Before the busy moment | normal | kept |
| The busy moment | one gap of 3 s | removed |
| The catch-up, about 8 s | bunched, with repeats | removed |
| After the catch-up | normal | kept |

That video loses about 9 or 10 seconds. The other 50 seconds can still be
picked.

### Why this is the right set to remove

The pieces that are removed are the ones whose timestamps are late, because
a late stretch always shows a gap or repeats. The pieces that are kept have
timestamps that are right to within about 0.1 s. Checked on six participants:
the worst kept piece was between 0.08 and 0.13 s late in five of them, and
0.21 s late in one.

Nothing is corrected. Affected pieces are simply never used.

### What it costs

- Across the six participants, between 2.5% and 12% of possible pieces are
  removed.
- Task videos lose more than unlabelled videos, because the program is often
  busy just as a new task recording starts.
- A short task that falls entirely inside a late stretch has no pieces left.
  Between 1 and 8 of the 91 tasks are lost this way, depending on the
  participant.

## 5. How the 500 clips are picked

Every one-second piece that was kept goes into one list, from all videos
together. The app picks from that list at random, and **every piece in the
list has the same chance**. A long video has more pieces in the list than a
short one, so it supplies more clips, in proportion to its length.

If a picked piece shares any frame with one already picked, it is thrown
back and another is drawn. So no two clips overlap.

A clip can start at any frame, not only on whole seconds. One clip might run
from 3.2 s to 4.2 s into a video.

The picking uses a fixed random seed, so every rater gets exactly the same
500 clips for a participant.

### Why the app picks a piece, and not a moment in time

An obvious other way would be to pick a random moment during the recording
and start the clip at the next frame after it. That is unfair when
timestamps have gaps.

Think of buses. If buses come every 10 minutes and you arrive at a random
time, you are equally likely to catch any of them. But if one bus is 3 hours
late, nearly everyone who arrives in those 3 hours gets on that one bus. In
the same way, the frame just after a 3-second gap would be picked about 90
times more often than a normal frame.

Picking directly from the list of pieces avoids this: each piece is in the
list once.

## 6. What is saved for each clip

Each clip is a row in `segments.csv`:

| Column | Meaning |
|---|---|
| `segment_id` | The clip's name, for example `seg_0042`; the clip file is `clips/seg_0042.mp4` |
| `video_file` | The video it was cut from |
| `start_frame`, `end_frame` | Its first and last frame in that video, counting from 0 |
| `start_time`, `end_time` | The timestamps of those two frames, in local time |
| `task` | The task being recorded; empty for unlabelled video |

`end_time` is about 0.97 s after `start_time`, not 1 s, because 30 frames
have 29 steps between them.

The frame numbers are exact. They are the surest record of where a clip came
from.

## 7. What to keep in mind when interpreting results

- **The clips are a random sample of the trustworthy footage, not of all
  footage.** The removed seconds cluster around moments when the recording
  program was busy, often the start of a task. If behaviour at those moments
  differs from the rest, the sample will not show it.
- **Some tasks may not appear at all.** A task can be missing from the 500
  clips by chance, or because all its footage was removed. The summary page
  says how many tasks have no usable piece.
- **Most clips come from unlabelled video**, because most of the recording
  is unlabelled video. The clips follow the footage.
- **Clip times are right to about 0.1 s, on the video computer's clock.**
  Within that, a frame can carry the next frame's time, an error of one
  frame (0.03 s).
- **There is a fixed delay that has not been measured.** Every timestamp is
  taken a little after the frame was filmed, because the picture has to
  travel from the camera to the program. This is probably a few hundredths
  of a second, and the same for every frame.
- **Clip times are not yet on the sensors' clock.** Each session has a jump
  task at the start and at the end for this purpose. Landings that can be
  seen in both the video and the sensor data give the difference between the
  two clocks and how much it changes over the session. They also cancel the
  fixed delay above. This step has not been done, and it is not part of this
  app.
- **The jump recordings themselves need checking.** In most participants one
  or both jump recordings contain a few affected frames, so the landings
  should be read from parts of those recordings where the timestamps are
  normal.
- **Only one participant is used so far**, the one least affected by the
  timestamp problem. Results from other participants would lose more footage
  and more tasks.

## 8. What has not been settled

- A proper fix for the late timestamps, which would allow the removed
  seconds to be used. One idea is to estimate when each frame was really
  filmed from the frames after it. It has not been adopted.
- Whether the version of the recording program used for the study stamps
  frames in the same way as the published version that was examined.
- How each sensor system records time, and so whether the jumps are needed
  to line the data up or only to check it.
- Participants whose videos are stored in session subfolders are not yet
  read by the app.
