"""Build the synthetic Bremen Data FDO and Dashboard FDO from a Bremen toolbox output folder (interim profile), with the
Hamburg objects as template: python scripts/build_bremen_objects.py <bremen toolbox folder>
Values stay synthetic; the payload files are copied byte for byte."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "test-data" / "fdo-cca-demo"
OBJECTS = ROOT / "objects"
HAMBURG = "https://example.org/stand-in/hamburg-cca-profile-demo"
BREMEN = "https://example.org/stand-in/bremen-cca-profile-demo"
HAMBURG_RECORD = "https://example.org/stand-in/hamburg-loom-record"
BREMEN_RECORD = "https://example.org/stand-in/bremen-loom-record"
# the claims of the Bremen object are the statements of the Bremen Loom record (tools/make_loom_records.py), in order
STATEMENTS = {"e5b60d07-c048-4f7d-b7c6-9bae9083c7ad": "1b7c0e2a-5f3d-4a9e-8c21-6d4e9f0a1b2c",
              "c5e8f5df-c589-4dd0-897d-61c215ef2fbd": "2c8d1f3b-6a4e-4b0f-9d32-7e5f0a1b2c3d",
              "dd84f7ed-6079-4760-8c13-d6d502df127a": "3d9e2a4c-7b5f-4c1a-ae43-8f6a1b2c3d4e"}
PRODUCT = "https://example.org/stand-in/product/"
BREMEN_PRODUCT = "https://example.org/stand-in/bremen/product/"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def data_fdo(toolbox: Path) -> None:
    source = {n["@id"]: n for n in load(toolbox / "ro-crate-metadata.json")["@graph"]}
    crate = copy.deepcopy(load(OBJECTS / "hamburg-cca-profile-demo" / "ro-crate-metadata.json"))
    box = source["#product-risk-healpix"]["outputFootprintBbox"]          # minx, miny, maxx, maxy
    cells = source["#product-risk-healpix"]["featureCount"]
    graph = []
    for node in crate["@graph"]:
        nid = node["@id"]
        if nid in ("#product-buildings-risk", "http://publications.europa.eu/resource/authority/access-right/RESTRICTED"):
            continue
        if nid == "./":
            node["name"] = "Bremen urban pluvial flood risk and social vulnerability: HEALPix cell products (demo)"
            node["description"] = ("Two public map products of the urban-pfr toolbox for Bremen, aggregated to HEALPix equal-area cells. "
                                   "Their claims are the statements of a separate Knowledge Loom record, linked by PID, not copied. "
                                   "Demo data: values are synthetic; shapes, variables and formats are synthetic test material.")
            node["datePublished"] = "2026-10-15"
            node["dateCreated"] = source["#run"]["endTime"][:10]
            node["spatialCoverage"] = {"@id": "#place-bremen-extent"}
            node["hasPart"] = [{"@id": "#product-risk-healpix"}, {"@id": "#product-vulnerability-healpix"}]
        elif nid == "#place-hamburg-extent":
            node = {"@id": "#place-bremen-extent", "@type": "Place", "name": "Bremen (demo extent)", "geo": {"@id": "#bbox-bremen-extent"}}
        elif nid == "#bbox-hamburg-extent":
            node = {"@id": "#bbox-bremen-extent", "@type": "GeoShape", "box": f"{box[1]} {box[0]} {box[3]} {box[2]}"}
        elif nid == "#spatial-structure-parameters":
            node["value"] = f"healpix_depth=15; crs=EPSG:4326; geometry=Polygon; cells={cells}"
        elif nid.startswith("#classification-"):
            breaks = {k: v for k, v in source[nid].items() if k in ("method", "thresholdStatus") or k.startswith("breaks_")}
            breaks["method"] = breaks["method"].replace(" per paper", "")   # the method text names no publication; values are synthetic
            node["value"] = json.dumps(breaks)
        elif nid.startswith("#product-"):
            node["identifier"] = BREMEN_PRODUCT + nid[len("#product-"):]
            node["spatialCoverage"] = {"@id": "#place-bremen-extent"}
        elif nid.startswith("public/"):
            file = toolbox / nid
            node["contentSize"] = file.stat().st_size
            node["sha256"] = sha256(file)
        elif nid == "#run":
            node["name"] = "demo fixture generation (urban-pfr 0.2.1)"
            node["endTime"] = source["#run"]["endTime"]
            params = {p["name"]: p["value"] for p in source["#run"].get("additionalProperty", [])}
            node["description"] = "; ".join([params.get("config_file", "")] + [f"{k}={params[k]}" for k in ("aggregation", "healpix_depth", "min_buildings_k", "synthetic", "synthesis_seed") if k in params]).lower()
        text = json.dumps(node).replace(HAMBURG, BREMEN).replace(HAMBURG_RECORD, BREMEN_RECORD).replace("Hamburg demo run", "Bremen demo run")
        for old, new in STATEMENTS.items():
            text = text.replace(old, new)
        graph.append(json.loads(text))
    crate["@graph"] = graph
    target = OBJECTS / "bremen-cca-profile-demo"
    save(target / "ro-crate-metadata.json", crate)
    (target / "public").mkdir(exist_ok=True)
    for nid in ("public/risk_healpix.fgb", "public/risk_healpix.pmtiles", "public/vulnerability_healpix.fgb", "public/vulnerability_healpix.pmtiles"):
        shutil.copyfile(toolbox / nid, target / nid)


def dashboard_fdo() -> None:
    crate = copy.deepcopy(load(OBJECTS / "hamburg-dashboard" / "ro-crate-metadata.json"))
    graph = []
    for node in crate["@graph"]:
        nid = node["@id"]
        text = json.dumps(node).replace(HAMBURG, BREMEN)
        node = json.loads(text)
        if nid == "./":
            node["name"] = "Bremen urban pluvial flood risk dashboard (synthetic composition)"
            node["description"] = "Five panels over the Bremen Data FDO and its Knowledge Loom record. Synthetic test object used for software validation."
            node["identifier"] = "https://example.org/stand-in/bremen-dashboard"
            node["datePublished"] = "2026-10-15"
        elif nid == "#dashboard":
            node["name"] = "Bremen urban pluvial flood risk"
        graph.append(node)
    crate["@graph"] = graph
    target = OBJECTS / "bremen-dashboard"
    save(target / "ro-crate-metadata.json", crate)
    shutil.copyfile(OBJECTS / "hamburg-dashboard" / "styles.css", target / "styles.css")


def index_and_checksums() -> None:
    pids = load(ROOT / "pids.json")
    pids["_note"] = ("stand-in PIDs; synthetic objects: the Hamburg and Bremen Data FDOs in the CCA profile with the dashboard additions, "
                     "their Knowledge Loom records, the Plugin FDOs and the Dashboard FDOs that compose them")
    pids[BREMEN] = {"fixture": "bremen-cca-profile-demo"}
    pids["https://example.org/stand-in/bremen-dashboard"] = {"fixture": "bremen-dashboard"}
    save(ROOT / "pids.json", pids)
    lines = ["# sha256 of each test crate; a test checks this list, update it when a crate changes"]
    for path in sorted(OBJECTS.glob("*/ro-crate-metadata.json")):
        lines.append(f"{path.parent.name} {sha256(path)}")
    (ROOT / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    data_fdo(Path(sys.argv[1]))
    dashboard_fdo()
    index_and_checksums()
    print("built", sorted(p.name for p in OBJECTS.iterdir()))
