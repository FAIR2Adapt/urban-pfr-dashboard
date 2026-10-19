"""The composer: a Dashboard FDO in, a plan out; exact binding, the plan's published shape, and what the composed source draws."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.composer import composer as composer_module  # noqa: E402
from backend.composer.binder import ExactSemanticBinder  # noqa: E402
from backend.composer.composer import CONTRACTS, compose  # noqa: E402
from backend.composer.models import DASHBOARD_PLAN_SCHEMA_ID, FAIL, PASS, PARTIAL, worse  # noqa: E402
from backend.composer.plan_from_config import plan_from_config  # noqa: E402
from backend.composer.registry import load_registry, resolve_renderer  # noqa: E402
from backend.composer.session import CompositionSession  # noqa: E402
from backend.config import load_config  # noqa: E402

FIXTURES = ROOT / "test-data" / "fdo-cca-demo"
DASH = "https://example.org/stand-in/hamburg-dashboard"
ALTERNATIVE = "https://example.org/stand-in/hamburg-dashboard-alternative"
DATA = "https://example.org/stand-in/hamburg-cca-profile-demo"
LOOM = "https://example.org/stand-in/hamburg-loom-record"
OVERLAY = "cca-dashboard-additions"
REGISTRY = load_registry(ROOT / "config" / "renderers.yaml")

sys.path.insert(0, str(ROOT / "tests"))
from support import HAVE_FDO_CONSUME, PROFILE_MAPS  # noqa: E402
from support import CONTRACTS as CONTRACT_FOLDER  # noqa: E402


def crate(folder: Path, name: str) -> dict:
    return json.loads((folder / "objects" / name / "ro-crate-metadata.json").read_text(encoding="utf-8"))


def save(folder: Path, name: str, data: dict) -> None:
    (folder / "objects" / name / "ro-crate-metadata.json").write_text(json.dumps(data), encoding="utf-8")


def node(data: dict, ident: str) -> dict:
    return next(e for e in data["@graph"] if e["@id"] == ident)


def session_for(folder: Path, assumed_profiles: dict | None = None) -> CompositionSession:
    from fdo_consume import consume
    return CompositionSession(consume, str(folder), CONTRACT_FOLDER, PROFILE_MAPS, overlay=OVERLAY, assumed_profiles=assumed_profiles)


def composed(mutate=None, registry=REGISTRY, assumed_profiles=None, pid=DASH):
    """compose() on a copy of the recorded objects after `mutate(folder)`; returns (plan, session)."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "fixtures"
        shutil.copytree(FIXTURES, folder, ignore=shutil.ignore_patterns("public"))
        if mutate:
            mutate(folder)
        session = session_for(folder, assumed_profiles)
        return compose(pid, registry, session), session


def by_id(plan) -> dict:
    return {p.id: p for p in plan.panels}


def entity(ident: str, etype: str, holders: list, fields: dict | None = None, access: str = "open", provides: list | None = None) -> dict:
    return {"id": ident, "type": etype, "holders": holders, "fields": fields or {}, "provides": provides or [],
            "access": {"state": access, "conditions": []}, "pid": None}


def plugin_binding(inputs: list) -> dict:
    """A plugin description by hand: inputs = [(name, kind, required, [(variable name, propertyID)])]."""
    entities = [entity("#plugin", "Plugin", ["./"], {"name": "p", "version": "1.0.0"})]
    for name, kind, required, variables in inputs:
        entities.append(entity(f"#in-{name}", "Input", ["#plugin"], {"name": name, "kind": kind, "required": required, "formats": []}))
        for var_name, iri in variables:
            entities.append(entity(f"#in-{name}-{var_name}", "Variable", [f"#in-{name}"], {"name": var_name, "property_id": iri}))
    return {"object": {"pid": "plugin", "name": "p", "access": {"state": "open", "conditions": []}}, "entities": entities, "resources": []}


