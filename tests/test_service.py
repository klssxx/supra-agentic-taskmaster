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
