"""Build the synthetic Knowledge Loom records of the Hamburg and Bremen demo runs in the profile 0.1.0 shape, into
test-data/loom-demo and test-data/fdo-cca-demo:
    python scripts/build_loom_records.py --figures <folder> --old-export <folder> --toolbox-root <folder>
Inputs (not in the repository): an earlier Hamburg Loom export (analysis descriptions and code snippets), the two interim
toolbox output folders under --toolbox-root (run parameters), and the figures rendered from the dashboard. The public
products come from the test data. Every value is synthetic; the statements are not findings."""
from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "test-data"
OLD = Path(".")        # set from --old-export
ALLOWED = Path(".")    # set from --toolbox-root
REPLACEMENTS: dict = {}   # set from --replacements
TEMPLATE_CITY = "Hamburg"
PROFILE = "https://knowledgeloom.science/profile/record/0.1.0"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
STAND_IN = "https://example.org/stand-in"

CITIES = {
    "hamburg": {"record": "hamburg-loom-record", "data": "hamburg-cca-profile-demo", "products": ROOT / "fdo-cca-demo" / "objects" / "hamburg-cca-profile-demo" / "public",
                "toolbox": ALLOWED / "hamburg-pmtiles-demo", "label": "Hamburg", "product_pid": f"{STAND_IN}/product/",
                "statements": [("e5b60d07-c048-4f7d-b7c6-9bae9083c7ad", "Synthetic test statement 1 for the Hamburg demo run (not a finding).", ["city", "flooding", "area-a"]),
                               ("c5e8f5df-c589-4dd0-897d-61c215ef2fbd", "Synthetic test statement 2 for the Hamburg demo run (not a finding).", ["city", "vulnerability"]),
                               ("dd84f7ed-6079-4760-8c13-d6d502df127a", "Synthetic test statement 3 for the Hamburg demo run (not a finding).", ["area-a", "area-b", "vulnerability"])]},
    "bremen": {"record": "bremen-loom-record", "data": "bremen-cca-profile-demo", "products": ROOT / "fdo-cca-demo" / "objects" / "bremen-cca-profile-demo" / "public",
               "toolbox": ALLOWED / "bremen-pmtiles-demo", "label": "Bremen", "product_pid": f"{STAND_IN}/bremen/product/",
               "statements": [("1b7c0e2a-5f3d-4a9e-8c21-6d4e9f0a1b2c", "Synthetic test statement 1 for the Bremen demo run (not a finding).", ["city", "flooding", "area-a"]),
                              ("2c8d1f3b-6a4e-4b0f-9d32-7e5f0a1b2c3d", "Synthetic test statement 2 for the Bremen demo run (not a finding).", ["city", "vulnerability"]),
                              ("3d9e2a4c-7b5f-4c1a-ae43-8f6a1b2c3d4e", "Synthetic test statement 3 for the Bremen demo run (not a finding).", ["area-a", "area-b", "vulnerability"])]},
}
CONCEPTS = {"city": ("{label}", "The city of the demo run; values are synthetic.", "https://example.org/concept/{city}"),
            "flooding": ("Pluvial flooding", "Flooding caused by heavy rain.", "https://example.org/concept/pluvial-flooding"),
            "vulnerability": ("Social vulnerability", "The degree to which a population is susceptible to harm from hazards.", "https://example.org/concept/social-vulnerability"),
            "area-a": ("Area A", "A synthetic area label used in the test.", "https://example.org/concept/area-a"),
            "area-b": ("Area B", "A synthetic area label used in the test.", "https://example.org/concept/area-b")}
ANALYSES = [("dcrhs811.json", "analysis-1-risk-hotspots.json", "figures/figure-1-risk-cells.png"),
            ("4yytye5v.json", "analysis-2-risk-assessment.json", "figures/figure-2-vulnerability-background.png"),
            ("2ckp1eat.json", "analysis-3-vulnerability.json", "figures/figure-3-vulnerability-drivers.png")]
FIGURE_NAMES = {"figures/figure-1-risk-cells.png": "Figure 1: pluvial flood risk per cell ({label} demo run; synthetic values)",
                "figures/figure-2-vulnerability-background.png": "Figure 2: risk cells over the social vulnerability background ({label} demo run; synthetic values)",
                "figures/figure-3-vulnerability-drivers.png": "Figure 3: risk cells over the vulnerability drivers ({label} demo run; synthetic values)"}
