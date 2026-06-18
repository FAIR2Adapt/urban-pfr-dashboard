"""Export a fully static build of the dashboard for GitHub Pages.
To do
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api import routes
from backend.config import load_config

FILES_RE = re.compile(r"^/api/sources/([^/]+)/files/(.+)$")
STATIC_MARKER = "<script>window.__STATIC_DATA__=true;</script>"
APP_SCRIPT = '<script type="module" src="js/app.js"></script>'

def _relativize(obj, package_root: Path, files_out: Path, copied: list):
    """Recursively turn every ``/api/sources/{id}/files/{name}`` reference into a
    relative ``data/{id}/files/{name}`` path, copying the file into ``files_out``.

    A referenced file that doesn't exist becomes ``None`` (the frontend already
    falls back gracefully), so a missing resource never breaks the build.
    """
    if isinstance(obj, dict):
        return {k: _relativize(v, package_root, files_out, copied) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_relativize(v, package_root, files_out, copied) for v in obj]
    if isinstance(obj, str):
        m = FILES_RE.match(obj)
        if not m:
            return obj
        source_id, name = m.group(1), m.group(2)
        src_file = package_root / name
        if not src_file.is_file():
            return None
        dest = files_out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest)
        copied.append(name)
        return f"data/{source_id}/files/{name}"
    return obj

def export(out_dir: Path):
    config = load_config(ROOT)
    frontend = ROOT / "frontend"

    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(frontend, out_dir)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    index = out_dir / "index.html"
    html = index.read_text(encoding="utf-8")
    if STATIC_MARKER not in html and APP_SCRIPT in html:
        html = html.replace(APP_SCRIPT, f"{STATIC_MARKER}\n{APP_SCRIPT}")
        index.write_text(html, encoding="utf-8")

    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    _status, sources_body = routes.list_sources(config)
    (data_dir / "sources.json").write_text(
        json.dumps(sources_body, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exported, skipped = [], []
    for source in config.sources:
        sid = source.get("id")
        if not source.get("enabled"):
            skipped.append((sid, "disabled"))
            continue
        try:
            dataset = routes.load_dataset_dict(config, sid)
        except Exception as exc:
            skipped.append((sid, str(exc)))
            continue
        package_root = (ROOT / source.get("locator", {}).get("value", "")).resolve()
        files_out = data_dir / sid / "files"
        copied: list = []
        dataset = _relativize(dataset, package_root, files_out, copied)
        (data_dir / sid).mkdir(parents=True, exist_ok=True)
        (data_dir / sid / "dataset.json").write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        exported.append((sid, len(set(copied))))

    print(f"Static export -> {out_dir}")
    for sid, n in exported:
        print(f"  [ok]   {sid}: {n} file(s) copied")
    for sid, why in skipped:
        print(f"  [skip] {sid}: {why}")
    if not exported:
        raise SystemExit("No sources exported — nothing to deploy.")
    return exported

def main():
    ap = argparse.ArgumentParser(description="Export a static (GitHub Pages) build.")
    ap.add_argument("--out", default="dist", help="output directory (default: dist)")
    args = ap.parse_args()
    out = Path(args.out)
    out = out if out.is_absolute() else (ROOT / out)
    export(out.resolve())

if __name__ == "__main__":
    main()
