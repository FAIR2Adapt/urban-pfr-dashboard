from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .classification import build_layer_style

RISK_FIELDS = ("smoothed_RIMA", "smoothed_RIWB")
SOCIAL_FIELDS = ("SVF", "Sensitivity", "CC")

ROLE_BY_KEY = {
    "riskMap": "primary-risk-layer",
    "boundaryOutline": "context-boundary-layer",
    "socialVulnerability": "social-vulnerability-background",
    "vulnerabilityDrivers": "vulnerability-drivers-background",
    "focusAreas": "focus-area-outline",
}

@dataclass
class WorkflowSummary:
    software: Optional[str] = None
    softwareVersion: Optional[str] = None
    runtime: Optional[str] = None
    runtimeVersion: Optional[str] = None
    operations: list[str] = field(default_factory=list)
    implementation: Optional[str] = None

@dataclass
class DashboardLayer:
    type: str = "geojson"
    role: str = ""
    label: Optional[str] = None
    sourceUrl: Optional[str] = None
    localPath: Optional[str] = None
    fields: list[str] = field(default_factory=list)
    rowCount: Optional[int] = None
    columnCount: Optional[int] = None
    style: dict = field(default_factory=dict)

@dataclass
class DashboardResource:
    id: str
    role: str = "preview"
    sourceUrl: Optional[str] = None
    localPath: Optional[str] = None
    relatedClaim: Optional[str] = None

@dataclass
class DashboardClaim:
    id: str
    label: Optional[str] = None
    inputs: list[dict] = field(default_factory=list)
    workflow: dict = field(default_factory=dict)
    outputs: list[dict] = field(default_factory=list)

class JsonLdHelper:
    @staticmethod
    def find_key(obj: dict, suffix: str) -> Any:
        if not isinstance(obj, dict):
            return None
        for key, value in obj.items():
            if isinstance(key, str) and key.endswith(suffix):
                return value
        return None

    @staticmethod
    def as_list(value: Any) -> list:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @staticmethod
    def text(value: Any) -> Optional[str]:
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, list):
            for item in value:
                got = JsonLdHelper.text(item)
                if got:
                    return got
            return None
        if isinstance(value, dict):
            for key in ("@value", "rdfs:label", "name", "label", "@id"):
                if value.get(key):
                    return JsonLdHelper.text(value[key])
            return None
        return str(value)

    @staticmethod
    def get_label(obj: dict) -> Optional[str]:
        return JsonLdHelper.text(JsonLdHelper.find_key(obj, "#label"))

    @staticmethod
    def get_source_url(obj: dict) -> Optional[str]:
        return JsonLdHelper.text(JsonLdHelper.find_key(obj, "#source_url"))

    @staticmethod
    def get_has_part(obj: dict) -> list:
        return JsonLdHelper.as_list(JsonLdHelper.find_key(obj, "#has_part"))

    @staticmethod
    def get_characteristics(obj: dict) -> dict:
        char = JsonLdHelper.find_key(obj, "#has_characteristic")
        node = char if isinstance(char, dict) else obj
        return {
            "rowCount": JsonLdHelper.find_key(node, "#number_of_rows"),
            "columnCount": JsonLdHelper.find_key(node, "#number_of_columns"),
        }

