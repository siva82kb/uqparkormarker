"""Flask routes only. All logic lives in the parkour package."""

import sys
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, url_for)

from parkour import (annotations, clipset, config, dataset, devreload, docs, extract, fmt,
                     loader, share, shared_ratings, summary, timing_report, transfer)

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


@app.context_processor
def _developer_mode():
    """In developer mode, pages are told where to ask whether files changed."""
    return {"dev_stamp_url": url_for("dev_stamp") if app.config.get("DEV") else None}


@app.route("/dev/stamp")
def dev_stamp():
    """Developer mode only: a value that changes when the app's files change."""
    if not app.config.get("DEV"):
        abort(404)
    return jsonify(stamp=devreload.stamp())


def _setup():
    """(local settings, study settings, subject's source folder), or None."""
    local = config.load_local()
    if not (local and local.get("source_dir") and local.get("subject")):
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


def _is_set_up(local: dict | None) -> bool:
    return bool(local and local.get("source_dir") and local.get("subject"))


@app.route("/")
def home():
    """Open on the page that matches the state of the clips.

    Clips on this computer come first. If there are none, shared clips on the
    RDM are fetched. If there are none there either, the videos are read and
    clips are generated here.
    """
    local = config.load_local()
    if not _is_set_up(local):
        return redirect(url_for("setup_page"))
    subject = local["subject"]
    state = clipset.state(subject)
    if state == "partial":
        return redirect(url_for("generate_page"))
    if state == "complete":
        # The rater's name is asked only now, when labelling is about to
        # start; nothing before this needs it.
        return redirect(url_for("annotate_page" if local.get("rater") else "signin_page"))
    try:
        on_rdm = share.shared_id(share.root(local, config.load_study()), subject)
    except share.Unreachable:
        return render_template("unreachable.html", folder=local["source_dir"])
    return redirect(url_for("fetch_page" if on_rdm else "summary_page"))


@app.route("/setup", methods=["GET", "POST"])
def setup_page():
    """First start: ask where the study folder is, and settle the participant.

    The participant is taken from the shared clips on the RDM if there are
    any (by itself if there is only one), else chosen from the participant
    folders in the study folder.
    """
    if _is_set_up(config.load_local()):
        return redirect(url_for("home"))
    typed = request.form.get("folder", "").strip().strip('"')
    chosen = request.form.get("subject", "")
    values = dict(typed=typed, problem=None, kind=None, names=[])
    if request.method == "POST" and typed:
        source = Path(typed)
        try:
            if not share.reachable(source):
                raise share.Unreachable
            kind, names = share.candidates(source, source / config.load_study()["share"]["folder"])
        except share.Unreachable:
            values["problem"] = "unreachable"
            return render_template("setup.html", **values)
        if len(names) == 1 and kind == "shared":
            chosen = names[0]
        if chosen in names and (kind == "shared" or dataset.has_videos(source, chosen)):
            config.set_local("source_dir", str(source))
            config.set_local("subject", chosen)
            return redirect(url_for("home"))
        values.update(kind=kind, names=names,
                      problem="no_videos" if chosen in names else
                              "nobody" if not names else None)
    elif request.method == "POST":
        values["problem"] = "empty"
    return render_template("setup.html", **values)


@app.route("/fetch", methods=["GET", "POST"])
def fetch_page():
    """Download the participant's shared clips from the RDM, with progress.
    POST tries again after a failure."""
    local = config.load_local()
    if not _is_set_up(local) or clipset.state(local["subject"]) != "none":
        return redirect(url_for("home"))
    study, subject = config.load_study(), local["subject"]
    progress = transfer.snapshot("download", subject)
    if progress["state"] == "idle" or request.method == "POST":
        folder, subject_dir = share.root(local, study), Path(local["source_dir"]) / subject
        transfer.start("download", subject,
                       lambda report: share.unpack(folder, subject, subject_dir, study, report))
        if request.method == "POST":
            return redirect(url_for("fetch_page"))
        progress = transfer.snapshot("download", subject)
    return render_template("transfer.html", kind="download", subject=subject,
                           progress=progress, status_url=url_for("transfer_status", kind="download"))


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    """POST puts this computer's clips on the RDM as a zip. GET shows how far
    it has got."""
    local = config.load_local()
    if not _is_set_up(local) or clipset.state(local["subject"]) != "complete":
        return redirect(url_for("home"))
    study, subject = config.load_study(), local["subject"]
    if request.method == "POST":
        folder = share.root(local, study)
        if share.standing(folder, subject, bool(local.get("clip_limit"))) == "upload":
            transfer.start("upload", subject, lambda report: share.pack(folder, subject, report))
        return redirect(url_for("upload_page"))
    progress = transfer.snapshot("upload", subject)
    if progress["state"] == "idle":
        return redirect(url_for("generate_page"))
    return render_template("transfer.html", kind="upload", subject=subject,
                           progress=progress, status_url=url_for("transfer_status", kind="upload"))


@app.route("/transfer/<kind>/status")
def transfer_status(kind: str):
    local = config.load_local()
    return jsonify(transfer.snapshot(kind, local["subject"]) if _is_set_up(local) else {})


@app.route("/signin", methods=["GET", "POST"])
def signin_page():
    """Ask the rater's name once, when the clips are ready, and keep it in
    local.toml."""
    local = config.load_local()
    if (local is None or local.get("rater")
            or clipset.state(local["subject"]) != "complete"):
        return redirect(url_for("home"))
    typed = request.form.get("name", "")
    verdict = _name_verdict(local, typed) if request.method == "POST" else None
    if verdict in ("free", "unchecked"):
        config.set_local("rater", annotations.clean_name(typed))
        return redirect(url_for("home"))
    return render_template("signin.html", typed=typed, verdict=verdict)


def _name_verdict(local: dict, typed: str) -> str:
    """What to make of a rater's name: 'empty' (nothing usable in it), 'taken'
    (already has ratings on the RDM for this participant), 'free', or
    'unchecked' (the RDM could not be asked, so the name is let through)."""
    name = annotations.clean_name(typed)
    if not name:
        return "empty"
    try:
        folder = share.root(local, config.load_study())
        return "taken" if name in shared_ratings.taken_names(folder, local["subject"]) else "free"
    except share.Unreachable:
        return "unchecked"


@app.route("/signin/check")
def signin_check():
    """For the sign-in page, as a name is typed: is it free?"""
    local = config.load_local()
    typed = request.args.get("name", "")
    verdict = _name_verdict(local, typed) if _is_set_up(local) else "unchecked"
    return jsonify(verdict=verdict, name=annotations.clean_name(typed))


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
        # How the finished clips stand against the RDM: can they be uploaded?
        standing=share.standing(share.root(local, study), subject,
                                bool(local.get("clip_limit"))) if clips else None,
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
    # Every clip is labelled: the labels go to the RDM by themselves.
    local = config.load_local()
    uploaded = shared_ratings.upload(share.root(local, study), subject, rater)
    return render_template(
        "done.html",
        subject=subject,
        total=len(ordered),
        counts=annotations.counts(ordered, labels, names),
        file=annotations.path(subject, rater),
        last=len(ordered) - 1,
        uploaded=uploaded,
        rater=rater,
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
    # `--dev`: restart on a change to the code, and reload the open page on a
    # change to any of the app's files. For development only.
    app.config["DEV"] = "--dev" in sys.argv
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEV"])
