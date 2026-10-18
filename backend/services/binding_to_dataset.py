"""Turn the fdo-consume answers for one object (one ConsumptionResult per panel) into the dataset the frontend renders."""
from __future__ import annotations

import re

from .binding_shapes import (assertions_of, box_range_note, classification_of, claims_of, distributions_of, evidence_of, variable_info,
                             failure_reason, metadata_of, property_of, structure_of)
from .binding_shapes import entities_held_by, footprint_note  # noqa: F401  (re-exported for the adapters)
from .binding_shapes import ROLE_BY_KEY
from .formats import crs_problem, layer_reading, refuse_all
FDO_CONSUME_PACKAGE_NAME = "fdo-consume"


SCHEMA = "fdo-consume-binding/5"


def binding_to_dataset(panels: dict, cfg: dict, source_id: str, evidence: dict | None = None) -> dict:
    """The dashboard dataset for one source from the consumptions of the metadata, claims and map contracts."""
    evidence = evidence or {}
    for name, c in panels.items():
        if c.binding is not None and c.binding.get("schema") != SCHEMA:
            raise ValueError(f"panel {name}: the binding is {c.binding.get('schema')!r}; this dashboard reads {SCHEMA}")
    head = panels["metadata"].binding
    warnings: list[str] = []
    layers, restricted = {}, []
    if panels.get("map") is not None and panels["map"].is_usable:
        layers, restricted, warnings = _layers(panels["map"].binding, cfg)
    claims = _claims(panels["claims"].binding, evidence) if panels.get("claims") is not None and panels["claims"].is_usable else []
    warnings += [f"claim {c['id']}: the asserting record has no such statement; the text shown is a copy in the data object"
                 for c in claims if c["linkChecked"] is False]
    shown = {name: _panel(name, c, layers, claims) for name, c in panels.items()}
    metadata = _metadata(head)
    return {
        "id": source_id, "label": metadata.get("title") or source_id, "sourceType": "fdo-resource",
        "profile": (head["object"]["profiles"] or [None])[0], "fieldSchema": None, "metadata": metadata,
        "claims": claims, "evidence": [_evidence(pid, c) for pid, c in evidence.items()], "layers": layers,
        "views": {"public": {"label": "Public", "layers": [k for k in layers if layers[k]["accessTier"] == "public"]}},
        "allowedViews": ["public"], "figures": [],
        "panels": shown,                                              # what the frontend draws or hides, and why
        "_consumption": {"package": FDO_CONSUME_PACKAGE_NAME, "panels": {**{name: c.summary() for name, c in panels.items()},
                                                       **{"evidence: " + pid.rsplit("/", 1)[-1]: c.summary() for pid, c in evidence.items()}}},
        "diagnostics": {"warnings": warnings, "missingFiles": [], "unmappedOutputs": [], "mode": "fdo-consume-binding",
                        "restricted": restricted, "accessRecord": _summary(panels)},
    }



reason_of = failure_reason
_assertions = assertions_of
_claims, _evidence, _metadata, _distributions, _property, _box_range_note = claims_of, evidence_of, metadata_of, distributions_of, property_of, box_range_note


def _held_by(binding: dict, dataset: dict, kind: str) -> list[dict]:
    return entities_held_by(binding, dataset, kind)


def _structure(binding: dict, dataset: dict, property_name: str | None) -> dict:
    return structure_of(binding, dataset, property_name)


def _classification(binding: dict, dataset: dict, spec: dict) -> tuple[dict, str | None]:
    breaks, note = classification_of(binding, dataset, spec.get("classification", ""))
    return breaks, (note + "; the layer is drawn without class breaks" if note else None)


def _sentence(reason: str | None, name: str) -> str | None:
    """The reader's codes as a sentence for the page header; other reasons pass through."""
    if not reason:
        return reason
    m = re.match(r"A7\.required_metadata (?:FAIL|INDETERMINATE): must absent: (\S+)", reason)
    if m:
        return f"the object does not declare {m.group(1)}, which the {name} panel needs"
    m = re.match(r"V0\.levels_present FAIL: must absent: (\S+)", reason)
    if m:
        return f"the object has no {m.group(1)}"
    return reason


def _panel(name: str, consumption, layers: dict, claims: list) -> dict:
    """Available or not, with the reason: the contract decides; a panel with nothing to show is not drawn either."""
    available, reason = consumption.is_usable, None
    if not available:
        reason = _sentence(reason_of(consumption), name)
        if any(d["code"] == "request.bad_contract" for d in consumption.diagnostics):
            reason = "the panel's contract needs a profile map that is not available here"
        if name == "map" and any(d["code"] == "A7.required_metadata" and d["status"] == "INDETERMINATE"
                                 for d in consumption.diagnostics):   # a must-term the profile does not define
            selected = ((getattr(consumption.record, "semantics", None) or {}).get("profile") or {}).get("selected")
            reason = ("the object declares no profile this dashboard reads, so it was read with the generic RO-Crate map, which defines no map products; its statements are in the metadata panel"
                      if selected in (None, "ro-crate") else
                      "this object's profile describes no map products (it may still list files); its statements are in the metadata panel")
    elif name == "claims" and not claims:
        available, reason = False, "the object carries no claim and no statement"
    elif name == "map" and not layers:
        available, reason = False, "no layer of config/dashboard.yaml matches a map product of the object"
    return {"contract": consumption.record.contract_id, "available": available, "reason": reason,
            "owner": None if available else "object"}


