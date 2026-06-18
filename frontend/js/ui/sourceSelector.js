import { state } from "../state.js";
import { $, mkEl } from "./dom.js";

const ALL = "__all__";

export function buildSourceSelector(onChange) {
  const select = $("sourceSelector");
  if (!select) return;
  select.innerHTML = "";

  const enabled = state.sources.filter((s) => s.enabled);
  const allSelected =
    enabled.length > 1 &&
    state.selectedSourceIds.length === enabled.length &&
    enabled.every((s) => state.selectedSourceIds.includes(s.id));
  const single = state.selectedSourceIds.length === 1 ? state.selectedSourceIds[0] : null;

  if (enabled.length > 1) {
    const optAll = mkEl("option");
    optAll.value = ALL;
    optAll.textContent = "All cities";
    optAll.selected = allSelected;
    select.appendChild(optAll);
  }

  state.sources.forEach((s) => {
    const opt = mkEl("option");
    opt.value = s.id;
    opt.textContent = cityName(s) + (s.enabled ? "" : " (planned)");
    opt.disabled = !s.enabled;
    if (!allSelected && s.id === single) opt.selected = true;
    if (s.note) opt.title = s.note;
    select.appendChild(opt);
  });

  if (!select.dataset.wired) {
    select.addEventListener("change", () => {
      state.selectedSourceIds =
        select.value === ALL
          ? state.sources.filter((s) => s.enabled).map((s) => s.id)
          : [select.value];
      onChange(state.selectedSourceIds);
    });
    select.dataset.wired = "1";
  }
}

function cityName(s) {
  const base = s.label || s.id || "";
  const first = base.split(/[\s—-]+/).filter(Boolean)[0] || s.id;
  return first ? first.charAt(0).toUpperCase() + first.slice(1) : s.id;
}