class ROCrateOutputMapper:
    METADATA_FILE = "ro-crate-metadata.json"

    def __init__(self, package_root: "Path | str", base_url: str | None = None):
        self.package_root = Path(package_root)

        self.base_url = base_url
        self._diagnostics: dict = {"warnings": [], "missingFiles": [], "unmappedOutputs": []}
        self._graph: list = []
        self._index: dict = {}
        self._geojson_cache: dict = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        path = self.package_root / self.METADATA_FILE
        if not path.exists():
            raise FileNotFoundError(f"RO-Crate metadata not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._graph = data.get("@graph", []) or []
        self._index = {
            e["@id"]: e for e in self._graph if isinstance(e, dict) and "@id" in e
        }

    @staticmethod
    def _types(entity: dict) -> list:
        type_value = entity.get("@type", [])
        return [type_value] if isinstance(type_value, str) else list(type_value)

    def _by_type(self, type_name: str) -> list:
        return [e for e in self._graph if type_name in self._types(e)]

    def _deref(self, ref: Any) -> Any:
        """Resolve a ``{"@id": ...}`` reference to the entity it points at."""
        if isinstance(ref, dict) and "@id" in ref:
            return self._index.get(ref["@id"], ref)
        if isinstance(ref, list):
            return [self._deref(r) for r in ref]
        return ref

    def _warn(self, message: str) -> None:
        if message not in self._diagnostics["warnings"]:
            self._diagnostics["warnings"].append(message)

    def _resolve_local(self, ref: Optional[str], track_missing: bool = False) -> Optional[str]:
        if not ref:
            return None
        name = os.path.basename(str(ref).rstrip("/"))
        if not name:
            return None
        if (self.package_root / name).exists():
            return name
        if track_missing and name not in self._diagnostics["missingFiles"]:
            self._diagnostics["missingFiles"].append(name)
        return None

    def to_dashboard_dataset(self, dataset_id: str = "hamburg-rocrate-derived") -> dict:
        """Parse the package and return one normalized dashboard dataset dict."""
        root = self._index.get("./", {})
        metadata = self._build_metadata(root)
        claims = self._build_claims()

        all_outputs = [
            {**out, "claim": claim["id"]}
            for claim in claims
            for out in claim["outputs"]
        ]
        layers = self._map_layers(all_outputs)
        figures = self._build_figures(claims)
        dashboard_views = self._build_dashboard_views(layers)
        ui = self._build_ui(layers, dashboard_views)

        dataset = {
            "id": dataset_id,
            "label": metadata.get("title") or dataset_id,
            "sourceType": "rocrate-output",
            "metadata": metadata,
            "claims": claims,
            "layers": layers,
            "dashboardViews": dashboard_views,
            "figures": figures,
            "ui": ui,
            "diagnostics": self._diagnostics,
        }

        for issue in self.validate_dashboard_dataset(dataset):
            self._warn(issue)
        return dataset

    def validate_dashboard_dataset(self, dataset: dict) -> list[str]:
        """Return a list of human-readable validation issues (empty == OK)."""
        issues: list[str] = []
        metadata = dataset.get("metadata") or {}
        if not metadata.get("title"):
            issues.append("metadata.title is missing")
        if not dataset.get("claims"):
            issues.append("no claims found in package")

        layers = dataset.get("layers") or {}
        risk = layers.get("riskMap") or {}
        if not risk:
            issues.append("riskMap layer is missing")
        else:
            if not risk.get("sourceUrl") and not risk.get("localPath"):
                issues.append("riskMap has neither a GeoJSON sourceUrl nor a localPath")
            risk_fields = {f for f in risk.get("fields", []) if f}
            if risk_fields:
                missing = [f for f in RISK_FIELDS if f not in risk_fields]
                if missing:
                    issues.append(
                        f"riskMap is missing expected risk fields: {', '.join(missing)}"
                    )
            if risk.get("localPath") and not (risk.get("style") or {}).get("breaks"):
                issues.append("riskMap.style.breaks missing despite a local GeoJSON")

        views = dataset.get("dashboardViews") or {}
        if not views:
            issues.append("dashboardViews is missing")
        for vid, view in views.items():
            bg = view.get("backgroundLayer")
            if bg and not layers.get(bg) and view.get("available", True):
                issues.append(f"dashboard view '{vid}' references missing layer '{bg}' but is marked available")
        if "focusAreas" not in layers:
            for vid, view in views.items():
                if "focusAreas" in (view.get("legendGroups") or []) or "focusAreas" in (view.get("optionalLayers") or []):
                    issues.append(f"dashboard view '{vid}' references focusAreas but no focusAreas layer exists")
        sv, vd = layers.get("socialVulnerability"), layers.get("vulnerabilityDrivers")
        if sv and vd and sv.get("role") == vd.get("role"):
            issues.append("socialVulnerability and vulnerabilityDrivers must be separate layers")

        for out in (dataset.get("diagnostics") or {}).get("unmappedOutputs", []):
            issues.append(
                f"unmapped output '{out.get('label') or out.get('sourceUrl') or '?'}' "
                f"(claim {out.get('claim')})"
            )
        return issues

    def _build_metadata(self, root: dict) -> dict:
        lic = self._deref(root.get("license"))
        if isinstance(lic, dict):
            license_id = lic.get("@id") or lic.get("identifier")
        else:
            license_id = lic

        pub = self._deref(root.get("publisher"))
        publisher: dict = {}
        if isinstance(pub, dict) and pub.get("@id"):
            publisher = {"id": pub.get("@id"), "name": pub.get("name"), "url": pub.get("url")}

        return {
            "title": root.get("name"),
            "description": root.get("description"),
            "datePublished": root.get("datePublished"),
            "status": root.get("status"),
            "license": license_id,
            "authors": [self._map_person(p) for p in self._by_type("Person")],
            "publisher": publisher,
            "concepts": [
                {
                    "id": c.get("@id"),
                    "label": c.get("rdfs:label"),
                    "definition": c.get("skos:definition"),
                    "seeAlso": c.get("rdfs:seeAlso"),
                }
                for c in self._by_type("skos:Concept")
            ],
            "statements": [
                {
                    "id": s.get("@id"),
                    "label": s.get("rdfs:label"),
                    "notation": s.get("notation"),
                    "concepts": [
                        r.get("@id")
                        for r in JsonLdHelper.as_list(s.get("concepts"))
                        if isinstance(r, dict)
                    ],
                }
                for s in self._by_type("Statement")
            ],
            "files": self._build_files(root),
        }

    def _map_person(self, person: dict) -> dict:
        pid = person.get("@id", "")
        aff = self._deref(person.get("affiliation"))
        affiliation = None
        if isinstance(aff, dict) and (aff.get("name") or aff.get("@id")):
            affiliation = {"id": aff.get("@id"), "name": aff.get("name"), "url": aff.get("url")}
        name = person.get("name") or " ".join(
            filter(None, [person.get("givenName"), person.get("familyName")])
        )
        return {
            "id": pid,
            "name": name or None,
            "givenName": person.get("givenName"),
            "familyName": person.get("familyName"),
            "orcid": pid if "orcid.org" in pid else None,
            "affiliation": affiliation,
        }

    def _build_files(self, root: dict) -> list:
        files = []
        for ref in JsonLdHelper.as_list(root.get("hasPart")):
            fid = ref.get("@id") if isinstance(ref, dict) else None
            if not fid:
                continue
            entity = self._index.get(fid, {})
            files.append({
                "id": fid,
                "name": entity.get("name", fid),
                "encodingFormat": entity.get("encodingFormat"),
                "type": self._types(entity),
                "localPath": self._resolve_local(fid, track_missing=True),
            })
        return files

    def _claim_files(self) -> list:
        return [
            f["@id"]
            for f in self._by_type("File")
            if f.get("encodingFormat") == "application/ld+json" and "@id" in f
        ]

    def _build_claims(self) -> list:
        claims = []
        for claim_id in self._claim_files():
            path = self.package_root / claim_id
            if not path.exists():
                self._resolve_local(claim_id, track_missing=True)
                self._warn(f"Claim file '{claim_id}' is declared in the crate but missing locally")
                claims.append(asdict(DashboardClaim(id=claim_id, workflow=asdict(WorkflowSummary()))))
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                self._warn(f"Could not read claim file '{claim_id}': {exc}")
                claims.append(asdict(DashboardClaim(id=claim_id, workflow=asdict(WorkflowSummary()))))
                continue
            claims.append(self._map_claim(claim_id, data))
        return claims

    def _map_claim(self, claim_id: str, data: dict) -> dict:
        helper = JsonLdHelper

        workflow_node = helper.find_key(data, "#has_part") or {}
        inputs = [
            self._map_io(node, is_output=False)
            for node in helper.as_list(helper.find_key(workflow_node, "#has_input"))
        ]
        outputs = [
            self._map_io(node, is_output=True)
            for node in helper.as_list(helper.find_key(workflow_node, "#has_output"))
        ]
        workflow = self._map_workflow(
            helper.as_list(helper.find_key(workflow_node, "#executes")),
            helper.find_key(data, "#is_implemented_by"),
        )
        return {
            "id": claim_id,
            "label": helper.get_label(data),
            "inputs": inputs,
            "workflow": workflow,
            "outputs": outputs,
        }

    def _map_io(self, node: dict, is_output: bool) -> dict:
        helper = JsonLdHelper
        fields = [helper.get_label(part) for part in helper.get_has_part(node) if helper.get_label(part)]
        chars = helper.get_characteristics(node)
        item = {
            "label": helper.get_label(node),
            "sourceUrl": helper.get_source_url(node),
            "fields": fields,
            "rowCount": chars.get("rowCount"),
            "columnCount": chars.get("columnCount"),
        }
        if is_output:

            expression = helper.find_key(node, "#has_expression")
            item["previewUrl"] = helper.get_source_url(expression) if isinstance(expression, dict) else None
        return item

    def _map_workflow(self, operation_nodes: list, implementation: Any) -> dict:
        helper = JsonLdHelper
        summary = WorkflowSummary(
            operations=[helper.get_label(op) for op in operation_nodes if helper.get_label(op)],
            implementation=implementation if isinstance(implementation, str) else None,
        )

        if operation_nodes:
            software = helper.find_key(operation_nodes[0], "#part_of")
            if isinstance(software, dict):
                summary.software = helper.get_label(software)
                summary.softwareVersion = helper.find_key(software, "#version_info")
                runtime = helper.find_key(software, "#part_of")
                if isinstance(runtime, dict):
                    summary.runtime = helper.get_label(runtime)
                    summary.runtimeVersion = helper.find_key(runtime, "#version_info")
        return asdict(summary)

    def _map_layers(self, outputs: list) -> dict:
        """Classify outputs into explicit layer roles (one slot per role)."""
        chosen: dict = {}
        for out in outputs:
            key = self._classify_layer(out.get("label"), out.get("fields") or [])
            if key is None:
                self._add_unmapped(out, "no matching layer role")
            elif key not in chosen:
                chosen[key] = out

        layers = {key: self._build_layer(out, ROLE_BY_KEY[key]) for key, out in chosen.items()}

        focus = self._detect_focus_areas()
        if focus:
            layers["focusAreas"] = focus

        if "riskMap" not in layers:
            self._warn("No risk-map output detected; layers.riskMap is missing")
        if "boundaryOutline" not in layers:
            self._warn("No boundary/context output detected; layers.boundaryOutline is missing")
        return layers

    @staticmethod
    def _classify_layer(label: Optional[str], fields: list) -> Optional[str]:
        """Assign one output to a single layer role (or None). Order matters."""
        text = (label or "").lower()
        fset = {f for f in fields if f}
        if "risk map" in text or "pfr" in text or "pluvial flood risk" in text:
            return "riskMap"
        if "smoothed_RIMA" in fset and "smoothed_RIWB" in fset:
            return "riskMap"
        if "SVF" in fset or "grey sv" in text:
            return "socialVulnerability"
        if "social vulnerability" in text and "sensitivity" not in text and "coping" not in text:
            return "socialVulnerability"
        if "Sensitivity" in fset or "CC" in fset:
            return "vulnerabilityDrivers"
        if any(w in text for w in ("coping capacity", "sensitivity", "bivariate")):
            return "vulnerabilityDrivers"
        non_geometry = [f for f in fset if f.lower() != "geometry"]
        if (
            not (fset & set(SOCIAL_FIELDS))
            and not non_geometry
            and any(w in text for w in ("boundary", "boundaries", "statistical unit", "outline"))
        ):
            return "boundaryOutline"
        return None

    def _load_geojson(self, filename: Optional[str]) -> Optional[dict]:
        """Read a package GeoJSON file as plain JSON (cached); never raises."""
        if not filename:
            return None
        if filename in self._geojson_cache:
            return self._geojson_cache[filename]
        data = None
        path = self.package_root / filename
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                self._warn(f"Could not read GeoJSON '{filename}' for classification: {exc}")
        self._geojson_cache[filename] = data
        return data

    def _detect_focus_areas(self) -> Optional[dict]:
        """Map a real focus-area GeoJSON if the crate ships one; else None (never fabricated)."""
        for entity in self._by_type("File"):
            name = str(entity.get("name") or entity.get("@id") or "").lower()
            fmt = str(entity.get("encodingFormat") or "").lower()
            if "focus" in name and ("geo+json" in fmt or name.endswith(".geojson")):
                fid = entity.get("@id")
                layer = asdict(DashboardLayer(
                    role="focus-area-outline",
                    label="Focus areas",
                    sourceUrl=entity.get("url"),
                    localPath=self._resolve_local(fid, track_missing=True),
                    fields=["name", "geometry"],
                ))
                layer["style"] = build_layer_style(layer, None)
                return layer
        return None

    def _build_layer(self, out: dict, role: str) -> dict:
        source_url = out.get("sourceUrl")
        local = self._resolve_local(source_url, track_missing=True)
        layer = asdict(DashboardLayer(
            role=role,
            label=out.get("label"),
            sourceUrl=source_url,
            localPath=local,
            fields=out.get("fields") or [],
            rowCount=out.get("rowCount"),
            columnCount=out.get("columnCount"),
        ))
        geojson = self._load_geojson(local) if local else None
        layer["style"] = build_layer_style(layer, geojson)
        return layer

    def _add_unmapped(self, out: dict, reason: str) -> None:
        self._diagnostics["unmappedOutputs"].append({
            "claim": out.get("claim"),
            "label": out.get("label"),
            "sourceUrl": out.get("sourceUrl"),
            "reason": reason,
        })

    def _build_figures(self, claims: list) -> list:
        figures: list = []
        seen: set = set()

        for claim in claims:
            for out in claim.get("outputs", []):
                preview = out.get("previewUrl")
                if not preview:
                    continue
                fid = os.path.basename(str(preview).rstrip("/"))
                if fid in seen:
                    continue
                seen.add(fid)
                figures.append(asdict(DashboardResource(
                    id=fid,
                    sourceUrl=preview,
                    localPath=self._resolve_local(preview, track_missing=True),
                    relatedClaim=claim.get("id"),
                )))

        for png in self._by_type("File"):
            if str(png.get("encodingFormat", "")).lower() != "image/png":
                continue
            fid = png.get("@id")
            if not fid or fid in seen:
                continue
            seen.add(fid)
            figures.append(asdict(DashboardResource(
                id=fid,
                sourceUrl=png.get("url"),
                localPath=self._resolve_local(fid, track_missing=True),
                relatedClaim=None,
            )))
        return figures

    def _build_dashboard_views(self, layers: dict) -> dict:
        """Paper Figures 4-6 as dashboard views; a view is unavailable if its layer is missing."""
        def has(key: str) -> bool:
            return bool(layers.get(key))

        focus_opt = ["focusAreas"] if has("focusAreas") else []

        def legend(groups: list) -> list:
            return [g for g in groups if not (g == "focusAreas" and not has("focusAreas"))]

        views = {
            "risk-hotspots": {
                "label": "Risk hotspots", "figure": "Figure 4",
                "description": "Shows PFRMA and PFRWB hotspots.",
                "riskLayer": "riskMap", "backgroundLayer": None,
                "optionalLayers": focus_opt + (["boundaryOutline"] if has("boundaryOutline") else []),
                "legendGroups": legend(["pfr", "focusAreas"]),
                "available": has("riskMap"),
            },
            "risk-social-vulnerability": {
                "label": "Risk + social vulnerability", "figure": "Figure 5",
                "description": "Adds overall social vulnerability below the PFR risk layer.",
                "riskLayer": "riskMap", "backgroundLayer": "socialVulnerability",
                "optionalLayers": list(focus_opt),
                "legendGroups": legend(["pfr", "socialVulnerability", "focusAreas"]),
                "available": has("riskMap") and has("socialVulnerability"),
            },
            "risk-drivers": {
                "label": "Risk drivers", "figure": "Figure 6",
                "description": "Shows whether vulnerability is driven by low coping capacity or high sensitivity.",
                "riskLayer": "riskMap", "backgroundLayer": "vulnerabilityDrivers",
                "optionalLayers": list(focus_opt),
                "legendGroups": legend(["pfr", "vulnerabilityDrivers", "focusAreas"]),
                "available": has("riskMap") and has("vulnerabilityDrivers"),
            },
        }
        reasons = {
            "risk-hotspots": "No risk-map layer detected.",
            "risk-social-vulnerability": "No overall social vulnerability layer detected.",
            "risk-drivers": "No vulnerability-drivers layer detected.",
        }
        for vid, view in views.items():
            if not view["available"]:
                view["disabledReason"] = reasons[vid]
        return views

    def _build_ui(self, layers: dict, dashboard_views: dict) -> dict:
        risk = layers.get("riskMap") or {}
        risk_fields = {f for f in risk.get("fields", []) if f}
        default_risk_fields = [f for f in RISK_FIELDS if f in risk_fields] or list(RISK_FIELDS)

        background_fields: list = []
        for key in ("socialVulnerability", "vulnerabilityDrivers"):
            for f in (layers.get(key) or {}).get("fields", []):
                if f and f.lower() != "geometry" and f not in background_fields:
                    background_fields.append(f)

        available = [vid for vid, v in dashboard_views.items() if v.get("available")]
        default_view = "risk-hotspots" if "risk-hotspots" in available else (
            available[0] if available else "risk-hotspots"
        )
        return {
            "defaultDashboardView": default_view,
            "defaultRiskFields": default_risk_fields,
            "availableBackgroundFields": background_fields,
            "availableDashboardViews": available,
        }
