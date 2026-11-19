# UQ Parkour Annotator: build plan

Status: build in progress. See section 9 for what is done.

## ICORR (temporary)

This section is temporary. It describes what is being built now so that the
annotation for the ICORR paper can be done. A final version of the way
clips are shared and handled will be designed after brainstorming with the
group, and will replace this section.

Where this section and the rest of the plan disagree, this section is what
applies to the ICORR work.

### What the ICORR work uses

- **One participant**, the one whose timestamps are least affected by the
  late-timestamp problem (see `CLAUDE.md`, "Parked problems").
- **The current settings in `study.toml`**: 1 s clips, the timestamp rule,
  and 70% of clips from task video. The number of clips is set low while
  the app is being tested and will be raised for the real set.
- **Raters are investigators on the study.** Most are clinicians, so the
  app must do the work: nothing is to be done by hand.

### The shared folder on the RDM

Clips are generated once, by one person, and every rater labels the same
files. Clips and ratings are shared through one folder on the RDM, inside
the study folder:

```
<source>/ICORR27 Annotate/
    clips/
        <Pxx>/
            <Pxx>_clips.zip        everything a rater needs, in one file
            <Pxx>_clips_id.txt     a short code that identifies the set
    ratings/
        <Pxx>_<rater>_annotations_<YYYYMMDD-HHMMSS>.csv
```

- The folder has a name of its own because the procedure for cutting clips
  will change. Clips made by a later procedure go in a folder with a
  different name, so the two are never mixed. The name is the setting
  `folder` under `[share]` in `study.toml`. That setting is not part of the
  design that clips are checked against, so changing it does not make
  existing clips count as mismatched.
- **The zip** holds the clips, `segments.csv`, `design.toml` and the saved
  reading of the videos (`recording.json.gz`). No label file ever goes in
  it. It is written under a temporary name and renamed when complete, on
  upload and on download, so a half-copied zip is never taken for a whole
  one.
- **The set code** is made from `segments.csv` and `design.toml`. It lets
  the app tell, without downloading the zip, whether the clips on a
  computer are the shared ones.

### What the app does on start

It checks in this order:

1. **No setup yet?** Ask where the study folder is (below).
2. **Are the clips on this computer?** Go to the annotator: the rater's
   name, then labelling.
3. **If not, is there a zip for the participant on the RDM?** Download and
   unpack it, with a progress bar, then go to the annotator.
4. **If neither**, carry on with the usual flow: read the videos, show the
   data summary, and generate the clips.

If the study folder cannot be reached (VPN off, drive not mapped), the app
says so and asks the person to connect and reload. It never guesses.

### First-time setup

One page, in place of typing into `local.toml`:

- It asks for the study folder (the RDM drive, or a copy) and checks that it
  exists. It gives short instructions for connecting; these do not contain
  the RDM address, which is never written in a committed file.
- **Participant.** If the shared folder holds clips for exactly one
  participant, the app takes that one. If it holds several, the person
  picks from them. If it holds none, the person picks from the participant
  folders found in the study folder (this is the person who will generate).

### Uploading clips

- When clips have been generated on a computer and the RDM has no zip for
  that participant, the generate page shows an **"Upload to RDM"** button.
- Pressing it packs the zip straight onto the RDM, with a progress bar.
- If a zip for the participant already exists, local clips are never
  uploaded: the button is not shown, and the upload checks once more just
  before writing.
- The button is not offered while the `clip_limit` test setting is on,
  since that would share only part of a set.

### Downloading clips

- The settings inside the zip must equal the rater's `study.toml` (apart
  from `[share]`). This is checked before the download. If they differ,
  the app says what differs and does not download.
- After unpacking, the saved reading of the videos is pointed at the
  rater's own study folder, so the data summary opens without reading the
  videos again, whatever drive letter the rater uses.

### Rater names

- **While typing**, the sign-in page says under the box whether the name is
  free. A name is taken if `ratings/` already has a file from it for this
  participant. While it is taken, the Start button is off. There is no
  pop-up. If the RDM cannot be reached, the page says the name could not be
  checked and lets the rater go on.
