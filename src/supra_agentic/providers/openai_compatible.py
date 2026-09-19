"""OpenAI-compatible HTTP provider used by local and cloud backends."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from .base import (
    AgentProvider,
    ProviderError,
    ProviderResponse,
    ProviderUnavailable,
    ToolInput,
    ToolSpec,
)


_AUTO_MODELS = {"", "auto", "default"}

# SUP-12: cota de tamano de respuesta (8 MiB) y log del motivo antes de
# devolver [] en list_models, para que una config mala no se lea como
# "sin modelos".
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Provider base URL must use http:// or https://")
    parsed = urlsplit(url)
    if parsed.username or parsed.password:
        raise ValueError("Provider base URL cannot contain embedded credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Provider base URL cannot contain query or fragment data")
    return url


def _tool_payload(tool: ToolInput) -> dict[str, Any]:
    if isinstance(tool, ToolSpec):
        return tool.as_openai_tool()
    if not isinstance(tool, Mapping):
        raise TypeError("Provider tools must be ToolSpec or mapping values")
    if tool.get("type") == "function" and isinstance(tool.get("function"), Mapping):
        return dict(tool)
    if "name" not in tool:
        raise ValueError("Provider tool mapping requires a name")
    return ToolSpec(
        name=str(tool["name"]),
        description=str(tool.get("description", "")),
        parameters=tool.get("parameters", {}),
    ).as_openai_tool()


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray, str)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


class OpenAICompatibleProvider(AgentProvider):
    """Provider for any endpoint implementing /chat/completions and /models."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
        provider_name: str = "openai-compatible",
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.default_model = (default_model or "").strip()
        self.timeout = (
            timeout if timeout is not None else _env_float("SUPRA_PROVIDER_TIMEOUT", 60.0)
        )
        if self.timeout <= 0:
            raise ValueError("Provider timeout must be greater than zero")
        self._transport = transport
        self._provider_name = provider_name
        self._cached_models: list[str] | None = None

    @property
    def name(self) -> str:
        return self._provider_name

    def metadata(self) -> dict[str, Any]:
        """Expose configuration that is safe to return from a health endpoint."""
        meta = {
            "name": self.name,
            "model": self.default_model or "auto",
            "configured": True,
            "protocol": "openai-compatible",
        }
        # SUP-12: la base_url se publica SOLO con env explicito
        # (SUPRA_EXPOSE_BASE_URL=1); por defecto se omite.
        if os.environ.get("SUPRA_EXPOSE_BASE_URL", "").strip() == "1":
            meta["base_url"] = self.base_url
        return meta

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json", "content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
            transport=self._transport,
        )

    def list_models(self) -> list[str]:
        """Discover models without failing generation when discovery is unsupported."""
        if self._cached_models is not None:
            return list(self._cached_models)
        try:
            with self._client() as client:
                response = client.get("/models")
        except httpx.HTTPError as exc:
            logger.warning("%s: GET /models failed (%s); returning no models", self.name, exc)
            return []
        if response.status_code != 200:
            logger.warning(
                "%s: GET /models returned HTTP %s; returning no models",
                self.name,
                response.status_code,
            )
            return []
        try:
            payload = response.json()
        except ValueError:
            logger.warning("%s: GET /models returned invalid JSON; returning no models", self.name)
            return []
        raw_models = payload.get("data", []) if isinstance(payload, Mapping) else []
        models = [
            str(item["id"]) for item in raw_models if isinstance(item, Mapping) and item.get("id")
        ]
        self._cached_models = models
        return list(models)

    def _resolve_model(self, requested: str | None) -> str:
        candidate = (requested or self.default_model).strip()
        if candidate and candidate.lower() not in _AUTO_MODELS:
            return candidate
        models = self.list_models()
        if models:
            return models[0]
        return candidate if candidate else "default"

    def generate(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[ToolInput] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        if not messages:
            raise ValueError("Provider generation requires at least one message")
        payload: dict[str, Any] = {
            "model": self._resolve_model(model),
            "messages": [dict(message) for message in messages],
        }
        if tools:
            payload["tools"] = [_tool_payload(tool) for tool in tools]
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            with self._client() as client:
                response = client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.name} endpoint is unavailable") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} provider returned HTTP {response.status_code}; check endpoint and credentials"
            )
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise ProviderError(
                f"{self.name} provider response exceeds {_MAX_RESPONSE_BYTES} bytes (SUP-12 limit)"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} provider returned invalid JSON") from exc
        if not isinstance(body, Mapping):
            raise ProviderError(f"{self.name} provider returned an invalid response object")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderError(f"{self.name} provider returned no choices")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise ProviderError(f"{self.name} provider returned no assistant message")
        raw_tool_calls = message.get("tool_calls", [])
        tool_calls = list(raw_tool_calls) if isinstance(raw_tool_calls, list) else []
        return ProviderResponse(
            text=_message_text(message.get("content")),
            tool_calls=tool_calls,
            raw=dict(body),
            provider=self.name,
            model=str(body.get("model") or payload["model"]),
        )
