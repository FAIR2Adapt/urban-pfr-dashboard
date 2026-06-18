from __future__ import annotations

import json
from pathlib import Path

STATEMENT_FIGURES = ("fig4", "fig5", "fig6")

def load_jsonld_statements(directory: str | Path) -> dict:
    statements: dict = {}
    folder = Path(directory)
    if not folder.is_dir():
        return statements
    for fig in STATEMENT_FIGURES:
        path = folder / f"statement1_{fig}.json"
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8") as handle:
                statements[fig] = json.load(handle)
        except Exception as exc:
            statements[fig] = {"error": str(exc)}
    return statements

def build_metadata(
    *,
    label: str,
    locator: dict | None = None,
    stats: dict | None = None,
    statements: dict | None = None,
    columns: dict | None = None,
    description: str | None = None,
    license: str | None = None,
    authors: list | None = None,
) -> dict:
    statements = statements or {}
    return {
        "title": label,
        "description": description
        or "Urban pluvial flood-risk visualization generated from model output.",
        "license": license or "See dataset documentation",
        "authors": authors or [],
        "source": {
            "locator": locator or {},
            "columns": columns or {},
            "stats": stats or {},
            "statements": statements,
            "availableStatements": sorted(statements.keys()),
        },
    }
