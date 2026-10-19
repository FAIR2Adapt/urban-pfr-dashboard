"""The configured sources: files served under the object's folder, the restricted tier listed and not served, the Loom record drawing the map it is based on, the test data synthetic and checksummed, errors said."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.adapters.base import AdapterError, DatasetLoadError  # noqa: E402
from backend.api import routes  # noqa: E402
from backend.config import load_config  # noqa: E402

SAME = ("role", "accessTier", "renderingStrategy", "sourceLayer", "crs", "geometryType", "featureCount",
        "outputFootprintBbox", "variables", "fields", "classification")


FIXTURES = ROOT / "test-data" / "fdo-cca-demo"


def console(source_id: str) -> dict:
    """What fdo-consume answered for a source, as the adapter logged it (logs/ is git-ignored)."""
    import json
    dataset(source_id)
    return json.loads((ROOT / "logs" / "fdo-consume" / f"{source_id}.json").read_text(encoding="utf-8"))


def dataset(source_id: str) -> dict:
    """The dataset of one configured source."""
    return routes.load_dataset_dict(load_config(ROOT), source_id)


from support import HAVE_FDO_CONSUME  # noqa: E402


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class FdoResourceTest(unittest.TestCase):
    def test_files_are_served_under_the_object_folder(self):
        ds = dataset("fdo-cca-demo")
        layer = ds["layers"]["riskMap"]
        self.assertEqual(layer["localPath"], "/api/sources/fdo-cca-demo/files/hamburg-cca-profile-demo/public/risk_healpix.fgb")
        self.assertTrue(all(d["path"].startswith("/api/sources/fdo-cca-demo/files/hamburg-cca-profile-demo/public/") for d in layer["distributions"]))
        self.assertTrue(all(f["localPath"].startswith("/api/sources/fdo-cca-demo/files/hamburg-cca-profile-demo/") for f in ds["metadata"]["files"]))
        record = ds["evidence"][0]
        self.assertTrue(record["files"][0]["localPath"].startswith("/api/sources/fdo-cca-demo/files/hamburg-loom-record/"))
        self.assertEqual(record["runParameters"]["software"]["name"], "urban-pfr")
        analysis = ds["claims"][0]["analysis"]
        self.assertEqual(len(analysis["procedure"]), 5)
        self.assertTrue(analysis["outputs"][0]["figureUrl"].endswith("/hamburg-loom-record/figures/figure-1-risk-cells.png"))
        self.assertEqual([c["label"] for c in ds["claims"][0]["concepts"]], ["Hamburg", "Pluvial flooding", "Area A"])

    def test_the_restricted_product_is_not_served_and_is_listed(self):
        ds = dataset("fdo-cca-demo")
        self.assertEqual(ds["diagnostics"]["restricted"], ["https://example.org/stand-in/product/buildings-risk"])
        self.assertNotIn("buildingsRisk", ds["layers"])
        self.assertEqual(ds["allowedViews"], ["public"])

    def test_every_panel_is_drawn_for_the_data_fdo(self):
        panels = dataset("fdo-cca-demo")["panels"]
        self.assertEqual({k: v["available"] for k, v in panels.items()}, {"metadata": True, "claims": True, "map": True})

    def test_the_test_crates_match_the_listed_checksums(self):
        import hashlib, re
        text = (ROOT / "test-data" / "fdo-cca-demo" / "checksums.txt").read_text(encoding="utf-8")
        listed = dict(re.findall(r"^(\S+) ([0-9a-f]{64})$", text, re.M))
        for path in sorted((ROOT / "test-data" / "fdo-cca-demo" / "objects").glob("*/ro-crate-metadata.json")):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), listed.get(path.parent.name), path.parent.name)

    def test_the_test_crates_say_they_are_synthetic_and_cite_no_real_identifier(self):
        import re
        for path in (ROOT / "test-data").glob("*/**/ro-crate-metadata.json"):
            if "local-only" in path.parts:  # git-ignored real records, never committed or published
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"ror\.org|orcid\.org/0000-000[1-9]|are real|\bpaper\b", text), str(path))

    def test_the_loom_only_source_shows_its_statements_and_the_map_of_its_data_fdo(self):
        ds = dataset("fdo-loom-record")
        self.assertEqual({k: v["available"] for k, v in ds["panels"].items()}, {"metadata": True, "claims": True, "map": True})
        self.assertEqual(ds["metadata"]["status"], "unpublished")
        self.assertEqual([a["name"] for a in ds["metadata"]["authors"]], ["Example Author 1", "Example Author 2"])

    def test_an_object_that_cannot_be_read_is_an_error_not_an_empty_dashboard(self):
        config = load_config(ROOT)
        bad = {"id": "x", "adapter": "fdo-resource", "enabled": True,
               "locator": {"pid": "https://example.org/stand-in/nothing", "fixtures": "test-data/fdo-cca-demo", "value": "test-data/fdo-cca-demo"}}
        from backend.adapters.registry import get_adapter
        with self.assertRaises(DatasetLoadError):
            get_adapter("fdo-resource").load_dataset(bad, {"root": config.root, "deployment": "public"})

    def test_without_the_fdo_consume_package_the_error_says_what_to_install(self):
        from backend.adapters.registry import get_adapter
        source = load_config(ROOT).get("fdo-cca-demo")
        with mock.patch.dict(sys.modules, {"fdo_consume": None}):
            with self.assertRaises(AdapterError) as caught:
                get_adapter("fdo-resource").load_dataset(source, {"root": ROOT, "deployment": "public"})
        self.assertEqual(caught.exception.status, 503)


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class LoomRecordMapTest(unittest.TestCase):
    """A Loom record describes statements and files, not map products; the page follows its isBasedOn link by PID."""
    def test_a_record_without_map_products_shows_the_map_of_the_object_it_is_based_on(self):
        for source, data_fdo in (("fdo-loom-record", "hamburg-cca-profile-demo"), ("bremen-loom-record", "bremen-cca-profile-demo")):
            if not load_config(ROOT).get(source).get("enabled"):   # the second city's objects are local only
                continue
            ds = dataset(source)
            self.assertTrue(ds["panels"]["map"]["available"], ds["panels"]["map"])
            self.assertEqual(ds["metadata"]["mapFrom"]["pid"], f"https://example.org/stand-in/{data_fdo}")
            self.assertEqual(set(ds["layers"]), {"riskMap", "socialVulnerability", "vulnerabilityDrivers"})
            for key, layer in ds["layers"].items():
                self.assertTrue((layer["localPath"] or "").startswith(f"/api/sources/{source}/files/{data_fdo}/"), (key, layer["localPath"]))
                self.assertEqual(layer["origin"]["pid"], ds["metadata"]["mapFrom"]["pid"])
            self.assertEqual(len(ds["claims"]), 3, "the record's own statements")
            self.assertTrue(any("isBasedOn" in w for w in ds["diagnostics"]["warnings"]))

    def test_the_link_is_not_followed_when_the_source_serves_one_folder_only(self):
        cfg = load_config(ROOT)
        source = dict(cfg.get("fdo-loom-record"))
        source["locator"] = {**source["locator"], "files": "test-data/fdo-cca-demo/objects/hamburg-loom-record"}
        ds = routes.get_adapter("fdo-resource").load_dataset(source, context={"root": ROOT, "deployment": "public"})
        self.assertEqual(ds["metadata"]["mapFrom"]["pid"], "https://example.org/stand-in/hamburg-cca-profile-demo")
        self.assertTrue(all(layer["localPath"] is None for layer in ds["layers"].values()))
        self.assertFalse(ds["panels"]["map"]["available"])


if __name__ == "__main__":
    unittest.main()
