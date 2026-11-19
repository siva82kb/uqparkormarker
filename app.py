"""Flask routes only. All logic lives in the parkour package."""

from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, url_for)

from parkour import (annotations, clipset, config, docs, extract, fmt, loader,
                     summary, timing_report)

app = Flask(__name__)
app.add_template_filter(fmt.duration, "duration")
app.add_template_filter(fmt.share, "share")
app.add_template_filter(fmt.clock, "clock")
app.add_template_filter(fmt.clip_number, "clip_number")


@app.context_processor
def _who():
    """Every page can show who is signed in and which subject is open."""
    local = config.load_local() or {}
    return {"rater": local.get("rater"), "open_subject": local.get("subject")}


def _setup():
    """(local settings, study settings, subject's source folder), or None."""
    local = config.load_local()
    if local is None:
        return None
    return local, config.load_study(), Path(local["source_dir"]) / local["subject"]


def _recording(setup):
    """(recording, None) once the videos are read; else (None, a progress page)."""
    local, study, subject_dir = setup
    recording = loader.cached(subject_dir)
    if recording is not None:
        return recording, None
    loader.start(subject_dir, study["source"]["utc_offset_hours"])
    return None, render_template(
        "loading.html", subject=local["subject"], source=subject_dir,
        progress=loader.snapshot(),
    )


@app.route("/")
def home():
    """Open on the page that matches the state of the clips."""
    local = config.load_local()
    if local is None:
        return render_template("setup_pending.html")
    state = clipset.state(local["subject"])
    if state == "none":
        return redirect(url_for("summary_page"))
    if state == "partial":
        return redirect(url_for("generate_page"))
    # The clips are ready. The rater's name is asked only now, when labelling
    # is about to start; nothing before this needs it.
    return redirect(url_for("annotate_page" if local.get("rater") else "signin_page"))


@app.route("/signin", methods=["GET", "POST"])
def signin_page():
    """Ask the rater's name once, when the clips are ready, and keep it in
    local.toml."""
    local = config.load_local()
    if (local is None or local.get("rater")
            or clipset.state(local["subject"]) != "complete"):
        return redirect(url_for("home"))
    typed = request.form.get("name", "")
    if request.method == "POST":
        name = annotations.clean_name(typed)
        if name:
            config.set_local("rater", name)
            return redirect(url_for("home"))
    return render_template(
        "signin.html", typed=typed, rejected=request.method == "POST"
    )


@app.route("/summary")
def summary_page():
    """The data summary, or a progress page while the videos are being read."""
    if (setup := _setup()) is None:
        return redirect(url_for("home"))
    local, study, _ = setup
    recording, waiting = _recording(setup)
    if recording is None:
        return waiting
    return render_template(
        "summary.html",
        subject=local["subject"],
        summary=summary.build(recording.videos, study, recording.missing),
        read_at=recording.read_at,
        study=study,
        clip_state=clipset.state(local["subject"]),
    )


@app.route("/summary/reread", methods=["POST"])
def summary_reread():
    """Throw away the saved read of the videos; the summary then reads again."""
    if (setup := _setup()) is not None:
        loader.forget(setup[2])
    return redirect(url_for("summary_page"))


@app.route("/summary/status")
def summary_status():
    return jsonify(loader.snapshot())


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
    # Once every clip is cut, the page also lists the clips and offers to go on.
    clips = clipset.read_segments(subject) if state == "complete" else []
    return render_template(
        "generate.html",
        subject=subject,
        study=study,
        source=subject_dir,
        folder=clipset.folder(subject),
        progress=extract.snapshot(subject),
        clip_limit=local.get("clip_limit"),
        clips=clips,
        spacing=clipset.spacing(clips) if clips else None,
    )


@app.route("/generate/status")
def generate_status():
    local = config.load_local()
    return jsonify(extract.snapshot(local["subject"]) if local else {})


# ---- Annotation: one clip at a time, in the rater's own order ----

def _annotation():
    """What the annotation pages work with, or (None, where to go instead).

    Returns ((subject, rater, study, clips in the rater's order, labels so
    far), None) when the rater is signed in and every clip has been cut.
    """
    local = config.load_local()
    if local is None or not local.get("rater"):
        return None, redirect(url_for("home"))
    subject, rater, study = local["subject"], local["rater"], config.load_study()
    differences = clipset.design_differences(subject, study)
    if differences:
        return None, render_template(
            "mismatch.html", differences=differences, folder=clipset.folder(subject)
        )
    if clipset.state(subject) != "complete":
        return None, redirect(url_for("home"))
    ordered = annotations.order(clipset.read_segments(subject), rater)
    return (subject, rater, study, ordered, annotations.read(subject, rater)), None


