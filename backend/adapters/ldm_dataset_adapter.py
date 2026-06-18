"""TIB LDM dataset adapter — PLANNED, not implemented yet.

Placeholder that fails gracefully with a clear, structured error so the source
can already appear in config/sources.json and the registry. Implement
`load_dataset` (resolve the LDM dataset URL, fetch its resources, map them onto
the normalized layers/metadata shape) to enable it.
"""
from __future__ import annotations

from .base import AdapterNotImplementedError, DataSourceAdapter

class LdmDatasetAdapter(DataSourceAdapter):
    adapter_name = "ldm-dataset"

    def load_dataset(self, source_config, context=None):
        raise AdapterNotImplementedError(
            "#TODO complete when TIB Loom record be public",
            details={
                "adapter": self.adapter_name,
                "sourceId": source_config.get("id"),
                "locator": source_config.get("locator", {}),
                "status": "planned",
            },
        )
