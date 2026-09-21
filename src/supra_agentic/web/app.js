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
    
    const steps = ['received', 'structured', 'stratified', 'restricted', 'completed'];
    const stageOrder = {
        'RECEIVED': 0,
        'STRUCTURED': 1,
        'STRATIFIED': 2,
        'RESTRICTED_EXECUTION_VERIFIED': 3,
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

function renderProjectPosture(posture) {
    setUIState('COMPLETED', posture.stage, posture);
    
    const container = document.getElementById('output-container');
    const decomp = posture.decomposition;
    const cand = posture.selected_candidate;
    const ver = posture.verification;
    const rex = posture.restricted_execution_results && posture.restricted_execution_results[posture.restricted_execution_results.length - 1];
    const out = posture.final_output;

    let html = `
        <div class="result-section">
            <h4>01. Deconstructed Invariants & Mutable Assumptions</h4>
            <div style="font-size: 0.85rem; margin-bottom: 0.5rem;">
                <strong>Domain:</strong> <span class="mono-text">${decomp ? decomp.domain : 'general'}</span> | 
                <strong>Objective:</strong> ${posture.objective}
            </div>
            <div class="invariants-grid">
                ${decomp ? decomp.invariants.map(inv => `
                    <div style="font-size: 0.8rem; color: #10B981;">&check; [INVARIANT] ${inv}</div>
                `).join('') : ''}
                ${decomp ? decomp.mutable_assumptions.map(mut => `
                    <div style="font-size: 0.8rem; color: #94A3B8;">&bull; [MUTABLE ASSUMPTION CHALLENGED] <span style="text-decoration: line-through;">${mut}</span></div>
                `).join('') : ''}
            </div>
        </div>

        <div class="result-section">
            <h4>02. Multi-Paradigm Candidate Pathways</h4>
            <div class="candidates-grid">
                ${posture.candidates ? posture.candidates.map(c => `
                    <div class="candidate-card ${c.is_selected ? 'selected' : ''}">
                        <div class="candidate-header">
                            <span>${c.pathway_name}</span>
                            <span class="badge ${c.is_selected ? 'badge-primary' : ''}">${c.paradigm_type}</span>
                        </div>
                        <p style="font-size: 0.8rem; color: #94A3B8; margin-bottom: 0.35rem;">${c.hypothesis}</p>
                        <div class="candidate-meta mono-text">
                            Feasibility: ${(c.feasibility_score * 100).toFixed(0)}% | Divergence: ${(c.divergence_score * 100).toFixed(0)}%
                        </div>
                    </div>
                `).join('') : ''}
            </div>
        </div>

        <div class="result-section">
            <h4>03. Strategy Coverage & Restricted Execution Telemetry</h4>
            <div style="font-size: 0.85rem;">
                <strong>Coverage Verdict:</strong> <span style="font-weight: 700;">${ver ? ver.verdict : 'NOT_EVALUATED'}</span>
                (Coverage fraction: ${ver ? (ver.confidence_score * 100).toFixed(1) + '%' : 'N/A'})
            </div>
            <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 0.25rem;">
                ${ver ? ver.rationale : 'No strategy-coverage evaluation is available.'}
            </div>
            ${rex ? `
                <div style="background: #000; padding: 0.5rem; border-radius: 4px; font-family: monospace; font-size: 0.75rem; color: #00FFCC; margin-top: 0.5rem;">
                    [RESTRICTED EXECUTION ${rex.passed ? 'PASS' : 'FAIL'} | IDENTITY ${rex.identity_bound ? 'BOUND' : 'UNBOUND'}]
                    ${rex.output_log} (${rex.duration_ms}ms)
                </div>
            ` : ''}
        </div>

        <div class="result-section">
            <h4>04. Empirical Falsification Hypothesis (H0)</h4>
            <div style="font-size: 0.8rem; color: #F59E0B; background: rgba(245, 158, 11, 0.08); padding: 0.6rem; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.2);">
                <strong>Falsifiable Null Hypothesis:</strong> ${out && out.null_hypothesis_h0 ? out.null_hypothesis_h0 : 'NOT_SPECIFIED'}<br>
                <strong>Evaluation:</strong> ${out && out.h0_evaluation_status ? out.h0_evaluation_status : 'NOT_EVALUATED'}
            </div>
        </div>

        <div class="result-section" style="border-bottom: none;">
            <h4>05. Checkpoint Audit Ledger</h4>
            <div style="font-size: 0.75rem; color: #94A3B8;">
                ${posture.checkpoints.map(chk => `
                    <div>&bull; <strong>[${chk.stage}]</strong> <code>${chk.actor}</code>: ${chk.title} — <em>${chk.evidence_summary}</em></div>
                `).join('')}
            </div>
        </div>
    `;

    container.innerHTML = html;

    // Show Export Bar
    const exportBar = document.getElementById('export-bar');
    exportBar.style.display = 'flex';
    document.getElementById('final-audit-hash').innerText = out && out.audit_sha256 ? out.audit_sha256 : 'NOT_AVAILABLE';
}

async function handleExportDossier() {
    if (!currentProjectId) return;
    try {
        const res = await fetch(`/api/v1/export/dossier/${currentProjectId}`);
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
    window.open(`/api/v1/export/dossier/html/${currentProjectId}`, '_blank');
}

async function loadRecentProjects() {
    try {
        const res = await fetch('/api/v1/projects?limit=5');
        const data = await res.json();
        const list = document.getElementById('recent-list');
        if (!data.projects || data.projects.length === 0) return;
        
        list.innerHTML = data.projects.map(p => `
            <div class="recent-item" onclick="loadProjectById('${p.project_id}')">
                <span>${p.objective.substring(0, 35)}...</span>
                <span class="mono-text" style="color: #00FFCC;">${p.stage}</span>
            </div>
        `).join('');
    } catch (e) {
        // Ignore
    }
}

async function loadProjectById(id) {
    try {
        const res = await fetch(`/api/v1/projects/${id}`);
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
