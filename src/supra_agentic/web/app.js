/**
 * SUPRA Agentic Taskmaster - Frontend Orchestrator v2.5
 */

let currentProjectId = null;

async function handleRunTask(event) {
    event.preventDefault();
    const objective = document.getElementById('objective-input').value.trim();
    const domain = document.getElementById('domain-select').value;
    const allowDisruptive = document.getElementById('disruptive-toggle').checked;
    
    if (!objective) return;

    setUIState('RUNNING', 'RECEIVED');
    
    try {
        const response = await fetch('/api/v1/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                objective: objective,
                domain: domain,
                allow_disruptive: allowDisruptive
            })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Execution failed');
        }

        const data = await response.json();
        currentProjectId = data.project_id;
        renderProjectPosture(data.posture);
        loadRecentProjects();
    } catch (exc) {
        alert('Execution Error: ' + exc.message);
        setUIState('STANDBY', 'FAILED');
    }
}

async function handleExampleRun() {
    setUIState('RUNNING', 'RECEIVED');
    
    try {
        const response = await fetch('/api/v1/examples/quick-run');
        if (!response.ok) throw new Error('Example endpoint failed');
        
        const data = await response.json();
        currentProjectId = data.project_id;
        document.getElementById('objective-input').value = data.posture.objective;
        renderProjectPosture(data.posture);
        loadRecentProjects();
    } catch (exc) {
        alert('Example Error: ' + exc.message);
        setUIState('STANDBY', 'FAILED');
    }
}

