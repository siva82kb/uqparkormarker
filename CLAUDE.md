# UQ Parkour Annotator

Local Flask app for labelling random 1 s video windows with FAABOS categories.
See `README.md` for usage and `PLAN.md` for the design and open decisions.

## Code conventions

- Concise, well-commented, highly modular code. One job per module.
- Standard library first. Third-party packages are limited to Flask,
  and imageio-ffmpeg.
- `app.py` holds routes only. Logic lives in the `parkour/` package.
- Storage is plain CSV. No database.
- The app never deletes clips or labels. Only `reset.py`, run by hand,
  clears a subject, and it moves annotation files to
  `data4annotation/_archive/` instead of deleting them.
- The title bar links only to Data summary, Annotation summary and Docs.
  Steps of normal use (generating, annotating) get no link there; pages
  offer them as buttons when they are available. Anything that explains
  the method or its problems is a docs page, listed in `parkour/docs.py`.
- The website is beautiful, minimal, professional and clean: plain HTML, one 
  stylesheet, one script, no front-end framework.

## Lessons from bugs

- **Never let a browser keep a clip.** On 2026-11-19 clips were served with
  a one-hour cache under addresses that are reused when clips are generated
  again (`seg_0001.mp4` ...). After regenerating, the browser showed the old
  videos, and labels were saved against the wrong clips. Clip addresses now
  carry a code for the set and are served `no-store`. Keep both. The same
  applies to anything else whose name is reused for new content.
- **Test a setting on a fresh start as well as on a resumed one.** The
  `clip_limit` test setting worked when the clip list already existed and
  was ignored the first time a list was made.

## Documentation

- The `.md` files must never be out of sync with the code. Any change to
  behaviour, folder layout, settings or build status updates `PLAN.md`,
  `README.md`, the docs pages in the app and this file in the same piece of work.
- The docs pages in the app (`templates/docs/`, listed in
  `parkour/docs.py`) are the only explanation of the method, for people
  who will interpret the results. Keep one copy: do not add a text
  version elsewhere. Write them in short, plain sentences with worked
  examples; the user finds dense technical wording hard to follow.
- Docs pages never write out a value that `study.toml` sets (number of
  clips, clip length, gap limit). They print what `docs.settings()` gives.
- Use one word per thing: a *video* is a recorded file, a *clip* is a
  one-second piece of it. Do not also call a clip a window or a segment in
  explanations.
- Never write participant names, the RDM path or the RDM record name in any
  committed file. Use `Pxx` and `<source>`.

## Parked problems

### Frame timestamps can be late (found 2026-11-19, worked around, not fixed)

The clips are to be lined up with the sensor data later, so this matters.
Do not implement a fix without the user's agreement on the method.

**Decided for now (quickest fix, for the ICORR paper).** Use one
participant, the one least affected. Never sample a window that contains a
repeated stamp or a step over 0.1 s (`parkour/timing.py`,
`max_step_seconds` in `study.toml`). Nothing is corrected. A proper fix and
the sync to the sensors remain to be done.

- **Cause.** In the recorder (github.com/siva82kb/armusevideo), the camera
  thread stores the read time in one shared variable (`imgtime`) and the
  main thread writes whatever that variable holds when it gets to a frame.
  When the main thread is busy, frames queue up and are then written in a
  burst with the current time, not their own. A stamp is therefore never
  early, but can be seconds late. Repeated stamps are a by-product.
  The repository writes video at 10 fps; the study recordings are 30 fps,
  so they were made with a modified version whose stamping logic has not
  been confirmed to be the same.
- **Size, across the six participants whose videos sit directly in
  `Video/`.** Frames stamped more than 0.2 s late: 0.03% in the cleanest
  participant, 2 to 3.3% in the other five. Worst single lag: 0.55 s in the
  cleanest, 2 to 11 s in the others. Separately, every session has time
  with no frames at all (0.6 to 17.7 s per session of 48 to 76 min), so
  counting frames at 30 fps cannot replace the stamps over long stretches.
  All six have a `.vidt` for every video and matching frame counts.
- **What mostly works.** A 1 s window with no repeated stamp and no step
  over 0.1 s is nearly always well-timed. The worst such window is 76 to
  128 ms late in five participants and 211 ms in one. The rule keeps 88 to
  97.5% of windows (76 to 95% of task video) and leaves 1 to 8 of the 91
  tasks with no usable window.
- **Jump recordings.** Used for syncing (see below). In most participants
  one or both jump recordings contain one to three repeated stamps or
  pauses, so they are not automatically clean.
- **Frame rate matters.** Recordings from 2022 made at 10 fps show almost
  no repeated stamps and no pauses; one made at 30 fps shows repeats but no
  long lags. So 30 fps explains the scattered repeats, and the multi-second
  lags in the study recordings need some further cause that varies by
  session.
- **Options discussed.** (a) Drop windows with a repeated stamp or a
  pause: chosen for now. (b) Estimate capture times: a frame was read no
  later than its own stamp, and no later than any later frame's stamp minus
  the frames between. (c) Both: correct, and record each clip's lag.
- **Not addressed by any of these.** One-frame jitter (about 30 ms), and
  the fixed delay between capture and stamp.
- **Syncing to the sensors.** A jump task at the start and end of each
  session is meant for this. Landings seen in both video and sensor data
  give the offset and drift between the video computer's clock and each
  sensor clock, and cancel the fixed camera delay. Whether the jumps are
  essential or only a check depends on whether the sensors share the
  computer's clock, which is not yet known. The app's job is only to hand
  over clips with exact frame numbers and well-timed stamps.
- **Current state of the code.** Windows failing the rule above are not
  sampled. Task video and unlabelled video are sampled separately
  (`task_share` in `study.toml`), and within each every allowed window start
  is equally likely. `start_time` and
  `end_time` in `segments.csv` are raw stamps of the first and last frame.
  The share of windows left out is shown on the summary page.
- **Docs pages.** Four pages under `/docs` (`timing-problem`,
  `timing-evidence`, `timing-rule`, `timing-open`) explain the problem, show
  it in the loaded subject's stamps, and set out the rule with its pros,
  cons and the alternatives (`PLAN.md` section 3a). `lag.py` measures
  lateness for these pages only (option (b)'s limit, used as a
  measurement, never to correct). The survey figures on the rule page are
  fixed text; update them if the survey is redone.

## Environment

- Run everything through `uv` (`uv run python ...`), never Anaconda, so
  development matches what raters get. Python 3.12, pinned in `pyproject.toml`.
- Tests: `uv run python -m unittest discover -s tests -t .`
- Source videos are on the RDM, mapped as a drive on this machine. The folder
  and subject in use are in `local.toml` (not committed).
- The RDM is slow over the VPN: one to two seconds to open any file. Do not
  scan it recursively; list one folder at a time and read files in parallel.
- Anything slow to produce for a subject is produced once and saved under
  `data4annotation/<subject>/` with the time it was made, then reused. It
  is redone only when the user asks. The timestamps read from the videos
  are saved this way (`parkour/recording_store.py`).
- `data/221125_SK_Test` is an early test recording with an older layout
  (`videos/` subfolder, 10 fps). The app no longer reads it.
- `private/` holds the user's older analysis code and data. Read-only reference.
