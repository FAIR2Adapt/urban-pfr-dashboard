"""Renderer registry: which trusted local implementation stands for which Plugin FDO, for which plugin version.
A plugin's url is never loaded."""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import FAIL, INDETERMINATE, PASS, RendererBinding

REQUIRED = ("plugin_pid", "supported_plugin_version", "renderer_id")


def load_registry(path: str | Path) -> dict:
    """{plugin pid: entry}; refused at load when an entry lacks a key, a plugin is listed twice or a channel has no variable."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    registry: dict = {}
    for index, entry in enumerate(data.get("renderers", [])):
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            raise ValueError(f"renderers.yaml entry {index}: missing {missing}")
        if entry["plugin_pid"] in registry:
            raise ValueError(f"renderers.yaml: plugin {entry['plugin_pid']} is listed twice")
        for name, channel_spec in (entry.get("channels") or {}).items():
            if not isinstance(channel_spec, dict) or "variable" not in channel_spec:
                raise ValueError(f"renderers.yaml: channel {name!r} of {entry['plugin_pid']} needs a variable")
        registry[entry["plugin_pid"]] = entry
    return registry


def resolve_renderer(registry: dict, plugin_pid: str, declared_version: str | None) -> RendererBinding | None:
    """None when no implementation is registered; else the binding with its compatibility status:
    PASS for the exact supported version, INDETERMINATE when the plugin declares none, FAIL for another version."""
    entry = registry.get(plugin_pid)
    if entry is None:
        return None
    supported = str(entry["supported_plugin_version"])
    status = INDETERMINATE if not declared_version else PASS if str(declared_version) == supported else FAIL
    return RendererBinding(entry["renderer_id"], supported, entry.get("channels") or {}, list(entry.get("palettes") or []), status)
