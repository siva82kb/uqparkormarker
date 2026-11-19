// UQ Parkour Annotator: small page behaviours. No framework.

// Timeline: name the stretch under the pointer in the line below the strip.
(function () {
  const strip = document.getElementById("timeline");
  const readout = document.getElementById("timeline-readout");
  if (!strip || !readout) return;

  const show = (span) => {
    readout.textContent = span
      ? `${span.dataset.label} · ${span.dataset.length}`
      : readout.dataset.idle;
    readout.classList.toggle("live", Boolean(span));
  };

  strip.addEventListener("pointermove", (e) => show(e.target.closest(".span")));
  strip.addEventListener("pointerleave", () => show(null));
})();

// Charts: show the note of the mark under the pointer in the line below the
// chart. A chart is any element followed by a .readout line; marks carry
// their note in data-tip.
document.querySelectorAll(".readout").forEach((readout) => {
  const chart = readout.closest("figure");
  if (!chart) return;
  const show = (mark) => {
    readout.textContent = mark ? mark.dataset.tip : readout.dataset.idle;
    readout.classList.toggle("live", Boolean(mark));
  };
  chart.addEventListener("pointermove", (e) => show(e.target.closest("[data-tip]")));
  chart.addEventListener("pointerleave", () => show(null));
});

// Docs pages: list the page's sections in the side column, and mark the one
// being read while the page scrolls.
(function () {
  const list = document.getElementById("doc-sections");
  const main = document.getElementById("doc-main");
  if (!list || !main) return;

  const links = [...main.querySelectorAll("h2")].map((heading, i) => {
    heading.id = heading.id || `section-${i + 1}`;
    const link = document.createElement("a");
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent;
    list.append(link);
    return { heading, link };
  });

  const mark = () => {
    // The section being read is the last heading above the upper part of the window.
    let current = links[0];
    for (const entry of links) {
      if (entry.heading.getBoundingClientRect().top < 140) current = entry;
    }
    links.forEach((entry) => entry.link.classList.toggle("here", entry === current));
  };
  document.addEventListener("scroll", mark, { passive: true });
  mark();
})();

// Progress bar (reading videos, cutting clips): ask the server how far the
// job has got and redraw the bar and the status line in place, until the job
// is done or has failed. A bar marked data-reload-when-done reloads the page
// at the end, to show what the finished job produced.
(function () {
  const bar = document.getElementById("progress");
  if (!bar) return;
  const POLL_MS = 600;
  const set = (id, change) => {           // some pages lack some of the parts
    const element = document.getElementById(id);
    if (element) change(element);
  };

  // Clip cutting only: one bar splitting the clips cut so far into task
  // video and unlabelled video, with a mark at the planned split.
  const drawMix = (p) => {
    const mix = document.getElementById("mix");
    if (!mix || !p.total || p.task_total === undefined) return;
    mix.hidden = false;
    const task = p.task_done, unlabelled = p.done - p.task_done;
    const percent = (part, whole) => (whole ? `${Math.round((100 * part) / whole)}%` : "");
    const part = (id, count) => set(id, (e) => {
      e.hidden = !count;
      e.style.flex = `${count} 1 0`;      // widths in proportion to the counts
    });
    part("mix-task", task);
    part("mix-unlabelled", unlabelled);
    set("mix-task-count", (e) => (e.textContent = task));
    set("mix-unlabelled-count", (e) => (e.textContent = unlabelled));
    set("mix-task-share", (e) => (e.textContent = percent(task, p.done)));
    set("mix-unlabelled-share", (e) => (e.textContent = percent(unlabelled, p.done)));

    const planned = percent(p.task_total, p.total);
    set("mix-target", (e) => (e.style.left = `${(100 * p.task_total) / p.total}%`));
    set("mix-target-label", (e) => (e.textContent = `planned ${planned}`));
    set("mix-bar", (e) => e.setAttribute("aria-label",
      `${task} clips from task video and ${unlabelled} from unlabelled video so far. ` +
      `Planned: ${planned} from task video.`));
  };

  const draw = (p) => {
    const share = p.total ? (100 * p.done) / p.total : 0;
    bar.setAttribute("aria-valuemax", p.total);
    bar.setAttribute("aria-valuenow", p.done);
    set("progress-fill", (e) => (e.style.width = `${share}%`));
    set("progress-count", (e) => (e.textContent = p.total
      ? `${p.done} of ${p.total}${p.unit ? " " + p.unit : ""} · ${Math.floor(share)}%`
      : "Preparing"));
    set("clip-total", (e) => p.total && (e.textContent = p.total));
    drawMix(p);
    set("progress-message", (e) => (e.textContent = p.message || "Starting…"));
    set("progress-error", (e) => { e.textContent = p.error; e.hidden = !p.error; });
    set("progress-help", (e) => (e.hidden = p.state === "done"));
    alive(p.state === "running", p.slow ? p.step_seconds : null);
    set("progress-time", (e) => (e.textContent = timeSpent(p)));
  };

  // "12 min 40 s", "1 h 52 min": a length of time in plain words.
  const length = (seconds) => {
    if (seconds < 60) return `${seconds} s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} min ${String(seconds % 60).padStart(2, "0")} s`;
    return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
  };

  // Clip cutting only: time spent in all, over every run, and a rough guess
  // of the time left. Both are worked out by the app.
  const timeSpent = (p) => {
    if (p.elapsed_seconds === undefined || !p.elapsed_seconds) return "";
    if (p.state === "done") return `· took ${length(p.elapsed_seconds)} in all`;
    let text = `· ${length(p.elapsed_seconds)} so far`;
    if (p.left_seconds !== null && p.left_seconds !== undefined) {
      text += p.left_seconds < 60
        ? " · less than a minute left"
        : ` · about ${length(60 * Math.round(p.left_seconds / 60)).replace(" 00 s", "")} left`;
    }
    return text;
  };

  // Signs of life: a pulsing dot while the app reports it is working. It is
  // shown only straight after the app has answered, so it cannot keep going
  // by itself if the app has stopped. (The time beside the heading ticks too.)
  // The status line stays quiet about the current clip unless the app says
  // that clip is slow; then it gives the time spent on it.
  const alive = (working, slowSeconds) => {
    set("progress-pulse", (e) => (e.hidden = !working));
    set("progress-seconds", (e) => (e.textContent = working && slowSeconds
      ? ` · this one is slow, ${length(slowSeconds)} so far`
      : ""));
  };

  const poll = async () => {
    let progress;
    try {
      progress = await (await fetch(bar.dataset.statusUrl, { cache: "no-store" })).json();
    } catch {
      alive(false);
      set("progress-message", (e) => (e.textContent = "Lost contact with the app. Is it still running?"));
      return setTimeout(poll, 3 * POLL_MS);
    }
    draw(progress);
    if (progress.state === "running") return setTimeout(poll, POLL_MS);
    if (progress.state === "done" && "reloadWhenDone" in bar.dataset) location.reload();
  };

  poll();
})();

