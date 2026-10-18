// The capabilities document (generated from the formats registry, the renderer registry, the contracts, the Plugin FDOs
// and the variation matrix) as tables. The static build carries data/capabilities.json; the server answers /api/capabilities.
import { esc } from "./ui/dom.js";

async function load() {
  for (const url of ["data/capabilities.json", "/api/capabilities"]) {
    try {
      const res = await fetch(url);
      if (res.ok) return res.json();
    } catch { /* next */ }
  }
  throw new Error("the capabilities document could not be read");
}

const table = (head, rows) => `<table class="cap-table"><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
  <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
const code = (s) => `<code>${esc(s)}</code>`;
const list = (xs) => (xs || []).map(code).join(", ");

function render(c) {
  document.getElementById("capHead").textContent = `${c.schema} · ${c.status}${c.commit ? ` · commit ${c.commit}` : ""} · generated from ${c.generatedFrom.join(", ")}`;
  const parts = [];
  parts.push("<h2>Data formats</h2>", table(["media type", "aliases", "kind", "read by", "limits", "status"],
    c.formats.map((f) => [code(f.mediaType), list(f.aliases), esc(f.kind), esc(f.engines.map((e) => c.engines[e]?.label || e).join(", ")),
      esc([f.maxFeaturesPerRead ? `${f.maxFeaturesPerRead} features per read` : "", f.maxBytes ? `${f.maxBytes / 1e6} MB` : "", f.note || ""].filter(Boolean).join("; ")),
      esc(f.status)])), `<p class="rp-muted">Any other format: ${esc(c.otherFormats.status)}, ${esc(c.otherFormats.reason)}.</p>`);
  parts.push("<h2>Map engines</h2>", table(["engine", "preference"], Object.values(c.engines).map((e) => [esc(e.label), list(e.prefer)])));
  parts.push("<h2>Renderers (trusted local implementations of Plugin FDOs)</h2>", table(["plugin", "supported version", "renderer", "channels", "palettes"],
    c.renderers.map((r) => [code(r.pluginPid), esc(r.supportedPluginVersion), code(r.renderer),
      esc(Object.entries(r.channels).map(([k, v]) => `${k}: ${v.variable}${v.breaks ? ` (${v.breaks})` : ""}`).join("; ")), list(r.palettes)])));
  parts.push("<h2>Plugin FDOs and their inputs</h2>", table(["plugin", "declared version", "inputs"],
    c.plugins.map((p) => [code(p.pid), esc(p.declaredVersion || ""), Array.isArray(p.inputs)
      ? p.inputs.map((i) => `${esc(i.name)} (${esc(i.kind || "")}${i.required ? ", required" : ""}): ${list(i.formats)}${i.variables.length ? `<br><span class="rp-muted">${i.variables.map(esc).join(", ")}</span>` : ""}`).join("<br>")
      : esc(p.inputs ? p.inputs.unreadable || "" : "not read")])));
  parts.push("<h2>Consumer contracts</h2>", table(["contract", "must", "should", "accepts"],
    c.contracts.map((k) => [code(k.id), list(k.must), list(k.should), list(k.accepts)])));
  parts.push("<h2>Built from the FDO: edits that change the page without code</h2>", table(["edit in the objects", "change on the page", "test"],
    c.builtFromTheFdo.map((r) => [esc(r.edit), esc(r.change), code(r.test)])));
  parts.push("<h2>Still code</h2>", `<ul>${c.stillCode.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`);
  document.getElementById("capBody").innerHTML = parts.join("");
}

load().then(render).catch((e) => { document.getElementById("capHead").textContent = e.message; });
