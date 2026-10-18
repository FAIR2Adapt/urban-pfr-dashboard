// The panels of a dataset, in order: from the plan when the source was composed, else derived from the layers of a
// source read through config/dashboard.yaml. Everything the map, the sidebar and the legend know about a panel comes through here.
import { state } from "./state.js";
import { drawableChannels } from "./map/renderers.js";
import { accessAllows, alignedEnabled, drawOrder, stateKey } from "./policy.js";

// A source without a Dashboard FDO carries layer roles and variable keys from config/dashboard.yaml; they are mapped
// to renderers and channels once, here, and nowhere else.
const CONFIG_BY_ROLE = {
  "primary-risk-layer": { renderer: "bivariate-map", channels: { x: ["risk_mobility_accessibility", "breaks_ma"], y: ["risk_wellbeing", "breaks_wb"] } },
  "social-vulnerability-background": { renderer: "single-variable-map", group: "background", channels: { value: ["social_vulnerability", "breaks_sv"] } },
  "vulnerability-drivers-background": { renderer: "bivariate-background", group: "background", channels: { x: ["sensitivity", "breaks_sensitivity"], y: ["coping_capacity", "breaks_coping"] } },
  "context-boundary-layer": { renderer: "outline" },
  "focus-area-outline": { renderer: "outline-focus" },
  "private-building-risk-layer": { renderer: "bivariate-map", channels: { x: ["risk_mobility_accessibility", "breaks_ma"], y: ["risk_wellbeing", "breaks_wb"] } },
};
const CONFIG_ORDER = ["social-vulnerability-background", "vulnerability-drivers-background", "context-boundary-layer", "focus-area-outline", "primary-risk-layer", "private-building-risk-layer"];
const CONFIG_LABELS = { "primary-risk-layer": "Risk map (PFR)", "social-vulnerability-background": "Social vulnerability background",
  "vulnerability-drivers-background": "Vulnerability drivers background", "context-boundary-layer": "Boundaries outline", "focus-area-outline": "Focus areas", "private-building-risk-layer": "Risk (building level)" };

export function panelsOf(dataset) {
  if (!dataset) return [];
  if (dataset.composition) {
    return dataset.composition.map((entry) => ({ ...entry, layer: entry.layer ? dataset.layers[entry.layer] : null }));
  }
  const out = [];
  for (const role of CONFIG_ORDER) {
    const key = Object.keys(dataset.layers || {}).find((k) => dataset.layers[k]?.role === role);
    if (!key) continue;
    const layer = dataset.layers[key], spec = CONFIG_BY_ROLE[role], classification = layer.classification || {};
    const variableMap = layer.variables || {};
    const channels = {};
    for (const [name, [variable, breaksKey]] of Object.entries(spec.channels || {})) channels[name] = { column: variableMap[variable], breaks: classification[breaksKey] || [] };
    out.push({ id: key, key, label: CONFIG_LABELS[role], renderer: spec.renderer, status: "PASS", access: "open", drawable: true, reason: null,
      diagnostics: [], kind: "map", exclusiveGroup: spec.group || null, position: out.length + 1, layer: { ...layer, channels, renderer: spec.renderer } });
  }
  return out;
}

export const mapPanels = (dataset) => panelsOf(dataset).filter((p) => p.kind === "map" && p.layer);

// a panel the page can draw: composed as drawable, its channels bound with declared breaks
export const canDraw = (panel) => panel.drawable !== false && drawableChannels(panel.renderer, panel.layer);

// enabled state keyed by source and panel; defaults: the first panel of an exclusive group on, the others off; outlines off
export function ensureEnabled(sourceId, dataset) {
  const seenGroup = new Set();
  for (const panel of mapPanels(dataset)) {
    const key = stateKey(sourceId, panel.key);
    if (key in state.enabledPanels) continue;
    if (panel.exclusiveGroup) { state.enabledPanels[key] = !seenGroup.has(panel.exclusiveGroup); seenGroup.add(panel.exclusiveGroup); }
    else state.enabledPanels[key] = panel.renderer !== "outline" && panel.renderer !== "outline-focus";
  }
}

export const isEnabled = (sourceId, panelKey) => !!state.enabledPanels[stateKey(sourceId, panelKey)];

export function setEnabled(sourceId, dataset, panelKey, on) {
  state.enabledPanels[stateKey(sourceId, panelKey)] = on;
  const me = mapPanels(dataset).find((p) => p.key === panelKey);
  if (on && me?.exclusiveGroup) {
    for (const panel of mapPanels(dataset)) {
      if (panel.key !== panelKey && panel.exclusiveGroup === me.exclusiveGroup) state.enabledPanels[stateKey(sourceId, panel.key)] = false;
    }
  }
}

// several cities on one map: the first source leads, the others take its enabled flags per renderer (policy.js)
export function alignEnabledAcross(sourceIds) {
  const [lead, ...others] = sourceIds.filter((id) => state.datasets[id]);
  if (!lead) return;
  ensureEnabled(lead, state.datasets[lead]);
  for (const sid of others) {
    ensureEnabled(sid, state.datasets[sid]);
    state.enabledPanels = alignedEnabled(state.enabledPanels, lead, mapPanels(state.datasets[lead]), sid, mapPanels(state.datasets[sid]));
  }
}

// one control for every source: the panels drawn by this renderer, in each selected source
export function setEnabledByRenderer(sourceIds, renderer, on) {
  for (const sid of sourceIds) {
    const dataset = state.datasets[sid];
    if (!dataset) continue;
    for (const panel of mapPanels(dataset)) if (panel.renderer === renderer) setEnabled(sid, dataset, panel.key, on);
  }
}

// what the map draws for one source: enabled, allowed in the current view, drawable; in stacking order (policy.js)
export const enabledMapPanels = (sourceId, dataset) =>
  drawOrder(mapPanels(dataset).filter((p) => isEnabled(sourceId, p.key) && accessAllows(p, state.view) && canDraw(p)));
