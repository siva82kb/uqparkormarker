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

  const draw = (p) => {
    const share = p.total ? (100 * p.done) / p.total : 0;
    bar.setAttribute("aria-valuemax", p.total);
    bar.setAttribute("aria-valuenow", p.done);
    set("progress-fill", (e) => (e.style.width = `${share}%`));
    set("progress-count", (e) => (e.textContent = p.total
      ? `${p.done} of ${p.total} · ${Math.floor(share)}%`
      : "Preparing"));
    set("clip-total", (e) => p.total && (e.textContent = p.total));
    set("progress-message", (e) => (e.textContent = p.message || "Starting…"));
    set("progress-error", (e) => { e.textContent = p.error; e.hidden = !p.error; });
    set("progress-help", (e) => (e.hidden = p.state === "done"));
  };

  const poll = async () => {
    let progress;
    try {
      progress = await (await fetch(bar.dataset.statusUrl, { cache: "no-store" })).json();
    } catch {
      set("progress-message", (e) => (e.textContent = "Lost contact with the app. Is it still running?"));
      return setTimeout(poll, 3 * POLL_MS);
    }
    draw(progress);
    if (progress.state === "running") return setTimeout(poll, POLL_MS);
    if (progress.state === "done" && "reloadWhenDone" in bar.dataset) location.reload();
  };

  poll();
})();
