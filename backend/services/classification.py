#TO DO validation
from __future__ import annotations

def head_tail_breaks(values: list, max_classes: int = 4) -> list:
    # threshold check required
    cur = sorted(v for v in values if isinstance(v, (int, float)) and v == v and v > 0)
    breaks: list = []
    while cur and len(breaks) < max(1, max_classes) - 1:
        mean = sum(cur) / len(cur)
        breaks.append(mean)
        head = [v for v in cur if v > mean]
        if not head or len(head) == len(cur):
            break
        cur = head
    return breaks

def numeric_values_from_geojson(geojson: dict, field: str) -> list:
    out: list = []
    for feat in (geojson or {}).get("features", []) or []:
        raw = (feat.get("properties") or {}).get(field)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val == val:
            out.append(val)
    return out

def build_layer_style(layer: dict, geojson: dict | None = None) -> dict:
    role = (layer or {}).get("role", "")

    if role == "primary-risk-layer":
        style = {
            "type": "bivariate-risk",
            "classification": "head-tail-breaks",
            "fields": {"ma": "smoothed_RIMA", "wb": "smoothed_RIWB"},
            "legend": {
                "title": "Pluvial flood risk (PFR)",
                "xLabel": "Mobility & Accessibility",
                "yLabel": "Well-being",
            },
        }
        if geojson:
            style["breaks"] = {
                "smoothed_RIMA": head_tail_breaks(numeric_values_from_geojson(geojson, "smoothed_RIMA"), 4),
                "smoothed_RIWB": head_tail_breaks(numeric_values_from_geojson(geojson, "smoothed_RIWB"), 4),
            }
        return style

    if role == "social-vulnerability-background":
        style = {
            "type": "choropleth",
            "classification": "quantile-or-precomputed",
            "field": "SVF",
            "legend": {"title": "Social vulnerability (SV)", "classes": ["low", "medium", "high", "very high"]},
        }
        if geojson:
            style["breaks"] = {"SVF": head_tail_breaks(numeric_values_from_geojson(geojson, "SVF"), 4)}
        return style

    if role == "vulnerability-drivers-background":
        style = {
            "type": "bivariate-vulnerability",
            "classification": "head-tail-breaks",
            "fields": {"sensitivity": "Sensitivity", "copingCapacity": "CC"},
            "legend": {
                "title": "Social vulnerability drivers",
                "xLabel": "Low coping capacity",
                "yLabel": "High sensitivity",
            },
        }
        if geojson:
            style["breaks"] = {
                "Sensitivity": head_tail_breaks(numeric_values_from_geojson(geojson, "Sensitivity"), 3),
                "CC": head_tail_breaks(numeric_values_from_geojson(geojson, "CC"), 3),
            }
        return style

    if role == "context-boundary-layer":
        return {"type": "outline", "legend": {"title": "Administrative boundaries"}}
    if role == "focus-area-outline":
        return {"type": "outline", "legend": {"title": "Focus areas"}}
    return {}