- **At the first upload** of ratings from a computer, the name is checked
  again. If it clashes, the app adds a random three-digit number (`ann`
  becomes `ann_417`) and tells the rater the name their ratings were
  uploaded under.
- The name used for uploads is remembered in `local.toml` as `uploaded_as`.
  Later uploads from the same computer use it without checking and count as
  the same rater. So **a rater must stay on one computer.**

### Uploading ratings

- When a rater has labelled every clip, the app copies their label file to
  `ratings/` by itself. Nothing is pressed.
- The copy is named as on the rater's computer, with the upload name and
  the date and time added: `<Pxx>_<name>_annotations_<YYYYMMDD-HHMMSS>.csv`.
  Inside the copy, the `rater` column carries the upload name, so the file
  name and its rows agree. The file on the rater's computer is not changed.
- An upload never replaces an earlier one. **The most recent file for a
  rater is the one that counts.** When an earlier one exists, the page says
  so, with its date, and that the new one is now the most recent.
- If nothing has changed since the last upload, nothing is uploaded again.
- If a rater changes a label after finishing, the next visit to the
  finished page uploads a new file.
- **Ratings are held back**, and the page says why, in two cases: the RDM
  has no zip for the participant yet (the clips must be shared first), or
  the clips on this computer are not the shared set (the person should run
  a reset and get the shared clips).

### When the RDM cannot be reached

The same rule everywhere (downloading clips, uploading clips, uploading
ratings, checking a name): the app says so in plain words, changes nothing,
and tries again the next time the page is opened. Ratings that could not be
uploaded stay safe on the rater's computer.

### Left out on purpose

- Any rule that a new set of clips must avoid footage used by an earlier
  set. The unique folder name keeps sets apart instead.
- A marker to stop two raters starting with the same name at the same
  moment. The three-digit number at upload covers it.

### Not settled

- Ethics approval probably does not cover copies of the clips on raters'
  own computers. This is set aside for now, because the raters are all
  investigators on the study. It must be settled before anyone else rates.
- The late timestamps, and lining clips up with the sensor data, are
  parked (see `CLAUDE.md`).
## 1. User flow

### One-time setup

The first time the app runs on a machine, it asks where the data is and
writes the answers to `local.toml`. It does not ask again.

The order of the whole flow is fixed:

1. Where is the data? (this setup)
2. Read it and show the summary.
3. Click to generate the clips.
4. Only then the annotator part: the rater's name, then labelling.

The rater's name is never asked before the clips are ready.

For the ICORR work the setup is one page that asks for the study folder and
settles the participant (see "First-time setup" in the ICORR section). The
fuller sequence in the table below is the original design and has not been
built; it will be revisited with the rest of the sharing design.

| Step | Screen | What happens |
|---|---|---|
| 1 | Data source | "Do you have the source videos, or ready-made 1 s clips?" |
| 2a | Source folder (source videos only) | Shows short instructions for mapping the RDM drive in Windows. User pastes the folder path, which can be the mapped RDM drive or a local copy. The app checks it exists. |
| 2b | (ready-made clips) | No path is asked for. |
| 3 | Choose subject | Lists subjects from the source folder (route a) or from `data4annotation/` (route b). From the source folder, only folders named `P` plus digits whose videos sit directly in `Video/` are listed. Subjects that already have clips are marked "clips ready". |

`local.toml` then holds the data source, the source folder (route a only)
and the subject. The rater's name is added later, at sign-in (see "Every
start"). One rater per computer. To change the setup,
edit or delete `local.toml` by hand; there is no reset link for now.

### Every start

After setup, the app checks the subject's folder in `data4annotation/` and
opens on the matching page:

| State of the clips | Page shown |
|---|---|
| Settings mismatch | Mismatch message in place of generating and annotating. The data summary, the annotation summary (without its button) and the docs can still be opened. |
| None generated | Summary (section 3) with a button to start generating, then progress. Source-video route only. |
| Partly generated | Progress page. Generation resumes automatically from the first missing clip. |
| Complete, no rater name yet | Sign in: the rater types their name, once. It is cleaned into a file-safe form and saved in `local.toml`. |
| Complete | Annotation, at the rater's next unlabelled clip. |
| Complete and all labelled | Done: label counts and the path of the annotation file. |

