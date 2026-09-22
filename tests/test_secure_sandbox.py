"""Contract tests for the Docker-backed secure sandbox boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import supra_agentic.sandbox as sandbox_module
from supra_agentic.sandbox import (
    DockerSandboxConfig,
    SandboxUnavailableError,
    run_python_in_secure_docker,
    sandbox_protocol_version,
)

IDENTITY = {
    "candidate_id": "cand-test",
    "mechanism_version": "sha256:" + "1" * 64,
    "claim_id": "claim-test",
}


def _config() -> DockerSandboxConfig:
    return DockerSandboxConfig(
        image="python:test",
        timeout_seconds=7.0,
        memory_mb=128,
        cpus=0.25,
        pids_limit=32,
    )


def test_secure_docker_command_enforces_isolation_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_id = "sha256:" + "a" * 64
    calls: list[list[str]] = []

    monkeypatch.setattr(sandbox_module.shutil, "which", lambda _name: "/usr/bin/docker")

    def _run(command: list[str], **kwargs):
        calls.append(list(command))
        if command[1:4] == ["image", "inspect", "--format={{.Id}}"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=image_id + "\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="SUPRA_SECURE_SANDBOX_OK\n",
            stderr="",
        )

    monkeypatch.setattr(sandbox_module.subprocess, "run", _run)

    receipt = run_python_in_secure_docker(
        "print('SUPRA_SECURE_SANDBOX_OK')\n",
        identity=IDENTITY,
        config=_config(),
    )

    assert receipt.passed is True
    assert receipt.identity_bound is True
    assert receipt.isolation_verified is True
    assert receipt.image == "python:test"
    assert receipt.image_id == image_id
    assert receipt.protocol_version is not None
    assert receipt.protocol_version.startswith("sha256:")
    assert receipt.scientific_validation is False

    assert len(calls) == 2
    run_cmd = calls[1]
    for expected in (
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--user=65534:65534",
        "--pids-limit=32",
        "--memory=128m",
        "--memory-swap=128m",
        "--cpus=0.25",
        "--ipc=none",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
    ):
        assert expected in run_cmd

    assert image_id in run_cmd
    assert "python:test" not in run_cmd
    assert run_cmd[-3:] == ["python", "-I", "/runner.py"]
    mount_index = run_cmd.index("--mount")
    assert "readonly" in run_cmd[mount_index + 1]


def test_secure_sandbox_never_pulls_missing_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda _name: "/usr/bin/docker")

    def _run(command: list[str], **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="not found")

    monkeypatch.setattr(sandbox_module.subprocess, "run", _run)
    with pytest.raises(SandboxUnavailableError, match="implicit pulls are forbidden"):
        run_python_in_secure_docker(
            "print('x')\n",
            identity=IDENTITY,
            config=_config(),
        )


def test_secure_sandbox_requires_docker_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda _name: None)
    with pytest.raises(SandboxUnavailableError, match="Docker executable"):
        run_python_in_secure_docker(
            "print('x')\n",
            identity=IDENTITY,
            config=_config(),
        )


def test_protocol_is_bound_to_immutable_image_identity() -> None:
    cfg = _config()
    first = sandbox_protocol_version("print('x')", cfg, "sha256:" + "a" * 64)
    second = sandbox_protocol_version("print('x')", cfg, "sha256:" + "b" * 64)
    assert first != second


def test_sandbox_source_contains_no_in_process_exec_fallback() -> None:
    source = Path("src/supra_agentic/sandbox.py").read_text(encoding="utf-8")
    assert "exec(" not in source
    assert "eval(" not in source
    assert "--network=none" in source
    assert "--pull=never" in source
