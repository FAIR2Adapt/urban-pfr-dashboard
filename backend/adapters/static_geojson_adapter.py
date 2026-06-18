#Static GeoJSON adapter — simple pass-through

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

from ..services import metadata_parser as mp
from .base import DataSourceAdapter, DatasetLoadError

class StaticGeoJsonAdapter(DataSourceAdapter):
    adapter_name = "static-geojson"

    def load_dataset(self, source_config, context=None):
        context = context or {}
        root = Path(context.get("root", "."))
        locator = source_config.get("locator", {})
        loc_type = locator.get("type")
        value = locator.get("value", "")

        try:
            if loc_type == "url":
                with urlopen(value, timeout=30) as resp:
                    geojson = json.loads(resp.read().decode("utf-8"))
            elif loc_type in ("local-path", "file"):
                path = (root / value).resolve()
                if not path.exists():
                    raise DatasetLoadError(f"Static GeoJSON file not found: {path}")
                with path.open(encoding="utf-8") as handle:
                    geojson = json.load(handle)
            else:
                raise DatasetLoadError(
                    f"static-geojson adapter cannot handle locator type '{loc_type}'. "
                    "Use 'url' or 'local-path'."
                )
        except DatasetLoadError:
            raise
        except Exception as exc:
            raise DatasetLoadError(f"Failed to load static GeoJSON: {exc}") from exc

        metadata = mp.build_metadata(
            label=source_config.get("label", source_config.get("id", "")),
            locator=locator,
            description="Static GeoJSON passed through without flood processing.",
        )
        return self.normalize_dataset(
            id=source_config.get("id"),
            label=source_config.get("label", source_config.get("id")),
            source_type="static-geojson",
            layers={"riskMap": {"type": "geojson", "data": geojson}},
            metadata=metadata,
            ui={"defaultLayer": "riskMap", "defaultRiskField": None, "availableRiskFields": []},
        )