OUTPUTS = {"outputs/risk_healpix.fgb": ("application/flatgeobuf", "Pluvial flood risk per HEALPix cell (FlatGeobuf)"),
           "outputs/risk_healpix.pmtiles": ("application/vnd.pmtiles", "Pluvial flood risk per HEALPix cell (PMTiles)"),
           "outputs/vulnerability_healpix.fgb": ("application/flatgeobuf", "Social vulnerability per HEALPix cell (FlatGeobuf)"),
           "outputs/vulnerability_healpix.pmtiles": ("application/vnd.pmtiles", "Social vulnerability per HEALPix cell (PMTiles)")}
CODE = {"42zw112u.py": ("code/compute_risk_demo.py", "risk computation call of the demo run"),
        "82t22sw3.py": ("code/compute_vulnerability_demo.py", "vulnerability computation call of the demo run"),
        "1awcm9c2.py": ("code/aggregate_healpix_demo.py", "HEALPix aggregation call of the demo run")}
CONTEXT = ["https://w3id.org/ro/crate/1.3/context",
           {"loom": "https://knowledgeloom.science/", "rdfs": "http://www.w3.org/2000/01/rdf-schema#", "skos": "http://www.w3.org/2004/02/skos/core#",
            "rdfs:label": "http://www.w3.org/2000/01/rdf-schema#label", "skos:definition": "http://www.w3.org/2004/02/skos/core#definition",
            "rdfs:seeAlso": {"@id": "http://www.w3.org/2000/01/rdf-schema#seeAlso", "@type": "@id"},
            "skos:exactMatch": {"@id": "http://www.w3.org/2004/02/skos/core#exactMatch", "@type": "@id"},
            "skos:closeMatch": {"@id": "http://www.w3.org/2004/02/skos/core#closeMatch", "@type": "@id"},
            "concepts": {"@id": "loom:concepts", "@type": "@id"}, "notation": "loom:notation",
            # reserved Loom terms outside profile 0.1.0 (its open question 12, option C): Loom namespace, no 0.1.0 semantics
            "supports": {"@id": "loom:supports", "@type": "@id"}, "components": {"@id": "loom:components", "@type": "@id"}}]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_parameters(toolbox: Path) -> dict:
    crate = {n["@id"]: n for n in json.loads((toolbox / "ro-crate-metadata.json").read_text(encoding="utf-8"))["@graph"]}
    run = crate["#run"]; software = crate[run["instrument"]["@id"]]
    return {"_note": "Input values as recorded by the urban-pfr run that produced the outputs listed with this record. Synthetic demo run; not a real result.",
            "software": {"name": software["name"], "version": software.get("softwareVersion")},
            "run": {"name": run["name"], "endTime": run.get("endTime")},
            "parameters": {p["name"]: p["value"] for p in run.get("additionalProperty", [])}}


def analysis_text(src: Path, city: dict, figure: str) -> str:
    """One analysis description of the template export, rewritten for this record: the local replacement table
    (--replacements, a JSON object of old to new text; the key "__figure_files__" lists the figure names to point at
    this record's figure), the template city replaced by this record's city, then the synthetic provenance."""
    text = src.read_text(encoding="utf-8")
    for a, b in REPLACEMENTS.items():
        if a == "__figure_files__":
            for name in b:
                text = text.replace(name, figure)
        else:
            text = text.replace(a, b)
    text = text.replace(TEMPLATE_CITY, city["label"])
    return json.dumps(_synthetic_provenance(json.loads(text)), ensure_ascii=False, indent=1) + "\n"


INPUT_LABELS = (("ALKIS", "Synthetic building and street inputs of the demo run (restricted tier; not part of this record; no real provider)"),
                ("flood depth", "Synthetic pluvial flood depth layers of the demo run (synthetic values; no real provider)"),
                ("Statistical units", "Synthetic statistical units with demographic indicators of the demo run (synthetic values; no real provider)"),
                ("Streets", "Synthetic street outlines of the demo run (EPSG:25832)"))


