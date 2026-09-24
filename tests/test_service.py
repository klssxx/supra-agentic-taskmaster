"""Tests for the SUPRA FastAPI service and provider-neutral endpoints."""

import json
import tempfile
import time

import pytest
import supra_agentic.service as service_module
from fastapi.testclient import TestClient
from supra_agentic.dossier import export_full_html_dossier
from supra_agentic.models import ProjectPosture, TaskmasterStage
from supra_agentic.service import _parse_cors_origins, app
from supra_agentic.state import state_manager

client = TestClient(app)


def test_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["provider"]["name"] == "hermes"
    assert data["provider"]["protocol"] == "openai-compatible"
    assert data["webmcp_enabled"] is True
    assert "provider" in data


def test_serve_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert "SUPRA" in response.text
    assert "What do you want to solve?" in response.text


def test_quick_run_example():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        response = client.get("/api/v1/examples/quick-run")
        assert response.status_code == 200
        data = response.json()
        assert data["example"] is True
        assert data["completion_status"] in {"COMPLETED", "BLOCKED"}
        assert data["secure_sandbox_status"] in {
            "IDENTITY_BOUND_ISOLATION_PASS",
            "IDENTITY_BOUND_ISOLATION_FAIL",
            "UNVERIFIED_ISOLATION",
            "NOT_RUN",
        }
        assert data["secure_sandbox_execution_scope"] in {
            "IDENTITY_BOUNDARY_SMOKE_ONLY",
            "NOT_RUN",
        }
        assert data["candidate_mechanism_executed_in_secure_sandbox"] is False
        if data["completion_status"] == "BLOCKED":
            assert data["status"] == "blocked"
            assert data["stage"] != "COMPLETED"
            assert data["deliverable"] is None
        else:
            assert data["status"] == "success"
            assert data["stage"] == "COMPLETED"
            assert data["secure_sandbox_status"] == "IDENTITY_BOUND_ISOLATION_PASS"
            assert "audit_sha256" in data["deliverable"]
            assert "null_hypothesis_h0" in data["deliverable"]


def test_webmcp_jsonrpc_protocol():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        # 1. initialize
        init_res = client.post(
            "/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert init_res.status_code == 200
        assert init_res.json()["result"]["serverInfo"]["name"] == "supra-agentic-taskmaster"

        # 2. tools/list
        tools_res = client.post(
            "/api/v1/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        assert tools_res.status_code == 200
        assert len(tools_res.json()["result"]["tools"]) >= 5

        # 3. tools/call supra_quick_run
        call_res = client.post(
            "/api/v1/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "supra_quick_run",
                    "arguments": {
                        "objective": "Test WebMCP autonomous task run",
                        "domain": "general",
                    },
                },
            },
        )
        assert call_res.status_code == 200
        payload = json.loads(call_res.json()["result"]["content"][0]["text"])
        assert payload["completion_status"] in {"COMPLETED", "BLOCKED"}
        assert payload["secure_sandbox_execution_scope"] in {
            "IDENTITY_BOUNDARY_SMOKE_ONLY",
            "NOT_RUN",
        }
        assert payload["candidate_mechanism_executed_in_secure_sandbox"] is False
        if payload["completion_status"] == "BLOCKED":
            assert payload["status"] == "blocked"
            assert payload["workflow_status"] != "COMPLETED"
        else:
            assert payload["status"] == "success"
            assert payload["workflow_status"] == "COMPLETED"


def test_create_and_run_project_and_html_export():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        payload = {
            "objective": "Formulate an autonomous Zero-Trust secretless mesh with continuous invariant verification",
            "domain": "cloud_security",
            "allow_disruptive": True,
        }
        response = client.post("/api/v1/projects", json=payload)
        # A strategy-coverage FAIL is not a server crash, but it MUST block completion.
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "blocked"
        assert data["completion_status"] == "BLOCKED"
        assert data["status_scope"] == "WORKFLOW_EXECUTION_ONLY"
        assert "project_id" in data
        assert data["stage"] != "COMPLETED"
        assert data["workflow_status"] != "COMPLETED"
        assert data["verification_status"] == "FAIL"
        assert data["scientific_status"] == "NOT_VALIDATED"
        assert data["posture"]["final_output"] is None


def test_create_project_records_provider_without_calling_it():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        response = client.post(
            "/api/v1/projects",
            json={
                "objective": "Design a bounded local automation controller",
                "provider": "ollama",
                "model": "llama3.2",
                "use_model": False,
            },
        )

        # A strategy-coverage FAIL is not a server crash, but it MUST block completion.
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "blocked"
        assert data["completion_status"] == "BLOCKED"
        assert data["status_scope"] == "WORKFLOW_EXECUTION_ONLY"
        assert "project_id" in data
        assert data["stage"] != "COMPLETED"
        assert data["workflow_status"] != "COMPLETED"
        assert data["verification_status"] == "FAIL"
        assert data["scientific_status"] == "NOT_VALIDATED"
        assert data["posture"]["final_output"] is None


