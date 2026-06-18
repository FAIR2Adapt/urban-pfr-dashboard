"""Pytest wrapper around the dashboard dataset contract checker."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

import check_dashboard_contract as contract

def _load_or_skip():
    try:
        return contract.load_dataset(None, None)
    except contract.NoDataError as exc:
        pytest.skip(str(exc))

def test_default_source_satisfies_contract():
    ds = _load_or_skip()
    errors, _ = contract.check(ds)
    assert not errors, "Contract errors:\n" + "\n".join(errors)

def test_dashboard_view_backgrounds_are_distinct():
    ds = _load_or_skip()
    views = ds.get("dashboardViews") or {}
    fig5 = (views.get("risk-social-vulnerability") or {}).get("backgroundLayer")
    fig6 = (views.get("risk-drivers") or {}).get("backgroundLayer")
    assert not (fig5 and fig6 and fig5 == fig6), "Figure 5 and 6 share a background layer"

def test_broken_dataset_is_rejected():
    bad = {"id": "x", "metadata": {}, "layers": {}, "dashboardViews": {}, "ui": {}, "diagnostics": {}}
    errors, _ = contract.check(bad)
    assert errors, "checker should reject a dataset with no riskMap / dashboard views"
