import { state, FIGURES, BASEMAPS } from "../state.js";
import { $, mkEl } from "./dom.js";
import { setBasemap } from "../map/map.js";

export function buildVisualizationSelector(onChange) {
  const container = $("visualizationSelector");
  if (!container) return;
  container.querySelectorAll(".layer-check, .layer-group, .viz-option, .viz-setup").forEach((b) => b.remove());
  const title = container.querySelector(".section-title");
  if (title) title.textContent = "Visualization";

  if (state.dataset?.sourceType === "rocrate-output") {
    buildLayerControls(container, onChange);
  } else {
    buildFigureButtons(container, onChange);
  }
}

function buildLayerControls(container, onChange) {
  const L = state.dataset?.layers || {};
  const E = state.enabledLayers;

  container.appendChild(
    layerCheck("Risk map (PFR)", E.riskMap, (v) => { E.riskMap = v; onChange(); }, true)
  );

  container.appendChild(groupLabel("Context background"));
  container.appendChild(
    layerCheck("Social vulnerability background", E.socialVulnerability, (v) => {
      E.socialVulnerability = v;
      if (v) E.vulnerabilityDrivers = false;   // mutually exclusive
      buildVisualizationSelector(onChange);
      onChange();
    })
  );
  container.appendChild(
    layerCheck("Vulnerability drivers background", E.vulnerabilityDrivers, (v) => {
      E.vulnerabilityDrivers = v;
      if (v) E.socialVulnerability = false;     // mutually exclusive
      buildVisualizationSelector(onChange);
      onChange();
    })
  );

  container.appendChild(groupLabel("Optional overlays"));
  container.appendChild(
    layerCheck("Boundaries outline", E.boundaryOutline, (v) => { E.boundaryOutline = v; onChange(); })
  );
  // Focus areas only when the dataset actually provides that layer.
  if (L.focusAreas) {
    container.appendChild(
      layerCheck("Focus areas", E.focusAreas, (v) => { E.focusAreas = v; onChange(); })
    );
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

function buildFigureButtons(container, onChange) {
  FIGURES.forEach((fig) => {
    const row = mkEl("label", "viz-option");
    const input = mkEl("input");
    input.type = "radio";
    input.name = "figure";
    input.checked = fig.key === state.figure;
    input.addEventListener("change", () => {
      if (input.checked) { state.figure = fig.key; onChange(); }
    });
    const span = mkEl("span");
    span.textContent = fig.label;
    row.appendChild(input);
    row.appendChild(span);
    container.appendChild(row);
  });
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
      if (input.checked) setBasemap(bm.value);
    });
    const span = mkEl("span");
    span.textContent = bm.label;
    row.appendChild(input);
    row.appendChild(span);
    container.appendChild(row);
  });
}
