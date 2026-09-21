from __future__ import annotations

import httpx
import pytest
from supra_agentic.providers import OpenAICompatibleProvider
from supra_agentic.providers.base import ProviderError
from supra_agentic.providers.openai_compatible import MAX_PROVIDER_RESPONSE_BYTES


def test_provider_metadata_does_not_expose_base_url() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://internal.example.test/v1", default_model="model"
    )
    metadata = provider.metadata()
    assert "base_url" not in metadata
    assert "internal.example.test" not in repr(metadata)


def test_list_models_failure_is_visible() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://provider.test/v1",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(503, text="private upstream failure")
        ),
    )
    with pytest.raises(ProviderError, match="HTTP 503") as raised:
        provider.list_models()
    assert "private upstream failure" not in str(raised.value)


def test_list_models_caches_success() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    provider = OpenAICompatibleProvider(
        base_url="http://provider.test/v1", transport=httpx.MockTransport(handler)
    )
    assert provider.list_models() == ["model-a"]
    assert provider.list_models() == ["model-a"]
    assert calls == 1


def test_generation_rejects_oversized_provider_response() -> None:
    oversized = b"{" + (b" " * MAX_PROVIDER_RESPONSE_BYTES) + b"}"
    provider = OpenAICompatibleProvider(
        base_url="http://provider.test/v1",
        default_model="model",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=oversized)),
    )
    with pytest.raises(ProviderError, match="exceeds"):
        provider.generate([{"role": "user", "content": "hello"}])
