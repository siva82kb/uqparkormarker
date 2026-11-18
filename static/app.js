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
