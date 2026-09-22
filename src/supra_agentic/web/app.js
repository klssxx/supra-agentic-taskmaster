let currentProjectId = null;
let currentPosture = null;

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function pct(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}

function verdictClass(verdict) {
  if (verdict === "PASS") return "pass";
  if (verdict === "FAIL") return "fail";
  if (verdict === "CONDITIONAL_PASS") return "warn";
  return "neutral";
}

function activateView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(v => v.classList.toggle("active", v.dataset.view === name));
  const target = $("view-" + name);
  if (target) target.classList.add("active");
  if (name !== "dashboard") renderDetailView(name);
}

function renderDetailView(name) {
  const hosts = {
    decomposition: ".decomposition-panel",
    strategies: ".strategies-panel",
    verification: ".validation-panel",
    evidence: ".evidence-panel"
  };
  const host = document.querySelector(`#view-${name} .detail-host`);
  if (host && hosts[name]) {
    const source = document.querySelector(hosts[name]);
    host.replaceChildren(source.cloneNode(true));
    const cloned = host.querySelector(".panel");
    if (cloned) cloned.classList.add("detail-card");
  }
}

function setStatus(stage) {
  $("current-stage").textContent = stage || "STANDBY";
  $("mini-stage").textContent = stage || "STANDBY";
  $("run-status").textContent = stage || "STANDBY";
  $("run-status").className = "status-badge " + (stage === "FAILED" ? "fail" : stage === "COMPLETED" ? "pass" : "neutral");
  if (window.causalCanvasInstance) window.causalCanvasInstance.updateStage(stage, currentPosture);
}

async function runTask() {
  const objective = $("objective-input").value.trim();
  if (!objective) {
    $("objective-input").focus();
    return;
  }

  $("run-btn").disabled = true;
  $("run-btn").textContent = "Ejecutando…";
  setStatus("RECEIVED");
  activateView("dashboard");

  try {
    const response = await fetch("/api/v1/projects", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        objective,
        domain: $("domain-select").value,
        allow_disruptive: $("disruptive-toggle").checked,
        use_model: $("model-toggle").checked
      })
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    currentProjectId = data.project_id;
    renderProject(data.posture);
    await Promise.all([loadProjects(), loadHealth()]);
  } catch (error) {
    setStatus("FAILED");
    $("conclusion-text").textContent = "La ejecución falló: " + error.message;
    $("conclusion-verdict").textContent = "FAILED";
  } finally {
    $("run-btn").disabled = false;
    $("run-btn").textContent = "✦ Ejecutar SUPRA";
  }
}

async function runExample() {
  $("example-btn").disabled = true;
  setStatus("RECEIVED");
  activateView("dashboard");
  try {
    const response = await fetch("/api/v1/examples/quick-run");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    currentProjectId = data.project_id;
    $("objective-input").value = data.posture.objective || "";
    renderProject(data.posture);
    await loadProjects();
  } catch (error) {
    setStatus("FAILED");
    $("conclusion-text").textContent = "El ejemplo falló: " + error.message;
  } finally {
    $("example-btn").disabled = false;
  }
}