def _synthetic_provenance(node, parent_key: str = ""):
    """Provenance of a synthetic record: inputs are named as synthetic without a source; outputs, figures and code
    point at the files in this record; the software is named as the run crate names it, without a repository URL."""
    if isinstance(node, list):
        return [_synthetic_provenance(x, parent_key) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        term = key.split("#")[-1]
        if term == "source_url" and isinstance(value, str):
            if parent_key == "has_input":
                continue                                      # a synthetic input has no source
            name = value.rsplit("/", 1)[-1]
            folder = "figures" if name.endswith(".png") else "code" if name.endswith(".py") else "outputs"
            out[key] = f"{folder}/{name}"
            continue
        if term == "is_implemented_by" and isinstance(value, str) and value.startswith("http"):
            out[key] = f"code/{value.rsplit('/', 1)[-1]}"
            continue
        if term == "has_support_url" and isinstance(value, str) and "github.com" in value:
            continue                                          # the run crate names no repository
        if term == "label" and parent_key == "has_input" and isinstance(value, str):
            out[key] = next((text for mark, text in INPUT_LABELS if mark in value), "Synthetic input of the demo run (no real provider)")
            continue
        if term == "label" and parent_key == "has_part" and isinstance(value, str) and "Streets" in value:
            out[key] = INPUT_LABELS[3][1]
            continue
        if term == "label" and value == "urban_pfr":
            out[key] = "urban-pfr"
            continue
        if term == "version_info" and node.get(key.replace("version_info", "label")) in ("urban_pfr", "urban-pfr"):
            out[key] = SOFTWARE_VERSION
            continue
        out[key] = _synthetic_provenance(value, term if term in ("has_input", "has_part", "has_output") else parent_key)
    return out


SOFTWARE_VERSION = "0.2.1"   # as the toolbox run crate states it; set per run in record()


def record(city: dict, figures: Path) -> None:
    pid = f"{STAND_IN}/{city['record']}"; data_pid = f"{STAND_IN}/{city['data']}"
    target = ROOT / "loom-demo" / "objects" / city["record"]
    shutil.rmtree(target, ignore_errors=True)
    for sub in ("outputs", "analyses", "figures", "code"):
        (target / sub).mkdir(parents=True)
    for name in ("risk_healpix.fgb", "risk_healpix.pmtiles", "vulnerability_healpix.fgb", "vulnerability_healpix.pmtiles"):
        shutil.copyfile(city["products"] / name, target / "outputs" / name)
    params = run_parameters(city["toolbox"])
    global SOFTWARE_VERSION
    SOFTWARE_VERSION = params["software"].get("version") or SOFTWARE_VERSION
    (target / "run-parameters.json").write_text(json.dumps(params, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for old, new in CODE.items():
        shutil.copyfile(OLD / old, target / new[0])
    for i, (src, dst, fig) in enumerate(ANALYSES):
        (target / "analyses" / dst).write_text(analysis_text(OLD / src, city, fig), encoding="utf-8")
        shutil.copyfile(figures / f"{city['record'].split('-')[0]}-{i + 1}-{['risk', 'vulnerability', 'drivers'][i]}.png", target / fig)
    concepts = {key: {"@id": f"#concept-{key}", "@type": ["skos:Concept"], "rdfs:label": label.format(label=city["label"]),
                      "skos:definition": definition, "rdfs:seeAlso": see.format(city=city["record"].split("-")[0])}
                for key, (label, definition, see) in CONCEPTS.items()}
    statements = [{"@id": f"#{uuid}", "@type": ["loom:Statement"], "rdfs:label": text, "notation": "LinguisticStatement",
                   "concepts": [{"@id": f"#concept-{c}"} for c in cs]} for uuid, text, cs in city["statements"]]
    parts = list(OUTPUTS) + ["run-parameters.json"] + [f"analyses/{a[1]}" for a in ANALYSES] + [a[2] for a in ANALYSES] + [c[0] for c in CODE.values()]
    graph = [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "conformsTo": {"@id": "https://w3id.org/ro/crate/1.3"}, "about": {"@id": "./"}},
        {"@id": "./", "@type": "Dataset", "identifier": pid,
         "name": f"Urban pluvial flood risk and social vulnerability for the {city['label']} demo run (synthetic test record)",
         "description": f"A synthetic Knowledge Loom record used only to test software. Three statements about the {city['label']} demo run of the urban-pfr toolbox, "
                        "each supported by an analysis description, a figure and the public HEALPix cell products the run produced. All values are synthetic; the statements are not findings.",
         "author": [{"@id": "https://example.org/person/author-1"}, {"@id": "https://example.org/person/author-2"}],
         "datePublished": datetime.date(2026, 10, 16).isoformat(), "license": {"@id": CC_BY},
         "isBasedOn": [{"@id": "#source-article"}, {"@id": data_pid}], "status": "unpublished",
         "about": ["urban pluvial flooding", "social vulnerability", "climate adaptation"], "publisher": {"@id": "https://example.org/institute"},
         "conformsTo": {"@id": PROFILE}, "hasPart": [{"@id": p} for p in parts]},
        {"@id": PROFILE, "@type": ["CreativeWork", "Profile"], "name": "Knowledge Loom Record RO-Crate Profile 0.1.0 (candidate URI)"},
        {"@id": CC_BY, "@type": "CreativeWork", "name": "CC BY 4.0"},
        {"@id": "https://example.org/institute", "@type": "Organization", "name": "Example Institute", "url": "https://example.org/"},
        {"@id": "https://example.org/person/author-1", "@type": "Person", "name": "Example Author 1", "givenName": "Example", "familyName": "Author 1"},
        {"@id": "https://example.org/person/author-2", "@type": "Person", "name": "Example Author 2", "givenName": "Example", "familyName": "Author 2"},
        {"@id": "#source-article", "@type": "ScholarlyArticle", "name": "Placeholder source article (synthetic; metadata not yet available)", "author": [{"@id": "https://example.org/person/author-1"}]},
        {"@id": data_pid, "@type": "Dataset", "name": f"{city['label']} urban pluvial flood risk and social vulnerability: HEALPix cell products (synthetic Data FDO)",
         "conformsTo": {"@id": "https://w3id.org/cca-crate-profile/0.9"}},
    ] + list(concepts.values()) + statements
    for (src, dst, fig), st in zip(ANALYSES, statements):
        graph.append({"@id": f"analyses/{dst}", "@type": "File", "name": f"Analysis description supporting the statement {st['@id']}", "encodingFormat": "application/ld+json",
                      "supports": [{"@id": st["@id"]}], "components": []})
    for path, (media, name) in OUTPUTS.items():   # the same bytes as the Data FDO's product, said so by size and product PID
        product = city["product_pid"] + ("risk-healpix" if path.startswith("outputs/risk") else "vulnerability-healpix")
        graph.append({"@id": path, "@type": "File", "name": name, "encodingFormat": media, "contentSize": (target / path).stat().st_size, "isBasedOn": {"@id": product}})
    graph.append({"@id": "run-parameters.json", "@type": "File", "name": "Input values recorded for the demo run", "encodingFormat": "application/json"})
    for path, name in FIGURE_NAMES.items():
        graph.append({"@id": path, "@type": "File", "name": name.format(label=city["label"]), "encodingFormat": "image/png"})
    for _, (path, name) in CODE.items():
        graph.append({"@id": path, "@type": "File", "name": name, "encodingFormat": "text/x-python"})
    (target / "ro-crate-metadata.json").write_text(json.dumps({"@context": CONTEXT, "@graph": graph}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    # the sources read the records from fdo-cca-demo as well
    copy = ROOT / "fdo-cca-demo" / "objects" / city["record"]
    shutil.rmtree(copy, ignore_errors=True); shutil.copytree(target, copy)


def indexes() -> None:
    for folder, note in (("loom-demo", "stand-in PIDs; synthetic Knowledge Loom records of the Hamburg and Bremen demo runs in the profile 0.1.0 shape, with the public HEALPix products as outputs"),
                         ("fdo-cca-demo", None)):
        path = ROOT / folder / "pids.json"; pids = json.loads(path.read_text(encoding="utf-8"))
        if note: pids["_note"] = note
        for city in CITIES.values():
            pids[f"{STAND_IN}/{city['record']}"] = {"fixture": city["record"]}
        path.write_text(json.dumps(pids, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        lines = ["# sha256 of each test crate; a test checks this list, update it when a crate changes"]
        for p in sorted((ROOT / folder / "objects").glob("*/ro-crate-metadata.json")):
            lines.append(f"{p.parent.name} {sha256(p)}")
        (ROOT / folder / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--figures", type=Path, required=True)
    ap.add_argument("--old-export", type=Path, required=True)
    ap.add_argument("--toolbox-root", type=Path, required=True)
    ap.add_argument("--replacements", type=Path, help="JSON object of text replacements applied to the template analyses")
    args = ap.parse_args()
    OLD, ALLOWED = args.old_export, args.toolbox_root
    if args.replacements:
        REPLACEMENTS = json.loads(args.replacements.read_text(encoding="utf-8"))
    for city in CITIES.values():
        city["toolbox"] = ALLOWED / city["toolbox"].name
        record(city, args.figures)
    indexes()
    print("records written:", [c["record"] for c in CITIES.values()])
