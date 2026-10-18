// The record panel: a docked panel beside the map with four tabs (statements, data, method, about) built from the
// dataset the adapters produced. It shows declared material only; a statement can switch on the layer it is about.
import { state } from "../state.js";
import { $, esc, safeUrl } from "./dom.js";
import { mapPanels, setEnabled } from "../composition.js";
import { classRanges, statusText } from "../map/classes.js";

const TABS = [["statements", "Statements"], ["data", "Data"], ["method", "Method"], ["about", "About"]];
let activeTab = "statements";
let afterChange = null;   // rebuilds controls and redraws after the panel switched a layer on
let autoOpened = false;

export function wireMetadataToggle(onChange) {
  afterChange = onChange;
  $("metaToggle")?.addEventListener("click", () => setMetaOpen(!state.showMeta));
  $("metaClose")?.addEventListener("click", () => setMetaOpen(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.showMeta) { setMetaOpen(false); $("metaToggle")?.focus(); } });
  const tabs = $("rpTabs");
  tabs?.addEventListener("click", (e) => { const b = e.target.closest("[role=tab]"); if (b) selectTab(b.dataset.tab); });
  tabs?.addEventListener("keydown", (e) => {   // arrows move between tabs, as a tab list does
    if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const i = TABS.findIndex(([k]) => k === activeTab), n = TABS.length;
    selectTab(TABS[(i + (e.key === "ArrowRight" ? 1 : n - 1)) % n][0]);
    tabs.querySelector(`[data-tab="${activeTab}"]`)?.focus();
  });
}

export function setMetadataAvailable(available) {
  const section = $("metadataSection");
  if (section) section.style.display = available ? "" : "none";
  if (!available) { setMetaOpen(false); return; }
  if (!autoOpened && window.innerWidth >= 1200 && (state.dataset?.claims || []).length) { autoOpened = true; setMetaOpen(true); }
}

// the strip and the header open the panel on its statements
export function openStatements() { selectTab("statements"); setMetaOpen(true); }

function setMetaOpen(open) {
  state.showMeta = open;
  $("metaToggle")?.classList.toggle("active", open);
  $("metaToggle")?.setAttribute("aria-pressed", String(open));
  $("recordPanel")?.classList.toggle("hidden", !open);
  if (open) refreshMetadataPanel();
  state.map?.invalidateSize?.();
  window.dispatchEvent(new Event("resize"));   // the WebGL map re-measures its container
}

function selectTab(key) {
  activeTab = TABS.some(([k]) => k === key) ? key : "statements";
  refreshMetadataPanel();
}

