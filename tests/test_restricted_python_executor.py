from __future__ import annotations

import json

import pytest
from supra_agentic import mcp_handler
from supra_agentic.state import state_manager
from supra_agentic.tools import (
    MAX_CODE_SIZE,
    MAX_FUZZ_ITERATIONS,
    MAX_OUTPUT_SIZE,
    restricted_python_executor,
)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(state_manager, "storage_dir", tmp_path)
    monkeypatch.setattr(state_manager, "_projects", {})


def _project_id() -> str:
    return state_manager.create_project(objective="bounded adversarial test").project_id


DANGEROUS_REMOTE_PAYLOADS = [
    "__import__('os').environ",
    "().__class__",
    "().__class__.__mro__",
    "().__class__.__mro__[1].__subclasses__()",
    "import importlib; importlib.import_module('os')",
    "open('secret.txt').read()",
    "import os; os.environ",
    "import subprocess; subprocess.run(['whoami'])",
    "import socket; socket.socket()",
    "print('x' * 10000000)",
    "raise RuntimeError('boom')",
    "while True: pass",
]


@pytest.mark.parametrize("payload", DANGEROUS_REMOTE_PAYLOADS)
def test_remote_python_payload_is_rejected_before_executor(monkeypatch, payload: str) -> None:
    called = False

    def forbidden_call(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("executor must not be reached")

    monkeypatch.setattr(mcp_handler, "restricted_python_executor", forbidden_call)
    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "supra_restricted_execution",
                "arguments": {
                    "project_id": _project_id(),
                    "code_snippet": payload,
                },
            },
        }
    )

    assert called is False
    assert response["error"]["code"] == -32602
    assert "code_snippet" in response["error"]["message"]


def test_direct_untrusted_code_is_rejected_before_exec(monkeypatch) -> None:
    called = False

    def forbidden_exec(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("exec boundary reached")

    monkeypatch.setattr("supra_agentic.tools._execute_trusted_code", forbidden_exec)
    with pytest.raises(PermissionError, match="trusted_internal"):
        restricted_python_executor(_project_id(), code_snippet="while True: pass")
    assert called is False


@pytest.mark.parametrize("value", [0, -1, MAX_FUZZ_ITERATIONS + 1, 10**9])
def test_fuzz_iterations_outside_contract_are_rejected(value: int) -> None:
    with pytest.raises(ValueError, match="fuzz_iterations"):
        restricted_python_executor(_project_id(), fuzz_iterations=value)


@pytest.mark.parametrize("value", [1, MAX_FUZZ_ITERATIONS])
def test_fuzz_iteration_boundaries_are_accepted(value: int) -> None:
    result = restricted_python_executor(_project_id(), fuzz_iterations=value)
    assert result["restricted_execution_result"]["passed"] is True


def test_oversized_trusted_source_is_rejected_before_exec(monkeypatch) -> None:
    called = False

    def forbidden_exec(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("exec boundary reached")

    monkeypatch.setattr("supra_agentic.tools._execute_trusted_code", forbidden_exec)
    with pytest.raises(ValueError, match="MAX_CODE_SIZE"):
        restricted_python_executor(
            _project_id(),
            code_snippet="x" * (MAX_CODE_SIZE + 1),
            trusted_internal=True,
        )
    assert called is False


def test_massive_output_is_bounded() -> None:
    result = restricted_python_executor(
        _project_id(),
        code_snippet=f"print('x' * {MAX_OUTPUT_SIZE + 1})",
        trusted_internal=True,
    )
    execution = result["restricted_execution_result"]
    assert execution["passed"] is False
    assert execution["error_type"] == "RuntimeError"
    assert "output limit" not in execution["output_log"].lower()
    assert len(execution["output_log"]) <= MAX_OUTPUT_SIZE


def test_trusted_exception_is_captured_at_boundary() -> None:
    result = restricted_python_executor(
        _project_id(),
        code_snippet="raise RuntimeError('expected failure')",
        trusted_internal=True,
    )
    execution = result["restricted_execution_result"]
    assert execution["passed"] is False
    assert execution["error_type"] == "RuntimeError"
    assert "expected failure" not in execution["output_log"]
    assert execution["side_effects_contained"] is False


def test_mcp_manifest_is_honest_and_exposes_no_code_field() -> None:
    manifest = next(
        item
        for item in mcp_handler.MCP_TOOLS_MANIFEST
        if item["name"] == "supra_restricted_execution"
    )
    assert "not a security sandbox" in manifest["description"].lower()
    assert "code_snippet" not in manifest["inputSchema"]["properties"]
    assert (
        manifest["inputSchema"]["properties"]["fuzz_iterations"]["maximum"] == MAX_FUZZ_ITERATIONS
    )


def test_remote_default_restricted_execution_is_internal_only() -> None:
    response = mcp_handler.handle_mcp_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "supra_restricted_execution",
                "arguments": {"project_id": _project_id(), "fuzz_iterations": 1},
            },
        }
    )
    assert "error" not in response
    result = json.loads(response["result"]["content"][0]["text"])
    assert result["restricted_execution_result"]["passed"] is True