def target_binding(datasets: list) -> dict:
    """A target by hand: datasets = [(id, access, [(column, propertyID)])]."""
    entities = []
    for ident, access, variables in datasets:
        entities.append(entity(ident, "Dataset", ["./"], {"name": ident}, access))
        for column, iri in variables:
            entities.append(entity(f"{ident}-{column}", "Variable", [ident], {"name": column, "property_id": iri}, access))
    return {"object": {"pid": "target", "name": "t", "access": {"state": "open", "conditions": []}}, "entities": entities, "resources": []}


class BinderTest(unittest.TestCase):
    def test_two_equal_candidates_stay_indeterminate_never_first_wins(self):
        plugin = plugin_binding([("main", "Dataset", True, [("v1", "iri:v1")])])
        target = target_binding([("#d1", "open", [("c", "iri:v1")]), ("#d2", "open", [("c", "iri:v1")])])
        result = ExactSemanticBinder().bind(plugin, target, None)
        self.assertEqual(result.status, "INDETERMINATE")
        self.assertEqual(result.inputs, [])

    def test_the_binder_does_not_write_into_the_fdo_consume_binding(self):
        plugin = plugin_binding([("main", "Dataset", True, [("v1", "iri:v1")])])
        target = target_binding([("#d", "open", [("col1", "iri:v1")])])
        before = json.dumps(target, sort_keys=True)
        ExactSemanticBinder().bind(plugin, target, None)
        self.assertEqual(json.dumps(target, sort_keys=True), before)


