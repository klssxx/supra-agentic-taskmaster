"""Static product-surface sentinels for SUPRA epistemic wording."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_astra_001_frontend_missing_values_never_default_to_pass_or_verified():
    app = _read("src/supra_agentic/web/app.js")
    forbidden = [
        "ver ? ver.verdict : 'PASS'",
        "ver ? (ver.confidence_score * 100).toFixed(1) : 95",
        "H0 verified against baseline.",
        "out && out.audit_sha256 ? out.audit_sha256 : 'VERIFIED'",
        "posture.sandbox_results",
        "'SANDBOX_VERIFIED': 3",
    ]
    for marker in forbidden:
        assert marker not in app
    assert "NOT_EVALUATED" in app
    assert "NOT_SPECIFIED" in app
    assert "NOT_AVAILABLE" in app
    assert "restricted_execution_results" in app


def test_astra_017_web_and_docs_do_not_claim_security_sandbox():
    index = _read("src/supra_agentic/web/index.html").casefold()
    readme = _read("README.md").casefold()
    architecture = _read("docs/ARCHITECTURE.md").casefold()
    dossier = _read("src/supra_agentic/dossier.py").casefold()

    assert "runs sandbox verification" not in index
    assert "bounded sandbox execution" not in architecture
    assert "sandbox_verified" not in architecture
    assert "execute_sandbox_action" not in architecture
    assert "deterministic sandbox remains contained" not in readme
    assert "h0 verified" not in dossier

    assert "not a security sandbox" in readme
    assert "not a security sandbox" in architecture


def test_astra_031_mcp_does_not_claim_full_pearl_or_scientific_validation():
    mcp = _read("src/supra_agentic/mcp_handler.py")
    assert "Judea Pearl counterfactual invariant testing" not in mcp
    assert "no full Pearl causal-inference implementation is claimed" in mcp
    assert "this is not scientific validation" in mcp


def test_astra_033_integrity_hash_is_not_described_as_truth():
    tools = _read("src/supra_agentic/tools.py")
    readme = _read("README.md")
    assert "SHA256_OF_SERIALIZED_PAYLOAD_NOT_TRUTH" in tools
    assert "it is not evidence that the payload is true" in readme


def test_frontend_escapes_dynamic_html_and_project_ids() -> None:
    app = _read("src/supra_agentic/web/app.js")
    assert "function escapeHtml(value)" in app
    assert "escapeHtml(posture.objective)" in app
    assert "escapeHtml(c.hypothesis)" in app
    assert "escapeHtml(chk.evidence_summary)" in app
    assert "encodeURIComponent(currentProjectId)" in app
    assert "encodeURIComponent(id)" in app
    assert 'onclick="loadProjectById' not in app