The same page opens when the app's name in the title bar is clicked. The
title bar itself links only to the two summaries and the docs (section 3a).

**Settings mismatch.** Each clip folder holds `design.toml`, a copy of the
settings it was made with. If it differs from the current `study.toml` in any
way (sampling settings, clip settings or labels), the app stops. The message
lists the settings that differ, names the folder to delete by hand, and warns
that annotation files are in that folder and should be moved out first. The
app never deletes or overwrites clips itself.

**Folder names.** Clips are matched to source videos by subject folder name.
A renamed clip folder is treated as no clips.

A rater who chose the source-video route but already has complete clips for
the subject goes straight to annotation; nothing is regenerated.

Output for a subject, shared by all raters:

```
data4annotation/<subject>/
    recording.json.gz                   what was read from the source videos, and when
    segments.csv                        the sampled windows
    design.toml                         copy of the settings and seed used
    clips/seg_0001.mp4 ...
    generation_time.json                time spent generating so far, over every run
    <subject>_<rater>_annotations.csv   one file per rater
```

If this folder is copied to a rater's machine with the clips already in it,
that rater needs no access to the source videos.

### Starting afresh

`reset.py` clears a subject so that clips can be generated and labelled
again, for example after the software or `study.toml` has changed. It is
run by hand, with the app stopped: `uv run python reset.py`.

| File in `data4annotation/<subject>/` | What a reset does |
|---|---|
| `clips/`, `segments.csv`, `design.toml` | Deleted. They can be made again. |
| `<subject>_<rater>_annotations.csv` | Never deleted. Moved to `data4annotation/_archive/<subject>_<date>-<time>/`. |
| `recording.json.gz` | Kept, unless `--recording` is given. |

The rater's name in `local.toml` is kept unless `--rater` is given. The
program lists what it will do and asks for the subject's name to be typed
before doing it (`--yes` skips the question). A subject other than the one
in `local.toml` can be named: `uv run python reset.py Pxx`. The app itself
still never deletes clips or labels.

## 2. Source data (as found on the RDM)

The source folder holds one folder per participant, named `P` plus digits,
among other folders that the app ignores.

```
<source>/Pxx/Video/experiment_details.json    subject name, task list, file-to-task mapping
<source>/Pxx/Video/{task_NNN|unlabelled_x}_<unix-microseconds>.avi
<source>/Pxx/Video/<same name>.vidt           one timestamp per frame
```

- `.vidt`: 8 bytes per frame, temporenc format, microsecond precision, local
  Brisbane time (UTC+10).
- The `.avi` header gives a nominal 30 frames per second. The measured rate
  differs from file to file (24 to 32 fps in one participant), so frame times
  always come from the `.vidt` file.
- A participant has about 180 to 200 videos, half task and half unlabelled.
- **Session subfolders.** Some participants have their videos in one or two
  session subfolders under `Video/` instead of directly in it. For now these
  participants are not offered in the subject list (see decision X).
- **Slow drive.** Over the VPN, opening any file on the RDM takes one to two
  seconds. The app therefore lists a folder once and reads 32 files at a
  time. Reading one participant takes one to two minutes; the page shows a
  progress bar meanwhile.
- **Read once.** What was read (every video's task, frame count, frame rate
  and timestamps) is saved in `data4annotation/<subject>/recording.json.gz`
  with the time of reading and the source folder. Every later start of the
  app uses that file and does not touch the source videos until clips are
  cut. The file is ignored if it is damaged or was read from a different
  folder. The data summary says when the videos were read and has a "Read
  the videos again" link, which is the only thing that replaces the file.

The early test recording in `data/221125_SK_Test` has an older layout
(a `videos/` subfolder, 10 fps) and is no longer read by the app.

