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

// LEGACY-COMPAT ONLY: variable mapping for old claim-based demo
// #TODO remove these names might not be used then after final metadata.
const LEGACY_VARIABLES = {
  risk_mobility_accessibility: "smoothed_RIMA",
  risk_wellbeing: "smoothed_RIWB",
  social_vulnerability: "SVF",
  sensitivity: "Sensitivity",
  coping_capacity: "CC",
  cell_id: "healpix_id",
  aggregation_count: "n_buildings",
};

// TODO check this final Hard cap mirroring the server-side FGB bbox limit.
const BBOX_LIMIT = 20000;

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

// Viewport-aware fetch: fgb-bbox layers ask the server only for the current
// map extent (C4 route); everything else keeps the plain resource fetch.
async function fetchLayerData(sourceId, output) {
  const url = resourceUrl(sourceId, output);
  if (!url) return null;
  const strategy = output.renderingStrategy || "";
  if (strategy.startsWith("fgb-bbox") && state.map) {
    const b = state.map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
      .map((v) => v.toFixed(5))
      .join(",");
    return cachedFetch(`${url}?bbox=${bbox}&limit=${BBOX_LIMIT}`);
  }
  return cachedFetch(url);
}

export async function addRocrateOutput(sourceId, output) {
  const geo = await fetchLayerData(sourceId, output);
  if (!geo) return null;
  const feats = geo.features || [];
  // Contract-driven: variables + classification come from the RO-Crate via the
  // dataset contract. Legacy claim-based crates fall back to LEGACY_VARIABLES.
  const V = output.variables && Object.keys(output.variables).length
    ? output.variables
    : LEGACY_VARIABLES;
  const cls = output.classification || {};
  const role = output.role || "";
  const hasVar = (name) =>
    V[name] &&
    ((output.fields || []).includes(V[name]) ||
      feats.some((f) => f.properties && V[name] in f.properties));

  if (role.includes("risk-layer") || hasVar("risk_mobility_accessibility")) {
    addRiskSurface(geo, feats, V, cls);
  } else if (role.includes("drivers") || (hasVar("sensitivity") && hasVar("coping_capacity"))) {
    const sKey = V.sensitivity, cKey = V.coping_capacity;
    const sB = cls.breaks_sensitivity?.length
      ? cls.breaks_sensitivity
      : headTailBreaks(feats.map((f) => +f.properties?.[sKey] || 0), 2);
    const cB = cls.breaks_coping?.length
      ? cls.breaks_coping
      : headTailBreaks(feats.map((f) => +f.properties?.[cKey] || 0), 2);
    track(
      L.geoJSON(geo, {
        style: (f) => ({
          fillColor: svBivarColor(
            classIndex(+f.properties?.[sKey] || 0, sB),
            classIndex(+f.properties?.[cKey] || 0, cB)
          ),
          color: "#9e9e9e",
          weight: 0.4,
          opacity: 0.5,
          fillOpacity: 0.62,
        }),
        onEachFeature: (f, l) => l.bindPopup(genericPopup(f, output.label)),
      })
    );
  } else if (role.includes("social-vulnerability") || hasVar("social_vulnerability")) {
    const svKey = V.social_vulnerability;
    const svB = cls.breaks_sv?.length
      ? cls.breaks_sv
      : headTailBreaks(feats.map((f) => +f.properties?.[svKey] || 0));
    track(
      L.geoJSON(geo, {
        style: (f) => ({
          fillColor: svGreyColor(classIndex(+f.properties?.[svKey] || 0, svB)),
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

function addRiskSurface(geo, feats, V = LEGACY_VARIABLES, cls = {}) {
  // Class breaks come from the crate's classification (provisional or
  // validated); data-driven head/tail is only the fallback when a crate
  // carries none. Property names always resolve through the variable mapping.
  const maKey = V.risk_mobility_accessibility;
  const wbKey = V.risk_wellbeing;
  const p0 = feats[0]?.properties || {};
  const aggregated =
    (V.cell_id && V.cell_id in p0) || (V.aggregation_count && V.aggregation_count in p0);
  const maBreaks = cls.breaks_ma?.length
    ? cls.breaks_ma
    : headTailBreaks(feats.map((f) => +f.properties?.[maKey] || 0));
  const wbBreaks = cls.breaks_wb?.length
    ? cls.breaks_wb
    : headTailBreaks(feats.map((f) => +f.properties?.[wbKey] || 0));
  const colorFor = (p) =>
    PFR_GRID[classIndex(+p?.[wbKey] || 0, wbBreaks)][classIndex(+p?.[maKey] || 0, maBreaks)];

  const keep = (p) =>
    classIndex(+p?.[maKey] || 0, maBreaks) > 0 ||
    classIndex(+p?.[wbKey] || 0, wbBreaks) > 0;

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

  // Draw polygons directly (no Voronoi) when either:
  //  - the layer is a small set of real building footprints (paper replication), or
  //  - the layer is pre-aggregated cells (HEALPix / choropleth) computed once using package
  const FOOTPRINT_MAX = 3000;
  const isPolygon = /Polygon/.test(feats[0]?.geometry?.type || "");
  const footprintMode = isPolygon && (aggregated || feats.length <= FOOTPRINT_MAX);

  if (!footprintMode && pts.length && typeof d3 !== "undefined" && d3.Delaunay) {
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
        ).bindPopup(riskFieldPopup({ properties: props[i] }, V))
      );
    }
    track(L.layerGroup(cells));
    return;
  }

  // FDO check + validation
  // Footprint , aggregated-cell , fallback render, colored by PFR.
  //  - real building footprints: draw ALL buildings (small input data)
  //  - aggregated cells (HEALPix/choropleth): draw ONLY hotspot cells
  track(
    L.geoJSON(geo, {
      filter: (f) => (aggregated ? keep(f.properties) : footprintMode || keep(f.properties)),
      style: (f) => ({
        fillColor: colorFor(f.properties),
        color: aggregated ? "#666" : "#555",
        weight: aggregated ? 0.4 : footprintMode ? 0.7 : 0.3,
        opacity: aggregated ? 0.6 : footprintMode ? 0.9 : 0.5,
        fillOpacity: aggregated ? 0.75 : 0.85,
      }),
      pointToLayer: (f, ll) =>
        L.circleMarker(ll, { radius: 3, fillColor: colorFor(f.properties), color: "#333", weight: 0.3, fillOpacity: 0.9 }),
      onEachFeature: (f, l) => l.bindPopup(riskFieldPopup(f, V)),
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

function riskFieldPopup(f, V = LEGACY_VARIABLES) {
  const p = f.properties || {};
  const num = (v) => (Number.isFinite(+v) ? (+v).toFixed(6) : "–");
  const cellId = V.cell_id && p[V.cell_id];
  const nBuild = V.aggregation_count && p[V.aggregation_count];
  const rows = [
    [V.risk_mobility_accessibility, num(p[V.risk_mobility_accessibility])],
    [V.risk_wellbeing, num(p[V.risk_wellbeing])],
  ];
  if (nBuild !== undefined && nBuild !== null) rows.push([V.aggregation_count, esc(nBuild)]);
  return `<div style="font-size:12px;min-width:150px">
    <strong>${esc(p.id || (cellId ? `Cell ${cellId}` : "Building"))}</strong>
    <table style="border-collapse:collapse;width:100%;margin-top:4px">
      ${rows.map(([k, v]) => `<tr><td style="color:#64748b;padding:1px 4px">${esc(k)}</td>
          <td style="text-align:right;font-weight:600">${v}</td></tr>`).join("")}
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
