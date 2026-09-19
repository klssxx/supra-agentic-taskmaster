"""Hermes/Nous provider backed by the local Hermes OpenAI-compatible proxy."""

from __future__ import annotations

import os

import httpx

from .openai_compatible import OpenAICompatibleProvider


class HermesProvider(OpenAICompatibleProvider):
    """Use Hermes' authenticated Nous session without embedding credentials.

    Hermes exposes a local OpenAI-compatible proxy. SUPRA talks only to that
    local boundary; the proxy owns OAuth, provider selection, and credential
    rotation. The proxy is intentionally not started automatically.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=(
                base_url
                or os.getenv("SUPRA_HERMES_BASE_URL")
                or os.getenv("HERMES_PROXY_URL")
                or "http://127.0.0.1:8645/v1"
            ),
            # The local proxy accepts a bearer token as a client boundary. It
            # is not a Nous credential and is never written to logs.
            api_key=api_key or os.getenv("SUPRA_HERMES_API_KEY") or "local",
            default_model=(
                default_model
                or os.getenv("SUPRA_HERMES_MODEL")
                or os.getenv("SUPRA_MODEL")
                or "auto"
            ),
            timeout=timeout,
            transport=transport,
            provider_name="hermes",
        )

    def metadata(self) -> dict[str, object]:
        data = super().metadata()
        data["upstream"] = "Nous Portal through Hermes proxy"
        data["proxy_start_command"] = "hermes proxy start --provider nous"
        return data

    def _resolve_model(self, requested: str | None) -> str:
        """Prefer a catalogued free model when the caller leaves it automatic."""
        candidate = (requested or self.default_model).strip()
        if candidate and candidate.lower() not in {"", "auto", "default"}:
            return candidate
        models = self.list_models()
        free_models = [model for model in models if model.lower().endswith(":free")]
        if free_models:
            return free_models[0]
        return models[0] if models else (candidate or "default")
