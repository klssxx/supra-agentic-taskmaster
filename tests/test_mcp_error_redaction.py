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
