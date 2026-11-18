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

// Clip generation: ask the server for progress and redraw the bar and the
// status line in place, until the job is done or has failed.
(function () {
  const bar = document.getElementById("progress");
  if (!bar) return;
  const byId = (id) => document.getElementById(id);
  const POLL_MS = 600;

  const draw = (p) => {
    const share = p.total ? (100 * p.done) / p.total : 0;
    byId("progress-fill").style.width = `${share}%`;
    bar.setAttribute("aria-valuemax", p.total);
    bar.setAttribute("aria-valuenow", p.done);
    byId("progress-count").textContent = p.total
      ? `${p.done} of ${p.total} · ${Math.floor(share)}%`
      : "Preparing";
    if (p.total) byId("clip-total").textContent = p.total;
    byId("progress-message").textContent = p.message || "Starting…";
    byId("progress-error").textContent = p.error;
    byId("progress-error").hidden = !p.error;
    byId("progress-help").hidden = p.state === "done";
  };

  const poll = async () => {
    let progress;
    try {
      progress = await (await fetch(bar.dataset.statusUrl, { cache: "no-store" })).json();
    } catch {
      byId("progress-message").textContent = "Lost contact with the app. Is it still running?";
      return setTimeout(poll, 3 * POLL_MS);
    }
    draw(progress);
    if (progress.state === "running") setTimeout(poll, POLL_MS);
  };

  poll();
})();