export function refreshMetadataPanel() {
  const panel = $("recordPanel");
  if (!panel || !state.showMeta) return;
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);
  const ds = ids.length ? state.datasets[ids[0]] : null;
  const body = $("rpBody"), tabs = $("rpTabs");
  if (!ds) { $("rpTitle").textContent = "No source selected"; $("rpMeta").textContent = ""; tabs.innerHTML = ""; body.innerHTML = ""; return; }
  header(ds);
  tabs.innerHTML = TABS.map(([k, label]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === activeTab}" ${k === activeTab ? "" : 'tabindex="-1"'}>${label}${k === "statements" && (ds.claims || []).length ? ` <span class="rp-count">${(ds.claims || []).length}</span>` : ""}</button>`).join("");
  const other = ids.length > 1 ? `<p class="rp-note">Showing ${esc(shortName(ids[0]))}; the other ${ids.length - 1 === 1 ? "city has" : "cities have"} their own records.</p>` : "";
  body.innerHTML = other + ({ statements: statementsTab, data: dataTab, method: methodTab, about: aboutTab }[activeTab])(ds);
  body.scrollTop = 0;
  body.querySelectorAll("[data-show-product]").forEach((b) => b.addEventListener("click", () => showOnMap(ids[0], ds, b.dataset.showProduct)));
  body.querySelectorAll("[data-view-file]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); viewFile(a); }));
}

const shortName = (id) => (state.sources.find((s) => s.id === id) || {}).city || id;
const isRecord = (ds) => [...(ds.metadata?.source?.profiles || []), ds.metadata?.source?.map || ""].some((p) => /knowledge-?loom/i.test(p));
const fmtSize = (b) => (!b ? "" : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : b >= 1e3 ? `${(b / 1e3).toFixed(0)} KB` : `${b} B`);
const fmtMedia = (m) => ({ "application/flatgeobuf": "FlatGeobuf", "application/vnd.pmtiles": "PMTiles", "application/geo+json": "GeoJSON", "application/ld+json": "JSON-LD",
  "application/json": "JSON", "image/png": "PNG", "text/x-python": "Python" }[m] || (m || "").split("/").pop() || "");
const chip = (c) => `<span class="rp-chip" ${c.definition ? `title="${esc(c.definition)}"` : ""}>${esc(c.label)}</span>`;

// code and descriptions are read in the panel; an image opens in a new tab; a data product is a plain link
const READ_IN_PANEL = /\.(py|json|jsonld|yaml|yml|txt|md|csv)$/i;
function fileLink(url, name, media) {
  if (!url) return `<span>${esc(name)}</span>`;
  if ((media || "").startsWith("image/") || /\.(png|jpe?g|svg|webp)$/i.test(url)) return `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">${esc(name)}</a>`;
  if (READ_IN_PANEL.test(url) || /json|python|text\//.test(media || "")) return `<a href="${esc(safeUrl(url))}" data-view-file="${esc(safeUrl(url))}">${esc(name)}</a>`;
  return `<a href="${esc(safeUrl(url))}">${esc(name)}</a>`;
}

const SHOWN_MAX = 40000;   // characters of a file shown in the panel
async function viewFile(link) {
  const url = link.dataset.viewFile;
  const open = link.parentElement.querySelector(".rp-view");
  if (open) { open.remove(); return; }
  const pre = document.createElement("pre");
  pre.className = "rp-code rp-view";
  pre.textContent = "loading…";
  link.parentElement.appendChild(pre);
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${r.status}`);
    let text = await r.text();
    if (/json/.test(url) || /json/.test(r.headers.get("content-type") || "")) { try { text = JSON.stringify(JSON.parse(text), null, 1); } catch { /* shown as received */ } }
    pre.textContent = text.length > SHOWN_MAX ? `${text.slice(0, SHOWN_MAX)}\n… (${text.length.toLocaleString()} characters; shown in part)` : text;
  } catch (e) {
    pre.textContent = `could not read the file (${e.message})`;
  }
}
const section = (title, html) => (html ? `<div class="meta-section-hdr">${title}</div>${html}` : "");

function header(ds) {
  const md = ds.metadata || {};
  $("rpKind").textContent = isRecord(ds) ? "Knowledge Loom record" : ds.composition ? "Dashboard object" : "Data object";
  $("rpTitle").textContent = md.title || ds.label || "";
  const authors = (md.authors || []).map((a) => (typeof a === "string" ? a : a.name)).filter(Boolean);
  const who = authors.length > 2 ? `${authors.slice(0, 2).join(", ")} et al.` : authors.join(", ");
  const bits = [who, (md.datePublished || "").slice(0, 10), md.license ? licenceName(md.license) : ""].filter(Boolean).map(esc);
  const status = md.status ? `<span class="rp-status">${esc(md.status)}</span>` : "";
  $("rpMeta").innerHTML = bits.join(" · ") + (status ? ` ${status}` : "");
}

const licenceName = (l) => (/by\/4\.0/i.test(l) ? "CC BY 4.0" : /by-sa/i.test(l) ? "CC BY-SA" : /cc0/i.test(l) ? "CC0" : l.replace(/^https?:\/\//, ""));

// ---- statements ----------------------------------------------------------------------------------------

function statementsTab(ds) {
  const claims = ds.claims || [];
  if (!claims.length) return `<p class="rp-empty">This object carries no statements.</p>`;
  const records = Object.fromEntries((ds.evidence || []).map((e) => [e.pid, e]));
  const products = new Set(mapPanels(ds).map((p) => p.layer?.product).filter(Boolean));
  const own = ds.metadata?.source?.pid;
  const groups = new Map();   // the record that asserts the statements, then its statements, as on the record's own page
  for (const c of claims) { const k = c.record || own; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(c); }
  let n = 0;
  return [...groups].map(([pid, list]) => {
    const record = records[pid];
    const card = pid !== own ? recordCard(record || { pid, title: list[0].recordName, usable: !!list[0].recordName }, list.length) : "";
    return card + list.map((c) => {
      const unconfirmed = c.linkChecked === false;
      n += 1;
      return `<article class="rp-card${unconfirmed ? " unconfirmed" : ""}">
      <div class="rp-card-no">${n}</div>
      <div class="rp-card-body">
        <p class="rp-statement">${c.label ? esc(c.label) : `<span class="rp-muted">statement ${esc(c.id)}: its text could not be read</span>`}</p>
        ${(c.concepts || []).length ? `<div class="rp-chips">${c.concepts.map(chip).join("")}</div>` : ""}
        ${unconfirmed ? `<p class="rp-warn">The record does not contain this statement; the text shown is a copy in the data object.</p>` : ""}
        ${c.about && products.has(c.about) ? `<button type="button" class="rp-action" data-show-product="${esc(c.about)}">Show on map</button>` : ""}
        ${c.analysis ? analysisDetails(c.analysis) : ""}
      </div>
    </article>`;
    }).join("");
  }).join("");
}

// the Knowledge Loom record behind a group of statements, as the panel header shows it on the record's own page
function recordCard(e, count) {
  if (!e.usable) return `<div class="rp-record"><span class="rp-kind">Knowledge Loom record</span><h4>${esc(e.pid)}</h4><p class="rp-warn">the record could not be read${(e.why || []).length ? `: ${esc(e.why.join("; "))}` : ""}</p></div>`;
  const who = (e.authors || []).length > 2 ? `${e.authors.slice(0, 2).join(", ")} et al.` : (e.authors || []).join(", ");
  const bits = [who, (e.date || "").slice(0, 10)].filter(Boolean).map(esc).join(" · ");
  return `<div class="rp-record">
    <span class="rp-kind">Knowledge Loom record</span>
    <h4>${esc(e.title || e.pid)}</h4>
    <p>${bits}${e.status ? ` <span class="rp-status">${esc(e.status)}</span>` : ""}</p>
    ${(e.field || []).length ? `<div class="rp-chips small">${e.field.map((f) => `<span class="rp-chip">${esc(f)}</span>`).join("")}</div>` : ""}
    <div class="rp-pid">${esc(e.pid)}</div>
    <p class="rp-muted">${count} statement${count === 1 ? "" : "s"}${(e.files || []).length ? ` · ${e.files.length} files` : ""}</p>
  </div>`;
}

function analysisDetails(a) {
  const dataset = (d) => `<li><span class="rp-ds-label">${esc(d.label || "")}</span>
      ${d.rows || d.columns ? `<span class="rp-muted"> · ${d.rows ? `${d.rows.toLocaleString()} rows` : ""}${d.rows && d.columns ? ", " : ""}${d.columns ? `${d.columns} columns` : ""}</span>` : ""}
      ${(d.components || []).length ? `<div class="rp-chips small">${d.components.map((x) => `<span class="rp-chip">${esc(x)}</span>`).join("")}</div>` : ""}
      ${d.fileUrl ? `<span class="rp-file">${fileLink(d.fileUrl, (d.file || "").split("/").pop(), "")}</span>` : d.file ? `<span class="rp-muted">${esc(d.file)}</span>` : ""}
      ${d.figureUrl ? `<a class="rp-fig" href="${esc(safeUrl(d.figureUrl))}" target="_blank" rel="noopener"><img src="${esc(safeUrl(d.figureUrl))}" alt="${esc(d.label || "figure")}" loading="lazy"></a>` : ""}
    </li>`;
  const steps = (a.procedure || []).map((s) => `<li><span class="rp-step">${esc(s.step || "")}</span>${s.software || s.language ? `<span class="rp-muted"> · ${esc([s.software, s.language].filter(Boolean).join(", "))}</span>` : ""}${s.code ? `<pre class="rp-code">${esc(s.code.trim())}</pre>` : ""}</li>`).join("");
  return `<details class="rp-analysis">
    <summary>Analysis behind this statement</summary>
    ${a.description ? `<p class="rp-desc">${esc(a.description)}</p>` : ""}
    ${(a.inputs || []).length ? `<h5>Input data</h5><ul class="rp-ds">${a.inputs.map(dataset).join("")}</ul>` : ""}
    ${(a.outputs || []).length ? `<h5>Output data</h5><ul class="rp-ds">${a.outputs.map(dataset).join("")}</ul>` : ""}
    ${steps ? `<h5>Procedure</h5><ol class="rp-steps">${steps}</ol>` : ""}
    ${a.implementationUrl ? `<h5>Implementation</h5><span class="rp-file">${fileLink(a.implementationUrl, (a.implementation || "").split("/").pop(), "text/x-python")}</span>` : a.implementation ? `<h5>Implementation</h5><span class="rp-muted">${esc(a.implementation)}</span>` : ""}
  </details>`;
}

function showOnMap(sourceId, ds, product) {
  const panel = mapPanels(ds).find((p) => p.layer?.product === product);
  if (!panel) return;
  setEnabled(sourceId, ds, panel.key, true);
  afterChange?.();
}

// ---- data ----------------------------------------------------------------------------------------------

function dataTab(ds) {
  const md = ds.metadata || {};
  const parts = [];
  if (isRecord(ds)) parts.push(filesSection("Files of the record", md.files || []), runSection(md.runParameters));
  else {
    for (const e of ds.evidence || []) {
      if (!e.usable) continue;
      parts.push(filesSection(`Files of the record: ${esc(e.title || e.pid)}`, e.files || []), runSection(e.runParameters));
    }
    parts.push(filesSection("Files of the data object", md.files || []));
  }
  parts.push(mapFilesSection(ds));
  const html = parts.filter(Boolean).join("");
  return html || `<p class="rp-empty">No files are declared.</p>`;
}

// per map layer: each declared file, its format as declared (or inferred from the file name) and what each map engine does with it
const ENGINES = [["webgl", "WebGL map (MapLibre)"], ["leaflet", "Leaflet fallback"]];
function mapFilesSection(ds) {
  const layers = Object.values(ds.layers || {}).filter((l) => (l.distributions || []).some((d) => d.read));
  if (!layers.length) return "";
  const rows = layers.map((l) => `<div class="rp-group">${esc(l.label || l.datasetLabel || "")}</div><ul class="rp-files">${l.distributions.map((d) => {
    const name = (d.declared_path || "").split("/").pop() || d.formatLabel;
    const how = d.formatSource && d.formatSource !== "declared" ? " (format inferred from the file name)" : "";
    const verdicts = ENGINES.map(([k, label]) => d.read?.[k] ? `<li>${label}: ${d.read[k].ok ? "drawn" : esc(d.read[k].reason)}</li>` : "").join("");
    return `<li>${esc(name)} <span class="rp-muted">${esc(d.formatLabel || d.format || "")}${how}${d.contentSize ? ` · ${fmtSize(+d.contentSize)}` : ""}</span><ul class="rp-diag">${verdicts}</ul></li>`;
  }).join("")}</ul>${(l.notes || []).map((n) => `<p class="rp-muted">${esc(n)}</p>`).join("")}`).join("");
  return section("Map files and how they are read", rows);
}

function filesSection(title, files) {
  if (!files.length) return "";
  const groups = new Map();
  for (const f of files) {
    const folder = f.id.includes("/") ? f.id.split("/")[0] : "files";
    if (!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(f);
  }
  const figures = files.filter((f) => (f.mediaType || "").startsWith("image/") && f.localPath);
  const rows = [...groups].map(([folder, list]) => `<div class="rp-group">${esc(folder)}</div><ul class="rp-files">${list.map((f) => `<li>
      ${fileLink(f.localPath, f.name || f.id, f.mediaType)}
      <span class="rp-muted">${[fmtMedia(f.mediaType), fmtSize(+f.contentSize || 0), f.accessTier === "restricted" ? "restricted" : ""].filter(Boolean).join(" · ")}</span>
    </li>`).join("")}</ul>`).join("");
  const gallery = figures.length ? `<div class="rp-gallery">${figures.map((f) => `<a href="${esc(safeUrl(f.localPath))}" target="_blank" rel="noopener" title="${esc(f.name || f.id)}"><img src="${esc(safeUrl(f.localPath))}" alt="${esc(f.name || f.id)}" loading="lazy"></a>`).join("")}</div>` : "";
  return section(title, gallery + rows);
}

function runSection(run) {
  if (!run) return "";
  const rows = Object.entries(run.parameters || {}).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</td></tr>`).join("");
  const head = [run.software?.name ? `${run.software.name}${run.software.version ? ` ${run.software.version}` : ""}` : "", run.run?.name, (run.run?.endTime || "").slice(0, 10)].filter(Boolean).map(esc).join(" · ");
  return section("Run parameters", `${head ? `<p class="rp-muted">${head}</p>` : ""}<table class="meta-col-table rp-table">${rows}</table>`);
}

// ---- method --------------------------------------------------------------------------------------------

function methodTab(ds) {
  const parts = [];
  const layers = mapPanels(ds).map((p) => p.layer).filter((l) => l && (l.classification?.method || Object.values(l.channels || {}).some((c) => (c?.breaks || []).length)));
  if (layers.length) {
    parts.push(section("Classification, as declared", layers.map((l) => {
      const ch = Object.entries(l.channels || {}).filter(([, c]) => (c?.breaks || []).length);
      return `<div class="meta-input-block"><div class="meta-input-title">${esc(l.label || "")}</div>
        ${l.classification?.method ? `<div class="rp-muted">${esc(l.classification.method)}</div>` : ""}
        ${statusText(l.classification?.thresholdStatus) ? `<div class="rp-muted">thresholds: ${esc(statusText(l.classification.thresholdStatus))}</div>` : ""}
        ${ch.map(([name, c]) => `<div class="rp-breaks"><span>${esc((l.variableInfo?.[c.column]?.description) || c.column)}</span> <code>${classRanges(c.breaks).map(esc).join(" · ")}</code></div>`).join("")}
      </div>`;
    }).join("")));
  }
  const seen = new Map();
  for (const c of ds.claims || []) for (const s of c.analysis?.procedure || []) if (s.step && !seen.has(s.step)) seen.set(s.step, s);
  if (seen.size) {
    parts.push(section("Procedure, as the record describes it", `<ol class="rp-steps">${[...seen.values()].map((s) => `<li><span class="rp-step">${esc(s.step)}</span>${s.software || s.language ? `<span class="rp-muted"> · ${esc([s.software, s.language].filter(Boolean).join(", "))}</span>` : ""}${s.code ? `<pre class="rp-code">${esc(s.code.trim())}</pre>` : ""}</li>`).join("")}</ol>`));
  }
  const impl = [...new Map((ds.claims || []).filter((c) => c.analysis?.implementation).map((c) => [c.analysis.implementation, c.analysis])).values()];
  if (impl.length) parts.push(section("Implementation", `<ul class="rp-files">${impl.map((a) => `<li>${fileLink(a.implementationUrl, a.implementation, "text/x-python")}</li>`).join("")}</ul>`));
  return parts.join("") || `<p class="rp-empty">The object declares no method.</p>`;
}

// ---- about ---------------------------------------------------------------------------------------------

function aboutTab(ds) {
  const md = ds.metadata || {};
  const src = md.source || {};
  const row = (k, v) => (v ? `<tr><td>${k}</td><td>${v}</td></tr>` : "");
  const authors = (md.authors || []).map((a) => (typeof a === "string" ? { name: a } : a));
  const facts = `<table class="meta-col-table rp-table">
    ${row("Published", esc((md.datePublished || "").slice(0, 10)))}
    ${row("Licence", md.license ? `<a href="${esc(safeUrl(md.license))}" target="_blank" rel="noopener">${esc(licenceName(md.license))}</a>` : "")}
    ${row("Status", esc(md.status || ""))}
    ${row("Identifier", src.pid ? `<span class="rp-pid">${esc(src.pid)}</span>` : "")}
    ${row("Profile", (src.profiles || []).map((p) => `<span class="rp-pid">${esc(p)}</span>`).join("<br>"))}
  </table>`;
  const who = authors.length ? `<ul class="rp-people">${authors.map((a) => `<li>${esc(a.name || "")}${a.affiliation?.name ? ` <span class="rp-muted">${esc(a.affiliation.name)}</span>` : ""}</li>`).join("")}</ul>` : "";
  const basedOn = md.mapFrom ? `<div class="meta-input-block"><div class="meta-input-title">${esc(md.mapFrom.title || md.mapFrom.pid)}</div><div class="rp-muted">${esc(md.mapFrom.status || "")}</div><div class="rp-pid">${esc(md.mapFrom.pid)}</div></div>` : "";
  const records = (ds.evidence || []).map((e) => e.usable
    ? `<div class="meta-input-block"><div class="meta-input-title">${esc(e.title)}</div>
        <div class="rp-muted">${[e.status, (e.date || "").slice(0, 10), (e.authors || []).join(", ")].filter(Boolean).map(esc).join(" · ")}</div>
        ${(e.field || []).length ? `<div class="rp-chips small">${e.field.map((f) => `<span class="rp-chip">${esc(f)}</span>`).join("")}</div>` : ""}
        <div class="rp-pid">${esc(e.pid)}</div></div>`
    : `<div class="meta-input-block"><div class="meta-input-title">${esc(e.pid)}</div><div class="rp-warn">the record could not be read: ${esc((e.why || []).join("; "))}</div></div>`).join("");
  const tiers = (md.files || []).filter((f) => f.accessTier === "restricted");
  const access = tiers.length ? `<ul class="rp-files">${tiers.map((f) => `<li>${esc(f.name || f.id)} <span class="rp-muted">restricted${f.conditionsOfAccess ? ` · ${esc(f.conditionsOfAccess)}` : ""}</span></li>`).join("")}</ul>` : "";
  const warnings = (ds.diagnostics?.warnings || []).filter(Boolean);
  const DIMENSIONS = ["resolution", "validation", "compatibility", "delivery"];
  const statuses = Object.entries(ds.diagnostics?.accessRecord || {}).map(([label, r]) =>
    `<li>${esc(label)}${r.contract ? ` <code>${esc(r.contract)}</code>` : ""}: ${DIMENSIONS.filter((d) => r.statuses?.[d]).map((d) => `${d} ${esc(r.statuses[d])}`).join(" · ")}</li>`);
  const technical = `<details class="rp-analysis"><summary>Technical details</summary>
      ${statuses.length ? `<div class="rp-group">Reader statuses per contract</div><ul class="rp-diag">${statuses.join("")}</ul>` : ""}
      ${warnings.length ? `<div class="rp-group">Notes</div><ul class="rp-diag">${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : `<p class="rp-muted">No notes from the adapters.</p>`}
      <p><a href="capabilities.html">What this dashboard reads</a>: formats, renderers, contracts, and the edits in the objects that change the page without code.</p>
      <p class="rp-muted">Read through ${esc(ds.sourceType || "")}${src.map ? ` with the profile map ${esc(src.map)}` : ""}${src.overlay ? ` and the overlay ${esc(src.overlay)}` : ""}.</p>
    </details>`;
  return `${md.description ? `<p class="rp-desc">${esc(md.description)}</p>` : ""}
    ${facts}
    ${section(`Authors (${authors.length})`, who)}
    ${section("Map drawn from", basedOn)}
    ${section("Records behind the statements", records)}
    ${section("Restricted parts", access)}
    ${technical}`;
}
