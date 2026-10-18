"""Compose a DashboardPlan from a Dashboard FDO: plugins resolved through the renderer registry, inputs bound by the binding policy."""
from __future__ import annotations

import json
import time

from .binder import BindingPolicy, EntityIndex, ExactSemanticBinder
from .models import (ERROR, FAIL, INFO, PARTIAL, PASS, USABLE, WARNING, DashboardPlan, PanelPlan, PluginReference,
                     TargetReference, worse)
from .registry import resolve_renderer
from .session import CompositionSession

DASHBOARD_CONTRACT, PLUGIN_CONTRACT, OBJECT_CONTRACT = "dashboard-composition-v1", "plugin-description-v1", "composer-object-v1"
CONTRACTS = (DASHBOARD_CONTRACT, PLUGIN_CONTRACT, OBJECT_CONTRACT)


def failure_reason(consumption) -> str:
    for diagnostic in consumption.diagnostics:
        if diagnostic["status"] in ("FAIL", "INDETERMINATE"):
            return f"{diagnostic['code']} {diagnostic['status']}: {diagnostic['message']}"
    return consumption.record.stopped or consumption.record.error or "not usable"


def compose(dashboard_pid: str, registry: dict, session: CompositionSession, binder: BindingPolicy | None = None) -> DashboardPlan:
    binder = binder or ExactSemanticBinder()
    clock = time.perf_counter()
    dashboard = session.consume_object(dashboard_pid, DASHBOARD_CONTRACT)
    if not dashboard.is_usable:
        plan = DashboardPlan(dashboard_pid, None, None, FAIL, evidence={"objects_read": session.crate_hashes()})
        plan.add("compose.dashboard_unreadable", ERROR, f"the Dashboard FDO could not be read: {failure_reason(dashboard)}")
        return plan
    dashboard_binding = dashboard.binding
    dashboard_entity = next(e for e in dashboard_binding["entities"] if e["type"] == "Dashboard")
    by_id = {e["id"]: e for e in dashboard_binding["entities"]}
    parts = dashboard_entity["fields"].get("panels") or []
    uncomposed = [part for part in parts if by_id.get(part, {}).get("type") != "Panel"]
    panels = [_compose_panel(by_id[part], dashboard_binding, registry, session, binder)
              for part in parts if by_id.get(part, {}).get("type") == "Panel"]
    _order(panels)
    _note_repeated_content(panels)
    usable = [p for p in panels if p.status in USABLE]
    status = PASS if panels and all(p.status == PASS for p in panels) else PARTIAL if usable else FAIL
    plan = DashboardPlan(dashboard_pid, dashboard_entity["fields"].get("name"), dashboard_entity["fields"].get("about"), status, panels,
                         evidence={"crate_sha256": dashboard.record.crate_sha256, "map": dashboard_binding["object"]["map"],
                                   "overlay": dashboard_binding["object"]["overlay"], "objects_read": session.crate_hashes(),
                                   "compose_ms": round((time.perf_counter() - clock) * 1000, 1)},
                         uncomposed_parts=uncomposed)
    if uncomposed:
        plan.add("compose.part_not_panel", INFO, f"{len(uncomposed)} part(s) of the dashboard are not panels and were not composed: {', '.join(uncomposed)}")
    if not panels:
        plan.add("compose.no_panel", ERROR, "the dashboard lists no panel")
    for diagnostic in session.assumptions.values():
        plan.diagnostics.append(diagnostic)
    return plan


def _order(panels: list) -> None:
    """By position, then by panel id (stable, not the crate's serialization order); shared or missing positions are said."""
    panels.sort(key=lambda p: (p.position is None, p.position if p.position is not None else 0, p.id))
    by_position: dict = {}
    for panel in panels:
        if panel.position is None:
            panel.add("order.no_position", WARNING, "no position: placed after the positioned panels, by panel id")
        else:
            by_position.setdefault(panel.position, []).append(panel.id)
    for position, ids in by_position.items():
        if len(ids) > 1:
            for panel in panels:
                if panel.id in ids:
                    panel.add("order.position_shared", WARNING, f"position {position} is shared with {', '.join(i for i in ids if i != panel.id)}; ordered by panel id")


def _content_identity(panel: PanelPlan) -> str:
    return json.dumps([panel.plugin.pid, panel.plugin.version, panel.target.pid, panel.target.fragment,
                       [(i.name, i.entity, i.variables) for i in panel.inputs], panel.settings], sort_keys=True, default=str)


