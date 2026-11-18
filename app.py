"""Flask routes only. All logic lives in the parkour package."""

from pathlib import Path

from flask import Flask, redirect, render_template, url_for

from parkour import config, dataset, fmt, summary

app = Flask(__name__)
app.add_template_filter(fmt.duration, "duration")


@app.route("/")
def home():
    if config.load_local() is None:
        return render_template("setup_pending.html")
    return redirect(url_for("summary_page"))


@app.route("/summary")
def summary_page():
    local = config.load_local()
    if local is None:
        return redirect(url_for("home"))
    study = config.load_study()
    offset = study["source"]["utc_offset_hours"]
    subject_dir = Path(local["source_dir"]) / local["subject"]
    return render_template(
        "summary.html",
        subject=local["subject"],
        summary=summary.build(
            dataset.load_videos(subject_dir, offset),
            study["sampling"]["window_seconds"],
            offset,
            dataset.missing_videos(subject_dir),
        ),
        study=study,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
