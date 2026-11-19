# UQ Parkour Annotator

A small local web app for labelling functional upper-limb use in the UQ Parkour
study videos. It draws random 1-second windows from a participant's videos,
cuts them into short clips, and shows them one at a time to a rater, who
assigns each clip a FAABOS category.

Everything runs on the rater's own computer. Nothing is uploaded.

**Status: under construction.** The data summary, clip generation, sign-in
and annotation work. The pages for choosing the data folder and participant
are not built yet, so those are set by hand (see below). `PLAN.md` has the
design, the decisions made, and the build order. How clips are
chosen, and what to keep in mind when interpreting the results, is explained
in the app itself, under **Docs**. That is the only copy.

## What you need

- 64-bit Windows.
- [uv](https://docs.astral.sh/uv/), which fetches the right Python and the
  packages on first run. A `run.bat` that installs it for you is planned
  but not written yet.
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

1. **Reads the videos, once.** The first time a participant is opened, a
   progress bar shows while the frame timestamps of every video are read.
   From the RDM this takes one to two minutes. The result is saved, so
   later starts of the app do not read the videos again. The data summary
   says when they were read, and has a "Read the videos again" link for
   the rare case that the source files have changed.
2. **Shows the data summary**: number of videos, recorded time, frame rate, a
   timeline of task and unlabelled video, problems found in the files, gaps,
   and the list of tasks.
3. **Generates the clips.** "Generate clips" chooses up to 500 random,
   non-overlapping 1 s windows (both numbers are set in `study.toml`), 70% of
   them from task video and 30% from unlabelled video (`task_share` in the
   same file), and cuts each into an MP4 clip, showing
   progress. If the app is closed part-way, it carries on from the first
   missing clip next time. When all clips are cut, the page lists every clip
   with its start time, says that no two clips share a frame, and shows an
   "Annotate clips" button to go on to labelling.

   Not every window can be chosen. The recorder sometimes stamped frames
   late, which shows in the timestamps as a pause followed by repeated
   values. A window containing a repeated timestamp, or a step of more than
   0.1 s between frames, is never sampled, so that every clip's times can be
   trusted when clips are later lined up with sensor data. The summary page
   says what share of windows this leaves out.

4. **Asks who you are**, once the clips are ready and not before, and
   remembers it on this computer.
5. **Shows the clips one at a time for labelling**, in an order that is
   shuffled differently for each rater.

## Labelling clips

Each clip plays in a loop. Under it are the five labels, numbered 1 to 5.

- **To label a clip, hold Shift and press its number, or hold Shift and click
  it.** The next clip then appears.
- A number key or a click *without* Shift does nothing. This is on purpose,
  so that a slip of the hand is never saved as a label. The labels light up
  while Shift is down.
- Use the number keys in the top row of the keyboard, not the number pad.
- **Backspace** shows the clip before, with the label you gave it. Label it
  again to change it.
- You can stop at any time. Each label is saved the moment you give it, and
  the app carries on from the first unlabelled clip next time.

When every clip is labelled, the app shows how many clips got each label and
where your file is.

## Finding your way around

The title bar has three links.

- **Data summary**: what was recorded for the participant.
- **Annotation summary**: how many clips you have labelled, the count of
  each label, and where your file is. The button to start or continue
  annotating appears here once every clip has been generated.
- **Docs**: how the method works and what to watch for. A contents page
  lists the pages in reading order: how clips are made, four pages on the
  late timestamps (the problem, what this participant's timestamps show, the
  rule the app uses with the points for and against it, and what is still
  open), and what to keep in mind when reading the results. Each page lists
  its sections on the left and links to the previous and next page at the
  top and bottom. Diagrams marked "Made-up example" are illustrations;
  charts marked "Measured" are drawn from the participant's own timestamp
  files. The docs change nothing about which clips are chosen.

There are no links for generating clips or annotating. Clicking the app's
name opens whichever of those the app is ready for.

## Which participants are listed

A participant is a folder named `P` plus digits in the source folder, with its
videos directly in a `Video` folder. Participants whose `Video` folder is
split into session subfolders are not offered for now.

## Where things are stored

```
<source>/Pxx/Video/*.avi, *.vidt, experiment_details.json     source videos (read only)

data4annotation/<subject>/
    recording.json.gz       what was read from the source videos, and when
    segments.csv            the sampled windows
    design.toml             copy of the settings they were drawn with
    clips/seg_0001.mp4 ...  the 1 s clips
    generation_time.json    time spent generating so far, over every run
    <subject>_<rater>_annotations.csv   one file per rater
```

The annotation file gets one row each time a clip is labelled: `segment_id`,
`label`, `rater`, `annotated_at`. If a clip is labelled again, a new row is
added, and the last row for a clip is the one that counts.

`data4annotation/` and `local.toml` are never committed to git.

`segments.csv` has one row per clip: `segment_id`, `video_file`,
`start_frame`, `end_frame` (inclusive), `start_time`, `end_time` (timestamps
of the first and last frame, local time), and `task` (empty for unlabelled
video).

## Starting afresh

To throw away a participant's clips and begin again (for example after the
software or `study.toml` has changed), stop the app and run:

```
uv run python reset.py
```

It lists what it will do and asks you to type the participant's name before
doing anything.

- The clips, `segments.csv` and `design.toml` are deleted.
- Annotation files are **not** deleted. They are moved to
  `data4annotation/_archive/`, in a folder named with the date and time.
- What was read from the source videos is kept, so the data summary does
  not have to be read again. Add `--recording` to clear that too.
- Your rater name is kept. Add `--rater` to be asked for it again.
- `uv run python reset.py Pxx` resets another participant's folder.

## Settings

`study.toml` holds the study design: the category labels, the number of
clips, the clip length, the sampling method and its random seed, the
timestamp rule, and the clip quality. Every rater must use the same `study.toml`. If it changes after
clips have been generated, the app stops and says what differs, because old
and new clips must not be mixed. Run `reset.py` (above) to clear the old ones.

## For developers

- Run everything through `uv`: `uv run python app.py`.
- Tests: `uv run python -m unittest discover -s tests -t .`
- Code layout and conventions: `PLAN.md` section 7 and `CLAUDE.md`.