// Sign-in: as a name is typed, ask the app whether it is free, and say so in
// the line under the box. While the name is taken or unusable, Start is off.
// (The app checks again when the form is sent, so this is a convenience.)
(function () {
  const form = document.getElementById("signin");
  if (!form) return;
  const box = document.getElementById("name");
  const line = document.getElementById("name-verdict");
  const start = document.getElementById("signin-start");
  let waiting = null, asked = 0;

  const show = (verdict) => {
    const bad = verdict === "taken" || verdict === "empty";
    line.textContent = verdict ? line.dataset[verdict] : "";
    line.classList.toggle("field-error", bad);
    box.setAttribute("aria-invalid", bad);
    start.disabled = bad;
  };

  const check = async () => {
    const mine = ++asked;                 // ignore answers to earlier typing
    if (!box.value.trim()) return show(null);
    try {
      const url = `${form.dataset.checkUrl}?name=${encodeURIComponent(box.value)}`;
      const answer = await (await fetch(url, { cache: "no-store" })).json();
      if (mine === asked) show(answer.verdict);
    } catch {
      if (mine === asked) show("unchecked");
    }
  };

  box.addEventListener("input", () => {
    start.disabled = true;                // until this name has been checked
    line.textContent = "Checking…";
    line.classList.remove("field-error");
    clearTimeout(waiting);
    waiting = setTimeout(check, 400);     // wait for a pause in the typing
  });
  if (box.value.trim()) check();
})();