function renderProject(posture) {
  if (!posture) return;
  currentPosture = posture;
  currentProjectId = posture.project_id || currentProjectId;
  const decomp = posture.decomposition || {};
  const candidates = Array.isArray(posture.candidates) ? posture.candidates : [];
  const verification = posture.verification || null;
  const sandbox = Array.isArray(posture.sandbox_results) && posture.sandbox_results.length
    ? posture.sandbox_results[posture.sandbox_results.length - 1] : null;
  const checkpoints = Array.isArray(posture.checkpoints) ? posture.checkpoints : [];
  const output = posture.final_output || {};

  $("objective-title").textContent = posture.objective || "Objetivo SUPRA";
  $("objective-subtitle").textContent = decomp.domain
    ? `Dominio ${decomp.domain} · ${candidates.length} estrategias · estado ${posture.stage}`
    : "Descomposición, estrategias, verificación y dossier con trazabilidad.";
  $("mini-project").textContent = currentProjectId || "Proyecto";
  $("mini-objective").textContent = posture.objective || "";
  $("domain-select").value = decomp.domain || $("domain-select").value;
  setStatus(posture.stage);

  renderDecomposition(posture);
  renderStrategies(candidates);
  renderVerification(verification, sandbox);
  renderEvidence(checkpoints);
  renderSandbox(sandbox);
  renderConclusion(verification, posture.stage);

  $("candidate-count").textContent = `${candidates.length} candidatas`;
  $("checkpoint-count").textContent = `${checkpoints.length} eventos`;
  $("decomp-count").textContent = `${(decomp.invariants || []).length} invariantes`;
  $("footer-summary").textContent = `${candidates.length} estrategias · ${checkpoints.length} checkpoints`;
  $("audit-hash").textContent = output.audit_sha256 || "N/A";

  const hasProject = Boolean(currentProjectId);
  $("dossier-btn").disabled = !hasProject;
  $("export-md").disabled = !hasProject;
  $("export-html").disabled = !hasProject;

  if (window.causalCanvasInstance) {
    window.causalCanvasInstance.setPosture(posture);
    $("graph-node-count").textContent = `${window.causalCanvasInstance.nodes.length} nodos`;
  }
}

function renderDecomposition(posture) {
  const decomp = posture.decomposition;
  const box = $("decomposition-tree");
  if (!decomp) {
    box.className = "objective-tree empty-panel";
    box.textContent = "Sin descomposición disponible.";
    return;
  }
  const invariants = decomp.invariants || [];
  const mutable = decomp.mutable_assumptions || [];
  box.className = "objective-tree";
  box.innerHTML = `
    <div class="tree-root"><strong>${esc(decomp.core_objective || posture.objective)}</strong><br><small>${esc(decomp.domain || "general")}</small></div>
    <div class="tree-grid">
      ${invariants.map((item, i) => `<div class="tree-node"><strong>I${i + 1} · Invariante</strong><small>${esc(item)}</small></div>`).join("")}
      ${mutable.map((item, i) => `<div class="tree-node mutable"><strong>M${i + 1} · Supuesto mutable</strong><small>${esc(item)}</small></div>`).join("")}
    </div>`;
}

function renderStrategies(candidates) {
  const body = $("strategies-body");
  if (!candidates.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty-row">Sin estrategias todavía.</td></tr>';
    return;
  }
  body.innerHTML = candidates.map((c, i) => `
    <tr class="${c.is_selected ? "selected-row" : ""}">
      <td>${String(i + 1).padStart(2, "0")}</td>
      <td><strong>${esc(c.pathway_name)}</strong></td>
      <td>${esc(c.paradigm_type)}</td>
      <td class="score">${pct(c.feasibility_score)}</td>
      <td>${pct(c.divergence_score)}</td>
      <td>${c.is_selected ? "SELECCIONADA" : "ALTERNATIVA"}</td>
    </tr>`).join("");
}

function renderVerification(ver, sandbox) {
  const verdict = ver ? ver.verdict : "NOT_EVALUATED";
  $("verification-verdict").textContent = verdict;
  $("verification-verdict").className = "status-badge " + verdictClass(verdict);
  $("verification-confidence").textContent = ver ? pct(ver.confidence_score) : "0%";
  $("sandbox-status").textContent = sandbox ? (sandbox.passed ? "PASS" : "FAIL") : "—";

  const box = $("verification-evidence");
  const evidence = ver && Array.isArray(ver.evidence) ? ver.evidence : [];
  if (!evidence.length) {
    box.className = "check-list empty-panel";
    box.textContent = ver ? esc(ver.rationale || "Sin evidencia por invariante.") : "La evidencia de invariantes aparecerá aquí.";
    return;
  }
  box.className = "check-list";
  box.innerHTML = evidence.map(e => {
    const cls = e.status === "PASS" ? "pass" : e.status === "FAIL" ? "fail" : "unknown";
    const icon = e.status === "PASS" ? "✓" : e.status === "FAIL" ? "×" : "○";
    return `<div class="check-item ${cls}"><b>${icon}</b><span><strong>${esc(e.status)}</strong> · ${esc(e.invariant)}<br><small>${esc(e.test || "")}</small></span></div>`;
  }).join("");
}

