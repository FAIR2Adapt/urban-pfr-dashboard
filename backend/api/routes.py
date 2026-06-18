from __future__ import annotations

import traceback

from ..adapters.base import AdapterError
from ..adapters.registry import get_adapter
from ..config import SourcesConfig

def list_sources(config: SourcesConfig):
    return 200, {
        "defaultSource": config.default_source,
        "sources": config.public_sources(),
    }

def load_dataset_dict(config: SourcesConfig, source_id: str) -> dict:
    #Resolve a source to its normalized dataset dict, or raise AdapterError.
    source = config.get(source_id)
    if source is None:
        raise AdapterError(f"Unknown source id: {source_id}", status=404)
    if not source.get("enabled", False):
        raise AdapterError(
            f"Source '{source_id}' is not enabled.",
            status=409,
            details={"adapter": source.get("adapter"), "note": source.get("note")},
        )
    return get_adapter(source.get("adapter")).load_dataset(source, context={"root": config.root})

def get_dataset(config: SourcesConfig, source_id: str):
    try:
        return 200, load_dataset_dict(config, source_id)
    except AdapterError as exc:

        return exc.status, exc.to_dict()
    except Exception as exc:
        traceback.print_exc()
        return 500, {"error": str(exc)}

def handle_api(config: SourcesConfig, parts: list[str]):
    if not parts or parts[0] != "api":
        return None
    if len(parts) == 2 and parts[1] == "sources":
        return list_sources(config)
    if len(parts) == 4 and parts[1] == "sources" and parts[3] == "dataset":
        return get_dataset(config, parts[2])
    return 404, {"error": "unknown api endpoint", "path": "/" + "/".join(parts)}
