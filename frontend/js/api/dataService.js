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
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function resourceUrl(sourceId, resource) {
  if (!resource) return null;
  if (resource.localPath) return resource.localPath;
  if (resource.sourceUrl) {
    return STATIC
      ? resource.sourceUrl
      : `/api/sources/${encodeURIComponent(sourceId)}/proxy?url=${encodeURIComponent(
          resource.sourceUrl
        )}`;
  }
  return null;
}
