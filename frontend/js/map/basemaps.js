// The basemaps the page offers, each with the attribution its provider requires. Both map paths and the sidebar read
// this list; the tiles are loaded from the providers' servers at run time (README, "Built with").
export const BASEMAPS = [
  { value: "esri_topo", label: "Esri Topographic", maxZoom: 19,
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles © Esri — Esri, HERE, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, and the GIS User Community" },
  { value: "light", label: "Light grey (Esri)", maxZoom: 19, nativeZoom: 16,   // a neutral canvas under the choropleths; tiles end at 16, scaled beyond
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS User Community" },
  { value: "satellite", label: "Satellite (Esri)", maxZoom: 19,
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles © Esri — Esri, Maxar, Earthstar Geographics, and the GIS User Community" },
];

export const basemapOf = (value) => BASEMAPS.find((b) => b.value === value) || BASEMAPS[0];
