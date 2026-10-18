"""FDO resource adapter: the dashboard dataset is read from an FDO through fdo-consume, one contract per panel."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import yaml

from ..config import files_root
from ..services.binding_to_dataset import binding_to_dataset, contract_accepts, footprint_note, reason_of
from ..services.formats import crs_problem, layer_reading, refuse_all
from ..services.loom_analyses import analyses_of, files_of, run_parameters_of
from .base import AdapterError, CompositionError, DataSourceAdapter, DatasetLoadError

CONFIG = "config/dashboard.yaml"
LOG_DIR = "logs/fdo-consume"          # git-ignored; what fdo-consume answered, per source


def _write_log(root: Path, source_id: str, consumption: dict) -> None:
    """Keep the fdo-consume answers out of the page; write them to logs/ for whoever debugs the data."""
    import json
    folder = root / LOG_DIR
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{source_id}.json").write_text(json.dumps(consumption, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # a read-only deployment just has no log


def _report_unserved_files(dataset: dict) -> None:
    """Files the object declares that are not in the served folder: listed in the diagnostics; the map panel is off when none is served."""
    missing = dataset["diagnostics"].setdefault("missingFiles", [])
    for key, layer in dataset["layers"].items():
        for d in layer.get("distributions", []):
            if d.get("path") is None and d.get("declared_path"):
                missing.append(d["declared_path"])
                dataset["diagnostics"]["warnings"].append(f"layer {key}: the file {d['declared_path']} is declared by the object but not in the served folder")
    if dataset["layers"] and all(layer.get("localPath") is None for layer in dataset["layers"].values()):
        panel = dataset["panels"].get("map", {})
        if panel.get("available"):
            panel.update({"available": False, "owner": "dashboard",
                          "reason": "the object is consumable, but none of its map files is in the folder this server serves: " + ", ".join(missing[:4])})

def _check_footprints(dataset: dict, root_of) -> None:
    """The declared bounding box of each layer against the bounds its FlatGeobuf file reports (header only);
    `root_of(layer)` gives the folder the layer's files are served from (one per object)."""
    try:
        from pyogrio import read_info
    except ImportError:
        return
    from urllib.parse import unquote
    for key, layer in dataset["layers"].items():
        leaflet = (layer.get("engines") or {}).get("leaflet") or {}
        box, served, package_root = layer.get("outputFootprintBbox"), leaflet.get("path") or "", root_of(layer)
        if not box or leaflet.get("reader") != "fgb-bbox" or "/files/" not in served or package_root is None:
            continue
        rel = unquote(served.split("/files/", 1)[1])
        if layer.get("origin", {}).get("folder"):   # composed layers carry their object's folder in the served path
            rel = rel.split("/", 1)[1] if "/" in rel else rel
        try:
            bounds = [float(b) for b in read_info(str(package_root / rel))["total_bounds"]]
        except Exception:   # an unreadable header: the declared box stays, nothing to compare
            continue
        note, use = footprint_note(box, bounds)
        if note:
            dataset["diagnostics"]["warnings"].append(f"layer {key}: {note}")
        if use:
            layer["outputFootprintBbox"] = use


# Profile attribute TBD: conformsTo in Loom exports; config names the record profile when the export declares none
def _follow_claim_records(claims, rule, consume, fixtures: str, contracts: str | None = None, profile_maps: str | None = None) -> dict:
    """The records that assert this object's claims, by PID, each consumed on its own."""
    # the asserting record is reached by PID and declares its own profile
    if not rule or claims is None or claims.binding is None:
        return {}
    records = sorted({e["fields"].get("record") for e in claims.binding["entities"]
                      if "Assertion" in e.get("provides", []) and str(e["fields"].get("record") or "").startswith(("http://", "https://"))})
    return {pid: consume(pid, rule["contract"], recorded_dir=fixtures, contracts=contracts, profile=rule.get("profile"), profile_maps=profile_maps)
            for pid in records}


def fixture_folders(fixtures: Path) -> dict:
    """{pid: (folder name, folder path)} of a recorded source: the registry that locates each object's files."""
    import json
    registry = json.loads((fixtures / "pids.json").read_text(encoding="utf-8"))
    return {pid: (entry["fixture"], fixtures / "objects" / entry["fixture"]) for pid, entry in registry.items() if isinstance(entry, dict)}


# Profile attribute TBD: role of isBasedOn links; the first link with a usable map contract is taken
def _map_from_record(panels: dict, cfg: dict, consume_for_contracts, fixtures: str, contracts: str | None, maps: str | None):
    """A record that describes no map products but says what it is based on (isBasedOn, by PID) shows the map of
    that object under its own statements. Nothing is copied: the record keeps the statements, the data object keeps
    the products, the page follows the link. Returns (pid, the map consumption of that object) or None."""
    rule = cfg.get("map_from_record")
    if not rule or panels.get("map") is None or panels["map"].is_usable:
        return None
    links = panels["metadata"].binding["object"]["fields"].get(rule.get("relation", "based_on")) or []
    for pid in [str(x) for x in (links if isinstance(links, list) else [links]) if str(x).startswith(("http://", "https://"))]:
        name = cfg["contracts"]["map"]
        answered = consume_for_contracts(pid, [name], recorded_dir=fixtures, contracts=contracts,
                                         profile_overlay=rule.get("profile_overlay"), profile_maps=maps)
        if answered[name].record.outcome == "ok" and answered[name].is_usable:
            return pid, answered[name]
    return None


