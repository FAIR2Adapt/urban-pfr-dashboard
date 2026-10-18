import { state } from "../state.js";
import { BASEMAPS } from "./basemaps.js";

function buildTiles() {
  const out = {};
  for (const b of BASEMAPS) out[b.value] = L.tileLayer(b.url, { attribution: b.attribution, maxZoom: b.maxZoom, maxNativeZoom: b.nativeZoom || b.maxZoom });
  return out;
}

export function initMap() {
  state.map = L.map("map", { zoomControl: true, preferCanvas: true, attributionControl: false }).setView(
    [53.55, 10.0],
    11
  );
  L.control.attribution({ position: "bottomleft", prefix: false }).addTo(state.map);   // the legend sits bottom right
  L.control.scale({ position: "bottomleft", imperial: false }).addTo(state.map);
  state.tiles = buildTiles();
  state.tiles[state.basemap].addTo(state.map);

  setTimeout(() => state.map.invalidateSize(), 120);
}

export function setBasemap(name) {
  if (!state.tiles[name] || name === state.basemap) return;
  state.map.removeLayer(state.tiles[state.basemap]);
  state.basemap = name;
  state.tiles[name].addTo(state.map);
}

// Animated camera for the Leaflet path; honours prefers-reduced-motion.
const FIT_OPTS = {
  padding: [30, 30],
  animate: !(window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches),
  duration: 1.2,
};

// The declared footprint ([west, south, east, north]) of what is about to be drawn. The flight is the page's own
// move, so the "moveend" it ends with is not a reason to read again; the reads use the footprint, not the camera.
export function fitToBbox(bbox) {
  if (!bbox || bbox.length !== 4) return;
  state.map.invalidateSize();
  state.selfMoves += 1;
  setTimeout(() => { state.selfMoves = Math.max(0, state.selfMoves - 1); }, 4000);   // a fit that does not move fires no event
  state.map.flyToBounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], FIT_OPTS);
}

export function fitToLayer(geojson) {
  if (!geojson || !(geojson.features || []).length) return;
  state.map.invalidateSize();
  try {
    const bounds = L.geoJSON(geojson).getBounds();
    if (bounds.isValid()) state.map.flyToBounds(bounds, FIT_OPTS);
  } catch {

  }
}

export function fitToLayers(geojsons) {
  state.map.invalidateSize();
  let bounds = null;
  for (const g of geojsons || []) {
    if (!g || !(g.features || []).length) continue;
    try {
      const b = L.geoJSON(g).getBounds();
      if (b.isValid()) bounds = bounds ? bounds.extend(b) : b;
    } catch {

    }
  }
  if (bounds && bounds.isValid()) state.map.flyToBounds(bounds, FIT_OPTS);
}
