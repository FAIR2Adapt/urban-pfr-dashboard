"""The config path (config/dashboard.yaml layers over one Data FDO) as a plan, for comparison with compose()."""
from __future__ import annotations

from ..services.binding_to_dataset import _variables
from .models import FAIL, PASS, DashboardPlan, InputBinding, PanelPlan, PluginReference, RendererBinding, TargetReference

SLOT_RENDERER = {"riskMap": "bivariate-map", "socialVulnerability": "single-variable-map", "vulnerabilityDrivers": "bivariate-background"}   # the layer keys of config/dashboard.yaml


def plan_from_config(data_pid: str, data_binding: dict, dashboard_config: dict, registry: dict) -> DashboardPlan:
    by_slot = {slot: next((e for e in registry.values() if e["renderer_id"] == renderer_id), None) for slot, renderer_id in SLOT_RENDERER.items()}
    datasets = {e["pid"]: e for e in data_binding["entities"] if e["type"] == "Dataset" and e["pid"]}
    panels = []
    for index, (slot, spec) in enumerate(dashboard_config["layers"].items()):
        renderer_entry, dataset = by_slot.get(slot), datasets.get(spec["product"])
        panel_plan = PanelPlan(f"config:{slot}", slot, PluginReference((renderer_entry or {}).get("plugin_pid")), TargetReference(data_pid),
                               position=index + 1)
        if renderer_entry is not None:
            panel_plan.renderer = RendererBinding(renderer_entry["renderer_id"], str(renderer_entry["supported_plugin_version"]),
                                                  renderer_entry.get("channels") or {}, list(renderer_entry.get("palettes") or []))
        if dataset is None or renderer_entry is None:
            panel_plan.fail("config.unbound", f"no dataset {spec['product']}" if dataset is None else f"no renderer for slot {slot}")
        else:
            panel_plan.target = TargetReference(data_pid, dataset["id"].lstrip("#"))
            panel_plan.inputs = [InputBinding("main", dataset["id"], "Dataset", _variables(data_binding, dataset, dashboard_config, spec), True)]
            panel_plan.settings = {"classification": spec.get("classification")}
        panels.append(panel_plan)
    status = PASS if panels and all(p.status == PASS for p in panels) else FAIL
    return DashboardPlan("config", dashboard_config.get("title"), data_pid, status, panels)
