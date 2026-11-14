/* Musteri listesi: arama, filtre, siralama ve sunucu tarafli sayfalama */
(function () {
  const PER_PAGE = 25;
  const SORTABLE = ["customer_id", "age", "credit_score", "balance", "num_products", "churn_probability"];
  const DEFAULTS = {
    page: 1, search: "", risk: "", gender: "", segment: "",
    active_member: "", status: "", sort_by: "customer_id", sort_order: "asc",
  };
  const FILTER_INPUTS = {
    search: "f-search", risk: "f-risk", status: "f-status",
    gender: "f-gender", segment: "f-segment", active_member: "f-active",
  };

  const state = Object.assign({}, DEFAULTS);
  const el = {
    body: document.getElementById("customers-body"),
    table: document.getElementById("customers-table"),
    info: document.getElementById("page-info"),
    pagination: document.getElementById("pagination"),
    error: document.getElementById("page-error"),
  };
  let requestCounter = 0;

  /* ---- URL ile durum senkronu (geri donunce filtreler kaybolmasin) ---- */
  function readUrl() {
    const params = new URLSearchParams(window.location.search);
    Object.keys(DEFAULTS).forEach((key) => {
      if (!params.has(key)) return;
      state[key] = key === "page" ? Math.max(1, parseInt(params.get(key), 10) || 1) : params.get(key);
    });
    if (!SORTABLE.includes(state.sort_by)) state.sort_by = DEFAULTS.sort_by;
    if (!["asc", "desc"].includes(state.sort_order)) state.sort_order = DEFAULTS.sort_order;
    Object.keys(FILTER_INPUTS).forEach((key) => {
      const input = document.getElementById(FILTER_INPUTS[key]);
      if (input.tagName === "SELECT" && ![...input.options].some((o) => o.value === state[key])) state[key] = "";
      input.value = state[key];
    });
  }

  function syncUrl() {
    const params = new URLSearchParams();
    Object.keys(DEFAULTS).forEach((key) => {
      if (String(state[key]) !== String(DEFAULTS[key])) params.set(key, state[key]);
    });
    const query = params.toString();
    history.replaceState(null, "", window.location.pathname + (query ? "?" + query : ""));
  }

  /* ---- Veri yukleme ---- */
  async function load() {
    const myRequest = ++requestCounter;       // eski cevaplar yenisini ezmesin
    el.table.classList.add("is-loading");
    el.error.classList.add("d-none");

    const params = new URLSearchParams({
      page: state.page, per_page: PER_PAGE, sort_by: state.sort_by, sort_order: state.sort_order,
    });
    ["search", "risk", "gender", "segment", "active_member", "status"].forEach((key) => {
      if (state[key] !== "") params.set(key, state[key]);
    });

    try {
      const data = await api("/api/customers?" + params.toString());
      if (myRequest !== requestCounter) return;
      state.page = data.page;
      renderRows(data.items);
      renderPagination(data);
      renderSortIndicators();
      syncUrl();
    } catch (error) {
      if (myRequest !== requestCounter) return;
      el.error.textContent = error.message;
      el.error.classList.remove("d-none");
    } finally {
      if (myRequest === requestCounter) el.table.classList.remove("is-loading");
    }
  }

  /* ---- Cizim ---- */
  function riskBadge(item) {
    return '<span class="badge-soft badge-risk-' + escapeHtml(item.risk_level) + '">' + escapeHtml(item.risk_label) + "</span>";
  }

  function renderRows(items) {
    if (!items.length) {
      el.body.innerHTML = '<tr><td colspan="10" class="empty-state">Filtrelere uygun müşteri bulunamadı.</td></tr>';
      return;
    }
    el.body.innerHTML = items.map((c) => {
      const id = escapeHtml(c.customer_id);
      const width = Math.max(2, Math.min(100, c.churn_probability_pct));
      return (
        '<tr data-href="/customers/' + id + '">' +
        '<td><a class="fw-semibold text-decoration-none" href="/customers/' + id + '">' + id + "</a></td>" +
        "<td>" + escapeHtml(c.age) + "</td>" +
        "<td>" + escapeHtml(GENDER_LABELS[c.gender] || c.gender) + "</td>" +
        "<td>" + (c.credit_score === null ? "—" : escapeHtml(Math.round(c.credit_score))) + "</td>" +
        '<td class="text-end">' + fmt.money(c.balance) + "</td>" +
        '<td class="text-center">' + escapeHtml(c.num_products) + "</td>" +
        "<td>" + (c.is_active_member
          ? '<span class="badge-soft badge-stayed">Aktif</span>'
          : '<span class="badge-soft badge-neutral">Pasif</span>') + "</td>" +
        '<td><div class="prob-cell"><div class="prob-track"><div class="prob-fill fill-' + escapeHtml(c.risk_level) +
        '" style="width:' + width + '%"></div></div><span class="prob-value">' + fmt.pct(c.churn_probability_pct) + "</span></div></td>" +
        "<td>" + riskBadge(c) + "</td>" +
        "<td>" + (c.exited
          ? '<span class="badge-soft badge-churned">Ayrıldı</span>'
          : '<span class="badge-soft badge-stayed">Müşteri</span>') + "</td>" +
        "</tr>"
      );
    }).join("");
  }

  function pageItems(current, total) {
    const pages = new Set([1, total, current - 1, current, current + 1]);
    if (current <= 3) [2, 3, 4].forEach((p) => pages.add(p));
    if (current >= total - 2) [total - 1, total - 2, total - 3].forEach((p) => pages.add(p));
    const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
    const out = [];
    sorted.forEach((p, i) => {
      if (i > 0 && p - sorted[i - 1] > 1) out.push("…");
      out.push(p);
    });
    return out;
  }

  function renderPagination(data) {
    const from = data.total ? (data.page - 1) * data.per_page + 1 : 0;
    const to = Math.min(data.page * data.per_page, data.total);
    el.info.textContent = fmt.int(from) + "–" + fmt.int(to) + " / " + fmt.int(data.total) + " müşteri";

    const item = (label, page, disabled, active) =>
      '<li class="page-item' + (disabled ? " disabled" : "") + (active ? " active" : "") + '">' +
      '<a class="page-link" href="#" data-page="' + page + '">' + label + "</a></li>";

    let html = item("‹", data.page - 1, data.page <= 1, false);
    pageItems(data.page, data.total_pages).forEach((p) => {
      html += p === "…"
        ? '<li class="page-item disabled"><span class="page-link">…</span></li>'
        : item(fmt.int(p), p, false, p === data.page);
    });
    html += item("›", data.page + 1, data.page >= data.total_pages, false);
    el.pagination.innerHTML = html;
  }

  function renderSortIndicators() {
    el.table.querySelectorAll("th.sortable").forEach((th) => {
      th.classList.remove("sorted-asc", "sorted-desc");
      if (th.dataset.sort === state.sort_by) th.classList.add("sorted-" + state.sort_order);
    });
  }

  /* ---- Olaylar ---- */
  function setFilter(key, value) {
    state[key] = value;
    state.page = 1;
    load();
  }

  let searchTimer = null;
  document.getElementById(FILTER_INPUTS.search).addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    const value = event.target.value.trim();
    searchTimer = setTimeout(() => setFilter("search", value), 300);
  });
  Object.keys(FILTER_INPUTS).filter((k) => k !== "search").forEach((key) => {
    document.getElementById(FILTER_INPUTS[key]).addEventListener("change", (event) => setFilter(key, event.target.value));
  });

  document.getElementById("f-reset").addEventListener("click", () => {
    Object.assign(state, DEFAULTS);
    Object.values(FILTER_INPUTS).forEach((id) => { document.getElementById(id).value = ""; });
    load();
  });

  el.table.querySelector("thead").addEventListener("click", (event) => {
    const th = event.target.closest("th.sortable");
    if (!th) return;
    if (state.sort_by === th.dataset.sort) {
      state.sort_order = state.sort_order === "asc" ? "desc" : "asc";
    } else {
      state.sort_by = th.dataset.sort;
      state.sort_order = th.dataset.sort === "customer_id" ? "asc" : "desc";
    }
    state.page = 1;
    load();
  });

  el.pagination.addEventListener("click", (event) => {
    event.preventDefault();
    const link = event.target.closest("a[data-page]");
    if (!link || link.closest(".disabled")) return;
    state.page = parseInt(link.dataset.page, 10);
    load();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  el.body.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    const row = event.target.closest("tr[data-href]");
    if (row) window.location.href = row.dataset.href;
  });

  readUrl();
  load();
})();