# UQ Parkour Annotator: build plan

Status: build in progress. See section 9 for what is done.

## 1. User flow

### One-time setup

The first time the app runs on a machine, it asks where the data is and
writes the answers to `local.toml`. It does not ask again.

| Step | Screen | What happens |
|---|---|---|
| 1 | Data source | "Do you have the source videos, or ready-made 1 s clips?" |
| 2a | Source folder (source videos only) | Shows short instructions for mapping the RDM drive in Windows. User pastes the folder path, which can be the mapped RDM drive or a local copy. The app checks it exists. |
| 2b | (ready-made clips) | No path is asked for. |
| 3 | Choose subject | Lists subjects from the source folder (route a) or from `data4annotation/` (route b). From the source folder, only folders named `P` plus digits whose videos sit directly in `Video/` are listed. Subjects that already have clips are marked "clips ready". |
| 4 | Sign in | Rater types their name. It is cleaned into a file-safe form. |

`local.toml` then holds the data source, the source folder (route a only),
the subject and the rater's name. One rater per computer. To change the setup,
edit or delete `local.toml` by hand; there is no reset link for now.

### Every start

After setup, the app checks the subject's folder in `data4annotation/` and
opens on the matching page:

| State of the clips | Page shown |
|---|---|
| Settings mismatch | Mismatch message only. Nothing else is available. |
| None generated | Summary (section 3) with a button to start generating, then progress. Source-video route only. |
| Partly generated | Progress page. Generation resumes automatically from the first missing clip. |
| Complete | Annotation, at the rater's next unlabelled clip. |
| Complete and all labelled | Done: label counts and the path of the annotation file. |

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
    segments.csv                        the sampled windows
    design.toml                         copy of the settings and seed used
    clips/seg_0001.mp4 ...
    <subject>_<rater>_annotations.csv   one file per rater
```

If this folder is copied to a rater's machine with the clips already in it,
that rater needs no access to the source videos.

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
  seconds. The app therefore lists a folder once, reads 32 files at a time,
  and keeps what it read in memory until it stops. Reading one participant
  takes about a minute; the page shows a progress bar meanwhile.

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
- While the videos are being read, the page shows a progress bar and the
  video being read, then reloads into the summary.
- Task table: task number, name, duration, number of repeats
- A timeline strip showing task, unlabelled and gap periods
- Number of 1 s windows available for sampling: those that pass the
  timestamp rule and fit without overlapping

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
- Windows are drawn one at a time, with every allowed start in every video
  equally likely, so longer files contribute proportionally more.
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
- `segments.csv` and `design.toml` are written before any cutting starts. A
  resumed run reuses that list and does not draw new windows.
- Each clip is written under a temporary name and renamed when finished, so a
  clip with its final name is always complete.
- Resume is automatic: on start, the app cuts only the clips that are missing.

## 6. Annotation

- The clip loops. Five buttons, keys `1`–`5`: the four FAABOS categories and
  "Unknown / arm out of view". `Backspace` returns to the previous clip.
- Presentation order is shuffled per rater, seeded from the rater's name.
- Each label is appended to the CSV and flushed immediately.
- On reopening, labelled clips are skipped.

## 7. Code layout

```
run.bat             downloads uv on first run, then starts the server and opens the browser
pyproject.toml      pinned Python version and packages
uv.lock             exact package versions, written by uv
.python-version     the Python version uv downloads
tests/              unit tests (standard-library unittest, no participant data)
study.toml          every design choice: labels, segment count, window length, seed, sampling strategy, timestamp rule, clip quality
local.toml          data source, source-video folder, subject and rater name; written by the app (ignored by git). Optional `clip_limit` for testing with a few clips
app.py              Flask routes only; no logic
parkour/
    config.py       load study.toml and local.toml
    vidt.py         decode .vidt timestamp files
    dataset.py      find subjects and videos; frame times per video; the only module that knows the folder layout
    loader.py       read a subject's videos in the background, with progress; keep the result in memory
    timing.py       which windows have trustworthy timestamps
    summary.py      build the data summary
    sampling/       one file per sampling strategy, chosen by name in study.toml
    clipset.py      a subject's clip folder: segments.csv, design.toml, which clips exist
    extract.py      cut clips with ffmpeg in a background thread; progress tracking
    fmt.py          format values for display
    annotations.py  read and append the annotation CSV
templates/          base, setup pages, loading, summary, generate, mismatch, annotate, done
static/             style.css, app.js
data4annotation/    clips and annotations (ignored by git)
```

Source videos are read from the folder set in `local.toml`: the mapped RDM
drive or a local copy. Clips and annotations are written to
`data4annotation/` inside the repo folder.

Third-party packages: Flask and imageio-ffmpeg. Everything else is the
standard library.

## 8. Look and feel

White page, hairline rules, compact spacing. Colours come from the UQ brand
palette: purple (`#51247A`) for the title bar, titles and task video, and the
UQ greys for rules and unlabelled video. Typefaces are UQ's web fonts:
Montserrat for headings and figures, Roboto for text. Both are bundled in
`static/fonts/` with their licences, so the app needs no internet after the
first run. The title bar stays at the top of the window while scrolling. Pages
that are read (setup, messages) sit in a narrow centred column; pages that
show data (summary) use the window width, up to about 1360 px. No front-end framework and no build step: plain
HTML, one stylesheet, one small script.

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
5. `annotations.py`, annotate page
6. Setup pages (data source, folder, subject, sign-in), styling pass
7. End-to-end run on the sample subject; `run.bat`; rater instructions
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
| Q | Page order | One-time setup: data source, source folder (if source videos), subject, rater name. Then, on every start, the page that matches the state of the clips. See section 1. |
| R | Where the setup values are kept | All in `local.toml`, written by the app once. No separate rater file. Changed by hand; no reset link for now. |
| T | Raters with ready-made clips and no RDM access | Handled by the first setup question. The clips route asks for no path and goes straight to annotation. |
| U | Interrupted generation | Resumes automatically from the first missing clip, reusing the saved window list. |
| V | Clips made with different settings | Any difference from `study.toml`, labels included, stops the app with a message. The folder is deleted by hand; the app never deletes clips. |
| W | Mapping the RDM drive | Done by the rater in Windows. The setup page shows short instructions. |
| X | Participants with session subfolders | Left out of the subject list for now. Only participants whose videos sit directly in `Video/`, with no subfolders there, are offered. |
| Y | Length of a clip | A fixed number of frames per video: `window_seconds` times the nominal frame rate. Every clip plays for the same time. |
| Z | Late frame timestamps | Quickest fix for now: windows containing a repeated stamp or a step over 0.1 s are never sampled. No times are corrected. A proper fix, and syncing to the sensors, are parked (see `CLAUDE.md`). |
| AA | Participant for the first paper | One participant, the one whose timestamps are least affected. The subject in use is set in `local.toml`. |
| L | Guarding against design changes | Settings in `study.toml`; sampling strategies swappable by name; `dataset.py` is the only module that knows the folder layout; each generated set saves a copy of the settings and seed it was made with. |

### Still open

None at present.
