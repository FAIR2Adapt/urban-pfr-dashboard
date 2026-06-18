import { state } from "../state.js";
import { $, mkEl } from "../ui/dom.js";
import { PFR_GRID, SV_GRID, SV_GREYS, SV_LABELS } from "./colors.js";

export function buildLegend() {
  const el = $("legendContent");
  if (!el) return;
  el.innerHTML = "";

  const ds = state.dataset;
  const type = ds?.sourceType;
  if (type === "rocrate-output") {
    const E = state.enabledLayers;
    const L = ds.layers || {};
    if (E.riskMap) el.appendChild(legendPFR());
    if (E.socialVulnerability && L.socialVulnerability) el.appendChild(legendGreySV());
    else if (E.vulnerabilityDrivers && L.vulnerabilityDrivers) el.appendChild(legendBivarSV());
    if (E.boundaryOutline && L.boundaryOutline) el.appendChild(legendBoundary());
    if (E.focusAreas && L.focusAreas) el.appendChild(legendFocus());
  } else {
    el.appendChild(legendPFR());
    if (type === "local-output" && state.figure === "figure5") el.appendChild(legendGreySV());
    if (type === "local-output" && state.figure === "figure6") el.appendChild(legendBivarSV());
  }

  if (!el.children.length) el.innerHTML = `<span class="grid-labels">No layers selected.</span>`;
}

function section() {
  return mkEl("div", "legend-section");
}

function swatch(color, label) {
  const row = mkEl("div", "swatch-row");
  row.innerHTML = `<div class="swatch" style="background:${color}"></div>
    <span class="grid-labels">${label}</span>`;
  return row;
}

function axisLabel(title, lo, hi, yLabel) {
  const d = mkEl("div", "grid-labels");
  d.style.marginTop = "4px";
  d.innerHTML = `${title}<br>${lo} ${hi}${yLabel ? `<br><em>${yLabel}</em>` : ""}`;
  return d;
}

function legendPFR() {
  const s = section();
  s.innerHTML = `<strong style="font-size:.8rem">Pluvial flood risk (PFR)</strong>`;
  s.appendChild(swatch("#f7e02e", "to mobility &amp; accessibility (MA)"));
  s.appendChild(swatch("#aa00e5", "to well-being (WB)"));
  const grid = mkEl("div", "bivar-grid");
  for (let ma = 3; ma >= 0; ma--) {
    for (let wb = 0; wb < 4; wb++) {
      const cell = mkEl("div", "bivar-cell");
      cell.style.background = ma === 0 && wb === 0 ? "transparent" : PFR_GRID[wb][ma];
      grid.appendChild(cell);
    }
  }
  s.appendChild(grid);
  s.appendChild(axisLabel("Well-being", "Low", "High", "Mobility &amp; Accessibility Low High"));
  return s;
}

function legendGreySV() {
  const s = section();
  s.innerHTML = `<strong style="font-size:.8rem">Social vulnerability (SV)</strong>`;
  SV_LABELS.forEach((lbl, i) => s.appendChild(swatch(SV_GREYS[i], lbl)));
  return s;
}

function legendBivarSV() {
  const s = section();
  s.innerHTML = `<strong style="font-size:.8rem">Social vulnerability — bivariate</strong>`;
  s.appendChild(swatch(SV_GRID[0][0], "SV due to low coping capacity"));
  s.appendChild(swatch(SV_GRID[2][2], "SV due to high sensitivity"));
  const grid = mkEl("div", "sv-grid");
  for (let cc = 0; cc < 3; cc++) {
    for (let si = 0; si < 3; si++) {
      const cell = mkEl("div", "sv-cell");
      cell.style.background = SV_GRID[cc][si];
      grid.appendChild(cell);
    }
  }
  s.appendChild(grid);
  s.appendChild(axisLabel("Sensitivity", "Low", "High", "Low coping capacity Low High"));
  return s;
}

function legendBoundary() {
  const s = section();
  s.innerHTML = `<div class="swatch-row">
    <div style="width:22px;height:14px;border:1px solid #1e3a5f;flex-shrink:0;background:rgba(30,58,95,.06)"></div>
    <span class="grid-labels">Administrative boundaries</span></div>`;
  return s;
}

function legendFocus() {
  const s = section();
  s.innerHTML = `<div class="swatch-row">
    <div style="width:22px;height:14px;border:2px solid #000;flex-shrink:0;background:transparent"></div>
    <span class="grid-labels">Focus areas</span></div>`;
  return s;
}