// Annotation: each clip gets a label for each arm. A key chooses an arm (the
// keys are listed on each arm, in data-keys: A or R for right, F or L for
// left); only then do that arm's labels work, by pressing 1 to 5 or by
// clicking. The other arm's labels, and both arms' before a choice is made,
// are off, so a stray click or number never becomes a label.
// Choosing a label saves nothing: the clip stays on screen showing both
// choices, and a wrong press can be put right. Moving on is the deliberate
// step that saves: the Next button or the right arrow sends both labels
// together, and only when both arms have one. The left arrow goes back one
// clip; choices not yet saved with Next are dropped.
(function () {
  const page = document.getElementById("annotate");
  if (!page) return;
  const form = document.getElementById("annotate-form");
  const hint = document.getElementById("annotate-hint");
  const next = document.getElementById("annotate-next");
  const arms = [...page.querySelectorAll(".arm")];
  const byName = new Map(arms.map((arm) => [arm.dataset.arm, arm]));
  // Which arm each key chooses, e.g. a -> right, r -> right, f -> left, l -> left.
  const armOfKey = new Map(arms.flatMap((arm) =>
    arm.dataset.keys.split(" ").map((key) => [key, arm.dataset.arm])));
  const picked = (arm) => arm.querySelector(".label-chosen")?.dataset.key ?? "";
  const saved = new Map(arms.map((arm) => [arm.dataset.arm, picked(arm)]));   // as the page arrived
  let chosen = null;                  // the arm that number keys go to
  let sent = false;

  const done = () => arms.every(picked);
  const changed = () => arms.some((arm) => picked(arm) !== saved.get(arm.dataset.arm));
  const say = (what, warn = false) => {
    hint.textContent = hint.dataset[what];
    hint.classList.toggle("refused", warn);
  };
  const rest = () => say(!done() ? chosen || "idle" : changed() ? "done" : "saved");

  const choose = (name) => {
    chosen = name;
    arms.forEach((arm) => {
      const on = arm.dataset.arm === name;
      arm.classList.toggle("arm-active", on);
      arm.querySelectorAll(".label").forEach((button) => (button.disabled = !on));
    });
    rest();
  };

  const pick = (name, key) => {       // mark this arm's label; nothing is saved yet
    byName.get(name).querySelectorAll(".label").forEach((button) =>
      button.classList.toggle("label-chosen", button.dataset.key === key));
    next.classList.toggle("button-off", !done());
    rest();
  };

  const moveOn = () => {
    if (!done()) return say("notDone", true);
    if (sent) return;
    sent = true;
    say("moving");                    // answer the press at once, before the next page arrives
    next.classList.add("button-busy");
    if (!changed()) return (location.href = page.dataset.next);    // nothing new to save
    arms.forEach((arm) => (form.elements[arm.dataset.arm].value = picked(arm)));
    form.submit();
  };

  arms.forEach((arm) => {
    // A click on a label counts only for the arm chosen with its key. A click
    // on an arm that is off (its buttons are disabled) just says what to do.
    arm.querySelectorAll(".label").forEach((button) =>
      button.addEventListener("click", () => {
        if (chosen === arm.dataset.arm) pick(chosen, button.dataset.key);
      }));
    arm.addEventListener("pointerdown", () => {
      if (chosen !== arm.dataset.arm) say("noArm", true);
    });
  });
  next.addEventListener("click", (event) => { event.preventDefault(); moveOn(); });

  document.addEventListener("keydown", (event) => {
    if (event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
    const key = event.key.toLowerCase();
    if (armOfKey.has(key)) {
      choose(armOfKey.get(key));
    } else if (/^[0-9]$/.test(key)) {
      const arm = chosen && byName.get(chosen);
      if (!arm) return say("noArm", true);
      if (arm.querySelector(`.label[data-key="${key}"]`)) pick(chosen, key);
    } else if (key === "arrowright") {
      event.preventDefault();
      moveOn();
    } else if (key === "arrowleft" && page.dataset.previous) {
      event.preventDefault();
      location.href = page.dataset.previous;
    }
  });

  rest();
})();

// Finished page: the labels are uploaded to the RDM in the background, so the
// page shows at once. Ask for the outcome until it is in, then show it in
// place of the "uploading" note.
(function () {
  const box = document.getElementById("upload-outcome");
  if (!box) return;
  const ask = async () => {
    try {
      const answer = await fetch(box.dataset.outcomeUrl, { cache: "no-store" });
      if (answer.status === 200) return (box.innerHTML = await answer.text());
    } catch {
      // The app did not answer: keep the note and ask again.
    }
    setTimeout(ask, 800);
  };
  ask();
})();

// Slow forms: a submit button with data-busy shows a spinner and that text
// once its form is sent, and cannot be pressed twice, until the next page
// arrives. A .busy-note in the same form is shown as well.
document.querySelectorAll("button[data-busy]").forEach((button) => {
  const form = button.form;
  if (!form) return;
  const idle = button.textContent;
  const note = form.querySelector(".busy-note");
  const set = (busy) => {
    button.classList.toggle("busy", busy);
    button.textContent = busy ? button.dataset.busy : idle;
    button.setAttribute("aria-busy", busy);
    if (note) note.hidden = !busy;
    // Disable after the form has gone, or the browser would not send it.
    setTimeout(() => (button.disabled = busy), 0);
  };
  form.addEventListener("submit", () => set(true));
  // Coming back with the Back button shows the page as it was left.
  window.addEventListener("pageshow", (e) => e.persisted && set(false));
});

// Developer mode (app started with --dev): reload this page when any of the
// app's files change. The server restarts on a change to the code, so a
// failed request just means "ask again in a moment".
(function () {
  const url = document.body.dataset.devStampUrl;
  if (!url) return;
  let seen = null;
  const ask = async () => {
    try {
      const { stamp } = await (await fetch(url, { cache: "no-store" })).json();
      if (seen !== null && stamp !== seen) return location.reload();
      seen = stamp;
    } catch { /* the server is restarting */ }
    setTimeout(ask, 1000);
  };
  ask();
})();
