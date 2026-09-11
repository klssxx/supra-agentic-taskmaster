"""Provider registry for SUPRA."""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .base import AgentProvider, ProviderError, ProviderResponse, ProviderUnavailable, ToolInput, ToolSpec
from .hermes import HermesProvider
from .nebius import get_nebius_provider, is_nebius_available, nebius_metadata
from .openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama endpoint using its OpenAI-compatible API."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            base_url=kwargs.pop("base_url", None)
            or os.getenv("SUPRA_OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434/v1",
            api_key=kwargs.pop("api_key", None) or os.getenv("SUPRA_OLLAMA_API_KEY"),
            default_model=kwargs.pop("default_model", None)
            or os.getenv("SUPRA_OLLAMA_MODEL")
            or os.getenv("SUPRA_MODEL")
            or "llama3.2",
            **kwargs,
            provider_name="ollama",
        )


class OpenAIProvider(OpenAICompatibleProvider):
    """OpenAI or another hosted endpoint using the same wire protocol."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            base_url=kwargs.pop("base_url", None)
            or os.getenv("SUPRA_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1",
            api_key=kwargs.pop("api_key", None)
            or os.getenv("SUPRA_API_KEY")
            or os.getenv("OPENAI_API_KEY"),
            default_model=kwargs.pop("default_model", None)
            or os.getenv("SUPRA_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "gpt-4o-mini",
            **kwargs,
            provider_name="openai",
        )


class CustomProvider(OpenAICompatibleProvider):
    """Arbitrary local/cloud OpenAI-compatible endpoint."""

    def __init__(self, **kwargs: Any) -> None:
        base_url = kwargs.pop("base_url", None) or os.getenv("SUPRA_BASE_URL")
        if not base_url:
            raise ValueError("SUPRA_BASE_URL is required for the custom provider")
        super().__init__(
            base_url=base_url,
            api_key=kwargs.pop("api_key", None) or os.getenv("SUPRA_API_KEY"),
            default_model=kwargs.pop("default_model", None) or os.getenv("SUPRA_MODEL") or "auto",
            **kwargs,
            provider_name="openai-compatible",
        )


ProviderFactory = Callable[[], AgentProvider]
_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "hermes": HermesProvider,
    "nous": HermesProvider,
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "nebius": get_nebius_provider,
    "nebius-token-factory": get_nebius_provider,
    "openai-compatible": CustomProvider,
    "custom": CustomProvider,
}


def provider_names() -> tuple[str, ...]:
    """Return supported provider names in stable order."""
    return tuple(_PROVIDER_FACTORIES)


def get_provider(name: str | None = None) -> AgentProvider:
    """Resolve a provider from an argument or SUPRA_PROVIDER."""
    selected = (name or os.getenv("SUPRA_PROVIDER") or "hermes").strip().lower()
    factory = _PROVIDER_FACTORIES.get(selected)
    if factory is None:
        available = ", ".join(provider_names())
        raise ValueError(f"Unknown SUPRA_PROVIDER {selected!r}; available: {available}")
    return factory()


__all__ = [
    "AgentProvider",
    "CustomProvider",
    "HermesProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "ProviderError",
    "ProviderResponse",
    "ProviderUnavailable",
    "ToolInput",
    "ToolSpec",
    "get_nebius_provider",
    "get_provider",
    "is_nebius_available",
    "nebius_metadata",
    "provider_names",
]