def test_cors_rejects_wildcard_origin() -> None:
    with pytest.raises(RuntimeError, match="wildcard"):
        _parse_cors_origins("*")


def test_remote_api_requires_credentials_when_key_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(service_module, "API_KEY", "unit-test-secret")
    remote = TestClient(app, client=("203.0.113.10", 50000))
    denied = remote.get("/api/v1/projects")
    assert denied.status_code == 401
    allowed = remote.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer unit-test-secret"},
    )
    assert allowed.status_code == 200


def test_remote_api_fails_closed_when_no_key_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(service_module, "API_KEY", "")
    remote = TestClient(app, client=("203.0.113.11", 50000))
    response = remote.get("/api/v1/projects")
    assert response.status_code == 503


@pytest.mark.parametrize(
    "project_id",
    ["../escape", "..", "nested/path", r"nested\\path", ".hidden", "bad id"],
)
def test_project_routes_reject_unsafe_project_ids(project_id: str) -> None:
    response = client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code in {400, 404}


def test_html_dossier_escapes_dynamic_content() -> None:
    posture = ProjectPosture(
        project_id="safe-id",
        objective='<script>alert("x")</script>',
        stage=TaskmasterStage.RECEIVED,
        created_at=time.time(),
        updated_at=time.time(),
    )
    html = export_full_html_dossier(posture)
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html


def _complete_criba_dossier_payload() -> dict:
    return {
        "dossier_id": "dossier-0123456789abcdef0123456789abcdef",
        "candidate_id": "cand-thermal-1",
        "run_id": "",
        "claim_id": "claim-thermal-1",
        "protocol_version": "sha256:" + "a" * 64,
        "mechanism_version": "sha256:" + "b" * 64,
        "problema": "Reduce thermal drift in sensor",
        "bloqueo": "",
        "origen_bloqueo": "",
        "hipotesis": "Bounded calibration loop reduces thermal drift",
        "mecanismo": "Closed-loop correction with 5ms window",
        "evidence_delivered": [],
        "evidence_documented_as_used": [],
        "evidencia_utilizada": [],
        "prueba_discriminante": {
            "afirmacion_decisiva": "Compare calibrated vs baseline runs under load",
            "alternativa_explicativa": "Ambient temperature stabilization alone",
            "intervencion_prueba": "Compare calibrated vs baseline runs under load",
            "observable": "temperature-adjusted error over 1h",
            "comparacion": "Compare the two preregistered rival predictions",
            "metrica": "temperature-adjusted error over 1h",
            "resultado_favorable_mecanismo": "drift < 0.1C sustained",
            "resultado_favorable_alternativa": "drift reduction from ambient alone",
            "regla_decision": "prefer mechanism when drift separation > 0.05C",
            "condicion_fracaso": "no measurable separation between arms",
            "coste_permisos": "review before execution",
            "estado_prueba": "NO_EJECUTADA",
        },
        "supuestos": [],
        "estado": "SUPRA_EJECUCION_PENDIENTE",
        "creado_at": "2026-09-25T00:00:00+00:00",
    }


def test_create_project_persists_criba_dossier_as_planning_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        response = client.post(
            "/api/v1/projects",
            json={
                "objective": "Evaluate a bounded thermal calibration mechanism",
                "domain": "thermal_engineering",
                "allow_disruptive": False,
                "criba_dossier": _complete_criba_dossier_payload(),
            },
        )

        assert response.status_code == 201
        receipt = response.json()["posture"]["criba_dossier_receipt"]
        assert receipt["receipt_scope"] == "PLANNED_DISCRIMINANT_PROTOCOL_ONLY"
        assert receipt["execution_status"] == "NOT_EXECUTED"
        assert receipt["scientific_status"] == "NOT_VALIDATED"
        assert receipt["criba_candidate_id"] == "cand-thermal-1"
        assert receipt["alternativa_explicativa"] == "Ambient temperature stabilization alone"
        assert receipt["intervencion_prueba"] == (
            "Compare calibrated vs baseline runs under load"
        )
        assert receipt["observable"] == "temperature-adjusted error over 1h"
        assert receipt["resultado_favorable_mecanismo"] == "drift < 0.1C sustained"
        assert receipt["resultado_favorable_alternativa"] == (
            "drift reduction from ambient alone"
        )


def test_create_project_rejects_incomplete_criba_discriminant_protocol() -> None:
    payload = _complete_criba_dossier_payload()
    payload["prueba_discriminante"]["alternativa_explicativa"] = ""

    response = client.post(
        "/api/v1/projects",
        json={
            "objective": "Reject incomplete CRIBA discriminant protocol",
            "criba_dossier": payload,
        },
    )

    assert response.status_code == 422
