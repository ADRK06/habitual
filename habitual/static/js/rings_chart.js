// Shared by habits/detail.html and rooms/room.html - both render the same
// three-ring (week/month/milestone) doughnut off a #rings-chart canvas with
// the same data-week/data-month/data-milestone attributes. Chart.getChart
// (not a manually tracked variable) finds any existing instance to destroy,
// since the canvas can be a brand-new DOM node after an htmx OOB swap on
// either page.
//
// Colours are read from the Colonies tokens (tailwind/input.css), never
// hardcoded hex, and mapped Week=Phosphor, Month=Steel, Milestone=Rust
// (Phase 1c group 4 - no mock shows this chart, so Month moved off Bone/
// --color-text: the palette table marks Bone "text" only, never a fill).
// No legend/tooltip is enabled, so there's no on-canvas text today, but
// Chart.js' own default font is still pointed at IBM Plex Mono (every
// number, per CLAUDE.md's Design direction) rather than its built-in
// sans-serif default, in case that ever changes.
if (window.Chart) {
  Chart.defaults.font.family = "'IBM Plex Mono', monospace";
}

function initRingsChart() {
  const canvas = document.getElementById("rings-chart");
  if (!canvas || !window.Chart) return;

  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const hexToRgba = (hex, alpha) => {
    const clean = hex.replace("#", "");
    const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean;
    const n = parseInt(full, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
  };
  const parsePair = (s) => s.split(",").map(Number);
  const [weekDone, weekTotal] = parsePair(canvas.dataset.week);
  const [monthDone, monthTotal] = parsePair(canvas.dataset.month);
  const [msDone, msTotal] = parsePair(canvas.dataset.milestone);
  const remainder = (done, total) => Math.max(total - done, 0);

  const phosphor = token("--color-phosphor");
  const steel = token("--color-steel");
  const rust = token("--color-rust");

  new Chart(canvas, {
    type: "doughnut",
    data: {
      datasets: [
        {
          data: [weekDone, remainder(weekDone, weekTotal)],
          backgroundColor: [phosphor, hexToRgba(phosphor, 0.16)],
          borderWidth: 0,
          radius: "100%",
          cutout: "78%",
        },
        {
          data: [monthDone, remainder(monthDone, monthTotal)],
          backgroundColor: [steel, hexToRgba(steel, 0.16)],
          borderWidth: 0,
          radius: "72%",
          cutout: "50%",
        },
        {
          data: [msDone, remainder(msDone, msTotal)],
          backgroundColor: [rust, hexToRgba(rust, 0.16)],
          borderWidth: 0,
          radius: "44%",
          cutout: "22%",
        },
      ],
    },
    options: {
      animation: window.prefersReducedMotion ? false : { animateRotate: true, duration: 900 },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    },
  });
}

function animateStrengthBar() {
  // querySelectorAll, not querySelector - the habit detail and room pages
  // only ever have one of these, but the dashboard now renders one per
  // habit card, and a bare querySelector would silently animate only the
  // first.
  if (!window.gsap || window.prefersReducedMotion || document.hidden) return;
  document.querySelectorAll("[data-strength-bar]").forEach((bar) => {
    const target = parseFloat(bar.dataset.strengthFraction);
    gsap.fromTo(bar, { scaleX: 0 }, { scaleX: target, duration: 0.8, ease: "power2.out" });
  });
}