function renderSandbox(sb) {
  const box = $("sandbox-detail");
  if (!sb) {
    box.className = "detail-content empty-panel";
    box.textContent = "Sin ejecución de sandbox.";
    return;
  }
  box.className = "detail-content";
  box.innerHTML = `
    <div class="metrics-row">
      <div class="metric-card"><small>Resultado</small><strong>${sb.passed ? "PASS" : "FAIL"}</strong></div>
      <div class="metric-card"><small>Contención declarada</small><strong>${sb.side_effects_contained ? "SÍ" : "NO"}</strong></div>
    </div>
    <div class="hash-card"><small>Tipo de acción</small><code>${esc(sb.action_type)}</code></div>
    <div class="hash-card"><small>Telemetría</small><code>${esc(sb.output_log)}</code></div>
    <div class="hash-card"><small>Duración</small><code>${esc(sb.duration_ms)} ms</code></div>`;
}

function renderEvidence(checkpoints) {
  const box = $("checkpoint-ledger");
  if (!checkpoints.length) {
    box.className = "ledger empty-panel";
    box.textContent = "Sin checkpoints registrados.";
    return;
  }
  box.className = "ledger";
  box.innerHTML = checkpoints.slice().reverse().map(c => {
    const stamp = c.timestamp ? new Date(c.timestamp * 1000).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit", second:"2-digit"}) : "—";
    return `<div class="ledger-row"><time>${esc(stamp)}</time><div><strong>${esc(c.title)}</strong><small>${esc(c.stage)} · ${esc(c.actor)} · ${esc(c.evidence_summary)}</small></div></div>`;
  }).join("");
}

function renderConclusion(ver, stage) {
  const verdict = ver ? ver.verdict : "NOT_EVALUATED";
  $("conclusion-verdict").textContent = verdict;
  if (!ver) {
    $("conclusion-text").textContent = stage === "FAILED"
      ? "La ejecución terminó con error antes de producir una verificación."
      : "Todavía no hay una ejecución evaluada.";
    return;
  }
  if (verdict === "PASS") {
    $("conclusion-text").textContent = `La verificación registrada es PASS con confianza ${pct(ver.confidence_score)}. Consulta la evidencia antes de tratarla como acreditación del sistema real.`;
  } else if (verdict === "CONDITIONAL_PASS") {
    $("conclusion-text").textContent = "Hay evidencia parcial: existen invariantes no evaluados y el resultado no debe interpretarse como verificación completa.";
  } else if (verdict === "FAIL") {
    $("conclusion-text").textContent = "La verificación contiene al menos un fallo. El estado del proyecto y el veredicto se muestran por separado.";
  } else {
    $("conclusion-text").textContent = "No existe evidencia ejecutable suficiente para evaluar todos los invariantes.";
  }
}

async function loadHealth() {
  try {
    const res = await fetch("/health");
    if (!res.ok) throw new Error();
    const data = await res.json();
    const provider = data.provider || {};
    $("provider-name").textContent = provider.name || provider.provider || "configurado";
    $("connection-pill").classList.add("online");
    $("connection-pill").innerHTML = "<i></i> Conectado";
    $("footer-connection").textContent = "● API conectada";
  } catch {
    $("connection-pill").classList.remove("online");
    $("connection-pill").innerHTML = "<i></i> Sin conexión";
    $("footer-connection").textContent = "● API no disponible";
  }
}

