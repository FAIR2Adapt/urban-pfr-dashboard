"""Validate the normalized dashboard dataset contract.

Loads the default source's dataset through the same backend route the API uses
(or a ``--file`` JSON), then checks the structure the dashboard-based frontend relies
on. Exits non-zero with a clear list of failures.

Usage:
  python scripts/check_dashboard_contract.py
  python scripts/check_dashboard_contract.py --source bremen-rocrate-local
  python scripts/check_dashboard_contract.py --file dashboard_dataset.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_TOP = ("id", "metadata", "layers", "dashboardViews", "ui", "diagnostics")
REQUIRED_VIEWS = ("risk-hotspots", "risk-social-vulnerability", "risk-drivers")
RISK_REFS = ("sourceUrl", "localPath", "dataUrl", "data")
EXPECTED_BG = {
    "risk-social-vulnerability": "socialVulnerability",
    "risk-drivers": "vulnerabilityDrivers",
}

class NoDataError(Exception):
    """No dataset is available to validate — either no source is configured, or a
    configured source's data directory is absent.

    Treated as a *skip*, not a failure: with no data the dashboard still starts
    and CI stays green; the full contract runs as soon as data is added.
    """

def _configured_data_path(cfg, source_id: str):
    src = cfg.get(source_id)
    if not src:
        return None
    value = (src.get("locator") or {}).get("value")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path

def load_dataset(source: str | None, file: str | None) -> dict:
    if file:
        return json.loads(Path(file).read_text(encoding="utf-8"))
    from backend.api import routes
    from backend.config import load_config
    cfg = load_config(ROOT)
    sid = source or cfg.default_source
    if not sid:
        raise NoDataError("no source configured (empty defaultSource / no sources) - nothing to validate")
    data_path = _configured_data_path(cfg, sid)
    if data_path is not None and not data_path.exists():
        raise NoDataError(f"no data found for source '{sid}' at {data_path}")
    return routes.load_dataset_dict(cfg, sid)

def check(ds: dict) -> tuple[list, list]:
    """Return (errors, warnings). Empty errors == contract satisfied."""
    errors: list = []
    warnings: list = []

    for key in REQUIRED_TOP:
        if key not in ds:
            errors.append(f"missing top-level key: {key}")

    layers = ds.get("layers") or {}
    views = ds.get("dashboardViews") or {}
    ui = ds.get("ui") or {}

    risk = layers.get("riskMap")
    if not risk:
        errors.append("layers.riskMap is missing")
    elif not any(risk.get(ref) for ref in RISK_REFS):
        errors.append(f"layers.riskMap has no usable source ref ({', '.join(RISK_REFS)})")

    for view_id in REQUIRED_VIEWS:
        if view_id not in views:
            errors.append(f"dashboardViews.{view_id} is missing")

    hotspots = views.get("risk-hotspots") or {}
    if hotspots.get("backgroundLayer") not in (None, ""):
        errors.append("risk-hotspots.backgroundLayer must be null or absent")

    for view_id, expected in EXPECTED_BG.items():
        view = views.get(view_id) or {}
        if not view:
            continue
        if view.get("available", True):
            if view.get("backgroundLayer") != expected:
                errors.append(
                    f"{view_id}.backgroundLayer should be '{expected}' "
                    f"(got {view.get('backgroundLayer')!r})"
                )
        elif not view.get("disabledReason"):
            errors.append(f"{view_id} is unavailable but has no disabledReason")

    fig5 = (views.get("risk-social-vulnerability") or {}).get("backgroundLayer")
    fig6 = (views.get("risk-drivers") or {}).get("backgroundLayer")
    if fig5 and fig6 and fig5 == fig6:
        errors.append(f"Figure 5 and Figure 6 must not use the same background layer ('{fig5}')")

    for view_id, view in views.items():
        bg = view.get("backgroundLayer")
        if bg and bg not in layers:
            if view.get("available", True):
                errors.append(f"dashboardView '{view_id}' references missing layer '{bg}' but is marked available")
            elif not view.get("disabledReason"):
                errors.append(f"dashboardView '{view_id}' references missing layer '{bg}' without a disabledReason")

    default_view = ui.get("defaultDashboardView")
    if not default_view:
        errors.append("ui.defaultDashboardView is missing")
    elif default_view not in views:
        errors.append(f"ui.defaultDashboardView '{default_view}' is not one of dashboardViews")

    diagnostics = ds.get("diagnostics")
    if diagnostics is None:
        errors.append("diagnostics is missing")
    else:
        warnings.extend(diagnostics.get("warnings") or [])

    return errors, warnings

def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the dashboard dataset contract.")
    ap.add_argument("--source", help="source id (default: config defaultSource)")
    ap.add_argument("--file", help="validate a dataset JSON file instead of loading via backend")
    args = ap.parse_args()

    try:
        ds = load_dataset(args.source, args.file)
    except NoDataError as exc:
        print(f"Dashboard contract check for: {args.source or 'default source'}")
        print(f"  [SKIP] {exc}")
        print("  Add data (see test-data/README.md); this check validates it once present.")
        return 0
    except Exception as exc:
        print(f"[FAIL] could not load dataset: {exc}")
        return 2

    errors, warnings = check(ds)
    label = args.file or args.source or "default source"
    print(f"Dashboard contract check for: {label}")
    if warnings:
        print(f"  {len(warnings)} warning(s) (non-fatal):")
        for w in warnings[:20]:
            print(f"    - {w}")
    if errors:
        print(f"  [FAIL] {len(errors)} contract error(s):")
        for e in errors:
            print(f"    x {e}")
        return 1
    print(
        "  [OK] contract satisfied "
        f"(layers: {', '.join((ds.get('layers') or {}).keys())}; "
        f"views: {', '.join((ds.get('dashboardViews') or {}).keys())})"
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