function setUIState(status, stage, posture) {
    const stageTag = document.getElementById('current-stage-tag');
    stageTag.innerText = stage || status;
    
    const steps = ['received', 'structured', 'stratified', 'sandbox', 'completed'];
    const stageOrder = {
        'RECEIVED': 0,
        'STRUCTURED': 1,
        'STRATIFIED': 2,
        'SANDBOX_VERIFIED': 3,
        'COMPLETED': 4
    };

    const currentIdx = stageOrder[stage] !== undefined ? stageOrder[stage] : 0;

    steps.forEach((s, idx) => {
        const el = document.getElementById(`step-${s}`);
        if (!el) return;
        el.classList.remove('active', 'completed');
        if (idx < currentIdx) {
            el.classList.add('completed');
        } else if (idx === currentIdx) {
            el.classList.add('active');
        }
    });

    if (window.causalCanvasInstance) {
        window.causalCanvasInstance.updateStage(stage, posture);
    }
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function renderProjectPosture(posture) {
    setUIState('COMPLETED', posture.stage, posture);
    
    const container = document.getElementById('output-container');
    const decomp = posture.decomposition;
    const cand = posture.selected_candidate;
    const ver = posture.verification;
    const sb = posture.sandbox_results && posture.sandbox_results[posture.sandbox_results.length - 1];
    const out = posture.final_output;

    let html = `
        <div class="result-section">
            <h4>01. Deconstructed Invariants & Mutable Assumptions</h4>
            <div style="font-size: 0.85rem; margin-bottom: 0.5rem;">
                <strong>Domain:</strong> <span class="mono-text">${escapeHtml(decomp ? decomp.domain : 'general')}</span> | 
                <strong>Objective:</strong> ${escapeHtml(posture.objective)}
            </div>
            <div class="invariants-grid">
                ${decomp ? decomp.invariants.map(inv => `
                    <div style="font-size: 0.8rem; color: #10B981;">&check; [INVARIANT] ${escapeHtml(inv)}</div>
                `).join('') : ''}
                ${decomp ? decomp.mutable_assumptions.map(mut => `
                    <div style="font-size: 0.8rem; color: #94A3B8;">&bull; [MUTABLE ASSUMPTION CHALLENGED] <span style="text-decoration: line-through;">${escapeHtml(mut)}</span></div>
                `).join('') : ''}
            </div>
        </div>

        <div class="result-section">
            <h4>02. Multi-Paradigm Candidate Pathways</h4>
            <div class="candidates-grid">
                ${posture.candidates ? posture.candidates.map(c => `
                    <div class="candidate-card ${c.is_selected ? 'selected' : ''}">
                        <div class="candidate-header">
                            <span>${escapeHtml(c.pathway_name)}</span>
                            <span class="badge ${c.is_selected ? 'badge-primary' : ''}">${escapeHtml(c.paradigm_type)}</span>
                        </div>
                        <p style="font-size: 0.8rem; color: #94A3B8; margin-bottom: 0.35rem;">${escapeHtml(c.hypothesis)}</p>
                        <div class="candidate-meta mono-text">
                            Feasibility: ${(c.feasibility_score * 100).toFixed(0)}% | Divergence: ${(c.divergence_score * 100).toFixed(0)}%
                        </div>
                    </div>
                `).join('') : ''}
            </div>
        </div>

        <div class="result-section">
            <h4>03. System Verification & Micro-Sandbox Telemetry</h4>
            <div style="font-size: 0.85rem;">
                <strong>Verdict:</strong> <span style="color: #10B981; font-weight: 700;">${escapeHtml(ver ? ver.verdict : 'NOT_EVALUATED')}</span> 
                (Confidence: ${ver ? (ver.confidence_score * 100).toFixed(1) : 'n/a'}%)
            </div>
            <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 0.25rem;">
                ${escapeHtml(ver ? ver.rationale : 'No verification recorded.')}
            </div>
            ${sb ? `
                <div style="background: #000; padding: 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.75rem; color: #00FFCC; margin-top: 0.5rem;">
                    [SANDBOX ${sb.passed ? 'PASS' : 'FAIL'}] ${escapeHtml(sb.output_log)} (${sb.duration_ms}ms)
                </div>
            ` : ''}
        </div>

        <div class="result-section">
            <h4>04. Empirical Falsification Hypothesis (H0)</h4>
            <div style="font-size: 0.8rem; color: #F59E0B; background: rgba(245, 158, 11, 0.08); padding: 0.6rem; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.2);">
                <strong>Falsifiable Null Hypothesis:</strong> ${escapeHtml(out && out.null_hypothesis_h0 ? out.null_hypothesis_h0 : 'H0 not declared.')}
            </div>
        </div>

        <div class="result-section" style="border-bottom: none;">
            <h4>05. Checkpoint Audit Ledger</h4>
            <div style="font-size: 0.75rem; color: #94A3B8;">
                ${posture.checkpoints.map(chk => `
                    <div>&bull; <strong>[${escapeHtml(chk.stage)}]</strong> <code>${escapeHtml(chk.actor)}</code>: ${escapeHtml(chk.title)} — <em>${escapeHtml(chk.evidence_summary)}</em></div>
                `).join('')}
            </div>
        </div>
    `;

    container.innerHTML = html;

    // Show Export Bar
    const exportBar = document.getElementById('export-bar');
    exportBar.style.display = 'flex';
    document.getElementById('final-audit-hash').innerText = out && out.audit_sha256 ? out.audit_sha256 : 'N/A';
}

async function handleExportDossier() {
    if (!currentProjectId) return;
    try {
        const res = await fetch(`/api/v1/export/dossier/${encodeURIComponent(currentProjectId)}`);
        const data = await res.json();
        
        const blob = new Blob([data.markdown_dossier], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `SUPRA_DOSSIER_${currentProjectId}.md`;
        a.click();
    } catch (exc) {
        alert('Export error: ' + exc.message);
    }
}

async function handleExportHtmlDossier() {
    if (!currentProjectId) return;
    window.open(`/api/v1/export/dossier/html/${encodeURIComponent(currentProjectId)}`, '_blank');
}

async function loadRecentProjects() {
    try {
        const res = await fetch('/api/v1/projects?limit=5');
        const data = await res.json();
        const list = document.getElementById('recent-list');
        if (!data.projects || data.projects.length === 0) return;
        
        list.replaceChildren(...data.projects.map(p => {
            const item = document.createElement('div');
            item.className = 'recent-item';
            const label = document.createElement('span');
            label.textContent = `${p.objective.substring(0, 35)}...`;
            const stage = document.createElement('span');
            stage.className = 'mono-text';
            stage.style.color = '#00FFCC';
            stage.textContent = p.stage;
            item.append(label, stage);
            item.addEventListener('click', () => loadProjectById(p.project_id));
            return item;
        }));
    } catch (e) {
        // Ignore
    }
}

async function loadProjectById(id) {
    try {
        const res = await fetch(`/api/v1/projects/${encodeURIComponent(id)}`);
        const data = await res.json();
        currentProjectId = id;
        document.getElementById('objective-input').value = data.posture.objective;
        renderProjectPosture(data.posture);
    } catch (e) {
        alert('Load error');
    }
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    loadRecentProjects();
});
