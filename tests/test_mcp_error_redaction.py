from __future__ import annotations

import logging
import time

from supra_agentic import mcp_handler
from supra_agentic.models import ProjectPosture, TaskmasterStage


def test_unexpected_mcp_error_does_not_disclose_exception_details(monkeypatch, caplog) -> None:
    sentinel = "SENTINEL_MCP_SECRET_DO_NOT_LEAK"

    def explode(*args, **kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(mcp_handler.taskmaster_runner, "run_golden_path", explode)
    caplog.set_level(logging.ERROR, logger="supra_agentic.mcp_handler")

    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 71,
            "method": "tools/call",
            "params": {
                "name": "supra_quick_run",
                "arguments": {"objective": "bounded regression objective"},
            },
        }
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 71,
        "error": {"code": -32603, "message": "Internal server error"},
    }
    assert sentinel not in str(response)
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text


def test_controlled_invalid_params_error_remains_specific() -> None:
    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 72,
            "method": "tools/call",
            "params": {
                "name": "supra_restricted_execution",
                "arguments": {
                    "project_id": "project-1",
                    "unsupported": "value",
                },
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == ("Invalid params: unsupported fields ['unsupported']")


def test_non_object_mcp_params_and_arguments_are_invalid_params() -> None:
    invalid_params = mcp_handler.handle_mcp_jsonrpc_request(
        {"jsonrpc": "2.0", "id": 80, "method": "tools/call", "params": []}
    )
    invalid_arguments = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 81,
            "method": "tools/call",
            "params": {"name": "supra_quick_run", "arguments": []},
        }
    )

    assert invalid_params["error"] == {
        "code": -32602,
        "message": "Invalid params: params must be an object",
    }
    assert invalid_arguments["error"] == {
        "code": -32602,
        "message": "Invalid params: arguments must be an object",
    }


def test_mcp_validates_tool_argument_types_before_dispatch(monkeypatch) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("invalid arguments reached the tool")

    monkeypatch.setattr(mcp_handler.taskmaster_runner, "run_golden_path", must_not_run)
    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 82,
            "method": "tools/call",
            "params": {
                "name": "supra_quick_run",
                "arguments": {"objective": 123},
            },
        }
    )

    assert response["error"] == {
        "code": -32602,
        "message": "Invalid params: objective must be a non-empty string",
    }


def test_mcp_rejects_unexpected_fields_for_every_public_tool(monkeypatch) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("unexpected arguments reached the tool")

    monkeypatch.setattr(mcp_handler.taskmaster_runner, "run_golden_path", must_not_run)
    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 83,
            "method": "tools/call",
            "params": {
                "name": "supra_quick_run",
                "arguments": {
                    "objective": "bounded objective",
                    "unsupported": "ignored before this fix",
                },
            },
        }
    )

    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == ("Invalid params: unsupported fields ['unsupported']")


def test_secure_sandbox_mcp_tool_does_not_accept_remote_code() -> None:
    manifest = next(
        item for item in mcp_handler.MCP_TOOLS_MANIFEST if item["name"] == "supra_secure_sandbox"
    )
    schema = manifest["inputSchema"]
    assert schema["required"] == ["project_id"]
    assert schema["additionalProperties"] is False
    assert "code_snippet" not in schema["properties"]

    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 73,
            "method": "tools/call",
            "params": {
                "name": "supra_secure_sandbox",
                "arguments": {
                    "project_id": "project-1",
                    "code_snippet": "print('forbidden')",
                },
            },
        }
    )
    assert response["error"]["code"] == -32602
    assert "unsupported fields" in response["error"]["message"]


def test_advertised_mcp_prompts_can_be_retrieved(monkeypatch) -> None:
    challenge = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 90,
            "method": "prompts/get",
            "params": {
                "name": "prompt_taskmaster_challenge",
                "arguments": {"objective": "Design a bounded coding agent"},
            },
        }
    )
    assert challenge["result"]["messages"][0]["role"] == "user"
    assert "Design a bounded coding agent" in challenge["result"]["messages"][0]["content"]["text"]

    posture = ProjectPosture(
        project_id="audit-project",
        objective="Audit an evidence ledger",
        stage=TaskmasterStage.RECEIVED,
        created_at=time.time(),
        updated_at=time.time(),
    )
    monkeypatch.setattr(mcp_handler.state_manager, "get_project", lambda _project_id: posture)
    audit = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 91,
            "method": "prompts/get",
            "params": {
                "name": "prompt_falsification_audit",
                "arguments": {"project_id": "audit-project"},
            },
        }
    )
    audit_text = audit["result"]["messages"][0]["content"]["text"]
    assert "audit-project" in audit_text
    assert "NOT_EVALUATED" in audit_text
    assert "do not promote" in audit_text.lower()


def test_mcp_prompt_get_rejects_invalid_arguments() -> None:
    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 92,
            "method": "prompts/get",
            "params": {
                "name": "prompt_taskmaster_challenge",
                "arguments": {"objective": "bounded", "unsupported": True},
            },
        }
    )
    assert response["error"]["code"] == -32602
    assert "unsupported fields" in response["error"]["message"]
