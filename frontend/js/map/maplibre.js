import { state, LAYERED } from "../state.js";
import { ensureEnabled, enabledMapPanels } from "../composition.js";
import { esc } from "../ui/dom.js";
import { drawableChannels, paletteFor } from "./renderers.js";
import { unionBbox } from "../policy.js";
import { basemapOf } from "./basemaps.js";
import { axisTitle, formatValue } from "./classes.js";

let gl = null;
let added = [];
let handlers = [];       // popup/cursor listeners, removed with their layers
let firstFit = true;     // first fit is a jump; later ones animate
let bottomLayerId = null;

const reducedMotion = () =>
  window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;

let glBroken = false;    // set if the GL map cannot start (e.g. no WebGL)
let styleReady = false;  // style loaded at least once

export const glAvailable = () =>
  !glBroken && typeof maplibregl !== "undefined" && typeof pmtiles !== "undefined";

export function initGl() {
  if (gl || !glAvailable()) return gl;
  // A machine with no usable WebGL (remote desktop, blocked GPU, old hardware)
  // throws here. That must not abort start-up: fall back to the Leaflet path.
  try {
    maplibregl.addProtocol("pmtiles", new pmtiles.Protocol().tile);
    gl = new maplibregl.Map({
      container: "glmap",
      style: { version: 8, sources: {}, layers: [] },
      center: [10.0, 53.55],
      zoom: 10,
      attributionControl: false,
    });
    window.__gl = gl;                 // exposed for tests and headless checks only
    gl.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    gl.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-left");   // the legend sits bottom right
    gl.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    gl.on("load", () => { styleReady = true; setBasemapGl(state.basemap); });
    // feature count on screen, for tests
    gl.on("idle", () => {
      const own = added.flatMap((a) => a.layers);
      document.body.dataset.renderedFeatures = String(own.length ? gl.queryRenderedFeatures({ layers: own }).length : 0);
    });
    // a tile or archive that cannot be read is a draw error of that layer, not a console line; the basemap is not ours
    gl.on("error", (e) => {
      const sid = e?.sourceId || e?.source?.id;
      if (!sid || !added.some((a) => a.source === sid)) return;
      const msg = `${sid}: ${e.error?.message || "tile or archive could not be read"}`;
      if (state.drawErrors.includes(msg)) return;
      state.drawErrors.push(msg);
      window.dispatchEvent(new Event("drawerrors"));
    });
  } catch (err) {
    console.warn("MapLibre unavailable, falling back to Leaflet:", err?.message || err);
    gl = null;
    glBroken = true;
    showGl(false);
  }
  return gl;
}

export function showGl(show) {
  const glDiv = document.getElementById("glmap");
  const leafletDiv = document.getElementById("map");
  if (!glDiv || !leafletDiv) return;
  glDiv.style.display = show ? "" : "none";
  leafletDiv.style.display = show ? "none" : "";
  if (show && gl) gl.resize();
}

export function setBasemapGl(key) {
  if (!gl || !gl.isStyleLoaded()) return;
  if (gl.getLayer("basemap")) gl.removeLayer("basemap");
  if (gl.getSource("basemap")) gl.removeSource("basemap");
  const b = basemapOf(key);
  gl.addSource("basemap", { type: "raster", tiles: [b.url], tileSize: 256, maxzoom: b.nativeZoom || b.maxZoom, attribution: b.attribution });   // tiles past the native zoom are scaled
  gl.addLayer({ id: "basemap", type: "raster", source: "basemap" },
    bottomLayerId && gl.getLayer(bottomLayerId) ? bottomLayerId : undefined);
}

// the file the server chose for this engine (config/formats.yaml), resolved against the page (project pages)
const glFile = (layer) => layer.engines?.webgl || null;
const absolute = (path) => new URL(path, document.baseURI).href;

// an outline only where a cell is wide enough to carry one; below zoom 12 it would only smear the fill
const OUTLINE = (color) => ["interpolate", ["linear"], ["zoom"], 11, "rgba(0,0,0,0)", 12.5, color];

const stepExpr = (key, breaks, outputs) => {
  const e = ["step", ["to-number", ["get", key], 0], outputs[0]];
  breaks.forEach((b, i) => e.push(b + 1e-12, outputs[i + 1]));
  return e;
};

