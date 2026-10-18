"""HTTP server: serves the frontend (static files) and the JSON API.
"""
from __future__ import annotations

import http.server
import json
import mimetypes
import re
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .adapters.base import AdapterError
from .api import routes
from .config import SourcesConfig, files_root, load_config

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Static files come from frontend/; /api/* is delegated to routes."""

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".html": "text/html",
        ".json": "application/json",
        ".geojson": "application/geo+json",
        ".png": "image/png",
    }

    def __init__(self, *args, frontend_dir=None, config=None, **kwargs):

        self._config = config
        super().__init__(*args, directory=str(frontend_dir), **kwargs)

    def log_message(self, fmt, *args):
        first = str(args[0]) if args else ""
        if "/api/" in first or (len(args) > 1 and str(args[1]) >= "400"):
            super().log_message(fmt, *args)

    def end_headers(self):
        if self._config.deployment == "public":   # an internal deployment answers its own origin only
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if len(parts) >= 5 and parts[0] == "api" and parts[1] == "sources" and parts[3] == "files":
            self._serve_source_file(parts[2], unquote("/".join(parts[4:])), parse_qs(parsed.query))

        elif parts and parts[0] == "api":
            status, body = routes.handle_api(self._config, parts)
            self._send_json(status, body)
        else:
            super().do_GET()

    def _send_json(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _authorize(self, source_id, rel):
        # the internal deployment serves the private tier; ODRL policies are not evaluated yet
        return self._config.deployment == "internal"

    def _serve_source_file(self, source_id, filename, query=None):
        """Serve one package file with Range support; no path traversal. A FlatGeobuf file is filtered by the browser."""
        source = self._config.get(source_id)
        if not source:
            return self._send_json(404, {"error": f"Unknown source id: {source_id}"})
        # Subpaths (public/…, private/…) are allowed
        if not filename or "\\" in filename or ".." in filename.split("/"):
            return self._send_json(403, {"error": "invalid filename"})
        package_root = files_root(source, self._config.root)
        if package_root is None:
            return self._send_json(404, {"error": f"source {source_id} serves no files"})
        target = (package_root / filename).resolve()
        try:
            rel = target.relative_to(package_root)
        except ValueError:
            return self._send_json(403, {"error": "path outside package root"})
        # the tier is checked before any byte is read
        if "private" in rel.parts:
            if not self._authorize(source_id, rel):
                return self._send_json(403, {
                    "error": "restricted",
                    "reason": "private tier — policy-controlled access (ODRL); authorization required",
                })
        if not target.is_file():
            return self._send_json(404, {"error": f"File not found: {filename}"})

        ctype = (
            self.extensions_map.get(target.suffix.lower())
            or mimetypes.guess_type(str(target))[0]
            or "application/octet-stream"
        )
        return self._serve_file_bytes(target, ctype)

    def _serve_file_bytes(self, target, ctype):
        # full (200) or partial (206) file response
        try:
            size = target.stat().st_size
        except OSError as exc:
            return self._send_json(500, {"error": str(exc)})

        start, end, status = 0, size - 1, 200
        range_header = (self.headers.get("Range") or "").strip()
        if range_header.startswith("bytes="):
            spec = range_header[6:].split(",")[0].strip()  # single range only
            m = re.match(r"^(\d*)-(\d*)$", spec)
            if not m or (not m.group(1) and not m.group(2)):
                return self._send_json(400, {"error": f"malformed Range: {range_header}"})
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            else:  # suffix form: bytes=-N (last N bytes)
                start = max(size - int(m.group(2)), 0)
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with target.open("rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client hung up mid-transfer




def _print_banner(root: Path, config: SourcesConfig, port: int):
    print("\n  Flood-Risk Dashboard")
    print(f"  root:   {root}")
    print(f"  config: {root / 'config' / 'sources.json'}")
    if config.sources:
        print(f"\n  Sources ({len(config.sources)}):")
        for s in config.sources:
            mark = "on " if s.get("enabled") else "off"
            print(f"    [{mark}] {str(s.get('id')):26} adapter={s.get('adapter')}")
    else:
        print("\n  No sources configured in config/sources.json")
    print(f"\n  Dashboard:  http://localhost:{port}")
    print(f"  API:        http://localhost:{port}/api/sources")
    print("  Ctrl+C to stop\n")

def run(root: str | Path, host: str = "0.0.0.0", port: int = 8000):
    root = Path(root).resolve()
    frontend_dir = root / "frontend"
    config = load_config(root)

    handler = partial(DashboardHandler, frontend_dir=frontend_dir, config=config)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer((host, port), handler) as httpd:
        _print_banner(root, config, port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Stopped.")
