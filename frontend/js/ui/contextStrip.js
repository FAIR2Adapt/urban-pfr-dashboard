// The strip between the header and the map: for each shown city, how the drawn layers are classified and with what
// status, the record the claims come from and its status, and the first claims. Everything is read from the dataset
// the adapters built; nothing here is interpreted. The full detail stays in the metadata overlay.
import { state, LAYERED } from "../state.js";
import { enabledMapPanels } from "../composition.js";
import { $, esc } from "./dom.js";
import { cityName } from "./sourceSelector.js";
import { statusText } from "../map/classes.js";
import { openStatements } from "./metadataPanel.js";

export function renderContextStrip() {
  const el = $("contextStrip");
  if (!el) return;
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);
  const blocks = ids.map((sid) => blockFor(sid, state.datasets[sid])).filter(Boolean);
  el.classList.toggle("hidden", !blocks.length);
  el.innerHTML = blocks.join("");
  el.querySelectorAll("[data-open-meta]").forEach((b) => b.addEventListener("click", () => openStatements()));
}

function blockFor(sid, ds) {
  const city = cityName(state.sources.find((s) => s.id === sid) || { id: sid, label: ds.label });
  const md = ds.metadata || {};
  const facts = [], byStatus = new Map();   // the layers on the map now, grouped by the status of their thresholds
  for (const p of LAYERED(ds) ? enabledMapPanels(sid, ds) : []) {
    const classified = Object.values(p.layer?.channels || {}).some((c) => Array.isArray(c?.breaks) && c.breaks.length);
    const status = statusText(p.layer?.classification?.thresholdStatus) || (classified ? "not stated" : "");
    if (status) byStatus.set(status, [...(byStatus.get(status) || []), p.label]);
  }
  if (byStatus.size === 1) facts.push(`class thresholds ${[...byStatus.keys()][0]}`);
  else for (const [status, labels] of byStatus) facts.push(`class thresholds ${status} (${labels.join(", ")})`);
  if (md.status) facts.push(`status: ${md.status}`);
  if (md.mapFrom) facts.push(`map: ${md.mapFrom.title || md.mapFrom.pid}${md.mapFrom.status ? ` (${md.mapFrom.status})` : ""}`);
  const claimsShown = ds.panels?.claims ? ds.panels.claims.available : true;   // the plan decides whether claims are a panel
  const all = claimsShown ? (ds.claims || []) : [];
  const claims = all.filter((c) => c.label && c.linkChecked !== false);   // a text the record does not confirm is counted, not quoted
  const unconfirmed = all.length - claims.length;
  const record = (ds.evidence || []).find((e) => e.usable);
  if (record && claims.length) facts.push(`claims from: ${record.title}${record.status ? ` (${record.status})` : ""}`);
  if (unconfirmed) facts.push(`${unconfirmed} claim${unconfirmed === 1 ? "" : "s"} not confirmed by the record (see scientific metadata)`);
  if (!facts.length && !claims.length) return null;
  const n = claims.length;
  return `<div class="context-city">
    <div class="context-head"><b>${esc(city)}</b>${facts.length ? ` <span class="context-facts">${facts.map(esc).join(" · ")}</span>` : ""}${n ? ` <button type="button" class="context-more" data-open-meta>${n} statement${n === 1 ? "" : "s"}</button>` : ""}</div>
  </div>`;
}
