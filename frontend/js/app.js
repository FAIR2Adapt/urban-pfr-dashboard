import { state, LAYERED } from "./state.js";
import { fetchSources, fetchDataset } from "./api/dataService.js";
import { initMap, fitToBbox, fitToLayers } from "./map/map.js";
import { unionBbox, stateKey } from "./policy.js";
import * as layers from "./map/layers.js";
import { ensureEnabled, enabledMapPanels, alignEnabledAcross } from "./composition.js";
import { buildLegend } from "./map/legends.js";
import { $, setText, setLoading, showError } from "./ui/dom.js";
import { buildVisualizationSelector, wireBasemap } from "./ui/sidebar.js";
import { buildSourceSelector, cityName } from "./ui/sourceSelector.js";
import { wireMetadataToggle, refreshMetadataPanel, setMetadataAvailable, openStatements } from "./ui/metadataPanel.js";
import { renderContextStrip } from "./ui/contextStrip.js";
import { glAvailable, initGl, showGl, renderGl } from "./map/maplibre.js";

document.addEventListener("DOMContentLoaded", init);

async function init() {
  initMap();
  if (state.renderer === "maplibre" && glAvailable()) initGl();
  wireBasemap();
  wireMetadataToggle(() => { buildVisualizationSelector(render); render(false); });
  wireViewportRefetch();
  await loadSources();
}

const useGl = () =>
  state.renderer === "maplibre" && glAvailable() && state.view === "public" && LAYERED(state.dataset);

// fgb-bbox layers: re-read after pan/zoom
function wireViewportRefetch() {
  let timer;
  state.map.on("moveend", () => {
    // MapLibre serves these from PMTiles, which tile themselves — refetching
    // there would tear down and reload every source on each pan/zoom.
    if (useGl()) return;
    if (state.selfMoves > 0) { state.selfMoves -= 1; return; }   // the page's own flight to a footprint; already read
    const layers = (state.dataset || {}).layers || {};
    const anyBbox = Object.values(layers).some(
      (l) => l && (l.renderingStrategy || "").startsWith("fgb-bbox")
    );
    if (!anyBbox) return;
    clearTimeout(timer);
    timer = setTimeout(() => render(false), 300);
  });
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
  // ?source=<id> opens one source
  const asked = new URLSearchParams(location.search).get("source") || window.__DEFAULT_SOURCE__;   // /loom/ and /combined/ set the latter
  const initial = enabled.find((s) => s.id === asked)?.id ||
    enabled.find((s) => s.id === state.defaultSource)?.id || enabled[0]?.id;
  state.selectedSourceIds = initial ? [initial] : [];
  const first = state.sources.find((s) => s.id === initial);
  if (first) state.sourceByCity[cityName(first)] = initial;
  buildSourceSelector(selectSources);

  if (state.selectedSourceIds.length) await selectSources(state.selectedSourceIds);
  else showError("No enabled data sources are configured.\n See the README section Configuration.");
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
    buildViewSelector();
    buildVisualizationSelector(render);
    await render(true);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

// "Hamburg", not the full crate title. Falls back to the source id.
const shortName = (id) =>
  cityName(state.sources.find((s) => s.id === id) || { id, label: state.datasets[id]?.label });

// Append a quiet marker when any shown object says it is synthetic (root creativeWorkStatus, read by fdo-consume).
// Profile attribute TBD: controlled status vocabulary; the word synthetic in the status text marks demo data
const subtitleFor = (ids, base) =>
  ids.some((i) => [state.datasets[i]?.metadata?.status, state.datasets[i]?.metadata?.mapFrom?.status].some((s) => String(s || "").toLowerCase().includes("synthetic")))
    ? `${base} · demo data`
    : base;

let renderGen = 0;   // each render gets a number; only the latest one draws (the fgb-bbox fetches are slow)

async function render(fit = false) {
  const gen = ++renderGen;
  const current = () => gen === renderGen;
  layers.clearLayers();
  state.drawErrors = [];
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);
  if (!ids.length) {
    setText("currentTitle", "No data source selected");
    setText("currentSubtitle", "");
    setMetadataAvailable(false);
    buildLegend();
    renderContextStrip();
    return;
  }

  const primary = state.datasets[ids[0]];
  state.dataset = primary;
  const multi = ids.length > 1;
  if (multi) alignEnabledAcross(ids);

  if (LAYERED(primary)) {
    // Header carries the city, nothing else; provenance lives in the metadata panel.
    setText("currentTitle", ids.map(shortName).join(" · "));
    setText("currentSubtitle", "");

    if (useGl()) {
      showGl(true);
      renderGl(fit, ids);          // every selected city, not just the first
      setText("currentSubtitle", withDrawErrors(subtitleFor(ids, mapSubtitle(primary))));
      setMetadataAvailable(true);
      buildLegend();
    renderContextStrip();
      refreshMetadataPanel();
      // no map but claims: open the claims
      if (primary.panels?.map && !primary.panels.map.available && (primary.claims || []).length && !state.showMeta) openStatements();
      return;
    }
    showGl(false);

    const riskGeos = [];
    const allGeos = [];
    let restricted = false;
    // A viewport-bound read (fgb-bbox) must use the viewport of the city about to be shown, not the one left behind:
    // on a change of source the map is moved to the declared footprint first, and the reads use that footprint.
    let footprint = null;
    if (fit) {
      const drawn = ids.flatMap((sid) => (LAYERED(state.datasets[sid]) ? (ensureEnabled(sid, state.datasets[sid]), enabledMapPanels(sid, state.datasets[sid])) : []));
      footprint = unionBbox(drawn.map((p) => p.layer?.outputFootprintBbox));
      if (footprint) fitToBbox(footprint);
    }
    for (const sid of ids) {
      const ds = state.datasets[sid];
      if (!LAYERED(ds)) continue;
      ensureEnabled(sid, ds);
      for (const p of enabledMapPanels(sid, ds)) {   // stacking order of policy.js: backgrounds first, then position
        const g = await layers.addPanel(sid, p, current, footprint);
        if (g) { allGeos.push(g); if (p.renderer === "bivariate-map") riskGeos.push(g); if (g.leftOut) state.leftOut[stateKey(sid, p.key)] = g.leftOut; }
        else if (state.view === "private" && p.layer?.accessTier === "private") restricted = true;
      }
    }
    if (!current()) return;   // a newer render owns the map and the header
    const truncated = [...riskGeos, ...allGeos].some((g) => g && g.truncated);
    // say which renderer, and what failed
    const fallback = glAvailable() ? "" : " · drawn with Leaflet (WebGL not available in this browser)";
    const failed = withDrawErrors("");
    setText("currentSubtitle", subtitleFor(ids, state.view === "private"
      ? (restricted ? "🔒 Private view — authorization required" : "🔒 Private view · building level")
      : mapSubtitle(primary))   // a source without a map panel says so, on this path too
      + (truncated ? " · only part of this view is shown; zoom in to load all cells" : "") + fallback + failed);
    if (fit && !footprint) fitToLayers((riskGeos.length ? riskGeos : allGeos).filter(Boolean));
  } else {
    setText("currentTitle", shortName(ids[0]));
    setText("currentSubtitle", "No drawable panel is available for this source.");
  }

  setMetadataAvailable(true);
  buildLegend();
    renderContextStrip();
  refreshMetadataPanel();
}

