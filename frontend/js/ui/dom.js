export const $ = (id) => document.getElementById(id);

export function setText(id, txt) {
  const el = $(id);
  if (el) el.textContent = txt;
}

export function mkEl(tag, cls) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  return el;
}

export function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// a URL from an object is used as href or src only when it is http(s) or relative; other schemes are dropped
export function safeUrl(u) {
  const s = String(u ?? "").trim();
  return !s || (/^[a-z][a-z0-9+.-]*:/i.test(s) && !/^https?:/i.test(s)) ? "" : s;
}

export function setLoading(on, msg) {
  const el = $("loadingOverlay");
  if (!el) return;
  el.classList.toggle("hidden", !on);
  const sp = $("spinner");
  if (sp) sp.style.display = "";
  const p = el.querySelector("p");
  if (p && msg) p.textContent = msg;
}

export function showError(msg) {
  const el = $("loadingOverlay");
  if (!el) return;
  el.classList.remove("hidden");
  const sp = $("spinner");
  if (sp) sp.style.display = "none";
  const p = el.querySelector("p");
  if (p) {
    p.innerHTML =
      `<strong style="color:#ef4444">Error</strong><br>` +
      `<span style="font-size:.8rem">${esc(msg)}</span><br>` +
      `<button onclick="document.getElementById('loadingOverlay').classList.add('hidden')" ` +
      `style="margin-top:.5rem;padding:.4rem .8rem;cursor:pointer;border:1px solid #ccc;` +
      `border-radius:4px;background:#f8fafc">Dismiss</button>`;
  }
}
