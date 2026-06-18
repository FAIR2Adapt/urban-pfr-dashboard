import { state } from "../state.js";
import { $, esc } from "./dom.js";

export function wireMetadataToggle() {
  const btn = $("metaToggle");
  const overlay = $("metaOverlay");
  btn?.addEventListener("click", () => {
    state.showMeta = !state.showMeta;
    btn.classList.toggle("active", state.showMeta);
    btn.setAttribute("aria-pressed", String(state.showMeta));
    overlay?.classList.toggle("hidden", !state.showMeta);
    if (state.showMeta) refreshMetadataPanel();
  });
  $("metaClose")?.addEventListener("click", () => {
    state.showMeta = false;
    btn?.classList.remove("active");
    btn?.setAttribute("aria-pressed", "false");
    overlay?.classList.add("hidden");
  });
}

export function setMetadataAvailable(available) {
  const section = $("metadataSection");
  if (section) section.style.display = available ? "" : "none";
  if (!available) {
    state.showMeta = false;
    $("metaToggle")?.classList.remove("active");
    $("metaToggle")?.setAttribute("aria-pressed", "false");
    $("metaOverlay")?.classList.add("hidden");
  }
}

export function refreshMetadataPanel() {
  const panel = $("metaContent");
  if (!panel) return;
  const ids = state.selectedSourceIds.filter((id) => state.datasets[id]);

  if (!ids.length) {
    panel.innerHTML = `<div class="meta-notice"><p>No metadata for this source.</p></div>`;
    return;
  }

  if (ids.length === 1) {
    panel.innerHTML = renderMetadata(state.datasets[ids[0]]);
  } else {

    panel.innerHTML =
      `<div class="meta-section-hdr">Selected sources (${ids.length})</div>` +
      ids
        .map(
          (id) =>
            `<div style="margin:0 0 16px;padding-bottom:14px;border-bottom:2px solid var(--border)">
               <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:6px">
                 ${esc(sourceName(id))}
               </div>
               ${renderMetadata(state.datasets[id])}
             </div>`
        )
        .join("");
  }

  const toggle = $("rawToggle");
  const pre = $("rawJson");
  toggle?.addEventListener("click", () => {
    pre?.classList.toggle("hidden");
    toggle.textContent = pre?.classList.contains("hidden")
      ? "Show raw JSON-LD ▾"
      : "Hide raw JSON-LD ▴";
  });
}

function sourceName(id) {
  return state.sources.find((s) => s.id === id)?.label || state.datasets[id]?.label || id;
}

function row(label, value) {
  return value != null && value !== ""
    ? `<tr><td style="color:#64748b;padding:2px 4px">${label}</td>
         <td style="text-align:right;font-weight:600">${esc(value)}</td></tr>`
    : "";
}

function section(title, bodyHtml) {
  return bodyHtml ? `<div class="meta-section-hdr">${title}</div>${bodyHtml}` : "";
}

