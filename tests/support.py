"""Shared by the FDO tests: is a usable fdo-consume (1.x API) installed, and may the tests skip without it."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = str(ROOT / "config" / "fdo" / "contracts")
PROFILE_MAPS = str(ROOT / "config" / "fdo" / "maps")

try:
    import fdo_consume
    from fdo_consume.contracts import load_contract
    HAVE_FDO_CONSUME = getattr(fdo_consume, "__version__", "").startswith("1.") and hasattr(fdo_consume, "describe")
    if HAVE_FDO_CONSUME:
        load_contract("cs3-map-v1", folder=CONTRACTS, profile_maps=PROFILE_MAPS)
except Exception:   # noqa: BLE001  (an older package raises its own error type for a missing contract)
    HAVE_FDO_CONSUME = False

if os.environ.get("FDO_CONSUME_REQUIRED") and not HAVE_FDO_CONSUME:
    raise ImportError("FDO_CONSUME_REQUIRED is set and no fdo-consume 1.x is installed: the FDO tests may not skip")
