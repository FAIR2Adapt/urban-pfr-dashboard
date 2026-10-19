"""The formats registry (config/formats.yaml): one normalisation of declared media types, and no copy of the list
elsewhere that disagrees with it (contract accepts, Plugin FDO test objects, frontend readers, the reader's suffix table)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.services import formats  # noqa: E402
from support import CONTRACTS, HAVE_FDO_CONSUME, PROFILE_MAPS  # noqa: E402

REG = formats.registry()
KNOWN = set(REG["_aliases"])


class NormalisationTest(unittest.TestCase):
    def test_aliases_case_and_parameters_give_the_canonical_type(self):
        for value in ("application/vnd.flatgeobuf", "application/x-flatgeobuf", "Application/FlatGeobuf", "application/flatgeobuf; charset=binary"):
            self.assertEqual(formats.canonical(value), "application/flatgeobuf", value)
        self.assertEqual(formats.canonical("application/vnd.pmtiles;version=3"), "application/vnd.pmtiles")

    def test_a_value_that_is_not_a_media_type_has_no_canonical_type(self):
        for value in (None, 42, {"@id": "x"}, "https://www.nationalarchives.gov.uk/PRONOM/fmt/0000", "FlatGeobuf", "a b/c"):
            self.assertIsNone(formats.canonical(value), value)

    def test_an_unlisted_type_stays_itself_and_is_refused(self):
        dist = [{"format": "application/geopackage+sqlite3", "path": "x.gpkg", "declared_path": "x.gpkg"}]
        chosen = formats.assess(dist)
        self.assertEqual(chosen, {"webgl": None, "leaflet": None})
        self.assertIn("no reader in this dashboard for application/geopackage+sqlite3", dist[0]["read"]["webgl"]["reason"])

    def test_each_engine_prefers_as_the_registry_says(self):
        dist = [{"format": "application/geo+json", "path": "a.geojson", "contentSize": 10},
                {"format": "application/flatgeobuf", "path": "a.fgb"}, {"format": "application/vnd.pmtiles", "path": "a.pmtiles"}]
        chosen = formats.assess(dist)
        self.assertEqual((chosen["webgl"]["reader"], chosen["leaflet"]["reader"]), ("pmtiles", "fgb-bbox"))
        self.assertIn("not used: PMTiles is preferred", dist[0]["read"]["webgl"]["reason"])

    def test_a_restricted_or_unserved_file_is_refused_with_the_reason(self):
        dist = [{"format": "application/flatgeobuf", "path": "a.fgb", "accessTier": "private"}, {"format": "application/vnd.pmtiles", "path": None}]
        formats.assess(dist)
        self.assertEqual(dist[0]["read"]["leaflet"]["reason"], "restricted; not served")
        self.assertEqual(dist[1]["read"]["webgl"]["reason"], "the file is not in the folder this server serves")


class DriftTest(unittest.TestCase):
    def test_every_engine_prefers_only_readable_formats_it_reads(self):
        for name, engine in REG["engines"].items():
            for media in engine["prefer"]:
                self.assertIn(name, REG["formats"][media]["engines"], (name, media))

    def test_the_frontend_implements_every_reader(self):
        code = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "frontend" / "js" / "map").glob("*.js"))
        for media, entry in REG["formats"].items():
            self.assertIn(f'"{entry["reader"]}"', code, media)

    def test_every_format_the_plugin_test_objects_accept_is_known(self):
        for crate in (ROOT / "test-data" / "fdo-cca-demo" / "objects").glob("plugin-*/ro-crate-metadata.json"):
            for node in json.loads(crate.read_text(encoding="utf-8"))["@graph"]:
                values = node.get("encodingFormat") if node.get("@type") == "FormalParameter" else None
                for value in values or []:
                    with self.subTest(plugin=crate.parent.name, format=value):
                        self.assertIn(value.lower(), KNOWN)

    @unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
    def test_the_map_contract_accepts_only_known_formats(self):
        from fdo_consume.contracts import load_contract
        for media in load_contract("cs3-map-v1", folder=CONTRACTS, profile_maps=PROFILE_MAPS).get("accepts", []):
            self.assertIn(media.lower(), KNOWN, media)

    @unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
    def test_the_readers_suffix_table_maps_map_files_to_known_formats(self):
        import fdo_consume
        table = yaml.safe_load((Path(fdo_consume.__file__).parent / "semantics" / "data" / "media-suffixes.yaml").read_text(encoding="utf-8"))
        flat = table.get("suffixes", table) if isinstance(table, dict) else {}
        for suffix in (".fgb", ".pmtiles", ".geojson"):
            media = flat.get(suffix) or flat.get(suffix.lstrip("."))
            if media is None:
                continue
            with self.subTest(suffix=suffix):
                self.assertIn(formats.canonical(media), REG["formats"])


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class CapabilitiesTest(unittest.TestCase):
    def test_the_document_is_generated_from_the_registries(self):
        from backend.api import routes
        from backend.config import load_config
        from backend.composer.registry import load_registry
        status, doc = routes.handle_api(load_config(ROOT), ["api", "capabilities"])
        self.assertEqual(status, 200)
        self.assertEqual(doc["status"], "prototype")
        self.assertEqual([f["mediaType"] for f in doc["formats"]], list(REG["formats"]))
        self.assertEqual({r["pluginPid"] for r in doc["renderers"]}, set(load_registry(ROOT / "config" / "renderers.yaml")))
        self.assertTrue(all(isinstance(p["inputs"], list) for p in doc["plugins"]), doc["plugins"])
        rows = yaml.safe_load((ROOT / "config" / "variation_matrix.yaml").read_text(encoding="utf-8"))["rows"]
        self.assertEqual(doc["builtFromTheFdo"], rows)
        self.assertEqual({f["status"] for f in doc["formats"]}, {"readable"})


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class ConfigPathTest(unittest.TestCase):
    def test_the_data_fdo_source_gives_each_engine_its_file(self):
        from backend.api import routes
        from backend.config import load_config
        layer = routes.load_dataset_dict(load_config(ROOT), "fdo-cca-demo")["layers"]["riskMap"]
        self.assertEqual(layer["engines"]["webgl"]["reader"], "pmtiles")
        self.assertEqual(layer["engines"]["leaflet"]["reader"], "fgb-bbox")
        self.assertTrue(layer["engines"]["leaflet"]["path"].startswith("/api/sources/fdo-cca-demo/files/"))
        self.assertEqual(layer["renderingStrategy"], "fgb-bbox")
        self.assertEqual(layer["notes"], [REG["formats"]["application/vnd.pmtiles"]["note"]])


if __name__ == "__main__":
    unittest.main()