## 3. Data summary report

- Number of videos, split into task and unlabelled
- Total recorded time, and time per group
- Recording start and end, and overall span
- Frame rate: median, minimum, maximum
- Gaps between consecutive files longer than 1 s
- Problems: videos listed in `experiment_details.json` but absent, video
  without `.vidt`, frame count different from timestamp count, timestamps
  going backwards, filename time more than 1 s from the first frame.
- The share of possible windows left out of sampling by the timestamp rule
  (section 4), and how many tasks are left with no usable window.
- The first time, while the videos are being read, the page shows a
  progress bar and the video being read, then reloads into the summary.
  After that the summary opens at once from the saved read (section 2),
  and says when the videos were read.
- Task table: task number, name, duration, number of repeats
- A timeline strip showing task, unlabelled and gap periods
- Number of 1 s windows available for sampling: those that pass the
  timestamp rule and fit without overlapping

## 3a. Title bar, annotation summary and docs

Addresses: `/` home, `/signin`, `/summary` (and `/summary/reread`), `/generate`, `/annotate`,
`/done`, `/annotations`, `/docs` and `/docs/<slug>`.

**Title bar.** Three links only: *Data summary*, *Annotation summary* and
*Docs*. There are no links for the steps of normal use (generating clips,
annotating). Those are reached through the app itself: the home page opens
the page that matches the state of the clips (section 1), and pages offer
the next step as a button when it is available.

**Annotation summary** (`/annotations`). For the signed-in rater: how many
clips there are, how many are labelled, the count of each label, and where
the annotation file is. It shows a "Start annotating" or "Continue
annotating" button only when every clip has been generated and the settings
match.

**Docs** (`/docs`). Everything about how the method works and what to watch
for lives here, not in the title bar. The contents page lists the pages in
reading order, in groups. `parkour/docs.py` is the one list that decides the
groups, the order, the addresses (`/docs/<slug>`) and "previous" and "next".

| Group | Page | Address | Needs the videos read |
|---|---|---|---|
| How the app works | From videos to clips (starts with the folder layout: source, output and shared folders, and names the file each step reads and writes) | `/docs/clips` | No |
| The timestamp problem | Some timestamps are late | `/docs/timing-problem` | No |
| | What this participant's timestamps show | `/docs/timing-evidence` | Yes |
| | The rule the app uses | `/docs/timing-rule` | Yes |
| | What the rule does not settle | `/docs/timing-open` | No |
| Using the results | What to keep in mind | `/docs/interpreting` | No |

- Every docs page has the same frame (`templates/docs/base.html`): links to
  the previous and next page at the top and at the bottom, and the page's
  sections listed in a column on the left. `app.js` builds that list from
  the page's `h2` headings and marks the section being read.
- The docs pages are the only explanation of the method. There is no
  separate text copy (`docs/HOW_IT_WORKS.md` was removed), so there is
  nothing to keep in step with them except the code.
- A docs page never writes out a value that is set in `study.toml` (number
  of clips, clip length, gap limit, number of labels). It prints the value
  handed to it by `docs.settings()`, so a change to `study.toml` shows on
  every page.
- **Lateness** is measured in `lag.py`: a frame was filmed no later than its
  own stamp, and no later than any later frame's stamp minus the frames
  between at the nominal frame rate (looking 60 s ahead). The stamp minus
  that limit is the least the stamp can be late. It is a measurement only.
- A frame is **removed** if no allowed window can contain it, and **kept**
  otherwise.
- Pictures marked "Made-up example" come from `timing_sketch.py`, a small
  model of the recorder. Pictures marked "Measured" come from
  `timing_report.py`. Orange always means a late stamp or a removed frame.
- The figures for the six participants on the rule page are fixed text from
  the survey of 19 November 2026 (see `CLAUDE.md`); they name no participant.
- Charts are plain SVG and HTML drawn by the templates. Pointing at a chart
  shows the value under the pointer in a line below it.

## 4. Sampling

