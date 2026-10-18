// Legend rules without DOM: how declared class breaks become labelled ranges, how a threshold status reads, how an axis
// is titled from what the object says about the bound column. Tested with node (tests/classes.test.mjs).

// a break as the data states it, short: 0.63 → "0.63", 0.00010378 → "0.000104", 12.5 → "12.5", 1.5e-5 → "1.5e-5"
export function formatBreak(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return String(v ?? "");
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1e-4 && a < 1e6) return (+v.toPrecision(3)).toString().includes("e") ? (+v.toPrecision(3)).toFixed(6).replace(/0+$/, "") : String(+v.toPrecision(3));
  return v.toExponential(1).replace(/\.0e/, "e").replace("e-0", "e-").replace("e+", "e");
}

// n breaks give n+1 classes: "≤ b0", "b0 – b1", …, "> b(n-1)"; class 0 is what classIndex() gives below the first break
export function classRanges(breaks) {
  const b = (breaks || []).filter((v) => typeof v === "number" && Number.isFinite(v));
  if (!b.length) return [];
  let text = b.map((v) => formatBreak(v));
  if (new Set(text).size < text.length) text = b.map((v) => (Math.abs(v) >= 1e-4 && Math.abs(v) < 1e6 ? String(+v.toPrecision(6)) : v.toExponential(5)));   // neighbours that round alike
  const out = [`≤ ${text[0]}`];
  for (let i = 1; i < b.length; i++) out.push(`${text[i - 1]} – ${text[i]}`);
  out.push(`> ${text[b.length - 1]}`);
  return out;
}

// the status of the class thresholds as the object states it, readable; nothing is assumed when it is absent
export function statusText(thresholdStatus) {
  const s = String(thresholdStatus || "").trim();
  if (!s) return "";
  if (s.startsWith("provisional")) return "provisional" + (s.includes("validation") ? ", pending scientific validation" : "");
  if (s.startsWith("validated") || s.startsWith("agreed")) return s.replace(/_/g, " ");
  return s.replace(/_/g, " ");
}

// the axis title of a channel: the object's description of the bound column, else the variable key as words, else the column
export function axisTitle(channel, layer) {
  const column = channel?.column;
  if (!column) return "";
  const info = layer?.variableInfo?.[column];
  if (info?.description) return info.description;
  const key = info?.key || Object.keys(layer?.variables || {}).find((k) => layer.variables[k] === column);
  return key ? key.replace(/_/g, " ") : column;
}

// the unit the object states for a column, when it states one
export const axisUnit = (channel, layer) => layer?.variableInfo?.[channel?.column]?.unit || "";

// a cell value for a popup: an integer as it is, a fraction with six significant digits, anything else as text
export function formatValue(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = typeof v === "number" ? v : (typeof v === "string" && v.trim() !== "" ? Number(v) : NaN);
  if (!Number.isFinite(n)) return String(v);
  return Number.isInteger(n) ? String(n) : String(+n.toPrecision(6));
}
