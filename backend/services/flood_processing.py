from __future__ import annotations

import math

RIMA_ALIASES = ["smoothed_RIMA", "RIMA", "PFRMA", "pfr_ma", "rima"]
RIWB_ALIASES = ["smoothed_RIWB", "RIWB", "PFRWB", "pfr_wb", "riwb"]
SVF_ALIASES = ["SVF", "SVPF", "SVI", "sv_factor"]
SENS_ALIASES = ["SV_Sensitivity", "Sensitivity", "sensitivity"]
COPING_ALIASES = ["SV_Coping_Capacity", "Coping_Capacity", "coping", "CC"]
ID_ALIASES = ["SU3_stadt_ID", "FID", "id", "OBJECTID"]

PFR_THRESHOLD = 0.05
SV_THRESHOLDS = [0.12, 0.16, 0.33]

DEFAULT_RISK_FIELD = "smoothed_RIMA"
AVAILABLE_RISK_FIELDS = ["smoothed_RIMA", "smoothed_RIWB"]

def resolve_column(columns, aliases):
    for alias in aliases:
        if alias in columns:
            return alias
    return None

def resolve_columns(columns) -> dict:
    return {
        "rima": resolve_column(columns, RIMA_ALIASES),
        "riwb": resolve_column(columns, RIWB_ALIASES),
        "svf": resolve_column(columns, SVF_ALIASES),
        "sensitivity": resolve_column(columns, SENS_ALIASES),
        "coping": resolve_column(columns, COPING_ALIASES),
        "id": resolve_column(columns, ID_ALIASES),
    }

def head_tail_breaks(arr, min_cls=3, max_cls=4, tail_ratio=0.4):
    #Todo Head/tail breaks classification 
    import numpy as np

    valid = arr[np.isfinite(arr) & (arr > 0)]
    if len(valid) < 10:
        bp = list(np.percentile(valid if len(valid) else [0], [25, 50, 75, 100]))
        return np.clip(np.digitize(arr, bp) - 1, 0, 3).astype(int), bp
    cur, bpts, n = valid.copy(), [float(valid.min())], 1
    while n < max_cls:
        mean = float(cur.mean())
        head = cur[cur > mean]
        if not len(head):
            break
        if (len(cur[cur <= mean]) / len(cur)) < tail_ratio and n >= min_cls:
            break
        bpts.append(mean)
        cur = head
        n += 1
    bpts.append(float(valid.max()))
    idx = np.clip(np.digitize(arr, bpts) - 1, 0, len(bpts) - 2)
    return np.clip((idx * 4 // max(len(bpts) - 1, 1)), 0, 3).astype(int), bpts

def build_risk_points(gdf, cols) -> tuple[dict, dict]:
    import numpy as np
    import pandas as pd
    from pyproj import Transformer

    rc, wc = cols.get("rima"), cols.get("riwb")
    if not rc or not wc:
        raise ValueError(
            f"Required RIMA/RIWB risk columns not found. Available columns: {list(gdf.columns)}"
        )
    sc, sc2, cc, ic = cols.get("svf"), cols.get("sensitivity"), cols.get("coping"), cols.get("id")

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:25832")
    elif gdf.crs.to_epsg() != 25832:
        gdf = gdf.to_crs("EPSG:25832")
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid & ~gdf.geometry.is_empty].copy()

    transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
    lons, lats = transformer.transform(
        gdf.geometry.centroid.x.values, gdf.geometry.centroid.y.values
    )

    rima = pd.to_numeric(gdf[rc], errors="coerce").fillna(0).values
    riwb = pd.to_numeric(gdf[wc], errors="coerce").fillna(0).values
    svf = pd.to_numeric(gdf[sc], errors="coerce").fillna(0).values if sc else np.zeros(len(gdf))
    sens = pd.to_numeric(gdf[sc2], errors="coerce").fillna(0).values if sc2 else np.zeros(len(gdf))
    cop = pd.to_numeric(gdf[cc], errors="coerce").fillna(0).values if cc else np.zeros(len(gdf))
    ids = gdf[ic].astype(str).values if ic else [str(i) for i in range(len(gdf))]

    ma_idx, ma_bk = head_tail_breaks(rima)
    wb_idx, wb_bk = head_tail_breaks(riwb)

    features = []
    for i in range(len(gdf)):
        if not (math.isfinite(lats[i]) and math.isfinite(lons[i])):
            continue
        mi, wi = int(ma_idx[i]), int(wb_idx[i])
        if mi == 0 and wi == 0:
            continue
        if rima[i] < PFR_THRESHOLD and riwb[i] < PFR_THRESHOLD:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(lons[i]), 7), round(float(lats[i]), 7)],
                },
                "properties": {
                    "id": ids[i],
                    "rima": round(float(rima[i]), 6),
                    "riwb": round(float(riwb[i]), 6),
                    "svf": round(float(svf[i]), 6),
                    "sens": round(float(sens[i]), 6),
                    "coping": round(float(cop[i]), 6),
                    "ma_idx": mi,
                    "wb_idx": wi,
                },
            }
        )

    def _summary(values, name):
        v = values[np.isfinite(values) & (values > 0)]
        if not len(v):
            return {}
        return {
            f"{name}_min": round(float(v.min()), 6),
            f"{name}_max": round(float(v.max()), 6),
            f"{name}_mean": round(float(v.mean()), 6),
            f"{name}_p33": round(float(np.percentile(v, 33)), 6),
            f"{name}_p67": round(float(np.percentile(v, 67)), 6),
        }

    stats = {
        "n_buildings": int(len(gdf)),
        "n_displayed": int(len(features)),
        "pfr_threshold": PFR_THRESHOLD,
        "rima_breaks": [round(v, 6) for v in ma_bk],
        "riwb_breaks": [round(v, 6) for v in wb_bk],
        **_summary(rima, "rima"),
        **_summary(riwb, "riwb"),
    }
    return {"type": "FeatureCollection", "features": features}, stats

def build_boundaries(gdf, cols) -> dict:
    import json

    import numpy as np
    import pandas as pd

    sc, s2, cc = cols.get("svf"), cols.get("sensitivity"), cols.get("coping")

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:25832")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf.geometry.simplify(0.0001)

    if sc:
        sv = pd.to_numeric(gdf[sc], errors="coerce").fillna(0)
        t1, t2, t3 = SV_THRESHOLDS
        gdf["sv_class"] = pd.cut(sv, bins=[-1e9, t1, t2, t3, 1e9], labels=[0, 1, 2, 3]).astype(int)
        gdf["svf_value"] = sv.round(5)
    else:
        gdf["sv_class"] = 0
        gdf["svf_value"] = 0.0

    if s2 and cc:
        def _norm(a):
            pos = a[a > 0]
            lo, hi = np.percentile(pos, [2, 98]) if len(pos) > 2 else (0, 1)
            return np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)

        s_vals = pd.to_numeric(gdf[s2], errors="coerce").fillna(0).values
        c_vals = pd.to_numeric(gdf[cc], errors="coerce").fillna(0).values
        bins4 = [0.0, 0.25, 0.5, 0.75, 1.0]
        gdf["sens_idx"] = np.clip(np.digitize(_norm(s_vals), bins4) - 1, 0, 3)
        gdf["coping_idx"] = np.clip(np.digitize(_norm(c_vals), bins4) - 1, 0, 3)
    else:
        gdf["sens_idx"] = 0
        gdf["coping_idx"] = 0

    keep = ["sv_class", "svf_value", "sens_idx", "coping_idx", "geometry"]
    present = [c for c in keep if c in gdf.columns]
    return json.loads(gdf[present].to_json())