- A window is a fixed number of consecutive frames lying wholly inside one
  video file: `window_seconds` from `study.toml` times the video's nominal
  frame rate, so 30 frames for 1 s at 30 fps. Every clip plays for exactly
  `window_seconds`.
- **Timestamp rule.** The recorder sometimes stamps frames late, by up to
  several seconds; a late stretch shows as a pause in the stamps followed by
  repeated stamps. A window is allowed only if no frame in it repeats the
  previous frame's stamp and no step between its frames is longer than
  `max_step_seconds` in `study.toml` (0.1 s). Windows that fail are never
  sampled; nothing is corrected. The rule is in `timing.py`, and the
  background is in `CLAUDE.md` under "Parked problems".
- A window may start at any frame that leaves it allowed (frame 96, say,
  which is 3.2 s in). There is no fixed 0 s, 1 s, 2 s grid.
- **Share from task video.** `task_share` in `study.toml` (0.7) is the share
  of clips taken from task video; the rest come from unlabelled video. With
  500 clips that is 350 and 150. The two kinds are sampled separately. If
  one kind cannot supply its number, fewer clips are made; the other kind
  does not make up the difference, and the summary page says so. Without
  `task_share`, clips are drawn from all videos together.
- Within each kind, windows are drawn one at a time, with every allowed start
  in every video equally likely, so longer files contribute proportionally
  more.
- Because task video is a small part of a recording (about a seventh in the
  participant used so far), the clips over-represent it. Figures for the
  whole session need the two kinds weighted by their share of the recording.
- Windows do not overlap one another: a draw that would share a frame with a
  window already chosen is discarded and drawn again.
- `start_time` and `end_time` in `segments.csv` are the timestamps of the
  window's first and last frame, so they are one frame short of
  `window_seconds` apart.
- Up to 500 per subject. Fewer if the subject has less usable footage.
- The random seed for choosing windows is fixed in `study.toml`, so every
  rater gets the same windows and clips for a given subject (see decision A).

`segments.csv` columns: `segment_id, video_file, start_frame, end_frame,
start_time, end_time, task`.

## 5. Clip extraction

- ffmpeg cuts each window by frame number and re-encodes to H.264 MP4, since
  browsers cannot play XVID. It seeks straight to the first frame instead of
  decoding from the start of the file; this was checked to return exactly the
  same frames, about 50 times faster on the longest video.
- Audio is dropped.
- ffmpeg comes from the `imageio-ffmpeg` package, so nothing is installed
  system-wide.
- Extraction runs in a background thread. The page polls for progress.
- **Signs of life.** A clip can take 10 to 30 seconds to cut, and nothing
  else on the page changes meanwhile. So the status text has a small dot in
  front of it that pulses while the app reports it is working, and the total
  time beside the heading (next point) ticks up every second. Both come from
  the app's answers, so they stop when the app stops; the text then says
  contact was lost.
- **A slow clip.** The status line says nothing about how long the current
  clip is taking, unless it is taking much longer than usual. Then it adds
  "· this one is slow, 2 min 16 s so far". A clip counts as slow once it has
  taken at least a minute and more than three times the average clip so far;
  the first clip, with nothing to compare with, after two minutes. Reading
  the videos and choosing the clips are never called slow.
- **Time spent.** Beside the "Progress" heading, in thin text, the page shows
  the time spent generating in all and a rough guess of the time left
  ("12 min 40 s so far · about 19 min left"); when finished, "took 1 h 52 min
  in all". The total covers everything the job does (reading the videos if
  needed, choosing the clips, cutting) and is cumulative over every run: it
  is saved to `generation_time.json` in the clip folder after each step, so
  it carries on after the app is stopped and started. Time while the app is
  closed is not counted, nor the time on a clip that was interrupted and has
  to be cut again. The guess of the time left uses the average time per clip
  so far, so it is available straight after a restart.
- Under the progress bar, the status text sits on the left. At the right
  edge, on the same row, a small live bar splits the clips cut so far into
  task video and unlabelled video. It is a quarter of the progress bar's
  width, thinner and paler than it, with the count and percentage of each
  kind above its ends and a thin mark where the split is planned to end up.
  Clips are cut in time order, so the split moves about before it settles on
  the mark. On a narrow screen the small bar drops below the text.
