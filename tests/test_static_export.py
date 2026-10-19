"""The static build GitHub Pages serves: every entry page, the vendored libraries, each source's dataset with its files, PMTiles and
FlatGeobuf as they are (read by range requests), no copies in other formats."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from support import HAVE_FDO_CONSUME  # noqa: E402


@unittest.skipUnless(HAVE_FDO_CONSUME, "fdo-consume not installed")
class StaticExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import export_static
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls.tmp.name) / "dist"
        export_static.export(cls.dist)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_entry_page_and_the_vendored_libraries_are_there(self):
        for page in ("index.html", "loom/index.html", "combined/index.html", "composed/index.html", ".nojekyll"):
            self.assertTrue((self.dist / page).is_file(), page)
        from backend.config import load_config
        bremen = load_config(ROOT).get("bremen-dashboard-demo")
        self.assertEqual((self.dist / "bremen" / "index.html").is_file(), bool(bremen and bremen.get("enabled")))
        for lib in ("vendor/maplibre-gl.js", "vendor/pmtiles.js", "vendor/leaflet/leaflet.js", "vendor/flatgeobuf/flatgeobuf-geojson.min.js"):
            self.assertTrue((self.dist / lib).is_file(), lib)

    def test_every_source_has_its_dataset_and_its_files(self):
        sources = json.loads((self.dist / "data" / "sources.json").read_text(encoding="utf-8"))["sources"]
        self.assertTrue(sources)
        for source in sources:
            if not source.get("enabled"):   # a source whose objects are not present is listed as disabled and not exported
                self.assertFalse((self.dist / "data" / source["id"]).exists(), source["id"])
                continue
            ds = json.loads((self.dist / "data" / source["id"] / "dataset.json").read_text(encoding="utf-8"))
            self.assertNotIn("_consumption", ds)
            for key, layer in ds["layers"].items():
                self.assertTrue((self.dist / layer["localPath"].lstrip("/")).is_file(), f"{source['id']}: {key}")
            for claim in ds.get("claims", []):
                for out in (claim.get("analysis") or {}).get("outputs", []):
                    if out.get("figureUrl"):
                        self.assertTrue((self.dist / out["figureUrl"].lstrip("/")).is_file(), out["figureUrl"])

    def test_pmtiles_and_flatgeobuf_are_kept_as_they_are(self):
        ds = json.loads((self.dist / "data" / "fdo-cca-demo" / "dataset.json").read_text(encoding="utf-8"))
        risk = ds["layers"]["riskMap"]
        self.assertEqual(risk["renderingStrategy"], "fgb-bbox")
        self.assertTrue(risk["localPath"].endswith("risk_healpix.fgb"))
        self.assertTrue(any(d["path"].endswith(".pmtiles") and (self.dist / d["path"].lstrip("/")).is_file() for d in risk["distributions"]))
        self.assertEqual(list(self.dist.rglob("*.geojson")), [])



class PrivatePathsTest(unittest.TestCase):
    """A reference into a private/ folder never reaches a static build: the file is not copied and the reference is dropped."""

    def test_private_references_are_withheld(self):
        import export_static
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "objects" / "x"
            (root / "public").mkdir(parents=True)
            (root / "private").mkdir()
            (root / "public" / "a.fgb").write_bytes(b"a")
            (root / "private" / "b.fgb").write_bytes(b"b")
            out, copied, withheld = Path(tmp) / "files", [], []
            dataset = {"layers": {"a": {"localPath": "/api/sources/x/files/public/a.fgb"},
                                  "b": {"localPath": "/api/sources/x/files/private/b.fgb", "distributions": [{"path": "/api/sources/x/files/private/b.fgb"}]}}}
            result = export_static._relativize(dataset, root, out, copied, withheld)
            self.assertEqual(result["layers"]["a"]["localPath"], "data/x/files/public/a.fgb")
            self.assertIsNone(result["layers"]["b"]["localPath"])
            self.assertIsNone(result["layers"]["b"]["distributions"][0]["path"])
            self.assertEqual((copied, withheld), (["public/a.fgb"], ["private/b.fgb", "private/b.fgb"]))
            self.assertFalse((out / "private").exists())
            self.assertTrue((out / "public" / "a.fgb").is_file())


if __name__ == "__main__":
    unittest.main()
