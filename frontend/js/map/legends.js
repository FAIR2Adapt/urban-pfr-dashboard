// The legend reads the same panels the map draws and shows what the data declares: the class breaks, how they were
// made (method) and their status, the axis titles from the object's description of the bound columns, and the
// classes the map leaves out. With several cities there is one legend per city and renderer, since the breaks differ.
import { state, LAYERED } from "../state.js";
import { enabledMapPanels } from "../composition.js";
import { $, mkEl, esc } from "../ui/dom.js";
import { cityName } from "../ui/sourceSelector.js";
import { PFR_GRID, SV_GRID, SV_GREYS } from "./colors.js";
import { paletteFor } from "./renderers.js";
import { axisTitle, axisUnit, classRanges, formatBreak } from "./classes.js";
import { stateKey } from "../policy.js";

// a layer of a source without a Dashboard FDO has no panel name of its own; the renderer's title stands in
const TITLES = { "bivariate-map": "Pluvial flood risk (PFR)", "single-variable-map": "Social vulnerability (SV)",
  "bivariate-background": "Vulnerability drivers (sensitivity × coping capacity)", "outline": "Administrative boundaries", "outline-focus": "Focus areas" };
const LEGEND = { "bivariate-map": legendBivariate, "single-variable-map": legendSingle, "bivariate-background": legendBivariateBackground, "outline": legendBoundary, "outline-focus": legendFocus };

export function buildLegend() {
  const el = $("legendContent");
  if (!el) return;
  el.innerHTML = "";
  const shown = state.selectedSourceIds.filter((sid) => LAYERED(state.datasets[sid]));
  for (const sid of shown) {
    const dataset = state.datasets[sid];
    const panels = enabledMapPanels(sid, dataset).filter((p) => LEGEND[p.renderer]);
    if (!panels.length) continue;
    if (shown.length > 1) el.appendChild(cityHeading(sid, dataset));
    for (const p of panels) {
      const title = dataset.composition ? p.label : TITLES[p.renderer] || p.label;
      el.appendChild(LEGEND[p.renderer](p.layer, title, paletteFor(p.renderer, p.layer), state.leftOut[stateKey(sid, p.key)]));
    }
  }
  if (!el.children.length) el.innerHTML = `<span class="grid-labels">No layers selected.</span>`;
}

function cityHeading(sid, dataset) {
  const d = mkEl("div", "legend-city");
  d.textContent = cityName(state.sources.find((s) => s.id === sid) || { id: sid, label: dataset.label });
  return d;
}

const section = () => mkEl("div", "legend-section");

function heading(s, text) {
  const strong = mkEl("strong");
  strong.textContent = text;
  s.appendChild(strong);
}

function swatch(color, label, none = false) {
  const row = mkEl("div", "swatch-row");
  row.innerHTML = `<div class="swatch${none ? " none" : ""}" style="${none ? "" : `background:${color}`}"></div><span class="grid-labels">${label}</span>`;
  return row;
}

// a tick label at each class boundary, numbers as the object states them (classes.js)
const ticks = (channel) => (Array.isArray(channel?.breaks) ? channel.breaks.map(formatBreak) : []);

// the title of an axis: the object's description of the column and its unit
function axisTitle_(channel, layer) {
  const unit = axisUnit(channel, layer);
  return esc(axisTitle(channel, layer)) + (unit ? ` <span class="legend-unit">${esc(unit)}</span>` : "");
}

