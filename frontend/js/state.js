export const state = {
  sources: [],
  defaultSource: null,
  selectedSourceIds: [],
  datasets: {},
  dataset: null,

  figure: "figure4",
  enabledLayers: {
    riskMap: true,
    socialVulnerability: false,
    vulnerabilityDrivers: false,
    boundaryOutline: false,
    focusAreas: true,
  },
  basemap: "esri_topo",
  map: null,
  tiles: {},
  activeLayers: [],
  fetchedLayers: {},
  showMeta: false,
};

export const BASEMAPS = [
  { value: "light", label: "Light — CARTO Positron" },
  { value: "voyager", label: "CARTO Voyager" },
  { value: "esri_topo", label: "Esri Topographic" },
  { value: "satellite", label: "Satellite (Esri)" },
];

export const FIGURES = [
  {
    key: "figure4",
    label: "Bivariate PFR and MA & WB risk",
    subtitle: "MA (yellow) × WB (purple) bivariate risk · simple boundary",
  },
  {
    key: "figure5",
    label: "Grey SV background and bivariate PFR points",
    subtitle: "Grey social-vulnerability background and bivariate PFR points",
  },
  {
    key: "figure6",
    label: "Sensitivity and Coping Capacity background and PFR points",
    subtitle: "Bivariate SV background (sensitivity × coping capacity) and PFR points",
  },
  {
    key: "overview",
    label: "Overview Map",
    subtitle: "Risk-magnitude overview",
  },
];
