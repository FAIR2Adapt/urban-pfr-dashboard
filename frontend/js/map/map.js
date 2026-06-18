import { state } from "../state.js";

function buildTiles() {
  const osm = "© OpenStreetMap contributors";
  const cartoAttr = osm + " © CARTO";
  const cdn = (style) =>
    L.tileLayer(`https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}{r}.png`, {
      attribution: cartoAttr,
      subdomains: "abcd",
      maxZoom: 19,
    });

  return {
    light: cdn("light_all"),
    voyager: cdn("rastertiles/voyager"),
    esri_topo: L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Tiles © Esri", maxZoom: 19 }
    ),
    satellite: L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Tiles © Esri, Maxar, Earthstar Geographics", maxZoom: 19 }
    ),
  };
}

export function initMap() {
  state.map = L.map("map", { zoomControl: true, preferCanvas: true }).setView(
    [53.55, 10.0],
    11
  );
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

export function fitToLayer(geojson) {
  if (!geojson || !(geojson.features || []).length) return;
  state.map.invalidateSize();
  try {
    const bounds = L.geoJSON(geojson).getBounds();
    if (bounds.isValid()) state.map.fitBounds(bounds, { padding: [30, 30] });
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
  if (bounds && bounds.isValid()) state.map.fitBounds(bounds, { padding: [30, 30] });
}
