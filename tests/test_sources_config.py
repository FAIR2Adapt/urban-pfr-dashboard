"""The source registry: a source serves one declared city; the API says which, the page never parses a label."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.api.routes import list_sources  # noqa: E402
from backend.config import SourcesConfig, city_of, load_config  # noqa: E402


class SourcesConfigTest(unittest.TestCase):
    def test_every_configured_source_declares_its_city(self):
        for name in ("sources.json", "sources.composed.json", "sources.loom.json", "sources.cca-profile.json"):
            data = json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))
            for s in data["sources"]:
                self.assertIn(s.get("city"), ("Hamburg", "Bremen"), f"{name}: {s['id']}")

    def test_the_api_carries_the_city_and_the_label_is_not_parsed(self):
        cfg = SourcesConfig({"sources": [{"id": "a", "label": "Hamburg Dashboard FDO (composed)", "city": "Hamburg", "enabled": True},
                                         {"id": "b", "label": "Bremen study record", "enabled": True}]}, ROOT)
        _, body = list_sources(cfg)
        self.assertEqual([s["city"] for s in body["sources"]], ["Hamburg", "Bremen study record"])   # no city: the label stands in, whole

    def test_a_city_that_is_not_a_string_is_refused_at_load(self):
        self.assertRaises(ValueError, city_of, {"id": "x", "city": 3})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.json"
            path.write_text(json.dumps({"sources": [{"id": "x", "city": ["Hamburg"], "enabled": True}]}), encoding="utf-8")
            import os
            os.environ["DASHBOARD_CONFIG"] = str(path)
            try:
                self.assertRaises(ValueError, load_config, tmp)
            finally:
                del os.environ["DASHBOARD_CONFIG"]

    def test_the_shipped_registry_lists_two_cities(self):
        cfg = load_config(ROOT)
        self.assertEqual(sorted({city_of(s) for s in cfg.sources}), ["Bremen", "Hamburg"])


if __name__ == "__main__":
    unittest.main()
