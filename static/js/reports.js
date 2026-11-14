/* Raporlar: ozet tablolar, yuksek riskli liste ve CSV disa aktarma */
(function () {
  const pageError = document.getElementById("page-error");
  const exportMessage = document.getElementById("export-message");
  const GEO_LABELS = { "Ic Anadolu": "İç Anadolu", "Dogu Anadolu": "Doğu Anadolu", "Guneydogu Anadolu": "Güneydoğu Anadolu" };

  function setField(name, text) {
    const el = document.querySelector('[data-field="' + name + '"]');
    if (!el) return;
    el.textContent = text;
    el.classList.remove("skeleton");
  }

  /* ---------------------------------------------------------- ozet tablolar */
  function breakdownTable(containerId, block, overall) {
    const maxRate = Math.max(...block.churn_rate_pct, 1);
    const rows = block.labels.map((label, i) => {
      const rate = block.churn_rate_pct[i];
      const above = rate > overall;
      return (
        "<tr><td>" + escapeHtml(label) + '</td><td class="text-end">' + fmt.int(block.total[i]) + '</td><td class="text-end">' +
        fmt.int(block.churned[i]) + '</td><td style="min-width:170px"><div class="prob-cell"><div class="prob-track">' +
        '<div class="prob-fill ' + (above ? "fill-high" : "fill-stay") + '" style="width:' + (rate / maxRate) * 100 + '%"></div></div>' +
        '<span class="prob-value">' + fmt.pct(rate) + "</span></div></td></tr>"
      );
    }).join("");
    document.getElementById(containerId).innerHTML =
      '<div class="table-responsive"><table class="table table-sm align-middle mb-0"><thead><tr><th>Grup</th>' +
      '<th class="text-end">Müşteri</th><th class="text-end">Ayrılan</th><th>Kayıp oranı</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
  }

  /* ------------------------------------------------ yuksek riskli musteriler */
  function renderHighRisk(data) {
    document.getElementById("high-subtitle").textContent =
      fmt.int(data.total) + " aktif müşteri yüksek risk grubunda (riski en yüksek ilk " + data.items.length + " gösteriliyor)";
    const body = document.getElementById("high-body");
    if (!data.items.length) {
      body.innerHTML = '<tr><td colspan="7" class="text-muted">Bu eşiklere göre yüksek riskli aktif müşteri yok.</td></tr>';
      return;
    }
    body.innerHTML = data.items.map((c) => {
      const id = escapeHtml(c.customer_id);
      return (
        '<tr><td><a class="fw-semibold text-decoration-none" href="/customers/' + id + '">' + id + "</a></td>" +
        "<td>" + escapeHtml(c.age) + "</td><td>" + escapeHtml(GENDER_LABELS[c.gender] || c.gender) + "</td>" +
        '<td class="text-end">' + fmt.money(c.balance) + "</td>" +
        "<td>" + (c.is_active_member ? "Aktif" : "Pasif") + "</td>" +
        '<td class="fw-semibold">' + fmt.pct(c.churn_probability_pct) + "</td>" +
        '<td><span class="badge-soft badge-risk-' + escapeHtml(c.risk_level) + '">' + escapeHtml(c.risk_label) + "</span></td></tr>"
      );
    }).join("");
  }

  /* ----------------------------------------------------------- dosya listesi */
  function renderExports(items) {
    const body = document.getElementById("exports-body");
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="5" class="text-muted">Henüz rapor oluşturulmadı.</td></tr>';
      return;
    }
    body.innerHTML = items.map((f) => (
      "<tr><td><code>" + escapeHtml(f.filename) + "</code></td><td>" + escapeHtml(f.label) + '</td><td class="text-end">' +
      fmt.dec1(f.size_kb) + " KB</td><td>" + escapeHtml(new Date(f.created).toLocaleString("tr-TR")) + "</td>" +
      '<td class="text-end"><a class="btn btn-sm btn-outline-secondary" href="' + escapeHtml(f.download_url) + '">İndir</a></td></tr>'
    )).join("");
  }

  async function refreshExports() {
    try {
      renderExports((await api("/api/reports/exports")).items);
    } catch (error) {
      document.getElementById("exports-body").innerHTML = '<tr><td colspan="5" class="text-muted">Dosya listesi yüklenemedi.</td></tr>';
    }
  }

  /* -------------------------------------------------------------- dis aktarma */
  function showExportMessage(type, html) {
    exportMessage.className = "alert alert-" + type;
    exportMessage.innerHTML = html;
  }

  async function runExport(button) {
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = "Hazırlanıyor…";
    exportMessage.classList.add("d-none");
    try {
      const result = await api("/api/reports/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: button.dataset.export, format: document.getElementById("csv-format").value }),
      });
      showExportMessage("success",
        "<strong>" + escapeHtml(result.label) + "</strong> hazır: " + fmt.int(result.rows) + " satır, " + fmt.dec1(result.size_kb) +
        " KB. İndirme başlamazsa <a href=\"" + escapeHtml(result.download_url) + '">buraya tıklayın</a>. ' +
        "Dosya <code>exports/" + escapeHtml(result.filename) + "</code> konumuna da kaydedildi.");
      const link = document.createElement("a");
      link.href = result.download_url;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      refreshExports();
    } catch (error) {
      showExportMessage("danger", escapeHtml(error.message));
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  document.querySelectorAll("[data-export]").forEach((button) => {
    button.addEventListener("click", () => runExport(button));
  });

  /* ------------------------------------------------------------------ acilis */
  async function init() {
    try {
      const [summary, charts, high, exportsList] = await Promise.all([
        api("/api/dashboard/summary"),
        api("/api/dashboard/charts"),
        api("/api/customers?risk=high&status=active&sort_by=churn_probability&sort_order=desc&per_page=15"),
        api("/api/reports/exports"),
      ]);
      setField("total_customers", fmt.int(summary.total_customers));
      setField("churned_customers", fmt.int(summary.churned_customers));
      setField("churn_rate_pct", fmt.pct(summary.churn_rate_pct));
      setField("risk_high", fmt.int(summary.risk_counts_active.high));

      const overall = summary.churn_rate_pct;
      breakdownTable("tbl-segment", charts.churn_by_segment, overall);
      breakdownTable("tbl-age", charts.churn_by_age, overall);
      const geo = Object.assign({}, charts.churn_by_geography, {
        labels: charts.churn_by_geography.labels.map((l) => GEO_LABELS[l] || l),
      });
      breakdownTable("tbl-geo", geo, overall);
      breakdownTable("tbl-gender", charts.churn_by_gender, overall);
      renderHighRisk(high);
      renderExports(exportsList.items);
    } catch (error) {
      pageError.textContent = error.message;
      pageError.classList.remove("d-none");
    }
  }

  init();
})();