class RegistryTest(unittest.TestCase):
    def test_another_plugin_version_is_not_run(self):
        self.assertEqual(resolve_renderer(REGISTRY, "https://example.org/stand-in/plugin/bivariate-risk-map", "1.0.0").status, PASS)
        self.assertEqual(resolve_renderer(REGISTRY, "https://example.org/stand-in/plugin/bivariate-risk-map", "2.0.0").status, FAIL)
        self.assertEqual(resolve_renderer(REGISTRY, "https://example.org/stand-in/plugin/bivariate-risk-map", None).status, "INDETERMINATE")
        self.assertIsNone(resolve_renderer(REGISTRY, "https://example.org/stand-in/plugin/none", "1.0.0"))


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class BoundaryTest(unittest.TestCase):
    def test_every_composer_contract_is_in_the_dashboard_folder(self):
        from fdo_consume.contracts import load_contract
        for name in CONTRACTS:
            self.assertEqual(load_contract(name, folder=CONTRACT_FOLDER, profile_maps=PROFILE_MAPS)["contract_id"], name)

    def test_the_overlay_is_the_dashboards_and_provides_the_composition_concepts(self):
        from fdo_consume.profiles import load_maps
        self.assertNotIn(OVERLAY, load_maps(None))
        spec = load_maps(PROFILE_MAPS)[OVERLAY]
        self.assertTrue(spec.get("overlay"))
        self.assertLessEqual({"Dashboard", "Panel", "Plugin", "Input", "Setting"}, set(spec["entities"]))

    def test_the_composer_opens_no_crate_and_loads_no_plugin_code(self):
        source = Path(composer_module.__file__).read_text(encoding="utf-8")
        for forbidden in ("ro-crate-metadata", "open(", "urlopen", "requests.", "@graph"):
            self.assertNotIn(forbidden, source)
        for name in ("hamburg", "risk_mobility", "PFRMA", "riskMap"):
            self.assertNotIn(name, source)


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class ComposerTest(unittest.TestCase):
    def test_a_restricted_dataset_reports_access_and_composition_apart(self):
        def restricted(folder):
            c = crate(folder, "hamburg-dashboard")
            node(c, "#panel-risk")["object"] = {"@id": DATA + "#product-buildings-risk"}
            save(folder, "hamburg-dashboard", c)
        plan, _ = composed(restricted)
        risk = by_id(plan)["#panel-risk"]
        # the restricted product carries no file in an accepted format: that is a composition FAIL; the restriction is
        # reported beside it, it neither causes nor hides the failure
        self.assertEqual((risk.status, risk.access, risk.drawable), (FAIL, "restricted", False))
        self.assertEqual(risk.input("main").entity, "#product-buildings-risk")
        self.assertLessEqual({"bind.no_format", "bind.restricted"}, set(risk.codes))
        self.assertNotIn("RESTRICTED", risk.status)

    def test_a_product_without_an_access_statement_is_unknown_and_not_drawn(self):
        def unstated(folder):
            data = crate(folder, "hamburg-cca-profile-demo")
            node(data, "#product-risk-healpix").pop("accessRights", None)
            save(folder, "hamburg-cca-profile-demo", data)
        risk = by_id(composed(unstated)[0])["#panel-risk"]
        self.assertEqual(risk.access, "unknown")
        self.assertFalse(risk.drawable)

    def test_a_setting_the_panel_states_twice_fails_the_panel(self):
        def twice(folder):
            data = crate(folder, "hamburg-dashboard")
            data["@graph"].append({"@id": "#panel-risk-colorScheme-2", "@type": "PropertyValue", "name": "colorScheme", "value": "greys"})
            node(data, "#panel-risk")["additionalProperty"].append({"@id": "#panel-risk-colorScheme-2"})
            save(folder, "hamburg-dashboard", data)
        risk = by_id(composed(twice)[0])["#panel-risk"]
        self.assertEqual(risk.status, FAIL)
        self.assertIn("panel.duplicate_setting", [d.code for d in risk.diagnostics])

    def test_input_values_are_read_strictly(self):
        def odd(folder):
            data = crate(folder, "plugin-bivariate-risk-map")
            node(data, "#input-optional")["valueRequired"] = "maybe"
            save(folder, "plugin-bivariate-risk-map", data)
        risk = by_id(composed(odd)[0])["#panel-risk"]
        self.assertIn("plugin.input_required_unreadable", [d.code for d in risk.diagnostics])
        self.assertTrue(next(i for i in risk.inputs if i.name == "optional").required)
        plugin = {"entities": [{"id": "#i", "type": "Input", "holders": [], "provides": [],
                                "fields": {"name": "main", "kind": "Dataset", "formats": ["application/flatgeobuf", 5]}}], "resources": []}
        target = {"object": {"pid": "x", "access": {"state": "open"}}, "entities": [], "resources": []}
        result = ExactSemanticBinder().bind(plugin, target, None)
        self.assertIn("plugin.input_format_unreadable", [d.code for d in result.diagnostics])

    def test_an_input_without_a_kind_is_not_bound(self):
        def no_kind(folder):
            data = crate(folder, "plugin-bivariate-risk-map")
            node(data, "#input-main").pop("additionalType")
            save(folder, "plugin-bivariate-risk-map", data)
        risk = by_id(composed(no_kind)[0])["#panel-risk"]
        self.assertEqual(risk.status, FAIL)
        self.assertIn("plugin.input_incomplete", [d.code for d in risk.diagnostics])

    def test_a_matched_variable_without_a_column_name_fails_the_input(self):
        def unnamed(folder):
            data = crate(folder, "hamburg-cca-profile-demo")
            for e in data["@graph"]:
                if e.get("@type") == "PropertyValue" and (e.get("propertyID") or {}).get("@id", "").endswith("/risk_wellbeing"):
                    e.pop("name", None)
            save(folder, "hamburg-cca-profile-demo", data)
        risk = by_id(composed(unnamed)[0])["#panel-risk"]
        self.assertEqual(risk.status, FAIL)
        self.assertIn("bind.no_column", [d.code for d in risk.diagnostics])

    def test_the_same_inputs_give_the_same_plan(self):
        first, second = composed()[0].to_dict(), composed()[0].to_dict()
        first["evidence"].pop("compose_ms"); second["evidence"].pop("compose_ms")
        self.assertEqual(first, second)

    def test_the_plan_from_the_dashboard_fdo_agrees_with_the_config_path(self):
        import yaml
        plan, session = composed()
        dashboard_config = yaml.safe_load((ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8"))
        old = {p.renderer.renderer_id: p for p in plan_from_config(DATA, session.binding_of(DATA), dashboard_config, REGISTRY).panels}
        new = {p.renderer.renderer_id: p for p in plan.panels if p.renderer.renderer_id in old}
        self.assertEqual(sorted(old), sorted(new))
        for slot, p in new.items():
            self.assertEqual(p.input("main").entity, old[slot].input("main").entity, slot)
            for key, column in p.input("main").variables.items():
                self.assertEqual(column, old[slot].input("main").variables[key], f"{slot}.{key}")
            self.assertEqual(p.settings["classification"], old[slot].settings["classification"])

    def test_the_plan_matches_the_golden_file(self):
        for pid, name in ((DASH, "plan.json"), (ALTERNATIVE, "plan-alternative.json")):
            plan, _ = composed(pid=pid)
            got = plan.to_dict(); got["evidence"].pop("compose_ms")
            want = json.loads((FIXTURES / "expected" / name).read_text(encoding="utf-8"))
            self.assertEqual(got, want, name)

    def test_the_plan_has_the_published_shape(self):
        schema = json.loads((ROOT / "backend" / "composer" / "plan.schema.json").read_text(encoding="utf-8"))
        plan_dict = composed()[0].to_dict()
        self.assertEqual(plan_dict["schema"], DASHBOARD_PLAN_SCHEMA_ID)
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed; the CI job installs it and validates the plan")
        jsonschema.validate(plan_dict, schema)


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class FdoDashboardSourceTest(unittest.TestCase):
    SAME = ("accessTier", "renderingStrategy", "sourceLayer", "crs", "geometryType", "featureCount", "outputFootprintBbox", "fields", "classification")

    PAIRS = {"riskMap": "panel-risk", "socialVulnerability": "panel-social-vulnerability", "vulnerabilityDrivers": "panel-drivers"}

    def dataset(self, source_id: str) -> dict:
        from backend.api import routes
        return routes.load_dataset_dict(load_config(ROOT), source_id)

    def composed_dataset(self, mutate=None, source_id: str = "fdo-dashboard-demo") -> dict:
        from backend.adapters.registry import get_adapter
        config = load_config(ROOT)
        source = next(s for s in config.sources if s["id"] == source_id)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "fixtures"
            shutil.copytree(FIXTURES, folder, ignore=shutil.ignore_patterns("public"))
            (folder / "objects" / "hamburg-cca-profile-demo" / "public").symlink_to((FIXTURES / "objects" / "hamburg-cca-profile-demo" / "public").resolve(), target_is_directory=True)
            if mutate:
                mutate(folder)
            return get_adapter("fdo-dashboard").load_dataset(dict(source, locator=dict(source["locator"], fixtures=str(folder))),
                                                             {"root": config.root, "deployment": "public"})

    def test_the_composed_source_draws_what_the_data_fdo_source_draws(self):
        old, new = self.dataset("fdo-cca-demo"), self.dataset("fdo-dashboard-demo")
        self.assertEqual(sorted(new["layers"]), sorted(self.PAIRS.values()))   # keyed by panel, not by a CS3 slot
        for slot, key in self.PAIRS.items():
            for field in self.SAME:
                self.assertEqual(new["layers"][key][field], old["layers"][slot][field], f"{key}.{field}")
            for var, column in new["layers"][key]["variables"].items():
                self.assertEqual(column, old["layers"][slot]["variables"][var], f"{key}.{var}")
        risk = new["layers"]["panel-risk"]
        self.assertEqual(risk["channels"]["x"], {"column": "PFRMA_smoothed", "breaks": old["layers"]["riskMap"]["classification"]["breaks_ma"]})
        self.assertEqual(risk["localPath"], "/api/sources/fdo-dashboard-demo/files/hamburg-cca-profile-demo/public/risk_healpix.fgb")
        self.assertEqual(risk["origin"], {"pid": DATA, "folder": "hamburg-cca-profile-demo"})
        self.assertEqual({k: v["available"] for k, v in new["panels"].items()}, {"map": True, "claims": True, "metadata": True})
        self.assertEqual(len(new["claims"]), 3)
        self.assertEqual(risk["style"]["colorScheme"], "yellow-purple")
        self.assertEqual([c["key"] for c in new["composition"]], ["panel-risk", "panel-social-vulnerability", "panel-drivers", "panel-claims", "panel-metadata"])
        self.assertEqual(new["composition"][1]["exclusiveGroup"], "background")
        self.assertTrue(all(c["drawable"] for c in new["composition"]))
        self.assertEqual(new["plan"]["status"], PASS)
        self.assertEqual(new["plan"]["schema"], DASHBOARD_PLAN_SCHEMA_ID)

    def test_two_data_fdos_in_one_dashboard_serve_files_from_their_own_folders(self):
        second = DATA + "-b"

        def split(folder):
            source = folder / "objects" / "hamburg-cca-profile-demo"
            twin = folder / "objects" / "hamburg-cca-profile-demo-b"
            twin.mkdir()
            c = json.loads((source / "ro-crate-metadata.json").read_text(encoding="utf-8"))
            node(c, "./")["identifier"] = second
            (twin / "ro-crate-metadata.json").write_text(json.dumps(c), encoding="utf-8")
            (twin / "public").symlink_to((source / "public").resolve(), target_is_directory=True)
            pids = json.loads((folder / "pids.json").read_text(encoding="utf-8"))
            pids[second] = {"fixture": "hamburg-cca-profile-demo-b"}
            (folder / "pids.json").write_text(json.dumps(pids), encoding="utf-8")
            d = crate(folder, "hamburg-dashboard")
            node(d, "#panel-social-vulnerability")["object"] = {"@id": second + "#product-vulnerability-healpix"}
            save(folder, "hamburg-dashboard", d)
        ds = self.composed_dataset(split)
        risk, sv = ds["layers"]["panel-risk"], ds["layers"]["panel-social-vulnerability"]
        self.assertEqual(risk["localPath"], "/api/sources/fdo-dashboard-demo/files/hamburg-cca-profile-demo/public/risk_healpix.fgb")
        self.assertEqual(sv["localPath"], "/api/sources/fdo-dashboard-demo/files/hamburg-cca-profile-demo-b/public/vulnerability_healpix.fgb")
        self.assertEqual((risk["origin"]["pid"], sv["origin"]["pid"]), (DATA, second))
        self.assertTrue(risk["drawable"] and sv["drawable"])

    def test_a_layer_without_declared_class_breaks_is_not_drawn_and_says_so(self):
        def no_breaks(folder):
            c = crate(folder, "hamburg-cca-profile-demo")
            node(c, "#product-risk-healpix")["additionalProperty"] = [p for p in node(c, "#product-risk-healpix")["additionalProperty"]
                                                                       if "classBreaks" not in p["@id"] and "class" not in p["@id"].lower()]
            save(folder, "hamburg-cca-profile-demo", c)
        ds = self.composed_dataset(no_breaks)
        risk = ds["layers"]["panel-risk"]
        self.assertFalse(risk["drawable"])
        self.assertEqual(risk["channels"]["x"]["breaks"], [])
        entry = next(c for c in ds["composition"] if c["key"] == "panel-risk")
        self.assertIn("projection.classification_absent", [d["code"] for d in entry["diagnostics"]])
        self.assertFalse(entry["drawable"])
        self.assertTrue(ds["panels"]["map"]["available"])   # the backgrounds still draw

    def test_a_composition_that_cannot_be_used_is_422_not_404(self):
        from backend.adapters.base import CompositionError
        def no_panels(folder):
            d = crate(folder, "hamburg-dashboard")
            node(d, "#dashboard")["hasPart"] = []
            save(folder, "hamburg-dashboard", d)
        with self.assertRaises(CompositionError) as caught:
            self.composed_dataset(no_panels)
        self.assertEqual(caught.exception.status, 422)


if __name__ == "__main__":
    unittest.main()
