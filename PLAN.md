# UQ Parkour Annotator: build plan

Status: draft for discussion. Nothing is built yet.

## 1. User flow

### One-time setup

The first time the app runs on a machine, it asks where the data is and
writes the answers to `local.toml`. It does not ask again.

| Step | Screen | What happens |
|---|---|---|
| 1 | Data source | "Do you have the source videos, or ready-made 1 s clips?" |
| 2a | Source folder (source videos only) | Shows short instructions for mapping the RDM drive in Windows. User pastes the folder path, which can be the mapped RDM drive or a local copy. The app checks it exists. |
| 2b | (ready-made clips) | No path is asked for. |
| 3 | Choose subject | Lists subjects from the source folder (route a) or from `data4annotation/` (route b). Subjects that already have clips are marked "clips ready". |
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

## 2. Source data (as found in `data/221125_SK_Test`)

- `videos/{task_NNN|unlabelled_x}_<unix-microseconds>.avi`: 1280×720, XVID, about 10 fps.
- `videos/<same name>.vidt`: one timestamp per frame, 8 bytes each, temporenc
  format, microsecond precision, local Brisbane time (UTC+10).
- `experiment_details.json`: subject name, task list, file-to-task mapping.

Frame rate varies between 9.6 and 10.4 fps, so windows are mapped to frames
using the `.vidt` times, not a fixed frame rate.

## 3. Data summary report

- Number of videos, split into task and unlabelled
- Total recorded time, and time per group
- Recording start and end, and overall span
- Frame rate: median, minimum, maximum
- Gaps between consecutive files longer than 1 s
- Problems: video without `.vidt`, frame count different from timestamp count,
  timestamps out of order, filename time disagreeing with first frame
- Task table: task number, name, duration, number of repeats
- A timeline strip showing task, unlabelled and gap periods
- Number of 1 s windows available for sampling

## 4. Sampling

- A window is a start time and an end time one second later, lying wholly
  inside one video file.
- Windows are drawn uniformly over recorded time, so longer files contribute
  proportionally more.
- Windows do not overlap one another.
- Up to 500 per subject. Fewer if the subject has less usable footage.
- The random seed for choosing windows is fixed in `study.toml`, so every
  rater gets the same windows and clips for a given subject (see decision A).

`segments.csv` columns: `segment_id, video_file, start_frame, end_frame,
start_time, end_time, task`.

## 5. Clip extraction

- ffmpeg cuts each window by frame number and re-encodes to H.264 MP4, since
  browsers cannot play XVID.
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
study.toml          every design choice: labels, segment count, window length, seed, sampling strategy
local.toml          data source, source-video folder, subject and rater name; written by the app (ignored by git)
app.py              Flask routes only; no logic
parkour/
    config.py       load study.toml and local.toml
    vidt.py         decode .vidt timestamp files
    dataset.py      find subjects and videos; frame times per video
    summary.py      build the data summary
    sampling/       one file per sampling strategy, chosen by name in study.toml
    extract.py      cut clips with ffmpeg; progress tracking
    annotations.py  read and append the annotation CSV
templates/          base, setup pages, summary, progress, mismatch, annotate, done
static/             style.css, app.js
data4annotation/    clips and annotations (ignored by git)
```

Source videos are read from the folder set in `local.toml`: the mapped RDM
drive or a local copy. Clips and annotations are written to
`data4annotation/` inside the repo folder.

Third-party packages: Flask and imageio-ffmpeg. Everything else is the
standard library.

## 8. Look and feel

One centred column, generous white space, system fonts, UQ purple (`#51247A`)
as the single accent colour. No front-end framework and no build step: plain
HTML, one stylesheet, one small script.

## 9. Build order

1. `vidt.py`, `dataset.py`, checked against the sample subject
2. `summary.py` and its page
3. `sampling.py`, `extract.py`, generate page with progress
4. `annotations.py`, annotate page
5. Sign-in, subject list, styling pass
6. End-to-end run on the sample subject; `run.bat`; rater instructions

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
| L | Guarding against design changes | Settings in `study.toml`; sampling strategies swappable by name; `dataset.py` is the only module that knows the folder layout; each generated set saves a copy of the settings and seed it was made with. |

### Still open

None at present.
