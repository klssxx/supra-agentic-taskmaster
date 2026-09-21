"""Provider contract tests for the provider-agnostic SUPRA runtime."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from supra_agentic.providers import (
    HermesProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    get_provider,
)
from supra_agentic.providers.base import ProviderError


def test_provider_registry_resolves_hermes_and_aliases() -> None:
    hermes = get_provider("hermes")
    nous = get_provider("nous")

    assert isinstance(hermes, HermesProvider)
    assert isinstance(nous, HermesProvider)
    assert hermes.name == "hermes"
    assert hermes.base_url == "http://127.0.0.1:8645/v1"


def test_provider_registry_resolves_ollama_without_network() -> None:
    provider = get_provider("ollama")

    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"
    assert provider.base_url == "http://127.0.0.1:11434/v1"


def test_provider_registry_uses_environment_for_custom_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPRA_PROVIDER", "openai-compatible")
    monkeypatch.setenv("SUPRA_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("SUPRA_MODEL", "local-model")

    provider = get_provider()

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "openai-compatible"
    assert provider.base_url == "http://127.0.0.1:9999/v1"
    assert provider.default_model == "local-model"


def test_openai_compatible_provider_parses_text_and_tool_calls() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "model-from-endpoint"}]})
        payload = json.loads(request.content)
        assert payload["model"] == "model-from-endpoint"
        assert payload["messages"][-1]["content"] == "Solve this"
        assert payload["tools"][0]["function"]["name"] == "record_checkpoint"
        return httpx.Response(
            200,
            json={
                "id": "chat-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Use a bounded checkpoint.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "record_checkpoint",
                                        "arguments": '{"project_id":"p-1"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="http://provider.test/v1",
        api_key="test-token",
        transport=httpx.MockTransport(handler),
    )
    response = provider.generate(
        [{"role": "user", "content": "Solve this"}],
        tools=[
            {
                "name": "record_checkpoint",
                "description": "Record a checkpoint",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    )

    assert response.provider == "openai-compatible"
    assert response.model == "model-from-endpoint"
    assert response.text == "Use a bounded checkpoint."
    assert response.tool_calls[0]["function"]["name"] == "record_checkpoint"
    assert requests[0].headers["authorization"] == "Bearer test-token"
    assert len(requests) == 2


def test_provider_rejects_http_errors_without_leaking_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="private credential material")

    provider = OpenAICompatibleProvider(
        base_url="http://provider.test/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError, match="HTTP 401") as exc_info:
        provider.generate([{"role": "user", "content": "hello"}], model="model")

    assert "private credential material" not in str(exc_info.value)


def test_generate_async_uses_same_contract() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "async ok"}}]})

    provider = OpenAICompatibleProvider(
        base_url="http://provider.test/v1",
        default_model="model",
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(provider.generate_async([{"role": "user", "content": "hello"}]))

    assert response.text == "async ok"
    assert response.model == "model"


def test_provider_rejects_embedded_url_credentials() -> None:
    with pytest.raises(ValueError, match="embedded credentials"):
        OpenAICompatibleProvider(base_url="https://user:password@example.test/v1")


def test_hermes_auto_model_prefers_free_catalog_entry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={"data": [{"id": "paid/model"}, {"id": "local/model:free"}]},
            )
        payload = json.loads(request.content)
        assert payload["model"] == "local/model:free"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = HermesProvider(
        base_url="http://provider.test/v1",
        transport=httpx.MockTransport(handler),
    )
    response = provider.generate([{"role": "user", "content": "hello"}])

    assert response.model == "local/model:free"
