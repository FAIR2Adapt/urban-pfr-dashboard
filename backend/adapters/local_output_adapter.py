"""Local-output adapter — the fully-implemented one.

Reads the public paper_format outputs already on disk and returns a normalized
dataset. The locator points at a directory expected to contain:
  - Final_Layer_CS3_public.geojson        -> riskMap layer  (required)
  - Statistical_Units_CS3_public.geojson  -> boundaries layer (optional)
  - statement1_fig*.json                  -> FAIR JSON-LD metadata (optional)
"""
from __future__ import annotations

from pathlib import Path

from ..services import flood_processing as fp
from ..services import geojson_loader as gl
from ..services import metadata_parser as mp
from .base import DataSourceAdapter, DatasetLoadError

RISK_FILE = "Final_Layer_CS3_public.geojson"
BOUNDARIES_FILE = "Statistical_Units_CS3_public.geojson"

class LocalOutputAdapter(DataSourceAdapter):
    adapter_name = "local-output"

    def load_dataset(self, source_config, context=None):
        context = context or {}
        root = Path(context.get("root", "."))
        locator = source_config.get("locator", {})
        base_dir = (root / locator.get("value", "")).resolve()

        if not base_dir.is_dir():
            raise DatasetLoadError(
                f"Local output directory not found: {base_dir}",
                details={"locator": locator},
            )

        ok, reason = gl.geo_available()
        if not ok:
            raise DatasetLoadError(
                "GeoPandas/pyproj are required for the local-output adapter. "
                "Install with: pip install -r requirements.txt",
                status=503,
                details={"importError": reason},
            )

        risk_path = base_dir / RISK_FILE
        if not risk_path.exists():
            raise DatasetLoadError(
                f"Required risk-map file missing: {risk_path}",
                details={"expected": RISK_FILE},
            )

        buildings = gl.read_geodataframe(risk_path)
        cols = fp.resolve_columns(list(buildings.columns))
        risk_fc, stats = fp.build_risk_points(buildings, cols)
        layers = {"riskMap": {"type": "geojson", "data": risk_fc}}

        boundaries_path = base_dir / BOUNDARIES_FILE
        if boundaries_path.exists():
            units = gl.read_geodataframe(boundaries_path)
            layers["boundaries"] = {
                "type": "geojson",
                "data": fp.build_boundaries(units, fp.resolve_columns(list(units.columns))),
            }

        statements = mp.load_jsonld_statements(base_dir)
        metadata = mp.build_metadata(
            label=source_config.get("label", source_config.get("id", "")),
            locator=locator,
            stats=stats,
            statements=statements,
            columns=cols,
        )

        ui = {
            "defaultLayer": "riskMap",
            "defaultRiskField": fp.DEFAULT_RISK_FIELD,
            "availableRiskFields": fp.AVAILABLE_RISK_FIELDS,
        }

        return self.normalize_dataset(
            id=source_config.get("id"),
            label=source_config.get("label", source_config.get("id")),
            source_type="local-output",
            layers=layers,
            metadata=metadata,
            ui=ui,
        )
