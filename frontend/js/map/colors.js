export const PFR_GRID = [
  ["#ffffff", "#ffef37", "#f7e02e", "#efc825"],
  ["#e8befe", "#e8be96", "#bfac6a", "#bc9023"],
  ["#df72ff", "#df7488", "#9a7c60", "#9d5115"],
  ["#aa00e5", "#ce3061", "#7f575f", "#8b0b00"],
];

export const SV_GRID = [
  ["#90be99", "#7ca793", "#557b7c"],
  ["#c7decc", "#a5c1c2", "#7894a9"],
  ["#ffffff", "#c5cde2", "#899cc4"],
];

export const SV_GREYS = ["#FFFFFF", "#D7D7D7", "#AEAEAE", "#8E8E8E"];

// Trusted palettes a composed colorScheme may name (config/renderers.yaml lists which renderer accepts which).
// Profile attribute TBD: shared palette list; a colorScheme name is resolved against this table
export const PALETTES = {
  "yellow-purple": { grid: PFR_GRID },
  "greys": { steps: SV_GREYS },
  "green-blue": { grid: SV_GRID },
};

const clamp3 = (v) => Math.min(Math.max(+v || 0, 0), 3);

export function svGreyColor(cls) {
  return SV_GREYS[clamp3(cls)];
}

export function svBivarColor(sensIdx, copingIdx) {
  const c2 = (v) => Math.min(Math.max(+v || 0, 0), 2);
  return SV_GRID[c2(copingIdx)][c2(sensIdx)];
}

export function classIndex(value, breaks) {
  let idx = 0;
  for (const b of breaks) if (value > b) idx++;
  return Math.min(idx, 3);
}
