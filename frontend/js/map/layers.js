import { state } from "../state.js";
import { esc } from "../ui/dom.js";
import { fetchResource, resourceUrl } from "../api/dataService.js";
import {
  pfrColor,
  svGreyColor,
  svBivarColor,
  overviewColor,
  SV_LABELS,
  PFR_GRID,
  headTailBreaks,
  classIndex,
} from "./colors.js";

const boundariesData = () => state.dataset?.layers?.boundaries?.data || null;
const riskData = () => state.dataset?.layers?.riskMap?.data || null;

function track(layer) {
  layer.addTo(state.map);
  state.activeLayers.push(layer);
  return layer;
}

export function clearLayers() {
  for (const layer of state.activeLayers) state.map.removeLayer(layer);
  state.activeLayers = [];
}

export function addOutline() {
  const data = boundariesData();
  if (!data) return;
  track(
    L.geoJSON(data, {
      style: () => ({ fill: false, color: "#1e3a5f", weight: 0.7, opacity: 0.7 }),
    })
  );
}

export function addGreySV() {
  const data = boundariesData();
  if (!data) return;
  track(
    L.geoJSON(data, {
      style: (f) => {
        const cls = +(f.properties.sv_class || 0);
        const alpha = [0.05, 0.28, 0.5, 0.68][cls] ?? 0.05;
        return {
          fillColor: svGreyColor(cls),
          fillOpacity: alpha,
          color: "#9e9e9e",
          weight: 0.4,
          opacity: 0.6,
        };
      },
      onEachFeature: (f, l) => l.bindPopup(unitPopup(f)),
    })
  );
}

export function addBivarSV() {
  const data = boundariesData();
  if (!data) return;
  track(
    L.geoJSON(data, {
      style: (f) => ({
        fillColor: svBivarColor(f.properties.sens_idx, f.properties.coping_idx),
        fillOpacity: 0.62,
        color: "#9e9e9e",
        weight: 0.4,
        opacity: 0.5,
      }),
      onEachFeature: (f, l) => l.bindPopup(unitPopup(f)),
    })
  );
}

export function addRiskPoints() {
  const data = riskData();
  if (!data) return;
  track(
    L.geoJSON(data, {
      pointToLayer: (f, latlng) =>
        L.circleMarker(latlng, {
          radius: 2.8,
          fillColor: pfrColor(f.properties),
          color: "#444",
          weight: 0.25,
          opacity: 0.8,
          fillOpacity: 0.92,
        }),
      onEachFeature: (f, l) => l.bindPopup(buildingPopup(f)),
    })
  );
}

export function addOverviewPoints() {
  const data = riskData();
  if (!data) return;
  track(
    L.geoJSON(data, {
      pointToLayer: (f, latlng) => {
        const r = Math.max(+f.properties.rima, +f.properties.riwb);
        return L.circleMarker(latlng, {
          radius: 3,
          fillColor: overviewColor(r),
          color: "#333",
          weight: 0.4,
          opacity: 0.8,
          fillOpacity: 0.85,
        });
      },
      onEachFeature: (f, l) => l.bindPopup(buildingPopup(f)),
    })
  );
}

function buildingPopup(f) {
  const p = f.properties;
  const col = pfrColor(p);
  return `<div style="font-size:12px;min-width:170px">
    <div style="display:flex;align-items:center;gap:7px;margin-bottom:7px">
      <div style="width:14px;height:14px;border-radius:3px;background:${col};border:1px solid #555"></div>
      <strong>Building ${esc(p.id || "–")}</strong>
    </div>
    <table style="border-collapse:collapse;width:100%">
      <tr><td style="color:#64748b;padding:1px 4px">RIMA (MA)</td>
          <td style="text-align:right;font-weight:600">${(+p.rima).toFixed(5)}</td></tr>
      <tr><td style="color:#64748b;padding:1px 4px">RIWB (WB)</td>
          <td style="text-align:right;font-weight:600">${(+p.riwb).toFixed(5)}</td></tr>
      <tr><td style="color:#64748b;padding:1px 4px">SVF</td>
          <td style="text-align:right">${(+p.svf).toFixed(4)}</td></tr>
      <tr><td style="color:#64748b;padding:1px 4px">Grid (WB,MA)</td>
          <td style="text-align:right">${p.wb_idx},${p.ma_idx}</td></tr>
    </table></div>`;
}

