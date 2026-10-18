// Consumer policies of this page that no profile term decides, as pure functions (testable with node):
// which panels the current view may show, how enabled state is keyed, and in which order map panels are stacked.

// Panel state belongs to one dashboard: the same panel id in two sources is two panels.
export const stateKey = (sourceId, panelKey) => `${sourceId}::${panelKey}`;

// Access is decided by the access state of what the panel binds and the tier of its layer, never by the renderer.
export function accessAllows(panel, view) {
  if (panel.access === "restricted") return false;
  const tier = panel.layer?.accessTier || "public";
  return tier === "public" || (tier === "private" && view === "private");
}

// Stacking: exclusive-group panels (backgrounds) below the others, then the Dashboard FDO's position. The
// profile gives a panel one `position`; this page uses it for the sidebar order and, within each group, the z-order.
// The footprint of what is drawn: the union of the declared bounding boxes ([west, south, east, north]) of the
// layers, read from the objects; null when none declares one. The map is moved there before any viewport-bound read.
export function unionBbox(bboxes) {
  let out = null;
  for (const b of bboxes || []) {
    if (!Array.isArray(b) || b.length !== 4 || b.some((v) => typeof v !== "number" || Number.isNaN(v))) continue;
    out = out ? [Math.min(out[0], b[0]), Math.min(out[1], b[1]), Math.max(out[2], b[2]), Math.max(out[3], b[3])] : [...b];
  }
  return out;
}

// Several cities on one map share one set of controls: a control addresses every panel drawn by the same renderer,
// in every selected source. The first source leads; the others take its enabled flags per renderer.
export function alignedEnabled(enabled, leadSourceId, leadPanels, sourceId, panels) {
  const out = { ...enabled };
  for (const panel of panels) {
    const lead = leadPanels.find((p) => p.renderer === panel.renderer);
    if (lead) out[stateKey(sourceId, panel.key)] = !!enabled[stateKey(leadSourceId, lead.key)];
  }
  return out;
}

export function drawOrder(panels) {
  return [...panels].sort((a, b) =>
    (a.exclusiveGroup ? 0 : 1) - (b.exclusiveGroup ? 0 : 1) || (a.position ?? 99) - (b.position ?? 99) || String(a.key).localeCompare(String(b.key)));
}
