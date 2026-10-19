"""Edits made only in the FDOs change the page as config/variation_matrix.yaml says, with no code edited: each test edits a
copy of the synthetic test objects and composes the Hamburg Dashboard FDO from it."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from support import HAVE_FDO_CONSUME  # noqa: E402

FIXTURES = ROOT / "test-data" / "fdo-cca-demo"
DATA = "hamburg-cca-profile-demo"
DASH_PID = "https://example.org/stand-in/hamburg-dashboard"
PLUGINS = ("plugin-bivariate-risk-map", "plugin-single-variable-map", "plugin-bivariate-background-map")
FGB, PMT = "public/risk_healpix.fgb", "public/risk_healpix.pmtiles"
GEOPACKAGE = "application/geopackage+sqlite3"


def copy_objects(tmp: Path) -> Path:
    """Crates and indexes copied, payload files linked: the edits touch metadata only."""
    out = tmp / "fixtures"
    for path in FIXTURES.rglob("*"):
        rel = path.relative_to(FIXTURES)
        if rel.parts[:2] and rel.parts[0] == "objects" and len(rel.parts) > 1 and rel.parts[1].startswith("bremen-"):
            continue
        target = out / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.suffix in (".json", ".txt"):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(path)
    return out


def edit_crate(folder: Path, name: str, change) -> None:
    path = folder / "objects" / name / "ro-crate-metadata.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change({e["@id"]: e for e in data["@graph"]}, data["@graph"])
    path.write_text(json.dumps(data), encoding="utf-8")


def set_format(file_id: str, value):
    def change(nodes, graph):
        nodes[file_id]["encodingFormat"] = value
    return change


def drop_distribution(file_id: str):
    def change(nodes, graph):
        product = nodes["#product-risk-healpix"]
        product["distribution"] = [d for d in product["distribution"] if d["@id"] != file_id]
        graph.remove(nodes[file_id])
    return change


def plugins_also_accept(media_type: str):
    def change(nodes, graph):
        for node in graph:
            if node.get("@type") == "FormalParameter" and isinstance(node.get("encodingFormat"), list):
                node["encodingFormat"] = node["encodingFormat"] + [media_type]
    return change


def composed(*edits, files: dict | None = None) -> dict:
    """The composed dataset of the Hamburg Dashboard FDO after the edits [(object folder, change)]; `files` adds small
    payload files {path under objects/: text}."""
    from backend.adapters.fdo_dashboard_adapter import FDODashboardAdapter
    with tempfile.TemporaryDirectory() as tmp:
        folder = copy_objects(Path(tmp))
        for rel, text in (files or {}).items():
            (folder / "objects" / rel).write_text(text, encoding="utf-8")
        for name, change in edits:
            edit_crate(folder, name, change)
        source = {"id": "matrix", "adapter": "fdo-dashboard",
                  "locator": {"pid": DASH_PID, "fixtures": str(folder), "profile_overlay": "cca-dashboard-additions"}}
        return FDODashboardAdapter().load_dataset(source, {"root": ROOT})


def risk(ds: dict) -> dict:
    return ds["layers"]["panel-risk"]


def by_file(layer: dict, file_id: str) -> dict:
    return next(d for d in layer["distributions"] if d["declared_path"] == file_id)


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class FormatEditsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = risk(composed())

    def test_the_baseline_gives_each_engine_its_file(self):
        self.assertEqual(self.baseline["engines"]["webgl"]["reader"], "pmtiles")
        self.assertEqual(self.baseline["engines"]["leaflet"]["reader"], "fgb-bbox")
        self.assertEqual(self.baseline["renderingStrategy"], "fgb-bbox")

    def test_an_alias_of_the_format_is_read_by_the_same_reader(self):
        layer = risk(composed((DATA, set_format(FGB, "application/vnd.flatgeobuf"))))
        self.assertEqual(layer["engines"]["leaflet"]["reader"], "fgb-bbox")
        self.assertTrue(layer["engines"]["leaflet"]["path"].endswith("risk_healpix.fgb"))
        self.assertEqual(layer["renderingStrategy"], "fgb-bbox")
        self.assertEqual(by_file(layer, FGB)["formatDeclared"], "application/vnd.flatgeobuf")

    def test_case_and_parameters_do_not_change_the_choice(self):
        layer = risk(composed((DATA, set_format(FGB, "application/FlatGeobuf")), (DATA, set_format(PMT, "application/vnd.pmtiles; version=3"))))
        self.assertEqual(layer["engines"], self.baseline["engines"])

    def test_each_engine_draws_the_file_it_reads(self):
        only_fgb = risk(composed((DATA, drop_distribution(PMT))))
        self.assertIsNone(only_fgb["engines"]["webgl"])
        self.assertIn("FlatGeobuf is not read by the WebGL map (MapLibre)", only_fgb["unread"]["webgl"])
        self.assertTrue(only_fgb["drawable"])
        only_pmtiles = risk(composed((DATA, drop_distribution(FGB))))
        self.assertIsNone(only_pmtiles["engines"]["leaflet"])
        self.assertIn("PMTiles is not read by the Leaflet fallback (no WebGL)", only_pmtiles["unread"]["leaflet"])
        self.assertEqual(only_pmtiles["engines"]["webgl"]["reader"], "pmtiles")

    def test_an_unread_format_is_refused_with_its_name(self):
        ds = composed((DATA, set_format(FGB, GEOPACKAGE)), (DATA, set_format(PMT, GEOPACKAGE)))
        entry = next(e for e in ds["composition"] if e["id"] == "#panel-risk")
        self.assertFalse(entry["drawable"])
        self.assertIn("accepted format", entry["reason"])          # the plugin accepts FlatGeobuf and PMTiles only
        accepted = composed((DATA, set_format(FGB, GEOPACKAGE)), (DATA, set_format(PMT, GEOPACKAGE)),
                            *[(p, plugins_also_accept(GEOPACKAGE)) for p in PLUGINS])
        entry = next(e for e in accepted["composition"] if e["id"] == "#panel-risk")
        self.assertFalse(entry["drawable"])
        self.assertIn(f"no reader in this dashboard for {GEOPACKAGE}", entry["reason"])

    def test_a_format_that_is_not_a_media_type_is_refused(self):
        pronom = {"@id": "https://www.nationalarchives.gov.uk/PRONOM/fmt/0000-example"}
        layer = risk(composed((DATA, set_format(FGB, [pronom, "application/flatgeobuf"]))))
        self.assertIn("is not a media type", by_file(layer, FGB)["read"]["leaflet"]["reason"])
        self.assertEqual(layer["engines"]["webgl"]["reader"], "pmtiles")

    def test_an_oversized_geojson_is_refused(self):
        def add_geojson(nodes, graph):
            nodes["#product-risk-healpix"]["distribution"].append({"@id": "public/risk_healpix.geojson"})
            graph.append({"@id": "public/risk_healpix.geojson", "@type": "File", "encodingFormat": "application/geo+json",
                          "contentSize": 90_000_000})
        layer = risk(composed((DATA, add_geojson), *[(p, plugins_also_accept("application/geo+json")) for p in PLUGINS],
                              files={f"{DATA}/public/risk_healpix.geojson": '{"type": "FeatureCollection", "features": []}'}))
        reason = by_file(layer, "public/risk_healpix.geojson")["read"]["webgl"]["reason"]
        self.assertIn("90 MB is more than the 50 MB", reason)
        self.assertEqual(layer["engines"]["webgl"]["reader"], "pmtiles")


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class ObjectEditsTest(unittest.TestCase):
    def test_a_product_in_another_coordinate_system_is_not_drawn(self):
        def projected(nodes, graph):
            nodes["#spatial-structure-parameters"]["value"] = nodes["#spatial-structure-parameters"]["value"].replace("EPSG:4326", "EPSG:25832")
        ds = composed((DATA, projected))
        entry = next(e for e in ds["composition"] if e["id"] == "#panel-risk")
        self.assertFalse(entry["drawable"])
        self.assertIn("EPSG:25832", entry["reason"])
        self.assertEqual(risk(ds)["engines"], {"webgl": None, "leaflet": None})

    def test_changed_breaks_reach_the_layer(self):
        def change(nodes, graph):
            value = json.loads(nodes["#classification-risk-healpix"]["value"])
            value["breaks_ma"] = [0.001, 0.01, 0.1]
            nodes["#classification-risk-healpix"]["value"] = json.dumps(value)
        layer = risk(composed((DATA, change)))
        self.assertEqual(layer["classification"]["breaks_ma"], [0.001, 0.01, 0.1])
        self.assertEqual(layer["channels"]["x"]["breaks"], [0.001, 0.01, 0.1])

    def test_panel_order_follows_the_dashboard(self):
        def swap(nodes, graph):
            nodes["#panel-social-vulnerability"]["position"], nodes["#panel-drivers"]["position"] = 3, 2
        order = [e["id"] for e in composed(("hamburg-dashboard", swap))["composition"]]
        self.assertLess(order.index("#panel-drivers"), order.index("#panel-social-vulnerability"))

    def test_a_restricted_product_is_not_drawn(self):
        def restrict(nodes, graph):
            nodes["#product-risk-healpix"]["accessRights"] = {"@id": "http://publications.europa.eu/resource/authority/access-right/RESTRICTED"}
        ds = composed((DATA, restrict))
        entry = next(e for e in ds["composition"] if e["id"] == "#panel-risk")
        self.assertFalse(entry["drawable"])
        self.assertNotIn("panel-risk", [k for k, layer in ds["layers"].items() if layer["drawable"]])


class MatrixTest(unittest.TestCase):
    def test_every_row_names_a_test_that_exists(self):
        import re
        import yaml
        rows = yaml.safe_load((ROOT / "config" / "variation_matrix.yaml").read_text(encoding="utf-8"))["rows"]
        self.assertTrue(rows)
        for row in rows:
            path, cls, name = row["test"].split("::")
            text = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(test=row["test"]):
                self.assertRegex(text, rf"class {cls}\b")
                self.assertRegex(text, rf"def {re.escape(name)}\(")


if __name__ == "__main__":
    unittest.main()
