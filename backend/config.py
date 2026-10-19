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
    def deployment(self):
        return self._data.get("deployment", "public")

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
                "city": city_of(s),
                "adapter": s.get("adapter"),
                "profile": (s.get("locator") or {}).get("profile"),
                "enabled": bool(s.get("enabled")),
                "note": s.get("note"),
            }
            for s in self.sources
        ]


def files_root(source: dict, root: "Path") -> "Path | None":
    """The folder this server serves a source's files from: `locator.files` (one object), else
    `locator.value`, else `<fixtures>/objects` for a recorded source whose paths start with the object's folder."""
    locator = source.get("locator") or {}
    for key in ("files", "value"):
        if locator.get(key):
            return (root / locator[key]).resolve()
    if locator.get("fixtures"):
        return (root / locator["fixtures"] / "objects").resolve()
    return None


def city_of(source: dict) -> str:
    """The city a source serves: declared in config (`city`); the label stands in when it is missing. Never parsed from the label."""
    city = source.get("city")
    if city is not None and not isinstance(city, str):
        raise ValueError(f"source {source.get('id')!r}: city must be a string")
    return city or source.get("label") or source.get("id") or ""

def _requires(data: dict, root: Path) -> dict:
    """Disable a source whose `requires` path (local, git-ignored) is absent."""
    for source in data.get("sources", []):
        needed = source.get("requires")
        if needed and not (root / needed).exists():
            source["enabled"] = False
            source["note"] = f"needs {needed} (local only, not in the repository)"
    return data

def _expand_env(data: dict) -> dict:

    for source in data.get("sources", []):
        locator = source.get("locator")
        if isinstance(locator, dict):
            for key in ("value", "files", "fixtures"):
                if isinstance(locator.get(key), str):
                    locator[key] = os.path.expandvars(locator[key])
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
        config = SourcesConfig(_requires(_expand_env(json.load(handle)), root), root)
    for source in config.sources:
        city_of(source)   # a wrong type fails at start, not in the browser
    return config
