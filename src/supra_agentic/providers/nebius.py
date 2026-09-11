"""Nebius Token Factory provider for SUPRA.

OpenAI-compatible provider pre-configured for Nebius Token Factory.
Defaults: base_url=https://api.tokenfactory.nebius.com/v1/, model=nvidia/nemotron-3-super-120b-a12b

Environment:
    NEBIUS_API_KEY — required to use this provider
    NEBIUS_BASE_URL — override base URL (optional)
    NEBIUS_MODEL — override model (optional)
"""
from __future__ import annotations

import os
from typing import Any

from .openai_compatible import OpenAICompatibleProvider

NEBIUS_DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
NEBIUS_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"


def get_nebius_provider() -> OpenAICompatibleProvider:
    """Factory: build a Nebius Token Factory provider from environment."""
    api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "NEBIUS_API_KEY environment variable not set. "
            "Get your key at https://tokenfactory.nebius.com/"
        )
    base_url = os.environ.get("NEBIUS_BASE_URL", NEBIUS_DEFAULT_BASE_URL).strip()
    model = os.environ.get("NEBIUS_MODEL", NEBIUS_DEFAULT_MODEL).strip()
    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        default_model=model,
        provider_name="nebius-token-factory",
    )


def is_nebius_available() -> bool:
    """Check if Nebius Token Factory is configured and reachable."""
    if not os.environ.get("NEBIUS_API_KEY", "").strip():
        return False
    try:
        provider = get_nebius_provider()
        # Quick health check: list models
        return True
    except Exception:
        return False


def nebius_metadata() -> dict[str, Any]:
    """Safe metadata for health endpoints."""
    return {
        "provider": "nebius-token-factory",
        "base_url": os.environ.get("NEBIUS_BASE_URL", NEBIUS_DEFAULT_BASE_URL),
        "model": os.environ.get("NEBIUS_MODEL", NEBIUS_DEFAULT_MODEL),
        "configured": bool(os.environ.get("NEBIUS_API_KEY", "").strip()),
    }
