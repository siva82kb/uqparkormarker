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
      ? `${p.done} of ${p.total} · ${Math.floor(share)}%`
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

// Annotation: a label is saved only while Shift is held down, whether it is
// given with a number key or with a click. A key or a click without Shift
// does nothing but say why, so a slip of the hand never becomes a label.
// Backspace (no Shift needed) shows the clip before this one.
(function () {
  const form = document.getElementById("annotate");
  if (!form) return;
  const hint = document.getElementById("annotate-hint");
  const buttons = [...form.querySelectorAll(".label")];
  const keys = new Set(buttons.map((button) => button.dataset.key));
  let sent = false;

  const arm = (on) => {               // show whether Shift is down
    document.body.classList.toggle("armed", on);
    hint.classList.remove("refused");
    hint.textContent = on ? hint.dataset.armed : hint.dataset.idle;
  };

  const refuse = () => {
    hint.classList.add("refused");
    hint.textContent = hint.dataset.refused;
  };

  const save = (key) => {
    if (sent) return;                 // one label per showing of a clip
    sent = true;
    document.getElementById("annotate-key").value = key;
    form.submit();
  };

  document.addEventListener("keydown", (event) => {
    if (event.key === "Shift") return arm(true);
    if (event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
    // event.code names the physical key, so Shift+1 is "Digit1", not "!".
    const digit = /^Digit(\d)$/.exec(event.code);
    if (digit && keys.has(digit[1])) {
      event.preventDefault();
      if (event.shiftKey) save(digit[1]);
      else refuse();
    } else if (event.key === "Backspace" && form.dataset.previous) {
      event.preventDefault();
      location.href = form.dataset.previous;
    }
  });
  document.addEventListener("keyup", (event) => {
    if (event.key === "Shift") arm(false);
  });
  window.addEventListener("blur", () => arm(false));   // Shift released elsewhere

  buttons.forEach((button) =>
    button.addEventListener("click", (event) => {
      if (event.shiftKey) save(button.dataset.key);
      else refuse();
    })
  );
})();