function unitPopup(f) {
  const p = f.properties;
  return `<div style="font-size:12px">
    <strong>Statistical Unit</strong><br>
    SV: <b>${SV_LABELS[+(p.sv_class || 0)]}</b> &nbsp; SVF=${(+(p.svf_value || 0)).toFixed(4)}
  </div>`;
}

async function cachedFetch(url) {
  if (!url) return null;
  if (url in state.fetchedLayers) return state.fetchedLayers[url];
  try {
    const geo = await fetchResource(url);
    state.fetchedLayers[url] = geo;
    return geo;
  } catch (e) {
    console.warn("Could not fetch resource:", url, e.message);
    state.fetchedLayers[url] = null;
    return null;
  }
}

export async function addRocrateOutput(sourceId, output) {
  const geo = await cachedFetch(resourceUrl(sourceId, output));
  if (!geo) return null;
  const feats = geo.features || [];
  const fields = output.fields || [];
  const hasRisk =
    fields.includes("smoothed_RIMA") ||
    feats.some((f) => f.properties && "smoothed_RIMA" in f.properties);

  if (hasRisk) {
    addRiskSurface(geo, feats);
  } else if (fields.includes("Sensitivity") && fields.includes("CC")) {

    const sB = headTailBreaks(feats.map((f) => +f.properties?.Sensitivity || 0), 2);
    const cB = headTailBreaks(feats.map((f) => +f.properties?.CC || 0), 2);
    track(
      L.geoJSON(geo, {
        style: (f) => ({
          fillColor: svBivarColor(
            classIndex(+f.properties?.Sensitivity || 0, sB),
            classIndex(+f.properties?.CC || 0, cB)
          ),
          color: "#9e9e9e",
          weight: 0.4,
          opacity: 0.5,
          fillOpacity: 0.62,
        }),
        onEachFeature: (f, l) => l.bindPopup(genericPopup(f, output.label)),
      })
    );
  } else if (fields.includes("SVF")) {
    const svB = headTailBreaks(feats.map((f) => +f.properties?.SVF || 0));
    track(
      L.geoJSON(geo, {
        style: (f) => ({
          fillColor: svGreyColor(classIndex(+f.properties?.SVF || 0, svB)),
          color: "#9e9e9e",
          weight: 0.4,
          opacity: 0.6,
          fillOpacity: 0.55,
        }),
        onEachFeature: (f, l) => l.bindPopup(genericPopup(f, output.label)),
      })
    );
  } else {
    track(
      L.geoJSON(geo, {
        style: () => ({ color: "#1e3a5f", weight: 0.7, opacity: 0.8, fillColor: "#1e3a5f", fillOpacity: 0.06 }),
        onEachFeature: (f, l) => l.bindPopup(genericPopup(f, output.label)),
      })
    );
  }
  return geo;
}

function addRiskSurface(geo, feats) {
  const maBreaks = headTailBreaks(feats.map((f) => +f.properties?.smoothed_RIMA || 0));
  const wbBreaks = headTailBreaks(feats.map((f) => +f.properties?.smoothed_RIWB || 0));
  const colorFor = (p) =>
    PFR_GRID[classIndex(+p?.smoothed_RIWB || 0, wbBreaks)][classIndex(+p?.smoothed_RIMA || 0, maBreaks)];

  const keep = (p) =>
    classIndex(+p?.smoothed_RIMA || 0, maBreaks) > 0 ||
    classIndex(+p?.smoothed_RIWB || 0, wbBreaks) > 0;

  const pts = [];
  const props = [];
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const f of feats) {
    const c = centroidLonLat(f.geometry);
    if (!c) continue;
    pts.push(c);
    props.push(f.properties);
    minX = Math.min(minX, c[0]); maxX = Math.max(maxX, c[0]);
    minY = Math.min(minY, c[1]); maxY = Math.max(maxY, c[1]);
  }

  if (pts.length && typeof d3 !== "undefined" && d3.Delaunay) {
    const pad = 0.003;
    const voronoi = d3.Delaunay.from(pts).voronoi([minX - pad, minY - pad, maxX + pad, maxY + pad]);

    const cap = Math.sqrt(((maxX - minX) * (maxY - minY)) / Math.max(pts.length, 1)) * 1.2;
    const cells = [];
    for (let i = 0; i < pts.length; i++) {
      if (!keep(props[i])) continue;
      const cell = voronoi.cellPolygon(i);
      if (!cell) continue;
      const [cx, cy] = pts[i];
      const clipped = clipToBox(cell, cx - cap, cy - cap, cx + cap, cy + cap);
      if (!clipped || clipped.length < 3) continue;
      const col = colorFor(props[i]);
      cells.push(
        L.polygon(
          clipped.map(([x, y]) => [y, x]),
          { color: col, weight: 0.5, fillColor: col, fillOpacity: 0.8 }
        ).bindPopup(riskFieldPopup({ properties: props[i] }))
      );
    }
    track(L.layerGroup(cells));
    return;
  }

  track(
    L.geoJSON(geo, {
      filter: (f) => keep(f.properties),
      style: (f) => ({ fillColor: colorFor(f.properties), color: "#333", weight: 0.3, opacity: 0.5, fillOpacity: 0.85 }),
      pointToLayer: (f, ll) =>
        L.circleMarker(ll, { radius: 3, fillColor: colorFor(f.properties), color: "#333", weight: 0.3, fillOpacity: 0.9 }),
      onEachFeature: (f, l) => l.bindPopup(riskFieldPopup(f)),
    })
  );
}

