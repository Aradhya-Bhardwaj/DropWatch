/* DropWatch charts. Each <canvas data-chart="..." data-source="id"> reads JSON written by the
   template's json_script tag, so views never build JavaScript strings. */
(function () {
  if (!window.Chart) return;
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  const INK = v("--ink"), INK_SOFT = v("--ink-soft"), MARIGOLD = v("--marigold"), TEAL = v("--teal");
  const MUTED = v("--muted"), GRID = v("--line-soft");
  const SERIES = [INK, MARIGOLD, TEAL, "#8a5bb0", "#5b6579"];

  Chart.defaults.font.family = '"Hind", system-ui, sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.color = MUTED;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.boxHeight = 12;
  Chart.defaults.plugins.tooltip.backgroundColor = INK;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.animation = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 400 };

  // Break long category labels onto two lines so they are not clipped
  const wrap = (label, max = 16) => {
    if (typeof label !== "string" || label.length <= max) return label;
    const words = label.split(" "), lines = [""];
    words.forEach((w) => {
      const cur = lines[lines.length - 1];
      if ((cur + " " + w).trim().length > max && cur) lines.push(w);
      else lines[lines.length - 1] = (cur + " " + w).trim();
    });
    return lines;
  };
  const pct = (x) => (x === null || x === undefined ? "hidden (small group)" : x.toFixed(1) + "%");
  const rateAxis = { beginAtZero: true, grid: { color: GRID }, border: { display: false },
                     ticks: { callback: (x) => x + "%" } };
  const catAxis = { grid: { display: false }, border: { color: v("--line") } };

  // A dashed line at the overall rate, so every bar reads as "above or below average"
  const referenceLine = {
    id: "reference",
    afterDatasetsDraw(chart, _args, opts) {
      if (opts.value === null || opts.value === undefined) return;
      const { ctx, chartArea, scales } = chart;
      const horizontal = chart.options.indexAxis === "y";
      const scale = horizontal ? scales.x : scales.y;
      const p = scale.getPixelForValue(opts.value);
      ctx.save();
      ctx.strokeStyle = INK; ctx.setLineDash([4, 4]); ctx.lineWidth = 1.25;
      ctx.beginPath();
      if (horizontal) { ctx.moveTo(p, chartArea.top); ctx.lineTo(p, chartArea.bottom); }
      else { ctx.moveTo(chartArea.left, p); ctx.lineTo(chartArea.right, p); }
      ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = INK; ctx.font = '600 12px "Hind", sans-serif';
      const label = "Overall " + opts.value.toFixed(1) + "%";
      if (horizontal) { ctx.textAlign = "left"; ctx.fillText(label, p + 6, chartArea.top + 12); }
      else { ctx.textAlign = "right"; ctx.fillText(label, chartArea.right, p - 6); }
      ctx.restore();
    },
  };

  function barColours(values, reference) {
    // Bars above 1.5x the overall rate take the alert colour; the rest stay ink
    return values.map((x) => (reference && x !== null && x >= reference * 1.5 ? MARIGOLD : INK_SOFT));
  }

  const builders = {
    bar(el, d) {
      return new Chart(el, {
        type: "bar",
        data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: barColours(d.values, d.reference),
                                                borderRadius: 4, maxBarThickness: 46 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false }, reference: { value: d.reference },
                   tooltip: { callbacks: { label: (c) => "Dropout " + pct(c.raw) } } },
                   scales: { y: rateAxis, x: catAxis } },
        plugins: [referenceLine],
      });
    },
    hbar(el, d) {
      return new Chart(el, {
        type: "bar",
        data: { labels: d.labels.map((l) => wrap(l, 22)), datasets: [{ data: d.values, backgroundColor: barColours(d.values, d.reference),
                                                borderRadius: 4, maxBarThickness: 22 }] },
        options: { indexAxis: "y", maintainAspectRatio: false,
                   plugins: { legend: { display: false }, reference: { value: d.reference },
                              tooltip: { callbacks: { label: (c) => "Dropout " + pct(c.raw) } } },
                   scales: { x: rateAxis, y: { ...catAxis, ticks: { autoSkip: false } } } },
        plugins: [referenceLine],
      });
    },
    share(el, d) {
      return new Chart(el, {
        type: "bar",
        data: { labels: d.labels.map((l) => wrap(l)), datasets: [{ data: d.values, backgroundColor: INK_SOFT, borderRadius: 4, maxBarThickness: 20 }] },
        options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false },
                   tooltip: { callbacks: { label: (c) => c.raw + "% of dropouts" } } },
                   scales: { x: { ...rateAxis, ticks: { callback: (x) => x + "%" } }, y: { ...catAxis, ticks: { autoSkip: false } } } },
      });
    },
    grouped(el, d) {
      return new Chart(el, {
        type: "bar",
        data: { labels: d.labels, datasets: d.series.map((s, i) => ({ label: s.label, data: s.values,
                backgroundColor: SERIES[i], borderRadius: 3, maxBarThickness: 18 })) },
        options: { maintainAspectRatio: false, plugins: { legend: { position: "top", align: "end" },
                   tooltip: { callbacks: { label: (c) => c.dataset.label + ": " + pct(c.raw) } } },
                   scales: { y: rateAxis, x: catAxis } },
      });
    },
    line(el, d) {
      const marker = d.marker;
      return new Chart(el, {
        type: "line",
        data: { labels: d.years, datasets: d.series.map((s, i) => ({ label: s.label, data: s.values,
                borderColor: SERIES[i % SERIES.length], backgroundColor: SERIES[i % SERIES.length],
                borderWidth: 2.5, pointRadius: 4, tension: 0, spanGaps: true })) },
        options: { maintainAspectRatio: false,
                   plugins: { legend: { display: d.series.length > 1, position: "top", align: "end" },
                              tooltip: { callbacks: { label: (c) => c.dataset.label + ": " + pct(c.raw) } } },
                   scales: { y: rateAxis, x: catAxis } },
        plugins: marker ? [{
          id: "start", afterDatasetsDraw(chart) {
            const x = chart.scales.x.getPixelForValue(d.years.indexOf(marker));
            const { ctx, chartArea } = chart;
            ctx.save(); ctx.strokeStyle = TEAL; ctx.setLineDash([4, 4]); ctx.beginPath();
            ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
            ctx.setLineDash([]); ctx.fillStyle = TEAL; ctx.font = '600 12px "Hind", sans-serif';
            const nearRight = x > chartArea.right - 100;
            ctx.textAlign = nearRight ? "right" : "left";
            ctx.fillText("Scheme starts", nearRight ? x - 6 : x + 6, chartArea.top + 12); ctx.restore();
          } }] : [],
      });
    },
  };

  document.querySelectorAll("canvas[data-chart]").forEach((el) => {
    const src = document.getElementById(el.dataset.source);
    if (!src) return;
    const build = builders[el.dataset.chart];
    if (build) build(el, JSON.parse(src.textContent));
  });
})();
