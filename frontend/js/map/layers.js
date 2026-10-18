import { state } from "../state.js";
import { esc } from "../ui/dom.js";
import { fetchResource, resourceUrl } from "../api/dataService.js";
import { svGreyColor, svBivarColor, classIndex } from "./colors.js";
import { axisTitle, formatValue } from "./classes.js";
import { drawableChannels, paletteFor } from "./renderers.js";

// Features read per layer and viewport when the layer does not state its cap (max_features_per_read in config/formats.yaml).
const BBOX_LIMIT = 20000;

function track(layer) {
  layer.addTo(state.map);
  state.activeLayers.push(layer);
  return layer;
}

export function clearLayers() {
  for (const layer of state.activeLayers) state.map.removeLayer(layer);
  state.activeLayers = [];
  // one canvas per draw: paths removed from a shared canvas can keep their pixels until it repaints
  if (state.map.options.renderer) state.map.removeLayer(state.map.options.renderer);
  state.map.options.renderer = L.canvas();
}

async function cachedFetch(url) {
  if (!url) return null;
  if (url in state.fetchedLayers) return state.fetchedLayers[url];
  try {
    const geo = await fetchResource(url);
    state.fetchedLayers[url] = geo;
    return geo;
  } catch (e) {
    console.warn("Could not fetch resource:", url, e.message);
    state.fetchedLayers[url] = null;
    state.drawErrors.push(`${url.split("?")[0].split("/").pop()}: ${e.message}`);   // shown in the header and the console
    return null;
  }
}

// A FlatGeobuf file is read by bounding box in the browser: the reader follows the file's spatial index with HTTP
// range requests, so a static host serves it like a server does. Capped at `limit` features, as the header says.
async function fetchFgbBbox(url, bounds, limit = BBOX_LIMIT) {
  const key = `${url}#${bounds.map((v) => v.toFixed(5)).join(",")}`;
  if (key in state.fetchedLayers) return state.fetchedLayers[key];
  if (typeof flatgeobuf === "undefined") {
    state.drawErrors.push(`${url.split("/").pop()}: the FlatGeobuf reader is not loaded`);
    return null;
  }
  const rect = { minX: bounds[0], minY: bounds[1], maxX: bounds[2], maxY: bounds[3] };
  const features = [];
  let truncated = false;
  try {
    for await (const feature of flatgeobuf.deserialize(url, rect)) {
      if (features.length >= limit) { truncated = true; break; }
      features.push(feature);
    }
  } catch (e) {
    console.warn("Could not read FlatGeobuf:", url, e.message);
    state.fetchedLayers[key] = null;
    state.drawErrors.push(`${url.split("/").pop()}: ${e.message}`);
    return null;
  }
  const geo = { type: "FeatureCollection", features, truncated };
  state.fetchedLayers[key] = geo;
  return geo;
}

async function fetchLayerData(sourceId, output, bounds = null) {
  const file = output.engines ? output.engines.leaflet : null;
  if (output.engines && !file) {   // nothing this engine reads: the server's reason, per declared file
    state.drawErrors.push(`${output.label || "layer"}: not drawn by the Leaflet fallback (${output.unread?.leaflet || "no readable file"})`);
    return null;
  }
  const url = file ? file.path : resourceUrl(sourceId, output);
  if (!url) return null;
  const strategy = file ? (file.reader === "fgb-bbox" ? "fgb-bbox" : "static") : (output.renderingStrategy || "");
  if (strategy.startsWith("fgb-bbox") && (bounds || state.map)) {
    const b = state.map.getBounds();
    return fetchFgbBbox(url, bounds || [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], file?.maxFeatures || BBOX_LIMIT);
  }
  return cachedFetch(url);
}

// isCurrent: false once a newer render has started; a stale render must not add its layer after the fetch
// Leaflet drawing per renderer id (capabilities: renderers.js): each draws one panel from its layer's channels
// (column + declared class breaks); no variable name of a case study appears here, and no breaks are computed.
const DRAW = {
  "bivariate-map": drawBivariate,
  "single-variable-map": drawSingleVariable,
  "bivariate-background": drawBivariateBackground,
  "outline": drawOutline,
  "outline-focus": drawOutline,
};

// isCurrent: false once a newer render has started; a stale render must not add its layer after the fetch
export async function addPanel(sourceId, panel, isCurrent = () => true, bounds = null) {
  const layer = panel.layer;
  const draw = DRAW[panel.renderer];
  if (!layer || !draw || !drawableChannels(panel.renderer, layer)) return null;
  const geo = await fetchLayerData(sourceId, layer, bounds);
  if (!geo || !isCurrent()) return null;
  draw(geo, geo.features || [], layer, panel);
  return geo;
}

const clampTo = (value, max) => Math.min(Math.max(+value || 0, 0), max);
const outlineOpacity = (o) => (state.map.getZoom() >= 12.5 ? o : 0);   // outlines only where a cell is wide enough to carry one

