// The trusted local renderers, in one place: what each draws on which channels, whether it needs class breaks, which
// palette it uses by default. The Leaflet drawing, the MapLibre spec and the legend of a renderer are looked up by this
// id in layers.js, maplibre.js and legends.js. No DOM here, so the rules can be tested with node.
import { PALETTES } from "./colors.js";

export const RENDERERS = {
  "bivariate-map": { kind: "map", channels: ["x", "y"], needsBreaks: true, classes: 4, palette: "yellow-purple" },
  "single-variable-map": { kind: "map", channels: ["value"], needsBreaks: true, classes: 4, palette: "greys" },
  "bivariate-background": { kind: "map", channels: ["x", "y"], needsBreaks: true, classes: 3, palette: "green-blue" },
  "outline": { kind: "map", channels: [], needsBreaks: false, palette: null },
  "outline-focus": { kind: "map", channels: [], needsBreaks: false, palette: null },
  "claims-list": { kind: "claims-list" },
  "metadata-card": { kind: "metadata-card" },
};

// A renderer draws only what the data declares: every channel bound to a column and, when the renderer classifies,
// breaks in the renderer's shape: exactly classes - 1 finite numbers, increasing. No path computes, pads or trims
// breaks (the classification is meaning-changing); a layer whose breaks do not fit is not drawn, and says so.
export function drawableChannels(rendererId, layer) {
  const spec = RENDERERS[rendererId];
  if (!spec || spec.kind !== "map" || !layer) return false;
  const channels = layer.channels || {};
  return spec.channels.every((name) => {
    const channel = channels[name];
    return !!channel?.column && (!spec.needsBreaks || breaksFit(channel.breaks, spec.classes));
  });
}

export const breaksFit = (breaks, classes) =>
  Array.isArray(breaks) && breaks.length === classes - 1
  && breaks.every((b, i) => typeof b === "number" && Number.isFinite(b) && (i === 0 || b > breaks[i - 1]));

// why a classified layer is not drawn, for the sidebar
export function breaksProblem(rendererId, layer) {
  const spec = RENDERERS[rendererId];
  if (!spec?.needsBreaks) return null;
  for (const name of spec.channels) {
    const b = layer?.channels?.[name]?.breaks;
    if (!Array.isArray(b) || !b.length) return `no declared class breaks for channel ${name}`;
    if (b.length !== spec.classes - 1) return `channel ${name} declares ${b.length} breaks; this renderer draws ${spec.classes} classes (${spec.classes - 1} breaks)`;
    if (!breaksFit(b, spec.classes)) return `the breaks of channel ${name} are not finite, increasing numbers`;
  }
  return null;
}

// The palette a layer is drawn with: its composed colorScheme when the renderer knows it, else the renderer's default.
export function paletteFor(rendererId, layer) {
  const spec = RENDERERS[rendererId] || {};
  const wanted = layer?.style?.colorScheme;
  const name = wanted && PALETTES[wanted] ? wanted : spec.palette;
  return name ? PALETTES[name] : null;
}
