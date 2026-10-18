"""Serve a built static site (``dist/``) locally as GitHub Pages would: MIME types, Range requests, a path prefix."""
from __future__ import annotations

import argparse
import functools
import http.server
import re
from pathlib import Path

PREFIX = ""

class StaticHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".html": "text/html",
        ".json": "application/json",
        ".geojson": "application/geo+json",
        ".png": "image/png",
        ".pmtiles": "application/vnd.pmtiles",
        ".fgb": "application/vnd.flatgeobuf",
    }

    def translate_path(self, path):
        if PREFIX and path.startswith(PREFIX):
            path = path[len(PREFIX):] or "/"
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        """A single byte range (bytes=a-b) answered with 206, as static hosts do; otherwise the normal file."""
        header = self.headers.get("Range")
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", header or "")
        if not match:
            return super().send_head()
        target = Path(self.translate_path(self.path))
        if not target.is_file():
            return super().send_head()
        size = target.stat().st_size
        start = int(match.group(1)) if match.group(1) else max(size - int(match.group(2)), 0)
        end = min(int(match.group(2)), size - 1) if match.group(1) and match.group(2) else size - 1
        if start >= size or start > end:
            self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(target)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        fh = target.open("rb"); fh.seek(start)
        self.range_remaining = end - start + 1
        return fh

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        self.range_remaining = None
        while remaining > 0:
            chunk = source.read(min(1 << 20, remaining))
            if not chunk:
                break
            outputfile.write(chunk); remaining -= len(chunk)

def main():
    ap = argparse.ArgumentParser(description="Preview a static build locally.")
    ap.add_argument("--dir", default="dist", help="directory to serve (default: dist)")
    ap.add_argument("--port", type=int, default=8011, help="port (default: 8011)")
    ap.add_argument("--prefix", default="", help="serve under this path, like a project page (e.g. /urban-pfr-dashboard)")
    args = ap.parse_args()
    global PREFIX
    PREFIX = args.prefix.rstrip("/")

    directory = str(Path(args.dir).resolve())
    handler = functools.partial(StaticHandler, directory=directory)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("", args.port), handler) as httpd:
        print(f"Serving {directory} at http://localhost:{args.port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")

if __name__ == "__main__":
    main()