def _note_repeated_content(panels: list) -> None:
    """Two panels with the same plugin, target, bindings and settings are two panels (their ids and positions differ);
    the repetition is noted, nothing is downgraded."""
    first_of: dict = {}
    for panel in panels:
        if panel.status not in USABLE:
            continue
        key = _content_identity(panel)
        if key in first_of:
            panel.add("panel.repeated_content", INFO, f"shows the same content as {first_of[key]} (same plugin, object, bindings and settings)")
        else:
            first_of[key] = panel.id


def _compose_panel(panel_entity: dict, dashboard_binding: dict, registry: dict, session: CompositionSession, binder: BindingPolicy) -> PanelPlan:
    panel_fields = panel_entity["fields"]
    raw_position = str(panel_fields.get("position") or "")
    position = int(raw_position) if raw_position.lstrip("-").isdigit() else None
    target_pid, _, fragment = (panel_fields.get("object") or "").partition("#")
    panel = PanelPlan(panel_entity["id"], panel_fields.get("name"), PluginReference(panel_fields.get("instrument")),
                      TargetReference(target_pid or None, fragment or None), position=position)
    declared_overrides = [(e["fields"].get("name"), e["fields"].get("value")) for e in dashboard_binding["entities"]
                          if e["type"] == "Property" and panel_entity["id"] in e["holders"]]
    override_names = [n for n, _ in declared_overrides]
    repeated = sorted({n for n in override_names if override_names.count(n) > 1})
    if repeated:
        panel.fail("panel.duplicate_setting", f"the panel sets {repeated} more than once")
        return panel
    panel_setting_overrides = dict(declared_overrides)
    if not panel_fields.get("instrument"):
        panel.fail("panel.no_instrument", "the panel names no plugin (instrument)")
        return panel
    plugin = session.consume_object(panel_fields["instrument"], PLUGIN_CONTRACT)
    if not plugin.is_usable:
        panel.fail("plugin.unreadable", f"plugin {panel_fields['instrument']} could not be read: {failure_reason(plugin)}")
        return panel
    plugin_binding = plugin.binding
    plugin_entity = next(e for e in plugin_binding["entities"] if e["type"] == "Plugin")
    panel.plugin = PluginReference(panel_fields["instrument"], plugin_entity["fields"].get("version"),
                                   plugin_entity["fields"].get("kind"), plugin_entity["fields"].get("name"))
    panel.evidence["plugin_sha256"] = plugin.record.crate_sha256
    _settings(panel, plugin_binding, panel_setting_overrides)
    panel.renderer = resolve_renderer(registry, panel.plugin.pid, panel.plugin.version)
    if panel.renderer is None:
        panel.add("registry.no_renderer", ERROR, f"no trusted implementation for plugin {panel.plugin.pid}")
    elif panel.renderer.status == FAIL:
        panel.add("registry.version_mismatch", ERROR,
                  f"plugin declares version {panel.plugin.version}; the implementation supports {panel.renderer.supported_plugin_version}; not run")
    elif panel.renderer.status != PASS:
        panel.add("registry.version_undeclared", WARNING,
                  f"the plugin declares no version; the implementation supports {panel.renderer.supported_plugin_version}; not run")
    if not target_pid:
        panel.fail("panel.no_object", "the panel names no object")
        return panel
    target = session.consume_object(target_pid, OBJECT_CONTRACT)
    if not target.is_usable:
        panel.fail("object.unreadable", f"object {target_pid} could not be read: {failure_reason(target)}")
        return panel
    panel.evidence["object_sha256"] = target.record.crate_sha256
    if target_pid in session.assumptions:
        panel.diagnostics.append(session.assumptions[target_pid])
    result = binder.bind(plugin_binding, target.binding, fragment or None)
    panel.inputs, panel.access = result.inputs, result.access
    panel.diagnostics.extend(result.diagnostics)
    panel.evidence["decisions"] = result.decisions
    panel.status = worse(panel.status, result.status)
    return panel


def _settings(panel: PanelPlan, plugin_binding: dict, overrides: dict) -> None:
    """Plugin defaults overlaid by the panel's declared values; names must be declared once by the plugin."""
    declared = [e["fields"].get("name") for e in plugin_binding["entities"] if e["type"] == "Setting"]
    repeated = sorted({n for n in declared if declared.count(n) > 1})
    if repeated:
        panel.fail("plugin.duplicate_setting", f"the plugin declares the setting name(s) {repeated} more than once")
        return
    defaults = {e["fields"].get("name"): e["fields"].get("default") for e in plugin_binding["entities"] if e["type"] == "Setting"}
    panel.settings = dict(defaults)
    for name, value in overrides.items():
        if name in defaults:
            panel.settings[name] = value
        else:
            panel.add("settings.undeclared", WARNING, f"setting {name!r} is not declared by the plugin; ignored")
