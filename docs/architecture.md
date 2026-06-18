# Architecture & internals

Deeper reference for developers. The [README](../README.md) covers running the app,
the dataset contract, and adding sources/adapters; this document holds the full file
tree and component-level notes.

## Design rules

1. **No hard-coded data paths in the map/UI.** The frontend asks for a source *by id*.
2. **The frontend doesn't know the source type.** Local file, RO-Crate, URL, ROHub,
   LDM, FDOResource — all return the *same normalized dataset shape*.
3. The **backend** picks the adapter from the registry (`config/sources.json`).
4. The **dashboard-view model** lives in the dataset (`dashboardViews`), not in frontend code.
5. Adding a source = editing config. Adding a source *type* = adding one adapter.

## Full file tree

```
flood-risk-dashboard/
  server.py                 # entry point: reads APP_HOST/APP_PORT, hands off to backend.app.run()
  requirements.txt
  Dockerfile  docker-compose.yml  .dockerignore
  README.md

  config/
    sources.json            # the data-source registry

  backend/
    app.py                  # HTTP server, static files, /api routing, file + proxy routes
    config.py               # loads config/sources.json (DASHBOARD_CONFIG, ${VAR} expansion)
    api/
      routes.py             # list_sources, get_dataset, handle_api
    adapters/
      base.py               # DataSourceAdapter contract + errors
      registry.py           # adapter-name -> adapter class
      local_output_adapter.py     # reads local "paper_format" GeoJSON outputs
      rocrate_output_adapter.py   # reads an RO-Crate output package
      static_geojson_adapter.py   # load a GeoJSON from path/URL
      ldm_dataset_adapter.py      # PLANNED placeholder
      rohub_rocrate_adapter.py    # PLANNED placeholder
      fdo_resource_adapter.py     # PLANNED placeholder
    services/
      rocrate_output_mapper.py    # RO-Crate package -> normalized dataset (+ dashboardViews)
      classification.py           # head/tail breaks + per-layer style metadata
      geojson_loader.py           # GeoPandas/pyproj file loading (lazy imports)
      flood_processing.py         # column resolution, breaks, point/boundary build
      metadata_parser.py          # metadata assembly + FAIR JSON-LD parsing

  frontend/
    index.html  styles.css
    js/
      app.js                # coordinator + render sequence
      state.js              # shared state + view/visualization definitions
      api/dataService.js    # the only module that calls the backend (live + static modes)
      map/{map,layers,legends,colors}.js
      ui/{dom,sidebar,sourceSelector,metadataPanel}.js

  scripts/
    inspect_rocrate_output.py     # debug: print/dump an RO-Crate mapping
    check_dashboard_contract.py   # validate the normalized dataset contract
    export_static.py              # bake a static (no-backend) build
    serve_static.py               # preview a static build locally

  tests/
    test_dashboard_contract.py    # pytest wrapper around the contract checker

  test-data/                            # data — LOCAL ONLY, git-ignored (not in repo)
```

## Backend flow

`server.py` → `backend.app.run(root, host, port)`:

1. `load_config(root)` reads the registry (honoring `DASHBOARD_CONFIG` and expanding
   `${VAR}` in `locator.value`).
2. `GET /api/sources` → `routes.list_sources` (selector metadata).
3. `GET /api/sources/{id}/dataset` → `routes.get_dataset` → `registry.get_adapter(...)`
   → `adapter.load_dataset(source, context={"root": ...})`.
4. `GET /api/sources/{id}/files/{name}` serves a resource **only** from that source's
   package root (path-traversal protected). `…/proxy?url=` fetches a whitelisted
   remote resource (anti-SSRF).

Heavy geo dependencies (geopandas/pyproj/shapely) are imported **lazily inside
functions**, so importing the backend and serving RO-Crate sources needs only the
standard library — useful for the static export and lightweight CI.

## RO-Crate mapper (`services/rocrate_output_mapper.py`)

- `ROCrateOutputMapper.to_dashboard_dataset()` parses the crate `@graph`, builds
  `metadata`, `claims`, `figures`, then classifies claim outputs into layer roles via
  `_classify_layer(...)`:
  - `riskMap` (`primary-risk-layer`) — `smoothed_RIMA` + `smoothed_RIWB`, or a
    risk/PFR label
  - `socialVulnerability` (`social-vulnerability-background`) — `SVF` / "grey SV"
  - `vulnerabilityDrivers` (`vulnerability-drivers-background`) — `Sensitivity` / `CC`
  - `boundaryOutline` (`context-boundary-layer`) — geometry-only boundary output
  - `focusAreas` (`focus-area-outline`) — only if a real focus-area file exists
- `_build_layer(...)` attaches `style` via `classification.build_layer_style(...)`,
  loading the local GeoJSON to precompute head/tail `breaks` when available.
- `_build_dashboard_views(...)` builds the Figure 4/5/6 views, marking a view
  `available: false` + `disabledReason` when its background layer is missing.
- `_build_ui(...)` sets `defaultDashboardView` + `availableDashboardViews`.
- `validate_dashboard_dataset(...)` folds contract issues into `diagnostics.warnings`.

The adapter (`rocrate_output_adapter.py`) then rewrites each resource's `localPath`
to a servable `/api/sources/{id}/files/{name}` URL when the file exists locally.

## Normalized dataset (full notes)

See the README's [Normalized dashboard dataset](../README.md#normalized-dashboard-dataset)
for the shape. Key points:

- `layers.riskMap` is the only required layer; the four background/overlay layers are
  optional and may be `{}` / absent.
- `dashboardViews[view].backgroundLayer` is `null` (Figure 4), `socialVulnerability`
  (Figure 5), or `vulnerabilityDrivers` (Figure 6) — **mutually exclusive**.
- `style.breaks` carries backend-computed head/tail classification so the frontend
  doesn't reclassify.
- `local-output` sources use a simpler shape (inline `layers.riskMap.data`), kept for
  backward compatibility.

## Contract test

`scripts/check_dashboard_contract.py` loads the default source (or `--file`) and
checks: required top-level keys, a usable `riskMap` source reference, the three views
views, Figure 5 ≠ Figure 6 background, no dangling layer references (unless
unavailable + `disabledReason`), and a valid `ui.defaultDashboardView`. `tests/` wraps it
for `pytest`, and CI runs it on every push/PR.
