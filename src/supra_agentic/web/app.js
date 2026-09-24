let currentProjectId = null;
let currentPosture = null;

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pct(value) {
  if (value === null || value === undefined) return "NOT_AVAILABLE";
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n * 100) + "%" : "NOT_AVAILABLE";
}

function verdictClass(verdict) {
  if (verdict === "PASS") return "pass";
  if (verdict === "FAIL") return "fail";
  if (verdict === "CONDITIONAL_PASS") return "warn";
  return "neutral";
}

function activateView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((v) => {
    v.classList.toggle("active", v.dataset.view === name);
  });
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
  const host = document.querySelector("#view-" + name + " .detail-host");
  if (!host || !hosts[name]) return;
  const source = document.querySelector(hosts[name]);
  if (!source) return;
  host.replaceChildren(source.cloneNode(true));
  const cloned = host.querySelector(".panel");
  if (cloned) cloned.classList.add("detail-card");
}

function setStatus(stage) {
  const value = stage || "STANDBY";
  $("current-stage").textContent = value;
  $("mini-stage").textContent = value;
  $("run-status").textContent = value;
  $("run-status").className = "status-badge " +
    (value === "FAILED" ? "fail" : value === "COMPLETED" ? "pass" : "neutral");
  if (window.causalCanvasInstance) {
    window.causalCanvasInstance.updateStage(value, currentPosture);
  }
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
        objective: objective,
        domain: $("domain-select").value,
        allow_disruptive: $("disruptive-toggle").checked,
        use_model: $("model-toggle").checked
      })
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || ("HTTP " + response.status));
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
    if (!response.ok) throw new Error("HTTP " + response.status);
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

function latest(items) {
  return Array.isArray(items) && items.length ? items[items.length - 1] : null;
}

