// layered dataset? decided by its shape, not the source name
export const LAYERED = (ds) =>
  !!ds && (ds.panels != null || Object.values(ds.layers || {}).some((l) => Array.isArray(l?.distributions)));

export const state = {
  sources: [],
  defaultSource: null,
  selectedSourceIds: [],
  sourceByCity: {},           // city -> source id last shown for it (sourceSelector.js)
  datasets: {},
  dataset: null,

  view: "public",            // public | private  (private = building-level, authorized)
  renderer: new URLSearchParams(location.search).get("renderer") || "maplibre",
  enabledPanels: {},          // panel key -> on/off; filled from the composition (composition.js)
  basemap: "light",           // the neutral canvas; the choropleth carries the colour
  map: null,
  tiles: {},
  activeLayers: [],
  selfMoves: 0,               // camera moves made by the page itself; their "moveend" must not start a re-read (app.js)
  fetchedLayers: {},
  leftOut: {},                // per source and panel: cells the risk layer left out (Leaflet path counts them)
  drawErrors: [],            // layers the map could not draw, with the reason
  showMeta: false,
};
