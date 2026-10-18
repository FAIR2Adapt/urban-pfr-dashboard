"""Shapes the page reads, built from an fdo-consume binding: distributions, classification, structure, metadata,
claims, evidence. Shared by the Data-FDO path (binding_to_dataset) and the composed path (projections)."""
from __future__ import annotations

import json

IN_CRATE = "in-crate:"


def failure_reason(consumption) -> str:
    """One line a reader can act on: the first step that was FAIL or INDETERMINATE, else why the record stopped."""
    for diagnostic in consumption.diagnostics:
        if diagnostic["status"] in ("FAIL", "INDETERMINATE"):
            return f"{diagnostic['code']} {diagnostic['status']}: {diagnostic['message']}"
    return consumption.record.stopped or consumption.record.error or "not usable"


def entities_held_by(binding: dict, dataset: dict, kind: str) -> list[dict]:
    """The entities or resources of one type that the dataset holds."""
    rows = binding["resources"] if kind == "resource" else [e for e in binding["entities"] if e["type"] == kind]
    return [r for r in rows if dataset["id"] in r["holders"]]


def assertions_of(binding: dict) -> list:
    return [e for e in binding["entities"] if "Assertion" in e.get("provides", [])]


# Profile attribute TBD: access tier of a File; derived from the path segment private/ until the profile states it
def distributions_of(binding: dict, dataset: dict) -> list:
    """The dataset's files in the shape the layer code reads; an in-crate path is relative to the object's folder."""
    out = []
    for resource in entities_held_by(binding, dataset, "resource"):
        path = resource["url"][len(IN_CRATE):] if resource["url"].startswith(IN_CRATE) else resource["url"]
        out.append({"path": path, "declared_path": path, "format": resource["media_type"], "contentSize": resource["size"],
                    "formatDeclared": resource.get("declared_media_type"), "formatSource": resource.get("media_type_source"),
                    "download": False, "accessTier": "public" if resource["access"]["state"] == "open" else "private",
                    "accepted": resource["accepted"]})
    return out


# Profile attribute TBD: description and unit of a Variable at level should; the column name is the fallback
def variable_info(binding: dict, dataset: dict, columns) -> dict:
    """column -> {key, description, unit} for the dataset's bound variables, so a legend can title an axis by what the
    object says the column is (schema:description, unitText); the key is the end of the propertyID."""
    out = {}
    for v in entities_held_by(binding, dataset, "Variable"):
        f = v["fields"]
        if f.get("name") in columns:
            out[f["name"]] = {"key": (f.get("property_id") or "").rsplit("/", 1)[-1] or None,
                              "description": f.get("description"), "unit": f.get("unit_text") or f.get("unit_code")}
    return out


def property_of(binding: dict, dataset: dict, name: str) -> str | None:
    """The value of one additionalProperty of the dataset, by its name."""
    for prop in entities_held_by(binding, dataset, "Property"):
        if prop["fields"].get("name") == name:
            return prop["fields"].get("value")
    return None


# Profile attribute TBD: classification term on the Variable (breaks, class count, method, status); read from a JSON string in additionalProperty
def classification_of(binding: dict, dataset: dict, property_name: str) -> tuple[dict, str | None]:
    """Class breaks kept as JSON in an additionalProperty of the dataset (the profile has no legend term)."""
    text = property_of(binding, dataset, property_name) if property_name else None
    if text is None:
        return {}, f"no additionalProperty named {property_name!r} on the product; no class breaks"
    try:
        return json.loads(text), None
    except ValueError:
        return {}, f"the additionalProperty {property_name!r} is not JSON; no class breaks"


# Profile attribute TBD: structured spatial terms (grid, CRS, feature count, bbox axis order); parsed from a string
def structure_of(binding: dict, dataset: dict, property_name: str | None) -> dict:
    """crs, geometry type and cell count from the configured structure property; the footprint from the spatial box."""
    params = (property_of(binding, dataset, property_name) or "") if property_name else ""
    pairs = dict(p.strip().split("=", 1) for p in params.split(";") if "=" in p)
    box = None
    text = dataset["fields"].get("spatial_box")
    if text:
        south, west, north, east = (float(x) for x in text.split())
        box = [west, south, east, north]
    return {"crs": pairs.get("crs"), "geometryType": pairs.get("geometry"),
            "featureCount": int(pairs["cells"]) if pairs.get("cells", "").isdigit() else None, "outputFootprintBbox": box}


def box_range_note(box: list | None) -> str | None:
    """Why a box [west, south, east, north] cannot be a longitude/latitude box, or None."""
    if not box:
        return None
    west, south, east, north = box
    if not (-90 <= south <= north <= 90) or not (-180 <= west <= 180 and -180 <= east <= 180):
        return f"the bounding box {box} is not a longitude/latitude box (axis order?)"
    return None


