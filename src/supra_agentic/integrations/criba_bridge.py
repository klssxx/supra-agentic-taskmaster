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
import subprocess
from typing import Any

CRIBA_ROOT = "C:/Users/KLSX/Music/INNOVATIONS/ACTIVE/CRIBA"
BLACKFORGE_ROOT = "C:/Users/KLSX/Music/INNOVATIONS/ACTIVE/CRIBA"  # blackforge está en criba


def call_criba(
    query: str,
    mode: str = "balanced",
    supporting_methods: int = 8,
    database: str | None = None,
) -> dict[str, Any]:
    """Invoke CRIBA activate as a subprocess."""
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
            cwd=CRIBA_ROOT,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"error": f"CRIBA exit code {result.returncode}", "stderr": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "CRIBA timeout after 60s"}
    except Exception as e:
        return {"error": str(e)}


def call_blackforge(
    query: str,
    seed: int = 1,
    profile: str = "hybrid",
    session_size: int = 12,
) -> dict[str, Any]:
    """Invoke BLACKFORGE headless pipeline as a subprocess."""
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
            cwd=BLACKFORGE_ROOT,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            # blackforge no tiene --json, parsear stdout manualmente
            return {"raw_output": result.stdout, "success": True}
        else:
            return {"error": f"BLACKFORGE exit code {result.returncode}", "stderr": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "BLACKFORGE timeout after 60s"}
    except Exception as e:
        return {"error": str(e)}
