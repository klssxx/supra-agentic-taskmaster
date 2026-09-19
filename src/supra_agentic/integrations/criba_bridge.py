"""Integration bridge between SUPRA and CRIBA/BLACKFORGE.

This module provides a programmatic interface for SUPRA to invoke
CRIBA and BLACKFORGE pipelines as tools within its workflow.

Usage:
    from supra_agentic.integrations import call_criba, call_blackforge

    result = call_criba("Diseñar sistema de autenticación seguro")
    result = call_blackforge("Analizar vulnerabilidades en API REST")
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

# Fallback historico: se acepta SOLO si contiene pyproject.toml (marca de raiz
# del repo). En entornos sin el repo (Docker/Linux) la resolucion devuelve
# None y el puente responde "unavailable" en vez de fallar en silencio.
_CRIBA_ROOT_FALLBACK = "C:/Users/KLSX/Music/INNOVATIONS/ACTIVE/CRIBA"
_DEFAULT_TIMEOUT = 60


def _resolve_criba_root() -> str | None:
    """Resolve the CRIBA repository root without hardcoded assumptions.

    Priority: SUPRA_CRIBA_ROOT, CRIBA_ROOT, then the historical fallback.
    A candidate is only accepted when it is a directory containing a
    pyproject.toml (repo marker); otherwise the bridge reports the root as
    unavailable instead of running a subprocess with a nonexistent cwd.
    """
    candidates = (
        os.environ.get("SUPRA_CRIBA_ROOT"),
        os.environ.get("CRIBA_ROOT"),
        _CRIBA_ROOT_FALLBACK,
    )
    for candidate in candidates:
        if not candidate:
            continue
        root = Path(candidate)
        if root.is_dir() and (root / "pyproject.toml").is_file():
            return str(root)
    return None


def _criba_timeout() -> int:
    """Timeout configurable por env (SUPRA_CRIBA_TIMEOUT), validado.

    Devuelve el valor si es un entero > 0; si el env esta ausente devuelve el
    default (60). Si el env existe pero NO es un entero positivo, devuelve 0
    para que la llamada lo reporte como error explicito en vez de correr con
    un timeout silenciosamente incorrecto.
    """
    raw = os.environ.get("SUPRA_CRIBA_TIMEOUT")
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def _timeout_error(name: str, raw: str) -> dict[str, Any]:
    return {
        "error": f"{name} timeout invalid: SUPRA_CRIBA_TIMEOUT={raw!r} is not a positive integer",
        "status": "unavailable",
    }


def call_criba(
    query: str,
    mode: str = "balanced",
    supporting_methods: int = 8,
    database: str | None = None,
) -> dict[str, Any]:
    """Invoke CRIBA activate as a subprocess."""
    root = _resolve_criba_root()
    if root is None:
        return {
            "error": "CRIBA root not found (set SUPRA_CRIBA_ROOT or CRIBA_ROOT to a checkout with pyproject.toml)",
            "status": "unavailable",
        }
    timeout = _criba_timeout()
    if timeout <= 0:
        return _timeout_error("CRIBA", os.environ.get("SUPRA_CRIBA_TIMEOUT", ""))
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "criba",
        "activate",
        "--query",
        query,
        "--mode",
        mode,
        "--supporting-methods",
        str(supporting_methods),
        "--json",
    ]
    if database:
        cmd.extend(["--database", database])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=root,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"error": f"CRIBA exit code {result.returncode}", "stderr": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": f"CRIBA timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def call_blackforge(
    query: str,
    seed: int = 1,
    profile: str = "hybrid",
    session_size: int = 12,
) -> dict[str, Any]:
    """Invoke BLACKFORGE headless pipeline as a subprocess."""
    root = _resolve_criba_root()
    if root is None:
        return {
            "error": "CRIBA root not found (set SUPRA_CRIBA_ROOT or CRIBA_ROOT to a checkout with pyproject.toml)",
            "status": "unavailable",
        }
    timeout = _criba_timeout()
    if timeout <= 0:
        return _timeout_error("BLACKFORGE", os.environ.get("SUPRA_CRIBA_TIMEOUT", ""))
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "criba",
        "blackforge",
        "--query",
        query,
        "--seed",
        str(seed),
        "--profile",
        profile,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=root,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            # blackforge no tiene --json, parsear stdout manualmente
            return {"raw_output": result.stdout, "success": True}
        else:
            return {
                "error": f"BLACKFORGE exit code {result.returncode}",
                "stderr": result.stderr[:500],
            }
    except subprocess.TimeoutExpired:
        return {"error": f"BLACKFORGE timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}
