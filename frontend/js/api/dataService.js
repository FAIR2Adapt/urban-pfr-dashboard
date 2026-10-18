const STATIC = typeof window !== "undefined" && window.__STATIC_DATA__ === true;

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).error;
    } catch {

    }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function fetchSources() {
  return getJSON(STATIC ? "data/sources.json" : "/api/sources");
}

export function fetchDataset(sourceId) {
  const id = encodeURIComponent(sourceId);
  return getJSON(STATIC ? `data/${id}/dataset.json` : `/api/sources/${id}/dataset`);
}

export async function fetchResource(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).error || ""; } catch { /* no JSON body */ }
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ""}`);
  }
  return res.json();
}

export function resourceUrl(sourceId, resource) {
  if (!resource) return null;
  return resource.localPath || resource.sourceUrl || null;
}
