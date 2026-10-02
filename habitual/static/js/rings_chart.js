// Shared by habits/detail.html and rooms/room.html - both render the same
// three-ring (week/month/milestone) doughnut off a #rings-chart canvas with
// the same data-week/data-month/data-milestone attributes. Chart.getChart
// (not a manually tracked variable) finds any existing instance to destroy,
// since the canvas can be a brand-new DOM node after an htmx OOB swap on
// either page.
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

  const accent = token("--color-accent");
  const text = token("--color-text");
  const streak = token("--color-streak");

  new Chart(canvas, {
    type: "doughnut",
    data: {
      datasets: [
        {
          data: [weekDone, remainder(weekDone, weekTotal)],
          backgroundColor: [accent, hexToRgba(accent, 0.16)],
          borderWidth: 0,
          radius: "100%",
          cutout: "78%",
        },
        {
          data: [monthDone, remainder(monthDone, monthTotal)],
          backgroundColor: [text, hexToRgba(text, 0.16)],
          borderWidth: 0,
          radius: "72%",
          cutout: "50%",
        },
        {
          data: [msDone, remainder(msDone, msTotal)],
          backgroundColor: [streak, hexToRgba(streak, 0.16)],
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
  const strengthBar = document.querySelector("[data-strength-bar]");
  if (strengthBar && window.gsap && !window.prefersReducedMotion && !document.hidden) {
    const target = parseFloat(strengthBar.dataset.strengthFraction);
    gsap.fromTo(strengthBar, { scaleX: 0 }, { scaleX: target, duration: 0.8, ease: "power2.out" });
  }
}
