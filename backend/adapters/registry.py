"""Adapter registry.

Maps the `adapter` string in config/sources.json to its adapter class. This is
the single place the backend decides *how* to resolve a source — add a new entry
here when you add a new adapter.
"""
from __future__ import annotations

from .base import AdapterError, DataSourceAdapter
from .fdo_resource_adapter import FDOResourceAdapter
from .ldm_dataset_adapter import LdmDatasetAdapter
from .local_output_adapter import LocalOutputAdapter
from .rocrate_output_adapter import ROCrateOutputAdapter
from .rohub_rocrate_adapter import ROHubROCrateAdapter
from .static_geojson_adapter import StaticGeoJsonAdapter

_REGISTRY: dict[str, type[DataSourceAdapter]] = {
    LocalOutputAdapter.adapter_name: LocalOutputAdapter,
    ROCrateOutputAdapter.adapter_name: ROCrateOutputAdapter,
    StaticGeoJsonAdapter.adapter_name: StaticGeoJsonAdapter,
    LdmDatasetAdapter.adapter_name: LdmDatasetAdapter,
    ROHubROCrateAdapter.adapter_name: ROHubROCrateAdapter,
    FDOResourceAdapter.adapter_name: FDOResourceAdapter,
}

def available_adapters() -> list[str]:
    return sorted(_REGISTRY)

def get_adapter(adapter_name: str) -> DataSourceAdapter:
    cls = _REGISTRY.get(adapter_name)
    if cls is None:
        raise AdapterError(
            f"Unknown adapter '{adapter_name}'. Known adapters: {available_adapters()}",
            status=400,
        )
    return cls()