def _serve_from_object(dataset: dict, pid: str, origin: dict, fixtures: Path, package_root: Path | None) -> None:
    """Layers that come from another object are served from that object's folder under the fixtures, as composed
    layers are; the source must therefore serve `<fixtures>/objects` (a locator without `files`)."""
    folder, _ = fixture_folders(fixtures).get(pid, (None, None))
    dataset["metadata"]["mapFrom"] = {"pid": pid, "title": origin.get("name"), "status": origin["fields"].get("status"), "relation": "isBasedOn"}
    dataset["diagnostics"]["warnings"].append(f"map: the record describes no map products; the map shown is the one of {pid}, "
                                              "which the record declares as isBasedOn")
    served_root = (fixtures / "objects").resolve()
    if folder is None or package_root is None or package_root.resolve() != served_root:
        for layer in dataset["layers"].values():
            layer["localPath"] = None
            for d in layer.get("distributions") or []:
                d["path"] = None
        dataset["diagnostics"]["warnings"].append("map: the files of that object are not served by this source (its locator must name the fixtures and no `files` folder)")
        return
    for layer in dataset["layers"].values():
        if layer.get("localPath"):
            layer["localPath"] = f"{folder}/{layer['localPath']}"
        for d in layer.get("distributions") or []:
            if d.get("path"):
                d["path"] = f"{folder}/{d['path']}"
        layer["origin"] = {"pid": pid, "folder": folder}


def _prefix_own_paths(dataset: dict, folder: str) -> None:
    """A source that serves the fixtures' objects folder: the main object's own files live under its folder."""
    for layer in dataset["layers"].values():
        if layer.get("origin"):
            continue
        if layer.get("localPath"):
            layer["localPath"] = f"{folder}/{layer['localPath']}"
        for d in layer.get("distributions") or []:
            if d.get("path"):
                d["path"] = f"{folder}/{d['path']}"
    for f in dataset["metadata"].get("files") or []:
        f["localPath"] = f"{folder}/{f['id']}"


def attach_record_material(dataset: dict, binding: dict, pid: str, own_folder: str | None, own_path: Path | None, evidence: dict,
                           folders: dict, source_id: str, package_root: Path | None) -> None:
    """What a Knowledge Loom record carries beyond its statements: the analysis descriptions that support them, the
    run parameters, the files. Read from the record's folder; served under the record's folder."""
    def served(folder: str | None, rel: str | None) -> str | None:
        if not rel or package_root is None:
            return None
        full = f"{folder}/{rel}" if folder else rel
        return f"/api/sources/{source_id}/files/{quote(full, safe='/')}" if (package_root / full).is_file() else None

    def with_urls(folder: str | None, analysis: dict) -> dict:
        out = dict(analysis)
        out["inputs"] = [dict(i, fileUrl=served(folder, i.get("file"))) for i in analysis["inputs"]]
        out["outputs"] = [dict(o, fileUrl=served(folder, o.get("file")), figureUrl=served(folder, o.get("figure"))) for o in analysis["outputs"]]
        out["implementationUrl"] = served(folder, analysis.get("implementation"))
        return out

    lookup: dict = {}
    if binding is not None and any(c.get("record") == pid for c in dataset["claims"]):   # the object itself is the record
        lookup.update({k: with_urls(own_folder, v) for k, v in analyses_of(binding, own_path).items()})
        dataset["metadata"]["runParameters"] = run_parameters_of(binding, own_path)
    for entry in dataset["evidence"]:
        consumption = evidence.get(entry["pid"])
        folder, path = folders.get(entry["pid"], (None, None))
        if consumption is None or consumption.binding is None or path is None:
            continue
        entry["files"] = [dict(f, localPath=served(folder, f["id"])) for f in files_of(consumption.binding)]
        entry["runParameters"] = run_parameters_of(consumption.binding, path)
        lookup.update({k: with_urls(folder, v) for k, v in analyses_of(consumption.binding, path).items()})
    for claim in dataset["claims"]:
        key = "#" + claim["id"].split("#", 1)[1] if "#" in claim["id"] else claim["id"]
        claim["analysis"] = lookup.get(key)


# The dashboard's consumer contracts and the draft dashboard additions to the CCA profile, read by fdo-consume from here.
FDO_FOLDERS = {"contracts": "config/fdo/contracts", "profile_maps": "config/fdo/maps"}


def _own_folder(root: Path, locator: dict, key: str) -> str:
    """The folder of the dashboard's contracts or profile maps; a source may name its own."""
    return str((root / (locator.get(key) or FDO_FOLDERS[key])).resolve())


