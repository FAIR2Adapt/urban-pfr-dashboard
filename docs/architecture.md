# Architecture Overview

Web dashboard for exploring urban pluvial flood risk and social vulnerability
(FAIR2Adapt, Hamburg case study). The design follows a FAIR-oriented separation of
concerns: resources, middleware, and applications are loosely coupled and interact
 through declared metadata and a normalized data contract.

## Resource layer

- Analysis results are packaged as **RO-Crate data products** with machine-readable
  metadata describing roles, variables, access tiers and rendering hints.
- Results are organized in **two access tiers**: an aggregated, privacy-preserving
  public tier based on **HEALPix equal-area cells**, and a detailed tier intended for
  controlled internal use.
- An  **annotation crate** carries the knowledge context.

## Middleware layer

- A thin service resolves packages, reads their metadata and exposes a normalized
  dataset contract to clients.
- Serving is scale-aware: aggregated HEALPix layers are published as **PMTiles**
  (a single-file tile archive derived from the canonical outputs, streamed via HTTP
  range requests), while detailed layers are read through **bounding-box queries**
  on FlatGeobuf that return only the features of the current map viewport under a
  server-side cap. Together these strategies span from a district sample to
  full-city coverage and, by design, to multi-city settings.

## Application layer

- A web map client renders the public HEALPix tier with MapLibre GL using self-contained, locally served libraries
- A metadata panel surfaces provenance, data-access conditions and the scholarly
  annotations directly from the crates.

## Nest steps

The architecture is prepared for the next integration steps: adoption of the official
partner FDO metadata as it becomes complete, consolidation of classification
thresholds following scientific validation, and a policy-based refinement of access
control. These are incremental extensions of existing interfaces.
