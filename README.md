# Flood-Risk Dashboard

This dashboard visualizes **urban pluvial flood-risk** from RO-Crate research packages.


## What the dashboard shows

- **Risk map (PFR)** — aggregated HEALPix cells (public tier), rendered with MapLibre GL.
- **Context backgrounds** — social vulnerability and vulnerability drivers.
- **Public / internal views** — the server decides which tiers a deployment may see.
- **Evidence / metadata** — provenance, data-access conditions and scholarly
  annotations read from the source RO-Crates.
---

## Online demo

GitHub Pages serves a static build of the dashboard with **synthetic demo data** (Hamburg and Bremen, no real results):

- <https://fair2adapt.github.io/urban-pfr-dashboard/>
---

## Quick start

**local:**

```bash
git clone https://github.com/FAIR2Adapt/urban-pfr-dashboard.git
git clone https://github.com/FAIR2Adapt/fdo-consume.git
cd urban-pfr-dashboard
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install ../fdo-consume
python server.py
```

**Docker:**

```bash
docker compose up --build
```

open <http://localhost:8000>.

- `?source=<id>` opens one source, e.g. `?source=fdo-loom-record` (Hamburg) or `?source=bremen-loom-record` (Bremen).
- MapLibre GL is the default renderer; without WebGL the map is drawn with Leaflet.
- The synthetic test data for Hamburg and Bremen is in `test-data/fdo-cca-demo`; no data generation is needed.
---

## Configuration and data sources

Sources are declared in `config/sources.json` (the registry). Each entry names an **adapter** and a **locator** (where
the FDO is found):

```json
{
  "id": "fdo-loom-record",
  "label": "Hamburg study record (Knowledge Loom; map from the Data FDO it is based on)",
  "city": "Hamburg",
  "adapter": "fdo-resource",
  "enabled": true,
  "locator": {
    "pid": "https://example.org/stand-in/hamburg-loom-record",
    "fixtures": "test-data/fdo-cca-demo",
    "profile": "knowledge-loom-0.1.0"
  }
}
```

- `fdo-resource` reads a Data FDO or a Knowledge Loom record; `fdo-dashboard` composes the page from a Dashboard FDO.
  Both read through [fdo-consume](https://github.com/FAIR2Adapt/fdo-consume).
- `locator.fixtures` is relative to the project root; `locator.profile` names the profile when the object does not
  declare it.
- `defaultSource` chooses what loads first; a source whose `requires` file is absent is shown as planned.
- Set `DASHBOARD_CONFIG` to point at a different registry file.
- `deployment` (`"public"`, default, or `"internal"`) controls whether the private tier is served.
- Other files: `config/formats.yaml` (readable formats and map engines), `config/renderers.yaml` (renderer per Plugin
  FDO), `config/dashboard.yaml` (panels of a Data FDO without a Dashboard FDO), `config/fdo/contracts/` and
  `config/fdo/maps/` (what each panel needs from an FDO, and the draft dashboard additions to the CCA profile).
