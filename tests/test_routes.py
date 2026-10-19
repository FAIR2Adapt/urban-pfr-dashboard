"""The file routes of the server: full and partial reads, the private tier, no path outside a source's folder."""
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import DashboardHandler  # noqa: E402
from backend.config import SourcesConfig  # noqa: E402

DATA = bytes(range(256)) * 4   # 1024 bytes, every byte position distinct within a run


class _QuietHandler(DashboardHandler):
    def log_message(self, *args):   # the refused requests below would otherwise print
        pass


class _Server:
    """The dashboard server on a free port, serving one source from a temporary folder."""

    def __init__(self, root: Path, deployment: str = "public"):
        config = SourcesConfig({"deployment": deployment, "sources": [
            {"id": "demo", "label": "Demo", "city": "Hamburg", "adapter": "fdo-resource", "enabled": True, "locator": {"files": "objects/demo"}}]}, root)
        handler = partial(_QuietHandler, frontend_dir=root / "frontend", config=config)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def get(self, path: str, headers: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        out = response.status, {k.lower(): v for k, v in response.getheaders()}, body
        conn.close()
        return out

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FileRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "objects/demo/public/sub").mkdir(parents=True)
        (root / "objects/demo/private").mkdir(parents=True)
        (root / "frontend").mkdir()
        (root / "objects/demo/public/a.bin").write_bytes(DATA)
        (root / "objects/demo/public/sub/b.txt").write_text("b", encoding="utf-8")
        (root / "objects/demo/private/s.bin").write_bytes(b"secret")
        (root / "frontend/index.html").write_text("<html>page</html>", encoding="utf-8")
        (root / "outside.txt").write_text("outside", encoding="utf-8")
        cls.public = _Server(root, "public")
        cls.internal = _Server(root, "internal")

    @classmethod
    def tearDownClass(cls):
        cls.public.close()
        cls.internal.close()
        cls.tmp.cleanup()

    # --- full and partial reads (PMTiles and FlatGeobuf are read by range requests in the browser) ---

    def test_a_public_file_is_served_whole_with_range_support_announced(self):
        status, headers, body = self.public.get("/api/sources/demo/files/public/a.bin")
        self.assertEqual(status, 200)
        self.assertEqual(body, DATA)
        self.assertEqual(headers["content-length"], str(len(DATA)))
        self.assertEqual(headers["accept-ranges"], "bytes")

    def test_a_range_in_the_middle_gives_206_with_the_bytes_asked(self):
        status, headers, body = self.public.get("/api/sources/demo/files/public/a.bin", {"Range": "bytes=10-19"})
        self.assertEqual(status, 206)
        self.assertEqual(body, DATA[10:20])
        self.assertEqual(headers["content-range"], f"bytes 10-19/{len(DATA)}")
        self.assertEqual(headers["content-length"], "10")

    def test_an_open_ended_range_runs_to_the_end(self):
        status, headers, body = self.public.get("/api/sources/demo/files/public/a.bin", {"Range": "bytes=1000-"})
        self.assertEqual(status, 206)
        self.assertEqual(body, DATA[1000:])
        self.assertEqual(headers["content-range"], f"bytes 1000-1023/{len(DATA)}")

    def test_a_suffix_range_gives_the_last_bytes(self):
        status, _, body = self.public.get("/api/sources/demo/files/public/a.bin", {"Range": "bytes=-5"})
        self.assertEqual(status, 206)
        self.assertEqual(body, DATA[-5:])

    def test_an_end_beyond_the_file_is_clamped(self):
        status, headers, body = self.public.get("/api/sources/demo/files/public/a.bin", {"Range": "bytes=1020-5000"})
        self.assertEqual(status, 206)
        self.assertEqual(body, DATA[1020:])
        self.assertEqual(headers["content-range"], f"bytes 1020-1023/{len(DATA)}")

    def test_a_range_past_the_end_is_416(self):
        status, headers, body = self.public.get("/api/sources/demo/files/public/a.bin", {"Range": "bytes=2000-"})
        self.assertEqual(status, 416)
        self.assertEqual(headers["content-range"], f"bytes */{len(DATA)}")
        self.assertEqual(body, b"")

    def test_a_malformed_range_is_400_and_an_empty_one_416(self):
        for value, expected in (("bytes=abc", 400), ("bytes=-", 400), ("bytes=5-2", 416)):
            status, _, _ = self.public.get("/api/sources/demo/files/public/a.bin", {"Range": value})
            self.assertEqual(status, expected, value)

    def test_a_subfolder_is_served(self):
        status, _, body = self.public.get("/api/sources/demo/files/public/sub/b.txt")
        self.assertEqual((status, body), (200, b"b"))

    # --- the private tier ---

    def test_the_private_tier_is_refused_in_a_public_deployment_before_any_read(self):
        status, _, body = self.public.get("/api/sources/demo/files/private/s.bin")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "restricted")
        status, _, _ = self.public.get("/api/sources/demo/files/private/s.bin", {"Range": "bytes=0-1"})
        self.assertEqual(status, 403)
        status, _, _ = self.public.get("/api/sources/demo/files/private/missing.bin")
        self.assertEqual(status, 403, "a missing private file is refused, not reported as missing")

    def test_the_private_tier_is_served_in_an_internal_deployment(self):
        status, _, body = self.internal.get("/api/sources/demo/files/private/s.bin")
        self.assertEqual((status, body), (200, b"secret"))

    # --- nothing outside the source's folder ---

    def test_a_path_with_dot_dot_is_refused(self):
        for path in ("/api/sources/demo/files/../../outside.txt", "/api/sources/demo/files/public/../../../outside.txt",
                     "/api/sources/demo/files/%2e%2e/%2e%2e/outside.txt", "/api/sources/demo/files/public%2f..%2f..%2foutside.txt"):
            status, _, body = self.public.get(path)
            self.assertEqual(status, 403, path)
            self.assertNotIn(b"outside", body, path)

    def test_a_backslash_or_empty_name_is_refused(self):
        status, _, _ = self.public.get("/api/sources/demo/files/public%5c..%5c..%5coutside.txt")
        self.assertEqual(status, 403)
        status, _, _ = self.public.get("/api/sources/demo/files/")
        self.assertNotEqual(status, 200)

    def test_an_unknown_source_or_file_is_404(self):
        status, _, _ = self.public.get("/api/sources/nope/files/public/a.bin")
        self.assertEqual(status, 404)
        status, _, _ = self.public.get("/api/sources/demo/files/public/missing.bin")
        self.assertEqual(status, 404)

    # --- the rest of the surface ---

    def test_the_source_list_and_the_page_are_served(self):
        status, headers, body = self.public.get("/api/sources")
        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("application/json"))
        self.assertEqual([s["id"] for s in json.loads(body)["sources"]], ["demo"])
        status, _, body = self.public.get("/")
        self.assertEqual((status, body), (200, b"<html>page</html>"))


if __name__ == "__main__":
    unittest.main()
