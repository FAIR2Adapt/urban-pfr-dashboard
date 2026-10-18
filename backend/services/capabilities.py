"""The capabilities document: what this dashboard reads and binds, generated from config/formats.yaml,
config/renderers.yaml, the dashboard contracts, the known Plugin FDOs and config/variation_matrix.yaml."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from ..composer.registry import load_registry
from ..adapters.fdo_resource_adapter import FDO_FOLDERS
from .formats import registry as formats_registry

SCHEMA = "urban-pfr-dashboard-capabilities/1"
CONTRACTS = ("cs3-metadata-v1", "cs3-claims-v1", "cs3-map-v1", "cs3-evidence-v1",
             "dashboard-composition-v1", "plugin-description-v1", "composer-object-v1")
STILL_CODE = [
    "readers: PMTiles, FlatGeobuf by bounding box, GeoJSON",
    "renderers and their channels: bivariate map, single-variable map, bivariate background, claims list, metadata card",
    "palette colours and the four classes per axis of the bivariate grid",
    "basemaps, start view, interface language",
]


def _commit(root: Path) -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:12]
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _contracts(root: Path) -> list:
    try:
        from fdo_consume.contracts import load_contract
    except ImportError:
        return [{"id": c, "available": False} for c in CONTRACTS]
    out = []
    for name in CONTRACTS:
        spec = load_contract(name, folder=str(root / FDO_FOLDERS["contracts"]), profile_maps=str(root / FDO_FOLDERS["profile_maps"]))
        out.append({"id": name, "consumer": spec.get("consumer"), "must": spec.get("must", []), "should": spec.get("should", []),
                    "accepts": spec.get("accepts", []), "overlay": spec.get("profile_additions")})
    return out


def _plugins(config, root: Path, renderer_registry: dict) -> list:
    """The Plugin FDOs the renderer registry names, with the inputs they declare, read from the first composed source's objects."""
    rows = [{"pid": pid, "renderer": e["renderer_id"], "supportedVersion": str(e["supported_plugin_version"]), "inputs": None}
            for pid, e in renderer_registry.items()]
    source = next((s for s in config.sources if s.get("adapter") == "fdo-dashboard" and s.get("enabled")), None)
    try:
        from fdo_consume import consume
    except ImportError:
        return rows
    if source is None:
        return rows
    locator = source.get("locator") or {}
    for row in rows:
        result = consume(row["pid"], "plugin-description-v1", recorded_dir=str((root / locator.get("fixtures", "")).resolve()),
                         profile_overlay=locator.get("profile_overlay"), contracts=str(root / FDO_FOLDERS["contracts"]),
                         profile_maps=str(root / FDO_FOLDERS["profile_maps"]))
        if not result.is_usable:
            row["inputs"] = {"unreadable": result.diagnostics[0]["message"] if result.diagnostics else "not usable"}
            continue
        binding = result.binding
        plugin = next((e for e in binding["entities"] if e["type"] == "Plugin"), {"fields": {}})
        row["declaredVersion"] = plugin["fields"].get("version")
        row["inputs"] = [{"name": i["fields"].get("name"), "kind": i["fields"].get("kind"),
                          "required": str(i["fields"].get("required", "True")).lower() != "false",
                          "formats": i["fields"].get("formats") or [],
                          "variables": [v["fields"].get("property_id") for v in binding["entities"]
                                        if v["type"] == "Variable" and i["id"] in v["holders"]]}
                         for i in binding["entities"] if i["type"] == "Input"]
    return rows


def capabilities(config, root: Path) -> dict:
    reg = formats_registry()
    renderer_registry = load_registry(root / "config" / "renderers.yaml")
    matrix = yaml.safe_load((root / "config" / "variation_matrix.yaml").read_text(encoding="utf-8"))
    return {
        "schema": SCHEMA, "status": "prototype", "commit": _commit(root),
        "generatedFrom": ["config/formats.yaml", "config/renderers.yaml", "config/fdo/contracts", "Plugin FDOs", "config/variation_matrix.yaml"],
        "formats": [{"mediaType": t, "label": e["label"], "aliases": e.get("aliases") or [], "kind": e["kind"], "reader": e["reader"],
                     "engines": e["engines"], "maxFeaturesPerRead": e.get("max_features_per_read"), "maxBytes": e.get("max_bytes"),
                     "note": e.get("note"), "status": "readable"} for t, e in reg["formats"].items()],
        "otherFormats": {"status": "not readable", "reason": reg["unlisted"].format(format="any other media type")},
        "engines": {k: {"label": v["label"], "prefer": v["prefer"]} for k, v in reg["engines"].items()},
        "renderers": [{"pluginPid": pid, "supportedPluginVersion": str(e["supported_plugin_version"]), "renderer": e["renderer_id"],
                       "channels": e.get("channels") or {}, "palettes": e.get("palettes") or []} for pid, e in renderer_registry.items()],
        "contracts": _contracts(root),
        "plugins": _plugins(config, root, renderer_registry),
        "builtFromTheFdo": matrix["rows"],
        "stillCode": STILL_CODE,
    }