function addVector(id, layer) {
  if (gl.getSource(id)) return null;              // already added this render
  const file = glFile(layer);
  const src = { source: id, layers: [] };
  if (file?.reader === "pmtiles") gl.addSource(id, { type: "vector", url: `pmtiles://${absolute(file.path)}` });
  else if (file?.reader === "geojson") gl.addSource(id, { type: "geojson", data: file.path });
  else {
    // nothing this engine reads: the server's reason, per declared file
    state.drawErrors.push(`${layer.label || id}: not drawn with WebGL (${layer.unread?.webgl || "no readable file"})`);
    window.dispatchEvent(new Event("drawerrors"));
    return null;
  }
  src.sourceLayer = file.reader === "pmtiles" ? layer.sourceLayer : undefined;
  added.push(src);
  return src;
}

function popupOn(id, fields, layer) {
  const click = (e) => {
    const p = e.features?.[0]?.properties || {};
    const rows = fields.filter((k) => k in p)
      .map((k) => `<tr><td style="color:#64748b;padding:1px 4px" title="${esc(k)}">${esc(axisTitle({ column: k }, layer))}</td><td style="text-align:right"><b>${esc(formatValue(p[k]))}</b></td></tr>`).join("");
    new maplibregl.Popup().setLngLat(e.lngLat)
      .setHTML(`<table style="font-size:12px">${rows}</table>`).addTo(gl);
  };
  const enter = () => (gl.getCanvas().style.cursor = "pointer");
  const leave = () => (gl.getCanvas().style.cursor = "");
  gl.on("click", id, click);
  gl.on("mouseenter", id, enter);
  gl.on("mouseleave", id, leave);
  handlers.push({ type: "click", layer: id, fn: click },
                { type: "mouseenter", layer: id, fn: enter },
                { type: "mouseleave", layer: id, fn: leave });
}

// ---- camera ---------------------------------------------------------------


// easeInOutCubic — no abrupt start or stop
const EASE = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

function smoothFit(bbox) {
  if (!gl || !bbox || bbox.length !== 4) return;
  const cam = gl.cameraForBounds(bbox, { padding: 48 });
  if (!cam) return;

  // First paint, or the user prefers less motion: go straight there.
  if (firstFit || reducedMotion()) {
    gl.jumpTo(cam);
    firstFit = false;
    return;
  }

  const from = gl.getCenter();
  const to = cam.center;
  const toLng = to.lng ?? to[0];
  const toLat = to.lat ?? to[1];
  const move = Math.hypot(from.lng - toLng, from.lat - toLat);
  const zoomJump = Math.abs(gl.getZoom() - (cam.zoom ?? gl.getZoom()));

  // A long hop (city -> city, city -> all cities) reads far better as a flight
  // that arcs out and back in than as a straight pan across empty countryside.
  if (move > 0.2 || zoomJump > 1.2) {
    gl.flyTo({ ...cam, duration: 1700, curve: 1.5, speed: 0.85, essential: true });
  } else {
    gl.easeTo({ ...cam, duration: 700, easing: EASE, essential: true });
  }
}

// ---- rendering -----------------------------------------------------

// A render is described first, then reconciled against what is already on the
// map. Sources that are still wanted are left alone, so toggling a background
// or refitting the camera no longer forces every PMTiles source to reload.

