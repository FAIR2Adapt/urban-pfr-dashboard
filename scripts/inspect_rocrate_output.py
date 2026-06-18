"""Inspect an RO-Crate output package and print a compact dashboard summary.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.rocrate_output_mapper import ROCrateOutputMapper

def _layer_line(layer: dict) -> str:
    if not layer:
        return "not detected"
    where = layer.get("localPath") or layer.get("sourceUrl") or "?"
    return (
        f"{layer.get('label')}  ->  {where}  "
        f"(rows={layer.get('rowCount')}, cols={layer.get('columnCount')})"
    )

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect an RO-Crate output package.")
    parser.add_argument("package_root", help="Path to the RO-Crate package directory")
    parser.add_argument("--out", help="Optional path to write the full dashboard dataset JSON")
    parser.add_argument("--id", default="hamburg-rocrate-local", help="Dataset id to embed")
    args = parser.parse_args(argv)

    mapper = ROCrateOutputMapper(args.package_root)
    dataset = mapper.to_dashboard_dataset(dataset_id=args.id)

    md = dataset["metadata"]
    layers = dataset.get("layers") or {}
    diagnostics = dataset["diagnostics"]

    print("=" * 72)
    print(f"Dataset title : {md.get('title')}")
    print(f"Dataset id    : {dataset['id']}")
    print(f"Authors       : {len(md.get('authors', []))}")
    print(f"Claims        : {len(dataset['claims'])}")
    print(f"Layers        : {len(layers)}")
    for key, layer in layers.items():
        print(f"   - {key}: {_layer_line(layer)}")
    print(f"Risk fields   : {', '.join((layers.get('riskMap') or {}).get('fields', [])) or '-'}")
    print(f"UI risk fields: {', '.join(dataset['ui'].get('defaultRiskFields', []))}")
    print(f"Background flds: {', '.join(dataset['ui'].get('availableBackgroundFields', [])) or '-'}")
    print(f"Dashboard views   : {', '.join((dataset.get('dashboardViews') or {}).keys()) or '-'}")
    print(f"Default view  : {dataset['ui'].get('defaultDashboardView')}")
    print(f"Figures       : {len(dataset['figures'])}")
    for fig in dataset["figures"]:
        where = fig.get("localPath") or "(remote only)"
        print(f"   - {fig['id']}  [claim={fig.get('relatedClaim')}]  {where}")

    warnings = diagnostics.get("warnings", [])
    print(f"Warnings      : {len(warnings)}")
    for warning in warnings:
        print(f"   ! {warning}")
    if diagnostics.get("missingFiles"):
        print(f"Missing files : {', '.join(diagnostics['missingFiles'])}")
    if diagnostics.get("unmappedOutputs"):
        print(f"Unmapped outs : {len(diagnostics['unmappedOutputs'])}")
    print("=" * 72)

    if args.out:
        out_path = Path(args.out)

        if out_path.is_dir() or args.out.endswith(("/", "\\")):
            out_path = out_path / "dashboard_dataset.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