- When every clip is cut, the page reloads once and then shows two more
  things. An "Annotate clips" button, which goes on to the rest of the
  workflow (the rater's name the first time, then labelling). And a list of
  all the clips in several columns, each with its clip number and the time
  its first frame was recorded, in time order, so it can be seen that no
  clip was generated twice. Above the list the page states the check made on
  frame numbers: that no two clips share a frame, which two clips come
  closest and by how many frames, and the smallest gap between two start
  times.
- `segments.csv` and `design.toml` are written before any cutting starts. A
  resumed run reuses that list and does not draw new windows.
- Each clip is written under a temporary name and renamed when finished, so a
  clip with its final name is always complete.
- Resume is automatic: on start, the app cuts only the clips that are missing.

## 6. Annotation

- **Sign-in.** Once the clips are ready, and never before, if `local.toml`
  has no rater yet the app asks for the rater's
  name once, cleans it into a file-safe form and saves it there.
- The clip loops, muted. Five labels, keys `1`–`5`: the four FAABOS
  categories and "Unknown / arm out of view".
- **Shift must be held to label**, with a number key or with a click. A key
  or a click without Shift saves nothing and the page says why, so a slip of
  the hand is never saved as a label. While Shift is down the labels light up.
- `Backspace` (no Shift) shows the clip before, with the label it was given.
  Labelling it again changes the label. A rater can look back but not ahead.
- The page shows only the clip, its place ("Clip 8 of 500") and a progress
  bar. It does not show the task or the video file, so the rater is not led.
- **A clip from an earlier set must never be shown.** Clip numbers are
  reused every time clips are generated, so the same number can mean a
  different clip. Two things guard against a browser showing an old one. The
  address of every clip carries a short code for the set
  (`/clips/<code>/seg_0007.mp4`); the code is made from the list of clips,
  the settings and the moment the list was written, so it changes whenever
  clips are generated again, and an address with an old code is refused. And
  the browser is told to store nothing (`Cache-Control: no-store`), with no
  fetching of the next clip in advance.
- Presentation order is shuffled per rater, seeded from the rater's name.
- Each label is appended to the CSV and written to disk at once. Columns:
  `segment_id, label, rater, annotated_at`. A relabel adds a row; the latest
  row for a clip counts.
- On reopening, the app goes to the first clip without a label.
- When every clip has a label, a page shows the count per label and where
  the file is.
- The annotation summary (section 3a) shows the same counts at any time,
  with progress, and is the only place outside the home page that offers
  annotation.

## 7. Code layout

```
run.bat             (not written yet) downloads uv on first run, then starts the server and opens the browser
pyproject.toml      pinned Python version and packages
uv.lock             exact package versions, written by uv
.python-version     the Python version uv downloads
tests/              unit tests (standard-library unittest, no participant data)
study.toml          every design choice: labels, segment count, window length, seed, sampling strategy, timestamp rule, clip quality
local.toml          data source, source-video folder, subject and rater name; written by the app (ignored by git). Optional `clip_limit` for testing with a few clips
app.py              Flask routes only; no logic
reset.py            run by hand: clear a subject's clips and set its labels aside, to start afresh
parkour/
    config.py       load study.toml and local.toml
    vidt.py         decode .vidt timestamp files
    dataset.py      find subjects and videos; frame times per video; the only module that knows the folder layout
    loader.py       read a subject's videos once, in the background, with progress; reuse the saved result
    recording_store.py  save what was read from a subject's videos, and load it on later starts
    share.py        the shared folder on the RDM: clips as one zip, up and down, and the set id
    shared_ratings.py  ratings in the shared folder: names in use, uploading with date and time
    transfer.py     run an upload or download in the background, with progress
    timing.py       which windows have trustworthy timestamps
    lag.py          measure how late each timestamp is (for the docs pages only)
    timing_report.py  numbers and series for the docs pages on timestamps, from a subject's videos
    timing_sketch.py  a made-up recording for the diagrams on those pages
    chart.py        axis and tick helpers for charts drawn as SVG
    docs.py         the list of docs pages: groups, order and addresses; the study.toml values they quote
    summary.py      build the data summary
    sampling/       one file per sampling strategy, chosen by name in study.toml
    clipset.py      a subject's clip folder: segments.csv, design.toml, which clips exist
    extract.py      cut clips with ffmpeg in a background thread; progress tracking
    fmt.py          format values for display
    devreload.py    developer mode (`app.py --dev`): tell the open page when the app's files change
    annotations.py  a rater's clip order; read and append the annotation CSV
    reset.py        what a reset removes, keeps and sets aside
templates/          base, setup, unreachable, transfer, signin, loading, summary, generate, mismatch,
                    annotate, done, annotation_summary
templates/docs/     the docs pages: shared frame, contents, figures, one file per page
static/             style.css, app.js, fonts/
data4annotation/    clips and annotations (ignored by git); _archive/ holds labels set aside by a reset
```

Source videos are read from the folder set in `local.toml`: the mapped RDM
drive or a local copy. Clips and annotations are written to
`data4annotation/` inside the repo folder.

Third-party packages: Flask and imageio-ffmpeg. Everything else is the
standard library.

## 8. Look and feel

A button whose form makes the app wait on the network drive (the Continue
button on the set-up page) carries `data-busy`. Once pressed it shows a
spinner and says what is happening, and cannot be pressed twice, until the
next page arrives.

White page, hairline rules, compact spacing. Colours come from the UQ brand
palette: purple (`#51247A`) for the title bar, titles and task video, and the
UQ greys for rules and unlabelled video. Typefaces are UQ's web fonts:
Montserrat for headings and figures, Roboto for text. Both are bundled in
`static/fonts/` with their licences, so the app needs no internet after the
first run. The title bar stays at the top of the window while scrolling. Pages
that are read (setup, messages) sit in a narrow centred column; pages that
show data (summaries, docs) use the window width, up to about 1230 px. A
docs page has its sections in a column on the left that stays in view.
Orange is used for one thing only: a late timestamp or a removed frame, in
the docs figures. No front-end framework and no build step: plain HTML, one
stylesheet, one small script.

## 9. Build order

Everything is run through `uv` from the first step (`uv run ...`), never
through another Python, so development uses the same pinned Python and
packages the raters will get. `uv.lock` is committed.

1. `pyproject.toml`, `study.toml`, `config.py` (done)
2. `vidt.py`, `dataset.py` (done; first checked against the test recording,
   then moved to the RDM layout and checked against one participant)
3. `loader.py`, `summary.py` and their pages (done; needs a hand-written
   `local.toml` until the setup pages exist)
4. `sampling/`, `timing.py`, `clipset.py`, `extract.py`, generate page with
   progress, and the settings-mismatch page (done). Cutting from the RDM over
   the VPN was timed at about 27 s per clip, so 500 clips take nearly four
   hours. Until that is sped up (cutting several clips at once is the
   obvious way), `clip_limit` in `local.toml` makes the app work with only
   the first few clips for testing.
4a. Docs pages: `docs.py`, `lag.py`, `timing_report.py`,
   `timing_sketch.py`, `chart.py`, the contents page and six pages (done;
   checked on one participant). Annotation summary page (done).
5. `annotations.py`, sign-in, annotate and done pages (done; checked on 25
   clips of one participant, including the Shift rule in a browser)
5a. ICORR sharing: share.py, shared_ratings.py, 	ransfer.py; the setup,
   download, upload and "not reachable" pages; the name check at sign-in;
   ratings uploaded from the finished page (done; checked against a folder
   standing in for the RDM, not yet against the RDM itself)
6. Styling pass
7. End-to-end run on the sample subject; `run.bat` (not written yet);
   rater instructions
8. First-run test from a fresh copy of the repo with no `.venv/` or
   `.runtime/`, ideally on a computer that has never run the app

## 10. Decisions

Many of these will change once the study design for the full dataset is
final. Design choices therefore live in one settings file (`study.toml`), not
in the code.

### Decided

| | Question | Decision |
|---|---|---|
| A | Should both raters label the same windows? | Yes. The seed for choosing windows is fixed, so all raters get the same clips for a subject. The order in which clips are shown is shuffled with a seed from the rater's name. |
| B | The category labels | FAABOS: Task-related functional, Non-task-related functional, Non-functional, No activity/movement. Wording taken from the literature; to be checked against the study protocol. |
| O | Fifth option | Yes: "Unknown / arm out of view". |
| E | Number of windows | Up to 500 per subject. |
| F | Where the source videos are | On the RDM, read through the mapped drive. The path is set in `local.toml`. Clips and annotations stay in `data4annotation/` in the repo folder. |
| M | How `uv` arrives | Downloaded by `run.bat` on first run. Not committed. |
| N | GitHub repo | Private. Access is given to the appropriate people. |
| P | Rater machines | Most likely 64-bit Windows. `run.bat` is Windows only. |
| C | Which videos to sample from | All video, task and unlabelled, uniform over recorded time. |
| D | What the rater sees | The 1 s clip only, looping. No context clip. |
| G | Web server | Flask. |
| H | How raters start the app | Download the repo from GitHub and double-click `run.bat`. It uses `uv` to fetch Python and the packages on first run, so the first run needs internet. No PyInstaller `.exe`. |
| I | Third-party packages | Flask and imageio-ffmpeg only. No h5py. Sensor files are not used. |
| J | Storage | CSV only. No database. |
| K | Participant data and GitHub | Never committed, and that includes subject names and the RDM path. `data/`, `data4annotation/`, `private/`, `local.toml` and the downloaded runtime are ignored by git. |
| Q | Page order | One-time setup: data source, source folder (if source videos), subject. Then, on every start, the page that matches the state of the clips. The rater's name is not part of setup: annotation only becomes relevant once the clips exist, so the name is asked then, once. See section 1. |
| AB | What the title bar links to | Data summary, Annotation summary and Docs only. Generating and annotating have no link; the app opens them when they are available. Everything that explains the method or its problems is a docs page. See section 3a. |
| R | Where the setup values are kept | All in `local.toml`, written by the app once. No separate rater file. Changed by hand; no reset link for now. |
| T | Raters with ready-made clips and no RDM access | Handled by the first setup question. The clips route asks for no path and goes straight to annotation. |
| U | Interrupted generation | Resumes automatically from the first missing clip, reusing the saved window list. |
| V | Clips made with different settings | Any difference from `study.toml`, labels included, stops the app with a message. The clips are cleared with `reset.py`, run by hand; the app never deletes clips. |
| AC | Starting afresh | `reset.py` deletes a subject's clips, `segments.csv` and `design.toml`, and moves annotation files to `data4annotation/_archive/`. Labels are never deleted. |
| W | Mapping the RDM drive | Done by the rater in Windows. The setup page shows short instructions. |
| X | Participants with session subfolders | Left out of the subject list for now. Only participants whose videos sit directly in `Video/`, with no subfolders there, are offered. |
| Y | Length of a clip | A fixed number of frames per video: `window_seconds` times the nominal frame rate. Every clip plays for the same time. |
| Z | Late frame timestamps | Quickest fix for now: windows containing a repeated stamp or a step over 0.1 s are never sampled. No times are corrected. A proper fix, and syncing to the sensors, are parked (see `CLAUDE.md`). |
| AA | Participant for the first paper | One participant, the one whose timestamps are least affected. The subject in use is set in `local.toml`. |
| AB | Mix of task and unlabelled clips | 70% of clips from task video and 30% from unlabelled video, for now (`task_share` in `study.toml`). The two kinds are sampled separately. |
| L | Guarding against design changes | Settings in `study.toml`; sampling strategies swappable by name; `dataset.py` is the only module that knows the folder layout; each generated set saves a copy of the settings and seed it was made with. |

### Still open

None at present.
