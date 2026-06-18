"""FDOResource adapter — PLANNED, not implemented yet.
Placeholder that fails with a clear, structured error. 
"""
from __future__ import annotations

from .base import AdapterNotImplementedError, DataSourceAdapter

class FDOResourceAdapter(DataSourceAdapter):
    adapter_name = "fdo-resource"

    def load_dataset(self, source_config, context=None):
        raise AdapterNotImplementedError(
            "The FDOResource adapter is not implemented yet.",
            details={
                "adapter": self.adapter_name,
                "sourceId": source_config.get("id"),
                "locator": source_config.get("locator", {}),
                "status": "planned",
            },
        )
