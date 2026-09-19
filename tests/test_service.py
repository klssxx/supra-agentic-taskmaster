"""Tests for the SUPRA FastAPI service and provider-neutral endpoints."""

from fastapi.testclient import TestClient
from supra_agentic.service import app

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

    response = client.get("/api/v1/examples/quick-run")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["example"] is True
    assert data["stage"] == "COMPLETED"
    assert "audit_sha256" in data["deliverable"]
    assert "null_hypothesis_h0" in data["deliverable"]


def test_webmcp_jsonrpc_protocol():

    # 1. initialize
    init_res = client.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_res.status_code == 200
    assert init_res.json()["result"]["serverInfo"]["name"] == "supra-agentic-taskmaster"

    # 2. tools/list
    tools_res = client.post("/api/v1/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
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
    assert "COMPLETED" in call_res.json()["result"]["content"][0]["text"]


def test_create_and_run_project_and_html_export():

    payload = {
        "objective": "Formulate an autonomous Zero-Trust secretless mesh with continuous invariant verification",
        "domain": "cloud_security",
        "allow_disruptive": True,
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["stage"] == "COMPLETED"
    pid = data["project_id"]

    # Get project
    get_res = client.get(f"/api/v1/projects/{pid}")
    assert get_res.status_code == 200
    assert get_res.json()["posture"]["stage"] == "COMPLETED"

    # Export markdown dossier
    exp_res = client.get(f"/api/v1/export/dossier/{pid}")
    assert exp_res.status_code == 200
    assert "TECHNICAL DOSSIER" in exp_res.json()["markdown_dossier"]

    # Export HTML dossier
    html_res = client.get(f"/api/v1/export/dossier/html/{pid}")
    assert html_res.status_code == 200
    assert "<svg" in html_res.text
    assert "SUPRA Autonomous Taskmaster Dossier" in html_res.text


def test_create_project_records_provider_without_calling_it():

    response = client.post(
        "/api/v1/projects",
        json={
            "objective": "Design a bounded local automation controller",
            "provider": "ollama",
            "model": "llama3.2",
            "use_model": False,
        },
    )

    assert response.status_code == 201
    posture = response.json()["posture"]
    assert posture["final_output"]["model_assistance"] == {
        "enabled": False,
        "provider": "ollama",
    }
