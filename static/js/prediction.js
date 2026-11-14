/* Yeni musteri tahmini: form dogrulama, API cagrisi ve sonucun gosterimi */
(function () {
  const form = document.getElementById("predict-form");
  const resultBody = document.getElementById("result-body");
  const resultCard = document.getElementById("result-card");
  const pageError = document.getElementById("page-error");
  const submitBtn = document.getElementById("submit-btn");
  const spinner = document.getElementById("submit-spinner");
  const submitLabel = document.getElementById("submit-label");

  /* Kurgusal ornek musteriler */
  const SAMPLES = {
    low: {
      Age: 29, Gender: "Male", Geography: "Ic Anadolu", CreditScore: 720, Tenure: 6,
      Balance: 85000, EstimatedSalary: 95000, NumOfProducts: 2, Complaints: 0, HasCrCard: 1, IsActiveMember: 1,
    },
    high: {
      Age: 55, Gender: "Female", Geography: "Ege", CreditScore: 580, Tenure: 2,
      Balance: 120000, EstimatedSalary: 60000, NumOfProducts: 3, Complaints: 2, HasCrCard: 1, IsActiveMember: 0,
    },
  };
  const LEVEL_INDEX = { low: 0, medium: 1, high: 2 };

  let requestCounter = 0;
  let historyCache = null;   // gecmis veride risk gruplarinin gercek ayrilma oranlari

  /* ---------------------------------------------------------- hata gosterimi */
  function fieldElement(name) { return form.elements[name]; }

  function showFieldError(name, message) {
    const input = fieldElement(name);
    if (!input) return;
    input.classList.add("is-invalid");
    const feedback = input.parentElement.querySelector(".invalid-feedback");
    if (feedback) feedback.textContent = message;
  }

  function clearErrors() {
    form.querySelectorAll(".is-invalid").forEach((el) => el.classList.remove("is-invalid"));
    form.querySelectorAll(".invalid-feedback").forEach((el) => { el.textContent = ""; });
    pageError.classList.add("d-none");
  }

  function showPageError(message) {
    pageError.textContent = message;
    pageError.classList.remove("d-none");
  }

  function clientMessage(input) {
    const v = input.validity;
    const label = input.dataset.label || "Bu alan";
    if (v.valueMissing) return label + " zorunludur.";
    if (v.badInput) return label + " sayı olmalıdır.";
    if (v.rangeUnderflow || v.rangeOverflow) {
      return label + " " + fmt.int(input.min) + " ile " + fmt.int(input.max) + " arasında olmalıdır.";
    }
    if (v.stepMismatch) return label + " tam sayı olmalıdır.";
    return label + " geçersiz.";
  }

  form.addEventListener("input", (event) => event.target.classList.remove("is-invalid"));
  form.addEventListener("change", (event) => event.target.classList.remove("is-invalid"));

  /* ------------------------------------------------------------ yukleniyor */
  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    spinner.classList.toggle("d-none", !isLoading);
    submitLabel.textContent = isLoading ? "Hesaplanıyor…" : "Tahmin Et";
  }

  /* ------------------------------------------------------------- sonuc */
  function formatFactorValue(feature, value) {
    if (value === null || value === undefined) return "Bilinmiyor";
    switch (feature) {
      case "HasCrCard": return Number(value) ? "Var" : "Yok";
      case "IsActiveMember": return Number(value) ? "Aktif" : "Pasif";
      case "Gender": return GENDER_LABELS[value] || value;
      case "Balance":
      case "EstimatedSalary": return fmt.money(value);
      default: return typeof value === "number" ? Number(value).toLocaleString("tr-TR", { maximumFractionDigits: 0 }) : value;
    }
  }

  function factorsHtml(factors) {
    if (!factors.length) {
      return '<span class="text-muted small">Belirgin bir etken bulunamadı: müşteri tipik bir profile yakın.</span>';
    }
    const maxImpact = Math.max(...factors.map((f) => Math.abs(f.impact_pct_points)));
    return factors.map((f) => {
      const up = f.direction === "increases";
      const width = Math.max(3, (Math.abs(f.impact_pct_points) / maxImpact) * 100);
      const amount = Math.abs(f.impact_pct_points).toLocaleString("tr-TR", { minimumFractionDigits: 1 });
      return (
        '<div class="factor-row"><div class="factor-head"><span><strong>' + escapeHtml(f.label) + "</strong> " +
        '<span class="text-muted">' + escapeHtml(formatFactorValue(f.feature, f.value)) + "</span></span>" +
        '<span class="' + (up ? "impact-up" : "impact-down") + '">' + (up ? "+" : "−") + amount + " puan</span></div>" +
        '<div class="factor-bar-track"><div class="factor-bar ' + (up ? "factor-up" : "factor-down") +
        '" style="width:' + width + '%"></div></div></div>'
      );
    }).join("");
  }

  async function loadHistory() {
    if (historyCache) return historyCache;
    try {
      const charts = await api("/api/dashboard/charts");
      historyCache = charts.risk_by_outcome;
    } catch (error) {
      historyCache = null;
    }
    return historyCache;
  }

  function historyHtml(data, history) {
    if (!history) return "";
    const i = LEVEL_INDEX[data.risk_level];
    const total = history.stayed[i] + history.churned[i];
    if (!total) return "";
    const rate = (history.churned[i] / total) * 100;
    return (
      '<div class="alert alert-info small mt-3 mb-0">Geçmiş verilerde <strong>' + escapeHtml(data.risk_label) +
      "</strong> risk grubundaki müşterilerin <strong>" + fmt.pct(rate) + "</strong> kadarı bankadan ayrıldı. " +
      "Yukarıdaki yüzde, müşterileri riske göre sıralayan bir model skorudur; gerçek ayrılma oranı değildir.</div>"
    );
  }

  function renderResult(data, history) {
    const low = data.thresholds.low_max * 100;
    const high = data.thresholds.high_min * 100;
    const level = escapeHtml(data.risk_level);
    const gradient =
      "linear-gradient(to right, var(--risk-low) 0%, var(--risk-low) " + low + "%, var(--risk-medium) " + low + "%, " +
      "var(--risk-medium) " + high + "%, var(--risk-high) " + high + "%, var(--risk-high) 100%)";
    const marker = Math.min(100, Math.max(0, data.probability_pct));

    resultBody.innerHTML =
      '<div class="d-flex align-items-center justify-content-between flex-wrap gap-2">' +
        '<div><div class="text-muted small">Tahmini ayrılma olasılığı</div>' +
        '<div class="big-prob risk-text-' + level + '">' + fmt.pct(data.probability_pct) + "</div></div>" +
        '<span class="badge-soft badge-risk-' + level + ' fs-6">' + escapeHtml(data.risk_label) + " risk</span>" +
      "</div>" +
      '<div class="gauge" style="background:' + gradient + '"><div class="gauge-marker" style="left:' + marker + '%"></div></div>' +
      '<div class="gauge-scale"><span>%0</span><span>%' + Math.round(low) + "</span><span>%" + Math.round(high) + "</span><span>%100</span></div>" +
      '<p class="small text-muted mt-2 mb-0">Eşikler: Düşük %' + Math.round(low) + " altı, Orta %" + Math.round(low) +
      "–%" + Math.round(high) + ", Yüksek %" + Math.round(high) + " ve üzeri.</p>" +
      historyHtml(data, history) +
      '<h3 class="h6 mt-4">Riski etkileyen faktörler</h3>' +
      '<p class="small text-muted">Her çubuk, özelliğin olasılığı tipik müşteriye göre kaç puan artırdığını (kırmızı) ya da azalttığını (yeşil) gösterir.</p>' +
      factorsHtml(data.factors) +
      '<div class="alert alert-light border small mt-3 mb-0">' + escapeHtml(data.disclaimer) + " Veriler kurgusaldır.</div>";

    if (window.innerWidth < 992) resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ------------------------------------------------------------- gonderim */
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors();

    const invalid = [...form.elements].filter((el) => el.name && !el.checkValidity());
    if (invalid.length) {
      invalid.forEach((el) => showFieldError(el.name, clientMessage(el)));
      invalid[0].focus();
      showPageError("Lütfen işaretli alanları düzeltip tekrar deneyin.");
      return;
    }

    const payload = {};
    [...form.elements].forEach((el) => { if (el.name) payload[el.name] = el.value.trim(); });

    const myRequest = ++requestCounter;
    setLoading(true);
    try {
      const data = await api("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const history = await loadHistory();
      if (myRequest !== requestCounter) return;
      renderResult(data, history);
    } catch (error) {
      if (myRequest !== requestCounter) return;
      if (error.details) {
        Object.keys(error.details).forEach((name) => showFieldError(name, error.details[name]));
        showPageError(error.message);
      } else {
        showPageError(error.message);
      }
    } finally {
      if (myRequest === requestCounter) setLoading(false);
    }
  });

  /* ------------------------------------------------------ ornek / temizle */
  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      const sample = SAMPLES[button.dataset.sample];
      clearErrors();
      Object.keys(sample).forEach((name) => { form.elements[name].value = String(sample[name]); });
      form.requestSubmit();
    });
  });

  form.addEventListener("reset", () => {
    requestCounter++;
    clearErrors();
    setLoading(false);
    resultBody.innerHTML =
      '<div class="result-placeholder">Formu doldurup <strong>Tahmin Et</strong> düğmesine basın.<br>Sonuç burada görünecek.</div>';
  });
})();