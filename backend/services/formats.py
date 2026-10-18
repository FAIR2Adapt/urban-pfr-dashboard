"""Data formats the dashboard reads (config/formats.yaml): the declared media type normalised, a verdict per map engine
for every declared distribution, and the file each engine draws."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "formats.yaml"


@lru_cache(maxsize=4)
def registry(path: str = str(REGISTRY_PATH)) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    aliases = {}
    for canonical_type, entry in data["formats"].items():
        aliases[canonical_type] = canonical_type
        for alias in entry.get("aliases") or []:
            aliases[alias.lower()] = canonical_type
    return {**data, "_aliases": aliases}


def canonical(media_type) -> str | None:
    """The canonical media type of a declared value; None when the value is not a media type (e.g. a format registry IRI)."""
    if not isinstance(media_type, str):
        return None
    base = media_type.split(";", 1)[0].strip().lower()
    if base.count("/") != 1 or base.startswith(("http:", "https:")) or " " in base:
        return None
    return registry()["_aliases"].get(base, base)


def entry(media_type) -> dict | None:
    return registry()["formats"].get(canonical(media_type) or "")


def label(media_type) -> str:
    known = entry(media_type)
    return known["label"] if known else (canonical(media_type) or str(media_type))


def engines() -> dict:
    return registry()["engines"]


def assess(distributions: list, accepts=None, accepts_label: str = "the consumer") -> dict:
    """Give each distribution `format` (canonical), a verdict per engine with a reason, and return the file each engine draws.
    `accepts(distribution)` says whether the consumer (plugin or contract) accepts the format; None accepts all."""
    reg = registry()
    for d in distributions:
        declared = d.get("format")
        d["formatDeclared"] = d.get("formatDeclared", declared)
        fmt = canonical(declared)
        d["format"] = fmt or declared
        d["formatLabel"] = label(declared)
        known = reg["formats"].get(fmt or "")
        common = None
        if fmt is None:
            common = f"the declared format {declared!r} is not a media type"
        elif known is None:
            common = reg["unlisted"].format(format=fmt)
        elif accepts is not None and not accepts(d):
            common = f"{accepts_label} does not accept {known['label']}"
        elif d.get("accessTier") == "private":
            common = "restricted; not served"
        elif not d.get("path"):
            common = "the file is not in the folder this server serves"
        elif known.get("max_bytes") and (d.get("contentSize") or 0) > known["max_bytes"]:
            common = (f"{(d['contentSize'] or 0) / 1e6:.0f} MB is more than the {known['max_bytes'] / 1e6:.0f} MB "
                      f"this dashboard reads whole as {known['label']}")
        d["read"] = {}
        for name, spec in reg["engines"].items():
            if common:
                d["read"][name] = {"ok": False, "reason": common}
            elif name not in known.get("engines", []):
                d["read"][name] = {"ok": False, "reason": f"{known['label']} is not read by {spec['label']}"}
            else:
                d["read"][name] = {"ok": True, "reason": None}
    chosen = {}
    for name, spec in reg["engines"].items():
        candidates = [d for d in distributions if d["read"][name]["ok"]]
        candidates.sort(key=lambda d: spec["prefer"].index(d["format"]) if d["format"] in spec["prefer"] else len(spec["prefer"]))
        pick = candidates[0] if candidates else None
        for d in candidates[1:]:
            d["read"][name] = {"ok": False, "reason": f"not used: {pick['formatLabel']} is preferred by {spec['label']}"}
        if pick is not None:
            known = reg["formats"][pick["format"]]
            pick["read"][name]["reason"] = "drawn"
            chosen[name] = {"path": pick["path"], "format": pick["format"], "reader": known["reader"],
                            "maxFeatures": known.get("max_features_per_read"), "note": known.get("note")}
        else:
            chosen[name] = None
    return chosen


def unread_reason(distributions: list, engine: str) -> str | None:
    """Why an engine draws nothing: the reasons of the declared distributions, one per file."""
    reasons = [f"{(d.get('declared_path') or '').rsplit('/', 1)[-1] or d.get('formatLabel')}: {d['read'][engine]['reason']}"
               for d in distributions if not d["read"][engine]["ok"]]
    return "; ".join(reasons) or "the product declares no distribution"


def strategy(chosen: dict) -> str:
    """The Leaflet path's reading strategy for the file it draws."""
    leaflet = chosen.get("leaflet")
    return "fgb-bbox" if leaflet and leaflet["reader"] == "fgb-bbox" else "static"


LONLAT = {"epsg:4326", "ogc:crs84", "crs84", "urn:ogc:def:crs:ogc:1.3:crs84", "urn:ogc:def:crs:epsg::4326",
          "http://www.opengis.net/def/crs/epsg/0/4326", "http://www.opengis.net/def/crs/ogc/1.3/crs84"}


def crs_problem(crs: str | None) -> str | None:
    """Why a declared coordinate system cannot be drawn: the browser readers take longitude/latitude (EPSG:4326) only."""
    if not crs or crs.strip().lower() in LONLAT:
        return None
    return f"the product is declared in {crs}; this dashboard draws longitude/latitude (EPSG:4326) only and does not reproject"


def refuse_all(reading: dict, reason: str) -> None:
    """No engine draws the layer, for one reason that holds for every file."""
    reading["engines"] = {name: None for name in reading["engines"]}
    reading["unread"] = {name: reason for name in reading["engines"]}
    reading["localPath"], reading["renderingStrategy"] = None, "static"


def layer_reading(distributions: list, accepts=None, accepts_label: str = "the consumer") -> dict:
    """The layer fields that say how each engine reads the product: the chosen file per engine, why an engine draws
    nothing, the strategy and served path the Leaflet path reads, notes on the chosen files."""
    chosen = assess(distributions, accepts, accepts_label)
    first = chosen.get("leaflet") or chosen.get("webgl")
    notes = sorted({c["note"] for c in chosen.values() if c and c.get("note")})
    return {"engines": chosen, "unread": {name: (None if c else unread_reason(distributions, name)) for name, c in chosen.items()},
            "renderingStrategy": strategy(chosen), "localPath": first["path"] if first else None, "notes": notes}
