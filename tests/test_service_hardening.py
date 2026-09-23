from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from supra_agentic import service

client = TestClient(service.app)


def _jsonrpc_body_of_size(size: int) -> bytes:
    prefix = b'{"jsonrpc":"2.0","id":1,"method":"initialize","padding":"'
    suffix = b'"}'
    if size < len(prefix) + len(suffix):
        raise ValueError("requested body is too small")
    return prefix + (b"x" * (size - len(prefix) - len(suffix))) + suffix


def _request_without_content_length(body: bytes) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/mcp",
            "headers": [],
        },
        receive,
    )


def test_cors_absent_is_closed() -> None:
    assert service._parse_cors_origins(None) == []
    assert service._parse_cors_origins("") == []


def test_cors_accepts_explicit_origins_and_rejects_wildcard() -> None:
    assert service._parse_cors_origins("https://one.example") == ["https://one.example"]
    assert service._parse_cors_origins("https://one.example, http://localhost:3000") == [
        "https://one.example",
        "http://localhost:3000",
    ]
    with pytest.raises(RuntimeError, match="wildcard"):
        service._parse_cors_origins("*")


@pytest.mark.parametrize("raw", ["one.example", "ftp://one.example", "https://ok.example,"])
def test_cors_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(RuntimeError):
        service._parse_cors_origins(raw)


def test_mcp_accepts_body_exactly_at_limit() -> None:
    body = _jsonrpc_body_of_size(service.MAX_MCP_BODY_SIZE)
    response = client.post(
        "/api/v1/mcp",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "supra-agentic-taskmaster"


def test_mcp_rejects_actual_body_above_limit_even_with_false_small_header() -> None:
    body = _jsonrpc_body_of_size(service.MAX_MCP_BODY_SIZE + 1)
    response = client.post(
        "/api/v1/mcp",
        content=body,
        headers={"content-type": "application/json", "content-length": "1"},
    )
    assert response.status_code == 413


def test_mcp_accepts_missing_content_length_when_actual_body_is_small() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode()
    result = asyncio.run(service.mcp_jsonrpc_endpoint(_request_without_content_length(body)))
    assert result["result"]["serverInfo"]["name"] == "supra-agentic-taskmaster"


def test_mcp_rejects_missing_content_length_when_actual_body_is_large() -> None:
    request = _request_without_content_length(_jsonrpc_body_of_size(service.MAX_MCP_BODY_SIZE + 1))
    with pytest.raises(HTTPException) as raised:
        asyncio.run(service.mcp_jsonrpc_endpoint(request))
    assert raised.value.status_code == 413


def test_mcp_rejects_invalid_content_length_json_and_jsonrpc() -> None:
    invalid_length = client.post(
        "/api/v1/mcp",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "not-a-number"},
    )
    assert invalid_length.status_code == 400

    invalid_json = client.post(
        "/api/v1/mcp", content=b"not-json", headers={"content-type": "application/json"}
    )
    assert invalid_json.status_code == 400

    invalid_rpc = client.post("/api/v1/mcp", json={"id": 1, "method": "initialize"})
    assert invalid_rpc.status_code == 400


def test_internal_project_error_is_generic_and_secret_not_logged(monkeypatch, caplog) -> None:
    secret = "SENTINEL_DO_NOT_LEAK_6f0f"

    def explode(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(service.TaskmasterRunner, "run_golden_path", explode)
    response = client.post(
        "/api/v1/projects",
        json={"objective": "bounded objective for error contract"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Project execution failed."}
    assert secret not in response.text
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
