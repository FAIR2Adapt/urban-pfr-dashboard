from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

_ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.app import run

def main():
    parser = argparse.ArgumentParser(description="Flood-Risk Dashboard (standalone prototype)")
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "0.0.0.0"),
                        help="Bind host (env APP_HOST, default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")),
                        help="Bind port (env APP_PORT, default 8000)")
    parser.add_argument("--root", default=None, help="Project root (defaults to this file's directory)")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else _ROOT
    run(root, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