def footprint_note(box: list, bounds: list, tolerance: float = 0.5) -> tuple[str | None, list | None]:
    """Compare a declared box with a file's own bounds (both [west, south, east, north]): a note, and the box to use."""
    near = lambda a, b: all(abs(x - y) <= tolerance for x, y in zip(a, b))   # noqa: E731
    if near(box, bounds):
        return None, None
    if near([box[1], box[0], box[3], box[2]], bounds):
        return "the declared bounding box is in latitude-longitude order; the file's own bounds are used", list(bounds)
    return f"the declared bounding box {box} differs from the file's own bounds {[round(b, 6) for b in bounds]}", None


def _tier(state: str) -> str:
    return {"open": "public", "restricted": "restricted"}.get(state, "unstated")


def metadata_of(binding: dict) -> dict:
    """The metadata panel's fields from the object's root concepts; no data is read from the crate."""
    obj, fields = binding["object"], binding["object"]["fields"]
    files = [{"id": r["id"], "name": r.get("name") or r["id"], "mediaType": r.get("media_type"), "accessTier": _tier(r["access"]["state"]),
              "conditionsOfAccess": "; ".join(r["access"]["conditions"]) or None, "contentSize": r["size"],
              "download": False, "localPath": None} for r in binding["resources"]]
    return {"title": obj["name"], "description": obj["description"], "datePublished": obj["date"], "status": fields.get("status"),
            "license": obj["licence"], "authors": [{"name": n} for n in (fields.get("author_name") or fields.get("author") or [])], "publisher": {},
            "concepts": [], "statements": [], "files": files,
            "source": {"pid": obj["pid"], "profiles": obj["profiles"], "map": obj["map"], "overlay": obj["overlay"]}}


def claims_of(binding: dict, evidence: dict | None = None) -> list:
    """Entities that provide Assertion, in the shape the evidence panel lists; the link to the asserting record is checked."""
    out = []
    for entity in assertions_of(binding):
        own_text = entity["fields"].get("text") or entity["fields"].get("label")
        record = entity["fields"].get("record") or binding["object"]["pid"]
        text, record_name, checked = own_text, None, None
        text_from = "the assertion itself" if own_text else None
        linked = (evidence or {}).get(record) if record != binding["object"]["pid"] else None
        if linked is not None and linked.binding is not None:
            record_name = linked.binding["object"]["name"]
            fragment = "#" + entity["id"].split("#", 1)[1] if "#" in entity["id"] else None
            stated = {a["id"]: a["fields"].get("label") or a["fields"].get("text") for a in assertions_of(linked.binding)}
            checked = fragment in stated
            if text is None and checked:
                text, text_from = stated[fragment], "the asserting record"
            elif own_text:
                text_from = "a copy in the data object" + ("" if checked else "; the record has no such statement")
        if linked is not None and linked.binding is not None:   # the record's own statement carries the concepts
            stated_entity = next((a for a in assertions_of(linked.binding) if a["id"] == fragment), None)
            concepts = concepts_of(linked.binding, (stated_entity or {}).get("fields", {}).get("concepts") or [])
        else:
            concepts = concepts_of(binding, entity["fields"].get("concepts") or [])
        out.append({"id": entity["id"], "label": text, "record": record, "recordName": record_name, "textFrom": text_from,
                    "about": entity["fields"].get("about"), "concepts": concepts,
                    "linkChecked": checked, "inputs": [], "outputs": []})
    return out


def concepts_of(binding: dict, ids) -> list:
    """The concepts a statement names, with the label and definition the record gives them."""
    ids = ids if isinstance(ids, list) else [ids]
    by_id = {e["id"]: e for e in binding["entities"] if e["type"] == "Concept"}
    return [{"id": i, "label": by_id[i]["fields"].get("label") or i, "definition": by_id[i]["fields"].get("definition"), "seeAlso": by_id[i]["fields"].get("see_also")}
            for i in ids if i in by_id]


def evidence_of(pid: str, consumption) -> dict:
    """One record that asserts claims of this object, as the evidence section lists it."""
    binding = consumption.binding
    if binding is None:
        return {"pid": pid, "usable": False, "why": [d["message"] for d in consumption.diagnostics[:3]]}
    obj, fields = binding["object"], binding["object"]["fields"]
    return {"pid": pid, "usable": True, "title": obj["name"], "status": fields.get("status"), "date": obj["date"],
            "authors": fields.get("author_name") or fields.get("author") or [], "field": fields.get("research_field") or [],
            "statements": [a["fields"].get("label") or a["fields"].get("text") for a in assertions_of(binding)],
            "files": [r["id"] for r in binding["resources"]]}


# The role of each layer slot of config/dashboard.yaml, as the page's renderers name them.
ROLE_BY_KEY = {
    "riskMap": "primary-risk-layer",
    "boundaryOutline": "context-boundary-layer",
    "socialVulnerability": "social-vulnerability-background",
    "vulnerabilityDrivers": "vulnerability-drivers-background",
    "focusAreas": "focus-area-outline",
    "buildingsRisk": "private-building-risk-layer",
    "statUnits": "private-statistical-units-layer",
}
