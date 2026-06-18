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
export const SV_LABELS = ["low", "medium", "high", "very high"];

const clamp3 = (v) => Math.min(Math.max(+v || 0, 0), 3);

export function pfrColor(props) {
  return PFR_GRID[clamp3(props.wb_idx)][clamp3(props.ma_idx)];
}

export function svGreyColor(cls) {
  return SV_GREYS[clamp3(cls)];
}

export function svBivarColor(sensIdx, copingIdx) {
  const c2 = (v) => Math.min(Math.max(+v || 0, 0), 2);
  return SV_GRID[c2(copingIdx)][c2(sensIdx)];
}

export function overviewColor(risk) {
  return risk > 0.1 ? "#ef4444" : risk > 0.01 ? "#f59e0b" : "#22c55e";
}

export function headTailBreaks(values, maxBreaks = 3) {
  let cur = values.filter((v) => Number.isFinite(v) && v > 0).sort((a, b) => a - b);
  const breaks = [];
  let n = 0;
  while (cur.length && n < maxBreaks) {
    const mean = cur.reduce((s, v) => s + v, 0) / cur.length;
    breaks.push(mean);
    const head = cur.filter((v) => v > mean);
    if (!head.length || head.length === cur.length) break;
    cur = head;
    n++;
  }
  return breaks;
}

export function classIndex(value, breaks) {
  let idx = 0;
  for (const b of breaks) if (value > b) idx++;
  return Math.min(idx, 3);
}