async function loadProviders() {
  const grid = $("providers-grid");
  try {
    const res = await fetch("/api/v1/providers");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const providers = data.providers || [];
    grid.className = "provider-grid";
    grid.innerHTML = providers.map(p => `
      <div class="provider-card ${p.configured !== false ? "ok" : ""}">
        <strong>${esc(p.name || "provider")}</strong>
        <small>${p.configured === false ? "No configurado" : "Disponible/configurado"}</small>
        <small>${esc(p.base_url || p.endpoint || p.model || "")}</small>
      </div>`).join("") || '<div class="empty-panel">No hay proveedores declarados.</div>';
  } catch (error) {
    grid.className = "provider-grid empty-panel";
    grid.textContent = "No se pudieron cargar proveedores: " + error.message;
  }
}

async function loadProjects() {
  const grid = $("projects-grid");
  try {
    const res = await fetch("/api/v1/projects?limit=30");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const projects = data.projects || [];
    grid.className = "projects-grid";
    grid.innerHTML = projects.map(p => `
      <div class="project-card" data-project-id="${esc(p.project_id)}">
        <strong>${esc((p.objective || "Sin objetivo").slice(0, 90))}</strong>
        <small>${esc(p.project_id)} · ${esc(p.stage)}</small>
        <small>${p.verification ? "Veredicto: " + esc(p.verification.verdict) : "Sin verificación"}</small>
      </div>`).join("") || '<div class="empty-panel">No hay proyectos persistidos.</div>';
    grid.querySelectorAll(".project-card").forEach(card => card.addEventListener("click", () => loadProject(card.dataset.projectId)));
  } catch (error) {
    grid.className = "projects-grid empty-panel";
    grid.textContent = "No se pudieron cargar proyectos: " + error.message;
  }
}

async function loadProject(id) {
  try {
    const res = await fetch("/api/v1/projects/" + encodeURIComponent(id));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentProjectId = data.project_id || id;
    $("objective-input").value = data.posture.objective || "";
    renderProject(data.posture);
    activateView("dashboard");
  } catch (error) {
    $("conclusion-text").textContent = "No se pudo cargar el proyecto: " + error.message;
  }
}

async function exportMarkdown() {
  if (!currentProjectId) return;
  const res = await fetch("/api/v1/export/dossier/" + encodeURIComponent(currentProjectId));
  if (!res.ok) return;
  const data = await res.json();
  const text = data.markdown_dossier || data.dossier || JSON.stringify(data, null, 2);
  const blob = new Blob([text], {type:"text/markdown"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `SUPRA_DOSSIER_${currentProjectId}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function openHtmlDossier() {
  if (!currentProjectId) return;
  window.open("/api/v1/export/dossier/html/" + encodeURIComponent(currentProjectId), "_blank", "noopener");
}

function wireUI() {
  document.querySelectorAll(".nav-item").forEach(btn => btn.addEventListener("click", () => activateView(btn.dataset.view)));
  $("run-btn").addEventListener("click", runTask);
  $("example-btn").addEventListener("click", runExample);
  $("dossier-btn").addEventListener("click", () => activateView("dossiers"));
  $("export-md").addEventListener("click", exportMarkdown);
  $("export-html").addEventListener("click", openHtmlDossier);
  $("refresh-providers").addEventListener("click", loadProviders);
  $("refresh-projects").addEventListener("click", loadProjects);
  $("global-search").addEventListener("input", (event) => {
    const q = event.target.value.trim().toLowerCase();
    document.querySelectorAll(".project-card").forEach(card => {
      card.style.display = !q || card.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
  $("global-search").addEventListener("focus", () => {
    if (!$("view-projects").classList.contains("active")) activateView("projects");
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  wireUI();
  await Promise.all([loadHealth(), loadProviders(), loadProjects()]);
});