// draw errors (a layer without a drawable distribution, a tile or archive error) go to the header
const withDrawErrors = (base) => state.drawErrors.length
  ? `${base} · the map could not draw ${state.drawErrors.length} layer${state.drawErrors.length === 1 ? "" : "s"}: ${state.drawErrors[0]}`
  : base;
window.addEventListener("drawerrors", () => {
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);
  if (ids.length) setText("currentSubtitle", withDrawErrors(subtitleFor(ids, mapSubtitle(state.dataset))));
});

const mapSubtitle = (ds) =>
  ds.panels?.map && !ds.panels.map.available
    ? `Map panel not available — ${ds.panels.map.reason || "no compatible map product is declared"}`
    : "Public view · aggregated cells";

// public or private view; the server decides what each tier may read
function buildViewSelector() {
  const sel = $("viewSelector");
  const section = $("viewSection");
  if (!sel || !section) return;
  const ds = state.dataset || {};
  const allowed = ds.allowedViews || ["public"];
  const views = ds.views || {};
  if (!allowed.includes(state.view)) state.view = "public";
  if (allowed.length <= 1) { section.style.display = "none"; return; }
  section.style.display = "";
  sel.innerHTML = "";
  allowed.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = (views[v] && views[v].label) || v;
    if (v === state.view) opt.selected = true;
    sel.appendChild(opt);
  });
  if (!sel.dataset.wired) {
    sel.addEventListener("change", () => { state.view = sel.value; render(true); });
    sel.dataset.wired = "1";
  }
}
