/* Tum sayfalarda ortak kullanilan yardimci fonksiyonlar */

/** JSON API'sine istek atar; hata varsa anlasilir bir Error firlatir. */
async function api(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (networkError) {
    throw new Error("Sunucuya ulaşılamadı. Uygulamanın (python app.py) çalıştığından emin olun.");
  }
  let data = null;
  try {
    data = await response.json();
  } catch (parseError) {
    /* govde JSON degilse asagida genel hata verilir */
  }
  if (!response.ok) {
    const error = new Error((data && data.error) || "İstek başarısız oldu (" + response.status + ").");
    error.status = response.status;
    error.details = data && data.details;   // form alanlarina ozel hata mesajlari (422)
    throw error;
  }
  return data;
}

/** Kullanicidan/sunucudan gelen metni HTML'e guvenle koymak icin. */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const fmt = {
  int: (n) => Number(n).toLocaleString("tr-TR"),
  dec1: (n) => Number(n).toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  pct: (n) => "%" + Number(n).toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  money: (n) => Number(n).toLocaleString("tr-TR", { maximumFractionDigits: 0 }) + " ₺",
};

const GENDER_LABELS = { Female: "Kadın", Male: "Erkek" };

/** Ust bardaki bildirim zilini gercek verilerle doldurur. */
async function loadNotifications() {
  const badge = document.getElementById("notif-badge");
  const list = document.getElementById("notif-list");
  if (!badge || !list) return;
  try {
    const data = await api("/api/notifications");
    const items = data.items || [];
    badge.textContent = items.length;
    badge.classList.toggle("d-none", items.length === 0);
    list.innerHTML = items.length
      ? items.map((n) => (
          '<div class="notif-item"><span class="notif-dot ' + escapeHtml(n.level) + '"></span><span>' +
          escapeHtml(n.message) + "</span></div>"
        )).join("")
      : '<div class="notif-item text-muted">Yeni bildirim yok.</div>';
  } catch (error) {
    badge.classList.add("d-none");
    list.innerHTML = '<div class="notif-item text-muted">Bildirimler yüklenemedi.</div>';
  }
}

/** Mobilde sol menuyu acip kapatir. */
function setupSidebar() {
  const toggle = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (toggle) toggle.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
  if (backdrop) backdrop.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
}

document.addEventListener("DOMContentLoaded", () => {
  setupSidebar();
  loadNotifications();
});