"""The analysis descriptions and run parameters a Knowledge Loom record lists: the files that support a statement,
read from the record's folder in the shape the page shows. Keys of the analysis template are matched by their fragment."""
from __future__ import annotations

import json
from pathlib import Path

JSON_TYPES = ("application/ld+json", "application/json")


def analyses_of(binding: dict, folder: Path | None) -> dict:
    """statement id -> analysis, for every file of the record that declares which statements it supports."""
    out: dict = {}
    if binding is None or folder is None:
        return out
    for resource in binding.get("resources", []):
        supports = (resource.get("fields") or {}).get("supports") or []
        supports = supports if isinstance(supports, list) else [supports]
        if not supports or (resource.get("media_type") or "") not in JSON_TYPES:
            continue
        doc = _read_json(folder / resource["id"])
        if not isinstance(doc, dict):
            continue
        analysis = _analysis(doc, resource["id"])
        for statement in supports:
            out[str(statement)] = analysis
    return out


def run_parameters_of(binding: dict, folder: Path | None) -> dict | None:
    """The run-parameters file of a record (software, run, parameters), when it lists one."""
    if binding is None or folder is None:
        return None
    for resource in binding.get("resources", []):
        if resource["id"].rsplit("/", 1)[-1] == "run-parameters.json":
            doc = _read_json(folder / resource["id"])
            if isinstance(doc, dict):
                return {"file": resource["id"], "software": doc.get("software") or {}, "run": doc.get("run") or {},
                        "parameters": doc.get("parameters") or {}}
    return None


def files_of(binding: dict) -> list:
    """The record's files with the name and size it declares, grouped later by the page."""
    return [{"id": r["id"], "name": r.get("name") or r["id"], "mediaType": r.get("media_type"), "contentSize": r.get("size"),
             "accessTier": {"open": "public", "restricted": "restricted"}.get(r["access"]["state"], "unstated"), "localPath": None}
            for r in binding.get("resources", [])]


def _read_json(path: Path):
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _frag(key: str) -> str:
    return key.rsplit("#", 1)[-1] if "#" in key else key


def _get(node, name: str):
    if not isinstance(node, dict):
        return None
    return next((v for k, v in node.items() if _frag(k) == name), None)


def _list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _version(node) -> str | None:
    label, version = _get(node, "label"), _get(node, "version_info")
    return f"{label} {version}".strip() if label else None


def _count(node, name: str) -> int | None:
    value = _get(node, name)
    try:
        return int(value) if value is not None and str(value).strip() != "" else None
    except ValueError:
        return None


def _dataset(node) -> dict:
    characteristic = _get(node, "has_characteristic") or {}
    expression = _get(node, "has_expression") or {}
    return {"label": _get(node, "label"), "components": [c for c in (_get(p, "label") for p in _list(_get(node, "has_part"))) if c],
            "file": _get(node, "source_url"), "figure": _get(expression, "source_url"),
            "rows": _count(characteristic, "number_of_rows"), "columns": _count(characteristic, "number_of_columns")}


def _analysis(doc: dict, rel: str) -> dict:
    part = _get(doc, "has_part") or {}
    procedure = []
    for step in _list(_get(part, "executes")):
        software = _get(step, "part_of") or {}
        procedure.append({"step": _get(step, "label"), "software": _version(software), "language": _version(_get(software, "part_of") or {}),
                          "code": _get(step, "is_implemented_by")})
    return {"file": rel, "description": _get(doc, "label"), "procedure": procedure,
            "inputs": [_dataset(i) for i in _list(_get(part, "has_input"))],
            "outputs": [_dataset(o) for o in _list(_get(part, "has_output"))],
            "implementation": _get(doc, "is_implemented_by")}