def contract_accepts(distribution: dict) -> bool:
    """On this path the map contract's accepts list decides; fdo-consume's flag says whether it matched."""
    return bool(distribution.get("accepted"))


def _layers(binding: dict, cfg: dict) -> tuple[dict, list, list]:
    """The layers of config/dashboard.yaml that the object's map products fill; the restricted products; warnings."""
    # every map product has a PID; layers are bound to products by it
    datasets = {e["pid"]: e for e in binding["entities"] if e["type"] == "Dataset" and e["pid"]}
    warnings = []
    layers: dict = {}
    for key, spec in cfg["layers"].items():
        dataset = datasets.get(spec["product"])
        if dataset is None:   # Profile attribute TBD: product role; a slot binds by the full set of listed variables when the product PID is another city's
            wanted = set(spec.get("variables", []))
            candidates = [d for d in datasets.values() if wanted and wanted <= set(_variables(binding, d, cfg, spec))]
            if len(candidates) != 1:
                warnings.append(f"layer {key}: no Dataset with the PID {spec['product']} in the object"
                                + (f"; {len(candidates)} datasets provide every configured variable, none chosen" if candidates else " and none provides every configured variable"))
                continue
            dataset = candidates[0]
            warnings.append(f"layer {key}: no Dataset with the PID {spec['product']}; bound by its variables to {dataset['pid']}")
        distributions = _distributions(binding, dataset)
        reading = layer_reading(distributions, contract_accepts, "the map contract")
        crs_note = crs_problem(_structure(binding, dataset, cfg.get("structure_property")).get("crs"))
        if crs_note:
            warnings.append(f"layer {key}: {crs_note}")
            refuse_all(reading, crs_note)
        renderable = next((d for d in distributions if any(r["ok"] for r in d["read"].values())), None)
        tier = "public" if dataset["access"]["state"] == "open" else "private"
        if tier == "private" and not renderable:
            continue
        variables = _variables(binding, dataset, cfg, spec)
        unbound = [k for k in spec.get("variables", []) if k not in variables]
        if unbound:   # a variable without a matching propertyID is not bound
            warnings.append(f"layer {key}: {len(unbound)} of {len(spec['variables'])} configured variables not bound "
                            f"(no propertyID ending in {', '.join(unbound[:4])}{', …' if len(unbound) > 4 else ''})")
        classification, note = _classification(binding, dataset, spec)
        if note:
            warnings.append(f"layer {key}: {note}")
        layers[key] = {
            "type": "vector", "role": ROLE_BY_KEY[key], "label": dataset["fields"].get("name"), "product": dataset["id"], "accessTier": tier,
            "renderingStrategy": reading["renderingStrategy"], "engines": reading["engines"], "unread": reading["unread"],
            "notes": reading["notes"], "sourceLayer": spec.get("sourceLayer"),
            **_structure(binding, dataset, cfg.get("structure_property")),
            "conditionsOfAccess": "; ".join(dataset["access"]["conditions"]) or None,
            "variables": variables, "fields": sorted(set(variables.values())),
            "variableInfo": variable_info(binding, dataset, set(variables.values())),
            "classification": classification, "distributions": distributions,
            "sourceUrl": None, "localPath": reading["localPath"], "style": {},
        }
        box_note = _box_range_note(layers[key]["outputFootprintBbox"])
        if box_note:
            warnings.append(f"layer {key}: {box_note}")
        if not renderable:
            warnings.append(f"layer {key}: no file this dashboard can draw: {reading['unread']['webgl']}")
        elif reading["unread"]["webgl"]:
            warnings.append(f"layer {key}: the WebGL map draws nothing ({reading['unread']['webgl']}); the map without WebGL can")
    records = {e["fields"].get("record") for e in _assertions(binding)}  # asserting records are not products
    restricted = [e["pid"] or e["id"] for e in binding["entities"]
                  if e["type"] == "Dataset" and e["access"]["state"] != "open" and e["id"] not in records
                  and not any(e["id"] in r["holders"] for r in binding["resources"])]
    return layers, restricted, warnings


def _variables(binding: dict, dataset: dict, cfg: dict, spec: dict) -> dict:
    """semantic key -> column name, by the end of each variable's propertyID."""
    # Variable.name is the column, propertyID a resolvable I-ADOPT IRI
    prefix = cfg.get("variable_id_prefix", "")
    by_key = {}
    for v in _held_by(binding, dataset, "Variable"):
        pid = v["fields"].get("property_id") or ""
        if pid.startswith(prefix):
            by_key[pid[len(prefix):]] = v["fields"].get("name")
    return {key: by_key[key] for key in spec["variables"] if key in by_key}


def _summary(panels: dict) -> dict:
    """What fdo-consume said, kept small: per panel the contract, the statuses and the record hash."""
    return {name: {"contract": c.record.contract_id, "statuses": c.statuses, "record_sha256": c.record.record_sha256,
                   "map": (c.binding or {}).get("object", {}).get("map")} for name, c in panels.items()}
