"""CS3 compatibility projection: a DashboardPlan as the dataset the current page reads (one layer per map panel,
keyed by panel). A temporary bridge between the composer and the existing frontend dataset model.

Consumer capabilities stated here: a map renderer takes exactly one Dataset input; a layer is drawn only with the
class breaks the data declares (none are computed); a colorScheme must be one the renderer lists."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from ..composer.models import INFO, OPEN, RESTRICTED, USABLE, WARNING, DashboardPlan, Diagnostic, PanelPlan
from ..composer.session import CompositionSession
from ..services.binding_shapes import (box_range_note, classification_of, claims_of, distributions_of, evidence_of, variable_info,
                                       metadata_of, structure_of)
from ..services.formats import canonical, crs_problem, layer_reading, refuse_all

MAP_RENDERERS = ("bivariate-map", "single-variable-map", "bivariate-background")
FDO_CONSUME_PACKAGE_NAME = "fdo-consume"


def panel_key(panel_id: str) -> str:
    return panel_id.lstrip("#").replace("/", "_")


def project_dashboard_plan_to_cs3_dataset(plan: DashboardPlan, session: CompositionSession, dashboard_config: dict, source_id: str,
                                          evidence: dict | None = None, resource_roots: dict | None = None) -> dict:
    """Layers from the drawable map panels in plan order; claims and metadata from their own panels; every status kept.
    `resource_roots`: {object pid: (served folder name, local folder)}; each layer's files are served from its own object."""
    evidence, resource_roots = evidence or {}, resource_roots or {}
    layers, restricted, composition = {}, [], []
    claims, metadata, metadata_binding = [], {}, None
    warnings = [d.message for d in plan.diagnostics if d.level != INFO]
    for panel_plan in plan.panels:
        renderer_id = panel_plan.renderer.renderer_id if panel_plan.renderer else None
        target_binding = session.binding_of(panel_plan.target.pid) if panel_plan.target.pid else None
        entry = {"id": panel_plan.id, "key": panel_key(panel_plan.id), "label": panel_plan.name or panel_key(panel_plan.id),
                 "renderer": renderer_id, "status": panel_plan.status, "access": panel_plan.access, "drawable": panel_plan.drawable,
                 "reason": "; ".join(d.message for d in panel_plan.diagnostics if d.level != INFO) or None,
                 "diagnostics": [d.to_dict() for d in panel_plan.diagnostics], "position": panel_plan.position,
                 "exclusiveGroup": panel_plan.settings.get("exclusiveGroup"),
                 "kind": "map" if renderer_id in MAP_RENDERERS else renderer_id, "layer": None}
        if renderer_id in MAP_RENDERERS:
            if panel_plan.drawable and target_binding is not None:
                layer = _project_map_layer(panel_plan, target_binding, dashboard_config, entry, source_id, resource_roots)
                if layer is not None:
                    layers[entry["key"]] = layer
                    entry["layer"] = entry["key"]
                    entry["drawable"] = layer["drawable"]
            elif panel_plan.status in USABLE and panel_plan.access == RESTRICTED:
                restricted.extend(i.entity for i in panel_plan.inputs if i.required and i.access == RESTRICTED)
        elif renderer_id == "claims-list":
            if panel_plan.drawable and target_binding is not None and not claims:
                claims = claims_of(target_binding, evidence)
        elif renderer_id == "metadata-card":
            if panel_plan.drawable and target_binding is not None and metadata_binding is None:
                metadata_binding, metadata = target_binding, metadata_of(target_binding)
                folder, local_root = resource_roots.get(panel_plan.target.pid, (None, None))
                for f in metadata["files"]:
                    f["localPath"] = _served_path(source_id, folder, local_root, f["id"])
        for diagnostic in entry["diagnostics"]:
            if diagnostic["level"] != "info":
                warnings.append(f"panel {panel_plan.id}: {diagnostic['message']}")
        composition.append(entry)
    if metadata_binding is None and plan.subject_pid:   # no metadata panel: head the page with the object the dashboard is about
        metadata_binding = session.binding_of(plan.subject_pid)
        metadata = metadata_of(metadata_binding) if metadata_binding is not None else {}
    drawn = [k for k, layer in layers.items() if layer["drawable"]]
    panels = {
        "map": _panel_state("map", [e for e in composition if e["kind"] == "map"], bool(drawn)),
        "claims": _panel_state("claims", [e for e in composition if e["kind"] == "claims-list"], bool(claims)),
        "metadata": _panel_state("metadata", [e for e in composition if e["kind"] == "metadata-card"], bool(metadata)),
    }
    return {
        "id": source_id, "label": plan.title or metadata.get("title") or source_id, "sourceType": "fdo-dashboard",
        "profile": ((metadata_binding or {}).get("object", {}).get("profiles") or [None])[0], "fieldSchema": None, "metadata": metadata,
        "claims": claims, "evidence": [evidence_of(pid, c) for pid, c in evidence.items()], "layers": layers,
        "views": {"public": {"label": "Public", "layers": [k for k in drawn if layers[k]["accessTier"] == "public"]}},
        "allowedViews": ["public"], "figures": [], "panels": panels,
        "composition": composition, "plan": plan.to_dict(),
        "_consumption": {"package": FDO_CONSUME_PACKAGE_NAME, "panels": {pid: c.summary() for (pid, _), c in session.consumptions.items()},
                         "evidence": {pid: c.summary() for pid, c in evidence.items()}},
        "diagnostics": {"warnings": warnings, "missingFiles": [], "unmappedOutputs": [], "mode": "fdo-dashboard-plan",
                        "restricted": restricted, "accessRecord": _access_record(session, evidence)},
    }


