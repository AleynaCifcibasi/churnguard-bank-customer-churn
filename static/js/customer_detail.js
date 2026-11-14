/* Musteri detayi: olasilik gostergesi, bilgiler ve risk faktorleri */
(function () {
  const root = document.getElementById("detail-root");
  const customerId = root.dataset.customerId;

  function $(id) { return document.getElementById(id); }

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

  function renderGauge(customer, thresholds) {
    const low = thresholds.low_max * 100;
    const high = thresholds.high_min * 100;
    $("d-prob").textContent = fmt.pct(customer.churn_probability_pct);
    $("d-gauge").style.background =
      "linear-gradient(to right, var(--risk-low) 0%, var(--risk-low) " + low + "%, var(--risk-medium) " + low + "%, " +
      "var(--risk-medium) " + high + "%, var(--risk-high) " + high + "%, var(--risk-high) 100%)";
    $("d-marker").style.left = Math.min(100, Math.max(0, customer.churn_probability_pct)) + "%";
    $("d-low-mark").textContent = "%" + Math.round(low);
    $("d-high-mark").textContent = "%" + Math.round(high);
    $("d-risk-text").textContent =
      "Güncel eşiklere göre bu müşteri " + customer.risk_label.toLowerCase() + " risk grubunda. " +
      "Düşük: %" + Math.round(low) + " altı, Orta: %" + Math.round(low) + "–%" + Math.round(high) + ", Yüksek: %" + Math.round(high) + " ve üzeri.";
  }

  function renderInfo(c) {
    const rows = [
      ["Yaş", c.age],
      ["Cinsiyet", GENDER_LABELS[c.gender] || c.gender],
      ["Bölge", c.geography || "Bilinmiyor"],
      ["Kredi skoru", c.credit_score === null ? "Bilinmiyor" : Math.round(c.credit_score)],
      ["Müşteri süresi", c.tenure + " yıl"],
      ["Hesap bakiyesi", fmt.money(c.balance)],
      ["Tahmini maaş", c.estimated_salary === null ? "Bilinmiyor" : fmt.money(c.estimated_salary)],
      ["Ürün sayısı", c.num_products],
      ["Kredi kartı", c.has_credit_card ? "Var" : "Yok"],
      ["Aktif üyelik", c.is_active_member ? "Aktif" : "Pasif"],
      ["Şikayet sayısı", c.complaints],
      ["Segment", c.segment],
    ];
    $("d-info").innerHTML = rows.map((r) => "<div><dt>" + escapeHtml(r[0]) + "</dt><dd>" + escapeHtml(r[1]) + "</dd></div>").join("");
  }

  function renderFactors(factors) {
    if (!factors.length) {
      $("d-factors").innerHTML = '<span class="text-muted">Belirgin bir etken bulunamadı: müşteri tipik bir profile yakın.</span>';
      return;
    }
    const maxImpact = Math.max(...factors.map((f) => Math.abs(f.impact_pct_points)));
    $("d-factors").innerHTML = factors.map((f) => {
      const up = f.direction === "increases";
      const width = Math.max(3, (Math.abs(f.impact_pct_points) / maxImpact) * 100);
      const sign = up ? "+" : "−";
      const amount = Math.abs(f.impact_pct_points).toLocaleString("tr-TR", { minimumFractionDigits: 1 });
      return (
        '<div class="factor-row"><div class="factor-head"><span><strong>' + escapeHtml(f.label) + "</strong> " +
        '<span class="text-muted">' + escapeHtml(formatFactorValue(f.feature, f.value)) +
        " (tipik: " + escapeHtml(formatFactorValue(f.feature, f.typical_value)) + ")</span></span>" +
        '<span class="' + (up ? "impact-up" : "impact-down") + '">' + sign + amount + " puan</span></div>" +
        '<div class="factor-bar-track"><div class="factor-bar ' + (up ? "factor-up" : "factor-down") +
        '" style="width:' + width + '%"></div></div></div>'
      );
    }).join("");
  }

  async function init() {
    try {
      const [customer, settings] = await Promise.all([
        api("/api/customers/" + encodeURIComponent(customerId)),
        api("/api/settings"),
      ]);
      $("d-id").textContent = customer.customer_id;
      $("d-badges").innerHTML =
        '<span class="badge-soft badge-risk-' + escapeHtml(customer.risk_level) + '">' + escapeHtml(customer.risk_label) + " risk</span>" +
        (customer.exited
          ? '<span class="badge-soft badge-churned">Bankadan ayrıldı</span>'
          : '<span class="badge-soft badge-stayed">Bankada müşteri</span>');
      renderGauge(customer, settings.risk_thresholds);
      renderInfo(customer);
      renderFactors(customer.factors);
      $("d-disclaimer").textContent = customer.disclaimer + " Veriler kurgusaldır.";
    } catch (error) {
      const box = $("page-error");
      box.textContent = error.message;
      box.classList.remove("d-none");
      $("d-factors").textContent = "";
    }
  }

  init();
})();