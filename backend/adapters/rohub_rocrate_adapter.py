# TO DO ROHub RO-Crate adapter — PLANNED

from __future__ import annotations

from .base import AdapterNotImplementedError, DataSourceAdapter

class ROHubROCrateAdapter(DataSourceAdapter):
    adapter_name = "rohub-rocrate"

    def load_dataset(self, source_config, context=None):
        raise AdapterNotImplementedError(
            "The ROHub RO-Crate adapter is not implemented yet — this is a planned data source.",
            details={
                "adapter": self.adapter_name,
                "sourceId": source_config.get("id"),
                "locator": source_config.get("locator", {}),
                "status": "planned",
            },
        )