def _access_record(session, evidence: dict) -> dict:
    """The reader's statuses per object and contract, as the page shows them under Technical details."""
    record = {}
    for (pid, contract), c in session.consumptions.items():
        short = pid.rsplit("/", 1)[-1]
        record[short if short not in record else f"{short} [{contract}]"] = {"contract": c.record.contract_id, "statuses": c.statuses}
    for pid, c in evidence.items():
        record[f"{pid.rsplit('/', 1)[-1]} (record)"] = {"contract": c.record.contract_id, "statuses": c.statuses}
    return record


def _panel_state(name: str, entries: list, shown: bool) -> dict:
    usable = [e for e in entries if e["status"] in USABLE and e["access"] == OPEN]
    reason = None if usable and shown else ("; ".join(e["reason"] or e["status"] for e in entries) or f"the dashboard has no {name} panel")
    return {"contract": "dashboard-composition-v1", "available": bool(usable) and shown, "reason": reason, "owner": None if usable else "object"}


def _project_map_layer(panel_plan: PanelPlan, target_binding: dict, dashboard_config: dict, entry: dict, source_id: str,
                       resource_roots: dict) -> dict | None:
    """One map layer from a drawable panel: the files the plugin reads, variables on the renderer's channels, the
    declared class breaks; served from the target object's own folder."""
    required_inputs = [i for i in panel_plan.inputs if i.kind == "Dataset" and i.required]
    if len(required_inputs) != 1:
        _note(entry, "projection.unsupported_inputs", WARNING,
              f"this consumer draws a map from exactly one required Dataset input; the panel binds {len(required_inputs)}")
        return None
    primary_input = required_inputs[0]
    elsewhere = [i.name for i in panel_plan.inputs if i.kind == "Dataset" and not i.required and i.entity != primary_input.entity]
    if elsewhere:
        _note(entry, "projection.unsupported_inputs", WARNING,
              f"this consumer reads optional variables from the same dataset as the required input; {elsewhere} bind another one")
        return None
    dataset = next(e for e in target_binding["entities"] if e["id"] == primary_input.entity)
    plugin_formats = {canonical(f) for f in primary_input.formats} - {None}
    folder, local_root = resource_roots.get(panel_plan.target.pid, (None, None))
    distributions = distributions_of(target_binding, dataset)
    for distribution in distributions:
        distribution["path"] = _served_path(source_id, folder, local_root, distribution["declared_path"])
    # the plugin's declared formats decide what it accepts, the formats registry what this dashboard reads
    reading = layer_reading(distributions, (lambda d: not plugin_formats or d["format"] in plugin_formats), "the plugin")
    renderable = next((d for d in distributions if any(r["ok"] for r in d["read"].values())), None)
    variables = {name: column for i in panel_plan.inputs for name, column in i.variables.items()}
    classification, note = classification_of(target_binding, dataset, panel_plan.settings.get("classification", ""))
    if note:
        _note(entry, "projection.classification_missing", WARNING, note)
    channels, without_breaks, without_column = {}, [], []
    for name, channel_spec in panel_plan.renderer.channels.items():
        column = variables.get(channel_spec.get("variable"))
        breaks = classification.get(channel_spec.get("breaks"), []) if channel_spec.get("breaks") else []
        channels[name] = {"column": column, "breaks": breaks}
        if not column:
            without_column.append(name)
        elif channel_spec.get("breaks") and not breaks:
            without_breaks.append(name)
    if without_column:
        _note(entry, "projection.channel_unbound", WARNING, f"the renderer's channel(s) {without_column} name no bound variable (check channels in renderers.yaml)")
    if without_breaks:
        _note(entry, "projection.classification_absent", WARNING,
              f"no declared class breaks for channel(s) {without_breaks}; the layer is not drawn (breaks are not computed by this consumer)")
    scheme = panel_plan.settings.get("colorScheme")
    if scheme and scheme not in panel_plan.renderer.palettes:
        _note(entry, "settings.palette_unknown", WARNING, f"colorScheme {scheme!r} is not one the renderer accepts {panel_plan.renderer.palettes}; the default is used")
        scheme = None
    if not renderable:
        _note(entry, "projection.no_servable_file", WARNING, "no file this dashboard can draw: " + reading["unread"]["webgl"])
    else:
        for engine, reason in reading["unread"].items():
            if reason:
                _note(entry, f"projection.no_file_for_{engine}", INFO, f"{engine}: nothing drawn ({reason})")
    structure = structure_of(target_binding, dataset, dashboard_config.get("structure_property"))
    crs_note = crs_problem(structure.get("crs"))
    if crs_note:
        _note(entry, "projection.crs_unsupported", WARNING, crs_note)
        refuse_all(reading, crs_note)
        renderable = None
    box_note = box_range_note(structure.get("outputFootprintBbox"))
    if box_note:
        _note(entry, "projection.box_axis_order", WARNING, box_note)
    stem = (renderable or {}).get("declared_path", "").rsplit("/", 1)[-1].rsplit(".", 1)[0] or None
    return {"type": "vector", "role": panel_plan.renderer.renderer_id, "label": entry["label"], "datasetLabel": dataset["fields"].get("name"), "product": dataset["id"],
            "accessTier": "public" if dataset["access"]["state"] == "open" else "private",
            "renderingStrategy": reading["renderingStrategy"], "engines": reading["engines"], "unread": reading["unread"], "notes": reading["notes"],
            "sourceLayer": stem, **structure,
            "conditionsOfAccess": "; ".join(dataset["access"]["conditions"]) or None,
            "variables": variables, "fields": sorted(set(variables.values())),
            "variableInfo": variable_info(target_binding, dataset, set(variables.values())), "classification": classification, "channels": channels,
            "distributions": distributions, "sourceUrl": None, "localPath": reading["localPath"],
            "style": {"colorScheme": scheme}, "panel": panel_plan.id, "renderer": panel_plan.renderer.renderer_id,
            "position": panel_plan.position, "exclusiveGroup": panel_plan.settings.get("exclusiveGroup"),
            "origin": {"pid": panel_plan.target.pid, "folder": folder},
            "drawable": bool(renderable) and not without_breaks and not without_column}


def _served_path(source_id: str, folder: str | None, local_root: Path | None, declared: str) -> str | None:
    """The URL this server serves a declared in-object path from, or None when the file is not in the object's folder."""
    rel = declared.lstrip("/")
    if rel.startswith("./"):
        rel = rel[2:]
    if not folder or local_root is None or "\\" in rel or ".." in rel.split("/") or not (local_root / rel).is_file():
        return None
    return f"/api/sources/{source_id}/files/{quote(folder, safe='')}/{quote(rel, safe='/')}"


def _note(entry: dict, code: str, level: str, message: str) -> None:
    entry["diagnostics"].append(Diagnostic(code, level, message).to_dict())
    if level != INFO:
        entry["reason"] = "; ".join(filter(None, [entry.get("reason"), message]))
