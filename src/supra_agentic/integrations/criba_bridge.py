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


def _find_criba_root() -> Path | None:
    """Find CRIBA root directory by checking env vars and searching for pyproject.toml.

    Priority:
    1. SUPRA_CRIBA_ROOT env var
    2. CRIBA_ROOT env var
    3. Search upward from this file for pyproject.toml containing 'criba'
    4. Search common locations relative to this file
    """
    # 1. Environment variables
    for env_var in ("SUPRA_CRIBA_ROOT", "CRIBA_ROOT"):
        env_path = os.environ.get(env_var)
        if env_path:
            path = Path(env_path).expanduser().resolve()
            if _is_criba_root(path):
                return path

    # 2. Search upward from this file for pyproject.toml with 'criba'
    current = Path(__file__).resolve()
    for parent in [current.parent] + list(current.parents):
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8")
                if "criba" in content.lower():
                    return parent
            except Exception:
                pass

    # 3. Common relative locations
    # From SUPRA src/supra_agentic/integrations/ -> up 4 levels -> CRIBA/
    supra_root = Path(__file__).resolve().parents[3]  # supra_agentic/
    common_paths = [
        supra_root.parent / "CRIBA",  # ../CRIBA
        supra_root.parent.parent / "CRIBA",  # ../../CRIBA
        Path.cwd() / "CRIBA",
        Path.home() / "Music" / "INNOVATIONS" / "ACTIVE" / "CRIBA",
    ]
    for path in common_paths:
        if _is_criba_root(path):
            return path.resolve()

    return None


def _is_criba_root(path: Path) -> bool:
    """Check if path is a valid CRIBA root (has pyproject.toml with criba)."""
    try:
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text(encoding="utf-8")
            return "criba" in content.lower()
    except Exception:
        pass
    return False


def _get_criba_root() -> Path:
    """Get CRIBA root or raise descriptive error."""
    root = _find_criba_root()
    if root is None:
        checked = []
        for env_var in ("SUPRA_CRIBA_ROOT", "CRIBA_ROOT"):
            if os.environ.get(env_var):
                checked.append(f"${env_var}={os.environ[env_var]}")
        checked.append("pyproject.toml search upward from criba_bridge.py")
        checked.append("common relative paths (../CRIBA, ../../CRIBA, etc.)")
        raise RuntimeError(
            "CRIBA root not found. Set SUPRA_CRIBA_ROOT or CRIBA_ROOT environment variable "
            f"to the CRIBA project directory. Checked: {', '.join(checked)}"
        )
    return root


def _get_timeout() -> int:
    """Get configurable timeout from environment (default 60s)."""
    try:
        return int(os.environ.get("SUPRA_CRIBA_TIMEOUT", "60"))
    except ValueError:
        return 60


# Backwards compatibility: compute once at import time but allow override via env
CRIBA_ROOT = _get_criba_root()
BLACKFORGE_ROOT = CRIBA_ROOT  # blackforge está en criba


def call_criba(
    query: str,
    mode: str = "balanced",
    supporting_methods: int = 8,
    database: str | None = None,
) -> dict[str, Any]:
    """Invoke CRIBA activate as a subprocess.

    Returns dict with either CRIBA result or error dict.
    Never raises exceptions - always returns dict.
    """
    # Re-resolve root at call time to respect env changes
    cwd = _get_criba_root()
    timeout = _get_timeout()

    cmd = [
        "uv", "run", "python", "-m", "criba", "activate",
        "--query", query,
        "--mode", mode,
        "--supporting-methods", str(supporting_methods),
        "--json",
    ]
    if database:
        cmd.extend(["--database", database])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
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
    """Invoke BLACKFORGE headless pipeline as a subprocess.

    Returns dict with either result or error dict.
    Never raises exceptions - always returns dict.
    """
    cwd = _get_criba_root()
    timeout = _get_timeout()

    cmd = [
        "uv", "run", "python", "-m", "criba", "blackforge",
        "--query", query,
        "--seed", str(seed),
        "--profile", profile,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            # blackforge no tiene --json, parsear stdout manualmente
            return {"raw_output": result.stdout, "success": True}
        else:
            return {"error": f"BLACKFORGE exit code {result.returncode}", "stderr": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": f"BLACKFORGE timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}