"""Adapter that loads a local RO-Crate output package as a dashboard dataset.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..services.rocrate_output_mapper import ROCrateOutputMapper
from .base import DataSourceAdapter, DatasetLoadError

METADATA_FILE = "ro-crate-metadata.json"
FALLBACK_DATASET = "dashboard_dataset.json"

class ROCrateOutputAdapter(DataSourceAdapter):
    adapter_name = "rocrate-output"

    def load_dataset(self, source_config, context=None):
        context = context or {}
        root = Path(context.get("root", "."))
        source_id = source_config.get("id", "hamburg-rocrate-derived")
        locator = source_config.get("locator", {})
        package_root = (root / locator.get("value", "")).resolve()

        if not package_root.is_dir():
            raise DatasetLoadError(
                f"RO-Crate package directory not found: {package_root}",
                details={"locator": locator},
            )

        if (package_root / METADATA_FILE).exists():

            try:
                mapper = ROCrateOutputMapper(package_root, base_url=locator.get("base_url"))
                dataset = mapper.to_dashboard_dataset(dataset_id=source_id)
            except FileNotFoundError as exc:
                raise DatasetLoadError(str(exc), details={"locator": locator}) from exc
        elif (package_root / FALLBACK_DATASET).exists():

            dataset = json.loads((package_root / FALLBACK_DATASET).read_text(encoding="utf-8"))
            dataset["id"] = source_id
            diagnostics = dataset.setdefault("diagnostics", {})
            diagnostics.setdefault("warnings", []).append(
                f"Loaded precomputed {FALLBACK_DATASET}; {METADATA_FILE} not found in package."
            )
            diagnostics["mode"] = "precomputed-fallback"
        else:
            raise DatasetLoadError(
                f"No {METADATA_FILE} or {FALLBACK_DATASET} found in {package_root}. "
                "Copy the RO-Crate output files there — see the README section "
                "'Using RO-Crate output packages'.",
                details={"locator": locator},
            )

        _localize_resource_urls(dataset, source_id, package_root)
        return dataset

def _localize_resource_urls(dataset: dict, source_id: str, package_root: Path) -> None:

    def served(ref):
        if not ref:
            return None
        name = os.path.basename(str(ref))
        if name and (package_root / name).exists():
            return f"/api/sources/{source_id}/files/{name}"
        return None

    for layer in (dataset.get("layers") or {}).values():
        if isinstance(layer, dict):
            layer["localPath"] = served(layer.get("localPath") or layer.get("sourceUrl"))

    for figure in dataset.get("figures") or []:
        if isinstance(figure, dict):
            figure["localPath"] = served(figure.get("localPath") or figure.get("sourceUrl"))

    for claim in dataset.get("claims") or []:
        for output in claim.get("outputs") or []:
            if isinstance(output, dict):
                output["localPath"] = served(output.get("localPath") or output.get("sourceUrl"))