@app.route("/annotate", methods=["GET", "POST"])
@app.route("/annotate/<int:position>")
def annotate_page(position: int | None = None):
    """Show a clip to label. POST saves a label and moves to the next clip
    without one. A position shows an earlier clip again, to change its label."""
    found, elsewhere = _annotation()
    if found is None:
        return elsewhere
    subject, rater, study, ordered, labels = found
    by_key = {label["key"]: label["name"] for label in study["labels"]}

    if request.method == "POST":
        segment_id, key = request.form.get("segment_id"), request.form.get("key")
        if key not in by_key or segment_id not in {s.segment_id for s in ordered}:
            abort(400)
        annotations.append(subject, rater, segment_id, by_key[key])
        return redirect(url_for("annotate_page"))

    upcoming = annotations.next_position(ordered, labels)   # first clip without a label
    if position is None:
        if upcoming is None:
            return redirect(url_for("done_page"))
        position = upcoming
    furthest = len(ordered) - 1 if upcoming is None else upcoming
    if not 0 <= position <= furthest:
        return redirect(url_for("annotate_page"))

    clip = ordered[position]
    return render_template(
        "annotate.html",
        clip=clip,
        position=position,
        total=len(ordered),
        labelled=sum(s.segment_id in labels for s in ordered),
        labels=study["labels"],
        current=labels.get(clip.segment_id),
        reviewing=position != upcoming,
        clip_set=clipset.set_code(subject),
    )


@app.route("/clips/<clip_set>/<segment_id>.mp4")
def clip_file(clip_set: str, segment_id: str):
    """One clip of the set now on disk.

    Clip numbers are reused every time clips are generated, so two things
    stop a browser from ever showing a clip from an earlier set: the address
    carries the code of the set, and the browser is told to store nothing.
    """
    local = config.load_local()
    if (local is None
            or clip_set != clipset.set_code(local["subject"])
            or segment_id not in {
                s.segment_id for s in clipset.read_segments(local["subject"])}):
        abort(404)
    response = send_file(
        clipset.clip_path(local["subject"], segment_id),
        mimetype="video/mp4", conditional=True, etag=False, max_age=0,
    )   # conditional: lets the player ask for part of the file, which looping needs
    response.headers["Cache-Control"] = "no-store"
    response.headers.pop("Last-Modified", None)
    response.headers.pop("Expires", None)
    return response


@app.route("/done")
def done_page():
    """Every clip has a label: show the counts and where the file is."""
    found, elsewhere = _annotation()
    if found is None:
        return elsewhere
    subject, rater, study, ordered, labels = found
    if annotations.next_position(ordered, labels) is not None:
        return redirect(url_for("annotate_page"))
    names = [label["name"] for label in study["labels"]]
    return render_template(
        "done.html",
        subject=subject,
        total=len(ordered),
        counts=annotations.counts(ordered, labels, names),
        file=annotations.path(subject, rater),
        last=len(ordered) - 1,
    )


# ---- Annotation summary: how far the rater has got ----

@app.route("/annotations")
def annotation_summary():
    """Progress and label counts. Offers annotation only when it is available."""
    local = config.load_local()
    if local is None or not local.get("rater"):
        return redirect(url_for("home"))
    subject, rater, study = local["subject"], local["rater"], config.load_study()
    state = clipset.state(subject)
    ordered = [] if state == "none" else annotations.order(
        clipset.read_segments(subject), rater)
    labels = annotations.read(subject, rater)
    names = [label["name"] for label in study["labels"]]
    return render_template(
        "annotation_summary.html",
        subject=subject,
        total=len(ordered),
        labelled=sum(s.segment_id in labels for s in ordered),
        ready=state == "complete" and not clipset.design_differences(subject, study),
        counts=annotations.counts(ordered, labels, names),
        file=annotations.path(subject, rater),
    )


# ---- Docs: how the method works and what to watch for ----

@app.route("/docs")
def docs_index():
    return render_template("docs/index.html", groups=docs.GROUPS)


@app.route("/docs/<slug>")
def docs_page(slug: str):
    """One docs page. Pages that show measurements wait for the videos."""
    if (found := docs.find(slug)) is None:
        abort(404)
    page, previous, following = found
    study = config.load_study()
    values = dict(page=page, previous=previous, following=following,
                  group=docs.group_of(page), study=study,
                  **docs.settings(study), **docs.figures(study))
    if page.needs_videos:
        if (setup := _setup()) is None:
            return redirect(url_for("home"))
        recording, waiting = _recording(setup)
        if recording is None:
            return waiting
        values.update(subject=setup[0]["subject"],
                      report=timing_report.build(recording.videos, study))
    return render_template(page.template, **values)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