class FDOResourceAdapter(DataSourceAdapter):
    adapter_name = "fdo-resource"

    def load_dataset(self, source_config, context=None):
        context = context or {}
        root = Path(context.get("root", "."))
        locator = source_config.get("locator", {})
        try:
            from fdo_consume import consume, consume_for_contracts
        except ImportError as exc:
            raise AdapterError("fdo-consume is not installed (see README, 'Run it locally')", status=503,
                               details={"adapter": self.adapter_name}) from exc
        cfg = yaml.safe_load((root / CONFIG).read_text(encoding="utf-8"))
        names = cfg["contracts"]
        fixtures = (root / locator.get("fixtures", "")).resolve()
        # contracts and profile maps are the ones fdo-consume ships; a source may name its own folders
        contracts, maps = _own_folder(root, locator, "contracts"), _own_folder(root, locator, "profile_maps")
        # objects without a declared profile: read with the map named in config
        # additions need their own IRI in conformsTo; until then config names the overlay
        # Profile attribute TBD: conformsTo IRI for the dashboard additions; the overlay is named per source until then
        read_as = locator.get("profile")
        answered = consume_for_contracts(locator["pid"], list(names.values()), recorded_dir=str(fixtures), contracts=contracts,
                                         profile=read_as, profile_overlay=locator.get("profile_overlay"), profile_maps=maps)
        panels = {panel: answered[name] for panel, name in names.items()}
        head = panels["metadata"]
        if head.record.outcome != "ok":
            raise DatasetLoadError(f"fdo-consume could not read the object: {head.record.stopped}",
                                   details={"error": head.record.error, "locator": locator, "summary": head.summary()})
        if not head.is_usable:
            raise CompositionError("the object does not give what the metadata panel needs: " + reason_of(head),
                                   details={"summary": head.summary()})
        evidence = _follow_claim_records(panels.get("claims"), cfg.get("evidence"), consume, str(fixtures), contracts, maps)
        linked = _map_from_record(panels, cfg, consume_for_contracts, str(fixtures), contracts, maps)
        own_map = panels["map"]
        if linked:
            panels["map"] = linked[1]
        package_root = files_root(source_config, root)   # the object's folder: the app serves its files from here
        dataset = binding_to_dataset(panels, cfg, source_config.get("id", "fdo"), evidence)
        if linked:
            dataset["_consumption"]["panels"]["map: the record itself"] = own_map.summary()
            _serve_from_object(dataset, linked[0], linked[1].binding["object"], fixtures, package_root)
        folders = fixture_folders(fixtures) if (fixtures / "pids.json").is_file() else {}
        serves_objects = package_root is not None and package_root.resolve() == (fixtures / "objects").resolve()
        own_folder, own_path = folders.get(locator["pid"], (None, None)) if serves_objects else (None, package_root)
        if serves_objects and own_folder:
            _prefix_own_paths(dataset, own_folder)
        attach_record_material(dataset, panels["metadata"].binding, locator["pid"], own_folder, own_path, evidence, folders if serves_objects else {},
                               source_config.get("id", "fdo"), package_root)
        _localize_resource_urls(dataset, source_config.get("id", "fdo"), package_root)
        _check_footprints(dataset, lambda layer: fixtures / "objects" / layer["origin"]["folder"] if layer.get("origin") else package_root)
        _write_log(root, source_config.get("id", "fdo"), dataset.pop("_consumption"))
        _report_unserved_files(dataset)
        # restricted datasets are listed, not served; the request route comes from
        # the profile's access request row, also for a dataset with no file in the crate
        return dataset


def _localize_resource_urls(dataset: dict, source_id: str, package_root: Path) -> None:

    def served(ref):
        if not ref:
            return None
        value = str(ref).strip()
        parsed = urlsplit(value)
        path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
        rel = unquote(path).lstrip("/")
        if rel.startswith("./"):
            rel = rel[2:]
        if not rel or "\\" in rel or ".." in rel.split("/") or not (package_root / rel).is_file():
            return None
        return f"/api/sources/{source_id}/files/{quote(rel, safe='/')}"

    for layer in (dataset.get("layers") or {}).values():
        if isinstance(layer, dict):
            layer["localPath"] = served(layer.get("localPath") or layer.get("sourceUrl"))
            for dist in layer.get("distributions") or []:
                if isinstance(dist, dict) and dist.get("path"):
                    dist["path"] = served(dist["path"])
            if layer.get("distributions"):   # the choice per engine again, now that unserved files have no path
                reading = layer_reading(layer["distributions"], contract_accepts, "the map contract")
                if crs_problem(layer.get("crs")):
                    refuse_all(reading, crs_problem(layer.get("crs")))
                layer.update(reading)

    for f in ((dataset.get("metadata") or {}).get("files") or []):
        if isinstance(f, dict) and f.get("localPath"):
            f["localPath"] = served(f["localPath"])

    for figure in dataset.get("figures") or []:
        if isinstance(figure, dict):
            figure["localPath"] = served(figure.get("localPath") or figure.get("sourceUrl"))

    for claim in dataset.get("claims") or []:
        for output in claim.get("outputs") or []:
            if isinstance(output, dict):
                output["localPath"] = served(output.get("localPath") or output.get("sourceUrl"))
