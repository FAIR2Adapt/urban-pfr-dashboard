"""FDO dashboard adapter: the dashboard is composed from a Dashboard FDO (plugins, objects) through the composer,
then projected onto the dataset the page reads. Every object's files are served from that object's own folder."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..composer.composer import FAIL, compose
from ..composer.registry import load_registry
from ..composer.session import OVERLAY, CompositionSession
from ..projections.cs3_dataset import project_dashboard_plan_to_cs3_dataset
from .base import AdapterError, CompositionError, DataSourceAdapter
from .fdo_resource_adapter import (CONFIG, _check_footprints, _follow_claim_records, _own_folder, _report_unserved_files, _write_log,
                                   attach_record_material, fixture_folders)

RENDERER_REGISTRY_PATH = "config/renderers.yaml"


class FDODashboardAdapter(DataSourceAdapter):
    adapter_name = "fdo-dashboard"

    def load_dataset(self, source_config: dict, context: dict | None = None) -> dict:
        context = context or {}
        root = Path(context.get("root", "."))
        locator = source_config.get("locator") or {}
        try:
            from fdo_consume import consume
        except ImportError as exc:
            raise AdapterError("fdo-consume is not installed (see README, 'Run it locally')", status=503,
                               details={"adapter": self.adapter_name}) from exc
        dashboard_config = yaml.safe_load((root / CONFIG).read_text(encoding="utf-8"))
        fixtures = (root / locator.get("fixtures", "")).resolve()
        contracts, profile_maps = _own_folder(root, locator, "contracts"), _own_folder(root, locator, "profile_maps")
        session = CompositionSession(consume, str(fixtures), contracts, profile_maps, locator.get("profile_overlay") or OVERLAY,
                                     assumed_profiles=locator.get("assumed_profiles"))
        plan = compose(locator["pid"], load_registry(root / RENDERER_REGISTRY_PATH), session)
        if plan.status == FAIL:
            raise CompositionError("the Dashboard FDO could not be composed: " + "; ".join(d.message for d in plan.diagnostics),
                                   details={"plan": plan.to_dict()})
        # claims follow the records from their own panel's target, not from the dashboard's `about`
        evidence: dict = {}
        for panel_plan in plan.drawable_panels:
            if panel_plan.renderer.renderer_id == "claims-list" and panel_plan.target.pid:
                target = session.consume_object(panel_plan.target.pid, "composer-object-v1")
                evidence.update(_follow_claim_records(target, dashboard_config.get("evidence"), consume, str(fixtures), contracts, profile_maps))
        source_id = source_config.get("id", "fdo-dashboard")
        roots = fixture_folders(fixtures)
        dataset = project_dashboard_plan_to_cs3_dataset(plan, session, dashboard_config, source_id, evidence, roots)
        attach_record_material(dataset, None, locator["pid"], None, None, evidence, roots, source_id, (fixtures / "objects").resolve())
        _check_footprints(dataset, lambda layer: roots.get((layer.get("origin") or {}).get("pid"), (None, None))[1])
        _write_log(root, source_id, dataset.pop("_consumption"))
        _report_unserved_files(dataset)
        return dataset