// a value is a finite number; a missing, null, empty or non-numeric cell is "no data" and is not drawn (the legend says so)
// Profile attribute TBD: no-data value per Variable; a missing or non-numeric value is not drawn
const finite = (v) => typeof v === "number" && Number.isFinite(v);   // as the MapLibre filter: numbers only
const hasValues = (p, columns) => columns.every((k) => finite(p?.[k]));

function drawSingleVariable(geo, feats, layer, panel) {
  const ch = layer.channels.value, key = ch.column, breaks = ch.breaks;
  const steps = paletteFor(panel.renderer, layer)?.steps || [];
  track(L.geoJSON(geo, {
    filter: (f) => hasValues(f.properties, [key]),
    style: (f) => ({ fillColor: steps[clampTo(classIndex(+f.properties[key], breaks), steps.length - 1)] || svGreyColor(0), color: "#9e9e9e", weight: 0.4, opacity: outlineOpacity(0.6), fillOpacity: 0.55 }),
    onEachFeature: (f, l) => l.bindPopup(fieldsPopup(f, layer)),
  }));
}

function drawBivariateBackground(geo, feats, layer, panel) {
  const x = layer.channels.x, y = layer.channels.y;
  const grid = paletteFor(panel.renderer, layer)?.grid;
  const colorFor = (p) => {
    const xi = classIndex(+p[x.column], x.breaks), yi = classIndex(+p[y.column], y.breaks);
    return grid ? grid[clampTo(yi, grid.length - 1)][clampTo(xi, grid[0].length - 1)] : svBivarColor(xi, yi);
  };
  track(L.geoJSON(geo, {
    filter: (f) => hasValues(f.properties, [x.column, y.column]),
    style: (f) => ({ fillColor: colorFor(f.properties),
      color: "#9e9e9e", weight: 0.4, opacity: outlineOpacity(0.5), fillOpacity: 0.62 }),
    onEachFeature: (f, l) => l.bindPopup(fieldsPopup(f, layer)),
  }));
}

function drawOutline(geo, feats, layer, panel) {
  const focus = panel.renderer === "outline-focus";
  track(L.geoJSON(geo, {
    style: () => (focus ? { fill: false, color: "#000", weight: 2, opacity: 0.9 } : { color: "#1e3a5f", weight: 0.7, opacity: 0.8, fillColor: "#1e3a5f", fillOpacity: 0.06 }),
    onEachFeature: (f, l) => l.bindPopup(fieldsPopup(f, layer)),
  }));
}

function drawBivariate(geo, feats, layer, panel) {
  const x = layer.channels.x, y = layer.channels.y;
  const maKey = x.column, wbKey = y.column;
  const maBreaks = x.breaks, wbBreaks = y.breaks;
  const grid = paletteFor(panel.renderer, layer).grid;
  const colorFor = (p) => grid[clampTo(classIndex(+p[wbKey], wbBreaks), grid.length - 1)][clampTo(classIndex(+p[maKey], maBreaks), grid[0].length - 1)];
  // Profile attribute TBD: display rule for the lowest class; cells below the first break on both axes are left out
  const keep = (p) => hasValues(p, [maKey, wbKey]) && (classIndex(+p[maKey], maBreaks) > 0 || classIndex(+p[wbKey], wbBreaks) > 0);

  let noValue = 0, belowFirstBreak = 0;
  for (const f of feats) { if (!hasValues(f.properties, [maKey, wbKey])) noValue++; else if (!keep(f.properties)) belowFirstBreak++; }
  geo.leftOut = { total: feats.length, noValue, belowFirstBreak };   // read by the legend (app.js keeps it per panel)
  track(L.geoJSON(geo, {   // cells drawn as they are; no data and classes below the first break are left out
    filter: (f) => keep(f.properties),
    style: (f) => ({ fillColor: colorFor(f.properties), color: "#666", weight: 0.4, opacity: outlineOpacity(0.6), fillOpacity: 0.75 }),
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 3, fillColor: colorFor(f.properties), color: "#333", weight: 0.3, fillOpacity: 0.9 }),
    onEachFeature: (f, l) => l.bindPopup(fieldsPopup(f, layer)),
  }));
}

// one cell: each bound column with the title the object gives it (classes.js) and its value
function fieldsPopup(f, layer) {
  const p = f.properties || {};
  const columns = [...new Set([...Object.values(layer.variables || {}), ...(layer.fields || [])])].filter((c) => c in p).slice(0, 8);   // declared order
  return `<div style="font-size:12px;min-width:150px"><strong>${esc(layer.label || "")}</strong>
    <table style="border-collapse:collapse;width:100%;margin-top:4px">
      ${columns.map((k) => `<tr><td style="color:#64748b;padding:1px 4px" title="${esc(k)}">${esc(axisTitle({ column: k }, layer))}</td><td style="text-align:right;font-weight:600">${esc(formatValue(p[k]))}</td></tr>`).join("")}
    </table></div>`;
}