// One spec per panel, by renderer, from the layer's channels (column + declared class breaks); the same drawable rule
// as the Leaflet path (renderers.js), so both paths classify identically or not at all.
function specFor(sid, panel) {
  const layer = panel.layer, ch = layer.channels || {};
  if (!drawableChannels(panel.renderer, layer)) return null;
  const palette = paletteFor(panel.renderer, layer) || {};
  const key = `gl-${sid}-${panel.key}`, fields = [...new Set([...Object.values(layer.variables || {}), ...(layer.fields || [])])];   // declared order
  // no data (a missing or non-numeric value on a channel) is not drawn, as on the Leaflet path
  const hasValues = (...columns) => ["all", ...columns.map((c) => ["==", ["typeof", ["get", c]], "number"])];
  if (panel.renderer === "single-variable-map") {
    return { key, layer, fields, filter: hasValues(ch.value.column),
      paint: { "fill-color": stepExpr(ch.value.column, ch.value.breaks, palette.steps), "fill-opacity": 0.55, "fill-outline-color": OUTLINE("#9e9e9e") } };
  }
  if (panel.renderer === "bivariate-background") {
    const grid = palette.grid;
    const rowExprs = Array.from({ length: ch.y.breaks.length + 1 }, (_, row) => stepExpr(ch.x.column, ch.x.breaks, grid[Math.min(row, grid.length - 1)]));
    return { key, layer, fields, filter: hasValues(ch.x.column, ch.y.column),
      paint: { "fill-color": stepExpr(ch.y.column, ch.y.breaks, rowExprs), "fill-opacity": 0.62, "fill-outline-color": OUTLINE("#9e9e9e") } };
  }
  if (panel.renderer === "bivariate-map") {
    const grid = palette.grid, ma = ch.x.column, wb = ch.y.column;
    const rowExprs = Array.from({ length: ch.y.breaks.length + 1 }, (_, row) => stepExpr(ma, ch.x.breaks, grid[Math.min(row, grid.length - 1)]));
    return { key, layer, fields, bbox: layer.outputFootprintBbox?.length === 4 ? layer.outputFootprintBbox : null,
      paint: { "fill-color": stepExpr(wb, ch.y.breaks, rowExprs), "fill-opacity": 0.75, "fill-outline-color": OUTLINE("#666") },
      filter: ["all", hasValues(ma, wb), ["any", [">", ["get", ma], ch.x.breaks[0]], [">", ["get", wb], ch.y.breaks[0]]]] };   // Profile attribute TBD: display rule for the lowest class
  }
  return null;
}

function dropEntry(entry) {
  for (const h of handlers.filter((x) => entry.layers.includes(x.layer))) gl.off(h.type, h.layer, h.fn);
  handlers = handlers.filter((x) => !entry.layers.includes(x.layer));
  entry.layers.forEach((id) => gl.getLayer(id) && gl.removeLayer(id));
  if (gl.getSource(entry.source)) gl.removeSource(entry.source);
  added = added.filter((a) => a !== entry);
}

function mountSpec(spec, beforeId) {
  const src = addVector(spec.key, spec.layer);
  if (!src) return null;
  const id = `${src.source}-fill`;
  const def = { id, type: "fill", source: src.source, paint: spec.paint };
  if (src.sourceLayer) def["source-layer"] = src.sourceLayer;
  if (spec.filter) def.filter = spec.filter;
  gl.addLayer(def, beforeId && gl.getLayer(beforeId) ? beforeId : undefined);
  src.layers.push(id);
  popupOn(id, spec.fields, spec.layer);
  return id;
}

export function renderGl(fit = false, ids = null) {
  // isStyleLoaded() flips back while tiles load; "load" fires once
  if (!gl) return;
  if (!styleReady) { gl.once("load", () => renderGl(fit, ids)); return; }
  const list = (ids?.length ? ids : state.selectedSourceIds)
    .filter((id) => LAYERED(state.datasets[id]));

  // Draw order: the plan's order per city, backgrounds first (composition.js)
  const specs = list.flatMap((sid) => { ensureEnabled(sid, state.datasets[sid]); return enabledMapPanels(sid, state.datasets[sid]).map((p) => specFor(sid, p)); }).filter(Boolean);

  const wanted = new Set(specs.map((s) => s.key));
  for (const entry of [...added]) if (!wanted.has(entry.source)) dropEntry(entry);

  // Walk back to front so each newly mounted layer can be inserted directly
  // beneath the next one that is already on the map.
  let nextId = null;
  for (let i = specs.length - 1; i >= 0; i--) {
    const spec = specs[i];
    const existing = added.find((a) => a.source === spec.key);
    if (existing) { nextId = existing.layers[0] || nextId; continue; }
    const id = mountSpec(spec, nextId);
    if (id) nextId = id;
  }
  bottomLayerId = specs.length ? `${specs[0].key}-fill` : null;

  if (fit) smoothFit(unionBbox(specs.map((s) => s.bbox).filter(Boolean)));
}
