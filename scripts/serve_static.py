"""Serve a built static site (``dist/``) locally with correct MIME types.
    python scripts/serve_static.py --dir dist --port 8011
"""
from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path

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
    }

def main():
    ap = argparse.ArgumentParser(description="Preview a static build locally.")
    ap.add_argument("--dir", default="dist", help="directory to serve (default: dist)")
    ap.add_argument("--port", type=int, default=8011, help="port (default: 8011)")
    args = ap.parse_args()

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