function renderProject(posture) {
  if (!posture) return;
  currentPosture = posture;
  currentProjectId = posture.project_id || currentProjectId;

  const decomp = posture.decomposition || {};
  const candidates = Array.isArray(posture.candidates) ? posture.candidates : [];
  const verification = posture.verification || null;
  const restricted = latest(posture.restricted_execution_results);
  const secure = latest(posture.secure_sandbox_results);
  const checkpoints = Array.isArray(posture.checkpoints) ? posture.checkpoints : [];
  const output = posture.final_output || {};

  $("objective-title").textContent = posture.objective || "Objetivo SUPRA";
  $("objective-subtitle").textContent = decomp.domain
    ? "Dominio " + decomp.domain + " · " + candidates.length + " estrategias · workflow " + (posture.stage || "UNKNOWN")
    : "Descomposición, estrategias, verificación, ejecución acotada y dossier con trazabilidad.";
  $("mini-project").textContent = currentProjectId || "Proyecto";
  $("mini-objective").textContent = posture.objective || "";
  $("domain-select").value = decomp.domain || $("domain-select").value;
  setStatus(posture.stage);

  renderDecomposition(posture);
  renderStrategies(candidates);
  renderVerification(verification, restricted, secure);
  renderEvidence(checkpoints);
  renderSandbox(restricted, secure);
  renderConclusion(verification, posture.stage, output, secure);

  $("candidate-count").textContent = candidates.length + " candidatas";
  $("checkpoint-count").textContent = checkpoints.length + " eventos";
  $("decomp-count").textContent = (decomp.invariants || []).length + " invariantes";
  $("footer-summary").textContent = candidates.length + " estrategias · " + checkpoints.length + " checkpoints";
  $("audit-hash").textContent = output.audit_sha256 || "NOT_AVAILABLE";

  const hasProject = Boolean(currentProjectId);
  $("dossier-btn").disabled = !hasProject;
  $("export-md").disabled = !hasProject;
  $("export-html").disabled = !hasProject;

  if (window.causalCanvasInstance) {
    window.causalCanvasInstance.setPosture(posture);
    $("graph-node-count").textContent = window.causalCanvasInstance.nodes.length + " nodos";
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

  const invariants = Array.isArray(decomp.invariants) ? decomp.invariants : [];
  const mutable = Array.isArray(decomp.mutable_assumptions) ? decomp.mutable_assumptions : [];
  const root = escapeHtml(decomp.core_objective || posture.objective);
  escapeHtml(posture.objective);

  box.className = "objective-tree";
  box.innerHTML =
    '<div class="tree-root"><strong>' + root + '</strong><br><small>' +
    escapeHtml(decomp.domain || "general") + '</small></div>' +
    '<div class="tree-grid">' +
    invariants.map((item, i) =>
      '<div class="tree-node"><strong>I' + (i + 1) + ' · Invariante</strong><small>' +
      escapeHtml(item) + '</small></div>'
    ).join("") +
    mutable.map((item, i) =>
      '<div class="tree-node mutable"><strong>M' + (i + 1) + ' · Supuesto mutable</strong><small>' +
      escapeHtml(item) + '</small></div>'
    ).join("") +
    '</div>';
}

function renderStrategies(candidates) {
  const body = $("strategies-body");
  if (!candidates.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty-row">Sin estrategias todavía.</td></tr>';
    return;
  }

  body.innerHTML = candidates.map((c, i) =>
    '<tr class="' + (c.is_selected ? "selected-row" : "") + '">' +
      '<td>' + String(i + 1).padStart(2, "0") + '</td>' +
      '<td><strong>' + escapeHtml(c.pathway_name || "NOT_SPECIFIED") + '</strong>' +
      '<small title="' + escapeHtml(c.hypothesis) + '">' + escapeHtml(c.hypothesis || "NOT_SPECIFIED") + '</small></td>' +
      '<td>' + escapeHtml(c.paradigm_type || "NOT_SPECIFIED") + '</td>' +
      '<td class="score">' + pct(c.feasibility_score) + '</td>' +
      '<td>' + pct(c.divergence_score) + '</td>' +
      '<td>' + (c.is_selected ? "SELECCIONADA" : "ALTERNATIVA") + '</td>' +
    '</tr>'
  ).join("");
}

function restrictedStatus(result) {
  if (!result) return "NOT_RUN";
  if (result.passed && result.identity_bound) return "IDENTITY_BOUND_PASS";
  if (result.passed) return "UNBOUND_PASS";
  return result.observed_result || "FAIL";
}

function secureStatus(result) {
  if (!result) return "NOT_RUN";
  if (result.passed && result.identity_bound && result.isolation_verified) {
    return "IDENTITY_BOUND_ISOLATION_PASS";
  }
  if (result.identity_bound && result.isolation_verified) {
    return "IDENTITY_BOUND_ISOLATION_FAIL";
  }
  return "UNVERIFIED_ISOLATION";
}

function renderVerification(ver, restricted, secure) {
  const verdict = ver ? ver.verdict : "NOT_EVALUATED";
  $("verification-verdict").textContent = verdict;
  $("verification-verdict").className = "status-badge " + verdictClass(verdict);
  $("verification-confidence").textContent = ver ? pct(ver.confidence_score) : "NOT_AVAILABLE";
  $("restricted-status").textContent = restrictedStatus(restricted);
  $("sandbox-status").textContent = secureStatus(secure);

  const box = $("verification-evidence");
  const evidence = ver && Array.isArray(ver.evidence) ? ver.evidence : [];
  if (!evidence.length) {
    box.className = "check-list empty-panel";
    box.textContent = ver
      ? (ver.rationale || "Sin evidencia por invariante.")
      : "NOT_EVALUATED — no existe evaluación de cobertura para mostrar.";
    return;
  }

  box.className = "check-list";
  box.innerHTML = evidence.map((e) => {
    const status = e.status || "NOT_EVALUATED";
    const cls = status === "PASS" ? "pass" : status === "FAIL" ? "fail" : "unknown";
    const icon = status === "PASS" ? "✓" : status === "FAIL" ? "×" : "○";
    return '<div class="check-item ' + cls + '"><b>' + icon + '</b><span><strong>' +
      escapeHtml(status) + '</strong> · ' + escapeHtml(e.invariant || "NOT_SPECIFIED") +
      '<br><small>' + escapeHtml(e.test || "NOT_SPECIFIED") + '</small></span></div>';
  }).join("");
}

function renderSandbox(restricted, secure) {
  const box = $("sandbox-detail");
  if (!restricted && !secure) {
    box.className = "detail-content empty-panel";
    box.textContent = "Sin restricted preflight ni secure-sandbox receipt.";
    return;
  }

  box.className = "detail-content";
  const restrictedHtml = restricted
    ? '<div class="hash-card"><small>Restricted preflight</small><code>' +
      escapeHtml(restrictedStatus(restricted)) +
      ' · identity_bound=' + escapeHtml(Boolean(restricted.identity_bound)) +
      ' · scope=' + escapeHtml(restricted.result_scope || "RESTRICTED_EXECUTION_ONLY") +
      '</code></div>'
    : '<div class="hash-card"><small>Restricted preflight</small><code>NOT_RUN</code></div>';

  const secureHtml = secure
    ? '<div class="hash-card"><small>Secure sandbox smoke</small><code>' +
      escapeHtml(secureStatus(secure)) +
      ' · scope=' + escapeHtml(secure.execution_scope || "NOT_SPECIFIED") +
      ' · security_scope=' + escapeHtml(secure.security_scope || "NOT_SPECIFIED") +
      '</code></div>' +
      '<div class="hash-card"><small>Candidate mechanism executed</small><code>' +
      escapeHtml(Boolean(secure.candidate_mechanism_executed)) +
      ' — isolation smoke is not scientific validation</code></div>' +
      '<div class="hash-card"><small>Backend / image identity</small><code>' +
      escapeHtml(secure.backend || "NOT_SPECIFIED") + ' · ' +
      escapeHtml(secure.image_id || "NOT_AVAILABLE") + '</code></div>'
    : '<div class="hash-card"><small>Secure sandbox smoke</small><code>NOT_RUN</code></div>';

  box.innerHTML = restrictedHtml + secureHtml;
}

function renderEvidence(checkpoints) {
  const box = $("checkpoint-ledger");
  if (!checkpoints.length) {
    box.className = "ledger empty-panel";
    box.textContent = "Sin checkpoints registrados.";
    return;
  }

  box.className = "ledger";
  box.innerHTML = checkpoints.slice().reverse().map((chk) => {
    const stamp = chk.timestamp
      ? new Date(chk.timestamp * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"})
      : "NOT_AVAILABLE";
    return '<div class="ledger-row"><time>' + escapeHtml(stamp) + '</time><div><strong>' +
      escapeHtml(chk.title || "NOT_SPECIFIED") + '</strong><small>' +
      escapeHtml(chk.stage || "NOT_SPECIFIED") + ' · ' +
      escapeHtml(chk.actor || "NOT_SPECIFIED") + ' · ' +
      escapeHtml(chk.evidence_summary) +
      '</small></div></div>';
  }).join("");
}

function renderConclusion(ver, stage, output, secure) {
  const verdict = ver ? ver.verdict : "NOT_EVALUATED";
  const scientific = output && output.scientific_status ? output.scientific_status : "NOT_VALIDATED";
  $("conclusion-verdict").textContent = verdict;

  if (!ver) {
    $("conclusion-text").textContent = stage === "FAILED"
      ? "El workflow terminó con error antes de producir una verificación."
      : "No existe una evaluación de cobertura ejecutada.";
    return;
  }

  const scope = ver.verification_scope || "TEXTUAL_STRATEGY_COVERAGE";
  const completion = stage === "COMPLETED" ? "Workflow COMPLETED." : "Workflow no completado.";
  const isolation = secure ? secureStatus(secure) : "NOT_RUN";
  $("conclusion-text").textContent =
    completion + " Verificación " + verdict + " bajo " + scope +
    ". Secure sandbox: " + isolation +
    ". Scientific status: " + scientific +
    ". Ninguno de estos estados se promueve automáticamente a validación científica.";
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
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const providers = data.providers || [];
    grid.className = "provider-grid";
    grid.innerHTML = providers.map((p) =>
      '<div class="provider-card ' + (p.configured !== false ? "ok" : "") + '">' +
      '<strong>' + escapeHtml(p.name || "provider") + '</strong>' +
      '<small>' + (p.configured === false ? "No configurado" : "Disponible/configurado") + '</small>' +
      '<small>' + escapeHtml(p.base_url || p.endpoint || p.model || "") + '</small></div>'
    ).join("") || '<div class="empty-panel">No hay proveedores declarados.</div>';
  } catch (error) {
    grid.className = "provider-grid empty-panel";
    grid.textContent = "No se pudieron cargar proveedores: " + error.message;
  }
}

async function loadProjects() {
  const grid = $("projects-grid");
  try {
    const res = await fetch("/api/v1/projects?limit=30");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const projects = data.projects || [];
    grid.className = "projects-grid";
    grid.replaceChildren();

    if (!projects.length) {
      grid.textContent = "No hay proyectos persistidos.";
      return;
    }

    projects.forEach((p) => {
      const card = document.createElement("div");
      card.className = "project-card";
      card.dataset.projectId = String(p.project_id || "");
      const title = document.createElement("strong");
      title.textContent = String(p.objective || "Sin objetivo").slice(0, 90);
      const stage = document.createElement("small");
      stage.textContent = String(p.project_id || "NOT_SPECIFIED") + " · " + String(p.stage || "UNKNOWN");
      const verification = document.createElement("small");
      verification.textContent = p.verification
        ? "Verificación: " + String(p.verification.verdict || "NOT_EVALUATED")
        : "Verificación: NOT_EVALUATED";
      card.append(title, stage, verification);
      card.addEventListener("click", () => loadProject(card.dataset.projectId));
      grid.appendChild(card);
    });
  } catch (error) {
    grid.className = "projects-grid empty-panel";
    grid.textContent = "No se pudieron cargar proyectos: " + error.message;
  }
}

async function loadProject(id) {
  try {
    const res = await fetch("/api/v1/projects/" + encodeURIComponent(id));
    if (!res.ok) throw new Error("HTTP " + res.status);
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
  const dossier = data.markdown_dossier || data.dossier || JSON.stringify(data, null, 2);
  const blob = new Blob([dossier], {type: "text/markdown"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "SUPRA_DOSSIER_" + currentProjectId + ".md";
  anchor.click();
  URL.revokeObjectURL(url);
}

function openHtmlDossier() {
  if (!currentProjectId) return;
  window.open(
    "/api/v1/export/dossier/html/" + encodeURIComponent(currentProjectId),
    "_blank",
    "noopener"
  );
}

function wireUI() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => activateView(btn.dataset.view));
  });
  $("run-btn").addEventListener("click", runTask);
  $("example-btn").addEventListener("click", runExample);
  $("dossier-btn").addEventListener("click", () => activateView("dossiers"));
  $("export-md").addEventListener("click", exportMarkdown);
  $("export-html").addEventListener("click", openHtmlDossier);
  $("refresh-providers").addEventListener("click", loadProviders);
  $("refresh-projects").addEventListener("click", loadProjects);
  $("global-search").addEventListener("input", (event) => {
    const q = event.target.value.trim().toLowerCase();
    document.querySelectorAll(".project-card").forEach((card) => {
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
