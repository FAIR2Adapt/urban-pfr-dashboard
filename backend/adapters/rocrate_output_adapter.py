"""Adapter that loads a local RO-Crate output package as a dashboard dataset.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

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

        # Authorization: internal deployment (or, later, an FDO Resolver policy
        # decision) unlocks the private view. Public deployment stays public-only.
        if context.get("deployment") == "internal" and (dataset.get("views") or {}).get("private"):
            dataset["allowedViews"] = ["public", "private"]

        return dataset

def _localize_resource_urls(dataset: dict, source_id: str, package_root: Path) -> None:

    def served(ref):
        if not ref:
            return None
        value = str(ref).strip()
        parsed = urlsplit(value)
        path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
        rel = unquote(path).lstrip("/")
        if rel.startswith("./"):
            rel = rel[2:]
        candidates = []
        if rel and "\\" not in rel and ".." not in rel.split("/"):
            candidates.append(rel)
        name = os.path.basename(rel.rstrip("/"))
        if not name:
            return None
        candidates.extend((name, f"public/{name}", f"private/{name}"))
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if (package_root / candidate).exists():
                return f"/api/sources/{source_id}/files/{quote(candidate, safe='/')}"
        return None

    for layer in (dataset.get("layers") or {}).values():
        if isinstance(layer, dict):
            layer["localPath"] = served(layer.get("localPath") or layer.get("sourceUrl"))
            # data-product crates: every distribution (fgb/gpkg/pmtiles) gets a
            # served URL so the frontend can render or offer it for download.
            for dist in layer.get("distributions") or []:
                if isinstance(dist, dict) and dist.get("path"):
                    dist["path"] = served(dist["path"])

    for f in ((dataset.get("metadata") or {}).get("files") or []):
        if isinstance(f, dict) and f.get("localPath"):
            f["localPath"] = served(f["localPath"])

    for figure in dataset.get("figures") or []:
        if isinstance(figure, dict):
            figure["localPath"] = served(figure.get("localPath") or figure.get("sourceUrl"))

    for claim in dataset.get("claims") or []:
        for output in claim.get("outputs") or []:
            if isinstance(output, dict):
                output["localPath"] = served(output.get("localPath") or output.get("sourceUrl"))
