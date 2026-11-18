"""Flask routes only. All logic lives in the parkour package."""

from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

from parkour import clipset, config, dataset, extract, fmt, summary

app = Flask(__name__)
app.add_template_filter(fmt.duration, "duration")


def _setup():
    """(local settings, study settings, subject's source folder), or None."""
    local = config.load_local()
    if local is None:
        return None
    return local, config.load_study(), Path(local["source_dir"]) / local["subject"]


@app.route("/")
def home():
    """Open on the page that matches the state of the clips."""
    local = config.load_local()
    if local is None:
        return render_template("setup_pending.html")
    started = clipset.state(local["subject"]) != "none"
    return redirect(url_for("generate_page" if started else "summary_page"))


@app.route("/summary")
def summary_page():
    if (setup := _setup()) is None:
        return redirect(url_for("home"))
    local, study, subject_dir = setup
    offset = study["source"]["utc_offset_hours"]
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
        clip_state=clipset.state(local["subject"]),
    )


@app.route("/generate", methods=["GET", "POST"])
def generate_page():
    """POST starts cutting clips. GET shows progress, resuming if interrupted."""
    if (setup := _setup()) is None:
        return redirect(url_for("home"))
    local, study, subject_dir = setup
    subject = local["subject"]

    differences = clipset.design_differences(subject, study)
    if differences:
        return render_template(
            "mismatch.html", differences=differences, folder=clipset.folder(subject)
        )

    posted = request.method == "POST"
    state = clipset.state(subject)
    if state == "none" and not posted and extract.snapshot(subject)["state"] == "idle":
        return redirect(url_for("summary_page"))    # nothing started yet
    if state != "complete":
        extract.ensure_running(subject, subject_dir, study)
    if posted:
        return redirect(url_for("generate_page"))   # so a reload does not re-post
    return render_template(
        "generate.html",
        subject=subject,
        study=study,
        source=subject_dir,
        folder=clipset.folder(subject),
        progress=extract.snapshot(subject),
    )


@app.route("/generate/status")
def generate_status():
    local = config.load_local()
    return jsonify(extract.snapshot(local["subject"]) if local else {})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
