/* Ayarlar: risk esiklerini onizleme ile degistirme ve model bilgisi */
(function () {
  const lowInput = document.getElementById("low-input");
  const highInput = document.getElementById("high-input");
  const saveBtn = document.getElementById("save-btn");
  const revertBtn = document.getElementById("revert-btn");
  const defaultBtn = document.getElementById("default-btn");
  const form = document.getElementById("threshold-form");
  const message = document.getElementById("settings-message");
  const pageError = document.getElementById("page-error");

  let saved = { low: 30, high: 60 };       // kayitli degerler (yuzde)
  let defaults = { low: 30, high: 60 };
  let previewTimer = null;
  let previewCounter = 0;

  const toPercent = (fraction) => Number((fraction * 100).toFixed(1));

  /* ----------------------------------------------------------- dogrulama */
  function currentValues() {
    return { low: parseFloat(lowInput.value), high: parseFloat(highInput.value) };
  }

  function validate() {
    const { low, high } = currentValues();
    const errors = {};
    [["low", lowInput, "Düşük risk sınırı"], ["high", highInput, "Yüksek risk sınırı"]].forEach(([key, input, label]) => {
      const v = key === "low" ? low : high;
      if (input.value.trim() === "" || Number.isNaN(v)) errors[key] = label + " zorunludur ve sayı olmalıdır.";
      else if (v < 1 || v > 99) errors[key] = label + " 1 ile 99 arasında olmalıdır.";
    });
    if (!errors.low && !errors.high && low >= high) {
      errors.high = "Yüksek risk sınırı, düşük risk sınırından büyük olmalıdır.";
    }
    return errors;
  }

  function showErrors(errors) {
    [["low", lowInput], ["high", highInput]].forEach(([key, input]) => {
      input.classList.toggle("is-invalid", Boolean(errors[key]));
      input.parentElement.querySelector(".invalid-feedback").textContent = errors[key] || "";
    });
  }

  /* ----------------------------------------------------------- gorunum */
  function updateZoneBar(low, high) {
    document.getElementById("zone-bar").style.background =
      "linear-gradient(to right, var(--risk-low) 0%, var(--risk-low) " + low + "%, var(--risk-medium) " + low + "%, " +
      "var(--risk-medium) " + high + "%, var(--risk-high) " + high + "%, var(--risk-high) 100%)";
    document.getElementById("zone-low").textContent = "%" + low;
    document.getElementById("zone-high").textContent = "%" + high;
  }

  function updateButtons(errors) {
    const { low, high } = currentValues();
    const dirty = low !== saved.low || high !== saved.high;
    saveBtn.disabled = !dirty || Object.keys(errors).length > 0;
    revertBtn.disabled = !dirty;
  }

  function showMessage(type, text) {
    message.className = "alert alert-" + type;
    message.textContent = text;
  }

  function clearPreview() {
    ["low", "medium", "high"].forEach((k) => { document.getElementById("pv-" + k).textContent = "–"; });
  }

  /* ----------------------------------------------------------- onizleme */
  async function preview() {
    const errors = validate();
    showErrors(errors);
    updateButtons(errors);
    if (Object.keys(errors).length) { clearPreview(); return; }

    const { low, high } = currentValues();
    updateZoneBar(low, high);
    const myRequest = ++previewCounter;
    try {
      const data = await api("/api/settings/risk-thresholds/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ low_max: low / 100, high_min: high / 100 }),
      });
      if (myRequest !== previewCounter) return;
      const counts = data.summary.risk_counts_active;
      ["low", "medium", "high"].forEach((k) => { document.getElementById("pv-" + k).textContent = fmt.int(counts[k]); });
    } catch (error) {
      if (myRequest !== previewCounter) return;
      clearPreview();
      showMessage("danger", error.message);
    }
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    message.classList.add("d-none");
    previewTimer = setTimeout(preview, 250);
    updateButtons(validate());
  }

  function setInputs(values) {
    lowInput.value = values.low;
    highInput.value = values.high;
    message.classList.add("d-none");
    preview();
  }

  lowInput.addEventListener("input", schedulePreview);
  highInput.addEventListener("input", schedulePreview);
  revertBtn.addEventListener("click", () => setInputs(saved));
  defaultBtn.addEventListener("click", () => setInputs(defaults));

  /* -------------------------------------------------------------- kaydet */
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errors = validate();
    showErrors(errors);
    if (Object.keys(errors).length) return;

    const { low, high } = currentValues();
    saveBtn.disabled = true;
    try {
      const data = await api("/api/settings/risk-thresholds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ low_max: low / 100, high_min: high / 100 }),
      });
      saved = { low: toPercent(data.risk_thresholds.low_max), high: toPercent(data.risk_thresholds.high_min) };
      showMessage("success", "Eşikler kaydedildi: Düşük %" + saved.low + " altı, Yüksek %" + saved.high + " ve üzeri. " +
        "Dashboard, liste ve raporlar yeni eşiklere göre güncellendi.");
      updateButtons(validate());
      loadNotificationsSafe();
    } catch (error) {
      showMessage("danger", error.message);
      updateButtons(validate());
    }
  });

  function loadNotificationsSafe() {
    if (typeof loadNotifications === "function") loadNotifications();   // zil bildirimlerini yenile
  }

  /* ---------------------------------------------------------- model bilgisi */
  function renderModel(health) {
    const el = document.getElementById("model-info");
    if (!health || !health.test_metrics) {
      el.innerHTML = "<div><dt>Model bilgisi alınamadı</dt><dd></dd></div>";
      return;
    }
    const m = health.test_metrics;
    const rows = [
      ["Model", health.model_name],
      ["Eğitim tarihi", new Date(health.trained_at).toLocaleString("tr-TR")],
      ["Recall (yakalama oranı)", fmt.pct(m.recall * 100)],
      ["Precision (isabet oranı)", fmt.pct(m.precision * 100)],
      ["F1 skoru", Number(m.f1).toLocaleString("tr-TR", { minimumFractionDigits: 3 })],
      ["ROC-AUC", Number(m.roc_auc).toLocaleString("tr-TR", { minimumFractionDigits: 3 })],
      ["Model karar eşiği", Number(m.threshold).toLocaleString("tr-TR", { minimumFractionDigits: 3 })],
      ["Müşteri sayısı", fmt.int(health.n_customers)],
    ];
    el.innerHTML = rows.map((r) => "<div><dt>" + escapeHtml(r[0]) + "</dt><dd>" + escapeHtml(r[1]) + "</dd></div>").join("");
  }

  async function init() {
    try {
      const [settings, health] = await Promise.all([
        api("/api/settings"),
        api("/api/health").catch(() => null),
      ]);
      saved = { low: toPercent(settings.risk_thresholds.low_max), high: toPercent(settings.risk_thresholds.high_min) };
      defaults = { low: toPercent(settings.defaults.low_max), high: toPercent(settings.defaults.high_min) };
      setInputs(saved);
      renderModel(health);
    } catch (error) {
      pageError.textContent = error.message;
      pageError.classList.remove("d-none");
    }
  }

  init();
})();