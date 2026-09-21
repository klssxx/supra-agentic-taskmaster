"""Dossier and Technical Export Generator with Embedded SVG Architecture."""

from __future__ import annotations

from .models import ProjectPosture


def generate_svg_architecture(posture: ProjectPosture) -> str:
    """Generate an inline SVG diagram representing the project's autonomous DAG."""
    cand_name = (
        posture.selected_candidate.pathway_name if posture.selected_candidate else "Standard"
    )
    verdict = posture.verification.verdict if posture.verification else "NOT_EVALUATED"

    return f"""<svg width="720" height="200" viewBox="0 0 720 200" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="blueGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4E75FF"/>
      <stop offset="100%" stop-color="#2563EB"/>
    </linearGradient>
    <linearGradient id="tealGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00FFCC"/>
      <stop offset="100%" stop-color="#10B981"/>
    </linearGradient>
  </defs>
  
  <rect width="100%" height="100%" fill="#07090E" rx="8" stroke="rgba(255,255,255,0.1)"/>
  
  <!-- Connector Lines -->
  <line x1="140" y1="100" x2="240" y2="100" stroke="#4E75FF" stroke-width="2" stroke-dasharray="4"/>
  <line x1="360" y1="100" x2="460" y2="100" stroke="#00FFCC" stroke-width="2"/>
  <line x1="580" y1="100" x2="630" y2="100" stroke="#10B981" stroke-width="2"/>

  <!-- Node 1: Invariants -->
  <rect x="20" y="60" width="120" height="80" rx="6" fill="#131822" stroke="#4E75FF" stroke-width="1.5"/>
  <text x="80" y="95" fill="#F0F4F8" font-family="sans-serif" font-size="11" font-weight="bold" text-anchor="middle">01. INVARIANTS</text>
  <text x="80" y="115" fill="#94A3B8" font-family="monospace" font-size="9" text-anchor="middle">do(X) Boundaries</text>

  <!-- Node 2: Strategy -->
  <rect x="240" y="60" width="120" height="80" rx="6" fill="#131822" stroke="#4E75FF" stroke-width="1.5"/>
  <text x="300" y="95" fill="#F0F4F8" font-family="sans-serif" font-size="11" font-weight="bold" text-anchor="middle">02. STRATEGY</text>
  <text x="300" y="115" fill="#00FFCC" font-family="monospace" font-size="9" text-anchor="middle">{cand_name[:14]}...</text>

  <!-- Node 3: Trusted Restricted Execution -->
  <rect x="460" y="60" width="120" height="80" rx="6" fill="#131822" stroke="#00FFCC" stroke-width="1.5"/>
  <text x="520" y="95" fill="#F0F4F8" font-family="sans-serif" font-size="11" font-weight="bold" text-anchor="middle">03. RESTRICTED</text>
  <text x="520" y="115" fill="#10B981" font-family="monospace" font-size="9" text-anchor="middle">Coverage ({verdict})</text>

  <!-- Node 4: Final Deliverable -->
  <circle cx="660" cy="100" r="28" fill="url(#tealGrad)"/>
  <text x="660" y="104" fill="#000000" font-family="sans-serif" font-size="10" font-weight="bold" text-anchor="middle">SHA-256</text>
</svg>"""


def export_full_html_dossier(posture: ProjectPosture) -> str:
    """Generate a printable, self-contained HTML technical specification."""
    svg = generate_svg_architecture(posture)
    decomp = posture.decomposition
    cand = posture.selected_candidate
    out = posture.final_output

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>SUPRA Technical Dossier — {posture.project_id}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1e293b; }}
  h1, h2, h3 {{ color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
  .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; background: #e0e7ff; color: #3730a3; }}
  .card {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; margin: 16px 0; background: #f8fafc; }}
  .mono {{ font-family: monospace; background: #e2e8f0; padding: 2px 5px; border-radius: 4px; font-size: 13px; }}
  ul {{ padding-left: 20px; }}
</style>
</head>
<body>
  <h1>SUPRA Autonomous Taskmaster Dossier</h1>
  <p><strong>Project ID:</strong> <span class="mono">{posture.project_id}</span> | <strong>Stage:</strong> <span class="badge">{posture.stage.value}</span></p>
  
  <div class="card">
    <h3>Executive Objective</h3>
    <p>{posture.objective}</p>
    <p><strong>Domain:</strong> <span class="mono">{decomp.domain if decomp else "general"}</span></p>
  </div>

  <h2>Autonomous Architectural Graph</h2>
  <div>{svg}</div>

  <h2>System Invariants & Boundary Constraints</h2>
  <ul>
    {"".join(f"<li><strong>[INVARIANT]</strong> {inv}</li>" for inv in (decomp.invariants if decomp else []))}
  </ul>

  <h2>Selected Strategy Candidate</h2>
  <div class="card">
    <h3>{cand.pathway_name if cand else "N/A"} <span class="badge">{cand.paradigm_type if cand else "N/A"}</span></h3>
    <p><strong>Hypothesis:</strong> {cand.hypothesis if cand else "N/A"}</p>
    <p><strong>Feasibility:</strong> {cand.feasibility_score if cand else 0.0:.2f} | <strong>Divergence:</strong> {cand.divergence_score if cand else 0.0:.2f}</p>
  </div>

  <h2>Empirical Falsification Hypothesis (H0)</h2>
  <div class="card" style="background: #fffbeb; border-color: #fef3c7;">
    <p><strong>Null Hypothesis:</strong> {out.get("null_hypothesis_h0", "NOT_EVALUATED: no H0 recorded") if out else "NOT_EVALUATED: no H0 recorded"}</p>
  </div>

  <h2>Cryptographic Integrity Signature</h2>
  <p><strong>SHA-256 Audit Hash:</strong> <span class="mono">{out.get("audit_sha256", "N/A") if out else "N/A"}</span></p>
</body>
</html>"""
