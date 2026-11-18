# UQ Parkour Annotator

A small local web app for labelling functional upper-limb use in the UQ Parkour
study videos. It draws random 1-second windows from a subject's videos, cuts
them into short clips, and shows them one at a time to a rater, who assigns
each clip one of four FAABOS categories.

Everything runs on the rater's own computer. Nothing is uploaded.

## What you need

- Python 3.10 or newer (Anaconda is fine)
- The packages in `requirements.txt` (Flask, imageio-ffmpeg; h5py is optional)
- The subject folders copied into `data/`

## Starting the app

1. Double-click `run.bat` (or run `python app.py`).
2. Your browser opens at `http://127.0.0.1:5000`.

## Using it

1. **Enter your name.** Your clips and annotations are stored under this name.
2. **Choose a subject** from the list of folders found in `data/`.
3. **Read the data summary** for that subject: videos, durations, frame rates,
   gaps, and any problems found.
4. **Generate segments.** The app picks the random 1 s windows and cuts the
   clips. This takes a few minutes and shows progress.
5. **Annotate.** Each clip loops until you label it. Keys `1`–`4` choose a
   category, `Backspace` goes back one clip. You can close the app at any time
   and carry on later.

## Where things are stored

```
data/<subject>/videos/*.avi, *.vidt         source videos and frame timestamps
data4annotation/<rater>/<subject>/
    segments.csv                            the sampled windows
    clips/seg_0001.mp4 ...                  the 1 s clips
    <subject>_<rater>_annotations.csv       the labels
```

## Annotation file

One row is appended each time a clip is labelled. If a clip is relabelled, a
new row is added and the latest row for that clip is the one that counts.

| Column | Meaning |
|---|---|
| `segment_id` | Clip identifier, matching `segments.csv` |
| `label` | The chosen category |
| `rater` | Rater name |
| `annotated_at` | When the label was saved (local time) |

## Settings

`config.json` holds the category labels, the number of segments, the window
length, and the folder locations.
