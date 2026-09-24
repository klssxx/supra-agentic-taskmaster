from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "supra_agentic" / "web"


def test_causal_workbench_exposes_real_supra_sections() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for section in (
        "Objetivo",
        "Descomposición",
        "Estrategias",
        "Verificación",
        "Sandbox",
        "Evidencia",
        "Dossiers",
        "Proveedores",
        "Proyectos",
    ):
        assert section in html
    assert 'id="causal-dag-canvas"' in html
    assert 'id="objective-input"' in html


def test_workbench_frontend_only_calls_existing_service_routes() -> None:
    js = (WEB / "app.js").read_text(encoding="utf-8")
    expected = (
        "/health",
        "/api/v1/projects",
        "/api/v1/examples/quick-run",
        "/api/v1/providers",
        "/api/v1/export/dossier/",
        "/api/v1/export/dossier/html/",
    )
    for route in expected:
        assert route in js

    assert "/api/v1/health" not in js
    assert "/api/v1/dossiers/run" not in js
    assert "/api/v1/projects/{project_id}/logs" not in js


def test_workbench_does_not_fabricate_default_pass_copy() -> None:
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'verdict : "PASS"' not in js
    assert '"NOT_EVALUATED"' in js
    assert "All system invariants rigorously satisfied" not in js
    assert "H0 verified" not in js


def test_workbench_uses_current_execution_contracts() -> None:
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "restricted_execution_results" in js
    assert "secure_sandbox_results" in js
    assert "posture.sandbox_results" not in js
    assert "IDENTITY_BOUND_ISOLATION_PASS" in js
    assert "candidate_mechanism_executed" in js
    assert "is not scientific validation" in js


def test_workbench_escapes_dynamic_html() -> None:
    js = (WEB / "app.js").read_text(encoding="utf-8")
    assert "function escapeHtml(value)" in js
    assert "escapeHtml(posture.objective)" in js
    assert "escapeHtml(c.hypothesis)" in js
    assert "escapeHtml(chk.evidence_summary)" in js