function renderMetadata(ds) {
  const md = ds.metadata || {};
  const src = md.source || {};
  const authors = (md.authors || []).map((a) => (typeof a === "string" ? { name: a } : a));

  const provenance = `<table class="meta-col-table">
      ${row("License", md.license)}
      ${row("Published", (md.datePublished || "").slice(0, 10))}
      ${row("Status", md.status)}
      ${row("Publisher", md.publisher?.name)}
      ${row("Adapter", ds.sourceType)}
    </table>`;

  const authorsHtml = authors.length
    ? `<ul style="margin:0;padding-left:16px;font-size:.82rem">${authors
        .slice(0, 30)
        .map((a) => {
          const aff = a.affiliation?.name
            ? ` — <span style="color:#64748b">${esc(a.affiliation.name)}</span>`
            : "";
          const orcid = a.orcid
            ? ` <a href="${esc(a.orcid)}" target="_blank" rel="noopener" style="font-size:.7rem">ORCID</a>`
            : "";
          return `<li>${esc(a.name || "")}${aff}${orcid}</li>`;
        })
        .join("")}</ul>`
    : "";

  const claims = (ds.claims || []).length
    ? ds.claims
        .map((c) => {
          const wf = c.workflow || {};
          const sw = wf.software
            ? `<code>${esc(wf.software)} v${esc(wf.softwareVersion || "?")}</code> · `
            : "";
          const ops = (wf.operations || []).join(", ");
          return `<div class="meta-input-block">
            <div class="meta-input-title">${esc(c.label || c.id)}</div>
            <div style="font-size:.74rem;color:#64748b">
              ${sw}${(c.inputs || []).length} inputs · ${(c.outputs || []).length} outputs
            </div>
            ${ops ? `<div style="font-size:.72rem;color:#64748b;margin-top:3px">ops: ${esc(ops)}</div>` : ""}
          </div>`;
        })
        .join("")
    : "";

  const figures = (ds.figures || []).length
    ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px">${ds.figures
        .map((f) => {
          const url = f.localPath || f.sourceUrl;
          if (!url) return "";
          return `<a href="${esc(url)}" target="_blank" rel="noopener"
              style="display:block;border:1px solid var(--border);border-radius:4px;overflow:hidden">
              <img src="${esc(url)}" alt="${esc(f.id)}" loading="lazy"
                   style="width:100%;display:block"
                   onerror="this.parentElement.style.display='none'"/></a>`;
        })
        .join("")}</div>`
    : "";

  const concepts = (md.concepts || []).length
    ? `<ul style="margin:0;padding-left:16px;font-size:.8rem">${md.concepts
        .map(
          (c) =>
            `<li><b>${esc(c.label)}</b>${
              c.definition ? ` — <span style="color:#64748b">${esc(c.definition)}</span>` : ""
            }</li>`
        )
        .join("")}</ul>`
    : "";

  const statementsList = Array.isArray(md.statements) ? md.statements : [];
  const statements = statementsList.length
    ? `<ul style="margin:0;padding-left:16px;font-size:.8rem">${statementsList
        .map((s) => `<li>${esc(s.label || s.id)}</li>`)
        .join("")}</ul>`
    : "";

  const stats = src.stats || {};
  const statsHtml = Object.keys(stats).length
    ? `<table class="meta-col-table">
         ${row("Buildings", stats.n_buildings?.toLocaleString?.())}
         ${row("Displayed PFR points", stats.n_displayed?.toLocaleString?.())}
         ${row("RIMA mean", stats.rima_mean)}
         ${row("RIWB mean", stats.riwb_mean)}
       </table>`
    : "";

  const jsonld = src.statements && !Array.isArray(src.statements) ? src.statements : null;
  const rawHtml =
    jsonld && Object.keys(jsonld).length
      ? `<div class="meta-raw-toggle" id="rawToggle">Show raw JSON-LD ▾</div>
         <pre class="meta-raw hidden" id="rawJson">${esc(JSON.stringify(jsonld, null, 2))}</pre>`
      : "";

  const warnings = (ds.diagnostics?.warnings || []).filter(Boolean);
  const diagnostics = warnings.length
    ? `<ul style="margin:0;padding-left:16px;font-size:.76rem;color:var(--amber)">${warnings
        .map((w) => `<li>${esc(w)}</li>`)
        .join("")}</ul>`
    : "";

  return `
    <div class="meta-header-row">
      <span class="meta-jsonld-badge">Dataset</span>
      <span class="meta-fig-badge">${esc(ds.sourceType || "")}</span>
    </div>
    <p class="meta-label">${esc(md.title || ds.label || "")}</p>
    ${md.description ? `<p style="color:var(--text-secondary);font-size:.82rem">${esc(md.description)}</p>` : ""}

    ${section("Provenance", provenance)}
    ${section(`Authors (${authors.length})`, authorsHtml)}
    ${section("Claims", claims)}
    ${section("Preview figures", figures)}
    ${section("Key concepts", concepts)}
    ${section("Statements", statements)}
    ${section("Statistics", statsHtml)}
    ${section("Diagnostics", diagnostics)}
    ${rawHtml}
  `;
}