function clipToBox(poly, xmin, ymin, xmax, ymax) {
  const clip = (pts, inside, intersect) => {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      const ain = inside(a);
      const bin = inside(b);
      if (ain) {
        out.push(a);
        if (!bin) out.push(intersect(a, b));
      } else if (bin) {
        out.push(intersect(a, b));
      }
    }
    return out;
  };
  let p = poly;
  p = clip(p, (q) => q[0] >= xmin, (a, b) => { const t = (xmin - a[0]) / (b[0] - a[0]); return [xmin, a[1] + t * (b[1] - a[1])]; });
  if (!p.length) return null;
  p = clip(p, (q) => q[0] <= xmax, (a, b) => { const t = (xmax - a[0]) / (b[0] - a[0]); return [xmax, a[1] + t * (b[1] - a[1])]; });
  if (!p.length) return null;
  p = clip(p, (q) => q[1] >= ymin, (a, b) => { const t = (ymin - a[1]) / (b[1] - a[1]); return [a[0] + t * (b[0] - a[0]), ymin]; });
  if (!p.length) return null;
  p = clip(p, (q) => q[1] <= ymax, (a, b) => { const t = (ymax - a[1]) / (b[1] - a[1]); return [a[0] + t * (b[0] - a[0]), ymax]; });
  return p.length ? p : null;
}

function centroidLonLat(geom) {
  if (!geom) return null;
  let ring;
  switch (geom.type) {
    case "Point":
      return geom.coordinates.slice(0, 2);
    case "Polygon":
      ring = geom.coordinates[0];
      break;
    case "MultiPolygon":
      ring = geom.coordinates[0] && geom.coordinates[0][0];
      break;
    default:
      return null;
  }
  if (!ring || !ring.length) return null;
  let sx = 0, sy = 0;
  for (const [x, y] of ring) {
    sx += x;
    sy += y;
  }
  return [sx / ring.length, sy / ring.length];
}

function riskFieldPopup(f) {
  const p = f.properties || {};
  const num = (v) => (Number.isFinite(+v) ? (+v).toFixed(4) : "–");
  return `<div style="font-size:12px;min-width:150px">
    <strong>${esc(p.id || "Building")}</strong>
    <table style="border-collapse:collapse;width:100%;margin-top:4px">
      <tr><td style="color:#64748b;padding:1px 4px">smoothed_RIMA</td>
          <td style="text-align:right;font-weight:600">${num(p.smoothed_RIMA)}</td></tr>
      <tr><td style="color:#64748b;padding:1px 4px">smoothed_RIWB</td>
          <td style="text-align:right;font-weight:600">${num(p.smoothed_RIWB)}</td></tr>
    </table></div>`;
}

function genericPopup(f, label) {
  const p = f.properties || {};
  const keys = Object.keys(p).filter((k) => k.toLowerCase() !== "geometry").slice(0, 6);
  const rows = keys
    .map(
      (k) => `<tr><td style="color:#64748b;padding:1px 4px">${esc(k)}</td>
        <td style="text-align:right">${esc(p[k])}</td></tr>`
    )
    .join("");
  return `<div style="font-size:12px;min-width:150px">
    <strong>${esc(label || "Feature")}</strong>
    ${rows ? `<table style="border-collapse:collapse;width:100%;margin-top:4px">${rows}</table>` : ""}
  </div>`;
}
