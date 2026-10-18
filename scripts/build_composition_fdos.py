"""Write the synthetic Dashboard FDO and Plugin FDOs (Dashboard and Plugin entities of the dashboard additions to the CCA profile)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "test-data" / "fdo-cca-demo"   # this repository's fixtures only; another folder needs --output
STAND_IN = "https://example.org/stand-in"
DATA = f"{STAND_IN}/hamburg-cca-profile-demo"
VAR = f"{STAND_IN}/variable"
PROFILE = "https://w3id.org/cca-crate-profile/0.9"
CONTEXT = ["https://w3id.org/ro/crate/1.2/context", {
    "input": "https://bioschemas.org/properties/input", "FormalParameter": "https://bioschemas.org/FormalParameter",
    "valueRequired": "https://schema.org/valueRequired", "valueName": "https://schema.org/valueName",
    "defaultValue": "https://schema.org/defaultValue", "softwareVersion": "https://schema.org/softwareVersion",
    "WebPageElement": "https://schema.org/WebPageElement", "PropertyValueSpecification": "https://schema.org/PropertyValueSpecification",
    "instrument": "https://schema.org/instrument", "object": "https://schema.org/object", "position": "https://schema.org/position"}]
FORMATS = ["application/flatgeobuf", "application/vnd.pmtiles"]

PLUGINS = {   # name: (kind of input, required variables, optional variables, settings {name: default})
    "bivariate-risk-map": ("Dataset", ["risk_mobility_accessibility", "risk_wellbeing"],
                           ["hazard_mobility_accessibility", "hazard_wellbeing", "cell_id", "aggregation_count"],
                           {"classification": "classBreaks", "colorScheme": "yellow-purple"}),
    "single-variable-map": ("Dataset", ["social_vulnerability"], ["svi", "sensitivity", "coping_capacity", "cell_id", "aggregation_count"],
                            {"classification": "classBreaks", "colorScheme": "greys", "exclusiveGroup": "background"}),
    "bivariate-background-map": ("Dataset", ["sensitivity", "coping_capacity"], ["social_vulnerability", "svi", "cell_id", "aggregation_count"],
                                 {"classification": "classBreaks", "colorScheme": "green-blue", "exclusiveGroup": "background"}),
    "claims-list": ("Claim", [], [], {}),
    "metadata-card": ("Object", [], [], {}),   # the whole object, declared as such (no Dataset is selected)
}
ALTERNATIVE = {   # an alternative plugin: the same propertyIDs, its own input variable names and version
    "alternative-risk-map": ("Dataset", [("ma", "risk_mobility_accessibility"), ("wb", "risk_wellbeing")], [("cell", "cell_id")],
                         {"classification": "classBreaks"}, "0.3.0"),
}
NAMES = {   # the panel's name as the dashboard author writes it: the sidebar and the legend show this, nothing else
    "#panel-risk": "Pluvial flood risk (PFR)",
    "#panel-social-vulnerability": "Social vulnerability (SV)",
    "#panel-drivers": "Vulnerability drivers (sensitivity × coping capacity)",
    "#panel-claims": "Claims",
    "#panel-metadata": "Scientific metadata",
}
PANELS = [   # id, plugin, object, position, settings
    ("#panel-risk", "bivariate-risk-map", f"{DATA}#product-risk-healpix", 1, {"colorScheme": "yellow-purple"}),
    ("#panel-social-vulnerability", "single-variable-map", f"{DATA}#product-vulnerability-healpix", 2, {}),
    ("#panel-drivers", "bivariate-background-map", f"{DATA}#product-vulnerability-healpix", 3, {}),
    ("#panel-claims", "claims-list", DATA, 4, {}),
    ("#panel-metadata", "metadata-card", DATA, 5, {}),
]
ALTERNATIVE_PANELS = [   # the same dashboard with the risk panel drawn by the alternative plugin; the other panels unchanged
    ("#panel-risk", "alternative-risk-map", f"{DATA}#product-risk-healpix", 1, {}),
    ("#panel-social-vulnerability", "single-variable-map", f"{DATA}#product-vulnerability-healpix", 2, {}),
    ("#panel-drivers", "bivariate-background-map", f"{DATA}#product-vulnerability-healpix", 3, {}),
    ("#panel-claims", "claims-list", DATA, 4, {}),
    ("#panel-metadata", "metadata-card", DATA, 5, {}),
]


def common(pid: str, name: str, description: str, main: str) -> list:
    """Root entity and the shared context entities of a synthetic crate."""
    return [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}, "about": {"@id": "./"}},
        {"@id": "./", "@type": "Dataset", "name": name, "description": description + " Synthetic test object used for software validation.",
         "identifier": pid, "datePublished": "2026-10-13", "license": {"@id": "https://creativecommons.org/licenses/by/4.0/"},
         "author": {"@id": "#fixture-builder"}, "publisher": {"@id": "https://example.org/institute"},
         "conformsTo": {"@id": PROFILE}, "mainEntity": {"@id": main}, "creativeWorkStatus": "demo: synthetic; no PID minted yet"},
        {"@id": PROFILE, "@type": ["CreativeWork", "Profile"], "name": "CCA-Crate profile 0.9 (test object)",
         "description": "Dashboard terms follow the draft dashboard additions to the CCA profile."},
        {"@id": "https://creativecommons.org/licenses/by/4.0/", "@type": "CreativeWork", "name": "CC BY 4.0"},
        {"@id": "#fixture-builder", "@type": "Organization", "name": "Test fixture builder (synthetic object)"},
        {"@id": "https://example.org/institute", "@type": "Organization", "name": "Example Institute", "url": "https://example.org/"},
    ]


def plugin_crate(name: str) -> tuple[str, dict]:
    kind, required, optional, settings = PLUGINS[name]
    pid = f"{STAND_IN}/plugin/{name}"
    graph = common(pid, f"Dashboard plugin: {name} (synthetic)", f"A view panel that draws {name.replace('-', ' ')}.", "#plugin")
    inputs = []
    for i, (var_names, req) in enumerate(((required, True), (optional, False))):
        if not var_names and i == 1:
            continue
        iid = "#input-main" if req else "#input-optional"
        node = {"@id": iid, "@type": "FormalParameter", "name": "main" if req else "optional", "additionalType": kind,
                "valueRequired": req, "encodingFormat": FORMATS if kind == "Dataset" else [],
                "variableMeasured": [{"@id": f"#var-{v}"} for v in var_names]}
        if kind == "Dataset":
            node["conformsTo"] = {"@id": f"{STAND_IN}/shape/map-input"}
        inputs.append(node)
        for v in var_names:
            graph.append({"@id": f"#var-{v}", "@type": "PropertyValue", "name": v, "propertyID": {"@id": f"{VAR}/{v}"}})
    graph += inputs
    for sname, default in settings.items():
        graph.append({"@id": f"#setting-{sname}", "@type": "PropertyValueSpecification", "valueName": sname, "defaultValue": default,
                      "description": f"setting {sname} of {name}"})
    graph.append({"@id": "#plugin", "@type": "SoftwareApplication", "name": name, "additionalType": "view panel",
                  "url": f"{STAND_IN}/plugin/{name}/panel.js", "softwareVersion": "1.0.0",
                  "softwareRequirements": "composer-interface 0.1", "input": [{"@id": n["@id"]} for n in inputs],
                  "additionalProperty": [{"@id": f"#setting-{s}"} for s in settings]})
    return pid, {"@context": CONTEXT, "@graph": graph}


def alternative_plugin_crate(name: str) -> tuple[str, dict]:
    kind, required, optional, settings, version = ALTERNATIVE[name]
    pid = f"{STAND_IN}/plugin/{name}"
    graph = common(pid, f"Dashboard plugin: {name} (synthetic, alternative implementation)", "A bivariate risk map from an alternative implementation.", "#plugin")
    inputs = []
    for iid, pairs, req in (("#input-main", required, True), ("#input-optional", optional, False)):
        inputs.append({"@id": iid, "@type": "FormalParameter", "name": "main" if req else "optional", "additionalType": kind, "valueRequired": req,
                       "encodingFormat": FORMATS, "variableMeasured": [{"@id": f"#var-{n}"} for n, _ in pairs]})
        for n, v in pairs:
            graph.append({"@id": f"#var-{n}", "@type": "PropertyValue", "name": n, "propertyID": {"@id": f"{VAR}/{v}"}})
    graph += inputs
    for sname, default in settings.items():
        graph.append({"@id": f"#setting-{sname}", "@type": "PropertyValueSpecification", "valueName": sname, "defaultValue": default})
    graph.append({"@id": "#plugin", "@type": "SoftwareApplication", "name": name, "additionalType": "view panel", "url": f"{STAND_IN}/plugin/{name}/panel.js",
                  "softwareVersion": version, "input": [{"@id": n["@id"]} for n in inputs], "additionalProperty": [{"@id": f"#setting-{s}"} for s in settings]})
    return pid, {"@context": CONTEXT, "@graph": graph}


def alternative_dashboard_crate() -> tuple[str, dict]:
    """A second composition: the same five panels, the risk panel drawn by the alternative plugin."""
    pid = f"{STAND_IN}/hamburg-dashboard-alternative"
    graph = common(pid, "Hamburg urban pluvial flood risk dashboard, risk panel by an alternative plugin (synthetic composition)",
                   "Five panels over the Hamburg Data FDO; the risk panel names an alternative risk plugin.", "#dashboard")
    parts = []
    for pid_panel, plugin, obj, position, _ in ALTERNATIVE_PANELS:
        graph.append({"@id": pid_panel, "@type": "WebPageElement", "name": NAMES[pid_panel],
                      "instrument": {"@id": f"{STAND_IN}/plugin/{plugin}"}, "object": {"@id": obj}, "position": position})
        parts.append({"@id": pid_panel})
    graph.append({"@id": "#dashboard", "@type": "CreativeWork", "name": "Hamburg urban pluvial flood risk (alternative risk plugin)", "about": {"@id": DATA}, "hasPart": parts})
    return pid, {"@context": CONTEXT, "@graph": graph}


def dashboard_crate() -> tuple[str, dict]:
    pid = f"{STAND_IN}/hamburg-dashboard"
    graph = common(pid, "Hamburg urban pluvial flood risk dashboard (synthetic composition)",
                   "Five panels over the Hamburg Data FDO and its Knowledge Loom record.", "#dashboard")
    parts = []
    for pid_panel, plugin, obj, position, settings in PANELS:
        node = {"@id": pid_panel, "@type": "WebPageElement", "name": NAMES[pid_panel],
                "instrument": {"@id": f"{STAND_IN}/plugin/{plugin}"}, "object": {"@id": obj}, "position": position}
        if settings:
            node["additionalProperty"] = [{"@id": f"{pid_panel}-{s}"} for s in settings]
            for s, v in settings.items():
                graph.append({"@id": f"{pid_panel}-{s}", "@type": "PropertyValue", "name": s, "value": v})
        graph.append(node)
        parts.append({"@id": pid_panel})
    graph.append({"@id": "styles.css", "@type": "File", "name": "dashboard stylesheet (not a panel)", "encodingFormat": "text/css"})
    parts.append({"@id": "styles.css"})
    graph.append({"@id": "#dashboard", "@type": "CreativeWork", "name": "Hamburg urban pluvial flood risk", "about": {"@id": DATA},
                  "hasPart": parts, "additionalProperty": [{"@id": "#style-primary"}]})
    graph.append({"@id": "#style-primary", "@type": "PropertyValue", "name": "primaryColor", "value": "#1f5f8b"})
    return pid, {"@context": CONTEXT, "@graph": graph}


def write_all(targets: list) -> None:
    crates = [plugin_crate(n) for n in PLUGINS] + [alternative_plugin_crate(n) for n in ALTERNATIVE] + [dashboard_crate(), alternative_dashboard_crate()]
    for target in targets:
        pids = json.loads((target / "pids.json").read_text(encoding="utf-8"))
        for pid, crate in crates:
            folder = target / "objects" / pid.rsplit("/", 1)[-1] if "plugin" not in pid else target / "objects" / ("plugin-" + pid.rsplit("/", 1)[-1])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "ro-crate-metadata.json").write_text(json.dumps(crate, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            if pid.endswith("/hamburg-dashboard"):   # the stylesheet the dashboard lists as a part that is not a panel
                (folder / "styles.css").write_text("/* synthetic dashboard stylesheet: a part of the Dashboard FDO that is not a panel */\n", encoding="utf-8")
            pids[pid] = {"fixture": folder.name}
        (target / "pids.json").write_text(json.dumps(pids, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        lines, seen = [], set()
        for line in (target / "checksums.txt").read_text(encoding="utf-8").splitlines():
            m = re.match(r"^(\S+) [0-9a-f]{64}$", line)
            if not m:
                lines.append(line)
                continue
            seen.add(m.group(1))
            lines.append(f"{m.group(1)} {hashlib.sha256((target / 'objects' / m.group(1) / 'ro-crate-metadata.json').read_bytes()).hexdigest()}")
        for pid, _ in crates:
            name = ("plugin-" if "plugin" in pid else "") + pid.rsplit("/", 1)[-1]
            if name not in seen:
                lines.append(f"{name} {hashlib.sha256((target / 'objects' / name / 'ro-crate-metadata.json').read_bytes()).hexdigest()}")
        (target / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(target, "->", len(crates), "composition objects")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write the synthetic Dashboard FDO and Plugin FDOs into a recorded-fixtures folder.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="fixtures folder with pids.json and checksums.txt (default: this repository's)")
    sys.exit(write_all([Path(parser.parse_args().output)]))