// a two-axis legend laid out as a chart: y upwards, x to the right, tick numbers at the boundaries between classes
function bivariateChart(colors, chX, chY, layer, blank) {
  const rows = colors.length, cols = colors[0].length;
  const wrap = mkEl("div", "bv");
  wrap.innerHTML = `
    <div class="bv-ytitle">${axisTitle_(chY, layer)}</div>
    <div class="bv-body">
      <div class="bv-yticks">${ticks(chY).map((t, i) => `<span style="bottom:${((i + 1) / rows) * 100}%">${esc(t)}</span>`).join("")}</div>
      <div class="bv-grid" style="grid-template-columns:repeat(${cols}, var(--bv-cell))">${
        Array.from({ length: rows }, (_, r) => rows - 1 - r).map((y) => colors[y].map((c, x) =>
          `<div class="bv-cell${blank && x === 0 && y === 0 ? " none" : ""}" style="${blank && x === 0 && y === 0 ? "" : `background:${c}`}"></div>`).join("")).join("")}</div>
    </div>
    <div class="bv-xticks">${ticks(chX).map((t, i) => `<span style="left:${((i + 1) / cols) * 100}%">${esc(t)}</span>`).join("")}</div>
    <div class="bv-xtitle">${axisTitle_(chX, layer)}</div>`;
  return wrap;
}

// the classification method as the object states it; the status of the thresholds is in the context strip
function methodLine(layer) {
  const method = layer?.classification?.method;
  if (!method) return null;
  const d = mkEl("div", "legend-note");
  d.textContent = `Classes: ${method}`;
  return d;
}

// what the risk layer left out, as counted when the cells were read (the WebGL path does not count)
function leftOutRow(counts) {
  const n = counts ? ` (${counts.belowFirstBreak.toLocaleString()} of ${counts.total.toLocaleString()} cells${counts.noValue ? `, ${counts.noValue.toLocaleString()} without a value` : ""})` : "";
  return swatch(null, `Not drawn: lowest class on both axes, or no value${n}`, true);
}

// 4 × 4: up = the y channel (rows, high at the top), right = the x channel (columns), as the map colours grid[y][x];
// the cell below the first break on both axes is left blank, as the map leaves those cells out
function legendBivariate(layer, title, palette = { grid: PFR_GRID }, leftOut = null) {
  const s = section();
  heading(s, title);
  const ch = layer?.channels || {};
  s.appendChild(bivariateChart(palette.grid || PFR_GRID, ch.x, ch.y, layer, true));
  s.appendChild(leftOutRow(leftOut));
  const m = methodLine(layer);
  if (m) s.appendChild(m);
  return s;
}

// steps from light to dark, each with its declared range; the qualitative words only when they match the class count
function legendSingle(layer, title, palette = { steps: SV_GREYS }) {
  const s = section();
  heading(s, title);
  const steps = palette.steps || SV_GREYS, ch = layer?.channels?.value, ranges = classRanges(ch?.breaks);
  steps.forEach((color, i) => s.appendChild(swatch(color, ranges[i] ? esc(ranges[i]) : `class ${i}`)));
  s.appendChild(swatch(null, "No value: not drawn", true));
  const t = mkEl("div", "legend-axis"); t.innerHTML = axisTitle_(ch, layer); s.appendChild(t);
  const m = methodLine(layer);
  if (m) s.appendChild(m);
  return s;
}

// 3 × 3: up = the y channel (rows, high at the top), right = the x channel (columns), as the map colours grid[y][x]
function legendBivariateBackground(layer, title, palette = { grid: SV_GRID }) {
  const s = section();
  heading(s, title);
  const ch = layer?.channels || {};
  s.appendChild(bivariateChart(palette.grid || SV_GRID, ch.x, ch.y, layer, false));
  s.appendChild(swatch(null, "No value: not drawn", true));
  const m = methodLine(layer);
  if (m) s.appendChild(m);
  return s;
}

function legendBoundary(layer, title) {
  const s = section();
  s.innerHTML = `<div class="swatch-row"><div style="width:22px;height:14px;border:1px solid #1e3a5f;flex-shrink:0;background:rgba(30,58,95,.06)"></div>
    <span class="grid-labels">${esc(title)}</span></div>`;
  return s;
}

function legendFocus(layer, title) {
  const s = section();
  s.innerHTML = `<div class="swatch-row"><div style="width:22px;height:14px;border:2px solid #000;flex-shrink:0;background:transparent"></div>
    <span class="grid-labels">${esc(title)}</span></div>`;
  return s;
}
