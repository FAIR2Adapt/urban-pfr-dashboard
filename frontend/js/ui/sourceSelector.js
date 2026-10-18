import { state } from "../state.js";
import { $, mkEl } from "./dom.js";

// The dropdown lists cities, not sources. A source is one object that serves a city (`city` in the source config);
// a deployment may list several sources for one city (demo, comparison). Which one a city shows is decided here,
// once, by one rule: the source already selected (the URL's ?source=), else the one last shown for that city in this
// session, else the configured default, else config order.
const ALL = "__all__";

export const cityName = (s) => s.city || s.label || s.id;

function cities() {
  const out = [];
  for (const s of state.sources) {
    const name = cityName(s);
    let c = out.find((x) => x.name === name);
    if (!c) { c = { name, sources: [], enabled: false }; out.push(c); }
    c.sources.push(s);
    c.enabled = c.enabled || !!s.enabled;
  }
  return out;
}

export function sourceForCity(name) {
  const own = state.sources.filter((s) => s.enabled && cityName(s) === name);
  const chosen = own.find((s) => state.selectedSourceIds.includes(s.id)) || own.find((s) => s.id === state.sourceByCity[name]) ||
    own.find((s) => s.id === state.defaultSource) || own[0] || null;
  if (chosen) state.sourceByCity[name] = chosen.id;   // a city keeps the object it was last shown from in this session
  return chosen;
}

const selectedCities = () =>
  new Set(state.selectedSourceIds.map((id) => cityName(state.sources.find((s) => s.id === id) || { id })));

export function buildSourceSelector(onChange) {
  const select = $("sourceSelector");
  if (!select) return;
  select.innerHTML = "";

  const list = cities();
  const open = list.filter((c) => c.enabled);
  const chosen = selectedCities();
  const allSelected = open.length > 1 && open.every((c) => chosen.has(c.name));

  if (open.length > 1) {
    const optAll = mkEl("option");
    optAll.value = ALL;
    optAll.textContent = "All cities";
    optAll.selected = allSelected;
    select.appendChild(optAll);
  }
  for (const c of list) {
    const opt = mkEl("option");
    opt.value = c.name;
    opt.textContent = c.name + (c.enabled ? "" : " (planned)");
    opt.disabled = !c.enabled;
    if (!allSelected && chosen.size === 1 && chosen.has(c.name)) opt.selected = true;
    const note = c.sources.find((s) => s.note)?.note;
    if (note) opt.title = note;
    select.appendChild(opt);
  }

  if (!select.dataset.wired) {
    select.addEventListener("change", () => {
      const picked = select.value === ALL ? cities().filter((c) => c.enabled).map((c) => c.name) : [select.value];
      state.selectedSourceIds = picked.map((name) => sourceForCity(name)).filter(Boolean).map((s) => s.id);
      onChange(state.selectedSourceIds);
    });
    select.dataset.wired = "1";
  }
}
