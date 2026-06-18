import { state, FIGURES } from "./state.js";
import { fetchSources, fetchDataset } from "./api/dataService.js";
import { initMap, fitToLayer, fitToLayers } from "./map/map.js";
import * as layers from "./map/layers.js";
import { buildLegend } from "./map/legends.js";
import { setText, setLoading, showError } from "./ui/dom.js";
import { buildVisualizationSelector, wireBasemap } from "./ui/sidebar.js";
import { buildSourceSelector } from "./ui/sourceSelector.js";
import { wireMetadataToggle, refreshMetadataPanel, setMetadataAvailable } from "./ui/metadataPanel.js";

document.addEventListener("DOMContentLoaded", init);

async function init() {
  initMap();
  wireBasemap();
  wireMetadataToggle();
  await loadSources();
}

async function loadSources() {
  try {
    const data = await fetchSources();
    state.sources = data.sources || [];
    state.defaultSource = data.defaultSource;
  } catch (err) {
    showError(`Could not load data sources: ${err.message}`);
    return;
  }

  const enabled = state.sources.filter((s) => s.enabled);
  const initial = enabled.find((s) => s.id === state.defaultSource)?.id || enabled[0]?.id;
  state.selectedSourceIds = initial ? [initial] : [];
  buildSourceSelector(selectSources);

  if (state.selectedSourceIds.length) await selectSources(state.selectedSourceIds);
  else showError("No enabled data sources are configured.\n See the README — Adding and converting data — for the full guide.");
}

async function selectSources(ids) {
  state.selectedSourceIds = ids;
  if (!ids.length) {
    render();
    return;
  }
  setLoading(true, "Loading…");
  try {
    await Promise.all(
      ids
        .filter((id) => !state.datasets[id])
        .map(async (id) => {
          state.datasets[id] = await fetchDataset(id);
        })
    );
    state.dataset = state.datasets[ids[0]] || null;
    buildVisualizationSelector(render);
    await render(true);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

async function render(fit = false) {
  layers.clearLayers();
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);
  if (!ids.length) {
    setText("currentTitle", "No data source selected");
    setText("currentSubtitle", "");
    setMetadataAvailable(false);
    buildLegend();
    return;
  }

  const primary = state.datasets[ids[0]];
  state.dataset = primary;
  const multi = ids.length > 1;

  if (primary.sourceType === "rocrate-output") {
    setText("currentTitle", multi ? `${ids.length} sources` : primary.label || "");
    setText("currentSubtitle", "");

    const E = state.enabledLayers;
    const riskGeos = [];
    const allGeos = [];
    for (const sid of ids) {
      const ds = state.datasets[sid];
      if (ds.sourceType !== "rocrate-output") continue;
      const L = ds.layers || {};

      // Exactly one social-vulnerability background, drawn underneath.
      if (E.socialVulnerability && L.socialVulnerability)
        allGeos.push(await layers.addRocrateOutput(sid, L.socialVulnerability));
      else if (E.vulnerabilityDrivers && L.vulnerabilityDrivers)
        allGeos.push(await layers.addRocrateOutput(sid, L.vulnerabilityDrivers));

      if (E.boundaryOutline && L.boundaryOutline)
        allGeos.push(await layers.addRocrateOutput(sid, L.boundaryOutline));

      if (E.focusAreas && L.focusAreas)
        allGeos.push(await layers.addRocrateOutput(sid, L.focusAreas));

      // PFR risk overlay always on top.
      if (E.riskMap && L.riskMap) {
        const g = await layers.addRocrateOutput(sid, L.riskMap);
        if (g) { riskGeos.push(g); allGeos.push(g); }
      }
    }
    if (fit) fitToLayers((riskGeos.length ? riskGeos : allGeos).filter(Boolean));
  } else {
    const fig = FIGURES.find((f) => f.key === state.figure) || FIGURES[0];
    setText("currentTitle", `${primary.label} — ${fig.label}`);
    setText("currentSubtitle", fig.subtitle || "");
    renderLocal(fit);
  }

  setMetadataAvailable(true);
  buildLegend();
  refreshMetadataPanel();
}

function renderLocal(fit) {
  switch (state.figure) {
    case "figure5":
      layers.addGreySV();
      layers.addRiskPoints();
      break;
    case "figure6":
      layers.addBivarSV();
      layers.addRiskPoints();
      break;
    case "overview":
      layers.addOutline();
      layers.addOverviewPoints();
      break;
    default:
      layers.addOutline();
      layers.addRiskPoints();
      break;
  }
  if (fit) fitToLayer(state.dataset.layers?.riskMap?.data);
}
