# UQ Parkour Annotator

A small local web app for labelling functional upper-limb use in the UQ Parkour
study videos. It draws random 1-second windows from a participant's videos,
cuts them into short clips, and will show them one at a time to a rater, who
assigns each clip a FAABOS category.

Everything runs on the rater's own computer. Nothing is uploaded.

**Status: under construction.** The data summary and clip generation work.
The setup pages and the annotation page are not built yet. `PLAN.md` has the
design, the decisions made, and the build order. `docs/HOW_IT_WORKS.md`
explains how clips are chosen and what to keep in mind when interpreting the
results.

## What you need

- 64-bit Windows.
- [uv](https://docs.astral.sh/uv/), which fetches the right Python and the
  packages on first run. A `run.bat` that installs it for you is planned.
- Access to the source videos: the study's RDM storage mapped as a drive
  (connect to the UQ VPN first if you are off campus), or a local copy.

## Starting the app

Until the setup pages exist, tell the app where the data is by creating a
file named `local.toml` next to `app.py`:

```toml
data_source = "videos"
source_dir = "X:/path/to/the/folder/holding/the/participant/folders"
subject = "Pxx"
```

While testing, you can add `clip_limit = 25` to `local.toml`. The app then
works with only the first 25 clips, which matters because cutting clips from
the RDM over the VPN takes about half a minute each (several hours for 500).
The full list of 500 is still drawn and saved; remove the line to cut the
rest.

Then, in a terminal in this folder:

```
uv run python app.py
```

and open `http://127.0.0.1:5000`.

## What the app does today

1. **Reads the videos.** The first page shows a progress bar while the frame
   timestamps of every video are read. From the RDM this takes about a minute
   and is done once each time the app starts.
2. **Shows the data summary**: number of videos, recorded time, frame rate, a
   timeline of task and unlabelled video, problems found in the files, gaps,
   and the list of tasks.
3. **Generates the clips.** "Generate clips" chooses up to 500 random,
   non-overlapping 1 s windows and cuts each into an MP4 clip, showing
   progress. If the app is closed part-way, it carries on from the first
   missing clip next time.

   Not every window can be chosen. The recorder sometimes stamped frames
   late, which shows in the timestamps as a pause followed by repeated
   values. A window containing a repeated timestamp, or a step of more than
   0.1 s between frames, is never sampled, so that every clip's times can be
   trusted when clips are later lined up with sensor data. The summary page
   says what share of windows this leaves out.

Annotation comes next.

## Which participants are listed

A participant is a folder named `P` plus digits in the source folder, with its
videos directly in a `Video` folder. Participants whose `Video` folder is
split into session subfolders are not offered for now.

## Where things are stored

```
<source>/Pxx/Video/*.avi, *.vidt, experiment_details.json     source videos (read only)

data4annotation/<subject>/
    segments.csv            the sampled windows
    design.toml             copy of the settings they were drawn with
    clips/seg_0001.mp4 ...  the 1 s clips
```

`data4annotation/` and `local.toml` are never committed to git.

`segments.csv` has one row per clip: `segment_id`, `video_file`,
`start_frame`, `end_frame` (inclusive), `start_time`, `end_time` (timestamps
of the first and last frame, local time), and `task` (empty for unlabelled
video).

## Settings

`study.toml` holds the study design: the category labels, the number of
clips, the clip length, the sampling method and its random seed, the
timestamp rule, and the clip quality. Every rater must use the same `study.toml`. If it changes after
clips have been generated, the app stops and says what differs, because old
and new clips must not be mixed.

## For developers

- Run everything through `uv`: `uv run python app.py`.
- Tests: `uv run python -m unittest discover -s tests -t .`
- Code layout and conventions: `PLAN.md` section 7 and `CLAUDE.md`.
