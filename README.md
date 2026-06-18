# Flood-Risk Dashboard

This dashboard visualizes **urban pluvial flood-risk** from RO-Crate research packages. 


## What the dashboard shows

- **Demo Study area** — pick **Hamburg**, **Bremen**, or **Compare all**.
- **Dashboard view** :
  - **Risk hotspots** 
  - **Risk and social vulnerability** 
- **Evidence / metadata** — shows the RO-Crate for the selected source.
---

## Quick start

**(local):**

```bash
clone repo 
cd /<path>
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

**Docker:**

```bash
docker compose up --build
```

open <http://localhost:8000>.

> `test-data/` is configured sources.

- If the dashboard loads but **no data appears**, add data (above) and check
  `config/sources.json`.
---


## Configuration and data sources

Sources are declared in `config/sources.json` (the registry). Each entry names an **adapter** and a **locator** (where the data lives):

```json
{
  "id": "hamburg-rocrate-local",
  "label": "Hamburg RO-Crate local output",
  "adapter": "rocrate-output",
  "enabled": true,
  "locator": { "type": "local-path", "value": "test-data/hamburg-rocrate" }
}
```

- `locator.value` is **relative to the project root** (resolves under `/app` in
  Docker). 
- `defaultSource` chooses what loads first; `enabled: false` sources show greyed out.
- Set `DASHBOARD_CONFIG` to point at a different registry file (see Docker).
---

### 3. Register the source

Add an entry to `config/sources.json` (see [Configuration and data sources](#configuration-and-data-sources)):

```json
{
  "id": "my-city-rocrate",
  "label": "My City RO-Crate output",
  "adapter": "rocrate-output",
  "enabled": true,
  "locator": { "type": "local-path", "value": "test-data/my-city-rocrate" }
}
```

Set `defaultSource` to your id if you want it to load first.



## Adding a new source

Add an entry to `sources` in `config/sources.json`, choosing an
existing `adapter` and a `locator`. 

---

## Adding a new adapter

For a new source *type*, add one adapter that returns the normalized contract:

```python
from .base import DataSourceAdapter

class MySourceAdapter(DataSourceAdapter):
    adapter_name = "my-source"          # matches "adapter" in sources.json

    def load_dataset(self, source_config, context=None):
        # ... resolve source_config["locator"], fetch/link resources ...
        return {
            "id": source_config["id"],
            "label": source_config.get("label"),
            ..
            },
            "ui": {"defaultDashboardView": "risk-hotspots"},
            "diagnostics": {"warnings": [], "missingFiles": [], "unmappedOutputs": []},
        }
```

Then register it in `backend/adapters/registry.py` and reference
`"adapter": "my-source"` from a source. Run
`python scripts/check_dashboard_contract.py` to confirm the shape.

