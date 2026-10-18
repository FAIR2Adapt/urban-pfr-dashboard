import { state, LAYERED } from "../state.js";
import { BASEMAPS } from "../map/basemaps.js";
import { panelsOf, mapPanels, ensureEnabled, setEnabled, isEnabled, canDraw, alignEnabledAcross, setEnabledByRenderer } from "../composition.js";
import { $, mkEl } from "./dom.js";
import { breaksProblem } from "../map/renderers.js";
import { setBasemap } from "../map/map.js";
import { setBasemapGl } from "../map/maplibre.js";

// Several cities on one map: a control names what a renderer draws, not one city's panel.
// Profile attribute TBD: human title per plugin renderer; these labels stand in when several cities share a control
const SHARED_LABELS = { "bivariate-map": "Pluvial flood risk (PFR)", "single-variable-map": "Social vulnerability (SV)",
  "bivariate-background": "Vulnerability drivers (sensitivity × coping capacity)", "outline": "Boundaries outline", "outline-focus": "Focus areas" };

export function buildVisualizationSelector(onChange) {
  const container = $("visualizationSelector");
  if (!container) return;
  container.querySelectorAll(".layer-check, .layer-group, .viz-option, .viz-setup").forEach((b) => b.remove());
  const title = container.querySelector(".section-title");
  if (title) title.textContent = "Visualization";

  if (LAYERED(state.dataset)) buildLayerControls(container, onChange);
}

function buildLayerControls(container, onChange) {
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);
  if (ids.length > 1) { buildSharedControls(container, ids, onChange); return; }
  const ds = state.dataset;
  const sourceId = state.selectedSourceIds[0];
  ensureEnabled(sourceId, ds);
  const groups = new Map();
  for (const p of mapPanels(ds)) {
    const g = p.exclusiveGroup || "";
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(p);
  }
  const inputs = {};   // panel key -> checkbox, so an exclusive group unchecks its siblings in place (no rebuild)
  for (const [g, panels] of [...groups].sort((a, b) => (a[0] === "" ? -1 : b[0] === "" ? 1 : 0))) {   // what the map is about first, then the backgrounds
    if (g) container.appendChild(groupLabel(`${g} (one at a time)`));
    for (const p of panels) {
      const drawable = canDraw(p);
      const label = (p.status === "PASS" ? p.label : `${p.label} · ${p.status}`) + (drawable ? "" : " · not drawn");
      const row = layerCheck(label, isEnabled(sourceId, p.key), (v) => {
        setEnabled(sourceId, ds, p.key, v);
        for (const q of mapPanels(ds)) if (inputs[q.key]) inputs[q.key].checked = isEnabled(sourceId, q.key);
        onChange();
      }, !g);
      if (!drawable) { row.querySelector("input").disabled = true; row.title = p.reason || breaksProblem(p.renderer, p.layer) || "not drawable"; }
      inputs[p.key] = row.querySelector("input");
      container.appendChild(row);
    }
  }
  for (const p of panelsOf(ds).filter((x) => x.kind !== "map" || !x.layer)) {
    if (p.status !== "PASS") { const d = mkEl("div", "layer-group"); d.textContent = `${p.label}: ${p.status}${p.reason ? " · " + p.reason : ""}`; container.appendChild(d); }
  }
}

// One control per renderer across the selected sources; a toggle acts on every city's panel of that renderer,
// and the exclusive groups of each source still hold.
function buildSharedControls(container, ids, onChange) {
  alignEnabledAcross(ids);
  const byRenderer = new Map();   // renderer -> { group, panel of the lead source or the first found }
  for (const sid of ids) {
    for (const p of mapPanels(state.datasets[sid])) {
      if (!byRenderer.has(p.renderer)) byRenderer.set(p.renderer, { group: p.exclusiveGroup || "", sid, panel: p });
    }
  }
  const groups = new Map();
  for (const [renderer, entry] of byRenderer) {
    if (!groups.has(entry.group)) groups.set(entry.group, []);
    groups.get(entry.group).push({ renderer, ...entry });
  }
  const inputs = {};
  const refresh = () => { for (const [renderer, entry] of byRenderer) if (inputs[renderer]) inputs[renderer].checked = isEnabled(entry.sid, entry.panel.key); };
  for (const [g, entries] of [...groups].sort((a, b) => (a[0] === "" ? -1 : b[0] === "" ? 1 : 0))) {
    if (g) container.appendChild(groupLabel(`${g} (one at a time, all cities)`));
    for (const e of entries) {
      const drawable = ids.some((sid) => mapPanels(state.datasets[sid]).some((p) => p.renderer === e.renderer && canDraw(p)));
      const label = (SHARED_LABELS[e.renderer] || e.panel.label) + (drawable ? "" : " · not drawn");
      const row = layerCheck(label, isEnabled(e.sid, e.panel.key), (v) => { setEnabledByRenderer(ids, e.renderer, v); refresh(); onChange(); }, !g);
      if (!drawable) row.querySelector("input").disabled = true;
      inputs[e.renderer] = row.querySelector("input");
      container.appendChild(row);
    }
  }
}

function layerCheck(label, checked, onToggle, strong = false) {
  const row = mkEl("label", "layer-check" + (strong ? " strong" : ""));
  const input = mkEl("input");
  input.type = "checkbox";
  input.checked = checked;
  input.addEventListener("change", () => onToggle(input.checked));
  const span = mkEl("span");
  span.textContent = label;
  row.appendChild(input);
  row.appendChild(span);
  return row;
}

function groupLabel(text) {
  const d = mkEl("div", "layer-group");
  d.textContent = text;
  return d;
}

export function wireBasemap() {
  const container = $("basemapSelector");
  if (!container) return;
  container.innerHTML = "";
  BASEMAPS.forEach((bm) => {
    const row = mkEl("label", "basemap-radio");
    const input = mkEl("input");
    input.type = "radio";
    input.name = "basemap";
    input.checked = bm.value === state.basemap;
    input.addEventListener("change", () => {
      if (input.checked) { setBasemap(bm.value); setBasemapGl(bm.value); }
    });
    const span = mkEl("span");
    span.textContent = bm.label;
    row.appendChild(input);
    row.appendChild(span);
    container.appendChild(row);
  });
}
