# """data-file loading helpers.

from __future__ import annotations

from pathlib import Path

def geo_available() -> tuple[bool, str]:
    try:
        import geopandas
        import pyproj

        return True, ""
    except Exception as exc:
        return False, str(exc)

def read_geodataframe(path: str | Path):
    import geopandas as gpd

    return gpd.read_file(str(path))
