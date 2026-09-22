"""Docker-backed secure sandbox execution boundary.

No in-process fallback is provided.  If Docker or the configured image is
unavailable, callers receive SandboxUnavailableError and must keep completion
blocked.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .models import (
    SECURE_SANDBOX_SEMANTICS_VERSION,
    SecureSandboxResult,
)

_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,199}$")
MAX_SANDBOX_CODE_BYTES = 64 * 1024
MAX_SANDBOX_OUTPUT_CHARS = 16_384


class SandboxUnavailableError(RuntimeError):
    """Raised when no verified external sandbox backend can be used."""


@dataclass(frozen=True, slots=True)
class DockerSandboxConfig:
    image: str
    timeout_seconds: float = 15.0
    memory_mb: int = 256
    cpus: float = 0.5
    pids_limit: int = 64

    @classmethod
    def from_env(cls) -> "DockerSandboxConfig":
        image = os.getenv("SUPRA_SANDBOX_IMAGE", "").strip()
        if not image:
            raise SandboxUnavailableError(
                "SUPRA_SANDBOX_IMAGE must name a pre-pulled sandbox image"
            )
        return cls(
            image=image,
            timeout_seconds=float(os.getenv("SUPRA_SANDBOX_TIMEOUT_SECONDS", "15")),
            memory_mb=int(os.getenv("SUPRA_SANDBOX_MEMORY_MB", "256")),
            cpus=float(os.getenv("SUPRA_SANDBOX_CPUS", "0.5")),
            pids_limit=int(os.getenv("SUPRA_SANDBOX_PIDS_LIMIT", "64")),
        )

    def validate(self) -> None:
        if not _IMAGE_RE.fullmatch(self.image):
            raise ValueError("Invalid SUPRA_SANDBOX_IMAGE")
        if not 1.0 <= self.timeout_seconds <= 120.0:
            raise ValueError("sandbox timeout must be between 1 and 120 seconds")
        if not 32 <= self.memory_mb <= 4096:
            raise ValueError("sandbox memory_mb must be between 32 and 4096")
        if not 0.1 <= self.cpus <= 4.0:
            raise ValueError("sandbox cpus must be between 0.1 and 4.0")
        if not 8 <= self.pids_limit <= 512:
            raise ValueError("sandbox pids_limit must be between 8 and 512")


def sandbox_protocol_version(
    code: str,
    config: DockerSandboxConfig,
    image_id: str,
) -> str:
    """Bind the receipt to code, immutable image identity, and isolation config."""
    payload = "\n".join(
        [
            "supra-secure-docker-v1",
            config.image,
            image_id,
            str(config.timeout_seconds),
            str(config.memory_mb),
            str(config.cpus),
            str(config.pids_limit),
            code,
        ]
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _docker_binary() -> str:
    binary = shutil.which("docker")
    if not binary:
        raise SandboxUnavailableError("Docker executable is unavailable")
    return binary


def _ensure_image_present(
    docker: str,
    config: DockerSandboxConfig,
) -> str:
    """Resolve a pre-pulled tag to an immutable image ID."""
    try:
        result = subprocess.run(
            [docker, "image", "inspect", "--format={{.Id}}", config.image],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxUnavailableError("Docker daemon is unavailable") from exc
    if result.returncode != 0:
        raise SandboxUnavailableError(
            "Configured sandbox image is not present locally; implicit pulls are forbidden"
        )
    image_id = (result.stdout or "").strip()
    if not image_id.startswith("sha256:"):
        raise SandboxUnavailableError("Docker image did not resolve to an immutable sha256 ID")
    return image_id


def _bounded(text: str) -> str:
    return text[:MAX_SANDBOX_OUTPUT_CHARS]


def run_python_in_secure_docker(
    code: str,
    *,
    identity: Mapping[str, str],
    config: DockerSandboxConfig | None = None,
) -> SecureSandboxResult:
    """Run Python inside a constrained Docker container and return its receipt."""
    raw = code.encode("utf-8")
    if not raw or len(raw) > MAX_SANDBOX_CODE_BYTES:
        raise ValueError(
            f"sandbox code must be 1..{MAX_SANDBOX_CODE_BYTES} UTF-8 bytes"
        )
    required_identity = ("candidate_id", "mechanism_version", "claim_id")
    if any(not str(identity.get(key, "")).strip() for key in required_identity):
        raise ValueError("secure sandbox requires complete candidate identity")

    cfg = config or DockerSandboxConfig.from_env()
    cfg.validate()
    docker = _docker_binary()
    image_id = _ensure_image_present(docker, cfg)
    protocol_version = sandbox_protocol_version(code, cfg, image_id)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="supra-sandbox-") as tmpdir:
        script = Path(tmpdir) / "runner.py"
        script.write_text(code, encoding="utf-8", newline="\n")
        script.chmod(0o444)

        command = [
            docker,
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            f"--pids-limit={cfg.pids_limit}",
            f"--memory={cfg.memory_mb}m",
            f"--memory-swap={cfg.memory_mb}m",
            f"--cpus={cfg.cpus}",
            "--ipc=none",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
            "--mount",
            f"type=bind,src={script},dst=/opt/supra/runner.py,readonly",
            image_id,
            "python",
            "-I",
            "/opt/supra/runner.py",
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
            )
            duration_ms = (time.monotonic() - started) * 1000
            passed = result.returncode == 0
            stdout = _bounded(result.stdout or "")
            stderr = _bounded(result.stderr or "")
            output = stdout if passed else stderr or stdout
            return SecureSandboxResult(
                execution_semantics_version=SECURE_SANDBOX_SEMANTICS_VERSION,
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version=protocol_version,
                image=cfg.image,
                image_id=image_id,
                passed=passed,
                observed_result="PASS" if passed else "FAIL",
                exit_code=result.returncode,
                output_log=output,
                error_type=None if passed else "SandboxProcessFailure",
                duration_ms=round(duration_ms, 2),
                timed_out=False,
                network_isolated=True,
                read_only_root=True,
                capabilities_dropped=True,
                no_new_privileges=True,
                non_root_user=True,
                resource_limits_applied=True,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = (time.monotonic() - started) * 1000
            output = _bounded(
                (exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr)
                or (exc.stdout.decode() if isinstance(exc.stdout, bytes) else exc.stdout)
                or ""
            )
            return SecureSandboxResult(
                execution_semantics_version=SECURE_SANDBOX_SEMANTICS_VERSION,
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version=protocol_version,
                image=cfg.image,
                image_id=image_id,
                passed=False,
                observed_result="FAIL",
                exit_code=None,
                output_log=output,
                error_type="SandboxTimeout",
                duration_ms=round(duration_ms, 2),
                timed_out=True,
                network_isolated=True,
                read_only_root=True,
                capabilities_dropped=True,
                no_new_privileges=True,
                non_root_user=True,
                resource_limits_applied=True,
            )
