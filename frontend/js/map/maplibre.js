import { state } from "../state.js";
import { esc } from "../ui/dom.js";
import { PFR_GRID, SV_GRID, SV_GREYS } from "./colors.js";

const BASEMAPS = {
  light: "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
  voyager: "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
  esri_topo: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
  satellite: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
};

let gl = null;
let added = [];

export const glAvailable = () =>
  typeof maplibregl !== "undefined" && typeof pmtiles !== "undefined";

export function initGl() {
  if (gl || !glAvailable()) return gl;
  maplibregl.addProtocol("pmtiles", new pmtiles.Protocol().tile);
  gl = new maplibregl.Map({
    container: "glmap",
    style: { version: 8, sources: {}, layers: [] },
    center: [10.0, 53.55],
    zoom: 10,
    attributionControl: { compact: true },
  });
  gl.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  gl.on("load", () => setBasemapGl(state.basemap));
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
  gl.addSource("basemap", {
    type: "raster", tiles: [BASEMAPS[key] || BASEMAPS.esri_topo],
    tileSize: 256, attribution: "© OpenStreetMap © CARTO / Esri",
  });
  gl.addLayer({ id: "basemap", type: "raster", source: "basemap" }, added[0]?.layers?.[0]);
}

const pmtilesUrl = (layer) => {
  const d = (layer.distributions || []).find((x) => x.format === "application/vnd.pmtiles" && x.path);
  return d ? `pmtiles://${new URL(d.path, location.origin).href}` : null;
};

const stepExpr = (key, breaks, outputs) => {
  const e = ["step", ["to-number", ["get", key], 0], outputs[0]];
  breaks.forEach((b, i) => e.push(b + 1e-12, outputs[i + 1]));
  return e;
};

function clearGl() {
  if (!gl) return;
  for (const a of added) {
    a.layers.forEach((id) => gl.getLayer(id) && gl.removeLayer(id));
    if (gl.getSource(a.source)) gl.removeSource(a.source);
  }
  added = [];
}

function addVector(id, layer) {
  const pm = pmtilesUrl(layer);
  const src = { source: id, layers: [] };
  if (pm) gl.addSource(id, { type: "vector", url: pm });
  else if ((layer.localPath || "").endsWith(".geojson"))
    gl.addSource(id, { type: "geojson", data: layer.localPath });
  else return null;
  src.sourceLayer = pm ? layer.sourceLayer : undefined;
  added.push(src);
  return src;
}

function fillLayer(src, suffix, paint, filter) {
  const id = `${src.source}-${suffix}`;
  const def = { id, type: "fill", source: src.source, paint };
  if (src.sourceLayer) def["source-layer"] = src.sourceLayer;
  if (filter) def.filter = filter;
  gl.addLayer(def);
  src.layers.push(id);
  return id;
}

function popupOn(id, fields) {
  gl.on("click", id, (e) => {
    const p = e.features?.[0]?.properties || {};
    const rows = fields.filter((k) => k in p)
      .map((k) => `<tr><td style="color:#64748b;padding:1px 4px">${esc(k)}</td><td style="text-align:right"><b>${esc(p[k])}</b></td></tr>`).join("");
    new maplibregl.Popup().setLngLat(e.lngLat)
      .setHTML(`<table style="font-size:12px">${rows}</table>`).addTo(gl);
  });
  gl.on("mouseenter", id, () => (gl.getCanvas().style.cursor = "pointer"));
  gl.on("mouseleave", id, () => (gl.getCanvas().style.cursor = ""));
}

export function renderGl(fit = false) {
  const ds = state.dataset;
  if (!gl || !gl.isStyleLoaded()) { gl && gl.once("load", () => renderGl(fit)); return; }
  clearGl();
  if (!ds || ds.sourceType !== "rocrate-output") return;
  const E = state.enabledLayers;
  const L = ds.layers || {};

  if (E.socialVulnerability && L.socialVulnerability) {
    const l = L.socialVulnerability, V = l.variables || {}, c = l.classification || {};
    const src = addVector("gl-sv", l);
    if (src && c.breaks_sv?.length) {
      fillLayer(src, "fill", {
        "fill-color": stepExpr(V.social_vulnerability, c.breaks_sv, SV_GREYS),
        "fill-opacity": 0.55, "fill-outline-color": "#9e9e9e",
      });
      popupOn(`${src.source}-fill`, Object.values(V));
    }
  } else if (E.vulnerabilityDrivers && L.vulnerabilityDrivers) {
    const l = L.vulnerabilityDrivers, V = l.variables || {}, c = l.classification || {};
    const src = addVector("gl-drivers", l);
    if (src && c.breaks_sensitivity?.length && c.breaks_coping?.length) {
      const rows = c.breaks_coping.length + 1;
      const rowExprs = Array.from({ length: rows }, (_, cc) =>
        stepExpr(V.sensitivity, c.breaks_sensitivity, SV_GRID[cc] || SV_GRID[SV_GRID.length - 1]));
      fillLayer(src, "fill", {
        "fill-color": stepExpr(V.coping_capacity, c.breaks_coping, rowExprs),
        "fill-opacity": 0.62, "fill-outline-color": "#9e9e9e",
      });
      popupOn(`${src.source}-fill`, Object.values(V));
    }
  }

  if (E.riskMap && L.riskMap) {
    const l = L.riskMap, V = l.variables || {}, c = l.classification || {};
    const src = addVector("gl-risk", l);
    if (src && c.breaks_ma?.length && c.breaks_wb?.length) {
      const ma = V.risk_mobility_accessibility, wb = V.risk_wellbeing;
      const rowExprs = Array.from({ length: c.breaks_wb.length + 1 }, (_, w) =>
        stepExpr(ma, c.breaks_ma, PFR_GRID[w]));
      fillLayer(src, "fill", {
        "fill-color": stepExpr(wb, c.breaks_wb, rowExprs),
        "fill-opacity": 0.75, "fill-outline-color": "#666",
      }, ["any",
        [">", ["to-number", ["get", ma], 0], c.breaks_ma[0]],
        [">", ["to-number", ["get", wb], 0], c.breaks_wb[0]]]);
      popupOn(`${src.source}-fill`, [ma, wb, V.aggregation_count].filter(Boolean));
      if (fit && l.outputFootprintBbox?.length === 4)
        gl.fitBounds(l.outputFootprintBbox, { padding: 20, duration: 0 });
    }
  }
}
