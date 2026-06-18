"""Data-source registry loader.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_REL = "config/sources.json"

class SourcesConfig:

    def __init__(self, data: dict, root: Path):
        self._data = data or {}
        self.root = root

    @property
    def default_source(self):
        return self._data.get("defaultSource")

    @property
    def sources(self) -> list[dict]:
        return self._data.get("sources", [])

    def get(self, source_id: str):
        for source in self.sources:
            if source.get("id") == source_id:
                return source
        return None

    def public_sources(self) -> list[dict]:
        return [
            {
                "id": s.get("id"),
                "label": s.get("label", s.get("id")),
                "adapter": s.get("adapter"),
                "enabled": bool(s.get("enabled")),
                "note": s.get("note"),
            }
            for s in self.sources
        ]

def _expand_env(data: dict) -> dict:

    for source in data.get("sources", []):
        locator = source.get("locator")
        if isinstance(locator, dict) and isinstance(locator.get("value"), str):
            locator["value"] = os.path.expandvars(locator["value"])
    return data

def load_config(root: str | Path) -> SourcesConfig:
    """Load the source registry. """
    root = Path(root)
    env_path = os.environ.get("DASHBOARD_CONFIG")
    if env_path:
        path = Path(env_path)
        if not path.is_absolute():
            path = root / path
    else:
        path = root / CONFIG_REL
    if not path.exists():
        return SourcesConfig({"defaultSource": None, "sources": []}, root)
    with path.open(encoding="utf-8") as handle:
        return SourcesConfig(_expand_env(json.load(handle)), root)
