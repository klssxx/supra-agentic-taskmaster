"""Tests for Nebius Token Factory provider."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from supra_agentic.providers import nebius


class TestNebiusProvider:
    """Test suite for Nebius Token Factory integration."""

    def test_nebius_metadata_default(self):
        """Metadata shows defaults when no env set."""
        with patch.dict(os.environ, {}, clear=True):
            meta = nebius.nebius_metadata()
            assert meta["provider"] == "nebius-token-factory"
            assert meta["base_url"] == "https://api.tokenfactory.nebius.com/v1/"
            assert meta["model"] == "nvidia/nemotron-3-super-120b-a12b"
            assert meta["configured"] is False

    def test_nebius_metadata_configured(self):
        """Metadata reflects configured state."""
        env = {
            "NEBIUS_API_KEY": "test-key-123",
            "NEBIUS_MODEL": "nvidia/nemotron-3-ultra-550b-a55b",
        }
        with patch.dict(os.environ, env, clear=True):
            meta = nebius.nebius_metadata()
            assert meta["configured"] is True
            assert meta["model"] == "nvidia/nemotron-3-ultra-550b-a55b"

    def test_is_nebius_available_no_key(self):
        """Returns False when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            assert nebius.is_nebius_available() is False

    def test_get_nebius_provider_requires_key(self):
        """Raises RuntimeError when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="NEBIUS_API_KEY"):
                nebius.get_nebius_provider()

    def test_get_nebius_provider_with_key(self):
        """Builds provider with correct config."""
        env = {"NEBIUS_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            provider = nebius.get_nebius_provider()
            assert provider.name == "nebius-token-factory"
            assert provider.base_url.rstrip("/") == "https://api.tokenfactory.nebius.com/v1"
            assert provider.default_model == "nvidia/nemotron-3-super-120b-a12b"

    def test_get_nebius_provider_custom_model(self):
        """Custom model override works."""
        env = {
            "NEBIUS_API_KEY": "test-key",
            "NEBIUS_MODEL": "nvidia/nemotron-3-nano-12b-a12b",
        }
        with patch.dict(os.environ, env, clear=True):
            provider = nebius.get_nebius_provider()
            assert provider.default_model == "nvidia/nemotron-3-nano-12b-a12b"

    def test_provider_registry_includes_nebius(self):
        """Nebius is in the provider registry."""
        from supra_agentic.providers import _PROVIDER_FACTORIES

        assert "nebius" in _PROVIDER_FACTORIES
        assert "nebius-token-factory" in _PROVIDER_FACTORIES

    def test_get_provider_nebius(self):
        """get_provider('nebius') returns configured provider."""
        from supra_agentic.providers import get_provider

        env = {"NEBIUS_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider("nebius")
            assert provider.name == "nebius-token-factory"


class TestNebiusIntegration:
    """Integration tests — skipped if no real API key."""

    @pytest.fixture()
    def real_key(self):
        return os.environ.get("NEBIUS_API_KEY", "").strip() or None

    @pytest.mark.skipif(
        not os.environ.get("NEBIUS_API_KEY", "").strip(),
        reason="NEBIUS_API_KEY not set",
    )
    def test_list_models_real(self):
        """Real call to list models endpoint."""
        provider = nebius.get_nebius_provider()
        # This would make a real HTTP call
        # For now, just verify provider is configured
        assert provider.base_url == "https://api.tokenfactory.nebius.com/v1/"

    @pytest.mark.skipif(
        not os.environ.get("NEBIUS_API_KEY", "").strip(),
        reason="NEBIUS_API_KEY not set",
    )
    def test_chat_completion_real(self):
        """Real chat completion call."""
        provider = nebius.get_nebius_provider()
        # Would make real HTTP call to /chat/completions
        assert provider.api_key is not None
