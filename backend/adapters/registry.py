"""Adapter registry: the `adapter` name of a source in config/sources.json to its class."""
from __future__ import annotations

from .base import AdapterError, DataSourceAdapter
from .fdo_dashboard_adapter import FDODashboardAdapter
from .fdo_resource_adapter import FDOResourceAdapter

# Profile attribute TBD: conformsTo IRIs for the composition and plugin profiles; the source config names the adapter
_REGISTRY: dict[str, type[DataSourceAdapter]] = {
    FDOResourceAdapter.adapter_name: FDOResourceAdapter,
    FDODashboardAdapter.adapter_name: FDODashboardAdapter,
}


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


def get_adapter(adapter_name: str) -> DataSourceAdapter:
    cls = _REGISTRY.get(adapter_name)
    if cls is None:
        raise AdapterError(f"Unknown adapter '{adapter_name}'. Known adapters: {available_adapters()}", status=400)
    return cls()
