# CS3 dashboard: urban pluvial flood risk

A web dashboard for FAIR2Adapt case study 3. It shows urban pluvial flood risk and social vulnerability on a map,
and the scientific claims behind it.

It reads two kinds of FAIR Digital Objects through [fdo-consume](https://github.com/FAIR2Adapt/fdo-consume):

- a **Data FDO** (CCA RO-Crate profile with the draft dashboard additions): the map products, variables, files and
  access;
- a **Knowledge Loom record**: the scientific statements, their authors and status.

The Data FDO links each claim to a statement of the Loom record by PID, and the Loom record names the Data FDO it is
based on (`isBasedOn`, by PID). The dashboard follows these links in both directions: the map comes from the data and
the claims come from the record, whichever object the page starts from. Nothing is copied between the two objects.

## Run it locally

```bash
git clone https://github.com/FAIR2Adapt/urban-pfr-dashboard.git
git clone https://github.com/FAIR2Adapt/fdo-consume.git
cd urban-pfr-dashboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install ../fdo-consume
python server.py
```

Open http://localhost:8000. `?source=<id>` opens one source; the ids are in `config/sources.json`.

## Configuration

| file | content |
|---|---|
| `config/sources.json` | data sources: adapter, city, PID, recorded fixtures or served folder |
| `config/renderers.yaml` | trusted local renderer per Plugin FDO: supported plugin version, channels, palettes |
| `config/dashboard.yaml` | path for a Data FDO without a Dashboard FDO: contract per panel, product per layer, evidence rule, Pages paths |
| `config/formats.yaml` | readable formats: canonical media type, aliases, reader, map engine, limits, engine preference |
| `config/variation_matrix.yaml` | FDO edits that change the page without code, each with its test |
| `config/fdo/contracts/` | consumer contracts: what each panel needs from an FDO |
| `config/fdo/maps/` | `cca-dashboard-additions`: draft dashboard additions to the CCA profile, read as an overlay on the CCA map |

The contracts (`cs3-map-v1`, `cs3-claims-v1`, `cs3-metadata-v1`, `cs3-evidence-v1`, `dashboard-composition-v1`,
`plugin-description-v1`, `composer-object-v1`) and the overlay belong to this dashboard; fdo-consume ships only the
maps of published profiles. A source may name other folders with `locator.contracts` and `locator.profile_maps`.
Presentation choices are configured here; facts about the data (files, variables, access) come from the FDO. A Data
FDO alone is read through `config/dashboard.yaml`; a Dashboard FDO is composed from its Plugin FDOs.

### Data formats

Files are chosen by their declared `encodingFormat`, not by file name. The value is normalised (lower case, no
parameters, aliases mapped) against `config/formats.yaml`. The WebGL map reads PMTiles, then GeoJSON; the map without
WebGL reads FlatGeobuf by bounding box, then GeoJSON. Every other declared file is listed with a reason in the record
panel's Data tab. No format is converted in the browser. `/api/capabilities` (static build: `data/capabilities.json`,
shown by `capabilities.html`) lists formats, renderers, contracts, Plugin FDOs and the variation matrix; it is
generated.

The Knowledge Loom export does not declare its profile; `evidence.profile` in `config/dashboard.yaml` and
`locator.profile` in `config/sources.json` name it.

## Development

```bash
python -m unittest discover -s tests                        # backend tests
npm test --prefix frontend                                  # frontend rules (access, order, legend classes)
python scripts/export_static.py --out dist                  # static build for GitHub Pages
python scripts/serve_static.py --dir dist --port 8011 --prefix /urban-pfr-dashboard
```

Without WebGL, the map is drawn with Leaflet, which reads FlatGeobuf by bounding box through HTTP range requests. The
server needs no geospatial library; `pyogrio` is optional and only checks declared footprints against file bounds.

## Built with

| component | use | licence |
|---|---|---|
| [fdo-consume](https://github.com/FAIR2Adapt/fdo-consume) | reading FDOs: profile maps, contracts, binding, record | MIT |
| MapLibre GL JS 5.6.0 | WebGL map; PMTiles by range requests | BSD-3 (`frontend/vendor/maplibre-gl.LICENSE.txt`) |
| pmtiles.js 3.0.0 | PMTiles protocol for MapLibre | BSD-3 (`frontend/vendor/pmtiles.LICENSE.txt`) |
| Leaflet 1.9.4 | map without WebGL | BSD-2 (`frontend/vendor/leaflet/LICENSE`) |
| flatgeobuf (JS, GeoJSON build) | FlatGeobuf by bounding box | BSD-2 (`frontend/vendor/flatgeobuf/LICENSE.txt`) |
| Esri World Topographic, World Imagery, Light Gray Canvas | basemaps, loaded at run time with Esri's attribution; Esri's terms apply | Esri |
| PyYAML | configuration files | MIT |
| jsonschema (tests only) | validating a composed plan | MIT |

JavaScript libraries are vendored in `frontend/vendor/`; no bundler or package registry is needed. The basemaps are the
only run-time dependency on another server.

## Docker

```bash
docker build -t urban-pfr-dashboard --build-arg FDO_CONSUME_PIP="https://github.com/FAIR2Adapt/fdo-consume/archive/v1.1.0.tar.gz" .
docker run -p 8000:8000 -v "$PWD/test-data:/app/test-data:ro" urban-pfr-dashboard    # http://localhost:8000
```

The test objects are not in the image and are mounted. Without the build argument, the FDO sources answer
"fdo-consume not installed".

The server is a demonstrator. The `internal` deployment serves the restricted tier to any caller; it is not an
authorization mechanism, and ODRL policies are not evaluated. A restricted deployment needs authentication in front of
the server. Cross-origin requests are allowed only in the `public` deployment.
