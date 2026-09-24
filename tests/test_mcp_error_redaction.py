from __future__ import annotations

import logging

from supra_agentic import mcp_handler


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
