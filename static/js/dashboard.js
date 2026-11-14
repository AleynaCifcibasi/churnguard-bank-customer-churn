/* Dashboard: kartlari ve grafikleri API verisiyle doldurur */
(function () {
  const COLORS = {
    stay: "#3b82f6", churn: "#ef4444", low: "#16a34a", medium: "#f59e0b",
    high: "#dc2626", violet: "#8b5cf6", teal: "#0d9488", slate: "#94a3b8",
  };

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = "#475569";

  /* Cubuklarin ustune degerleri yazan kucuk eklenti */
  const valueLabels = {
    id: "valueLabels",
    afterDatasetsDraw(chart, args, opts) {
      if (!opts || !opts.enabled) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.font = "600 12px " + Chart.defaults.font.family;
      ctx.fillStyle = "#334155";
      ctx.textAlign = "center";
      chart.data.datasets.forEach((dataset, index) => {
        if (dataset.type === "line") return;
        chart.getDatasetMeta(index).data.forEach((bar, i) => {
          ctx.fillText(opts.format(dataset.data[i]), bar.x, bar.y - 6);
        });
      });
      ctx.restore();
    },
  };

  function setField(name, text) {
    const el = document.querySelector('[data-field="' + name + '"]');
    if (!el) return;
    el.textContent = text;
    el.classList.remove("skeleton");
  }

  function renderCards(summary) {
    setField("total_customers", fmt.int(summary.total_customers));
    setField("churned_customers", fmt.int(summary.churned_customers));
    setField("active_customers", fmt.int(summary.active_customers));
    setField("churn_rate_pct", fmt.pct(summary.churn_rate_pct));

    const risk = summary.risk_counts_active;
    const low = Math.round(summary.thresholds.low_max * 100);
    const high = Math.round(summary.thresholds.high_min * 100);
    setField("risk_high", fmt.int(risk.high));
    setField("risk_medium", fmt.int(risk.medium));
    setField("risk_low", fmt.int(risk.low));
    setField("risk_high_range", "Olasılık %" + high + " ve üzeri");
    setField("risk_medium_range", "Olasılık %" + low + " – %" + high + " arası");
    setField("risk_low_range", "Olasılık %" + low + " altında");
  }

  function doughnut(canvasId, labels, values, colors) {
    new Chart(document.getElementById(canvasId), {
      type: "doughnut",
      data: {
        labels: labels.map((label, i) => label + ": " + fmt.int(values[i])),
        datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: "#fff" }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: "62%",
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label(ctx) {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const share = total ? (ctx.parsed / total) * 100 : 0;
                return " " + ctx.label + " (" + fmt.pct(share) + ")";
              },
            },
          },
        },
      },
    });
  }

  function rateBar(canvasId, block, overall, color) {
    new Chart(document.getElementById(canvasId), {
      type: "bar",
      data: {
        labels: block.labels,
        datasets: [
          { type: "bar", label: "Kayıp oranı", data: block.churn_rate_pct, backgroundColor: color, borderRadius: 6, maxBarThickness: 64, pointStyle: "rectRounded" },
          { type: "line", label: "Genel ortalama", data: block.labels.map(() => overall), borderColor: COLORS.slate,
            borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 0, pointStyle: "line" },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true } },
          valueLabels: { enabled: true, format: (v) => fmt.pct(v) },
          tooltip: {
            callbacks: {
              label(ctx) {
                return " " + ctx.dataset.label + ": " + fmt.pct(ctx.parsed.y);
              },
              afterLabel(ctx) {
                if (ctx.dataset.type === "line") return "";
                return " " + fmt.int(block.churned[ctx.dataIndex]) + " / " + fmt.int(block.total[ctx.dataIndex]) + " müşteri ayrıldı";
              },
            },
          },
        },
        scales: {
          y: { beginAtZero: true, grace: "15%", ticks: { callback: (v) => v + "%" }, grid: { color: "#eef2f7" } },
          x: { grid: { display: false } },
        },
      },
      plugins: [valueLabels],
    });
  }

  function renderCharts(charts, summary) {
    const overall = summary.churn_rate_pct;

    doughnut("chart-churn", charts.churn_distribution.labels, charts.churn_distribution.values, [COLORS.stay, COLORS.churn]);
    doughnut("chart-risk", charts.risk_distribution_active.labels, charts.risk_distribution_active.values,
      [COLORS.low, COLORS.medium, COLORS.high]);

    rateBar("chart-age", charts.churn_by_age, overall, COLORS.stay);
    rateBar("chart-gender", charts.churn_by_gender, overall, COLORS.violet);
    rateBar("chart-card", charts.churn_by_credit_card, overall, COLORS.teal);
    rateBar("chart-segment", charts.churn_by_segment, overall, COLORS.medium);

    const outcome = charts.risk_by_outcome;
    new Chart(document.getElementById("chart-outcome"), {
      type: "bar",
      data: {
        labels: outcome.labels,
        datasets: [
          { label: "Bankada kaldı", data: outcome.stayed, backgroundColor: COLORS.stay, borderRadius: 4 },
          { label: "Ayrıldı", data: outcome.churned, backgroundColor: COLORS.churn, borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true, grid: { color: "#eef2f7" }, ticks: { callback: (v) => fmt.int(v) } },
        },
      },
    });

    const parts = outcome.labels.map((label, i) => {
      const total = outcome.stayed[i] + outcome.churned[i];
      const rate = total ? (outcome.churned[i] / total) * 100 : 0;
      return label + " risk grubunda ayrılan oranı " + fmt.pct(rate);
    });
    document.getElementById("outcome-caption").textContent = parts.join(" · ") + ".";
  }

  async function init() {
    try {
      const [summary, charts] = await Promise.all([
        api("/api/dashboard/summary"),
        api("/api/dashboard/charts"),
      ]);
      renderCards(summary);
      renderCharts(charts, summary);
    } catch (error) {
      const box = document.getElementById("page-error");
      box.textContent = error.message;
      box.classList.remove("d-none");
    }
  }

  init();
})();